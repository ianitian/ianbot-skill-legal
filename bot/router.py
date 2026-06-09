from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from bot.adapters import slack as slack_adapter
from bot.adapters import telegram as telegram_adapter
from bot.handlers.echo import handle_echo
from bot.idempotency import try_record_event
from bot.outbound.slack_client import send_slack_reply
from bot.outbound.telegram_client import send_telegram_reply
from bot.schemas import BotEvent, BotReply
from core.config import Settings, get_settings

router = APIRouter()


def _slack_enabled(settings: Settings) -> bool:
    return "slack" in settings.bot_platforms_enabled


def _telegram_enabled(settings: Settings) -> bool:
    return "telegram" in settings.bot_platforms_enabled


def _process_message(settings: Settings, event: BotEvent) -> None:
    if not try_record_event(event.platform, event.event_id):
        return

    if event.forced_reply:
        reply = BotReply(text=event.forced_reply)
    else:
        reply = handle_echo(event)
        if reply is None:
            return

    if event.platform == "slack":
        send_slack_reply(settings, event, reply)
    elif event.platform == "telegram":
        send_telegram_reply(settings, event, reply)


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
        _process_message(settings, event)

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
    event = telegram_adapter.parse_telegram_payload(body, settings)
    if event is None:
        return Response(status_code=200)

    if event.event_type == "message":
        _process_message(settings, event)

    return Response(status_code=200)
