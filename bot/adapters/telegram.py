import json
import logging
import re
from typing import Any, Optional

from bot.schemas import BotEvent
from core.config import Settings

logger = logging.getLogger(__name__)

_GROUP_CHAT_TYPES = frozenset({"group", "supergroup"})
_DM_REDIRECT_REPLY = "Private DM to won-bot is disabled; please use in a group chat"
_BOT_COMMAND_SUFFIX_RE = re.compile(r"^(/\w+)@\w+$", re.IGNORECASE)


def verify_telegram_webhook_secret(settings_secret: str, path_secret: str) -> bool:
    if not settings_secret or not settings_secret.strip():
        return False
    return hmac_compare(settings_secret.strip(), path_secret)


def hmac_compare(expected: str, actual: str) -> bool:
    import hmac

    return hmac.compare_digest(expected, actual)


def _normalized_bot_username(settings: Settings) -> str:
    return (settings.telegram_bot_username or "").strip().lstrip("@").lower()


def _entity_text(text: str, entity: dict[str, Any]) -> str:
    offset = int(entity.get("offset") or 0)
    length = int(entity.get("length") or 0)
    return text[offset : offset + length]


def _entity_user_username(entity: dict[str, Any]) -> str:
    user = entity.get("user") or {}
    return str(user.get("username") or "").strip().lstrip("@").lower()


def message_addresses_bot(text: str, entities: list[dict[str, Any]], bot_username: str) -> bool:
    if not bot_username:
        return False
    target = bot_username.lower()

    for entity in entities:
        entity_type = entity.get("type")
        if entity_type == "mention":
            mention = _entity_text(text, entity).lower().lstrip("@")
            if mention == target:
                return True
        elif entity_type == "text_mention":
            if _entity_user_username(entity) == target:
                return True
        elif entity_type == "bot_command":
            command = _entity_text(text, entity).lower()
            if command.endswith(f"@{target}"):
                return True

    return False


def normalize_group_message_text(text: str, entities: list[dict[str, Any]], bot_username: str) -> str:
    if not bot_username:
        return text.strip()

    target = bot_username.lower()
    cleaned = text

    for entity in sorted(entities, key=lambda item: int(item.get("offset") or 0), reverse=True):
        entity_type = entity.get("type")
        offset = int(entity.get("offset") or 0)
        length = int(entity.get("length") or 0)
        segment = _entity_text(cleaned, entity)

        if entity_type == "mention" and segment.lower().lstrip("@") == target:
            cleaned = cleaned[:offset] + cleaned[offset + length :]
        elif entity_type == "text_mention" and _entity_user_username(entity) == target:
            cleaned = cleaned[:offset] + cleaned[offset + length :]
        elif entity_type == "bot_command" and segment.lower().endswith(f"@{target}"):
            match = _BOT_COMMAND_SUFFIX_RE.match(segment)
            cleaned = match.group(1) if match else segment.split("@", 1)[0]

    return cleaned.strip()


def _passes_group_gating(
    settings: Settings,
    chat: dict[str, Any],
    text: str,
    entities: list[dict[str, Any]],
) -> Optional[str]:
    """Return normalized message text if allowed, else None."""
    allowed = settings.telegram_allowed_chat_ids_set
    if not allowed:
        return None

    chat_type = str(chat.get("type") or "")
    chat_id = str(chat.get("id") or "")

    if chat_type not in _GROUP_CHAT_TYPES:
        logger.debug("Ignoring Telegram message from unsupported chat type=%s", chat_type)
        return None
    if chat_id not in allowed:
        logger.info(
            "Ignoring Telegram message from non-allowlisted chat_id=%s (add to TELEGRAM_ALLOWED_CHAT_IDS)",
            chat_id,
        )
        return None

    bot_username = _normalized_bot_username(settings)
    if not bot_username:
        return None
    if not message_addresses_bot(text, entities, bot_username):
        logger.debug(
            "Ignoring Telegram group message not addressed to @%s (mention, text_mention, or command)",
            bot_username,
        )
        return None

    normalized = normalize_group_message_text(text, entities, bot_username)
    return normalized if normalized else None


def parse_telegram_payload(body: bytes, settings: Settings) -> Optional[BotEvent]:
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
    entities = message.get("entities") or []
    text_str = str(text)

    user = message.get("from") or {}
    first = (user.get("first_name") or "").strip()
    last = (user.get("last_name") or "").strip()
    user_name = " ".join(part for part in (first, last) if part)
    chat_type = str(chat.get("type") or "")
    allowed = settings.telegram_allowed_chat_ids_set

    if allowed and chat_type == "private":
        logger.debug("Redirecting Telegram private DM to group-chat message")
        return BotEvent(
            platform="telegram",
            event_type="message",
            event_id=str(update_id),
            user_id=str(user.get("id") or ""),
            user_name=user_name,
            chat_id=str(chat.get("id") or ""),
            forced_reply=_DM_REDIRECT_REPLY,
            raw=data,
        )

    gated_text = _passes_group_gating(settings, chat, text_str, entities)
    if gated_text is None:
        return None

    return BotEvent(
        platform="telegram",
        event_type="message",
        event_id=str(update_id),
        user_id=str(user.get("id") or ""),
        user_name=user_name,
        chat_id=str(chat.get("id") or ""),
        text=gated_text,
        raw=data,
    )
