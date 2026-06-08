# Walkthrough: Windows-Optimized HR Screening Tool

## What Was Built

Created [hr_screening_tool_v2_win.py](file:///Users/admin/Documents/Project_HR_Screening_Prototypes/hr_screening_tool_v2_win.py) — a Windows-optimized fork of [hr_screening_tool_v2.py](file:///Users/admin/Documents/Project_HR_Screening_Prototypes/hr_screening_tool_v2.py) with **7 major optimizations** while preserving all 14 original features.

---

## Optimizations Applied

### 1. Async I/O with IOCP (biggest perf win)

| Before (macOS) | After (Windows) |
|---|---|
| `subprocess.run()` — blocks the thread | `asyncio.create_subprocess_exec()` — non-blocking |
| `time.sleep()` for delays — wastes time | `asyncio.sleep()` — event loop stays free |
| Rate limit backoff blocks everything | Async backoff, other work continues |

Windows `asyncio` uses **IOCP** (I/O Completion Ports) — the fastest async I/O mechanism on the platform. Claude CLI calls, rate-limit waits, and sub-batch pauses all happen without blocking.

**Key functions changed:**
- [ask_claude_async](file:///Users/admin/Documents/Project_HR_Screening_Prototypes/hr_screening_tool_v2_win.py#L200-L241) — async version using `create_subprocess_exec`
- [screen_single_resume_async](file:///Users/admin/Documents/Project_HR_Screening_Prototypes/hr_screening_tool_v2_win.py#L394-L513) — full async pipeline
- [_run_batch_async](file:///Users/admin/Documents/Project_HR_Screening_Prototypes/hr_screening_tool_v2_win.py#L516-L527) — semaphore-controlled concurrency

### 2. Windows Console Setup

[_setup_windows_console()](file:///Users/admin/Documents/Project_HR_Screening_Prototypes/hr_screening_tool_v2_win.py#L29-L71) runs at import time:
- Forces UTF-8 encoding (Windows defaults to cp1252)
- Enables ANSI escape codes via `kernel32.SetConsoleMode()`
- Sets the console title to "HR Screening Tool v2 — Windows"
- Initializes `colorama` if available

**Emoji replaced with ASCII-safe equivalents:**
- `✅` → `[OK]`, `⚠️` → `[!!]`, `❌` → `[XX]`
- `⏭️` → `[>>]`, `⏸️` → `[||]`, `↩️` → `<<`

### 3. CUDA/DirectML GPU Support

[GPU detection block](file:///Users/admin/Documents/Project_HR_Screening_Prototypes/hr_screening_tool_v2_win.py#L78-L101):
- **NVIDIA:** `torch.cuda.is_available()` → `AcceleratorDevice('cuda')`
- **AMD/Intel:** `torch_directml` fallback → `AcceleratorDevice('auto')`
- Same batch-threshold logic: GPU only for batches > 5 resumes

### 4. Pathlib Throughout

All `os.path.join()` calls replaced with `pathlib.Path` operations:
- `RESUMES_DIR`, `JD_DIR`, `RESULTS_DIR` are `Path` objects
- `Path.iterdir()` replaces `os.listdir()`
- `Path.unlink()` replaces `os.remove()`
- `os.fspath()` used when passing to Docling (which expects strings)

### 5. Atomic File Writes + Locking

[save_tracking()](file:///Users/admin/Documents/Project_HR_Screening_Prototypes/hr_screening_tool_v2_win.py#L273-L283):
- Writes to `.tmp` first, then renames — prevents corruption on crash
- [_file_lock()](file:///Users/admin/Documents/Project_HR_Screening_Prototypes/hr_screening_tool_v2_win.py#L156-L172) context manager uses `msvcrt.locking()` for Windows-native file locking

### 6. Process Priority Control

[_elevated_priority()](file:///Users/admin/Documents/Project_HR_Screening_Prototypes/hr_screening_tool_v2_win.py#L138-L152) context manager:
- Raises to `ABOVE_NORMAL_PRIORITY_CLASS` during batch processing
- Restores original priority when done
- Uses `kernel32.SetPriorityClass()` — Windows-native API

### 7. Graceful Ctrl+C Shutdown

[_signal_handler()](file:///Users/admin/Documents/Project_HR_Screening_Prototypes/hr_screening_tool_v2_win.py#L121-L131):
- First `Ctrl+C`: sets `_shutdown_requested` flag, finishes current resume, saves tracking, exits cleanly
- Second `Ctrl+C`: forces immediate exit
- Progress is never lost — partial results are saved to CSV

---

## Feature Parity Matrix

| # | Feature | Preserved? |
|---|---|---|
| 1 | Screen new resumes (skip cached) | Yes |
| 2 | Re-analyze all resumes | Yes |
| 3 | Re-analyze specific resume | Yes |
| 4 | Write job description | Yes |
| 5 | Phone screening questions | Yes |
| 6 | View screening history | Yes |
| 7 | Maintenance: delete JD + resumes | Yes |
| 8 | Maintenance: delete resumes | Yes |
| 9 | PDF extraction via Docling | Yes |
| 10 | PDF quality rating | Yes |
| 11 | Tracking/caching system | Yes (same JSON format) |
| 12 | Rate limiting & backoff | Yes (now async) |
| 13 | Sub-batch processing | Yes |
| 14 | Back-navigation (`b`) | Yes |

> [!NOTE]
> The tracking file `screening_history_v2.json` uses the same format — you can share it between macOS and Windows versions.

---

## Validation

- **Syntax verified**: `py_compile.compile()` passed with no errors
- **No new dependencies required**: All Windows-specific modules (`msvcrt`, `ctypes`, `asyncio`, `signal`, `pathlib`) are in the Python standard library
- **Optional dependencies**: `colorama` (for older terminals), `torch-directml` (for AMD GPUs)

---

## Runtime Fixes (Post-Build)

Three issues were discovered and fixed when running on a Python 3.14 system with the Claude desktop app installed.

### Fix 1 — PyTorch / docling `OSError` on Python 3.13+

**Problem:** PyTorch is not yet compatible with Python 3.13 or 3.14. Its DLL fails to load, raising `OSError: [WinError 1114]` instead of `ImportError`. The original `try/except ImportError` blocks did not catch this, so the script crashed at import time.

**Affected blocks:**
- `import torch` (GPU detection)
- `import torch_directml` (DirectML fallback)
- `from docling.document_converter import ...` (docling internally imports `transformers` → `torch`)

**Fix:** All three `except ImportError` clauses updated to `except (ImportError, OSError)`. The tool now falls back to CPU / no-PDF-support cleanly on unsupported Python versions.

### Fix 2 — Claude CLI not found when installed via desktop app

**Problem:** The Claude desktop app installs `claude.exe` inside a versioned subdirectory:
```
%LOCALAPPDATA%\Packages\Claude_...\LocalCache\Roaming\Claude\claude-code\2.x.x\claude.exe
```
Only the parent `claude-code\` folder is on PATH, not the versioned subfolder. `shutil.which("claude")` therefore returns `None` and the script exits with "Claude Code is not installed".

**Fix:** Added `_find_claude()` — a startup helper that first tries `shutil.which`, then walks one level into the versioned subdirectory under the Packages install path. The resolved path is stored in `CLAUDE_EXE` and used everywhere the CLI is invoked.

### Fix 3 — Python 3.12 virtual environment

**Problem:** docling and PyTorch require Python ≤ 3.12. The system had only Python 3.14.

**Solution (using uv):**
1. Installed uv via `winget install astral-sh.uv` (shared global cache, hardlinks wheels into venvs)
2. Created a project-local virtual environment: `uv venv --python 3.12 .venv` (uv fetches Python 3.12 if absent)
3. Installed `docling[full]` and `colorama` into the venv: `uv pip install "docling[full]" colorama`
4. Created `run.ps1` — a launcher that invokes the venv's Python automatically

**`run.ps1`** (project root):
```powershell
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
& "$scriptDir\.venv\Scripts\python.exe" "$scriptDir\hr_screening_tool_v2_win.py" @args
```

---

## How to Run on Windows

```powershell
cd "C:\path\to\HR-Screening---v2-claude-windows"
.\run.ps1
```

> Do **not** use `python hr_screening_tool_v2_win.py` directly — if the system Python is 3.13 or 3.14, docling and GPU support will be silently disabled.
