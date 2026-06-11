from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import field_validator
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
    drive_debug_sa_fallback: bool = False
    google_cloud_project: Optional[str] = None

    @field_validator("drive_debug_sa_fallback", mode="before")
    @classmethod
    def _parse_drive_debug_sa_fallback(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower() in {"yes", "true", "1"}
        return value
    google_cloud_location: Optional[str] = None
    bot_platforms: str = ""
    slack_signing_secret: Optional[str] = None
    slack_bot_token: Optional[str] = None
    telegram_bot_token: Optional[str] = None
    telegram_webhook_secret: Optional[str] = None
    telegram_allowed_chat_ids: str = ""
    telegram_bot_username: Optional[str] = None
    bot_faq_enabled: bool = False
    bot_faq_path: str = "bot/content/faqs.yaml"
    bot_faq_min_score: int = 80
    bot_receptionist_enabled: bool = False
    bot_receptionist_fast_faq_score: int = 95
    bot_receptionist_gray_low: int = 40
    bot_receptionist_candidate_limit: int = 3
    bot_telegram_use_polling: bool = False

    @field_validator("bot_receptionist_enabled", mode="before")
    @classmethod
    def _parse_bot_receptionist_enabled(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower() in {"yes", "true", "1"}
        return value

    @field_validator("bot_receptionist_fast_faq_score", mode="before")
    @classmethod
    def _parse_bot_receptionist_fast_faq_score(cls, value: object) -> object:
        if isinstance(value, str) and value.strip():
            return int(value.strip())
        return value

    @field_validator("bot_receptionist_gray_low", mode="before")
    @classmethod
    def _parse_bot_receptionist_gray_low(cls, value: object) -> object:
        if isinstance(value, str) and value.strip():
            return int(value.strip())
        return value

    @field_validator("bot_receptionist_candidate_limit", mode="before")
    @classmethod
    def _parse_bot_receptionist_candidate_limit(cls, value: object) -> object:
        if isinstance(value, str) and value.strip():
            return int(value.strip())
        return value

    @field_validator("bot_telegram_use_polling", mode="before")
    @classmethod
    def _parse_bot_telegram_use_polling(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower() in {"yes", "true", "1"}
        return value

    @field_validator("bot_faq_enabled", mode="before")
    @classmethod
    def _parse_bot_faq_enabled(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower() in {"yes", "true", "1"}
        return value

    @field_validator("bot_faq_min_score", mode="before")
    @classmethod
    def _parse_bot_faq_min_score(cls, value: object) -> object:
        if isinstance(value, str) and value.strip():
            return int(value.strip())
        return value

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
    def drive_sa_fallback_available(self) -> bool:
        return self.drive_debug_sa_fallback and self._credentials_file_exists

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

    @property
    def bot_platforms_enabled(self) -> frozenset[str]:
        raw = (self.bot_platforms or "").strip()
        if not raw:
            return frozenset()
        return frozenset(p.strip().lower() for p in raw.split(",") if p.strip())

    @property
    def bot_slack_configured(self) -> bool:
        return bool(
            self.slack_signing_secret
            and self.slack_signing_secret.strip()
            and self.slack_bot_token
            and self.slack_bot_token.strip()
        )

    @property
    def bot_telegram_configured(self) -> bool:
        return bool(
            self.telegram_bot_token
            and self.telegram_bot_token.strip()
            and self.telegram_webhook_secret
            and self.telegram_webhook_secret.strip()
        )

    @property
    def telegram_allowed_chat_ids_set(self) -> frozenset[str]:
        raw = (self.telegram_allowed_chat_ids or "").strip()
        if not raw:
            return frozenset()
        return frozenset(part.strip() for part in raw.split(",") if part.strip())

    @property
    def telegram_group_gating_configured(self) -> bool:
        username = (self.telegram_bot_username or "").strip().lstrip("@")
        return bool(self.telegram_allowed_chat_ids_set and username)

    @property
    def bot_faq_count(self) -> int:
        if not self.bot_faq_enabled:
            return 0
        from core.bot_faq import load_faq_catalog

        return load_faq_catalog(self.bot_faq_path).count

    @property
    def bot_faq_configured(self) -> bool:
        return self.bot_faq_enabled and self.bot_faq_count > 0

    @property
    def bot_receptionist_configured(self) -> bool:
        return self.bot_receptionist_enabled and self.gemini_configured


@lru_cache
def get_settings() -> Settings:
    return Settings()
