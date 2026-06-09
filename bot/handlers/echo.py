from typing import Optional

from bot.schemas import BotEvent, BotReply

_TODDLER_REPLY = (
    "I am a toddler and slowly learning things. "
    "I only know how to respond to ping and hello right now."
)


def _display_name(event: BotEvent) -> str:
    name = (event.user_name or "").strip()
    return name if name else "friend"


def handle_echo(event: BotEvent) -> Optional[BotReply]:
    text = (event.text or "").strip()
    if not text:
        return None

    normalized = text.lower()
    if normalized in {"/ping", "ping"}:
        return BotReply(text="pong")
    if normalized in {"/hello", "hello"}:
        return BotReply(text=f"Hello, {_display_name(event)}")
    return BotReply(text=_TODDLER_REPLY)
