import hashlib
import hmac
import json
import os
import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("INGEST_SECRET", "test-secret")

from bot.idempotency import clear_memory_seen  # noqa: E402
from core.config import get_settings  # noqa: E402
from ingest.api import app  # noqa: E402

client = TestClient(app)

_TEST_SLACK_SIGNING_SECRET = "test-signing-secret"
_TEST_TELEGRAM_WEBHOOK_SECRET = "test-webhook-secret"
_TEST_TG_CHAT_ID = "-10099"
_TEST_TG_BOT_USERNAME = "testbot"


def _clear_caches() -> None:
    os.environ["INGEST_SECRET"] = "test-secret"
    get_settings.cache_clear()
    clear_memory_seen()


def _slack_signature(body: bytes, secret: str = _TEST_SLACK_SIGNING_SECRET) -> tuple[str, str]:
    timestamp = str(int(time.time()))
    basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
    digest = hmac.new(
        secret.encode("utf-8"),
        basestring.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return timestamp, f"v0={digest}"


def _slack_headers(body: bytes, secret: str = _TEST_SLACK_SIGNING_SECRET) -> dict[str, str]:
    timestamp, signature = _slack_signature(body, secret)
    return {
        "X-Slack-Request-Timestamp": timestamp,
        "X-Slack-Signature": signature,
        "Content-Type": "application/json",
    }


def _enable_slack(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_PLATFORMS", "slack,telegram")
    monkeypatch.setenv("SLACK_SIGNING_SECRET", _TEST_SLACK_SIGNING_SECRET)
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test-token")
    _clear_caches()


def _enable_telegram(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_PLATFORMS", "slack,telegram")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:ABC")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", _TEST_TELEGRAM_WEBHOOK_SECRET)
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_IDS", _TEST_TG_CHAT_ID)
    monkeypatch.setenv("TELEGRAM_BOT_USERNAME", _TEST_TG_BOT_USERNAME)
    _clear_caches()


def _telegram_group_payload(
    command_text: str,
    update_id: int = 42,
    chat_id: str = _TEST_TG_CHAT_ID,
    chat_type: str = "supergroup",
    first_name: str = "Ada",
    last_name: str = "Lovelace",
) -> dict:
    mention = f"@{_TEST_TG_BOT_USERNAME}"
    text = f"{mention} {command_text}".strip()
    entities = [{"offset": 0, "length": len(mention), "type": "mention"}]
    return {
        "update_id": update_id,
        "message": {
            "text": text,
            "entities": entities,
            "chat": {"id": int(chat_id), "type": chat_type},
            "from": {"id": 7, "first_name": first_name, "last_name": last_name},
        },
    }


def test_health_includes_bot_fields():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "bot_platforms" in data
    assert "bot_slack_configured" in data
    assert "bot_telegram_configured" in data
    assert "telegram_group_gating_configured" in data
    assert isinstance(data["bot_platforms"], list)


def test_slack_url_verification(monkeypatch):
    _enable_slack(monkeypatch)
    body = json.dumps({"type": "url_verification", "challenge": "challenge-token"}).encode()
    response = client.post("/webhooks/slack/events", content=body, headers=_slack_headers(body))
    assert response.status_code == 200
    assert response.json() == {"challenge": "challenge-token"}
    _clear_caches()


def test_slack_bad_signature(monkeypatch):
    _enable_slack(monkeypatch)
    body = json.dumps({"type": "url_verification", "challenge": "x"}).encode()
    headers = _slack_headers(body, secret="wrong-secret")
    response = client.post("/webhooks/slack/events", content=body, headers=headers)
    assert response.status_code == 401
    _clear_caches()


def test_slack_message_echo(monkeypatch):
    _enable_slack(monkeypatch)
    payload = {
        "type": "event_callback",
        "event_id": "Ev001",
        "event": {
            "type": "message",
            "user": "U1",
            "channel": "C1",
            "text": "hello",
            "ts": "123.456",
        },
    }
    body = json.dumps(payload).encode()
    with patch("bot.router.send_slack_reply") as mock_send:
        response = client.post(
            "/webhooks/slack/events", content=body, headers=_slack_headers(body)
        )
        assert response.status_code == 200
        mock_send.assert_called_once()
        reply = mock_send.call_args[0][2]
        assert reply.text == "Hello, friend"
    _clear_caches()


def test_slack_ping_returns_pong(monkeypatch):
    _enable_slack(monkeypatch)
    payload = {
        "type": "event_callback",
        "event_id": "Ev002",
        "event": {
            "type": "message",
            "user": "U1",
            "channel": "C1",
            "text": "/ping",
            "ts": "123.457",
        },
    }
    body = json.dumps(payload).encode()
    with patch("bot.router.send_slack_reply") as mock_send:
        response = client.post(
            "/webhooks/slack/events", content=body, headers=_slack_headers(body)
        )
        assert response.status_code == 200
        reply = mock_send.call_args[0][2]
        assert reply.text == "pong"
    _clear_caches()


def test_slack_duplicate_event_id_skips_outbound(monkeypatch):
    _enable_slack(monkeypatch)
    payload = {
        "type": "event_callback",
        "event_id": "Ev-dup",
        "event": {
            "type": "message",
            "user": "U1",
            "channel": "C1",
            "text": "hello",
            "ts": "123.458",
        },
    }
    body = json.dumps(payload).encode()
    headers = _slack_headers(body)
    with patch("bot.router.send_slack_reply") as mock_send:
        client.post("/webhooks/slack/events", content=body, headers=headers)
        client.post("/webhooks/slack/events", content=body, headers=headers)
        assert mock_send.call_count == 1
    _clear_caches()


def test_slack_interactions_stub(monkeypatch):
    _enable_slack(monkeypatch)
    body = b"payload=%7B%7D"
    timestamp, signature = _slack_signature(body)
    headers = {
        "X-Slack-Request-Timestamp": timestamp,
        "X-Slack-Signature": signature,
        "Content-Type": "application/x-www-form-urlencoded",
    }
    response = client.post("/webhooks/slack/interactions", content=body, headers=headers)
    assert response.status_code == 200
    assert response.content == b""
    _clear_caches()


def test_slack_platform_disabled_returns_404(monkeypatch):
    monkeypatch.setenv("BOT_PLATFORMS", "telegram")
    monkeypatch.setenv("SLACK_SIGNING_SECRET", _TEST_SLACK_SIGNING_SECRET)
    _clear_caches()
    body = json.dumps({"type": "url_verification", "challenge": "x"}).encode()
    response = client.post("/webhooks/slack/events", content=body, headers=_slack_headers(body))
    assert response.status_code == 404
    _clear_caches()


def test_telegram_wrong_secret_returns_404(monkeypatch):
    _enable_telegram(monkeypatch)
    body = json.dumps(_telegram_group_payload("hi")).encode()
    response = client.post("/webhooks/telegram/wrong-secret", content=body)
    assert response.status_code == 404
    _clear_caches()


def test_telegram_echo_with_mention(monkeypatch):
    _enable_telegram(monkeypatch)
    body = json.dumps(_telegram_group_payload("hello")).encode()
    with patch("bot.router.send_telegram_reply") as mock_send:
        response = client.post(
            f"/webhooks/telegram/{_TEST_TELEGRAM_WEBHOOK_SECRET}", content=body
        )
        assert response.status_code == 200
        mock_send.assert_called_once()
        reply = mock_send.call_args[0][2]
        assert reply.text == "Hello, Ada Lovelace"
    _clear_caches()


def test_telegram_unknown_command_returns_toddler_message(monkeypatch):
    _enable_telegram(monkeypatch)
    body = json.dumps(_telegram_group_payload("what is a contract?", update_id=44)).encode()
    with patch("bot.router.send_telegram_reply") as mock_send:
        client.post(f"/webhooks/telegram/{_TEST_TELEGRAM_WEBHOOK_SECRET}", content=body)
        reply = mock_send.call_args[0][2]
        assert "toddler" in reply.text
        assert "ping and hello" in reply.text
    _clear_caches()


def test_telegram_ping_returns_pong(monkeypatch):
    _enable_telegram(monkeypatch)
    body = json.dumps(_telegram_group_payload("ping", update_id=43)).encode()
    with patch("bot.router.send_telegram_reply") as mock_send:
        client.post(f"/webhooks/telegram/{_TEST_TELEGRAM_WEBHOOK_SECRET}", content=body)
        reply = mock_send.call_args[0][2]
        assert reply.text == "pong"
    _clear_caches()


def test_telegram_private_chat_redirects_to_group(monkeypatch):
    _enable_telegram(monkeypatch)
    payload = _telegram_group_payload("hello", update_id=45)
    payload["message"]["chat"] = {"id": 12345, "type": "private"}
    body = json.dumps(payload).encode()
    with patch("bot.router.send_telegram_reply") as mock_send:
        client.post(f"/webhooks/telegram/{_TEST_TELEGRAM_WEBHOOK_SECRET}", content=body)
        mock_send.assert_called_once()
        reply = mock_send.call_args[0][2]
        assert reply.text == "Private DM to won-bot is disabled; please use in a group chat"
    _clear_caches()


def test_telegram_non_allowlisted_group_ignored(monkeypatch):
    _enable_telegram(monkeypatch)
    body = json.dumps(_telegram_group_payload("hello", update_id=46, chat_id="-100000")).encode()
    with patch("bot.router.send_telegram_reply") as mock_send:
        client.post(f"/webhooks/telegram/{_TEST_TELEGRAM_WEBHOOK_SECRET}", content=body)
        mock_send.assert_not_called()
    _clear_caches()


def test_telegram_group_without_mention_ignored(monkeypatch):
    _enable_telegram(monkeypatch)
    body = json.dumps(
        {
            "update_id": 47,
            "message": {
                "text": "hello",
                "chat": {"id": int(_TEST_TG_CHAT_ID), "type": "supergroup"},
                "from": {"id": 7, "first_name": "Ada"},
            },
        }
    ).encode()
    with patch("bot.router.send_telegram_reply") as mock_send:
        client.post(f"/webhooks/telegram/{_TEST_TELEGRAM_WEBHOOK_SECRET}", content=body)
        mock_send.assert_not_called()
    _clear_caches()


def test_telegram_duplicate_update_id_skips_outbound(monkeypatch):
    _enable_telegram(monkeypatch)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    _clear_caches()
    body = json.dumps(_telegram_group_payload("hi", update_id=100)).encode()
    with patch("bot.router.send_telegram_reply") as mock_send:
        client.post(f"/webhooks/telegram/{_TEST_TELEGRAM_WEBHOOK_SECRET}", content=body)
        client.post(f"/webhooks/telegram/{_TEST_TELEGRAM_WEBHOOK_SECRET}", content=body)
        assert mock_send.call_count == 1
    _clear_caches()


def test_telegram_ping_bot_command(monkeypatch):
    _enable_telegram(monkeypatch)
    body = json.dumps(
        {
            "update_id": 48,
            "message": {
                "text": "/ping@testbot",
                "entities": [{"offset": 0, "length": 13, "type": "bot_command"}],
                "chat": {"id": int(_TEST_TG_CHAT_ID), "type": "group"},
                "from": {"id": 7, "first_name": "Ada"},
            },
        }
    ).encode()
    with patch("bot.router.send_telegram_reply") as mock_send:
        client.post(f"/webhooks/telegram/{_TEST_TELEGRAM_WEBHOOK_SECRET}", content=body)
        mock_send.assert_called_once()
        reply = mock_send.call_args[0][2]
        assert reply.text == "pong"
    _clear_caches()


def test_telegram_text_mention_hello(monkeypatch):
    _enable_telegram(monkeypatch)
    mention = "@testbot"
    body = json.dumps(
        {
            "update_id": 49,
            "message": {
                "text": f"{mention} hello",
                "entities": [
                    {
                        "offset": 0,
                        "length": len(mention),
                        "type": "text_mention",
                        "user": {"id": 99, "username": "testbot", "is_bot": True},
                    }
                ],
                "chat": {"id": int(_TEST_TG_CHAT_ID), "type": "group"},
                "from": {"id": 7, "first_name": "Ada"},
            },
        }
    ).encode()
    with patch("bot.router.send_telegram_reply") as mock_send:
        client.post(f"/webhooks/telegram/{_TEST_TELEGRAM_WEBHOOK_SECRET}", content=body)
        mock_send.assert_called_once()
        reply = mock_send.call_args[0][2]
        assert reply.text == "Hello, Ada"
    _clear_caches()


def test_telegram_mention_helpers():
    from bot.adapters.telegram import message_addresses_bot, normalize_group_message_text

    text = "@testbot hello"
    entities = [{"offset": 0, "length": 8, "type": "mention"}]
    assert message_addresses_bot(text, entities, "testbot") is True
    assert normalize_group_message_text(text, entities, "testbot") == "hello"

    cmd = "/ping@testbot"
    cmd_entities = [{"offset": 0, "length": 13, "type": "bot_command"}]
    assert message_addresses_bot(cmd, cmd_entities, "testbot") is True
    assert normalize_group_message_text(cmd, cmd_entities, "testbot") == "/ping"


def test_echo_handler_unit():
    from bot.handlers.echo import handle_echo
    from bot.schemas import BotEvent

    event = BotEvent(
        platform="slack",
        event_type="message",
        event_id="1",
        text="ping",
    )
    assert handle_echo(event).text == "pong"

    event.text = "/ping"
    assert handle_echo(event).text == "pong"

    event.text = "hello"
    event.user_name = "Ian"
    assert handle_echo(event).text == "Hello, Ian"

    event.text = "help"
    assert "toddler" in handle_echo(event).text

    event.text = "   "
    assert handle_echo(event) is None
