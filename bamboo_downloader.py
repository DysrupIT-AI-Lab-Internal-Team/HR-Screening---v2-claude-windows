#!/usr/bin/env python3
"""
BambooHR Resume Downloader — menu-driven front-end.

This wraps the BambooHR downloader (the bamboohr/ package — originally a
standalone argparse CLI) in the same interactive, numbered-menu navigation used
throughout HR Screening Tool v2.  Every feature of the old CLI is reachable here
without typing flags:

  * List Job Openings                (was: --list-jobs [--status ...])
  * Download Resumes for a Job        (was: --job-id N [--applicant-status ...] [--force])
  * Show Download Report / dashboard  (was: --job-id N --report)
  * Migrate v1 files -> v2 folders     (was: --job-id N --migrate)
  * Test API Connection               (was: --test)

Navigation matches the rest of the tool: [0] goes back, and typing 'b' at any
prompt returns to the menu via the shared BackToMenu exception.
"""

import os
import re
import time

from cli_common import BackToMenu, print_header, print_submenu, nav_input
from bamboohr.logger import get_logger
from bamboohr.client import (
    BambooHRClient,
    AuthError,
    NotFoundError,
    RateLimitError,
    APIError,
)
from bamboohr.files import build_filename, save_file, stage_to_folder
from bamboohr.tracker import (
    DownloadTracker,
    STATUS_DOWNLOADED,
    STATUS_FAILED,
    STATUS_NO_RESUME,
)
from bamboohr.stats import StatsCollector

# Pattern to detect v1-style filenames: (Stage_Label)_AppID_...
_V1_FILENAME_RE = re.compile(r"^\((.+?)\)_(\d+)_(.+)$")

JOB_STATUSES = ["Open", "On Hold", "Filled", "Canceled", "Draft", "All"]
APPLICANT_STATUSES = ["ALL", "ALL_ACTIVE", "ACTIVE", "HIRED", "INACTIVE"]


class ConfigError(Exception):
    pass


# ─────────────────────────────────────────────
# CONFIG (read lazily so the main tool still runs
# when BambooHR credentials are not configured)
# ─────────────────────────────────────────────

def _load_config():
    """
    Read BambooHR settings from the environment.

    Returns (api_key, subdomain, download_dir, delay_seconds).
    Raises ConfigError with a friendly message if credentials are missing so the
    Download Resume menu can report it without crashing the whole tool.
    """
    api_key = os.getenv("BAMBOOHR_API_KEY", "").strip()
    subdomain = os.getenv("BAMBOOHR_SUBDOMAIN", "").strip()
    download_dir = os.getenv("DOWNLOAD_DIR", "./resume_downloads").strip() or "./resume_downloads"
    delay_raw = os.getenv("API_DELAY_SECONDS", "2.0").strip() or "2.0"
    try:
        delay = float(delay_raw)
    except ValueError:
        delay = 2.0

    missing = [
        k for k, v in (("BAMBOOHR_API_KEY", api_key), ("BAMBOOHR_SUBDOMAIN", subdomain))
        if not v
    ]
    if missing:
        raise ConfigError(
            "Missing required BambooHR setting(s): " + ", ".join(missing) + "\n"
            "     Add them to your .env file (see .env.example):\n"
            "       BAMBOOHR_API_KEY=your-api-key\n"
            "       BAMBOOHR_SUBDOMAIN=your-company-subdomain"
        )
    return api_key, subdomain, download_dir, delay


# ─────────────────────────────────────────────
# JOB FOLDER NAMING  ("<id> - <requisition name>")
# ─────────────────────────────────────────────

def _safe_dirname(name):
    """Strip characters invalid in Windows folder names; keep spaces and hyphens."""
    cleaned = re.sub(r'[<>:"/\\|?*]', "", name)
    cleaned = re.sub(r"\s+", " ", cleaned).strip().rstrip(".")
    return cleaned


def _job_folder_name(job_id, job_title):
    """
    Folder name for a job's downloads, e.g. '788 - Dynamics CRM developer'.
    Falls back to the legacy 'job_<id>' form when the title is unknown.
    """
    title = _safe_dirname(job_title or "")
    return f"{job_id} - {title}" if title else f"job_{job_id}"


def _resolve_job_dir(download_dir, job_id, job_title):
    """
    Return the download folder path for a job.

    Prefers the new '<id> - <title>' folder, but if an older 'job_<id>' folder
    already exists (from before this naming change) it is reused so existing
    downloads keep working without duplication.
    """
    new_dir = os.path.join(download_dir, _job_folder_name(job_id, job_title))
    if os.path.isdir(new_dir):
        return new_dir
    legacy = os.path.join(download_dir, f"job_{job_id}")
    if os.path.isdir(legacy):
        return legacy
    return new_dir


def _lookup_job_title(client, job_id, log):
    """Best-effort lookup of a job opening's title (for folder naming)."""
    try:
        jobs = client.get_jobs(status_filter="All")
    except (AuthError, APIError) as e:
        log.warning(f"Could not look up job title: {e}")
        return ""
    for job in jobs:
        if str(job.get("id")) == str(job_id):
            return job.get("title", {}).get("label", "") or ""
    return ""


# ─────────────────────────────────────────────
# SHARED PROMPT HELPERS (menu-driven equivalents
# of the old --status / --applicant-status flags)
# ─────────────────────────────────────────────

def _choose_from(options, label, default):
    """Print a numbered list and return the chosen value (Enter picks default)."""
    print(f"\n  {label}:")
    for i, opt in enumerate(options, 1):
        marker = "  (default)" if opt == default else ""
        print(f"    [{i}] {opt}{marker}")
    choice = nav_input(f"\n  Select {label.lower()} [default: {default}]: ")
    if not choice:
        return default
    if choice.isdigit() and 1 <= int(choice) <= len(options):
        return options[int(choice) - 1]
    return choice  # allow a custom value to be typed through


# ─────────────────────────────────────────────
# FEATURE: LIST JOBS
# ─────────────────────────────────────────────

def _list_jobs(client, status_filter, log):
    try:
        jobs = client.get_jobs(status_filter=status_filter)
    except AuthError as e:
        log.error(f"Authentication failed: {e}")
        return
    except APIError as e:
        log.error(f"Failed to fetch jobs: {e}")
        return

    if not jobs:
        print(f"\n  No jobs found with status: {status_filter}\n")
        return

    width = 70
    print(f"\n{'=' * width}")
    print(f"  Job Openings — Status: {status_filter}")
    print(f"{'=' * width}")
    print(f"  {'ID':<8} {'Status':<12} Title")
    print(f"  {'-'*6}  {'-'*10}  {'-'*45}")
    for job in jobs:
        jid = job.get("id", "?")
        jstatus = job.get("status", {}).get("label", "?")
        jtitle = job.get("title", {}).get("label", "?")
        print(f"  {jid:<8} {jstatus:<12} {jtitle}")
    print(f"{'=' * width}")
    print(f"  Total: {len(jobs)} job(s)\n")


def _menu_list_jobs(client, log):
    print_header("[R]  List Job Openings")
    status = _choose_from(JOB_STATUSES, "Job status filter", "Open")
    _list_jobs(client, status, log)


# ─────────────────────────────────────────────
# FEATURE: DOWNLOAD RESUMES FOR A JOB
# ─────────────────────────────────────────────

def _prompt_job_id(client, log):
    """Ask for a job ID, offering to list jobs first if the user isn't sure."""
    job_id_str = nav_input("\n  Enter Job Opening ID (or press Enter to list jobs first): ")
    if not job_id_str:
        _list_jobs(client, "Open", log)
        job_id_str = nav_input("\n  Enter Job Opening ID: ")
    if not job_id_str.isdigit():
        print("\n  [!]  Invalid job ID — must be a number.\n")
        return None
    return int(job_id_str)


def _download_job(client, job_id, applicant_status, download_dir, force, log):
    """Core download loop — one resume per application, organized by pipeline stage."""
    log.info(f"Job ID    : {job_id}")
    log.info(f"Applicants: {applicant_status}")

    tracker = DownloadTracker(job_id=job_id, base_dir=download_dir)

    try:
        applications = client.get_applications(job_id, application_status=applicant_status)
    except AuthError as e:
        log.error(f"Auth error fetching applications: {e}")
        return
    except APIError as e:
        log.error(f"Failed to fetch applications: {e}")
        return

    if not applications:
        log.warning(f"No applications found for job ID {job_id}.")
        return

    # Derive the job title from the applications so the folder can be named
    # "<id> - <requisition name>" (e.g. "788 - Dynamics CRM developer").
    job_title = applications[0].get("job", {}).get("title", {}).get("label", "")
    job_dir = _resolve_job_dir(download_dir, job_id, job_title)
    os.makedirs(job_dir, exist_ok=True)
    log.info(f"Download directory: {os.path.abspath(job_dir)}")

    stats = StatsCollector(job_id=job_id, job_title=job_title)

    log.info(f"Processing {len(applications)} application(s)...")

    for i, app in enumerate(applications, start=1):
        app_id = app.get("id")
        if not app_id:
            log.warning(f"[{i}/{len(applications)}] Skipping entry with no ID: {app}")
            continue

        app_id = int(app_id)

        applicant = app.get("applicant", {})
        first_name = applicant.get("firstName", "")
        last_name = applicant.get("lastName", "")
        position = app.get("job", {}).get("title", {}).get("label", "") or "Unknown_Position"
        applicant_name = f"{first_name} {last_name}".strip() or f"Applicant_{app_id}"
        applicant_stage = app.get("status", {}).get("label", "")
        stats.record_stage(applicant_stage)

        log.info(f"[{i}/{len(applications)}] {applicant_name} (ID: {app_id}) [{applicant_stage}]")

        # Check tracker for existing record
        record = tracker.get_record(app_id)
        if record and record.get("status") == STATUS_DOWNLOADED and not force:
            old_stage = record.get("applicant_stage", "")
            if old_stage == applicant_stage:
                log.info("  -> Already downloaded, skipping.")
                stats.record_skipped()
                continue
            else:
                # Stage changed — move file to new folder without re-downloading
                old_filename = record.get("filename", "")
                old_path = os.path.join(job_dir, stage_to_folder(old_stage), old_filename)
                new_folder_path = os.path.join(job_dir, stage_to_folder(applicant_stage))
                new_path = os.path.join(new_folder_path, old_filename)
                try:
                    os.makedirs(new_folder_path, exist_ok=True)
                    os.rename(old_path, new_path)
                    log.info(f"  -> Stage changed [{old_stage}] -> [{applicant_stage}], moved file.")
                    tracker.mark(
                        app_id,
                        STATUS_DOWNLOADED,
                        applicant_name=applicant_name,
                        applicant_stage=applicant_stage,
                        filename=old_filename,
                        file_size_bytes=record.get("file_size_bytes", 0),
                    )
                except OSError as e:
                    log.warning(f"  -> Could not move file: {e}. Skipping.")
                stats.record_moved(applicant_name, app_id, old_stage, applicant_stage)
                continue

        # Download resume
        file_bytes = None
        for attempt in range(2):
            try:
                file_bytes, content_type = client.download_resume(app_id)
                break
            except NotFoundError:
                log.warning(f"  -> No resume found for application {app_id}.")
                tracker.mark(app_id, STATUS_NO_RESUME, applicant_name=applicant_name, applicant_stage=applicant_stage)
                stats.record_no_resume()
                file_bytes = None
                break
            except RateLimitError as e:
                wait = e.retry_after or 30
                log.warning(f"  -> Rate limited. Waiting {wait}s before retry...")
                time.sleep(wait)
                if attempt == 1:
                    log.error(f"  -> Rate limit retry failed for {app_id}.")
                    tracker.mark(app_id, STATUS_FAILED, applicant_name=applicant_name, applicant_stage=applicant_stage, error_message=str(e))
                    stats.record_failed()
                    file_bytes = None
            except (APIError, Exception) as e:
                log.error(f"  -> Download error for {app_id}: {e}")
                tracker.mark(app_id, STATUS_FAILED, applicant_name=applicant_name, applicant_stage=applicant_stage, error_message=str(e))
                stats.record_failed()
                file_bytes = None
                break

        if file_bytes is None:
            continue

        # Save file into stage subfolder
        stage_folder_path = os.path.join(job_dir, stage_to_folder(applicant_stage))
        os.makedirs(stage_folder_path, exist_ok=True)
        filename = build_filename(app_id, first_name, last_name, position, content_type)
        dest_path = os.path.join(stage_folder_path, filename)

        try:
            size = save_file(file_bytes, dest_path)
            log.info(f"  -> Saved: {stage_to_folder(applicant_stage)}/{filename} ({size:,} bytes)")
            tracker.mark(
                app_id,
                STATUS_DOWNLOADED,
                applicant_name=applicant_name,
                applicant_stage=applicant_stage,
                filename=filename,
                file_size_bytes=size,
            )
            stats.record_downloaded()
        except OSError as e:
            log.error(f"  -> Failed to write file {filename}: {e}")
            tracker.mark(app_id, STATUS_FAILED, applicant_name=applicant_name, applicant_stage=applicant_stage, error_message=str(e))
            stats.record_failed()

    stats.print_summary()


def _menu_download(client, download_dir, log):
    print_header("[R]  Download Resumes for a Job")
    job_id = _prompt_job_id(client, log)
    if job_id is None:
        return
    applicant_status = _choose_from(APPLICANT_STATUSES, "Applicant status filter", "ALL")
    force = nav_input("\n  Re-download even if already downloaded? (y/n) [default: n]: ").lower() == "y"
    _download_job(client, job_id, applicant_status, download_dir, force, log)


# ─────────────────────────────────────────────
# FEATURE: REPORT / DASHBOARD (from saved state)
# ─────────────────────────────────────────────

def _menu_report(download_dir, log):
    print_header("[R]  Download Report (Dashboard)")
    job_id_str = nav_input("\n  Enter Job Opening ID to report on: ")
    if not job_id_str.isdigit():
        print("\n  [!]  Invalid job ID — must be a number.\n")
        return
    job_id = int(job_id_str)

    tracker = DownloadTracker(job_id=job_id, base_dir=download_dir)
    if not tracker._state:
        log.error(
            f"No state file found for job {job_id}. "
            "Run a download first before viewing the report."
        )
        return

    stats = StatsCollector(job_id=job_id, job_title="")
    for record in tracker._state.values():
        status = record.get("status", "")
        stage = record.get("applicant_stage", "Unknown")
        stats.record_stage(stage)
        if status == STATUS_DOWNLOADED:
            stats.record_downloaded()
        elif status == STATUS_NO_RESUME:
            stats.record_no_resume()
        elif status == STATUS_FAILED:
            stats.record_failed()

    stats.print_summary()


# ─────────────────────────────────────────────
# FEATURE: MIGRATE v1 files -> v2 stage folders
# ─────────────────────────────────────────────

def _migrate_v1_files(job_dir, tracker, log):
    """
    Move v1-style flat files (e.g. (Phone_Screened)_17834_John_Doe_Dev.pdf) into
    the appropriate stage subfolder, strip the stage prefix, and update tracking.
    """
    if not os.path.isdir(job_dir):
        log.error(f"Job directory does not exist: {job_dir}")
        return

    moved = 0
    skipped = 0

    for fname in os.listdir(job_dir):
        src = os.path.join(job_dir, fname)
        if not os.path.isfile(src):
            continue  # skip subdirectories

        match = _V1_FILENAME_RE.match(fname)
        if not match:
            log.debug(f"  Skipping (not a v1 filename): {fname}")
            skipped += 1
            continue

        raw_stage = match.group(1)
        app_id_str = match.group(2)
        rest = match.group(3)

        folder_name = stage_to_folder(raw_stage)
        new_filename = f"{app_id_str}_{rest}"
        dest_dir = os.path.join(job_dir, folder_name)
        dest = os.path.join(dest_dir, new_filename)

        try:
            os.makedirs(dest_dir, exist_ok=True)
            os.rename(src, dest)
            log.info(f"  Moved: {fname} -> {folder_name}/{new_filename}")

            app_id = int(app_id_str)
            record = tracker.get_record(app_id)
            if record and record.get("status") == STATUS_DOWNLOADED:
                tracker.mark(
                    app_id,
                    STATUS_DOWNLOADED,
                    applicant_name=record.get("applicant_name", ""),
                    applicant_stage=record.get("applicant_stage", raw_stage),
                    filename=new_filename,
                    file_size_bytes=record.get("file_size_bytes", 0),
                )
            moved += 1
        except OSError as e:
            log.warning(f"  Failed to move {fname}: {e}")
            skipped += 1

    log.info(f"Migration complete: {moved} file(s) moved, {skipped} skipped.")


def _menu_migrate(client, download_dir, log):
    print_header("[R]  Migrate v1 Files -> v2 Stage Folders")
    job_id_str = nav_input("\n  Enter Job Opening ID to migrate: ")
    if not job_id_str.isdigit():
        print("\n  [!]  Invalid job ID — must be a number.\n")
        return
    job_id = int(job_id_str)
    job_title = _lookup_job_title(client, job_id, log)
    job_dir = _resolve_job_dir(download_dir, job_id, job_title)
    tracker = DownloadTracker(job_id=job_id, base_dir=download_dir)
    log.info("Running v1 -> v2 migration...")
    _migrate_v1_files(job_dir, tracker, log)


# ─────────────────────────────────────────────
# FEATURE: TEST API CONNECTION
# ─────────────────────────────────────────────

def _menu_test(client, log):
    print_header("[R]  Test API Connection")
    try:
        client.test_connection()
        log.info("Connection test passed.")
        print("\n  [OK]  BambooHR API connection is working.\n")
    except AuthError as e:
        log.error(f"Authentication failed: {e}")
        print("\n  [X]  Authentication failed — check BAMBOOHR_API_KEY in your .env.\n")
    except APIError as e:
        log.error(f"Connection test failed: {e}")
        print("\n  [X]  Connection test failed. See log for details.\n")


# ─────────────────────────────────────────────
# ENTRY POINT (called from the main menu)
# ─────────────────────────────────────────────

def download_resume_menu():
    """Interactive Download Resume submenu, navigated like the rest of the tool."""
    print_header("[R]  Download Resume (BambooHR)")

    try:
        api_key, subdomain, download_dir, delay = _load_config()
    except ConfigError as e:
        print(f"\n  [X]  {e}\n")
        return

    log = get_logger()
    client = BambooHRClient(api_key=api_key, subdomain=subdomain, delay_seconds=delay)
    log.info(f"BambooHR subdomain: {subdomain}  |  delay: {delay}s")

    while True:
        print_header("[R]  Download Resume (BambooHR)")
        try:
            choice = print_submenu([
                "List Job Openings",
                "Download Resumes for a Job",
                "Show Download Report (dashboard)",
                "Migrate v1 Files -> v2 Stage Folders",
                "Test API Connection",
            ])
        except BackToMenu:
            return

        try:
            if choice == 1:
                _menu_list_jobs(client, log)
            elif choice == 2:
                _menu_download(client, download_dir, log)
            elif choice == 3:
                _menu_report(download_dir, log)
            elif choice == 4:
                _menu_migrate(client, download_dir, log)
            elif choice == 5:
                _menu_test(client, log)
        except BackToMenu:
            continue

        input("\n  Press Enter to continue...")
