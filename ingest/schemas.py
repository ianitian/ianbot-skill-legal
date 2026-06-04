from typing import Optional

from pydantic import BaseModel, Field


class IngestRequest(BaseModel):
    drive_file_id: str = Field(..., min_length=1)
    file_name: str = "unknown.pdf"
    mime_type: str = "application/pdf"
    source: str = "apps-script"
    triggered_at: Optional[str] = None


class IngestResponse(BaseModel):
    status: str
    drive_file_id: str
    mode: str
    counterparty: Optional[str] = None
    message: Optional[str] = None


class SyncSheetResponse(BaseModel):
    status: str
    mode: str
    synced: int = 0
    message: Optional[str] = None
