# Quickstart Guide

Get the HR Screening Tool v2 running on a **brand-new Windows machine** from scratch.

The tool bundles two features behind one menu:

- **AI resume screening** — Claude + Docling (OCR / layout-aware PDF extraction)
- **BambooHR resume downloader** — pull applicant resumes straight from BambooHR

There are two ways to install once the repo is on the machine:

- **Automated (recommended)** — run `.\setup.ps1`, which syncs dependencies, creates
  your config and input folders, and can pre-fetch the OCR models and launch the tool.
- **Manual** — run each `uv` command yourself (kept at the end as reference / for
  troubleshooting).

Either way, **Steps 1–3 must be done first** — cloning the repo, the Visual C++ runtime,
and the PowerShell execution policy are things `setup.ps1` cannot do for you.

---

## Step 1 — Install prerequisites

Open **Windows PowerShell** and move into your Documents folder:

```powershell
cd $HOME\Documents
```

### winget (package manager)

```powershell
winget --version
```

Should print a version (e.g. `v1.28.x`). winget ships with Windows 11. If missing, update
the **App Installer** package from the Microsoft Store.

### git (to clone the repo)

```powershell
git --version
```

If missing:

```powershell
winget install Git.Git --accept-package-agreements --accept-source-agreements
```

### uv (Python package manager)

```powershell
uv --version
```

Should print a version (e.g. `uv 0.11.x`). If you get "not recognized", install it:

```powershell
winget install astral-sh.uv --accept-package-agreements --accept-source-agreements
```

Close and re-open PowerShell after installing.

> `setup.ps1` will attempt to install uv for you if it's missing — but installing it now
> avoids a "re-open PowerShell and re-run" round-trip later.

### Python 3.12 (optional — uv installs it on demand)

You do **not** need Python from python.org or any PATH edits — uv manages Python. You can
pre-install the 3.12 build to make the first sync faster:

```powershell
uv python install 3.12
```

(Skippable — `uv sync` / `setup.ps1` auto-downloads Python 3.12 if it's missing.)

### Claude Code

```powershell
where.exe claude
```

If you see a path, Claude is installed. Otherwise install it with the official installer
(adds `claude` to your PATH automatically):

```powershell
irm https://claude.ai/install.ps1 | iex
```

Close and re-open PowerShell, then confirm with `where.exe claude`.

> Claude Code requires a Pro, Max, Team, or Enterprise account. On first launch, run
> `claude` once and follow the browser prompt to sign in. The screening feature calls
> Claude; the BambooHR downloader does not.

---

## Step 2 — Install Visual C++ 2022 Redistributable

PyTorch (required by Docling) needs the **2022** runtime. The 2019 version that ships with
many machines is not sufficient.

```powershell
winget install Microsoft.VCRedist.2015+.x64 --accept-package-agreements --accept-source-agreements
```

> Safe to run even if already installed — winget reports "already installed" and exits.

---

## Step 3 — Clone the repo and allow scripts

```powershell
git clone https://github.com/DysrupIT-AI-Lab-Internal-Team/HR-Screening---v2-claude-windows.git
cd HR-Screening---v2-claude-windows
```

Allow local PowerShell scripts (`setup.ps1`, `run.ps1`) to run for your user. Windows blocks
scripts by default, so run this once:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

This applies only to your account and needs no administrator rights.

---

## Step 4 — Run the automated setup (recommended)

From the project root:

```powershell
.\setup.ps1 -SetupOnly -DownloadModels
```

That one command:

1. Checks **uv** (installs it via winget if missing) and detects **Claude Code**.
2. Runs `uv sync` — creates the `.venv` and installs the exact locked dependencies
   (`docling` + `torch`/`torchvision`/`transformers`, `colorama`, `python-dotenv`,
   `requests`, `rich`). PyTorch comes in via Docling; **CPU only, no GPU setup needed.**
3. Verifies Docling actually imports (catches torch/transformers drift early).
4. Creates a local **`.env`** from `.env.example` (if one doesn't already exist).
5. Creates the input folders **`resume_screening\`, `jd\`, `results\`**.
6. `-DownloadModels` pre-fetches Docling's OCR / layout models (needs internet — see the
   note below).

Flag reference:

| Command | What it does |
|---------|--------------|
| `.\setup.ps1` | Set up, then **launch the tool immediately** |
| `.\setup.ps1 -SetupOnly` | Set up only — don't launch (use this the first time so you can configure `.env` first) |
| `.\setup.ps1 -DownloadModels` | Also pre-fetch Docling models |

> **First run downloads a lot.** The first `uv sync` on a machine pulls PyTorch (~120 MB)
> and several ML libraries into uv's global cache. Later syncs hardlink from that cache, so
> they're near-instant. `-DownloadModels` additionally fetches the RapidOCR models
> (~40 MB) plus Docling's layout/table models. Models cache under your user profile and are
> downloaded once per machine — so the *first* resume isn't slow later. If the machine will
> screen offline, run `-DownloadModels` while it still has internet.

If `uv sync` fails, see [Troubleshooting](#troubleshooting).

---

## Step 5 — Configure `.env`

`setup.ps1` already created `.env` from `.env.example`. Open it:

```powershell
notepad .env
```

| Setting | Needed for | Notes |
|---------|-----------|-------|
| `CLAUDE_MODEL` | Screening | Leave **blank** to use Claude Code's default model (recommended for Pro), or set e.g. `claude-sonnet-4-6` |
| `BAMBOOHR_API_KEY` | Download Resume | BambooHR → top-right menu → **API Keys** → generate a key with applicant-tracking (ATS) read access |
| `BAMBOOHR_SUBDOMAIN` | Download Resume | Your company's BambooHR subdomain (the `xxx` in `xxx.bamboohr.com`) |
| `DOWNLOAD_DIR` | Download Resume | Where resumes are saved. Default `./resume_downloads` — leave as-is unless you have a reason to change it |
| `API_DELAY_SECONDS` | Download Resume | Seconds between BambooHR API calls (default `2.0`) — rate-limit friendly |

> `.env` is git-ignored and stays local. If you only use screening, leave the `BAMBOOHR_*`
> values blank — the **Download Resume** menu will simply explain what's missing if you open
> it without credentials.

---

## Step 6 — Add your input files

`setup.ps1` already created the folders. Add your files:

- **Resumes to screen** → subfolders under `resume_screening\`, one per role
  e.g. `resume_screening\DevOps Engineer\john_doe.pdf`  (`.pdf` or `.txt`)
- **Job descriptions** → `jd\`
  e.g. `jd\devops_engineer.txt`  (`.txt` or `.md`)

You don't need to create `resume_downloads\` — the **Download Resume** feature creates it
automatically, organizing files as `resume_downloads\<id> - <requisition name>\<stage>\`
(e.g. `resume_downloads\788 - Dynamics CRM developer\Hired\`).

---

## Step 7 — Run the tool

```powershell
.\run.ps1
```

`run.ps1` launches via `uv run`, syncing from `uv.lock` and running inside the environment —
no activation needed. (Equivalent: `uv run hr_screening_tool_v2_win.py`.)

You should see the main menu:

```
==============================================================
   HR SCREENING TOOL v2  --  Windows Optimized
   Powered by Claude Code Pro
   PDF extraction: Docling -- OCR + layout-aware Markdown
==============================================================

  Main Menu
  [1] Screen New Resumes          (skips already analyzed)
  [2] Re-analyze All Resumes      (ignores history)
  [3] Re-analyze Specific Resume  (one file only)
  [4] Write a Job Description
  [5] Generate Phone Screening Questions
  [6] View Screening History
  [7] Download Resume            (BambooHR job openings)
  [8] Maintenance
  [0] Exit
```

Navigation is the same everywhere: pick a number, `[0]` goes back, and typing `b` at any
prompt returns to the menu.

---

## Manual setup (alternative to Step 4)

If you prefer to run the steps yourself, or need them for troubleshooting, `setup.ps1` is
just a wrapper around these:

**1. Install dependencies**

```powershell
uv sync
```

Creates the Python 3.12 environment automatically and installs the locked versions. You
never activate a venv or call `pip`. Verify the interpreter:

```powershell
uv run python --version   # expect Python 3.12.x
```

**2. Verify the install**

```powershell
uv run python -c "import torch; from docling.document_converter import DocumentConverter; print('docling + torch OK -', torch.__version__)"
```

Confirm the Claude CLI is detected:

```powershell
uv run python -c "
import shutil, os
from pathlib import Path
hit = shutil.which('claude')
if not hit:
    base = Path(os.environ.get('LOCALAPPDATA','')) / 'Packages'
    for pkg in base.iterdir():
        if 'claude' in pkg.name.lower():
            for sub in sorted((pkg / 'LocalCache' / 'Roaming' / 'Claude' / 'claude-code').iterdir(), reverse=True):
                exe = sub / 'claude.exe'
                if exe.is_file():
                    hit = str(exe)
                    break
print('Claude CLI:', hit or 'NOT FOUND')
"
```

**3. Pre-download Docling models (recommended, needs internet)**

```powershell
uv run docling-tools models download
```

**4. Create config + folders**

```powershell
copy .env.example .env
New-Item -ItemType Directory -Force resume_screening, jd, results
```

**5. Run**

```powershell
uv run hr_screening_tool_v2_win.py
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `setup.ps1` cannot be loaded / "running scripts is disabled" | Execution policy not set | Run Step 3's `Set-ExecutionPolicy` command, then re-run |
| `.\setup.ps1` says uv installed but not on PATH | uv just installed in this session | Close and re-open PowerShell, then re-run `.\setup.ps1` |
| `docling not installed` / PDF support disabled | Deps not synced, **or** running system Python instead of the uv env | Re-run `.\setup.ps1` (or `uv sync`); launch via `.\run.ps1` — never `python hr_screening_tool_v2_win.py` |
| `docling failed to import after sync` | torch/transformers version drift | `uv sync --reinstall`, then re-run |
| `ModuleNotFoundError: No module named 'torch'` | `uv sync` did not complete | Re-run `uv sync` from the project root |
| First resume hangs / connection errors during processing | OCR/layout models downloading on first run | Run `.\setup.ps1 -DownloadModels` (or `uv run docling-tools models download`) while online |
| `OSError: [WinError 1114] c10.dll` | Missing Visual C++ 2022 runtime | Re-run Step 2 |
| `Claude Code is not installed or not in PATH` | Claude not installed, or PATH stale | `irm https://claude.ai/install.ps1 \| iex`, re-open PowerShell |
| Download Resume says `Missing required BambooHR setting(s)` | `BAMBOOHR_API_KEY` / `BAMBOOHR_SUBDOMAIN` blank | Add them to `.env` (Step 5) |
| BambooHR **Test API Connection** fails auth | Wrong key or subdomain | Re-check the API key and that `BAMBOOHR_SUBDOMAIN` is just the subdomain, not the full URL |
| `uv` not recognized | uv not installed or PATH stale | `winget install astral-sh.uv`, re-open PowerShell |
| `uv sync` can't find / create the environment | Not in the project folder, or Python 3.12 unavailable | Run uv commands from the project root; uv auto-downloads Python 3.12 |
| First install is slow / downloads a lot | Cold uv cache (first machine ever) | One-time — later syncs hardlink from the cache instantly |
