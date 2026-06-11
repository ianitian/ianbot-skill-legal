from typing import Optional

from bot.schemas import BotEvent, BotReply
from core.bot_faq import load_faq_catalog
from core.config import Settings

_RECEPTIONIST_STUB_TEXT = (
    "won-bot receptionist (scaffold): Vertex gate not wired yet. "
    "Set BOT_RECEPTIONIST_ENABLED=false to use FAQ/fallback, or complete Phase 2 on this branch."
)


def handle_receptionist(settings: Settings, event: BotEvent) -> Optional[BotReply]:
    text = (event.text or "").strip()
    if not text:
        return None

    catalog = load_faq_catalog(settings.bot_faq_path)
    candidates = catalog.match_top_candidates(
        text,
        limit=settings.bot_receptionist_candidate_limit,
    )
    top_score = candidates[0].score if candidates else 0

    return BotReply(
        text=_RECEPTIONIST_STUB_TEXT,
        handler="receptionist",
        handler_metadata={
            "phase": "scaffold",
            "candidate_count": len(candidates),
            "top_fuzzy_score": top_score,
            "top_faq_id": candidates[0].faq_id if candidates else None,
        },
    )
