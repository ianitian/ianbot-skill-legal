import os
from unittest.mock import patch

from fastapi.testclient import TestClient

# Use a fixed secret for tests before app imports settings cache.
os.environ.setdefault("INGEST_SECRET", "test-secret")

from core.config import get_settings  # noqa: E402
from core.drive import DriveDownloadError  # noqa: E402
from ingest.api import app  # noqa: E402

client = TestClient(app)
HEADERS = {"X-Ingest-Secret": "test-secret"}


def _clear_settings_cache() -> None:
    get_settings.cache_clear()


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert isinstance(data["drive_configured"], bool)


def test_ingest_requires_secret():
    response = client.post("/ingest", json={"drive_file_id": "abc123"})
    assert response.status_code == 401


def test_ingest_stub(monkeypatch):
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "")
    _clear_settings_cache()

    response = client.post(
        "/ingest",
        headers=HEADERS,
        json={
            "drive_file_id": "file-id-1",
            "file_name": "ACME_Corp_MSA.pdf",
            "mime_type": "application/pdf",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["drive_file_id"] == "file-id-1"
    assert data["mode"] in ("stub", "database")
    _clear_settings_cache()


def test_ingest_downloads_pdf_when_configured(monkeypatch, tmp_path):
    creds_file = tmp_path / "sa.json"
    creds_file.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(creds_file))
    _clear_settings_cache()

    pdf_bytes = b"%PDF-1.4\n"
    with patch("core.drive.download_pdf", return_value=pdf_bytes):
        response = client.post(
            "/ingest",
            headers=HEADERS,
            json={
                "drive_file_id": "file-id-2",
                "file_name": "ACME_Corp_MSA.pdf",
                "mime_type": "application/pdf",
            },
        )

    _clear_settings_cache()
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["drive_file_id"] == "file-id-2"


def test_ingest_drive_404(monkeypatch, tmp_path):
    creds_file = tmp_path / "sa.json"
    creds_file.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(creds_file))
    _clear_settings_cache()

    with patch(
        "core.drive.download_pdf",
        side_effect=DriveDownloadError(404, "Drive API error for file missing"),
    ):
        response = client.post(
            "/ingest",
            headers=HEADERS,
            json={
                "drive_file_id": "missing-id",
                "file_name": "ACME_Corp_MSA.pdf",
                "mime_type": "application/pdf",
            },
        )

    _clear_settings_cache()
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "error"
    assert "404" in (data.get("message") or "")


def test_sync_sheet_stub():
    response = client.post("/sync/sheet", headers=HEADERS)
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
