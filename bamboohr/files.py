import os
import re
import logging

logger = logging.getLogger("bamboohr")

_CONTENT_TYPE_TO_EXT = {
    "application/pdf": ".pdf",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/zip": ".zip",
    "text/plain": ".txt",
    "application/rtf": ".rtf",
}


def _sanitize(value: str) -> str:
    value = value.strip()
    value = re.sub(r"[^\w\s-]", "", value)
    value = re.sub(r"[\s/\\]+", "_", value)
    return value or "unknown"


def content_type_to_ext(content_type: str) -> str:
    base = content_type.split(";")[0].strip().lower()
    for mime, ext in _CONTENT_TYPE_TO_EXT.items():
        if mime in base:
            return ext
    if "pdf" in base:
        return ".pdf"
    if "word" in base or "officedocument" in base:
        return ".docx"
    if "text" in base:
        return ".txt"
    return ".bin"


def stage_to_folder(stage: str) -> str:
    """Returns a sanitized folder name for the given pipeline stage."""
    return _sanitize(stage) if stage.strip() else "Unknown_Stage"


def build_filename(
    app_id: int,
    first_name: str,
    last_name: str,
    position: str,
    content_type: str,
) -> str:
    """Builds a filename without stage prefix — stage is now the parent folder."""
    ext = content_type_to_ext(content_type)
    first = _sanitize(first_name)
    last = _sanitize(last_name)
    pos = _sanitize(position)
    return f"{app_id}_{first}_{last}_{pos}{ext}"


def save_file(data: bytes, dest_path: str) -> int:
    tmp_path = dest_path + ".tmp"
    try:
        with open(tmp_path, "wb") as f:
            f.write(data)
        os.replace(tmp_path, dest_path)
        return len(data)
    except OSError as e:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise e
