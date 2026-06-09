import logging

import httpx

from bot.schemas import BotEvent, BotReply
from core.config import Settings

logger = logging.getLogger(__name__)

_SLACK_API_URL = "https://slack.com/api/chat.postMessage"


def send_slack_reply(settings: Settings, event: BotEvent, reply: BotReply) -> None:
    token = settings.slack_bot_token
    if not token or not token.strip():
        logger.warning("SLACK_BOT_TOKEN not set; skipping outbound reply")
        return
    if not event.chat_id:
        logger.warning("Slack event missing channel; skipping outbound reply")
        return

    payload: dict[str, object] = {
        "channel": event.chat_id,
        "text": reply.text,
    }
    if event.thread_id:
        payload["thread_ts"] = event.thread_id

    response = httpx.post(
        _SLACK_API_URL,
        headers={"Authorization": f"Bearer {token.strip()}"},
        json=payload,
        timeout=10.0,
    )
    response.raise_for_status()
    data = response.json()
    if not data.get("ok"):
        logger.error("Slack chat.postMessage failed: %s", data.get("error"))
