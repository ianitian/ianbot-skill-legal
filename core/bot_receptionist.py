from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from core.bot_faq import FaqMatch
from core.config import Settings

ReceptionistDecisionType = Literal["use_faq", "generate", "decline"]


@dataclass(frozen=True)
class ReceptionistDecision:
    decision: ReceptionistDecisionType
    faq_id: Optional[str] = None
    confidence: Optional[float] = None
    response: Optional[str] = None


def decide(
    settings: Settings,
    user_text: str,
    candidates: list[FaqMatch],
) -> ReceptionistDecision:
    """Vertex receptionist gate (Phase 2). Scaffold raises until wired."""
    _ = (settings, user_text, candidates)
    raise NotImplementedError("receptionist decide() is not implemented until Phase 2")
