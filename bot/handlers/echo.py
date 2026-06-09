from typing import Optional

from bot.schemas import BotEvent, BotReply


def handle_echo(event: BotEvent) -> Optional[BotReply]:
    text = (event.text or "").strip()
    if not text:
        return None
    if text.lower() in {"/ping", "ping"}:
        return BotReply(text="pong")
    return BotReply(text=f"You said: {text}")
