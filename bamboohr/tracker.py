import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("bamboohr")

STATUS_DOWNLOADED = "downloaded"
STATUS_SKIPPED = "skipped"
STATUS_FAILED = "failed"
STATUS_NO_RESUME = "no_resume"


class DownloadTracker:
    def __init__(self, job_id: int, base_dir: str):
        os.makedirs(base_dir, exist_ok=True)
        self._path = os.path.join(base_dir, f"state_{job_id}.json")
        self._state: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self._path):
            logger.debug(f"No existing state file at {self._path} — starting fresh.")
            return
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                self._state = json.load(f)
            logger.info(f"Loaded state: {len(self._state)} record(s) from {self._path}")
        except json.JSONDecodeError as e:
            logger.warning(f"State file corrupted ({e}) — starting fresh.")
            self._state = {}

    def get_record(self, app_id: int) -> Optional[dict]:
        """Returns the full stored record for an applicant, or None if not tracked."""
        return self._state.get(str(app_id))

    def is_downloaded(self, app_id: int) -> bool:
        record = self._state.get(str(app_id))
        return record is not None and record.get("status") == STATUS_DOWNLOADED

    def mark(
        self,
        app_id: int,
        status: str,
        applicant_name: str = "",
        applicant_stage: str = "",
        filename: str = "",
        file_size_bytes: int = 0,
        error_message: str = "",
    ) -> None:
        self._state[str(app_id)] = {
            "status": status,
            "applicant_name": applicant_name,
            "applicant_stage": applicant_stage,
            "filename": filename,
            "file_size_bytes": file_size_bytes,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "error_message": error_message,
        }
        self.save()

    def save(self) -> None:
        tmp_path = self._path + ".tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self._state, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, self._path)
        except OSError as e:
            logger.error(f"Failed to save state file: {e}")
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def summary(self) -> dict[str, int]:
        counts: dict[str, int] = {
            STATUS_DOWNLOADED: 0,
            STATUS_SKIPPED: 0,
            STATUS_FAILED: 0,
            STATUS_NO_RESUME: 0,
        }
        for record in self._state.values():
            s = record.get("status", "")
            if s in counts:
                counts[s] += 1
        return counts
