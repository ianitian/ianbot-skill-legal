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

- Health: http://localhost:8000/health (`drive_configured`, `drive_auth` — `file` or `adc`)
- Ingest: `curl -X POST http://localhost:8000/ingest \
  -H "Content-Type: application/json" \
  -H "X-Ingest-Secret: change-me-local-only" \
  -d '{"drive_file_id":"test123","file_name":"Sample.pdf"}'`

With `DATABASE_URL` set (see `.env.example`), ingest writes to local Postgres.

When Drive is configured, `/ingest` downloads the PDF from Drive **in memory** (no file written to disk), then runs extraction.

**Drive auth (pick one):**

```bash
# Option A — service account key or WIF credentials file (legacy local)
DRIVE_AUTH=file
GOOGLE_APPLICATION_CREDENTIALS=/path/to/credentials.json

# Option B — gcloud Application Default Credentials (WIF / user login)
DRIVE_AUTH=adc
# GOOGLE_APPLICATION_CREDENTIALS unset
gcloud auth application-default login
gcloud config set project apps-staging
```

`DRIVE_AUTH=auto` (default) uses the credentials file when `GOOGLE_APPLICATION_CREDENTIALS` points at an existing file; otherwise ADC.

### Local hybrid (ADC + SA fallback)

Use while Vertex runs on gcloud ADC but Drive API is not yet enabled on the quota project (e.g. `apps-staging-wvisc`):

```bash
DRIVE_AUTH=adc
DRIVE_DEBUG_SA_FALLBACK=yes
GOOGLE_APPLICATION_CREDENTIALS=/path/to/ingest-sa.json
GEMINI_BACKEND=vertex
GOOGLE_CLOUD_PROJECT=apps-staging-wvisc
```

Unset `GOOGLE_APPLICATION_CREDENTIALS` in your **shell** before starting uvicorn so the process does not pick up the SA path for Vertex ADC (the app reads the path from `.env` for Drive fallback only).

On Drive **403**, the app retries once with the SA key file. **Do not enable `DRIVE_DEBUG_SA_FALLBACK` in production.**

Re-test with a real `drive_file_id` via curl, the helper script, or Apps Script `testPokeIngestWebhook`:

```bash
./scripts/test_ingest.py --health \
  "https://drive.google.com/file/d/YOUR_FILE_ID/view" \
  "ACME_Contract.pdf"
```

The script reads `INGEST_SECRET` from `.env` (optional `INGEST_API_URL`, default `http://localhost:8000`).

### Gemini extraction (dev — AI Studio)

1. Create an API key in **Google AI Studio**: `https://aistudio.google.com/apikey`
2. Set in `.env`:

```bash
GEMINI_ENABLED=true
GEMINI_API_KEY=your-key-here
GEMINI_BACKEND=studio
GEMINI_MODEL=gemini-2.5-flash-lite
```

3. Restart `uvicorn` (settings are cached).
4. Ingest a real PDF `drive_file_id` and verify extracted fields in Postgres.

### Vertex extraction (prod path)

Use when GCP Vertex AI is enabled and legal approves processing confidential PDFs in-project.

1. In GCP: enable **Vertex AI API**, confirm billing, grant the ingest service account **Vertex AI User** (`roles/aiplatform.user`).
2. Set in `.env`:

```bash
GEMINI_ENABLED=true
GEMINI_BACKEND=vertex
GEMINI_MODEL=gemini-2.5-flash-lite
GOOGLE_CLOUD_PROJECT=your-gcp-project
GOOGLE_CLOUD_LOCATION=us-central1
GOOGLE_APPLICATION_CREDENTIALS=/path/to/ingest-sa.json
```

3. Restart `uvicorn`. `GET /health` should show `gemini_configured: true` and `gemini_backend: vertex`.
4. Re-ingest a PDF and verify extracted fields in Postgres.

Locally, ADC comes from `GOOGLE_APPLICATION_CREDENTIALS` (same SA JSON as Drive). On GKE, workload identity provides ADC without a JSON file on the pod.

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
docker build -t wonbot-api:local .
docker run --rm -p 8000:8000 --env-file .env wonbot-api:local
```

## Bot webhooks (A1 — Slack + Telegram echo)

Set in `.env` (see `.env.example`):

```bash
BOT_PLATFORMS=slack,telegram
SLACK_SIGNING_SECRET=
SLACK_BOT_TOKEN=
TELEGRAM_BOT_TOKEN=
TELEGRAM_WEBHOOK_SECRET=
TELEGRAM_ALLOWED_CHAT_IDS=-1001234567890
TELEGRAM_BOT_USERNAME=legallywon_bot
```

`GET /health` reports `bot_platforms`, `bot_slack_configured`, `bot_telegram_configured`, `telegram_group_gating_configured`, and FAQ fields (`bot_faq_enabled`, `bot_faq_configured`, `bot_faq_count`).

**Telegram group gating:** DMs are ignored. Only `group` / `supergroup` chats listed in `TELEGRAM_ALLOWED_CHAT_IDS` are handled, and the message must **@mention** the bot (`TELEGRAM_BOT_USERNAME`). To discover a group chat id: `@mention` the bot once, then check server logs for `non-allowlisted chat_id=...` and add that id to `.env`.

**Idempotency:** when `DATABASE_URL` is set, events are deduped in `bot_processed_events`. Without a DB, an in-memory set is used (resets on process restart).

### Local smoke test

1. Start API: `uvicorn ingest.api:app --reload --port 8000`
2. Tunnel: `ngrok http 8000`
3. **Slack:** App → Event Subscriptions → Request URL `https://<ngrok>/webhooks/slack/events` (needs `SLACK_SIGNING_SECRET`). Subscribe to `message.im` or bot DMs as needed.
4. **Telegram:** `curl "https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://<ngrok>/webhooks/telegram/<TELEGRAM_WEBHOOK_SECRET>"`
5. In an allowlisted group: `@legallywon_bot ping` → `pong`; `@legallywon_bot hello` → `Hello, <name>`; `@legallywon_bot about` → build summary (version, handler status, Indexed DB based Q&A line)

Slack interactivity URL (stub, returns 200): `https://<ngrok>/webhooks/slack/interactions`

### FAQ layer (A1.5 — rapidfuzz)

Enable scripted answers in `.env`:

```bash
BOT_FAQ_ENABLED=true
BOT_FAQ_PATH=bot/content/faqs.yaml
BOT_FAQ_MIN_SCORE=80
```

Edit `bot/content/faqs.yaml` to add FAQs (`id`, `question`, `triggers`, `answer`). Restart uvicorn after `.env` changes.

With FAQ enabled, `@legallywon_bot what can you do` should match the `capabilities` entry (disclaimer prefix + answer). Unknown questions get the same build summary as `about` (handler `fallback`) until A2 (Vertex) and B1 (Indexed DB based Q&A).

Counsel observer feed (A1.6) is documented in [bot/README.md](../bot/README.md) — dev uses one Telegram bot; live will split Q&A bot vs ian-bot audit to Slack.

**Telegram local dev — polling vs webhook:** ngrok often fails to receive Telegram webhook traffic (`91.108.x.x` never hits uvicorn). Use long-polling instead:

```bash
BOT_TELEGRAM_USE_POLLING=true
```

Restart uvicorn; the app deletes the webhook and polls `getUpdates` in the background. ngrok is only needed for Slack or webhook testing, not Telegram inbound in polling mode.

See [bot/README.md](../bot/README.md) for the full launch ladder (A2+).

## Apps Script → local API

Use [ngrok](https://ngrok.com/) or similar to expose port 8000, then set Script Properties `INGEST_WEBHOOK_URL` to `https://….ngrok.io/ingest`. Do not commit tunnel URLs or secrets.
