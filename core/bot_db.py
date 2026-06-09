from core.db import get_connection


def record_processed_event(platform: str, event_id: str) -> bool:
    """Insert idempotency key. Returns True if new, False if duplicate."""
    with get_connection() as conn:
        row = conn.execute(
            """
            INSERT INTO bot_processed_events (platform, event_id)
            VALUES (%(platform)s, %(event_id)s)
            ON CONFLICT DO NOTHING
            RETURNING event_id
            """,
            {"platform": platform, "event_id": event_id},
        ).fetchone()
    return row is not None
