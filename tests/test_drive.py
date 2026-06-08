import json
from unittest.mock import MagicMock, patch

import google.auth.exceptions
import pytest

from core.config import get_settings
from core.drive import (
    DriveNotConfiguredError,
    _load_drive_credentials,
    _resolve_drive_auth_mode,
    clear_drive_service_cache,
)


def _clear_caches() -> None:
    get_settings.cache_clear()
    clear_drive_service_cache()


def test_resolve_drive_auth_mode_auto_prefers_file_when_path_exists(monkeypatch, tmp_path):
    creds_file = tmp_path / "sa.json"
    creds_file.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("DRIVE_AUTH", "auto")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(creds_file))
    _clear_caches()

    assert _resolve_drive_auth_mode(get_settings()) == "file"
    _clear_caches()


def test_resolve_drive_auth_mode_auto_falls_back_to_adc(monkeypatch):
    monkeypatch.setenv("DRIVE_AUTH", "auto")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "")
    _clear_caches()

    assert _resolve_drive_auth_mode(get_settings()) == "adc"
    _clear_caches()


def test_drive_configured_adc_mode(monkeypatch):
    monkeypatch.setenv("DRIVE_AUTH", "adc")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "")
    _clear_caches()

    settings = get_settings()
    assert settings.drive_configured is True
    assert settings.drive_auth_mode == "adc"
    _clear_caches()


def test_drive_configured_file_mode_requires_existing_file(monkeypatch):
    monkeypatch.setenv("DRIVE_AUTH", "file")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/does/not/exist.json")
    _clear_caches()

    settings = get_settings()
    assert settings.drive_configured is False
    _clear_caches()


def test_load_drive_credentials_from_file(monkeypatch, tmp_path):
    creds_file = tmp_path / "sa.json"
    creds_file.write_text(
        json.dumps({"type": "service_account", "project_id": "test"}),
        encoding="utf-8",
    )
    monkeypatch.setenv("DRIVE_AUTH", "file")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(creds_file))
    _clear_caches()

    mock_creds = MagicMock()
    with patch("core.drive.google.auth.load_credentials_from_file", return_value=(mock_creds, "test")):
        creds, mode = _load_drive_credentials(get_settings())

    assert creds is mock_creds
    assert mode == "file"
    _clear_caches()


def test_load_drive_credentials_adc(monkeypatch):
    monkeypatch.setenv("DRIVE_AUTH", "adc")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "")
    _clear_caches()

    mock_creds = MagicMock()
    mock_creds.with_scopes_if_required.return_value = mock_creds
    with patch("core.drive.google.auth.default", return_value=(mock_creds, "test")):
        creds, mode = _load_drive_credentials(get_settings())

    assert creds is mock_creds
    assert mode == "adc"
    mock_creds.with_scopes_if_required.assert_called_once()
    _clear_caches()


def test_load_drive_credentials_adc_missing(monkeypatch):
    monkeypatch.setenv("DRIVE_AUTH", "adc")
    _clear_caches()

    with patch(
        "core.drive.google.auth.default",
        side_effect=google.auth.exceptions.DefaultCredentialsError("no adc"),
    ):
        with pytest.raises(DriveNotConfiguredError, match="ADC not available"):
            _load_drive_credentials(get_settings())

    _clear_caches()
