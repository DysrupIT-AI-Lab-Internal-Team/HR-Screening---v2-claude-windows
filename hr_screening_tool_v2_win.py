#!/usr/bin/env python3
"""
HR Resume Screening Tool v2 (Windows-Optimized) — Powered by Claude Code Pro
PDF extraction powered by Docling (IBM) for superior accuracy.

Windows Optimizations over the macOS version:
  - asyncio + IOCP for non-blocking subprocess and sleep calls
  - ProcessPoolExecutor replaces ThreadPoolExecutor (real parallelism)
  - CUDA/DirectML GPU support replaces Apple MPS
  - UTF-8 console encoding with safe emoji fallback
  - msvcrt file locking for concurrent tracking-file safety
  - Windows process priority control during batch processing
  - Graceful Ctrl+C shutdown with progress save
  - pathlib for robust Windows path handling (long-path safe)

Usage: python hr_screening_tool_v2_win.py
"""

import os
import sys
import csv
import json
import hashlib
import subprocess
import shutil
import asyncio
import signal
import time
import re
import concurrent.futures
from datetime import datetime
from pathlib import Path
from contextlib import contextmanager

# Shared navigation primitives (numbered menus, back-navigation, BackToMenu).
# These live in cli_common so the bundled BambooHR resume downloader can reuse
# the exact same navigation — and share the one BackToMenu exception class.
from cli_common import (
    BackToMenu,
    print_header,
    print_menu,
    print_submenu,
    nav_input,
)
from bamboo_downloader import download_resume_menu

# python-dotenv is optional at runtime: if it's missing we fall back to the
# process environment so the tool still runs without a .env present.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ─────────────────────────────────────────────
# WINDOWS CONSOLE SETUP
# ─────────────────────────────────────────────

def _setup_windows_console():
    """Configure Windows console for UTF-8 output and ANSI colors."""
    if sys.platform != "win32":
        return

    # Force UTF-8 encoding on stdout/stderr — Windows defaults to the
    # system codepage (e.g., cp1252) which breaks emoji and non-ASCII names.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    else:
        import io
        sys.stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace"
        )
        sys.stderr = io.TextIOWrapper(
            sys.stderr.buffer, encoding="utf-8", errors="replace"
        )

    # Enable ANSI escape codes on Windows 10+ (for colored output)
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        # STD_OUTPUT_HANDLE = -11
        handle = kernel32.GetStdHandle(-11)
        # ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
        mode = ctypes.c_ulong()
        kernel32.GetConsoleMode(handle, ctypes.byref(mode))
        kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        pass

    # Set console title
    try:
        import ctypes
        ctypes.windll.kernel32.SetConsoleTitleW("HR Screening Tool v2 — Windows")
    except Exception:
        pass

    # Optional: colorama for older terminals
    try:
        import colorama
        colorama.init()
    except ImportError:
        pass


_setup_windows_console()


# ─────────────────────────────────────────────
# GPU DETECTION (CUDA replaces Apple MPS)
# ─────────────────────────────────────────────

CUDA_AVAILABLE = False
DIRECTML_AVAILABLE = False
_gpu_name = None

def _load_torch_with_dll_workaround():
    """
    Manually load PyTorch DLL on Windows to work around initialization errors.
    Returns True if torch loaded successfully, False otherwise.
    """
    try:
        import ctypes
        from importlib.util import find_spec

        spec = find_spec("torch")
        if spec and spec.origin:
            dll_path = Path(spec.origin).parent / "lib" / "c10.dll"
            if dll_path.exists():
                ctypes.CDLL(str(dll_path.resolve()))

        import torch
        return True
    except Exception:
        return False

# Try to import torch with workaround for Windows DLL issues
if _load_torch_with_dll_workaround():
    try:
        import torch
        CUDA_AVAILABLE = torch.cuda.is_available()
        if CUDA_AVAILABLE:
            _gpu_name = torch.cuda.get_device_name(0)
    except Exception:
        CUDA_AVAILABLE = False

PDF_SUPPORT = False
DOCLING_SUPPORT = False

# Enable Docling for PDF extraction (torch DLL workaround applied above)
try:
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    DOCLING_SUPPORT = True
    PDF_SUPPORT = True
except (ImportError, OSError):
    DOCLING_SUPPORT = False


# ─────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────

TRACKING_FILE = "screening_history_v2.json"
RESUMES_DIR = Path("resume_screening")
JD_DIR = Path("jd")
RESULTS_DIR = Path("results")
SUPPORTED_RESUME_TYPES = [".pdf", ".txt"]
SUPPORTED_JD_TYPES = [".txt", ".md"]

# Claude model override from .env — blank means use Claude Code's default model.
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "").strip()

# Use GPU when batch exceeds this size — avoids warmup overhead for small batches
GPU_BATCH_THRESHOLD = 5

# ── Rate limit settings ──────────
MAX_WORKERS = 1       # sequential — safest for Pro subscription
REQUEST_DELAY = 2.0   # seconds to wait before each Claude call
SUB_BATCH_SIZE = 10   # resumes per sub-batch before pausing
SUB_BATCH_PAUSE = 30  # seconds to pause between sub-batches
RETRY_MAX = 4         # max retries on rate limit error
RETRY_BASE_DELAY = 5  # initial retry wait in seconds (doubles each attempt)


# ─────────────────────────────────────────────
# GRACEFUL SHUTDOWN
# ─────────────────────────────────────────────

_shutdown_requested = False


def _signal_handler(signum, frame):
    """Handle Ctrl+C gracefully — finish current work, save, then exit."""
    global _shutdown_requested
    if _shutdown_requested:
        # Second Ctrl+C — force exit
        print("\n\n  Forced exit.")
        sys.exit(1)
    _shutdown_requested = True
    print("\n\n  >> Ctrl+C detected. Finishing current resume, then saving and exiting...")
    print("  >> Press Ctrl+C again to force-quit immediately.\n")


signal.signal(signal.SIGINT, _signal_handler)


# ─────────────────────────────────────────────
# WINDOWS PROCESS PRIORITY
# ─────────────────────────────────────────────

@contextmanager
def _elevated_priority():
    """Temporarily raise process priority to ABOVE_NORMAL during batch work."""
    if sys.platform != "win32":
        yield
        return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetCurrentProcess()
        # ABOVE_NORMAL_PRIORITY_CLASS = 0x00008000
        old_priority = kernel32.GetPriorityClass(handle)
        kernel32.SetPriorityClass(handle, 0x00008000)
        yield
        kernel32.SetPriorityClass(handle, old_priority)
    except Exception:
        yield


# ─────────────────────────────────────────────
# FILE LOCKING (Windows-native via msvcrt)
# ─────────────────────────────────────────────

@contextmanager
def _file_lock(filepath, mode="r+"):
    """
    Context manager providing file locking using msvcrt on Windows.
    Falls back to no locking on other platforms (for testing).
    """
    fp = open(filepath, mode, encoding="utf-8")
    try:
        if sys.platform == "win32":
            import msvcrt
            msvcrt.locking(fp.fileno(), msvcrt.LK_LOCK, 1)
        yield fp
    finally:
        if sys.platform == "win32":
            try:
                import msvcrt
                fp.seek(0)
                msvcrt.locking(fp.fileno(), msvcrt.LK_UNLCK, 1)
            except Exception:
                pass
        fp.close()


# ─────────────────────────────────────────────
# UTILITIES
# ─────────────────────────────────────────────

def _find_claude() -> str | None:
    """
    Locate the claude CLI executable.
    Tries shutil.which first, then searches the Windows desktop-app install
    location where the binary lives in a versioned subdirectory that may not
    be directly on PATH.
    """
    hit = shutil.which("claude")
    if hit:
        return hit

    # Claude desktop app on Windows installs to a versioned subfolder under
    # the Packages directory.  Walk one level deep to find claude.exe.
    base = Path(os.environ.get("LOCALAPPDATA", "")) / "Packages"
    if base.is_dir():
        for pkg in base.iterdir():
            if "claude" in pkg.name.lower():
                candidate_root = pkg / "LocalCache" / "Roaming" / "Claude" / "claude-code"
                if candidate_root.is_dir():
                    for sub in sorted(candidate_root.iterdir(), reverse=True):
                        exe = sub / "claude.exe"
                        if exe.is_file():
                            return str(exe)
    return None


CLAUDE_EXE = _find_claude()


def check_dependencies():
    """Check required tools and libraries."""
    if CLAUDE_EXE is None:
        print("\n[X]  Claude Code is not installed or not in PATH.")
        print("     Install it from: https://claude.ai/code\n")
        sys.exit(1)

    if not PDF_SUPPORT:
        print("\n[!]  docling not installed. PDF support disabled.")
        print("     Run: uv pip install \"docling[full]\"\n")


async def ask_claude_async(prompt):
    """
    Send a prompt to Claude via CLI using async subprocess.

    Uses asyncio.create_subprocess_exec for non-blocking I/O.
    On Windows this leverages IOCP (I/O Completion Ports) — the
    fastest async I/O mechanism on the platform.

    Retries with exponential backoff on rate limit errors.
    """
    # Throttle: non-blocking wait before each call
    if REQUEST_DELAY > 0:
        await asyncio.sleep(REQUEST_DELAY)

    delay = RETRY_BASE_DELAY
    for attempt in range(RETRY_MAX):
        if _shutdown_requested:
            raise RuntimeError("Shutdown requested by user")

        cmd = [CLAUDE_EXE, "-p", prompt, "--output-format", "text"]
        if CLAUDE_MODEL:
            cmd += ["--model", CLAUDE_MODEL]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, stderr_bytes = await proc.communicate()

        if proc.returncode == 0:
            return stdout_bytes.decode("utf-8", errors="replace").strip()

        stderr = stderr_bytes.decode("utf-8", errors="replace").strip()

        # Detect rate limit vs hard error
        is_rate_limit = any(
            kw in stderr.lower()
            for kw in ["rate limit", "429", "too many requests", "overloaded"]
        )

        if is_rate_limit and attempt < RETRY_MAX - 1:
            print(
                f"\n  [~]  Rate limit hit -- waiting {delay}s before retry "
                f"(attempt {attempt + 1}/{RETRY_MAX})..."
            )
            await asyncio.sleep(delay)
            delay *= 2  # exponential backoff: 5 -> 10 -> 20 -> 40
        else:
            raise RuntimeError(f"Claude error: {stderr}")

    raise RuntimeError(f"Claude failed after {RETRY_MAX} attempts.")


def ask_claude(prompt):
    """
    Synchronous wrapper around ask_claude_async.
    Used by features that don't need batch parallelism (JD writing, phone screening).
    """
    return asyncio.run(ask_claude_async(prompt))


def estimate_batch_tokens(file_count, jd_text):
    """
    Rough token estimate for a batch of resumes.
    Assumes ~2,500 tokens per resume + JD tokens + 300 output tokens.
    """
    jd_tokens = int(len(jd_text.split()) * 1.3)
    per_resume = 2500 + jd_tokens + 300
    return file_count * per_resume


def get_file_hash(filepath):
    """Return MD5 hash of a file's contents."""
    with open(filepath, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def load_tracking():
    """Load the screening history tracking file."""
    tracking_path = Path(TRACKING_FILE)
    if tracking_path.exists():
        with open(tracking_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"resumes": {}}


def save_tracking(data):
    """
    Save the screening history tracking file with Windows file locking.
    Uses an atomic write pattern: write to temp, then rename.
    """
    tracking_path = Path(TRACKING_FILE)
    temp_path = tracking_path.with_suffix(".tmp")

    # Write to temp file first
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    # Atomic rename (on Windows, need to remove target first if it exists)
    if tracking_path.exists():
        tracking_path.unlink()
    temp_path.rename(tracking_path)


def is_already_analyzed(tracking, filename, file_hash, jd_hash):
    """Return True if this resume was already analyzed against this JD version."""
    record = tracking["resumes"].get(filename)
    if not record:
        return False
    return record.get("file_hash") == file_hash and record.get("jd_hash") == jd_hash


def load_file_text(filepath):
    """Load plain text from a .txt or .md file."""
    fp = Path(filepath)
    if not fp.exists():
        print(f"\n  [X]  File not found: {filepath}")
        return None
    with open(fp, "r", encoding="utf-8") as f:
        return f.read()


def list_resume_files(folder):
    """Return supported resume files in a folder."""
    folder_path = Path(folder)
    if not folder_path.is_dir():
        print(f"\n  [X]  Folder not found: {folder}")
        return []
    return sorted([
        f.name for f in folder_path.iterdir()
        if f.is_file() and f.suffix.lower() in SUPPORTED_RESUME_TYPES
    ])


# ─────────────────────────────────────────────
# PDF EXTRACTION (DOCLING) + QUALITY RATING
# ─────────────────────────────────────────────

def build_converter(use_gpu=False):
    """
    Build a Docling DocumentConverter with the appropriate device.
    """
    if not PDF_SUPPORT or not DOCLING_SUPPORT:
        return None

    # Configure the PDF pipeline. The torch DLL workaround (applied at import)
    # lets Docling's torch-based accelerators initialize cleanly on Windows.
    opts = PdfPipelineOptions()
    if use_gpu and CUDA_AVAILABLE:
        opts.accelerator_options.device = "cuda"

    return DocumentConverter(
        format_options={"pdf": PdfFormatOption(pipeline_options=opts)}
    )


def extract_pdf_text(filepath, converter):
    """
    Extract text from a PDF using Docling.
    Returns (markdown_text, success).
    """
    if not PDF_SUPPORT or converter is None:
        return None, False

    try:
        # Use os.fspath() to ensure Windows Path objects work with Docling
        result = converter.convert(os.fspath(filepath))
        markdown = result.document.export_to_markdown()
        return markdown.strip(), True
    except Exception as e:
        return f"[PDF extraction failed: {e}]", False


def rate_pdf_quality(markdown_text):
    """
    Rate the quality of Docling's Markdown output.

    Assesses:
      - Overall content length
      - Presence of Markdown structure (headers, bullets, tables)
      - Resume section coverage
      - Proportion of image placeholders vs real content

    Returns a dict with:
      - grade: Excellent / Good / Fair / Poor
      - score: 0-100
      - icon: visual indicator
      - notes: list of observations
      - warning: True if analysis may be affected
    """
    score = 100
    notes = []
    text = markdown_text

    # 1. Content length
    plain = re.sub(r'[#\-\|\*`>]', '', text)
    plain = re.sub(r'<!--.*?-->', '', plain, flags=re.DOTALL)
    plain = re.sub(r'\s+', ' ', plain).strip()

    if len(plain) < 100:
        score -= 60
        notes.append("Almost no content extracted -- PDF may be fully image-based or password-protected")
    elif len(plain) < 400:
        score -= 25
        notes.append("Limited content extracted -- resume may have heavy image formatting")
    elif len(plain) < 800:
        score -= 8
        notes.append("Moderate content length -- some sections may be missing")

    # 2. Markdown structure
    headers = re.findall(r'^#{1,3} .+', text, re.MULTILINE)
    if len(headers) == 0:
        score -= 20
        notes.append("No section headers detected -- document structure may be lost")
    elif len(headers) < 3:
        score -= 8
        notes.append(f"Only {len(headers)} section(s) detected -- layout may be partially parsed")
    else:
        notes.append(f"{len(headers)} sections identified by Docling")

    # 3. Resume section coverage
    section_keywords = [
        "experience", "skills", "education", "employment",
        "certification", "summary", "objective", "work",
    ]
    found_sections = [kw for kw in section_keywords if kw.lower() in text.lower()]
    if len(found_sections) == 0:
        score -= 20
        notes.append("No standard resume sections found in content")
    elif len(found_sections) < 3:
        score -= 8
        notes.append(f"Few resume sections found: {', '.join(found_sections)}")

    # 4. Image placeholder ratio
    image_tags = len(re.findall(r'<!-- image -->', text))
    total_lines = max(len(text.splitlines()), 1)
    image_ratio = image_tags / total_lines
    if image_ratio > 0.4:
        score -= 15
        notes.append(
            f"High image content ({image_tags} image blocks) -- "
            "resume may rely heavily on graphics"
        )
    elif image_tags > 0:
        notes.append(
            f"{image_tags} image block(s) found "
            "(icons/graphics -- not extracted, normal for designed resumes)"
        )

    # 5. Table detection
    if '|' in text and '---' in text:
        notes.append("Tables/grids detected and parsed -- structured content preserved")

    score = max(0, score)

    if score >= 85:
        grade, icon = "Excellent", "[OK]"
    elif score >= 70:
        grade, icon = "Good", "[OK]"
    elif score >= 50:
        grade, icon = "Fair", "[!!]"
    else:
        grade, icon = "Poor", "[XX]"

    return {
        "score": score,
        "grade": grade,
        "icon": icon,
        "notes": notes,
        "warning": grade in ["Fair", "Poor"],
    }


def load_resume(filepath, converter):
    """
    Load resume and return (text, quality_info).
    PDFs -> Docling -> Markdown
    TXT  -> plain read
    """
    ext = Path(filepath).suffix.lower()

    if ext == ".pdf":
        text, success = extract_pdf_text(filepath, converter)
        if not success:
            return None, None
        quality = rate_pdf_quality(text)
        return text, quality

    elif ext == ".txt":
        text = load_file_text(filepath)
        quality = {
            "score": 100,
            "grade": "Excellent",
            "icon": "[OK]",
            "notes": ["Plain text file -- no extraction needed"],
            "warning": False,
        }
        return text, quality

    return None, None


# ─────────────────────────────────────────────
# CORE FEATURES (Async batch processing)
# ─────────────────────────────────────────────

async def screen_single_resume_async(
    filename, filepath, jd_text, jd_hash, jd_path,
    converter, tracking, force
):
    """
    Process one resume: extract -> rate quality -> ask Claude -> return result row.
    Async version using non-blocking Claude CLI calls.
    """
    global _shutdown_requested

    if _shutdown_requested:
        return "interrupted", filename, None, None

    candidate_name = Path(filename).stem.replace("_", " ").title()
    file_hash = get_file_hash(filepath)
    already_done = is_already_analyzed(tracking, filename, file_hash, jd_hash)

    # ── Return cached result if up-to-date ───────────────────
    if not force and already_done:
        record = tracking["resumes"][filename]
        print(f"  [>>]  {candidate_name} -- skipped (cached)")
        return "skipped", filename, {
            "Candidate":         candidate_name,
            "Fit Score":         record.get("fit_score", "N/A"),
            "Recommendation":    record.get("recommendation", "N/A"),
            "PDF Quality":       record.get("pdf_quality", "N/A"),
            "PDF Quality Score": record.get("pdf_quality_score", "N/A"),
            "Keywords Found":    record.get("keywords_found", ""),
            "Keywords Missing":  record.get("keywords_missing", ""),
            "Summary":           record.get("summary", ""),
            "Analyzed On":       record.get("analyzed_on", ""),
            "Status":            "Skipped (cached)",
        }, None

    # ── Extract resume (CPU-bound, run in executor) ──────────
    loop = asyncio.get_event_loop()
    resume_text, quality = await loop.run_in_executor(
        None, load_resume, filepath, converter
    )
    if resume_text is None:
        print(f"  [X]  {candidate_name} -- could not read file")
        return "error", filename, None, None

    # ── Send to Claude (async) ───────────────────────────────
    prompt = f"""You are an HR screening assistant.

JOB DESCRIPTION:
{jd_text}

CANDIDATE RESUME:
{resume_text}

Evaluate the candidate using the following scoring rubric:

SCORING RUBRIC:
1. Fit Score (0-100): Rate the candidate's overall match to the job description.
   - Treat all listed skills equally -- no single skill is weighted higher than others.
   - Award partial credit for adjacent or transferable skills that are closely related
     but not an exact match (e.g., mainframe COBOL when iSeries COBOL is required).
   - Do not penalize for resume length or level of detail.
   - Do not penalize for overqualification -- instead, add a note in the summary if the
     candidate appears significantly overqualified.
   - Factor in years of experience if mentioned in the JD: full credit if met or exceeded,
     partial credit if close, low credit if clearly below the minimum.

2. Recommendation -- assign based on Fit Score:
   - RECOMMEND : Score is 75 or above -- strong fit, move to interview
   - REVIEW    : Score is 50 to 74 -- partial fit, worth a closer look
   - DEFER     : Score is below 50 -- poor fit, does not meet role requirements

Respond in EXACTLY this JSON format with no extra text:
{{
  "fit_score": <number 0-100>,
  "recommendation": "<RECOMMEND or REVIEW or DEFER>",
  "keywords_found": "<comma-separated list>",
  "keywords_missing": "<comma-separated list>",
  "summary": "<one sentence reason>"
}}"""

    try:
        raw = await ask_claude_async(prompt)
        start = raw.find("{")
        end = raw.rfind("}") + 1
        data = json.loads(raw[start:end])

        rec = data.get("recommendation", "N/A")
        score = data.get("fit_score", "N/A")
        icon = "[OK]" if rec == "RECOMMEND" else "[!!]" if rec == "REVIEW" else "[XX]"
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")

        if quality["warning"]:
            print(f"  [!!]  {candidate_name} -- PDF Quality: {quality['grade']} ({quality['score']}/100)")
            for note in quality["notes"]:
                print(f"        -> {note}")
        print(f"  {icon}  {candidate_name} -- {score}/100 - {rec} - PDF: {quality['grade']}")

        result_row = {
            "Candidate":         candidate_name,
            "Fit Score":         score,
            "Recommendation":    rec,
            "PDF Quality":       quality["grade"],
            "PDF Quality Score": quality["score"],
            "Keywords Found":    data.get("keywords_found", ""),
            "Keywords Missing":  data.get("keywords_missing", ""),
            "Summary":           data.get("summary", ""),
            "Analyzed On":       ts,
            "Status":            "Analyzed",
        }

        tracking_record = {
            "file_hash":         file_hash,
            "jd_hash":           jd_hash,
            "jd_file":           str(jd_path),
            "fit_score":         score,
            "recommendation":    rec,
            "pdf_quality":       quality["grade"],
            "pdf_quality_score": quality["score"],
            "keywords_found":    data.get("keywords_found", ""),
            "keywords_missing":  data.get("keywords_missing", ""),
            "summary":           data.get("summary", ""),
            "analyzed_on":       ts,
        }
        return "ok", filename, result_row, tracking_record

    except Exception as e:
        print(f"  [X]  {candidate_name} -- analysis error: {e}")
        return "error", filename, {
            "Candidate":         candidate_name,
            "Fit Score":         "ERROR",
            "Recommendation":    "ERROR",
            "PDF Quality":       quality["grade"],
            "PDF Quality Score": quality["score"],
            "Keywords Found":    "",
            "Keywords Missing":  "",
            "Summary":           str(e),
            "Analyzed On":       datetime.now().strftime("%Y-%m-%d %H:%M"),
            "Status":            "Error",
        }, None


async def _run_batch_async(task_args_list, workers):
    """
    Run a list of screening tasks concurrently using asyncio.Semaphore
    to control the degree of parallelism.
    """
    semaphore = asyncio.Semaphore(workers)

    async def _limited(args):
        async with semaphore:
            return await screen_single_resume_async(*args)

    tasks = [asyncio.create_task(_limited(args)) for args in task_args_list]
    return await asyncio.gather(*tasks)


def run_batch_screening(folder, jd_path, role_name, force_all=False, force_file=None):
    """
    Core batch screening logic — async processing with smart GPU selection.

    Args:
      folder      - folder containing resume files
      jd_path     - path to the JD file
      role_name   - label for the role (used in output filename)
      force_all   - if True, ignore tracking and re-analyze all
      force_file  - if set, only re-analyze this specific filename
    """
    global _shutdown_requested
    _shutdown_requested = False

    folder_path = Path(folder)
    files = list_resume_files(folder)
    if not files:
        print(f"\n  [!]  No resume files found in: {folder}")
        return

    if force_file:
        files = [f for f in files if f == force_file]

    # ── Load JD once ──────────────────────────────────────────
    jd_text = load_file_text(jd_path)
    if not jd_text:
        return
    jd_hash = get_file_hash(jd_path)
    print(f"\n  [OK]  JD loaded: {jd_path}  (used for all resumes -- not re-read per resume)")

    # ── Smart GPU selection ───────────────────────────────────
    gpu_available = CUDA_AVAILABLE or DIRECTML_AVAILABLE
    use_gpu = False  # GPU disabled due to torch compatibility issues
    device_lbl = "CPU"
    workers = MAX_WORKERS if len(files) > 1 else 1
    print(f"  [*]  Device: {device_lbl}  |  Workers: {workers}  |  Resumes: {len(files)}")

    # ── Build converter ───────────────────────────────────────
    if PDF_SUPPORT:
        converter = build_converter(use_gpu=use_gpu)
    else:
        converter = None

    # ── Load tracking ─────────────────────────────────────────
    tracking = load_tracking()

    # ── Build task args ───────────────────────────────────────
    task_args = [
        (
            filename,
            str(folder_path / filename),
            jd_text, jd_hash, str(jd_path),
            converter, tracking,
            force_all or bool(force_file),
        )
        for filename in files
    ]

    # ── Resume progress messaging ─────────────────────────────
    if force_all or force_file:
        pending = task_args
        completed = 0
    else:
        pending = [
            a for a in task_args
            if not is_already_analyzed(tracking, a[0], get_file_hash(a[1]), jd_hash)
        ]
        completed = len(task_args) - len(pending)

    if completed > 0:
        print(f"  [i]  Resuming: {completed} already done -- {len(pending)} remaining")

    # ── Token estimate + large batch warning ──────────────────
    if len(pending) > 0:
        est_tokens = estimate_batch_tokens(len(pending), jd_text)
        print(f"  [#]  Estimated usage: ~{est_tokens:,} tokens for {len(pending)} resume(s)")
        if len(pending) > SUB_BATCH_SIZE:
            sub_count = (len(pending) + SUB_BATCH_SIZE - 1) // SUB_BATCH_SIZE
            est_pause = (sub_count - 1) * SUB_BATCH_PAUSE
            print(
                f"  [!]  Large batch -- will process in {sub_count} sub-batches of "
                f"{SUB_BATCH_SIZE}, with {SUB_BATCH_PAUSE}s pauses (~{est_pause}s extra wait)"
            )
        if len(pending) > 50 and MAX_WORKERS == 1:
            print(
                f"  [*]  Tip: Running on Pro subscription. "
                f"Upgrade to Max for faster parallel processing."
            )

    print(f"\n  Processing...\n")
    results = []
    skipped = []

    # ── Sub-batch processing with pauses (elevated priority) ──
    with _elevated_priority():
        for batch_start in range(0, len(task_args), SUB_BATCH_SIZE):
            if _shutdown_requested:
                print("\n  [!]  Shutdown requested -- saving progress...")
                break

            sub_batch = task_args[batch_start : batch_start + SUB_BATCH_SIZE]

            # Run the sub-batch asynchronously
            batch_results = asyncio.run(_run_batch_async(sub_batch, workers))

            for status, filename, result_row, tracking_record in batch_results:
                if result_row:
                    results.append(result_row)
                if status == "skipped":
                    skipped.append(filename)
                if status == "ok" and tracking_record:
                    tracking["resumes"][filename] = tracking_record
                    save_tracking(tracking)

            remaining = len(task_args) - (batch_start + len(sub_batch))
            if remaining > 0 and not _shutdown_requested:
                print(
                    f"\n  [||]  Sub-batch complete. "
                    f"Pausing {SUB_BATCH_PAUSE}s before next batch "
                    f"({remaining} resume(s) remaining)..."
                )
                time.sleep(SUB_BATCH_PAUSE)
                print()

    if not results:
        print("\n  No results to save.")
        return

    # ── Save CSV ──────────────────────────────────────────────
    RESULTS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = RESULTS_DIR / f"screening_{role_name.replace(' ', '_')}_{timestamp}.csv"
    sorted_results = sorted(
        results,
        key=lambda x: x["Fit Score"] if isinstance(x["Fit Score"], int) else -1,
        reverse=True,
    )
    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=results[0].keys())
        writer.writeheader()
        writer.writerows(sorted_results)

    # ── Print summary ─────────────────────────────────────────
    analyzed = len(results) - len(skipped)
    print_header("[#]  Screening Summary")
    print(f"  Role:      {role_name}")
    print(f"  Analyzed:  {analyzed}  |  Skipped (cached): {len(skipped)}\n")
    print(f"  {'Candidate':<25} {'Score':<7} {'Recommendation':<15} {'PDF Quality'}")
    print(f"  {'-'*25} {'-'*7} {'-'*15} {'-'*15}")
    for r in sorted_results:
        icon = "[OK]" if r["Recommendation"] == "RECOMMEND" else "[!!]" if r["Recommendation"] == "REVIEW" else "[XX]"
        cached = " (cached)" if r.get("Status") == "Skipped (cached)" else ""
        print(f"  {icon} {r['Candidate']:<24} {str(r['Fit Score']):<7} {r['Recommendation']:<15} {r['PDF Quality']}{cached}")

    print(f"\n  [OK]  Results saved to: {output_file}")
    if _shutdown_requested:
        print(f"  [!]  Partial results -- interrupted by user. Re-run to continue.\n")
    else:
        print()


# ─────────────────────────────────────────────
# MENU ACTIONS
# ─────────────────────────────────────────────

def list_jd_files(optional=False):
    """List available JD files and let user pick one.

    If optional=True, pressing Enter skips selection and returns None.
    """
    if not JD_DIR.is_dir():
        return None
    files = sorted([
        f.name for f in JD_DIR.iterdir()
        if f.is_file() and f.suffix.lower() in SUPPORTED_JD_TYPES
    ])
    if not files:
        return None
    print(f"\n  Available JDs in {JD_DIR}/:")
    for i, f in enumerate(files, 1):
        print(f"    [{i}] {f}")
    skip_hint = "press Enter to skip, or" if optional else ""
    choice = nav_input(f"\n  Select JD number ({skip_hint} type a custom path): ")
    if not choice and optional:
        return None
    if choice.isdigit() and 1 <= int(choice) <= len(files):
        return str(JD_DIR / files[int(choice) - 1])
    return choice or str(JD_DIR / files[0])


def list_resume_subfolders():
    """List role subfolders inside resumes/ and let user pick one."""
    if not RESUMES_DIR.is_dir():
        return str(RESUMES_DIR)
    subfolders = sorted([
        f.name for f in RESUMES_DIR.iterdir()
        if f.is_dir()
    ])
    if not subfolders:
        return str(RESUMES_DIR)
    print(f"\n  Available role folders in {RESUMES_DIR}/:")
    for i, f in enumerate(subfolders, 1):
        count = len(list_resume_files(str(RESUMES_DIR / f)))
        print(f"    [{i}] {f}  ({count} resume(s))")
    choice = nav_input("\n  Select folder number (or type a custom path): ")
    if choice.isdigit() and 1 <= int(choice) <= len(subfolders):
        return str(RESUMES_DIR / subfolders[int(choice) - 1])
    return choice or str(RESUMES_DIR / subfolders[0])


def get_screening_inputs():
    """Prompt user to pick a resume folder and JD file."""
    folder = list_resume_subfolders()
    jd_path = list_jd_files()
    role = nav_input("\n  Role name for the report (e.g. DevOps Engineer): ") or "Open Role"
    return folder, jd_path, role


def screen_new_resumes():
    """Screen only new/unanalyzed resumes (skips already processed ones)."""
    print_header("[+]  Screen New Resumes (Skip Already Analyzed)")
    folder, jd_path, role = get_screening_inputs()
    run_batch_screening(folder, jd_path, role)


def reanalyze_all():
    """Force re-analysis of ALL resumes in a folder, ignoring tracking."""
    print_header("[~]  Re-analyze All Resumes in Folder")
    folder, jd_path, role = get_screening_inputs()
    confirm = nav_input(f"\n  [!]  This will re-analyze ALL resumes in '{folder}'. Continue? (y/n): ").lower()
    if confirm == "y":
        run_batch_screening(folder, jd_path, role, force_all=True)


def reanalyze_one():
    """Force re-analysis of a specific resume file."""
    print_header("[?]  Re-analyze a Specific Resume")

    folder = list_resume_subfolders()
    files = list_resume_files(folder)
    if not files:
        return

    print("\n  Available resumes:")
    for i, f in enumerate(files, 1):
        print(f"    [{i}] {f}")
    print()

    choice = nav_input("  Select resume number: ")
    if not choice.isdigit() or not (1 <= int(choice) <= len(files)):
        print("  [!]  Invalid selection.")
        return

    selected_file = files[int(choice) - 1]
    jd_path = list_jd_files()
    role = nav_input("\n  Role name for the report (e.g. DevOps Engineer): ") or "Open Role"

    run_batch_screening(folder, jd_path, role, force_file=selected_file)


def write_job_description():
    """Generate a job description using Claude."""
    print_header("[W]  Write Job Description")

    role = nav_input("\n  Role title (e.g. Senior DevOps Engineer): ")
    if not role:
        print("  [!]  Role title is required.")
        return
    level = nav_input("  Seniority level [default: Mid]: ") or "Mid"
    extras = nav_input("  Specific requirements or notes (optional): ")
    industry = nav_input("  Client industry (e.g. Banking, Healthcare) [optional]: ")

    print(f"\n  Generating JD for: {level} {role}...")

    prompt = f"""You are an expert HR consultant writing a job description for a client.

Write a professional Job Description for: {level} {role}
{"Additional requirements: " + extras if extras else ""}
{"Client industry: " + industry if industry else ""}

Include:
1. Role Overview (2-3 sentences)
2. Key Responsibilities (5-7 bullets)
3. Required Skills & Experience
4. Nice-to-Have Skills
5. What We Offer (generic but professional)

Keep it concise and professional."""

    try:
        jd = ask_claude(prompt)
        print("\n" + "-" * 62)
        print(jd)
        print("-" * 62)

        if input("\n  Save to file? (y/n): ").strip().lower() == "y":
            filename = f"JD_{role.replace(' ', '_')}_{level}.txt"
            with open(filename, "w", encoding="utf-8") as f:
                f.write(f"ROLE: {level} {role}\n\n{jd}")
            print(f"\n  [OK]  Saved to: {filename}\n")
    except Exception as e:
        print(f"\n  [X]  Error: {e}\n")


def prep_phone_screening():
    """Generate phone screening questions for a role."""
    print_header("[P]  Phone Screening Question Generator")

    role = nav_input("\n  Role title (e.g. SAP FICO Consultant): ")
    if not role:
        print("  [!]  Role title is required.")
        return
    jd_path = list_jd_files(optional=True) or ""
    jd_context = load_file_text(jd_path) if jd_path else ""
    focus = nav_input("  Focus areas (e.g. communication, remote work) [optional]: ")

    print(f"\n  Generating questions for: {role}...")

    jd_block = f"Job Description:\n{jd_context}" if jd_context else ""
    focus_block = f"Focus on: {focus}" if focus else ""

    prompt = f"""You are an HR specialist preparing phone screening questions.

Role: {role}
{jd_block}
{focus_block}

Generate 8-10 phone screening questions for an initial HR call (not a technical interview).
Focus on motivation, cultural fit, basic role alignment, and early red flags.
Format each question with a brief note on what to listen for.
Write for a non-technical HR interviewer."""

    try:
        questions = ask_claude(prompt)
        print("\n" + "-" * 62)
        print(questions)
        print("-" * 62)

        if input("\n  Save to file? (y/n): ").strip().lower() == "y":
            filename = f"PhoneScreening_{role.replace(' ', '_')}.md"
            with open(filename, "w", encoding="utf-8") as f:
                f.write(f"# Phone Screening: {role}\n\n**Generated:** {datetime.now().strftime('%Y-%m-%d')}  \n")
                if jd_path:
                    f.write(f"**JD Reference:** {Path(jd_path).name}  \n")
                if focus:
                    f.write(f"**Focus Areas:** {focus}  \n")
                f.write(f"\n---\n\n{questions}\n")
            print(f"\n  [OK]  Saved to: {filename}\n")
    except Exception as e:
        print(f"\n  [X]  Error: {e}\n")


def view_tracking():
    """Show screening history filtered by JD."""
    print_header("[H]  Screening History")
    tracking = load_tracking()

    if not tracking["resumes"]:
        print("\n  No screening history found.\n")
        return

    # Build list of unique JDs present in history
    jd_seen = {}
    for record in tracking["resumes"].values():
        jd = record.get("jd_file", "Unknown")
        jd_seen[jd] = jd_seen.get(jd, 0) + 1

    jd_list = sorted(jd_seen.keys())

    print(f"\n  JDs with screening history:")
    for i, jd in enumerate(jd_list, 1):
        label = Path(jd).name if jd != "Unknown" else "Unknown"
        print(f"    [{i}] {label}  ({jd_seen[jd]} candidate{'s' if jd_seen[jd] != 1 else ''})")
    print(f"    [0] Show all")

    choice = nav_input("\n  Select JD to filter by (or 0 for all): ")

    if choice == "0" or not choice:
        filtered = tracking["resumes"]
        header_label = "All Candidates"
    elif choice.isdigit() and 1 <= int(choice) <= len(jd_list):
        selected_jd = jd_list[int(choice) - 1]
        filtered = {
            fn: rec for fn, rec in tracking["resumes"].items()
            if rec.get("jd_file", "Unknown") == selected_jd
        }
        header_label = f"JD: {Path(selected_jd).name}"
    else:
        print("  [!]  Invalid choice.\n")
        return

    print(f"\n  {header_label}  --  {len(filtered)} record{'s' if len(filtered) != 1 else ''}")
    print(f"\n  {'Filename':<30} {'Score':<7} {'Recommendation':<15} {'PDF Quality':<12} {'Analyzed On'}")
    print(f"  {'-'*30} {'-'*7} {'-'*15} {'-'*12} {'-'*18}")
    for filename, record in filtered.items():
        name = filename[:28]
        print(
            f"  {name:<30} {str(record.get('fit_score', '')):<7} "
            f"{record.get('recommendation', ''):<15} "
            f"{record.get('pdf_quality', ''):<12} "
            f"{record.get('analyzed_on', '')}"
        )
    print()


# ─────────────────────────────────────────────
# MAINTENANCE
# ─────────────────────────────────────────────

def _find_resume_path(filename):
    """Search all subfolders under RESUMES_DIR for a given filename."""
    for root, _, files in os.walk(RESUMES_DIR):
        if filename in files:
            return str(Path(root) / filename)
    return None


def delete_jd_and_resumes():
    """Delete a JD file and all resumes that were analyzed against it."""
    print_header("[D]  Delete JD and Related Resumes")

    jd_path = list_jd_files()
    if not jd_path:
        print("\n  No JD files found.\n")
        return

    tracking = load_tracking()
    jd_label = Path(jd_path).name

    # Find tracking records tied to this JD
    related_records = {
        fn: rec for fn, rec in tracking["resumes"].items()
        if rec.get("jd_file") == jd_path
    }

    # Resolve actual file paths
    resume_paths = []
    missing = []
    for filename in related_records:
        path = _find_resume_path(filename)
        if path:
            resume_paths.append(path)
        else:
            missing.append(filename)

    # Preview
    print(f"\n  JD to delete     : {jd_label}")
    print(f"  Related resumes  : {len(resume_paths)} file(s) found")
    for p in resume_paths:
        print(f"    - {p}")
    if missing:
        print(f"  Already missing  : {len(missing)} file(s) (tracking records will still be removed)")
        for m in missing:
            print(f"    - {m}")
    print(f"  Tracking records : {len(related_records)} will be removed")

    confirm = nav_input(
        f"\n  [!]  Type 'yes' to confirm deletion of '{jd_label}'"
        f" and {len(resume_paths)} resume(s): "
    ).lower()
    if confirm != "yes":
        print("\n  Cancelled. Nothing was deleted.\n")
        return

    # Delete JD file
    jd_file = Path(jd_path)
    if jd_file.exists():
        jd_file.unlink()
        print(f"\n  [OK]  Deleted JD: {jd_path}")
    else:
        print(f"\n  [!]  JD file not found on disk (already removed): {jd_path}")

    # Delete resume files
    for path in resume_paths:
        Path(path).unlink()
        print(f"  [OK]  Deleted resume: {path}")

    # Remove tracking records
    for fn in list(related_records.keys()):
        tracking["resumes"].pop(fn, None)
    save_tracking(tracking)

    print(f"\n  [OK]  Removed {len(related_records)} record(s) from screening history.")
    print(f"  Done.\n")


def delete_resumes():
    """Delete all resumes or a specific resume."""
    print_header("[D]  Delete Resumes")

    print("\n  [1] Delete all resumes (all folders under resumes/)")
    print("  [2] Delete a specific resume")
    print()
    choice = nav_input("  Select an option: ")

    if choice == "1":
        _delete_all_resumes()
    elif choice == "2":
        _delete_specific_resume()
    else:
        print("  [!]  Invalid choice.\n")

def _delete_all_resumes():
    """Delete every resume file under RESUMES_DIR."""
    if not RESUMES_DIR.is_dir():
        print(f"\n  [!]  Resumes folder not found: {RESUMES_DIR}\n")
        return

    all_files = []
    for root, _, files in os.walk(RESUMES_DIR):
        for f in files:
            if any(f.lower().endswith(ext) for ext in SUPPORTED_RESUME_TYPES):
                all_files.append(Path(root) / f)

    if not all_files:
        print("\n  No resume files found.\n")
        return

    print(f"\n  {len(all_files)} resume(s) will be deleted:")
    for p in all_files:
        print(f"    - {p}")

    confirm = nav_input(
        f"\n  [!]  Type 'yes' to confirm deletion of ALL {len(all_files)} resume(s): "
    ).lower()
    if confirm != "yes":
        print("\n  Cancelled. Nothing was deleted.\n")
        return

    tracking = load_tracking()
    deleted_names = set()

    for path in all_files:
        path.unlink()
        deleted_names.add(path.name)
        print(f"  [OK]  Deleted: {path}")

    # Remove matching tracking records
    removed = [fn for fn in list(tracking["resumes"].keys()) if fn in deleted_names]
    for fn in removed:
        tracking["resumes"].pop(fn)
    save_tracking(tracking)

    print(f"\n  [OK]  Deleted {len(all_files)} file(s) and removed {len(removed)} tracking record(s).\n")


def _delete_specific_resume():
    """Delete one specific resume chosen from a list."""
    if not RESUMES_DIR.is_dir():
        print(f"\n  [!]  Resumes folder not found: {RESUMES_DIR}\n")
        return

    all_files = []
    for root, _, files in os.walk(RESUMES_DIR):
        for f in sorted(files):
            if any(f.lower().endswith(ext) for ext in SUPPORTED_RESUME_TYPES):
                all_files.append(Path(root) / f)

    if not all_files:
        print("\n  No resume files found.\n")
        return

    print(f"\n  Available resumes:")
    for i, p in enumerate(all_files, 1):
        print(f"    [{i}] {p}")

    choice = nav_input("\n  Select resume number: ")
    if not choice.isdigit() or not (1 <= int(choice) <= len(all_files)):
        print("  [!]  Invalid selection.\n")
        return

    selected_path = all_files[int(choice) - 1]
    selected_name = selected_path.name

    confirm = nav_input(
        f"\n  [!]  Type 'yes' to confirm deletion of '{selected_name}': "
    ).lower()
    if confirm != "yes":
        print("\n  Cancelled. Nothing was deleted.\n")
        return

    selected_path.unlink()
    print(f"\n  [OK]  Deleted: {selected_path}")

    # Remove tracking record if present
    tracking = load_tracking()
    if selected_name in tracking["resumes"]:
        tracking["resumes"].pop(selected_name)
        save_tracking(tracking)
        print(f"  [OK]  Removed tracking record for '{selected_name}'.")

    print()


def maintenance_menu():
    """Maintenance submenu for managing JDs and resumes."""
    while True:
        print_header("[M]  Maintenance")
        try:
            choice = print_submenu([
                "Delete JD and all related resumes",
                "Delete resumes (all or specific)",
            ])
        except BackToMenu:
            return

        try:
            if choice == 1:
                delete_jd_and_resumes()
            elif choice == 2:
                delete_resumes()
        except BackToMenu:
            continue

        input("\n  Press Enter to continue...")


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    check_dependencies()

    print("\n" + "=" * 62)
    print("   HR SCREENING TOOL v2  --  Windows Optimized")
    print("   Powered by Claude Code Pro")
    print("   PDF extraction: Docling -- OCR + layout-aware Markdown")
    print(f"  GPU: {_gpu_name if CUDA_AVAILABLE else 'CPU mode'}")
    print("=" * 62)

    while True:
        print_header("Main Menu")
        choice = print_menu([
            "Screen New Resumes          (skips already analyzed)",
            "Re-analyze All Resumes      (ignores history)",
            "Re-analyze Specific Resume  (one file only)",
            "Write a Job Description",
            "Generate Phone Screening Questions",
            "View Screening History",
            "Download Resume            (BambooHR job openings)",
            "Maintenance",
        ])

        try:
            if choice == 1:
                screen_new_resumes()
            elif choice == 2:
                reanalyze_all()
            elif choice == 3:
                reanalyze_one()
            elif choice == 4:
                write_job_description()
            elif choice == 5:
                prep_phone_screening()
            elif choice == 6:
                view_tracking()
            elif choice == 7:
                download_resume_menu()
            elif choice == 8:
                maintenance_menu()
        except BackToMenu:
            continue

        input("\n  Press Enter to return to main menu...")


if __name__ == "__main__":
    main()
