import io
import logging
from pathlib import Path
from typing import Any, Optional, Tuple

import google.auth
from google.auth.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

from core.config import Settings, get_settings

DRIVE_READONLY_SCOPE = "https://www.googleapis.com/auth/drive.readonly"

logger = logging.getLogger(__name__)


class DriveNotConfiguredError(RuntimeError):
    """Raised when Drive credentials are missing or invalid."""


class DriveDownloadError(RuntimeError):
    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        self.message = message
        super().__init__(message)


def _resolve_drive_auth_mode(settings: Settings) -> str:
    mode = (settings.drive_auth or "auto").strip().lower()
    if mode not in {"auto", "file", "adc"}:
        raise DriveNotConfiguredError(f"Invalid DRIVE_AUTH: {settings.drive_auth}")
    if mode == "auto":
        creds_path = settings.google_application_credentials
        if creds_path and creds_path.strip() and Path(creds_path).is_file():
            return "file"
        return "adc"
    return mode


def _credentials_file_path(settings: Settings) -> str:
    creds_path = settings.google_application_credentials
    if not creds_path or not creds_path.strip():
        raise DriveNotConfiguredError(
            "GOOGLE_APPLICATION_CREDENTIALS is not set (required when DRIVE_AUTH=file)"
        )
    if not Path(creds_path).is_file():
        raise DriveNotConfiguredError(
            f"GOOGLE_APPLICATION_CREDENTIALS file not found: {creds_path}"
        )
    return creds_path


def _load_drive_credentials(settings: Settings, mode: Optional[str] = None) -> Tuple[Credentials, str]:
    resolved_mode = mode or _resolve_drive_auth_mode(settings)
    scopes = [DRIVE_READONLY_SCOPE]

    if resolved_mode == "file":
        creds, _project = google.auth.load_credentials_from_file(
            _credentials_file_path(settings),
            scopes=scopes,
        )
        return creds, resolved_mode

    try:
        creds, _project = google.auth.default(scopes=scopes)
    except google.auth.exceptions.DefaultCredentialsError as exc:
        raise DriveNotConfiguredError(
            "Drive ADC not available (run gcloud auth application-default login "
            "or set GOOGLE_APPLICATION_CREDENTIALS to a credentials file)"
        ) from exc

    if hasattr(creds, "with_scopes_if_required"):
        creds = creds.with_scopes_if_required(scopes)
    return creds, resolved_mode


def _build_drive_service(settings: Settings, mode: str) -> Any:
    creds, _resolved = _load_drive_credentials(settings, mode=mode)
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def clear_drive_service_cache() -> None:
    """No-op retained for tests that clear settings between cases."""
    return None


def _download_pdf_with_service(drive: Any, drive_file_id: str) -> bytes:
    request = drive.files().get_media(fileId=drive_file_id, supportsAllDrives=True)
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buf.getvalue()


def download_pdf(drive_file_id: str) -> bytes:
    """Download a Drive file into memory. Caller must not persist bytes to disk."""
    settings = get_settings()
    if not settings.drive_configured:
        raise DriveNotConfiguredError("Drive credentials are not configured")

    primary_mode = _resolve_drive_auth_mode(settings)
    modes_to_try = [primary_mode]
    if (
        primary_mode == "adc"
        and settings.drive_sa_fallback_available
        and "file" not in modes_to_try
    ):
        modes_to_try.append("file")

    last_http_error: Optional[HttpError] = None
    for mode in modes_to_try:
        try:
            drive = _build_drive_service(settings, mode)
            data = _download_pdf_with_service(drive, drive_file_id)
        except HttpError as exc:
            status = exc.resp.status if exc.resp else 0
            if (
                status == 403
                and mode == "adc"
                and len(modes_to_try) > 1
            ):
                logger.warning(
                    "Drive ADC returned 403 for %s; retrying with SA file (DRIVE_DEBUG_SA_FALLBACK)",
                    drive_file_id,
                )
                last_http_error = exc
                continue
            raise DriveDownloadError(status, f"Drive API error for file {drive_file_id}") from exc

        if mode == "file" and primary_mode == "adc" and len(modes_to_try) > 1:
            logger.warning(
                "Drive download succeeded via SA fallback for %s (local debug only)",
                drive_file_id,
            )

        if not data:
            raise DriveDownloadError(0, "Downloaded file is empty")
        if data[:4] != b"%PDF":
            raise DriveDownloadError(0, "Downloaded content is not a PDF")
        return data

    if last_http_error is not None:
        status = last_http_error.resp.status if last_http_error.resp else 0
        raise DriveDownloadError(status, f"Drive API error for file {drive_file_id}") from last_http_error

    raise DriveDownloadError(0, f"Drive download failed for file {drive_file_id}")
