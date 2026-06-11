import os
from pathlib import Path

import pytest

os.environ.setdefault("INGEST_SECRET", "test-secret")

from bot.handlers.dispatch import dispatch_message, handle_fallback  # noqa: E402
from bot.handlers.faq import FAQ_DISCLAIMER, handle_faq  # noqa: E402
from bot.schemas import BotEvent  # noqa: E402
from core.bot_faq import clear_faq_catalog_cache, load_faq_catalog  # noqa: E402
from core.config import Settings, get_settings  # noqa: E402

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


def test_faq_catalog_loads_seed_entries():
    _clear_caches()
    catalog = load_faq_catalog(str(_DEFAULT_FAQ_PATH))
    assert catalog.count == 6


def test_faq_match_capabilities():
    _clear_caches()
    catalog = load_faq_catalog(str(_DEFAULT_FAQ_PATH))
    match = catalog.match("what can you do", min_score=70)
    assert match is not None
    assert match.faq_id == "capabilities"
    assert match.score >= 70


def test_faq_match_below_threshold_returns_none():
    _clear_caches()
    catalog = load_faq_catalog(str(_DEFAULT_FAQ_PATH))
    assert catalog.match("completely unrelated gibberish xyz", min_score=80) is None


def test_handle_faq_disabled_returns_none():
    _clear_caches()
    settings = _settings(bot_faq_enabled=False)
    assert handle_faq(settings, _event("what can you do")) is None


def test_handle_faq_adds_disclaimer_and_metadata():
    _clear_caches()
    settings = _settings()
    reply = handle_faq(settings, _event("what can you do"))
    assert reply is not None
    assert reply.text.startswith(FAQ_DISCLAIMER)
    assert reply.handler == "faq"
    assert reply.handler_metadata["faq_id"] == "capabilities"
    assert reply.handler_metadata["score"] >= 80


def test_dispatch_echo_wins_over_faq():
    _clear_caches()
    settings = _settings()
    reply = dispatch_message(settings, _event("ping"))
    assert reply is not None
    assert reply.text == "pong"
    assert reply.handler == "echo"


def test_dispatch_faq_when_enabled():
    _clear_caches()
    settings = _settings()
    reply = dispatch_message(settings, _event("what can you do"))
    assert reply is not None
    assert reply.handler == "faq"
    assert FAQ_DISCLAIMER in reply.text


def test_dispatch_fallback_when_faq_disabled():
    _clear_caches()
    settings = _settings(bot_faq_enabled=False)
    reply = dispatch_message(settings, _event("what can you do"))
    assert reply is not None
    assert reply.handler == "fallback"
    assert "wonbot-api v" in reply.text
    assert "Indexed DB based Q&A: not enabled" in reply.text


def test_dispatch_fallback_for_unknown_question():
    _clear_caches()
    settings = _settings()
    reply = dispatch_message(settings, _event("xyzzy plugh"))
    assert reply is not None
    assert reply.handler == "fallback"
    assert reply.text == handle_fallback(_event("xyzzy")).text


def test_health_reports_faq_fields(monkeypatch: pytest.MonkeyPatch):
    from fastapi.testclient import TestClient

    from ingest.api import app

    _clear_caches()
    monkeypatch.setenv("BOT_FAQ_ENABLED", "true")
    monkeypatch.setenv("BOT_FAQ_PATH", str(_DEFAULT_FAQ_PATH))
    get_settings.cache_clear()

    response = TestClient(app).get("/health")
    payload = response.json()
    assert payload["bot_faq_enabled"] is True
    assert payload["bot_faq_configured"] is True
    assert payload["bot_faq_count"] == 6

    _clear_caches()
