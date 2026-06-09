import hashlib
import hmac
import json
import time
from typing import Any, Optional

from fastapi import HTTPException, status

from bot.schemas import BotEvent
from core.config import Settings

_MAX_SIGNATURE_AGE_SECONDS = 60 * 5


def verify_slack_signature(
    signing_secret: str,
    timestamp: str,
    body: bytes,
    signature: str,
) -> None:
    if not signing_secret or not signing_secret.strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Slack signing secret not configured",
        )
    if not timestamp or not signature:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Slack signature headers",
        )
    try:
        request_age = abs(time.time() - int(timestamp))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Slack timestamp",
        ) from exc
    if request_age > _MAX_SIGNATURE_AGE_SECONDS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Slack request timestamp too old",
        )

    basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
    digest = hmac.new(
        signing_secret.encode("utf-8"),
        basestring.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    expected = f"v0={digest}"
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Slack signature",
        )


def parse_slack_payload(settings: Settings, body: bytes) -> Optional[BotEvent]:
    data = json.loads(body.decode("utf-8"))

    if data.get("type") == "url_verification":
        challenge = data.get("challenge")
        if not challenge:
            return None
        return BotEvent(
            platform="slack",
            event_type="url_verification",
            event_id="url_verification",
            challenge=str(challenge),
            raw=data,
        )

    if data.get("type") != "event_callback":
        return None

    envelope_id = data.get("event_id") or ""
    event: dict[str, Any] = data.get("event") or {}
    if event.get("type") != "message":
        return None
    if event.get("bot_id") or event.get("subtype"):
        return None

    text = event.get("text")
    if text is None:
        return None

    event_id = envelope_id or event.get("client_msg_id") or event.get("ts") or ""
    if not event_id:
        return None

    return BotEvent(
        platform="slack",
        event_type="message",
        event_id=str(event_id),
        user_id=str(event.get("user") or ""),
        chat_id=str(event.get("channel") or ""),
        text=str(text),
        thread_id=str(event.get("thread_ts") or event.get("ts") or "") or None,
        raw=data,
    )
