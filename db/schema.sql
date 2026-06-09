-- Local dev / AlloyDB-compatible catalog (design may evolve).

CREATE TABLE IF NOT EXISTS contracts (
    drive_file_id TEXT PRIMARY KEY,
    file_name TEXT,
    mime_type TEXT,
    counterparty TEXT,
    signed_date DATE,
    total_value NUMERIC,
    currency TEXT DEFAULT 'USD',
    summary_text TEXT,
    watch_outs JSONB,
    extraction JSONB,
    drive_modified_at TIMESTAMPTZ,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS payments (
    id BIGSERIAL PRIMARY KEY,
    sheet_row_id TEXT,
    contract_ref TEXT,
    drive_file_id TEXT REFERENCES contracts (drive_file_id) ON DELETE SET NULL,
    payment_date DATE,
    amount NUMERIC,
    payee TEXT,
    memo TEXT,
    synced_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (sheet_row_id)
);

CREATE INDEX IF NOT EXISTS idx_payments_drive_file_id ON payments (drive_file_id);
CREATE INDEX IF NOT EXISTS idx_payments_contract_ref ON payments (contract_ref);

CREATE TABLE IF NOT EXISTS aliases (
    alias TEXT NOT NULL,
    drive_file_id TEXT NOT NULL REFERENCES contracts (drive_file_id) ON DELETE CASCADE,
    PRIMARY KEY (alias, drive_file_id)
);

CREATE TABLE IF NOT EXISTS ingest_log (
    id BIGSERIAL PRIMARY KEY,
    drive_file_id TEXT,
    status TEXT NOT NULL,
    detail TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS bot_processed_events (
    platform TEXT NOT NULL,
    event_id TEXT NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (platform, event_id)
);
