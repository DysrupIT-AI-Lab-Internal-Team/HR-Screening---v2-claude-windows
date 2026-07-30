# BambooHR Resume Downloader — Admin Guide (v2)

**Tool:** DIT Download Resume per JD  
**Language:** Python 3.9+ (managed by [uv](https://docs.astral.sh/uv/))  
**Version:** 2.0.0

> **⚠️ Integration note (2026):** This downloader is now built into the HR
> Screening Tool v2. There is no separate `main.py` anymore — launch the HR tool
> (`.\run.ps1`) and pick **Download Resume** from the main menu. The old
> command-line flags shown throughout this guide map to menu options as follows:
>
> | Old command | New menu path |
> |---|---|
> | `main.py --test` | Download Resume → **Test API Connection** |
> | `main.py --list-jobs [--status X]` | Download Resume → **List Job Openings** |
> | `main.py --job-id N [--applicant-status X] [--force]` | Download Resume → **Download Resumes for a Job** |
> | `main.py --job-id N --report` | Download Resume → **Show Download Report** |
> | `main.py --job-id N --migrate` | Download Resume → **Migrate v1 Files → v2 Stage Folders** |
>
> The BambooHR credential/setup sections below still apply — set
> `BAMBOOHR_API_KEY` and `BAMBOOHR_SUBDOMAIN` in the project's root `.env`.
>
> Two folder details also changed in the integrated tool: downloads now go to
> **`resume_downloads/`** (was `downloads/`), and each job's folder is named
> **`<id> - <requisition name>`** (e.g. `788 - Dynamics CRM developer`) instead
> of `job_<id>`. Examples below still say `downloads/job_<id>/` for historical
> reference.

---

## Overview

This tool connects to BambooHR via API and downloads resumes for all applicants of a specific job opening. Resumes are organized into subfolders by applicant stage (e.g. `Phone_Screened/`, `Hired/`). The tracker remembers what was already downloaded — on re-runs, only new applicants are fetched, and applicants whose stage changed are automatically moved to the correct folder without re-downloading.

A Rich terminal dashboard is displayed at the end of every run showing a summary, a stage breakdown chart, and any file movements.

---

## What's New in v2

| Feature | v1 | v2 |
|---|---|---|
| Folder structure | Flat — all files in `job_{id}/` | Stage subfolders — `job_{id}/{Stage}/` |
| Stage in filename | Prefix: `(Phone_Screened)_17834_...` | Removed — folder name serves that purpose |
| Stage change handling | File stays in wrong folder | File auto-moved to new folder, no re-download |
| Terminal output | Plain log lines | Rich dashboard with summary, bar chart, movements table |
| Migrate v1 files | — | `--migrate` flag reorganizes v1 files into v2 structure |

---

## Installation on a New Machine

### 1. Prerequisites

- [uv](https://docs.astral.sh/uv/) (manages Python and dependencies — no separate Python install needed)
- Internet access to reach `api.bamboohr.com`

Verify uv is installed:

```bash
uv --version
```

Install it if missing — macOS/Linux:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Windows (PowerShell): `winget install astral-sh.uv`

### 2. Copy the Project Files

Copy the following files to the target machine (do **not** copy `.env` — it is machine-specific):

```
main.py
bamboohr_client.py
downloader.py
tracker.py
stats.py
config.py
logger.py
pyproject.toml
uv.lock
.python-version
.env.example
.gitignore
ADMIN_GUIDE.md
```

> **Tip:** the simplest way to copy a complete, correct file set is `bash prepare_install.sh`,
> which zips everything (including `pyproject.toml`, `uv.lock`, and `.python-version`) for you.

The `downloads/` and `logs/` folders are created automatically on first run.

### 3. Install Dependencies

```bash
uv sync
```

This creates `.venv`, fetches the pinned Python version if needed, and installs the exact
locked dependencies. Run the tool with `uv run main.py ...` (no activation required).

Three packages are required:

| Package | Purpose |
|---|---|
| `requests` | HTTP calls to BambooHR API |
| `python-dotenv` | Reads credentials from `.env` |
| `rich` | Terminal dashboard output |

### 4. Create the `.env` File

```bash
cp .env.example .env
```

Open `.env` and fill in the values:

```
BAMBOOHR_API_KEY=your_api_key_here
BAMBOOHR_SUBDOMAIN=dysrupit
DOWNLOAD_DIR=./resume_downloads
API_DELAY_SECONDS=2.0
```

**How to get the API key:**  
In BambooHR → top-right menu → *API Keys* → Generate a new key with ATS/applicant tracking read access.

### 5. Test the Connection

```bash
uv run main.py --test
```

Expected output:
```
[INFO] ... BambooHR Resume Downloader v2.0.0
[INFO] ... API connection successful.
[INFO] ... Connection test passed. Exiting (--test mode).
```

---

## Finding Job IDs

Job IDs appear in the BambooHR hiring URL:

```
https://dysrupit.bamboohr.com/hiring/jobs/224
                                           ^^^
                                        Job ID = 224
```

Or list them directly from the tool:

```bash
# List all Open jobs (default)
uv run main.py --list-jobs

# Filter by job status
uv run main.py --list-jobs --status "On Hold"
uv run main.py --list-jobs --status Filled
uv run main.py --list-jobs --status Canceled
uv run main.py --list-jobs --status Draft

# List ALL jobs regardless of status
uv run main.py --list-jobs --status All
```

Sample output:
```
======================================================================
  Job Openings — Status: Open
======================================================================
  ID       Status       Title
  ------  ----------  ---------------------------------------------
  224      Open         Junior IT Operations & M365 Administrator
  223      Open         IBM iSeries Developer
  175      Open         Junior AI Developer
======================================================================
  Total: 3 job(s)
```

---

## Downloading Resumes

```bash
uv run main.py --job-id 224
```

This fetches all applicants (all statuses, all pages) and downloads each resume once. On re-run, already-downloaded resumes are skipped. If an applicant moved to a new stage since the last run, their file is automatically relocated to the correct subfolder — no re-download needed.

### Output Folder Structure

```
downloads/
  job_224/
    Applied/
      17900_Jane_Smith_Junior_IT_Operations.pdf
    Phone_Screened/
      17834_John_Doe_Junior_IT_Operations.pdf
    Hired/
      17836_Bob_Lee_Junior_IT_Operations.pdf
    Not_a_Fit-Paperscreening/
      17850_Alice_Cruz_Junior_IT_Operations.docx
  state_224.json          ← download tracker for job 224
```

**Filename format:** `{application_id}_{First}_{Last}_{Position}.{ext}`

The stage is the **folder name**, not part of the filename. Stage folder names use underscores (e.g. `Phone_Screened`, `Not_a_Fit-Paperscreening`).

### How Resume Files Are Matched to Applicants

The tool fetches each applicant's **application detail** from BambooHR to retrieve the `resumeFileId` field, then downloads `/v1/files/{resumeFileId}`. This ensures the correct resume is always downloaded.

> **Note:** This requires two API calls per applicant — one for the detail, one for the file. For large job openings this is slower but necessary for correctness. Use `--delay 1.0` to reduce wait time if needed.

---

## Filtering Which Applicants to Download

By default the tool downloads resumes for **everyone who ever applied**. Use `--applicant-status` to narrow this down:

| Value | Who is included |
|---|---|
| `ALL` | Every applicant ever submitted **(default)** |
| `ALL_ACTIVE` | Only those still in the running |
| `ACTIVE` | Active pipeline only |
| `HIRED` | Hired applicants only |
| `INACTIVE` | Disqualified / withdrawn applicants only |

```bash
# Download only active applicants
uv run main.py --job-id 224 --applicant-status ALL_ACTIVE

# Download only hired applicants
uv run main.py --job-id 224 --applicant-status HIRED
```

---

## Migrating v1 Files to v2 Folder Structure

If you have existing files from v1 (flat folder, stage prefix in filename), the `--migrate` flag will reorganize them into v2 subfolders without re-downloading anything.

```bash
uv run main.py --job-id 224 --migrate
```

What it does:
1. Scans `downloads/job_224/` for v1-style files (e.g. `(Phone_Screened)_17834_John_Doe_...pdf`)
2. Creates the appropriate stage subfolder (e.g. `Phone_Screened/`)
3. Moves the file and strips the stage prefix from the filename
4. Updates the tracker to reflect the new location

After migration, running `uv run main.py --job-id 224` normally will pick up from where the tracker left off.

---

## Terminal Dashboard

At the end of every run, a Rich dashboard is displayed:

```
┌─────────────────────────────────────────────────────────┐
│          BAMBOOHR RESUME DOWNLOAD REPORT                │
│   Job ID: 224  │  Junior IT Operations & M365 Admin    │
│   Run: 2026-04-16 09:30 PST                             │
└─────────────────────────────────────────────────────────┘

╭──────────────────── OVERALL SUMMARY ────────────────────╮
│  Total Applicants          210                          │
│  ✔  New Downloads           45                          │
│  ➜  Stage Movements          3                          │
│  –  Skipped (no change)    155                          │
│  ✘  No Resume                5                          │
│  ⚠  Failed                   2                          │
╰─────────────────────────────────────────────────────────╯

╭──────────────────── APPLICANTS BY STAGE ────────────────╮
│  Applied                  88  ████████████░░░░░░░░      │
│  Phone Screened           42  ████████░░░░░░░░░░░░      │
│  Not a Fit-Paperscreen    40  ███████░░░░░░░░░░░░░      │
│  ...                                                    │
╰─────────────────────────────────────────────────────────╯

╭──────────────────── STAGE MOVEMENTS THIS RUN ───────────╮
│  Applicant (ID)     From Stage         To Stage         │
│  John Doe (17834)   Applied            Phone Screened   │
╰─────────────────────────────────────────────────────────╯
```

If any downloads failed, a red warning panel is shown — check the log file for details.

---

## Viewing the Dashboard Without Re-downloading

Use `--report` to render the dashboard from the existing state file at any time — no API calls, no downloads.

```bash
uv run main.py --job-id 224 --report
```

This reads `downloads/state_224.json` and displays the summary and stage breakdown immediately. Useful for checking the current status of a job's downloads at a glance.

> **Note:** `--report` shows totals and stage distribution based on the last known state.
> The **Stage Movements** table and **Skipped** count will not appear — those are tracked per run only and are not stored in the state file.

---

## All Parameters

| Parameter | Required | Default | Description |
|---|---|---|---|
| `--job-id N` | Yes* | — | Job Opening ID to download resumes for |
| `--list-jobs` | No | — | List job openings and their IDs, then exit |
| `--status STATUS` | No | `Open` | Job status filter for `--list-jobs` |
| `--applicant-status STATUS` | No | `ALL` | Which applicants to download (see table above) |
| `--test` | No | — | Test API connection only, then exit |
| `--force` | No | — | Re-download all resumes even if already cached |
| `--migrate` | No | — | Reorganize v1 flat files into v2 stage subfolders |
| `--report` | No | — | Show dashboard from existing state file, no download |
| `--download-dir PATH` | No | `.env` value | Override download directory |
| `--delay SECONDS` | No | `.env` value | Seconds between API calls (default 2.0) |
| `--version` | No | — | Print version and exit |

*`--job-id` is not required when using `--list-jobs` or `--test`.

### `.env` Settings

| Variable | Required | Default | Description |
|---|---|---|---|
| `BAMBOOHR_API_KEY` | Yes | — | BambooHR API key |
| `BAMBOOHR_SUBDOMAIN` | Yes | — | BambooHR subdomain (e.g. `dysrupit`) |
| `DOWNLOAD_DIR` | No | `./resume_downloads` | Base folder for downloaded files |
| `API_DELAY_SECONDS` | No | `2.0` | Delay between API/download calls |

---

## Testing

### Test 1 — Connection only

```bash
uv run main.py --test
```

Confirms the API key and subdomain are valid without downloading anything.

### Test 2 — List jobs

```bash
uv run main.py --list-jobs
```

Confirms ATS API access and shows available job IDs.

### Test 3 — Download all applicants

```bash
uv run main.py --job-id 224
```

Downloads resumes into stage subfolders. Run again — already-downloaded files are skipped, stage-changed applicants are moved.

### Test 4 — Download active applicants only

```bash
uv run main.py --job-id 224 --applicant-status ALL_ACTIVE
```

Confirms the applicant status filter works.

### Test 5 — Force re-download

```bash
uv run main.py --job-id 224 --force
```

Downloads everything again regardless of cache. Useful after resumes have been updated in BambooHR.

---

## How to Reset and Re-download All Resumes for a Job

Each job has its own state file that tracks what has been downloaded:

```
downloads/state_{job_id}.json
```

### Steps to reset:

**1. Delete the state file:**

```bash
rm downloads/state_224.json
```

**2. Delete the downloaded files:**

```bash
rm -rf downloads/job_224/
```

**3. Run the download again:**

```bash
uv run main.py --job-id 224
```

> **Tip:** To re-download without manually deleting files, use `--force`. It will overwrite existing files and reset the tracker:
> ```bash
> uv run main.py --job-id 224 --force
> ```

---

## Log Files

Every run creates a timestamped log file in `logs/`:

```
logs/bamboohr_2026-04-16_09-30-00.log
```

Logs contain full detail: each applicant's name, stage, download size, skips, file movements, and errors. Always check the log when a download fails — the error and applicant details are recorded there.

---

## Troubleshooting

| Problem | Likely Cause | Fix |
|---|---|---|
| `Missing required environment variable` | `.env` not created or empty | Copy `.env.example` to `.env` and fill in values |
| `Authentication failed` | Wrong API key | Regenerate key in BambooHR → API Keys |
| `Access forbidden` | API key lacks ATS permissions | Enable ATS/applicant tracking access on the key |
| `TypeError: unsupported operand type(s) for \|` | Python 3.9 incompatibility (fixed in v2) | Ensure you have the latest `tracker.py` |
| `uv: command not found` | uv not installed or not on PATH | Install uv (see Prerequisites) and reopen the terminal |
| `No interpreter found for Python 3.12` | uv couldn't fetch Python | Run `uv python install 3.12`, then `uv sync` |
| All applicants skipped on first run | Stale state file from a previous run | Delete `downloads/state_{job_id}.json` and re-run |
| File moved to wrong stage folder | Stage changed in BambooHR since last run | This is expected — re-run without `--force` to auto-move |
| `--migrate` moves 0 files | Files are already in v2 format, or wrong job ID | Check the job directory for v1-style filenames |
| Downloaded resume belongs to a different person | Very old bug (pre-v1) — was using application ID instead of `resumeFileId` | Delete state file and downloaded files, re-run with latest code |
