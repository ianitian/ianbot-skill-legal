import os
from unittest.mock import patch

import pytest

os.environ.setdefault("INGEST_SECRET", "test-secret")

from bot.debug import emit_debug, format_debug_message  # noqa: E402
from bot.delivery import deliver_bot_reply  # noqa: E402
from bot.handlers.dispatch import dispatch_message  # noqa: E402
from bot.schemas import BotEvent, BotReply  # noqa: E402
from core.bot_faq import clear_faq_catalog_cache  # noqa: E402
from core.config import Settings, get_settings  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from ingest.api import app  # noqa: E402


def _clear_caches() -> None:
    os.environ["DATABASE_URL"] = ""
    get_settings.cache_clear()
    clear_faq_catalog_cache()


def _settings(**overrides: object) -> Settings:
    return Settings(
        ingest_secret="test-secret",
        bot_platforms="slack,telegram",
        slack_signing_secret="test-signing-secret",
        slack_bot_token="xoxb-test",
        telegram_bot_token="123:ABC",
        bot_faq_enabled=overrides.pop("bot_faq_enabled", True),
        bot_faq_path=overrides.pop("bot_faq_path", "bot/content/faqs.yaml"),
        bot_faq_min_score=overrides.pop("bot_faq_min_score", 80),
        bot_debug_enabled=overrides.pop("bot_debug_enabled", True),
        **overrides,
    )


def _event(**overrides: object) -> BotEvent:
    defaults = {
        "platform": "telegram",
        "event_type": "message",
        "event_id": "evt-1",
        "chat_id": "-10099",
        "text": "what can you do",
    }
    defaults.update(overrides)
    return BotEvent(**defaults)


def test_format_debug_message_includes_fuzzy_top_on_miss():
    settings = _settings(bot_faq_min_score=99)
    reply = dispatch_message(settings, _event(text="xyzzy unknown question"))
    assert reply is not None
    assert reply.handler == "fallback"

    text = format_debug_message(settings, _event(text="xyzzy unknown question"), reply)
    assert "handler: fallback" in text
    assert "fuzzy: miss" in text
    assert "threshold 99" in text
    assert "top candidates:" in text


def test_format_debug_message_includes_faq_hit():
    settings = _settings()
    reply = dispatch_message(settings, _event(text="what can you do"))
    assert reply is not None
    assert reply.handler == "faq"

    text = format_debug_message(settings, _event(text="what can you do"), reply)
    assert "handler: faq" in text
    assert "fuzzy: matched" in text
    assert "faq_id: capabilities" in text


def test_emit_debug_telegram_only(monkeypatch: pytest.MonkeyPatch):
    settings = _settings(telegram_debug_chat_id="12345", slack_debug_channel_id="")
    event = _event(platform="telegram")

    with patch("bot.debug.send_telegram_text") as mock_tg, patch(
        "bot.debug.post_slack_message"
    ) as mock_slack:
        emit_debug(settings, event, "debug body")
        mock_tg.assert_called_once_with(settings, "12345", "debug body")
        mock_slack.assert_not_called()


def test_emit_debug_slack_channel_when_configured():
    settings = _settings(slack_debug_channel_id="C_DEBUG")
    event = _event(platform="slack", chat_id="C1", thread_id="123.456")

    with patch("bot.debug.send_telegram_text") as mock_tg, patch(
        "bot.debug.post_slack_message"
    ) as mock_slack:
        emit_debug(settings, event, "debug body")
        mock_tg.assert_not_called()
        mock_slack.assert_called_once_with(settings, "C_DEBUG", "debug body")


def test_emit_debug_slack_thread_when_channel_empty():
    settings = _settings(slack_debug_channel_id="")
    event = _event(platform="slack", chat_id="C1", thread_id="123.456")

    with patch("bot.debug.post_slack_message") as mock_slack:
        emit_debug(settings, event, "debug body")
        mock_slack.assert_called_once_with(
            settings, "C1", "debug body", thread_ts="123.456"
        )


def test_deliver_bot_reply_skips_debug_when_disabled():
    settings = _settings(bot_debug_enabled=False)
    event = _event()
    reply = BotReply(text="hello", handler="echo")

    with patch("bot.delivery.send_telegram_reply") as mock_reply, patch(
        "bot.delivery.emit_debug"
    ) as mock_debug:
        deliver_bot_reply(settings, event, reply)
        mock_reply.assert_called_once_with(settings, event, reply)
        mock_debug.assert_not_called()


def test_deliver_bot_reply_emits_debug_when_enabled():
    settings = _settings(bot_debug_enabled=True, telegram_debug_chat_id="99")
    event = _event()
    reply = BotReply(text="hello", handler="echo")

    with patch("bot.delivery.send_telegram_reply"), patch(
        "bot.delivery.emit_debug"
    ) as mock_debug:
        deliver_bot_reply(settings, event, reply)
        mock_debug.assert_called_once()
        debug_text = mock_debug.call_args[0][2]
        assert "[won-bot debug]" in debug_text


def test_health_reports_debug_fields(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("BOT_DEBUG_ENABLED", "true")
    monkeypatch.setenv("TELEGRAM_DEBUG_CHAT_ID", "123")
    monkeypatch.setenv("SLACK_DEBUG_CHANNEL_ID", "C99")
    monkeypatch.setenv("SLACK_SIGNING_SECRET", "x")
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb")
    _clear_caches()

    response = TestClient(app).get("/health")
    payload = response.json()
    assert payload["bot_debug_enabled"] is True
    assert payload["bot_debug_telegram_configured"] is True
    assert payload["bot_debug_slack_channel_configured"] is True
    assert payload["bot_debug_slack_thread_available"] is False
    _clear_caches()
