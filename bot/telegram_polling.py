import asyncio
import json
import logging
from typing import Optional

import httpx

from bot.adapters import telegram as telegram_adapter
from bot.delivery import process_inbound_message
from core.config import Settings, get_settings

logger = logging.getLogger(__name__)

_poll_task: Optional[asyncio.Task] = None
_stop_event: Optional[asyncio.Event] = None


def process_telegram_update(body: bytes) -> bool:
    """Parse and handle one Telegram update JSON. Return True if handled."""
    settings = get_settings()
    try:
        data = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        logger.warning("Telegram update JSON parse failed")
        return False

    update_id = data.get("update_id")
    message = data.get("message") or {}
    chat = message.get("chat") or {}
    logger.info(
        "Telegram update_id=%s chat_id=%s type=%s text=%r entities=%s",
        update_id,
        chat.get("id"),
        chat.get("type"),
        message.get("text"),
        message.get("entities"),
    )

    event = telegram_adapter.parse_telegram_payload(body, settings)
    if event is None:
        logger.info("Telegram update_id=%s ignored by gating/parser", update_id)
        return False

    if event.event_type == "message":
        process_inbound_message(settings, event)
        return True
    return False


async def _poll_loop(stop_event: asyncio.Event) -> None:
    token = (get_settings().telegram_bot_token or "").strip()
    if not token:
        logger.warning("BOT_TELEGRAM_USE_POLLING set but TELEGRAM_BOT_TOKEN missing")
        return

    try:
        async with httpx.AsyncClient(timeout=35.0) as client:
            delete_resp = await client.get(
                f"https://api.telegram.org/bot{token}/deleteWebhook",
                params={"drop_pending_updates": False},
            )
            delete_resp.raise_for_status()
            logger.info("Telegram polling mode: webhook deleted (%s)", delete_resp.json().get("description"))
    except httpx.HTTPError as exc:
        logger.error("Failed to delete Telegram webhook for polling mode: %s", exc)
        return

    offset = 0
    api_url = f"https://api.telegram.org/bot{token}/getUpdates"

    while not stop_event.is_set():
        try:
            async with httpx.AsyncClient(timeout=35.0) as client:
                response = await client.get(
                    api_url,
                    params={"timeout": 25, "offset": offset, "allowed_updates": '["message","callback_query"]'},
                )
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPError as exc:
            logger.error("Telegram getUpdates failed: %s", exc)
            await asyncio.sleep(5)
            continue

        if not payload.get("ok"):
            logger.error("Telegram getUpdates not ok: %s", payload.get("description"))
            await asyncio.sleep(5)
            continue

        for update in payload.get("result") or []:
            if stop_event.is_set():
                break
            update_id = int(update.get("update_id") or 0)
            offset = update_id + 1
            body = json.dumps(update).encode("utf-8")
            await asyncio.to_thread(process_telegram_update, body)

        await asyncio.sleep(0.1)


def polling_is_active() -> bool:
    return _poll_task is not None and not _poll_task.done()


def start_polling() -> Optional[asyncio.Task]:
    global _poll_task, _stop_event
    settings = get_settings()
    if not settings.bot_telegram_use_polling:
        return None
    if "telegram" not in settings.bot_platforms_enabled:
        logger.warning("BOT_TELEGRAM_USE_POLLING set but telegram not in BOT_PLATFORMS")
        return None

    _stop_event = asyncio.Event()
    _poll_task = asyncio.create_task(_poll_loop(_stop_event), name="telegram-polling")
    logger.info("Telegram long-polling started (dev mode)")
    return _poll_task


async def stop_polling() -> None:
    global _poll_task, _stop_event
    if _stop_event is not None:
        _stop_event.set()
    if _poll_task is not None:
        _poll_task.cancel()
        try:
            await _poll_task
        except asyncio.CancelledError:
            pass
    _poll_task = None
    _stop_event = None
