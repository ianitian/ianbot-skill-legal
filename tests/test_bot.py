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
    _clear_caches()


def test_health_includes_bot_fields():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "bot_platforms" in data
    assert "bot_slack_configured" in data
    assert "bot_telegram_configured" in data
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
        assert reply.text == "You said: hello"
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
    body = json.dumps({"update_id": 1, "message": {"text": "hi", "chat": {"id": 1}, "from": {"id": 2}}}).encode()
    response = client.post("/webhooks/telegram/wrong-secret", content=body)
    assert response.status_code == 404
    _clear_caches()


def test_telegram_echo(monkeypatch):
    _enable_telegram(monkeypatch)
    body = json.dumps(
        {
            "update_id": 42,
            "message": {"text": "hello", "chat": {"id": 99}, "from": {"id": 7}},
        }
    ).encode()
    with patch("bot.router.send_telegram_reply") as mock_send:
        response = client.post(
            f"/webhooks/telegram/{_TEST_TELEGRAM_WEBHOOK_SECRET}", content=body
        )
        assert response.status_code == 200
        mock_send.assert_called_once()
        reply = mock_send.call_args[0][2]
        assert reply.text == "You said: hello"
    _clear_caches()


def test_telegram_ping_returns_pong(monkeypatch):
    _enable_telegram(monkeypatch)
    body = json.dumps(
        {
            "update_id": 43,
            "message": {"text": "ping", "chat": {"id": 99}, "from": {"id": 7}},
        }
    ).encode()
    with patch("bot.router.send_telegram_reply") as mock_send:
        client.post(f"/webhooks/telegram/{_TEST_TELEGRAM_WEBHOOK_SECRET}", content=body)
        reply = mock_send.call_args[0][2]
        assert reply.text == "pong"
    _clear_caches()


def test_telegram_duplicate_update_id_skips_outbound(monkeypatch):
    _enable_telegram(monkeypatch)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    _clear_caches()
    body = json.dumps(
        {
            "update_id": 100,
            "message": {"text": "hi", "chat": {"id": 1}, "from": {"id": 2}},
        }
    ).encode()
    with patch("bot.router.send_telegram_reply") as mock_send:
        client.post(f"/webhooks/telegram/{_TEST_TELEGRAM_WEBHOOK_SECRET}", content=body)
        client.post(f"/webhooks/telegram/{_TEST_TELEGRAM_WEBHOOK_SECRET}", content=body)
        assert mock_send.call_count == 1
    _clear_caches()


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
    assert handle_echo(event).text == "You said: hello"

    event.text = "   "
    assert handle_echo(event) is None
