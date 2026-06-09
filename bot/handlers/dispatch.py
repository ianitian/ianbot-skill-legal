from typing import Optional

from bot.handlers.echo import format_about_reply, handle_echo
from bot.handlers.faq import handle_faq
from bot.schemas import BotEvent, BotReply
from core.config import Settings


def handle_fallback(event: BotEvent) -> BotReply:
    return BotReply(
        text=format_about_reply(),
        handler="fallback",
        handler_metadata={"reason": "no_match"},
    )


def dispatch_message(settings: Settings, event: BotEvent) -> Optional[BotReply]:
    text = (event.text or "").strip()
    if not text:
        return None

    echo_reply = handle_echo(event)
    if echo_reply is not None:
        return echo_reply

    faq_reply = handle_faq(settings, event)
    if faq_reply is not None:
        return faq_reply

    return handle_fallback(event)
