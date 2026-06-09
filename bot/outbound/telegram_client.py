import logging

import httpx

from bot.schemas import BotEvent, BotReply
from core.config import Settings

logger = logging.getLogger(__name__)


def _telegram_api_url(settings: Settings) -> str:
    token = (settings.telegram_bot_token or "").strip()
    return f"https://api.telegram.org/bot{token}/sendMessage"


def send_telegram_reply(settings: Settings, event: BotEvent, reply: BotReply) -> None:
    token = settings.telegram_bot_token
    if not token or not token.strip():
        logger.warning("TELEGRAM_BOT_TOKEN not set; skipping outbound reply")
        return
    if not event.chat_id:
        logger.warning("Telegram event missing chat_id; skipping outbound reply")
        return

    try:
        response = httpx.post(
            _telegram_api_url(settings),
            json={"chat_id": event.chat_id, "text": reply.text},
            timeout=10.0,
        )
        response.raise_for_status()
        data = response.json()
        if not data.get("ok"):
            logger.error("Telegram sendMessage failed: %s", data.get("description"))
    except httpx.HTTPError as exc:
        logger.error("Telegram sendMessage request failed: %s", exc)
