import json
import logging

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from bot.adapters import slack as slack_adapter
from bot.adapters import telegram as telegram_adapter
from bot.delivery import process_inbound_message
from core.config import Settings, get_settings

logger = logging.getLogger(__name__)

router = APIRouter()


def _slack_enabled(settings: Settings) -> bool:
    return "slack" in settings.bot_platforms_enabled


def _telegram_enabled(settings: Settings) -> bool:
    return "telegram" in settings.bot_platforms_enabled


@router.post("/slack/events")
async def slack_events(request: Request) -> Response:
    settings = get_settings()
    if not _slack_enabled(settings):
        return Response(status_code=404)

    body = await request.body()
    slack_adapter.verify_slack_signature(
        settings.slack_signing_secret or "",
        request.headers.get("X-Slack-Request-Timestamp", ""),
        body,
        request.headers.get("X-Slack-Signature", ""),
    )

    event = slack_adapter.parse_slack_payload(settings, body)
    if event is None:
        return Response(status_code=200)

    if event.event_type == "url_verification":
        return JSONResponse({"challenge": event.challenge})

    if event.event_type == "message":
        process_inbound_message(settings, event)

    return Response(status_code=200)


@router.post("/slack/interactions")
async def slack_interactions(request: Request) -> Response:
    settings = get_settings()
    if not _slack_enabled(settings):
        return Response(status_code=404)

    body = await request.body()
    slack_adapter.verify_slack_signature(
        settings.slack_signing_secret or "",
        request.headers.get("X-Slack-Request-Timestamp", ""),
        body,
        request.headers.get("X-Slack-Signature", ""),
    )
    return Response(status_code=200)


@router.post("/telegram/{webhook_secret}")
async def telegram_webhook(webhook_secret: str, request: Request) -> Response:
    settings = get_settings()
    if not _telegram_enabled(settings):
        return Response(status_code=404)

    expected = settings.telegram_webhook_secret or ""
    if not telegram_adapter.verify_telegram_webhook_secret(expected, webhook_secret):
        return Response(status_code=404)

    body = await request.body()
    try:
        raw = json.loads(body.decode("utf-8"))
        message = raw.get("message") or {}
        chat = message.get("chat") or {}
        logger.info(
            "Telegram webhook update_id=%s chat_id=%s type=%s text=%r",
            raw.get("update_id"),
            chat.get("id"),
            chat.get("type"),
            message.get("text"),
        )
    except (UnicodeDecodeError, json.JSONDecodeError):
        logger.warning("Telegram webhook body is not valid JSON")

    event = telegram_adapter.parse_telegram_payload(body, settings)
    if event is None:
        logger.info("Telegram webhook ignored by gating/parser")
        return Response(status_code=200)

    if event.event_type == "message":
        process_inbound_message(settings, event)

    return Response(status_code=200)
