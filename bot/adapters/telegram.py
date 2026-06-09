import json
from typing import Any, Optional

from bot.schemas import BotEvent


def verify_telegram_webhook_secret(settings_secret: str, path_secret: str) -> bool:
    if not settings_secret or not settings_secret.strip():
        return False
    return hmac_compare(settings_secret.strip(), path_secret)


def hmac_compare(expected: str, actual: str) -> bool:
    import hmac

    return hmac.compare_digest(expected, actual)


def parse_telegram_payload(body: bytes) -> Optional[BotEvent]:
    data = json.loads(body.decode("utf-8"))
    update_id = data.get("update_id")
    if update_id is None:
        return None

    message: dict[str, Any] = data.get("message") or {}
    if not message:
        return None

    text = message.get("text")
    if text is None:
        return None

    chat = message.get("chat") or {}
    user = message.get("from") or {}

    return BotEvent(
        platform="telegram",
        event_type="message",
        event_id=str(update_id),
        user_id=str(user.get("id") or ""),
        chat_id=str(chat.get("id") or ""),
        text=str(text),
        raw=data,
    )
