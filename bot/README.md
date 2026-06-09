# Bot webhooks (`bot/`)

Incoming messages from **Slack** and **Telegram** hit the same `ianbot-api` deployment as ingest. Platform-specific verification and JSON live in **adapters**; contract Q&A, linking, and access control live in **core** and **handlers**.

See also the product roadmap in [readme.md](../readme.md) (Phases 2b–4).

## Design principle

**Platform adapters in, domain logic out.**

Slack and Telegram differ in payloads, verification, and reply mechanics. Handlers only see normalized events:

| Normalized event | Examples |
|------------------|----------|
| `message.received` | Slack DM, Telegram text or command |
| `action.clicked` | Slack block button, Telegram inline keyboard |
| `url_verification` | Slack Events API handshake |

Outbound code maps `BotReply` → Slack blocks or Telegram `sendMessage` / `answerCallbackQuery`.

---

## Launch ladder (ship one step at a time)

Each step is deployable behind the same Ingress URLs. Later steps add handler depth, not webhook rewrites.

| Step | What ships | Safe audience | User experience |
|------|------------|---------------|-----------------|
| **A1** ✅ | Webhook verify + echo | Dev / smoke test | Bot echoes or replies `pong` |
| **A2** | Vertex conversational chat (no DB) | Small internal test | Back-and-forth NLP; system prompt says catalog not connected yet |
| **A3** | Allowlist + audit log | Allowlisted users only | Strangers get a polite access-denied message |
| **B1** | Catalog Q&A (Postgres + citations) | Allowlisted users | Answers grounded in ingested PDFs; “not found” when empty |
| **C** | Payment-link buttons + action tokens | Finance allowlist | Click to link sheet row → `contract_ref` |
| **D** | Sheet-triggered outbound messages | Finance workflow | Checkbox → bot posts link options in Slack/TG |
| **E** | Hardening | Production | Rate limits, golden tests, monitoring, disclaimer policy |

### Incremental feature order (your sequence)

1. **Respond to text** → A1  
2. **Vertex NLP prompt/answer loop** → A2 (reuse `core/gemini_client.py`; separate chat prompt from PDF extract)  
3. **Allowlist gating** → A3 (middleware in router; no adapter changes)  
4. **Refer to PDF DB** → B1 (retrieve from `contracts` / `aliases`, cite sources)  
5. **Linking and sheet flows** → C, D  

Until **B1**, keep a strict system prompt: do not invent contract clauses.

---

## Request flow

```text
Slack / Telegram
       │
       ▼ POST /webhooks/{platform}/...
  bot/adapters/*     verify signature / secret token
       │
       ▼ BotEvent (normalized)
  bot/router.py      idempotency → allowlist → dispatch
       │
       ├── handlers/qa.py          (A2 generic → B1 catalog-grounded)
       └── handlers/link_payment.py (C+)
       │
       ▼ BotReply
  bot/outbound/*     platform API or sync response body
```

Slack Events and interactivity must **ack within ~3s**. Return `200` immediately when work is slow; call `chat.postMessage` or `response_url` afterward.

---

## HTTP surface

Mounted under `/webhooks` on the same FastAPI app as ingest (`ingest/api.py`).

| Route | Caller | Purpose |
|-------|--------|---------|
| `POST /webhooks/slack/events` | Slack Events API | DMs, mentions, messages |
| `POST /webhooks/slack/interactions` | Slack interactivity | Button clicks |
| `POST /webhooks/telegram/{secret}` | Telegram Bot API | All updates (`message`, `callback_query`, …) |

Ingest (`POST /ingest`, `POST /sync/sheet`) keeps **`X-Ingest-Secret`**. Bot routes use **platform verification** (signing secret, path token)—not the ingest secret.

---

## Layout

```text
bot/
  router.py           # FastAPI routes (implemented A1)
  schemas.py          # BotEvent, BotReply
  idempotency.py      # DB or in-memory dedup (A1)
  adapters/
    slack.py          # signature verify, parse events (A1)
    telegram.py       # secret path, parse Update JSON (A1)
  outbound/
    slack_client.py   # chat.postMessage (A1)
    telegram_client.py
  handlers/
    echo.py           # A1: /ping → pong, else echo
    qa.py             # A2 → B1 (planned)
    link_payment.py   # C+ (planned)

core/
  bot_db.py           # bot_processed_events (A1)
  bot_auth.py         # allowlist (A3, planned)
  bot_qa.py           # retrieval + Gemini (B1, planned)
  bot_linking.py      # suggest contracts, write contract_ref (C+, planned)
```

**A1 idempotency:** Postgres `bot_processed_events` when `DATABASE_URL` is set; otherwise in-memory dedup (dev-only, resets on restart).

---

## Normalized schemas (contract for parallel work)

Agree these before Slack and Telegram adapters diverge.

**`BotEvent`**

- `platform`: `slack` | `telegram`
- `event_type`: `message` | `action` | `url_verification`
- `event_id`: Slack `event_id` or Telegram `update_id` (idempotency key)
- `user_id`, `chat_id`
- `text` (optional)
- `action_id` (optional), e.g. `link:tok_8f3a`
- `raw`: debug only; never send to Gemini

**`BotReply`**

- `text`
- `citations`: list of `drive_file_id` or file names (B1+)
- `ephemeral`: Slack-only
- `buttons`: optional; outbound layer maps to Block Kit or inline keyboard

Telegram `callback_data` is max 64 bytes—use short tokens and resolve via `bot_action_tokens` in the DB.

---

## Config (env / Secret Manager)

```bash
# Feature flags
BOT_PLATFORMS=slack,telegram   # comma-separated; omit to disable

# Slack
SLACK_SIGNING_SECRET=
SLACK_BOT_TOKEN=               # outbound only; never log

# Telegram
TELEGRAM_BOT_TOKEN=
TELEGRAM_WEBHOOK_SECRET=       # path segment, not the bot token
```

Local dev: ngrok (or similar) → Ingress; Slack/Telegram webhook URLs point at staging host.

---

## Database additions (A3 / C+)

```sql
-- Allowlist (A3)
CREATE TABLE bot_allowlist (
    platform TEXT NOT NULL,
    external_user_id TEXT NOT NULL,
    roles TEXT[] NOT NULL DEFAULT '{qa}',
    PRIMARY KEY (platform, external_user_id)
);

-- Idempotency (A1)
CREATE TABLE bot_processed_events (
    platform TEXT NOT NULL,
    event_id TEXT NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (platform, event_id)
);

-- Short-lived button state (C)
CREATE TABLE bot_action_tokens (
    token TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    payload JSONB NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL
);

-- Audit (A3+)
CREATE TABLE bot_audit_log (
    id BIGSERIAL PRIMARY KEY,
    platform TEXT,
    user_id TEXT,
    event_type TEXT,
    detail JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

---

## Platform notes

| Concern | Slack | Telegram |
|---------|-------|----------|
| Verification | `X-Slack-Signature` + timestamp | Secret path + optional IP allowlist |
| Handshake | `url_verification` + `challenge` | `setWebhook` to HTTPS URL |
| Buttons | Block Kit `action_id` | `callback_data` (use DB tokens) |
| Dedup | `event_id` | `update_id` |

---

## Security checklist

1. Verify raw body before JSON parse (Slack).
2. Insert `bot_processed_events` before handling; on conflict return `200`.
3. Allowlist before any catalog or linking action (A3+ for external users).
4. Redact tokens in logs; audit `user_id` + `event_type` only.
5. Prepend **“Not legal advice”** on Q&A replies (product requirement).
6. Never enable `DRIVE_DEBUG_SA_FALLBACK` in prod bot paths—that is ingest-only.

---

## Testing

| Layer | Focus |
|-------|--------|
| `adapters/slack.py` | Fixture payloads, valid/invalid signatures |
| `adapters/telegram.py` | Update JSON → `BotEvent`, wrong secret → 404 |
| `handlers/qa.py` | Mocked Vertex; B1 adds DB fixtures |
| `handlers/link_payment.py` | Token resolve + `payments` update |
| End-to-end | Signed POST in `tests/test_bot.py` |

Golden questions for B1 live in `tests/fixtures/` (TBD).

---

## Parallel setup (Slack vs Telegram)

| Phase | Slack team | Telegram team | Shared backend |
|-------|------------|---------------|----------------|
| A1 | Events URL + handshake | `setWebhook` | `schemas`, echo handler |
| A2 | — | — | `core/bot_qa.py` chat mode |
| A3 | — | — | `bot_allowlist`, router gate |
| B1 | — | — | Retrieval + citations |
| C–D | Interactivity URL | Inline keyboards | `bot_linking`, tokens |
| E | Prod allowlist | Prod allowlist | Ops hardening |

**First implementation target:** A1 (verify + echo + idempotency). No business logic in adapters.
