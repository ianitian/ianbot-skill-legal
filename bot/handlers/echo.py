from typing import Optional

from bot.schemas import BotEvent, BotReply
from core.config import get_settings
from core.version import get_app_version

_ABOUT_COMMANDS = {"/about", "about", "/version", "version"}


def _display_name(event: BotEvent) -> str:
    name = (event.user_name or "").strip()
    return name if name else "friend"


def format_about_reply() -> str:
    settings = get_settings()
    version = get_app_version()
    faq_status = "on" if settings.bot_faq_enabled else "off"
    return (
        "won-bot — legal Q&A bot (dev)\n"
        f"ianbot-api v{version}\n"
        "\n"
        "Echo commands (exact):\n"
        "  ping, /ping          → pong\n"
        "  hello, /hello        → greeting\n"
        "  about, /about        → this info\n"
        "  version, /version    → this info\n"
        "\n"
        f"Handlers: echo + rapidfuzz FAQ ({faq_status})\n"
        "Vertex chat: not enabled\n"
        "Indexed DB based Q&A: not enabled"
    )


def handle_echo(event: BotEvent) -> Optional[BotReply]:
    text = (event.text or "").strip()
    if not text:
        return None

    normalized = text.lower()
    if normalized in {"/ping", "ping"}:
        return BotReply(text="pong", handler="echo")
    if normalized in {"/hello", "hello"}:
        return BotReply(text=f"Hello, {_display_name(event)}", handler="echo")
    if normalized in _ABOUT_COMMANDS:
        version = get_app_version()
        return BotReply(
            text=format_about_reply(),
            handler="echo",
            handler_metadata={"command": "about", "version": version},
        )
    return None
