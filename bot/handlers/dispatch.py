from typing import Optional

from bot.handlers.echo import format_about_reply, handle_echo
from bot.handlers.faq import handle_faq
from bot.schemas import BotEvent, BotReply
from core.bot_faq import load_faq_catalog
from core.config import Settings


def _enrich_debug_metadata(settings: Settings, event: BotEvent, reply: BotReply) -> BotReply:
    if not settings.bot_debug_enabled or not settings.bot_faq_enabled:
        return reply

    text = (event.text or "").strip()
    catalog = load_faq_catalog(settings.bot_faq_path)
    top = catalog.match_top_candidates(text, limit=3)
    meta = dict(reply.handler_metadata)
    meta["fuzzy_threshold"] = settings.bot_faq_min_score
    meta["fuzzy_matched"] = reply.handler == "faq"
    meta["fuzzy_top"] = [
        {
            "faq_id": match.faq_id,
            "score": match.score,
            "question": match.canonical_question,
        }
        for match in top
    ]
    return reply.model_copy(update={"handler_metadata": meta})


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
        return _enrich_debug_metadata(settings, event, echo_reply)

    faq_reply = handle_faq(settings, event)
    if faq_reply is not None:
        return _enrich_debug_metadata(settings, event, faq_reply)

    return _enrich_debug_metadata(settings, event, handle_fallback(event))
