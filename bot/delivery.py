from bot.debug import emit_debug, format_debug_message
from bot.handlers.dispatch import dispatch_message
from bot.idempotency import try_record_event
from bot.outbound.slack_client import send_slack_reply
from bot.outbound.telegram_client import send_telegram_reply
from bot.schemas import BotEvent, BotReply
from core.config import Settings


def deliver_bot_reply(settings: Settings, event: BotEvent, reply: BotReply) -> None:
    if event.platform == "slack":
        send_slack_reply(settings, event, reply)
    elif event.platform == "telegram":
        send_telegram_reply(settings, event, reply)

    if settings.bot_debug_enabled:
        emit_debug(settings, event, format_debug_message(settings, event, reply))


def process_inbound_message(settings: Settings, event: BotEvent) -> None:
    if not try_record_event(event.platform, event.event_id):
        return

    if event.forced_reply:
        reply = BotReply(text=event.forced_reply)
    else:
        reply = dispatch_message(settings, event)
        if reply is None:
            return

    deliver_bot_reply(settings, event, reply)
