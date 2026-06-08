# HR Screening Tool v2 — Windows

An AI-powered resume screening tool built for Windows, using Claude Code Pro as the AI backend and Docling (IBM) for high-accuracy PDF extraction.

## Features

- **Batch resume screening** — score and rank candidates against a job description
- **Smart caching** — skips already-analyzed resumes; re-run anytime without duplicate costs
- **PDF extraction via Docling** — converts PDF resumes to structured Markdown before analysis
- **PDF quality rating** — flags low-quality extractions (image-heavy or scanned PDFs)
- **Job description writer** — generate professional JDs with Claude
- **Phone screening generator** — produce tailored HR interview questions
- **Screening history** — view past results filtered by JD
- **Maintenance tools** — delete JDs, resumes, and their tracking records together

### Windows-specific optimizations

- `asyncio` + IOCP for non-blocking subprocess I/O
- CUDA / DirectML GPU support for Docling (auto-selected based on batch size)
- `msvcrt` file locking for safe concurrent tracking-file writes
- Atomic tracking-file saves (write-to-temp + rename)
- Windows process priority elevation during batch processing
- Graceful Ctrl+C shutdown — finishes the current resume, saves progress, then exits

---

## Requirements

- Windows 10 / 11
- **Python 3.12** (required — docling and PyTorch are not yet compatible with Python 3.13/3.14). `uv` can install this for you.
- [uv](https://docs.astral.sh/uv/) package manager — `winget install astral-sh.uv`
- [Claude Code](https://claude.ai/code) desktop app installed

---

## Installation

```powershell
git clone <repo-url>
cd HR-Screening---v2-claude-windows
```

> This project uses **uv** instead of pip. uv keeps a single global wheel cache and
> hardlinks packages into each venv, so the large PyTorch wheels are downloaded once and
> never duplicated per project. Install uv with `winget install astral-sh.uv` if you
> don't have it.

### 1. Create the virtual environment

```powershell
uv venv --python 3.12 .venv
```

uv downloads a standalone Python 3.12 automatically if one isn't already installed — no
separate `winget install Python.Python.3.12` needed.

### 2. Install dependencies

```powershell
uv pip install "docling[full]" colorama
```

uv installs into the `.venv` in the current folder automatically. Use `docling[full]`
(not plain `docling`) so PyTorch is included — PDF extraction fails without it.

### GPU support (optional)

For NVIDIA GPUs (CUDA):
```powershell
uv pip install torch --index-url https://download.pytorch.org/whl/cu121
```

For AMD / Intel GPUs (DirectML):
```powershell
uv pip install torch-directml
```

GPU is auto-enabled when batch size exceeds 5 resumes. Falls back to CPU otherwise.

---

## Folder structure

```
project/
├── hr_screening_tool_v2_win.py
├── run.ps1                     ← use this to launch the tool
├── requirements.txt
├── .venv/                      ← Python 3.12 virtual environment
├── screening_history_v2.json   ← auto-created on first run
├── resumes/
│   └── <role-name>/            ← one subfolder per role
│       ├── candidate1.pdf
│       └── candidate2.txt
├── jd/
│   ├── role1.txt
│   └── role2.md
└── results/
    └── screening_<role>_<timestamp>.csv
```

Place resume files (`.pdf` or `.txt`) inside subfolders under `resumes/`.  
Place job description files (`.txt` or `.md`) inside `jd/`.

---

## Usage

```powershell
.\run.ps1
```

`run.ps1` activates the `.venv` Python 3.12 environment automatically. Do not run with plain `python` — that would use the system Python and docling will fail on Python 3.13+.

### Main menu options

| Option | Description |
|--------|-------------|
| Screen New Resumes | Analyze only unprocessed resumes (uses cache) |
| Re-analyze All Resumes | Force re-analysis of every resume in a folder |
| Re-analyze Specific Resume | Re-run one resume file |
| Write a Job Description | Generate a JD with Claude |
| Generate Phone Screening Questions | Create HR interview questions for a role |
| View Screening History | Browse past results filtered by JD |
| Maintenance | Delete JDs and/or resumes with tracking cleanup |

---

## Screening output

Results are saved as CSV to `results/screening_<role>_<timestamp>.csv`, sorted by fit score descending.

| Column | Description |
|--------|-------------|
| Candidate | Name derived from filename |
| Fit Score | 0–100 match score |
| Recommendation | `RECOMMEND` / `REVIEW` / `DEFER` |
| PDF Quality | Excellent / Good / Fair / Poor |
| PDF Quality Score | 0–100 extraction confidence |
| Keywords Found | Matched JD keywords |
| Keywords Missing | JD keywords absent from resume |
| Summary | One-sentence Claude summary |
| Analyzed On | Timestamp |

### Recommendation thresholds

| Score | Recommendation |
|-------|---------------|
| 75–100 | RECOMMEND — strong fit, move to interview |
| 50–74 | REVIEW — partial fit, worth a closer look |
| 0–49 | DEFER — does not meet role requirements |

---

## Rate limiting

Configured for Claude Code **Pro** subscriptions by default:

| Setting | Default | Description |
|---------|---------|-------------|
| `MAX_WORKERS` | 1 | Sequential processing (safe for Pro) |
| `REQUEST_DELAY` | 2.0s | Delay before each Claude call |
| `SUB_BATCH_SIZE` | 10 | Resumes per sub-batch |
| `SUB_BATCH_PAUSE` | 30s | Pause between sub-batches |
| `RETRY_MAX` | 4 | Retries on rate limit (exponential backoff) |

Adjust constants at the top of `hr_screening_tool_v2_win.py` if you have a Max subscription.

---

## Notes

- Press **Ctrl+C** once to finish the current resume and exit cleanly. Press twice to force-quit immediately.
- The tracking file (`screening_history_v2.json`) stores hashes of both the resume and JD — re-screening is triggered automatically if either file changes.
- PDF resumes with heavy image formatting or scanned pages will receive a lower PDF quality score. The tool flags these and still attempts analysis, but results may be less accurate.
- The Claude CLI is located automatically even when installed via the Claude desktop app (where the executable lives in a versioned subdirectory not directly on PATH).
- Running with plain `python` on Python 3.13+ will disable PDF support and GPU detection silently — always use `.\run.ps1`.
