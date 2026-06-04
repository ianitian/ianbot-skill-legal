from contextlib import contextmanager
from typing import Iterator

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from core.config import get_settings
from core.extract import ContractFields, fields_to_extraction_json


@contextmanager
def get_connection() -> Iterator[psycopg.Connection]:
    settings = get_settings()
    if not settings.database_configured:
        raise RuntimeError("DATABASE_URL is not configured")
    conn = psycopg.connect(settings.database_url, row_factory=dict_row)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def upsert_contract(
    drive_file_id: str,
    file_name: str,
    mime_type: str,
    fields: ContractFields,
) -> None:
    extraction = fields_to_extraction_json(fields)
    watch_outs = extraction.get("watch_outs") or []

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO contracts (
                drive_file_id, file_name, mime_type, counterparty, signed_date,
                total_value, currency, summary_text, watch_outs, extraction, updated_at
            ) VALUES (
                %(drive_file_id)s, %(file_name)s, %(mime_type)s, %(counterparty)s,
                %(signed_date)s, %(total_value)s, %(currency)s, %(summary_text)s,
                %(watch_outs)s::jsonb, %(extraction)s::jsonb, NOW()
            )
            ON CONFLICT (drive_file_id) DO UPDATE SET
                file_name = EXCLUDED.file_name,
                mime_type = EXCLUDED.mime_type,
                counterparty = EXCLUDED.counterparty,
                signed_date = EXCLUDED.signed_date,
                total_value = EXCLUDED.total_value,
                currency = EXCLUDED.currency,
                summary_text = EXCLUDED.summary_text,
                watch_outs = EXCLUDED.watch_outs,
                extraction = EXCLUDED.extraction,
                updated_at = NOW()
            """,
            {
                "drive_file_id": drive_file_id,
                "file_name": file_name,
                "mime_type": mime_type,
                "counterparty": fields.counterparty,
                "signed_date": fields.signed_date,
                "total_value": fields.total_value,
                "currency": fields.currency,
                "summary_text": fields.summary_text,
                "watch_outs": Jsonb(watch_outs),
                "extraction": Jsonb(extraction),
            },
        )
        conn.execute(
            """
            INSERT INTO ingest_log (drive_file_id, status, detail)
            VALUES (%(drive_file_id)s, 'ok', 'ingested')
            """,
            {"drive_file_id": drive_file_id},
        )


def count_contracts() -> int:
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM contracts").fetchone()
        return int(row["n"]) if row else 0
