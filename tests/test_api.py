import os

from fastapi.testclient import TestClient

# Use a fixed secret for tests before app imports settings cache.
os.environ.setdefault("INGEST_SECRET", "test-secret")

from ingest.api import app  # noqa: E402

client = TestClient(app)
HEADERS = {"X-Ingest-Secret": "test-secret"}


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_ingest_requires_secret():
    response = client.post("/ingest", json={"drive_file_id": "abc123"})
    assert response.status_code == 401


def test_ingest_stub():
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


def test_sync_sheet_stub():
    response = client.post("/sync/sheet", headers=HEADERS)
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
