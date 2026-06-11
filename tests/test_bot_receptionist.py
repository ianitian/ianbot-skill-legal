import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("INGEST_SECRET", "test-secret")

from bot.handlers.dispatch import dispatch_message  # noqa: E402
from bot.schemas import BotEvent  # noqa: E402
from core.bot_faq import clear_faq_catalog_cache, load_faq_catalog  # noqa: E402
from core.config import Settings, get_settings  # noqa: E402
from ingest.api import app  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_FAQ_PATH = _REPO_ROOT / "bot" / "content" / "faqs.yaml"


def _clear_caches() -> None:
    get_settings.cache_clear()
    clear_faq_catalog_cache()


def _settings(**overrides: object) -> Settings:
    return Settings(
        ingest_secret="test-secret",
        bot_faq_enabled=overrides.pop("bot_faq_enabled", True),
        bot_faq_path=overrides.pop("bot_faq_path", str(_DEFAULT_FAQ_PATH)),
        bot_faq_min_score=overrides.pop("bot_faq_min_score", 80),
        bot_receptionist_enabled=overrides.pop("bot_receptionist_enabled", False),
        **overrides,
    )


def _event(text: str) -> BotEvent:
    return BotEvent(
        platform="telegram",
        event_type="message",
        event_id="1",
        text=text,
        user_name="Ada",
    )


def test_match_top_candidates_returns_ranked_results():
    _clear_caches()
    catalog = load_faq_catalog(str(_DEFAULT_FAQ_PATH))
    results = catalog.match_top_candidates("what can you do", limit=3)
    assert len(results) >= 1
    assert results[0].faq_id == "capabilities"
    assert results[0].score >= 80
    if len(results) > 1:
        assert results[0].score >= results[1].score


def test_dispatch_legacy_faq_when_receptionist_disabled():
    _clear_caches()
    settings = _settings(bot_receptionist_enabled=False)
    reply = dispatch_message(settings, _event("what can you do"))
    assert reply is not None
    assert reply.handler == "faq"


def test_dispatch_fallback_when_receptionist_disabled():
    _clear_caches()
    settings = _settings(bot_receptionist_enabled=False)
    reply = dispatch_message(settings, _event("xyzzy plugh"))
    assert reply is not None
    assert reply.handler == "fallback"


def test_dispatch_receptionist_stub_when_enabled():
    _clear_caches()
    settings = _settings(bot_receptionist_enabled=True)
    reply = dispatch_message(settings, _event("what can you do"))
    assert reply is not None
    assert reply.handler == "receptionist"
    assert reply.handler_metadata.get("phase") == "scaffold"
    assert reply.handler_metadata.get("candidate_count", 0) >= 1


def test_health_includes_receptionist_fields(monkeypatch: pytest.MonkeyPatch):
    _clear_caches()
    monkeypatch.setenv("BOT_RECEPTIONIST_ENABLED", "false")
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["bot_receptionist_enabled"] is False
    assert payload["bot_receptionist_configured"] is False
