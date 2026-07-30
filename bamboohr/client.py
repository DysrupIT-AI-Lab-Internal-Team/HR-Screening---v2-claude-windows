import time
import logging
import requests
from typing import Optional

logger = logging.getLogger("bamboohr")


class AuthError(Exception):
    pass


class PermissionError(Exception):
    pass


class NotFoundError(Exception):
    pass


class RateLimitError(Exception):
    def __init__(self, message: str, retry_after: Optional[int] = None):
        super().__init__(message)
        self.retry_after = retry_after


class APIError(Exception):
    def __init__(self, message: str, status_code: int):
        super().__init__(message)
        self.status_code = status_code


class BambooHRClient:
    BASE_URL = "https://api.bamboohr.com/api/gateway.php"

    def __init__(self, api_key: str, subdomain: str, delay_seconds: float = 2.0):
        self.subdomain = subdomain
        self.delay_seconds = delay_seconds
        self._last_call_time: float = 0.0

        self._session = requests.Session()
        self._session.auth = (api_key, "x")
        self._session.headers.update({
            "Accept": "application/json",
            "User-Agent": "DIT-BambooHR-Resume-Downloader/1.0",
        })

    def _url(self, path: str) -> str:
        return f"{self.BASE_URL}/{self.subdomain}/{path}"

    def _respect_rate_limit(self) -> None:
        elapsed = time.monotonic() - self._last_call_time
        if elapsed < self.delay_seconds:
            wait = self.delay_seconds - elapsed
            logger.debug(f"Rate limiting: sleeping {wait:.2f}s")
            time.sleep(wait)
        self._last_call_time = time.monotonic()

    def _handle_error(self, resp: requests.Response) -> None:
        if resp.status_code == 401:
            raise AuthError("Authentication failed — check your API key.")
        if resp.status_code == 403:
            raise PermissionError("Access forbidden — insufficient API permissions.")
        if resp.status_code == 404:
            raise NotFoundError(f"Resource not found: {resp.url}")
        if resp.status_code in (429, 503):
            retry_after = resp.headers.get("Retry-After")
            retry_int = int(retry_after) if retry_after and retry_after.isdigit() else None
            raise RateLimitError(
                f"Rate limited (HTTP {resp.status_code})", retry_after=retry_int
            )
        if not resp.ok:
            raise APIError(f"Unexpected status {resp.status_code}: {resp.url}", resp.status_code)

    def _get(self, path: str, **kwargs) -> requests.Response:
        self._respect_rate_limit()
        url = self._url(path)
        try:
            resp = self._session.get(url, timeout=120, **kwargs)
        except requests.Timeout:
            raise APIError(f"Request timed out: {url}", 0)
        except requests.ConnectionError as e:
            raise APIError(f"Connection error: {e}", 0)
        self._handle_error(resp)
        return resp

    def test_connection(self) -> None:
        logger.info("Testing BambooHR API connection...")
        self._get("v1/meta/users")
        logger.info("API connection successful.")

    def get_jobs(self, status_filter: str = "Open") -> list[dict]:
        """
        Returns job openings, optionally filtered by status.
        status_filter: "Open" | "On Hold" | "Filled" | "Canceled" | "Draft" | "All"
        """
        resp = self._get("v1/applicant_tracking/jobs")
        jobs = resp.json()
        if status_filter.lower() == "all":
            return jobs
        return [j for j in jobs if j.get("status", {}).get("label", "") == status_filter]

    def get_applications(self, job_id: int, application_status: str = "ALL") -> list[dict]:
        """
        Returns applications for a job opening.
        application_status: ALL | ALL_ACTIVE | NEW | ACTIVE | INACTIVE | HIRED
          - ALL        → every applicant ever (default)
          - ALL_ACTIVE → only those still in the running
        Handles pagination automatically (50 records per page).
        """
        logger.info(f"Fetching applications for job ID {job_id} (status filter: {application_status})...")
        all_applications: list[dict] = []
        page = 1

        while True:
            resp = self._get(
                "v1/applicant_tracking/applications",
                params={"jobId": job_id, "applicationStatus": application_status, "page": page},
            )
            data = resp.json()

            if isinstance(data, list):
                all_applications.extend(data)
                break

            apps = data.get("applications", [])
            all_applications.extend(apps)
            logger.debug(f"  Page {page}: {len(apps)} application(s)")

            if data.get("paginationComplete", True) or not apps:
                break
            page += 1

        logger.info(f"Found {len(all_applications)} application(s) for job ID {job_id}.")
        return all_applications

    def get_application_detail(self, app_id: int) -> dict:
        logger.debug(f"Fetching detail for application {app_id}...")
        resp = self._get(f"v1/applicant_tracking/applications/{app_id}")
        return resp.json()

    def get_resume_file_id(self, app_id: int) -> int:
        """
        Fetches the application detail and returns the resumeFileId.
        Raises NotFoundError if the application has no resume attached.
        """
        detail = self.get_application_detail(app_id)
        file_id = detail.get("resumeFileId")
        if not file_id:
            raise NotFoundError(f"No resume attached to application {app_id}")
        return int(file_id)

    def download_resume(self, app_id: int) -> tuple[bytes, str]:
        """
        Returns (file_bytes, content_type).
        Fetches the resumeFileId from the application detail first, then
        downloads /v1/files/{resumeFileId} — ensures the correct file is retrieved.
        Raises NotFoundError if the application has no resume attached.
        """
        file_id = self.get_resume_file_id(app_id)
        logger.debug(f"Application {app_id} → resumeFileId {file_id}")

        self._respect_rate_limit()
        url = self._url(f"v1/files/{file_id}")
        try:
            resp = self._session.get(url, timeout=120, headers={"Accept": "*/*"})
        except requests.Timeout:
            raise APIError(f"Request timed out: {url}", 0)
        except requests.ConnectionError as e:
            raise APIError(f"Connection error: {e}", 0)

        if resp.status_code == 404:
            raise NotFoundError(f"No file found for resumeFileId {file_id} (application {app_id})")
        self._handle_error(resp)
        return self._extract_file(resp, app_id)

    def _extract_file(self, resp: requests.Response, app_id: int) -> tuple[bytes, str]:
        content_type = resp.headers.get("Content-Type", "application/octet-stream")
        if "text/html" in content_type.lower():
            raise APIError(
                f"Received HTML instead of a file for application {app_id} — likely an error page.",
                resp.status_code,
            )
        return resp.content, content_type
