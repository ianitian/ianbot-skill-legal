import logging

import httpx

from bot.schemas import BotEvent, BotReply
from core.config import Settings

logger = logging.getLogger(__name__)

_SLACK_API_URL = "https://slack.com/api/chat.postMessage"


def post_slack_message(
    settings: Settings,
    channel: str,
    text: str,
    *,
    thread_ts: str | None = None,
) -> None:
    token = settings.slack_bot_token
    if not token or not token.strip():
        logger.warning("SLACK_BOT_TOKEN not set; skipping Slack chat.postMessage")
        return
    if not channel or not channel.strip():
        logger.warning("Slack channel missing; skipping chat.postMessage")
        return

    payload: dict[str, object] = {"channel": channel, "text": text}
    if thread_ts:
        payload["thread_ts"] = thread_ts

    try:
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
    except httpx.HTTPError as exc:
        logger.error("Slack chat.postMessage request failed: %s", exc)


def send_slack_reply(settings: Settings, event: BotEvent, reply: BotReply) -> None:
    if not event.chat_id:
        logger.warning("Slack event missing channel; skipping outbound reply")
        return

    post_slack_message(
        settings,
        event.chat_id,
        reply.text,
        thread_ts=event.thread_id,
    )
