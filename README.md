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
- **Resume downloader** — pull applicant resumes straight from BambooHR by job opening (built into the menu)
- **Maintenance tools** — delete JDs, resumes, and their tracking records together

### Windows-specific optimizations

- `asyncio` + IOCP for non-blocking subprocess I/O
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

> This project uses **uv** instead of pip. You never create or activate a virtual
> environment by hand and never call `pip` — uv manages the environment, and `uv run`
> executes the tool inside it. uv keeps a single global wheel cache and hardlinks packages
> into each environment, so the large PyTorch wheels are downloaded once and never
> duplicated per project. Install uv with `winget install astral-sh.uv` if you don't have it.

### 1. Install dependencies

Dependencies are declared in `pyproject.toml` and pinned in `uv.lock` (both committed).
Install them with:

```powershell
uv sync
```

`uv sync` creates a Python 3.12 environment automatically (downloading a standalone
Python 3.12 build if one isn't already installed — no separate `winget install
Python.Python.3.12` needed) and installs the exact locked versions. PyTorch is pulled in as
a transitive dependency of `docling`, so PDF extraction works out of the box.

### 2. Configure the environment

```powershell
copy .env.example .env
```

Edit `.env` if you want to pin a specific Claude model (see [Configuration](#configuration)).
Leaving `CLAUDE_MODEL` blank uses Claude Code's default model.

> PDF extraction runs on CPU — no GPU setup is required.

---

## Configuration

Configuration lives in a `.env` file (loaded automatically via `python-dotenv`). Copy
`.env.example` to `.env` and adjust as needed. `.env` is git-ignored and must never be
committed.

| Variable | Default | Description |
|----------|---------|-------------|
| `CLAUDE_MODEL` | *(blank)* | Claude model to use. Blank = Claude Code's default model. Set to a model name (e.g. `claude-sonnet-4-6`) to override. |

## Models used

| Purpose | Model | Notes |
|---------|-------|-------|
| Screening & generation | **Claude Code** (default model unless `CLAUDE_MODEL` is set) | No API key required; runs via the Claude Code CLI. |
| PDF extraction (`hr_screening_tool_v2_win.py`) | **Docling** (IBM) | Layout-aware Markdown extraction with bundled PyTorch models. |

## Folder structure

```
project/
├── hr_screening_tool_v2_win.py
├── run.ps1                     ← use this to launch the tool
├── pyproject.toml              ← dependency declarations (uv)
├── uv.lock                     ← pinned dependency versions
├── .env.example                ← config template (committed)
├── .env                        ← local config (never committed)
├── .venv/                      ← Python 3.12 virtual environment
├── screening_history_v2.json   ← auto-created on first run
├── resume_screening/
│   └── <role-name>/            ← one subfolder per role
│       ├── candidate1.pdf
│       └── candidate2.txt
├── jd/
│   ├── role1.txt
│   └── role2.md
└── results/
    └── screening_<role>_<timestamp>.csv
```

Place resume files (`.pdf` or `.txt`) inside subfolders under `resume_screening/`.  
Place job description files (`.txt` or `.md`) inside `jd/`.

---

## Usage

```powershell
.\run.ps1
```

`run.ps1` launches the tool via `uv run`, which syncs the Python 3.12 environment from
`uv.lock` and runs inside it automatically — no activation needed. You can also run it
directly with `uv run hr_screening_tool_v2_win.py`. Do not run with plain `python` — that
would use the system Python and docling will fail on Python 3.13+.

### Main menu options

| Option | Description |
|--------|-------------|
| Screen New Resumes | Analyze only unprocessed resumes (uses cache) |
| Re-analyze All Resumes | Force re-analysis of every resume in a folder |
| Re-analyze Specific Resume | Re-run one resume file |
| Write a Job Description | Generate a JD with Claude |
| Generate Phone Screening Questions | Create HR interview questions for a role |
| View Screening History | Browse past results filtered by JD |
| Download Resume | Download applicant resumes from BambooHR by job opening |
| Maintenance | Delete JDs and/or resumes with tracking cleanup |

### Download Resume (BambooHR)

Pulls applicant resumes straight from BambooHR, organized into
`resume_downloads/<id> - <requisition name>/<pipeline-stage>/` folders
(e.g. `resume_downloads/788 - Dynamics CRM developer/Hired/`). It reuses the same numbered-menu
navigation as the rest of the tool (`[0]` goes back, `b` returns to the menu),
and exposes every feature of the standalone downloader:

| Sub-option | Description |
|------------|-------------|
| List Job Openings | List jobs and their IDs, filtered by status |
| Download Resumes for a Job | Download resumes for a job ID, with applicant-status filter and force re-download |
| Show Download Report | Render the summary dashboard from saved state (no API calls) |
| Migrate v1 Files → v2 Stage Folders | Reorganize old flat filenames into stage subfolders |
| Test API Connection | Verify your BambooHR API key and subdomain |

Requires `BAMBOOHR_API_KEY` and `BAMBOOHR_SUBDOMAIN` in your `.env` (see
`.env.example`). If they are not set, the menu explains what to add and returns.

---

## Project structure

```
hr_screening_tool_v2_win.py   Main entry point — the interactive menu tool
cli_common.py                 Shared menu/navigation helpers (used by both features)
bamboo_downloader.py          "Download Resume" menu front-end
bamboohr/                     BambooHR downloader package
  client.py                     API client
  files.py                      filename building + safe file writes
  tracker.py                    per-job download-state tracking
  stats.py                      Rich summary dashboard
  logger.py                     logging setup
jd/                           Job descriptions (screening inputs)
resume_screening/             Resumes to screen, grouped by role folder
results/                      Screening result CSVs
resume_downloads/             BambooHR downloads: "<id> - <title>/<stage>/" + state files (git-ignored)
docs/                         BambooHR downloader admin & how-to guides
```

The resume downloader was originally a separate command-line project; its
features are now fully merged into this tool and reached through the menu.

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
- Running with plain `python` on Python 3.13+ will disable PDF support silently — always use `.\run.ps1` or `uv run hr_screening_tool_v2_win.py`.
