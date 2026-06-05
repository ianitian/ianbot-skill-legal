import io
from functools import lru_cache
from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

from core.config import get_settings

DRIVE_READONLY_SCOPE = "https://www.googleapis.com/auth/drive.readonly"


class DriveNotConfiguredError(RuntimeError):
    """Raised when GOOGLE_APPLICATION_CREDENTIALS is missing or not a file."""


class DriveDownloadError(RuntimeError):
    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        self.message = message
        super().__init__(message)


@lru_cache
def _get_drive_service() -> Any:
    settings = get_settings()
    creds_path = settings.google_application_credentials
    if not creds_path or not creds_path.strip():
        raise DriveNotConfiguredError("GOOGLE_APPLICATION_CREDENTIALS is not set")
    creds = service_account.Credentials.from_service_account_file(
        creds_path,
        scopes=[DRIVE_READONLY_SCOPE],
    )
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def download_pdf(drive_file_id: str) -> bytes:
    """Download a Drive file into memory. Caller must not persist bytes to disk."""
    settings = get_settings()
    if not settings.drive_configured:
        raise DriveNotConfiguredError("Drive credentials are not configured")

    try:
        drive = _get_drive_service()
        request = drive.files().get_media(fileId=drive_file_id, supportsAllDrives=True)
        buf = io.BytesIO()
        downloader = MediaIoBaseDownload(buf, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        data = buf.getvalue()
    except HttpError as exc:
        status = exc.resp.status if exc.resp else 0
        raise DriveDownloadError(status, f"Drive API error for file {drive_file_id}") from exc

    if not data:
        raise DriveDownloadError(0, "Downloaded file is empty")
    if data[:4] != b"%PDF":
        raise DriveDownloadError(0, "Downloaded content is not a PDF")

    return data
