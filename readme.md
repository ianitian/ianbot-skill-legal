# exp-wonbot-fuzzy-vertex v0.1.1
**Base document** for product, engineering, DevOps, finance, and legal. Describes what we plan to build, how pieces connect, and what each group needs to decide or provide.

This repo powers **won-bot**—a new internal **Slack** bot for legal Q&A, payment linking, and related workflows. It is separate from the existing **ian-bot** Slack app (Drive alerts only). A **Telegram** adapter exists in the codebase for **local debugging only**; it is not part of the production UI.

The system is comprised of two key aspects: a **chatbot for internal use only** that handles legal Q&As for light topics, and, ultimately, **deep fact-based answers** by referring to signed contractual agreements from the company archive (**Google Drive**). The former is for general users within the organization; the latter is for **select allowlisted** users. Similarly, **financial data** (payments and disbursements) may ultimately be integrated to provide more detailed answers regarding signed agreements and contractual obligations.

Signed contracts (PDFs in Drive) and payment rows (finance Google Sheet) are indexed in a **searchable Indexed DB** (Postgres/AlloyDB). **Vertex AI Gemini** in our GCP project reads each contract once to extract fields and helps word answers—we are **not training a custom AI model**. When new files or rows appear, we **refresh the Indexed DB**; that is not “training.”

**Usage:** Low volume (back office and management, a few times per month). Architecture stays small: **wonbot-api** on **GKE**, **Indexed DB** in **AlloyDB** (PostgreSQL-compatible). **Scheduling uses Google Apps Script time-driven triggers only**—no dedicated cron VM, Cloud Scheduler, or Kubernetes CronJob required.

FYI / nomenclature:

- **Indexed DB** — company-controlled Postgres/AlloyDB where extracted PDF text and fields (plus synced sheet rows) are stored and indexed for contract Q&A. Not a public AI training dataset.
- **won-bot** — new **Slack** bot for legal Q&A, payment linking, and scripted FAQs (this repo). Launched as its own app; we are **not** extending **ian-bot**.
- **ian-bot** — existing Slack app for Drive alerts and related messages only. Stays as-is; contract Q&A and linking live on **won-bot**.
- **wonbot-api** — backend FastAPI service (ingest, sync, webhook handlers) deployed on GKE; same deployment serves **won-bot** Slack webhooks.
- **Telegram (dev only)** — optional adapter for local smoke tests and debugging (`bot/adapters/telegram.py`, polling mode). Not shipped as a production channel for won-bot.

---

## For finance

The Google Sheet the finance team uses to track expenses may be incorporated in a later design phase. That may require additional columns—e.g. a **URL or Drive file ID** linking each payment row to the relevant signed agreement—so payment data can sync into the **Indexed DB** and support richer answers about deals and obligations.

---

## For legal and compliance

**Future feature (not live today):** For allowlisted **deep contract Q&A**, signed PDFs remain in **Google Drive** (source of truth). **wonbot-api** will ingest each file once through **Vertex AI Gemini** in our GCP project, extract key fields into the **Indexed DB**, and answer only from that indexed data, with citations and “not found” when nothing matches. This is **not legal advice**; it is internal decision-support with a disclaimer. Retention and access rules will be set before go-live.

---

## For DevOps and engineering

**Stack note:** Org standard is **GKE + AlloyDB** (not Cloud Run + Cloud SQL). Same FastAPI app and endpoints; different deploy and database targets.

### Services map (minimal footprint)

We want **one GKE Deployment (`wonbot-api`)**, **AlloyDB** for the **Indexed DB**, and **Apps Script for all triggers and schedules** (no dedicated cron VM).

```text
┌──────────────────────────────────────────────────────────────────┐
│  Google Workspace (no servers we manage)                         │
│                                                                  │
│  • Apps Script — Drive watch, Slack alerts, timed triggers       │
│  • Drive       — signed PDFs (folder tree)                       │
│  • Sheet       — payments + contract_ref                         │
└────────────────────────────┬─────────────────┬───────────────────┘
                             │                 │
                    HTTPS    │                 │  Google APIs
                    (poke)   │                 │  (Drive / Sheets)
                             v                 v
              ┌──────────────────────────┐   ┌──────────────────────────┐
              │  GKE: wonbot-api         │   │  Vertex AI Gemini        │
              │  (Deployment + Ingress)  │   │                          │
              │                          │   │                          │
              │  POST /ingest            │──>│  PDF extraction          │
              │  POST /sync/sheet        │   │  Answer wording (later)  │
              │  GET  /health            │   │                          │
              │  later: /slack/events    │   │                          │
              └────────────┬─────────────┘   └──────────────────────────┘
                           │
                           │  SQL (PostgreSQL wire protocol)
                           v
              ┌──────────────────────────┐
              │  AlloyDB                 │
              │                          │
              │  contracts, payments,    │
              │  aliases (schema TBD)    │
              └──────────────────────────┘

              ┌──────────────────────────┐
              │  Slack                   │
              │                          │
              │  • Webhook — ian-bot     │
              │    Drive alerts (today)  │
              │  • Events API → Ingress  │
              │    won-bot Q&A + linking │
              └──────────────────────────┘
```

| Component | Role | Hosted by |
|-----------|------|-----------|
| **Apps Script** | New PDF → Slack alert + `POST /ingest`; optional daily `POST /sync/sheet` | Google |
| **GKE (`wonbot-api`)** | Ingest PDF, sync sheet, Slack interactivity, Q&A logic | GCP |
| **AlloyDB** | **Indexed DB** (contracts, payments)—PostgreSQL-compatible; schema TBD | GCP |
| **Secret Manager** | API keys, DB URL, ingest secret, Slack secrets | GCP |
| **Service account** | Robot Google identity for Drive + Sheet API access (via workload identity on GKE) | GCP |
| **Vertex AI Gemini** | Extract fields from PDF; compose answers from Indexed DB | GCP |
| **ian-bot (Slack)** | Drive alerts only (unchanged) | Slack |
| **won-bot (Slack)** | Q&A, payment linking, FAQ (this repo) | Slack |

### Ingest service (wireframe)

**Not** the Slack bot. A small **Python (FastAPI)** API that indexes extracted data into the **Indexed DB** (Postgres).

| Endpoint | Called by | Purpose |
|----------|-----------|---------|
| `POST /ingest` | Apps Script after new PDF | Body: `drive_file_id`. Download PDF → Gemini → upsert contract. |
| `POST /sync/sheet` | Apps Script **daily** time-driven trigger | Copy finance sheet → AlloyDB (including `contract_ref`). |
| `GET /health` | Monitoring | Liveness check. |

**`POST /ingest` steps:** validate shared secret header → download PDF via service account → skip if not PDF or unchanged → Gemini JSON extraction → upsert by `drive_file_id` → return 200 or error.

**Security:** `X-Ingest-Secret` (or similar) on `/ingest` and `/sync/sheet`; not open anonymous internet. Real values in **Secret Manager**, not in this public repo.

**Later (same `wonbot-api` Deployment):** **won-bot** Slack Events API + interactivity for payment linking and Q&A.

### Scheduling: Apps Script only (no cron VM)

We do **not** need a dedicated cron VM, **Cloud Scheduler**, or a **Kubernetes CronJob** for this project. **Google Apps Script time-driven triggers** are the chosen approach: they call our GKE Ingress URLs on a schedule; GKE does the real work.

| Job | Trigger (Apps Script) |
|-----|------------------------|
| New PDF alert + index | Recurring trigger → `checkForNewFiles` → Slack + `pokeIngestWebhook` → `POST /ingest` |
| Daily sheet → AlloyDB | **Daily** time-driven trigger → `syncSheetToBackend()` → `POST /sync/sheet` |
| Optional Drive catch-up | **Weekly** time-driven trigger → `reconcileDrive()` → rescan endpoint (if we add one) |

**Apps Script** = doorbell **and alarm clock** (alerts + schedules). **GKE (`wonbot-api`)** = kitchen (Gemini, AlloyDB, Slack handlers).

**Why this is enough:** Each scheduled run only needs to `UrlFetchApp.fetch` one HTTPS endpoint—well within Apps Script limits. No separate cron infrastructure to deploy or pay for.

**Optional later (only if platform team requires GCP-native cron):** Cloud Scheduler or a K8s CronJob hitting the same Ingress URLs—**not planned for v1**; pick one mechanism total if we ever add a second.

### Google Cloud pieces (plain English)

#### GKE (Google Kubernetes Engine)

Runs our application as containers in a cluster. Expose **HTTPS** via **Ingress** (org standard hostname + TLS).

- **Deployment** `wonbot-api` — FastAPI app from the same Docker image as local dev.
- **Service** (ClusterIP) — routes traffic to pods.
- **Ingress** — public URL for Apps Script (`POST /ingest`) and later Slack Events API.
- Low traffic: often **1 replica** is enough; use platform templates (Helm/Kustomize) if available.
- **Probes** — Kubernetes `liveness` / `readiness` on `GET /health`.

Apps Script Script Properties use the **Ingress base URL** (e.g. `https://wonbot-api.<your-domain>/ingest`), not `*.run.app`.

#### AlloyDB

Managed **PostgreSQL-compatible** database for the **Indexed DB**. Separate from GKE; connect from pods over **private networking** (VPC / Private Service Connect / AlloyDB Auth Proxy—per platform team).

- Same SQL and drivers as Postgres; **schema design is deferred**.
- Connection string in Secret Manager → pod env `DATABASE_URL`.

#### Secret Manager

A **vault** for sensitive strings (database password, ingest webhook secret, Slack signing secret, bot tokens). Vertex Gemini uses **workload identity** in prod—no API key in pods. Mounted into pods via **External Secrets Operator** or your org’s pattern. **Do not commit secrets to this public GitHub repo.**

| Secret (example name) | Used for |
|------------------------|----------|
| `ingest-webhook-secret` | Apps Script → `/ingest` and `/sync/sheet` auth |
| `database-url` | Postgres connection |
| `slack-signing-secret` | Verify Slack interactive payloads |
| `slack-bot-token` | Post messages / update sheet via API (later) |

Apps Script uses **Script Properties** for the ingest URL and the same shared secret (Google-hosted, not in Git).

#### Service account

A **robot Google account** for programs (not humans), e.g. `wonbot@….iam.gserviceaccount.com`.

- Bind to GKE pods via **workload identity** (Kubernetes service account → GCP service account)—preferred over JSON key files in the cluster.
- **Share** the contract Drive folder and finance sheet with this email (like sharing with a colleague).
- **Never** commit the JSON key file to the public repo.

#### Other GCP terms (reference)

| Term | Meaning |
|------|---------|
| **GCP project** | Billing + container for GKE, AlloyDB, secrets |
| **GKE namespace** | Where `wonbot-api` Deployment lives (e.g. `wonbot`) |
| **Ingress / Gateway** | Public HTTPS entry to the API |
| **Region** | Where cluster and AlloyDB run (e.g. `us-central1`) |
| **IAM** | Who can deploy, who can read secrets |
| **Cloud Scheduler** | Not used for v1 (Apps Script handles schedules). Optional GCP alternative if policy requires it |
| **Vertex AI** | Gemini inside our GCP project (`GEMINI_BACKEND=vertex`); required for confidential PDFs |

### Slack: two connection types

| Pattern | Used for | Points to |
|---------|----------|-----------|
| **Incoming webhook** | **ian-bot** “new file” Drive alerts | Slack URL; Apps Script posts JSON |
| **Events API + interactivity** | **won-bot** payment link buttons, Q&A | **Ingress** HTTPS on GKE (Slack signing secret) |

### DevOps setup checklist

- [ ] GCP **project** + **GKE** cluster (or shared cluster) + namespace for `wonbot-api`.
- [ ] **AlloyDB** instance (when schema is ready); private connectivity from GKE per platform standard.
- [ ] **Deployment**, **Service**, **Ingress** (+ TLS); `GET /health` probes configured.
- [ ] **Workload identity** — GCP service account for Drive/Sheet; share contract folder + finance sheet (write for `contract_ref`).
- [ ] **Secret Manager** entries; sync to pods (External Secrets or org pattern).
- [ ] Provide **Ingress base URL** for Apps Script Script Properties (`/ingest`, `/sync/sheet`).
- [ ] Enable **Vertex AI** API, billing, and IAM (`roles/aiplatform.user` on ingest SA).
- [ ] Apps Script **daily** time-driven trigger for `syncSheetToBackend` → `POST /sync/sheet` (no Cloud Scheduler / CronJob for v1).
- [ ] Public repo: no real tokens in Git; rotate any secrets ever pasted into chat or commits.

### Suggested DevOps one-liner

> **GKE Deployment** `wonbot-api` behind **Ingress**; **AlloyDB** as the **Indexed DB** (Postgres); **Apps Script** for Drive alerts, **timed schedules**, and HTTP pokes to ingest/sync; **Secret Manager** + **workload identity** for Drive/Sheet; **ian-bot** webhook for Drive alerts; **won-bot** via **Ingress** for Q&A and linking. **No cron VM, Cloud Scheduler, or CronJob.**

---

## Slack: ian-bot vs won-bot

| | **ian-bot (unchanged)** | **won-bot (this repo)** |
|--|-------------------------|-------------------------|
| **Role** | Alerts when new signed PDFs land in Drive (via Apps Script). | (1) **Payment linking**—buttons to fill `contract_ref` on the sheet. (2) **Contract Q&A**—questions about deals and payments using **Indexed DB** + Gemini. (3) Scripted FAQ and echo (shipped in dev). |
| **Who sees it** | Whatever channels/users already get Drive alerts. | **Back office and management only** (allowlist—not company-wide). |
| **Platform** | Slack (incoming webhook). | Slack (Events API + interactivity). |

**Decision:** Contract Q&A and payment linking ship on **won-bot**, a new Slack app—not by extending **ian-bot**. **ian-bot** keeps Drive alerts only.

Access control: allowlisted Slack user IDs for **won-bot**. Others may still get Drive alerts from **ian-bot**; they should not get Q&A or linking unless added to the allowlist.

---

## What we’re building (big picture)

| Piece | What it does |
|--------|----------------|
| **Google Drive** | Official home for signed PDFs (inbox + subfolders). **File ID** stays the same when moved between folders. |
| **Finance Google Sheet** | Payment log + new **`contract_ref`** column (via Slack linking). |
| **Apps Script** | Drive alerts via **ian-bot**; poke ingest on new PDF; **daily** time-driven trigger for sheet sync. |
| **GKE (`wonbot-api`)** | Index PDFs, sync sheet; **won-bot** webhook handlers (via Ingress). |
| **AlloyDB** | PostgreSQL-compatible **Indexed DB** for Q&A and payment totals. |
| **Vertex AI Gemini** | Extract contract fields; write answers from Indexed DB only. |

```text
  Drive (PDFs)
       |
       v
  Apps Script ----alert----> ian-bot (existing webhook)
       |
       +---- POST /ingest ---> GKE (wonbot-api) + Gemini ---> AlloyDB

  Finance Sheet (+ contract_ref)
       |
       |  "Link to contract" -> won-bot buttons -> contract_ref filled
       v
  Apps Script (daily trigger) ---> POST /sync/sheet ---> AlloyDB

  won-bot (Slack) ---> Ingress (GKE) ---> AlloyDB + Gemini (Q&A, allowlisted)
```

---

## Apps Script (existing + planned)

**Today:** `checkForNewFiles` scans the Drive folder, sends Slack alert for new files.

**Added (foundation):** `pokeIngestWebhook(file)` after each alert—`POST` to GKE Ingress `/ingest` with `drive_file_id`, using URL and secret from **Script Properties** (skips if URL not set).

**Planned triggers:**

| Trigger | Function | Action |
|---------|----------|--------|
| Every N minutes (existing) | `checkForNewFiles` | Slack alert + `/ingest` |
| Daily | `syncSheetToBackend` | `POST /sync/sheet` |
| Weekly (optional) | `reconcileDrive` | Catch-up scan if needed |
| On sheet edit (later) | `onLinkCheckbox` | Start Slack linking for row |

**Note:** Current script lists **direct children** of the root folder only; files only in subfolders may need a later recursive scan or ingest poke when moved—file ID still stable when moved within the tree.

---

## Project to-do

Ship order follows the **bot launch ladder** (A→E in [bot/README.md](bot/README.md)) on top of ingest + **Indexed DB**. ✅ = shipped in repo today.

### Infrastructure — ingest & Indexed DB

**Phase 0 — Setup and access**

- [ ] GCP project + **GKE** + **AlloyDB** + **Secret Manager** + **service account** (workload identity).
- [x] **Indexed DB** — local Postgres via Docker + `schema.sql` (dev); **AlloyDB** for prod TBD.
- [x] Drive **root folder ID** + service account access to contract tree (Apps Script, local `.env`, private ops notes—not in this public repo).
- [ ] Apps Script Script Properties: ingest URL + secret in **prod** (pattern in `docs/apps-script.md`).
- [x] **won-bot** as new Slack app (not extending **ian-bot**) for Q&A + linking.
- [ ] Decide **won-bot** link message destination (channel vs DM).

**Phase 1 — Indexed DB schema**

- [x] Tables: **contracts**, **payments**, **aliases**, `ingest_log`, `bot_processed_events` (`db/schema.sql`).
- [x] **Drive file ID** as stable contract key; local dev setup (Docker Compose, `scripts/wipe-local-db.sh`, `docs/DEV.md`).
- [ ] Populate **aliases** for golden questions; verify retrieval on 2–3 real contracts.

**Phase 2 — Ingest on `wonbot-api`**

- [x] `GET /health`, `POST /ingest`, `POST /sync/sheet` (sheet endpoint stub).
- [x] Drive download (SA / ADC); PDF only; idempotent contract upsert.
- [x] Vertex Gemini extraction → Indexed DB (local Postgres today).
- [ ] Real **sheet sync** + `contract_ref` (Sheets API; finance sheet ID + column mapping in private ops).
- [ ] Verify payment totals vs sheet for 2–3 linked contracts.
- [ ] Deploy to **GKE** (Deployment + Ingress); prod Apps Script `pokeIngestWebhook` + debounce duplicate file IDs.
- [x] Keep ian-bot Drive alerts (Apps Script).
- [ ] **Daily** Apps Script trigger → `POST /sync/sheet`.
- [ ] Optional: ingest status in Slack alert text.

---

### Bot launch ladder (A → E)

**A1 — Webhooks + echo** ✅

- [x] Adapters: Slack signature verify (`bot/adapters/slack.py`); Telegram adapter for **local debug only** (`bot/adapters/telegram.py`).
- [x] Routes: `/webhooks/slack/events`, `/webhooks/slack/interactions` (stub); `/webhooks/telegram/{secret}` (dev/debug).
- [x] Echo: `ping`, `hello`, `about`, `version`; idempotency via `bot_processed_events` or in-memory fallback.
- [x] Outbound: `slack_client` (prod); `telegram_client` + polling mode for local debugging only.

**A1.5 — FAQ layer** ✅

- [x] `bot/content/faqs.yaml`, `core/bot_faq.py` (rapidfuzz), `handlers/faq.py`.
- [x] Dispatch: echo → FAQ → about fallback; disclaimer prefix; `handler` + metadata on `BotReply`.

**A1.6 — Counsel observer feed**

- [ ] `notify_observers()` after `dispatch_message` (fire-and-forget; `bot/observers/`).
- [ ] Dev: optional audit copies to `TELEGRAM_OBSERVER_CHAT_ID` (Telegram debug channel only).
- [ ] Live: separate audit path → Slack channel via **won-bot** or dedicated audit webhook (`SLACK_AUDIT_*` env).

**A2 — Vertex conversational chat (no Indexed DB)**

- [ ] `handlers/qa.py` + `core/bot_qa.py` chat mode (reuse `gemini_client`; prompt separate from PDF extract).
- [ ] Wire into dispatch; system prompt: **Indexed DB not connected**—do not invent clauses.
- [ ] Small internal test audience before wider rollout.

**A3 — Allowlist + audit**

- [ ] `core/bot_auth.py` + `bot_allowlist` table; router gate before handlers.
- [ ] Strangers get polite access-denied; allowlist back office + management (Slack user IDs).
- [ ] Audit log policy: `user_id` + handler route (complements A1.6 observer).

**B1 — Indexed DB based Q&A**

- [ ] Retrieval from `contracts` / `aliases` in `core/bot_qa.py`; citations on `BotReply`.
- [ ] `handlers/qa.py` grounded answers; “not found” when Indexed DB has no match.
- [ ] Golden questions in `tests/fixtures/`; finance/legal UAT on sample deals.
- [ ] Prod bot on GKE Ingress (same FastAPI deployment as ingest).

**C — Payment-link buttons**

- [ ] `core/bot_linking.py` — suggest 3–5 contracts for a payment row.
- [ ] `handlers/link_payment.py` + `bot_action_tokens` (short `callback_data` tokens).
- [ ] Slack Block Kit buttons; interactivity handler writes **`contract_ref`** on sheet.
- [ ] Finance allowlist for link actions only.

**D — Sheet-triggered outbound**

- [ ] Finance sheet: **`contract_ref`** / link-status columns (see **For finance**); URL or Drive file ID per row.
- [ ] Apps Script `onLinkCheckbox` (or equivalent) → **won-bot** posts link options in Slack.
- [ ] Document finance **sheet ID** + column mapping (private ops).

**E — Hardening & go-live**

- [ ] Rate limits; redact tokens in logs.
- [ ] Monitoring, DB backups, disclaimer policy, retention rules.
- [ ] Prod allowlist on Slack.
- [ ] Recursive Drive scan or subfolder catch-up (optional).
- [ ] Later: full-text search, OCR, optional web UI.

---

## Suggested build order

1. ~~Ingest + Indexed DB (local)~~ ✅ → prod GKE + Apps Script poke + sheet sync.
2. ~~**A1** + **A1.5** (echo + FAQ)~~ ✅ → **A1.6** observer → **A2** Vertex chat → **A3** allowlist.
3. **B1** Indexed DB Q&A (citations) for allowlisted users.
4. **C** + **D** payment linking (`contract_ref`) + sheet-triggered bot messages.
5. **E** golden tests, monitoring, go-live.

---

## Decisions still open

| Topic | Choices | Decision |
|--------|---------|----------|
| Gemini | **Vertex AI** in GCP (`GEMINI_BACKEND=vertex`); legacy AI Studio key path in code for local experiments only | _Vertex for prod_ |
| GKE / AlloyDB | Namespace, Ingress host, AlloyDB instance (platform template?) | _TBD_ |
| Sheet sync schedule | **Apps Script daily trigger** (no Cloud Scheduler / CronJob for v1) | _decided_ |
| Slack bot | Extend **ian-bot** vs new **won-bot** app | _**won-bot** (new app)_ |
| Q&A / linking users | Allowlist: back office + management | _TBD_ |
| Link messages | Finance channel vs DM | _TBD_ |

---

## IDs to fill in later

> **Warning:** This repo is set to **public**. Do **not** enter actual IDs, tokens, or other real values in this file or in committed config. Keep real values in private notes, a password manager, **Secret Manager**, or **Apps Script Script Properties** only.

| What | ID |
|------|-----|
| Drive root folder | |
| Finance sheet | |
| Slack workspace | |
| ian-bot (Slack app — Drive alerts) | |
| won-bot (Slack app — Q&A + linking) | |
| GCP project | |
| Ingress URL (wonbot-api) | |
| AlloyDB instance | |
| GKE cluster / namespace | |

---

## Code folders

```text
bot/           # won-bot Slack webhooks; Telegram adapter for local debug only
ingest/        # FastAPI app (wonbot-api): /health, /ingest, /sync/sheet
core/          # config, auth, extract, db
db/            # schema.sql
docs/          # DEV.md, apps-script notes
deploy/        # GKE manifests (later)
tests/         # API smoke tests
```

**Local dev:** see [docs/DEV.md](docs/DEV.md).

---

## Versioning

**Current version:** `0.1.0` (also in [`VERSION`](VERSION), `pyproject.toml`, `readme.md` title, and `GET /health` → `version`).

| Bump | When | How |
|------|------|-----|
| **Patch** `0.0.1` → `0.0.2` | Every routine revision commit | Auto: enable [`.githooks/pre-commit`](.githooks/pre-commit) via `./scripts/setup-git-hooks.sh`, **or** run `./scripts/commit-revision.sh -m "your message"` |
| **Minor** `0.1.0` → `0.2.0` | Only when you explicitly want a minor release | `python3 scripts/bump_minor.py`, update changelog, then `git commit` (use `--no-verify` if hooks would patch-bump again) |
| **Major** `1.0.0` → `2.0.0` | Only when you explicitly want a major release | `python3 scripts/bump_major.py`, update changelog, then `git commit` |

**Commit messages:** include the version tag, e.g. `feat(v0.0.1): …` or `fix(v0.0.2): …`.

**Skip auto patch bump** (rare): `git commit --no-verify`.

After enabling hooks, each `git commit` bumps patch and stages `VERSION`, `pyproject.toml`, `ingest/api.py`, and the `readme.md` title (`# exp-wonbot-fuzzy-vertex vX.X.X`) before the commit is created—add changelog notes in the same commit when you can.

---

## Changelog

### v0.1.0

- FAQ layer (A1.5): rapidfuzz matching against `bot/content/faqs.yaml`; toggle via `BOT_FAQ_ENABLED`.
- Dispatch chain: echo (ping/hello/about/version) → FAQ → about fallback; `BotReply` carries `handler` + metadata for future audit observer.
- Echo `about` / `version` and unknown questions return a verbose build summary (handler status, Indexed DB based Q&A line).
- Six seed FAQs (capabilities, limitations, how-to-ask, legal clearance, data handling, ping help) with global WIP disclaimer prefix.
- Counsel observer direction documented (dev: optional Telegram debug feed; live: **won-bot** Q&A + audit to Slack) — not implemented.
- Reader-facing docs use **Indexed DB** for the Postgres/AlloyDB store of extracted PDF fields.
- `GET /health` adds `bot_faq_enabled`, `bot_faq_configured`, `bot_faq_count`. Vertex chat (A2) and Indexed DB based Q&A (B1) remain on hold.

### v0.0.8

- Telegram adapter (local debug): group gating via `TELEGRAM_ALLOWED_CHAT_IDS` + `TELEGRAM_BOT_USERNAME`; not a production won-bot channel.
- Group messages accepted via `@mention`, `text_mention` (picker), or `/command@bot`; echo replies `pong` / `Hello, name` / toddler fallback.
- Outbound API errors logged without failing the webhook response.

### v0.0.7

- Bot A1: Slack webhook adapters (`/webhooks/slack/events`, `/webhooks/slack/interactions` stub); Telegram route added for local debugging.
- Echo handler: `ping` / `/ping` → `pong`; other text → `You said: …`. Idempotency via `bot_processed_events` or in-memory fallback.
- `GET /health` adds `bot_platforms`, `bot_slack_configured`, `bot_telegram_configured`. See `bot/README.md` and `docs/DEV.md`.

### v0.0.5

- Vertex Gemini extraction: `VertexGeminiClient` using `google-genai` with `vertexai=True`; config via `GOOGLE_CLOUD_PROJECT` and `GOOGLE_CLOUD_LOCATION`.
- `gemini_configured` and ingest error messages are backend-aware (studio vs vertex); `GET /health` includes `gemini_backend`.
- Docs: Vertex setup in `docs/DEV.md` and `.env.example`.

### v0.0.4

- Gemini extraction (dev): AI Studio API-key backend (`core/gemini_client.py`) wired into `core/extract.py`.
- `/ingest` now returns `status: error` when Gemini is enabled but missing Drive bytes or API key; `GET /health` includes `gemini_configured`.
- **Security note:** early AI Studio API-key path for local testing only; production uses **Vertex AI** after legal/IT sign-off.

### v0.0.3

- `/ingest` downloads contract PDFs from Drive in memory via service account (`core/drive.py`); `GET /health` reports `drive_configured`.
- Google client libraries added to project dependencies; Drive download errors return `status: error` with HTTP 200 for Apps Script pokes.

### v0.0.2

- Local dev: `scripts/wipe-local-db.sh` full **Indexed DB** reset (local Postgres via Docker volume + `schema.sql`); documented in `docs/DEV.md`.
- Phase 0 helpers: `scripts/test_drive_sa.py` and `test_drive_sa2.py` to validate service account folder list and PDF download.
- `.gitignore` rules for GCP service account JSON key downloads (keep keys out of the public repo).

### v0.0.1

- Initial **wonbot-api** scaffold: FastAPI (`/health`, `/ingest`, `/sync/sheet`), stub Gemini extraction, local **Indexed DB** (Postgres schema) via Docker Compose.
- Docs for DevOps (GKE + AlloyDB), finance (`contract_ref`), legal, and Apps Script ingest poke.
- API smoke tests; versioning scripts and optional git hook for patch bumps.
