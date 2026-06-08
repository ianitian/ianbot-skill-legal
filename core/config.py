from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    ingest_secret: str = "change-me-local-only"
    database_url: Optional[str] = None
    gemini_enabled: bool = False
    gemini_api_key: Optional[str] = None
    gemini_backend: str = "studio"
    gemini_model: str = "gemini-2.0-flash"
    google_application_credentials: Optional[str] = None
    drive_auth: str = "auto"
    google_cloud_project: Optional[str] = None
    google_cloud_location: Optional[str] = None

    @property
    def database_configured(self) -> bool:
        return bool(self.database_url and self.database_url.strip())

    @property
    def drive_auth_mode(self) -> str:
        mode = (self.drive_auth or "auto").strip().lower()
        if mode == "adc":
            return "adc"
        if mode == "file":
            return "file"
        return "file" if self._credentials_file_exists else "adc"

    @property
    def _credentials_file_exists(self) -> bool:
        path = self.google_application_credentials
        return bool(path and path.strip() and Path(path).is_file())

    @property
    def drive_configured(self) -> bool:
        mode = (self.drive_auth or "auto").strip().lower()
        if mode == "adc":
            return True
        if mode == "file":
            return self._credentials_file_exists
        return self._credentials_file_exists or True

    @property
    def gemini_configured(self) -> bool:
        backend = (self.gemini_backend or "studio").strip().lower()
        if backend == "studio":
            return bool(self.gemini_api_key and self.gemini_api_key.strip())
        if backend == "vertex":
            return bool(
                self.google_cloud_project
                and self.google_cloud_project.strip()
                and self.google_cloud_location
                and self.google_cloud_location.strip()
            )
        return False


@lru_cache
def get_settings() -> Settings:
    return Settings()
