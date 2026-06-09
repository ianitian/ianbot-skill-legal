from typing import Optional

from fastapi import APIRouter, Depends

from core.auth import verify_ingest_secret
from core.config import get_settings
from core.version import get_app_version
from core import db as db_module
from core import drive as drive_module
from core.drive import DriveDownloadError, DriveNotConfiguredError
from core.extract import extract_contract
from core.gemini_client import GeminiExtractionError, gemini_not_configured_message
from ingest.schemas import IngestRequest, IngestResponse, SyncSheetResponse

router = APIRouter()


@router.get("/health")
def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "version": get_app_version(),
        "database_configured": settings.database_configured,
        "drive_configured": settings.drive_configured,
        "drive_auth": settings.drive_auth_mode,
        "drive_sa_fallback": settings.drive_sa_fallback_available,
        "gemini_enabled": settings.gemini_enabled,
        "gemini_configured": settings.gemini_configured,
        "gemini_backend": settings.gemini_backend,
        "bot_platforms": sorted(settings.bot_platforms_enabled),
        "bot_slack_configured": settings.bot_slack_configured,
        "bot_telegram_configured": settings.bot_telegram_configured,
    }


@router.post("/ingest", response_model=IngestResponse, dependencies=[Depends(verify_ingest_secret)])
def ingest(ingest_request: IngestRequest) -> IngestResponse:
    settings = get_settings()
    if ingest_request.mime_type != "application/pdf":
        return IngestResponse(
            status="skipped",
            drive_file_id=ingest_request.drive_file_id,
            mode="stub",
            message=f"Unsupported mime type: {ingest_request.mime_type}",
        )

    mode = "database" if settings.database_configured else "stub"
    message: Optional[str] = None

    if settings.drive_configured:
        try:
            pdf_bytes = drive_module.download_pdf(ingest_request.drive_file_id)
        except DriveNotConfiguredError:
            pdf_bytes = b""
            message = "Drive credentials not configured."
        except DriveDownloadError as exc:
            return IngestResponse(
                status="error",
                drive_file_id=ingest_request.drive_file_id,
                mode=mode,
                message=f"Drive download failed ({exc.status_code}): {exc.message}",
            )
    else:
        pdf_bytes = b""
        if settings.gemini_enabled:
            return IngestResponse(
                status="error",
                drive_file_id=ingest_request.drive_file_id,
                mode=mode,
                message=(
                    "Drive download required for Gemini extraction "
                    "(set GOOGLE_APPLICATION_CREDENTIALS for file auth, or DRIVE_AUTH=adc with gcloud ADC)."
                ),
            )
        message = "Drive not configured; stub extraction only (empty PDF bytes)."

    if settings.gemini_enabled and not settings.gemini_configured:
        return IngestResponse(
            status="error",
            drive_file_id=ingest_request.drive_file_id,
            mode=mode,
            message=gemini_not_configured_message(settings),
        )

    try:
        fields = extract_contract(
            pdf_bytes,
            ingest_request.file_name,
            gemini_enabled=settings.gemini_enabled,
        )
    except GeminiExtractionError as exc:
        return IngestResponse(
            status="error",
            drive_file_id=ingest_request.drive_file_id,
            mode=mode,
            message=f"Extraction failed: {exc}",
        )

    if settings.database_configured:
        try:
            db_module.upsert_contract(
                ingest_request.drive_file_id,
                ingest_request.file_name,
                ingest_request.mime_type,
                fields,
            )
        except Exception as exc:  # noqa: BLE001 — surface as 503 until ops hardens handlers
            return IngestResponse(
                status="error",
                drive_file_id=ingest_request.drive_file_id,
                mode="database",
                counterparty=fields.counterparty,
                message=str(exc),
            )
    else:
        message = "DATABASE_URL not set; returned stub extraction only."

    return IngestResponse(
        status="ok",
        drive_file_id=ingest_request.drive_file_id,
        mode=mode,
        counterparty=fields.counterparty,
        message=message,
    )


@router.post("/sync/sheet", response_model=SyncSheetResponse, dependencies=[Depends(verify_ingest_secret)])
def sync_sheet() -> SyncSheetResponse:
    settings = get_settings()
    if not settings.database_configured:
        return SyncSheetResponse(
            status="ok",
            mode="stub",
            synced=0,
            message="DATABASE_URL not set; sheet sync not implemented in stub mode.",
        )

    # TODO: Google Sheets API when SHEET_ID + service account are available (Phase 0).
    return SyncSheetResponse(
        status="ok",
        mode="stub",
        synced=0,
        message="Sheet sync placeholder — wire Sheets API after Phase 0.",
    )
