from typing import Optional

from fastapi import Header, HTTPException, status

from core.config import get_settings


def verify_ingest_secret(
    x_ingest_secret: Optional[str] = Header(default=None, alias="X-Ingest-Secret"),
) -> None:
    settings = get_settings()
    if not x_ingest_secret or x_ingest_secret != settings.ingest_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-Ingest-Secret",
        )
