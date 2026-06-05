# Local development

## Prerequisites

- Python 3.9+ (3.12+ recommended)
- Docker (for Postgres)

## Setup

```bash
cp .env.example .env
# Edit INGEST_SECRET in .env if you like.

python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

docker compose up -d postgres
```

**Wipe local DB (full reset):** `./scripts/wipe-local-db.sh` — removes the Postgres volume and recreates tables from `db/schema.sql`.

## Run API

```bash
uvicorn ingest.api:app --reload --port 8000
```

- Health: http://localhost:8000/health (`drive_configured` is true when `GOOGLE_APPLICATION_CREDENTIALS` points at a service account JSON file)
- Ingest: `curl -X POST http://localhost:8000/ingest \
  -H "Content-Type: application/json" \
  -H "X-Ingest-Secret: change-me-local-only" \
  -d '{"drive_file_id":"test123","file_name":"Sample.pdf"}'`

With `DATABASE_URL` set (see `.env.example`), ingest writes to local Postgres.

When `GOOGLE_APPLICATION_CREDENTIALS` is set, `/ingest` downloads the PDF from Drive **in memory** (no file written to disk), then runs extraction. Re-test with a real `drive_file_id` via curl or Apps Script `testPokeIngestWebhook`.

## Tests

```bash
pytest
```

## Versioning (commits)

- **First release** and tagged commits: include version in message, e.g. `feat(v0.0.1): …`.
- **Routine revisions:** run `./scripts/commit-revision.sh -m "fix(v0.0.2): …"` (bumps patch), or enable `./scripts/setup-git-hooks.sh` so every `git commit` auto-bumps patch.
- **Minor / major:** only when you run `scripts/bump_minor.py` or `scripts/bump_major.py` yourself.

## Docker image (matches GKE-bound Dockerfile)

```bash
docker build -t ianbot-api:local .
docker run --rm -p 8000:8000 --env-file .env ianbot-api:local
```

## Apps Script → local API

Use [ngrok](https://ngrok.com/) or similar to expose port 8000, then set Script Properties `INGEST_WEBHOOK_URL` to `https://….ngrok.io/ingest`. Do not commit tunnel URLs or secrets.
