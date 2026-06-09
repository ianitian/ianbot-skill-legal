import logging

from core.bot_db import record_processed_event
from core.config import get_settings

logger = logging.getLogger(__name__)

_memory_seen: set[str] = set()


def try_record_event(platform: str, event_id: str) -> bool:
    """Return True if this event should be processed (first time seen)."""
    settings = get_settings()
    if settings.database_configured:
        try:
            return record_processed_event(platform, event_id)
        except Exception:
            logger.exception(
                "bot_processed_events insert failed; falling back to in-memory dedup"
            )

    key = f"{platform}:{event_id}"
    if key in _memory_seen:
        return False
    _memory_seen.add(key)
    return True


def clear_memory_seen() -> None:
    """Test helper: reset in-memory dedup state."""
    _memory_seen.clear()
