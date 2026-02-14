"""
Drive router: HTTP endpoints for root folder, file list, download.

Delegates business logic to services.drive_service. All Drive API access
uses get_valid_access_token (handles refresh). On 401, retries once after
forcing refresh. Enforces limits and validates inputs.
"""
import requests
from requests.exceptions import HTTPError as RequestsHTTPError
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth import get_current_user, get_valid_access_token
from config import MAX_DOWNLOAD_FILES, MAX_ELIGIBLE_FILE_SIZE_BYTES
from database import get_db
from models import User
from services.drive_service import (
    ScanLimitExceeded,
    collect_eligible_recursive,
    download_file_with_size_limit,
    safe_filename,
    user_storage_path,
    validate_folder,
    resolve_download_path,
)

router = APIRouter(prefix="/drive")


# --- Request models ---


class SetRootFolderBody(BaseModel):
    """Request body for setting the Drive root folder for book discovery."""
    folder_id: str = Field(..., min_length=1, max_length=255)


class DownloadBody(BaseModel):
    """Request body for downloading files by Drive file ids."""
    file_ids: list[str] = Field(..., max_length=MAX_DOWNLOAD_FILES)


# --- Endpoints ---


@router.post("/root-folder")
def set_root_folder(
    body: SetRootFolderBody,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Set the root folder in Google Drive from which the app will discover books.
    Validates that folder_id exists and is a folder before storing.
    """
    folder_id = body.folder_id.strip()
    if not folder_id:
        raise HTTPException(status_code=400, detail="folder_id cannot be empty")

    access_token = get_valid_access_token(user, db)
    try:
        valid = validate_folder(access_token, folder_id)
    except RequestsHTTPError as e:
        if getattr(e, "response", None) is not None and e.response.status_code == 401:
            access_token = get_valid_access_token(user, db, force_refresh=True)
            valid = validate_folder(access_token, folder_id)
        else:
            raise

    if not valid:
        raise HTTPException(
            status_code=400,
            detail="Folder not found or not a folder; check the ID and your Drive access",
        )

    user.drive_root_folder_id = folder_id
    db.commit()
    return {"ok": True, "folder_id": user.drive_root_folder_id}


@router.get("/root-folder")
def get_root_folder(user: User = Depends(get_current_user)):
    """Return the current root folder id if set."""
    return {"folder_id": user.drive_root_folder_id}


def _list_files_impl(access_token: str, folder_id: str):
    """Inner logic for list_files; may raise ScanLimitExceeded or requests.HTTPError."""
    return collect_eligible_recursive(
        access_token,
        folder_id,
        max_size_bytes=MAX_ELIGIBLE_FILE_SIZE_BYTES,
    )


@router.get("/files")
def list_files(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    List all eligible books under the user's chosen root folder (and its
    subfolders). Eligible = PDF, EPUB, DOCX and size <= MAX_ELIGIBLE_FILE_SIZE_BYTES.
    Scan is bounded by MAX_SCAN_FOLDERS and MAX_SCAN_FILES.
    Retries once on 401 after forcing token refresh.
    """
    if not user.drive_root_folder_id:
        return {"files": [], "message": "Set a root folder first (POST /drive/root-folder)"}

    access_token = get_valid_access_token(user, db)
    try:
        files = _list_files_impl(access_token, user.drive_root_folder_id)
    except RequestsHTTPError as e:
        if getattr(e, "response", None) is not None and e.response.status_code == 401:
            access_token = get_valid_access_token(user, db, force_refresh=True)
            files = _list_files_impl(access_token, user.drive_root_folder_id)
        else:
            raise
    except ScanLimitExceeded as e:
        raise HTTPException(status_code=400, detail=str(e.msg))
    return {"files": files}


@router.post("/download")
def download_files(
    body: DownloadBody,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Download the given Drive files to the user's storage namespace. Only files
    that are under the user's root folder and eligible can be downloaded.
    Max MAX_DOWNLOAD_FILES per request; stream size enforced.
    """
    if not body.file_ids:
        return {"downloaded": [], "message": "No file_ids provided"}

    if len(body.file_ids) > MAX_DOWNLOAD_FILES:
        raise HTTPException(
            status_code=400,
            detail=f"At most {MAX_DOWNLOAD_FILES} files per request",
        )

    if not user.drive_root_folder_id:
        raise HTTPException(
            status_code=400,
            detail="Set a root folder first (POST /drive/root-folder)",
        )

    access_token = get_valid_access_token(user, db)
    try:
        eligible = collect_eligible_recursive(
            access_token,
            user.drive_root_folder_id,
            max_size_bytes=MAX_ELIGIBLE_FILE_SIZE_BYTES,
        )
    except RequestsHTTPError as e:
        if getattr(e, "response", None) is not None and e.response.status_code == 401:
            access_token = get_valid_access_token(user, db, force_refresh=True)
            eligible = collect_eligible_recursive(
                access_token,
                user.drive_root_folder_id,
                max_size_bytes=MAX_ELIGIBLE_FILE_SIZE_BYTES,
            )
        else:
            raise
    except ScanLimitExceeded as e:
        raise HTTPException(status_code=400, detail=str(e.msg))

    allowed_ids = {f["id"] for f in eligible}
    name_by_id = {f["id"]: f["name"] for f in eligible}

    for fid in body.file_ids:
        if fid not in allowed_ids:
            raise HTTPException(
                status_code=400,
                detail=f"File {fid} is not an eligible file under your root folder",
            )

    raw_dir = user_storage_path(user.id, "drive", "raw")
    downloaded: list[str] = []

    for fid in body.file_ids:
        name = name_by_id.get(fid, "unknown")
        safe_name = safe_filename(name) or fid
        dest_path = resolve_download_path(raw_dir, safe_name)

        try:
            basename = download_file_with_size_limit(
                access_token,
                fid,
                dest_path,
                max_bytes=MAX_ELIGIBLE_FILE_SIZE_BYTES,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        downloaded.append(basename)

    return {"downloaded": downloaded}
