#!/usr/bin/env bash
# Wipe local dev Postgres: remove Docker volume and recreate DB from db/schema.sql.
set -euo pipefail

cd "$(dirname "$0")/.."

echo "==> Stopping Postgres and removing volume (ianbot_pgdata)..."
docker compose down -v

echo "==> Starting fresh Postgres..."
docker compose up -d postgres

echo "==> Waiting for Postgres..."
ready=0
for _ in $(seq 1 30); do
  if docker compose exec -T postgres pg_isready -U ianbot -d ianbot >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 1
done

if [[ "$ready" -ne 1 ]]; then
  echo "ERROR: Postgres did not become ready in 30s." >&2
  exit 1
fi

echo "==> Table row counts (should all be 0):"
docker compose exec -T postgres psql -U ianbot -d ianbot -c "
SELECT 'contracts' AS table_name, COUNT(*)::int AS rows FROM contracts
UNION ALL SELECT 'payments', COUNT(*)::int FROM payments
UNION ALL SELECT 'aliases', COUNT(*)::int FROM aliases
UNION ALL SELECT 'ingest_log', COUNT(*)::int FROM ingest_log;
"

echo "Done. Local catalog is empty; schema reapplied from db/schema.sql."
