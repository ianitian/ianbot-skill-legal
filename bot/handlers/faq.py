from typing import Optional

from bot.schemas import BotEvent, BotReply
from core.bot_faq import load_faq_catalog
from core.config import Settings

FAQ_DISCLAIMER = (
    "{Warning: WIP / general advice only. For actual legal clearance, please discuss with Won.}"
)


def _format_faq_reply(answer: str) -> str:
    body = answer.strip()
    return f"{FAQ_DISCLAIMER}\n\n{body}" if body else FAQ_DISCLAIMER


def handle_faq(settings: Settings, event: BotEvent) -> Optional[BotReply]:
    if not settings.bot_faq_enabled:
        return None

    text = (event.text or "").strip()
    if not text:
        return None

    catalog = load_faq_catalog(settings.bot_faq_path)
    if catalog.count == 0:
        return None

    match = catalog.match(text, settings.bot_faq_min_score)
    if match is None:
        return None

    return BotReply(
        text=_format_faq_reply(match.answer),
        handler="faq",
        handler_metadata={
            "faq_id": match.faq_id,
            "score": match.score,
            "matched_question": match.canonical_question,
        },
    )
