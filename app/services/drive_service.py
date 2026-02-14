"""
Drive service: Google Drive API integration, recursive scan, download.

Business logic separated from HTTP layer. All Drive API calls use timeouts
and respect config limits (scan folders/files, download count, stream size).
"""
import os
import re
from typing import Any

import requests

from config import (
    DRIVE_DOWNLOAD_TIMEOUT,
    DRIVE_REQUEST_TIMEOUT,
    MAX_DOWNLOAD_FILES,
    MAX_ELIGIBLE_FILE_SIZE_BYTES,
    MAX_SCAN_FILES,
    MAX_SCAN_FOLDERS,
    STORAGE_ROOT,
)

# Supported book formats for later TTS pipeline
ELIGIBLE_MIME_TYPES = {
    "application/pdf",
    "application/epub+zip",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

FOLDER_MIME = "application/vnd.google-apps.folder"


def _drive_request(
    method: str,
    url: str,
    access_token: str,
    **kwargs: Any,
) -> dict | list | None:
    """Call Drive API with timeout; returns JSON. Raises on HTTP errors."""
    headers = {"Authorization": f"Bearer {access_token}"}
    if "headers" in kwargs:
        headers.update(kwargs.pop("headers"))
    kwargs.setdefault("timeout", DRIVE_REQUEST_TIMEOUT)
    resp = requests.request(method, url, headers=headers, **kwargs)
    resp.raise_for_status()
    if resp.content:
        return resp.json()
    return None


def _list_page(
    access_token: str,
    parent_id: str,
    page_token: str | None = None,
) -> dict:
    """List files and folders in a single Drive folder (one page)."""
    params = {
        "q": f"'{parent_id}' in parents and trashed = false",
        "fields": "nextPageToken, files(id, name, mimeType, size)",
    }
    if page_token:
        params["pageToken"] = page_token
    data = _drive_request(
        "GET",
        "https://www.googleapis.com/drive/v3/files",
        access_token,
        params=params,
    )
    return data or {"files": [], "nextPageToken": None}


class ScanLimitExceeded(Exception):
    """Raised when recursive scan exceeds MAX_SCAN_FOLDERS or MAX_SCAN_FILES."""

    def __init__(self, msg: str):
        self.msg = msg
        super().__init__(msg)


def collect_eligible_recursive(
    access_token: str,
    folder_id: str,
    max_size_bytes: int = MAX_ELIGIBLE_FILE_SIZE_BYTES,
) -> list[dict]:
    """
    Recursively list eligible files under folder_id. Respects MAX_SCAN_FOLDERS
    and MAX_SCAN_FILES. Returns list of {id, name, mimeType, size}.
    Raises ScanLimitExceeded if limits exceeded.
    """
    result: list[dict] = []
    stack = [folder_id]
    seen = {folder_id}
    folders_processed = 0

    while stack:
        if folders_processed >= MAX_SCAN_FOLDERS:
            raise ScanLimitExceeded(
                f"Scan limit exceeded: max {MAX_SCAN_FOLDERS} folders"
            )
        if len(result) >= MAX_SCAN_FILES:
            raise ScanLimitExceeded(
                f"Scan limit exceeded: max {MAX_SCAN_FILES} eligible files"
            )

        parent_id = stack.pop()
        folders_processed += 1
        page_token = None

        while True:
            page = _list_page(access_token, parent_id, page_token)
            for f in page.get("files", []):
                fid = f.get("id")
                if not fid:
                    continue
                mime = f.get("mimeType") or ""
                if mime == FOLDER_MIME:
                    if fid not in seen:
                        seen.add(fid)
                        stack.append(fid)
                    continue
                if mime not in ELIGIBLE_MIME_TYPES:
                    continue
                size_raw = f.get("size")
                if size_raw is not None:
                    try:
                        size_int = int(size_raw)
                    except (ValueError, TypeError):
                        continue
                    if size_int > max_size_bytes:
                        continue
                    size = size_raw
                else:
                    size = None

                if len(result) >= MAX_SCAN_FILES:
                    raise ScanLimitExceeded(
                        f"Scan limit exceeded: max {MAX_SCAN_FILES} eligible files"
                    )
                result.append({
                    "id": fid,
                    "name": f.get("name", "unknown"),
                    "mimeType": mime,
                    "size": size,
                })
            page_token = page.get("nextPageToken")
            if not page_token:
                break

    return result


def validate_folder(access_token: str, folder_id: str) -> bool:
    """
    Verify folder_id exists, belongs to user's Drive, and is a folder.
    Returns True if valid; False if not found or not a folder; raises on other API errors.
    """
    try:
        data = _drive_request(
            "GET",
            f"https://www.googleapis.com/drive/v3/files/{folder_id}",
            access_token,
            params={"fields": "id, mimeType"},
        )
    except requests.exceptions.HTTPError as e:
        if e.response is not None and e.response.status_code == 404:
            return False
        raise
    if not data:
        return False
    mime = data.get("mimeType")
    return mime == FOLDER_MIME


def safe_filename(name: str) -> str:
    """Remove path separators and reserved chars so name is safe for filesystem."""
    safe = re.sub(r'[\\/:*?"<>|\s]+', "_", name)
    if len(safe) > 200:
        safe = safe[:200]
    return safe or "unnamed"


def user_storage_path(user_id: str, *parts: str) -> str:
    """Build path under storage/users/user_<id>/...; create dirs if needed."""
    path = os.path.join(STORAGE_ROOT, "users", f"user_{user_id}", *parts)
    os.makedirs(path, exist_ok=True)
    return path


def download_file_with_size_limit(
    access_token: str,
    file_id: str,
    dest_path: str,
    max_bytes: int = MAX_ELIGIBLE_FILE_SIZE_BYTES,
) -> str:
    """
    Stream file from Drive to dest_path. Aborts and deletes partial file
    if content exceeds max_bytes. Returns final filename (may have _N suffix).
    """
    resp = requests.get(
        f"https://www.googleapis.com/drive/v3/files/{file_id}",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"alt": "media"},
        stream=True,
        timeout=DRIVE_DOWNLOAD_TIMEOUT,
    )
    resp.raise_for_status()

    total = 0
    try:
        with open(dest_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                total += len(chunk)
                if total > max_bytes:
                    f.close()
                    if os.path.exists(dest_path):
                        os.remove(dest_path)
                    raise ValueError(
                        f"File exceeds max size ({max_bytes} bytes); "
                        f"aborted at {total} bytes"
                    )
                f.write(chunk)
    except (ValueError, IOError):
        if os.path.exists(dest_path):
            try:
                os.remove(dest_path)
            except OSError:
                pass
        raise
    return os.path.basename(dest_path)


def resolve_download_path(raw_dir: str, base_name: str) -> str:
    """Return path for file; append _N if base_name already exists."""
    path = os.path.join(raw_dir, base_name)
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(base_name)
    for i in range(1, 100):
        path = os.path.join(raw_dir, f"{base}_{i}{ext}")
        if not os.path.exists(path):
            return path
    return os.path.join(raw_dir, f"{base}_99{ext}")
