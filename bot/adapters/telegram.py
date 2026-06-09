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
_MENTION_IN_TEXT_RE = re.compile(r"@(\w+)", re.IGNORECASE)


def _utf16_len(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def _utf16_slice(text: str, offset: int, length: int) -> str:
    """Telegram entity offsets/lengths are UTF-16 code units."""
    encoded = text.encode("utf-16-le")
    start = offset * 2
    end = (offset + length) * 2
    return encoded[start:end].decode("utf-16-le")


def _utf16_remove_range(text: str, offset: int, length: int) -> str:
    total = _utf16_len(text)
    return _utf16_slice(text, 0, offset) + _utf16_slice(text, offset + length, total - offset - length)


def _bot_id_from_token(token: Optional[str]) -> str:
    if not token:
        return ""
    bot_id = token.strip().split(":", 1)[0]
    return bot_id if bot_id.isdigit() else ""


def _mention_in_text(text: str, bot_username: str) -> bool:
    if not bot_username:
        return False
    target = bot_username.lower()
    for match in _MENTION_IN_TEXT_RE.finditer(text):
        if match.group(1).lower() == target:
            return True
    return False


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
    return _utf16_slice(text, offset, length)


def _entity_user_username(entity: dict[str, Any]) -> str:
    user = entity.get("user") or {}
    return str(user.get("username") or "").strip().lstrip("@").lower()


def is_reply_to_bot(message: dict[str, Any], bot_username: str) -> bool:
    if not bot_username:
        return False
    reply = message.get("reply_to_message") or {}
    user = reply.get("from") or {}
    if not user.get("is_bot"):
        return False
    username = str(user.get("username") or "").strip().lstrip("@").lower()
    return username == bot_username.lower()


def message_addresses_bot(
    text: str,
    entities: list[dict[str, Any]],
    bot_username: str,
    bot_id: str = "",
) -> bool:
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
            user = entity.get("user") or {}
            if _entity_user_username(entity) == target:
                return True
            if bot_id and user.get("is_bot") and str(user.get("id") or "") == bot_id:
                return True
        elif entity_type == "bot_command":
            command = _entity_text(text, entity).lower()
            if command.endswith(f"@{target}"):
                return True

    return _mention_in_text(text, bot_username)


def normalize_group_message_text(
    text: str,
    entities: list[dict[str, Any]],
    bot_username: str,
    bot_id: str = "",
) -> str:
    if not bot_username:
        return text.strip()

    target = bot_username.lower()
    cleaned = text

    for entity in sorted(entities, key=lambda item: int(item.get("offset") or 0), reverse=True):
        entity_type = entity.get("type")
        offset = int(entity.get("offset") or 0)
        length = int(entity.get("length") or 0)
        segment = _entity_text(cleaned, entity)
        user = entity.get("user") or {}
        is_bot_mention = entity_type == "text_mention" and (
            _entity_user_username(entity) == target
            or (bot_id and user.get("is_bot") and str(user.get("id") or "") == bot_id)
        )

        if entity_type == "mention" and segment.lower().lstrip("@") == target:
            cleaned = _utf16_remove_range(cleaned, offset, length)
        elif is_bot_mention:
            cleaned = _utf16_remove_range(cleaned, offset, length)
        elif entity_type == "bot_command" and segment.lower().endswith(f"@{target}"):
            match = _BOT_COMMAND_SUFFIX_RE.match(segment)
            cleaned = match.group(1) if match else segment.split("@", 1)[0]

    cleaned = cleaned.strip()
    pattern = re.compile(rf"^@{re.escape(target)}\s*", re.IGNORECASE)
    return pattern.sub("", cleaned).strip()


def _passes_group_gating(
    settings: Settings,
    message: dict[str, Any],
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
    bot_id = _bot_id_from_token(settings.telegram_bot_token)
    addressed = message_addresses_bot(text, entities, bot_username, bot_id)
    if not addressed and not is_reply_to_bot(message, bot_username):
        logger.info(
            "Ignoring Telegram group message not addressed to @%s (mention, command, or reply-to-bot); text=%r entities=%s",
            bot_username,
            text,
            entities,
        )
        return None

    if addressed:
        normalized = normalize_group_message_text(text, entities, bot_username, bot_id)
    else:
        normalized = text.strip()
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

    gated_text = _passes_group_gating(settings, message, chat, text_str, entities)
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
