from typing import Optional

from fastapi import APIRouter, Depends

from core.auth import verify_ingest_secret
from core.config import Settings, get_settings
from core.version import get_app_version
from core import db as db_module
from core.extract import extract_contract
from ingest.schemas import IngestRequest, IngestResponse, SyncSheetResponse

router = APIRouter()


@router.get("/health")
def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "version": get_app_version(),
        "database_configured": settings.database_configured,
        "gemini_enabled": settings.gemini_enabled,
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

    # PDF bytes from Drive — TODO when service account is available (Phase 0).
    pdf_bytes = b""
    fields = extract_contract(
        pdf_bytes,
        ingest_request.file_name,
        gemini_enabled=settings.gemini_enabled,
    )

    mode = "database" if settings.database_configured else "stub"
    message: Optional[str] = None

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
