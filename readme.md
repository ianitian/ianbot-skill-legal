# ianbot-skill-legal v0.0.7
**Base document** for product, engineering, DevOps, finance, and legal. Describes what we plan to build, how pieces connect, and what each group needs to decide or provide.

Upgrade plans for Slack bot, "ian-bot", that will reference and answer user queries based on:

- **Signed contracts** (PDFs in a Google Drive folder tree), and
- **Payments** (rows in a finance Google Sheet).

The system keeps a **searchable catalog in Postgres** (a normal database) and uses **Google Gemini** to read contracts once and to write answers—we are **not training a custom AI model**. When new files or rows appear, we **refresh the catalog**; that is not “training.”

**Usage:** Low volume (back office and management, a few times per month). Architecture stays small: **ianbot-api** on **GKE**, catalog in **AlloyDB** (PostgreSQL-compatible). **Scheduling uses Google Apps Script time-driven triggers only**—no dedicated cron VM, Cloud Scheduler, or Kubernetes CronJob required.

FYI / nomenclature:

- Our existing bot is called **ian-bot** (Drive alerts and related messages). Contract Q&A and payment linking may live on **ian-bot** (extended) or on a **new** Slack app—we have not decided yet (see below).
- All backend service names will be called ianbot-api.
- This repo is called ianbot-skill-legal, to "add legal skill". If there are other feature ideas, they will likely be called "ianbot-skill-XXX".

---

## For finance

### New column: `contract_ref`

The finance Google Sheet already has payment fields (date, amount, payee, etc.). We will add a **new column** called **`contract_ref`**.

| What | Explanation |
|------|-------------|
| **What it holds** | A link to the signed contract in Drive (URL), or the Drive **file ID** for that PDF. |
| **Who fills it** | Usually **not typed by hand**. After finance marks a row for linking, **ian-bot** (or our backend) posts options in Slack; finance **clicks** the right contract, and the system **writes this column**. |
| **Why we need it** | Payments and contracts are separate lists. This column is the official “this payment belongs to **that** contract” so totals and Q&A stay correct. |
| **Related columns** | Link **status** (e.g. needs link / linked / none) and a **“Link to contract”** checkbox to start the Slack flow. |

Until `contract_ref` is set for a row, the assistant should treat that payment as **not linked** (no reliable “how much paid on this deal” for that row).

### What we need from finance

- [x] Agree to the new columns above on the existing payment sheet.
- [ ] Use the **“Link to contract”** flow in Slack when prompted (pick from suggested contracts; do not skip if the payment belongs to a deal).
- [ ] Optionally add a **`contract_ref`** on historical rows we care about (can be phased in).
- [ ] Confirm column names for date, amount, payee, memo so engineering can map the sheet sync.

### Payment linking flow (Slack)

1. Finance enters a payment row as usual.
2. They check **“Link to contract”** (or set status to “needs link”).
3. The system suggests **a few likely contracts** in Slack (buttons).
4. Finance picks one (or “None of these”).
5. **`contract_ref`** is written on that row; a nightly sync copies it into the catalog database.

**Rules:** Always confirm in Slack—no silent auto-linking (wrong link = wrong payment totals).

---

## For legal and compliance

### What the system does with contract PDFs

- PDFs stay in **Google Drive** (source of truth). We do not replace your filing process.
- A backend service **downloads** a PDF when it is new or updated, sends text/content to **Google Gemini** to extract structured fields (party names, dates, summary, “watch outs”), and stores **extracted text and fields** in a company-controlled **Postgres** database—not in a public AI training dataset (confirm exact terms with IT for **Vertex AI** vs **AI Studio API key**).
- The Slack assistant answers using **that catalog only** and must cite sources; it should say “not found” rather than invent clauses.

### What this is not

- **Not legal advice.** Decision-support for internal lookup only; disclaimer in the bot.
- **Not a replacement** for reading originals on important decisions.
- **Not custom model training** on your contracts.

### Questions for legal / IT to close

- [ ] Is **Vertex AI** (Gemini inside our GCP project) required for confidential PDFs, or is an API key acceptable?
- [ ] Data retention: how long may we keep extracted fields and query logs?
- [ ] Who may access the bot (planned: **back office + management** allowlist only)?

### Gemini extraction — Studio (dev) and Vertex (prod)

**v0.0.4+ enables real Gemini extraction** when `GEMINI_ENABLED=true`.

| Backend | Env | Use |
|---------|-----|-----|
| `studio` | `GEMINI_API_KEY` | Local dev / validation (AI Studio) |
| `vertex` | `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION` + ADC | Production ingest inside GCP |

**v0.0.5 implements the Vertex client** (`VertexGeminiClient` via `google-genai` with `vertexai=True`). Flip `GEMINI_BACKEND=vertex` once Vertex AI API, billing, and IAM (`roles/aiplatform.user` on the ingest SA) are ready.

**Risks not fully verified yet:**

- AI Studio API terms and data retention are **not signed off** by legal for confidential signed contracts.
- API keys in local `.env` are fine for dev only; **production must not** rely on long-lived Studio keys in the repo or pods.
- Vertex legal/IT approval for confidential PDFs is still an open question (see checklist above).

Until Vertex is approved and enabled in GCP, treat AI Studio extraction as **local/dev validation only**, not production-ready for sensitive PDFs.

---

## For DevOps and engineering

**Stack note:** Org standard is **GKE + AlloyDB** (not Cloud Run + Cloud SQL). Same FastAPI app and endpoints; different deploy and database targets.

### Services map (minimal footprint)

We want **one GKE Deployment (`ianbot-api`)**, **AlloyDB** for the catalog, and **Apps Script for all triggers and schedules** (no dedicated cron VM).

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
              │  GKE: ianbot-api         │   │  Gemini API (Google)     │
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
              │    alerts (today)        │
              │  • Events API → Ingress  │
              │    linking + Q&A (later) │
              └──────────────────────────┘
```

| Component | Role | Hosted by |
|-----------|------|-----------|
| **Apps Script** | New PDF → Slack alert + `POST /ingest`; optional daily `POST /sync/sheet` | Google |
| **GKE (`ianbot-api`)** | Ingest PDF, sync sheet, Slack interactivity, Q&A logic | GCP |
| **AlloyDB** | Catalog (contracts, payments)—PostgreSQL-compatible; schema TBD | GCP |
| **Secret Manager** | API keys, DB URL, ingest secret, Slack secrets | GCP |
| **Service account** | Robot Google identity for Drive + Sheet API access (via workload identity on GKE) | GCP |
| **Gemini** | Extract fields from PDF; compose answers from catalog | Google |
| **ian-bot (Slack)** | Alerts today; may add Q&A + linking later | Slack |

### Ingest service (wireframe)

**Not** the Slack bot. A small **Python (FastAPI)** API that fills Postgres.

| Endpoint | Called by | Purpose |
|----------|-----------|---------|
| `POST /ingest` | Apps Script after new PDF | Body: `drive_file_id`. Download PDF → Gemini → upsert contract. |
| `POST /sync/sheet` | Apps Script **daily** time-driven trigger | Copy finance sheet → AlloyDB (including `contract_ref`). |
| `GET /health` | Monitoring | Liveness check. |

**`POST /ingest` steps:** validate shared secret header → download PDF via service account → skip if not PDF or unchanged → Gemini JSON extraction → upsert by `drive_file_id` → return 200 or error.

**Security:** `X-Ingest-Secret` (or similar) on `/ingest` and `/sync/sheet`; not open anonymous internet. Real values in **Secret Manager**, not in this public repo.

**Later (same `ianbot-api` Deployment):** Slack Events API + interactivity for payment linking and Q&A.

### Scheduling: Apps Script only (no cron VM)

We do **not** need a dedicated cron VM, **Cloud Scheduler**, or a **Kubernetes CronJob** for this project. **Google Apps Script time-driven triggers** are the chosen approach: they call our GKE Ingress URLs on a schedule; GKE does the real work.

| Job | Trigger (Apps Script) |
|-----|------------------------|
| New PDF alert + index | Recurring trigger → `checkForNewFiles` → Slack + `pokeIngestWebhook` → `POST /ingest` |
| Daily sheet → AlloyDB | **Daily** time-driven trigger → `syncSheetToBackend()` → `POST /sync/sheet` |
| Optional Drive catch-up | **Weekly** time-driven trigger → `reconcileDrive()` → rescan endpoint (if we add one) |

**Apps Script** = doorbell **and alarm clock** (alerts + schedules). **GKE (`ianbot-api`)** = kitchen (Gemini, AlloyDB, Slack handlers).

**Why this is enough:** Each scheduled run only needs to `UrlFetchApp.fetch` one HTTPS endpoint—well within Apps Script limits. No separate cron infrastructure to deploy or pay for.

**Optional later (only if platform team requires GCP-native cron):** Cloud Scheduler or a K8s CronJob hitting the same Ingress URLs—**not planned for v1**; pick one mechanism total if we ever add a second.

### Google Cloud pieces (plain English)

#### GKE (Google Kubernetes Engine)

Runs our application as containers in a cluster. Expose **HTTPS** via **Ingress** (org standard hostname + TLS).

- **Deployment** `ianbot-api` — FastAPI app from the same Docker image as local dev.
- **Service** (ClusterIP) — routes traffic to pods.
- **Ingress** — public URL for Apps Script (`POST /ingest`) and later Slack Events API.
- Low traffic: often **1 replica** is enough; use platform templates (Helm/Kustomize) if available.
- **Probes** — Kubernetes `liveness` / `readiness` on `GET /health`.

Apps Script Script Properties use the **Ingress base URL** (e.g. `https://ianbot-api.<your-domain>/ingest`), not `*.run.app`.

#### AlloyDB

Managed **PostgreSQL-compatible** database for the catalog. Separate from GKE; connect from pods over **private networking** (VPC / Private Service Connect / AlloyDB Auth Proxy—per platform team).

- Same SQL and drivers as Postgres; **schema design is deferred**.
- Connection string in Secret Manager → pod env `DATABASE_URL`.

#### Secret Manager

A **vault** for sensitive strings (Gemini key, database password, ingest webhook secret, Slack signing secret, bot tokens). Mounted into pods via **External Secrets Operator** or your org’s pattern. **Do not commit secrets to this public GitHub repo.**

| Secret (example name) | Used for |
|------------------------|----------|
| `ingest-webhook-secret` | Apps Script → `/ingest` and `/sync/sheet` auth |
| `gemini-api-key` | PDF extraction and answers |
| `database-url` | Postgres connection |
| `slack-signing-secret` | Verify Slack interactive payloads |
| `slack-bot-token` | Post messages / update sheet via API (later) |

Apps Script uses **Script Properties** for the ingest URL and the same shared secret (Google-hosted, not in Git).

#### Service account

A **robot Google account** for programs (not humans), e.g. `ianbot@….iam.gserviceaccount.com`.

- Bind to GKE pods via **workload identity** (Kubernetes service account → GCP service account)—preferred over JSON key files in the cluster.
- **Share** the contract Drive folder and finance sheet with this email (like sharing with a colleague).
- **Never** commit the JSON key file to the public repo.

#### Other GCP terms (reference)

| Term | Meaning |
|------|---------|
| **GCP project** | Billing + container for GKE, AlloyDB, secrets |
| **GKE namespace** | Where `ianbot-api` Deployment lives (e.g. `ianbot-legal`) |
| **Ingress / Gateway** | Public HTTPS entry to the API |
| **Region** | Where cluster and AlloyDB run (e.g. `us-central1`) |
| **IAM** | Who can deploy, who can read secrets |
| **Cloud Scheduler** | Not used for v1 (Apps Script handles schedules). Optional GCP alternative if policy requires it |
| **Vertex AI** | Enterprise Gemini path in GCP (legal may require this) |

### Slack: two connection types

| Pattern | Used for | Points to |
|---------|----------|-----------|
| **Incoming webhook** | ian-bot “new file” alerts today | Slack URL; Apps Script posts JSON |
| **Events API + interactivity** | Payment link buttons, Q&A later | **Ingress** HTTPS on GKE (Slack signing secret) |

### DevOps setup checklist

- [ ] GCP **project** + **GKE** cluster (or shared cluster) + namespace for `ianbot-api`.
- [ ] **AlloyDB** instance (when schema is ready); private connectivity from GKE per platform standard.
- [ ] **Deployment**, **Service**, **Ingress** (+ TLS); `GET /health` probes configured.
- [ ] **Workload identity** — GCP service account for Drive/Sheet; share contract folder + finance sheet (write for `contract_ref`).
- [ ] **Secret Manager** entries; sync to pods (External Secrets or org pattern).
- [ ] Provide **Ingress base URL** for Apps Script Script Properties (`/ingest`, `/sync/sheet`).
- [ ] Confirm **Gemini**: Vertex vs AI Studio.
- [ ] Apps Script **daily** time-driven trigger for `syncSheetToBackend` → `POST /sync/sheet` (no Cloud Scheduler / CronJob for v1).
- [ ] Public repo: no real tokens in Git; rotate any secrets ever pasted into chat or commits.

### Suggested DevOps one-liner

> **GKE Deployment** `ianbot-api` behind **Ingress**; **AlloyDB** as the Postgres catalog; **Apps Script** for Drive alerts, **timed schedules**, and HTTP pokes to ingest/sync; **Secret Manager** + **workload identity** for Drive/Sheet; **Slack** webhooks for alerts today and **Ingress** for interactivity later. **No cron VM, Cloud Scheduler, or CronJob.**

---

## Slack: ian-bot today vs contract features

| | **Today (ian-bot)** | **Planned add-ons** |
|--|---------------------|---------------------|
| **Role** | Alerts when new signed PDFs land in Drive (via Apps Script). | (1) **Payment linking**—buttons to fill `contract_ref` on the sheet. (2) **Contract Q&A**—questions about deals and payments using Postgres + Gemini. |
| **Who sees it** | Whatever channels/users already get alerts. | **Back office and management only** (allowlist—not company-wide). |
| **How to build it** | Keep as-is for alerts. | **Option A:** Extend **ian-bot**. **Option B:** Second Slack app for linking + Q&A only. |

Access control: allowlisted Slack user IDs. Others may still get Drive alerts; they should not get Q&A or linking unless added.

---

## What we’re building (big picture)

| Piece | What it does |
|--------|----------------|
| **Google Drive** | Official home for signed PDFs (inbox + subfolders). **File ID** stays the same when moved between folders. |
| **Finance Google Sheet** | Payment log + new **`contract_ref`** column (via Slack linking). |
| **Apps Script** | Alerts via **ian-bot**; poke ingest on new PDF; **daily** time-driven trigger for sheet sync. |
| **GKE (`ianbot-api`)** | Index PDFs, sync sheet, later Slack handlers (via Ingress). |
| **AlloyDB** | PostgreSQL-compatible catalog for Q&A and payment totals. |
| **Gemini** | Extract contract fields; write answers from catalog only. |

```text
  Drive (PDFs)
       |
       v
  Apps Script ----alert----> ian-bot (existing webhook)
       |
       +---- POST /ingest ---> GKE (ianbot-api) + Gemini ---> AlloyDB

  Finance Sheet (+ contract_ref)
       |
       |  "Link to contract" -> Slack buttons -> contract_ref filled
       v
  Apps Script (daily trigger) ---> POST /sync/sheet ---> AlloyDB

  ian-bot (later) ---> Ingress (GKE) ---> AlloyDB + Gemini (Q&A, allowlisted)
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

### Phase 0 — Setup and access

- [ ] Confirm with IT/legal: Gemini via **Vertex AI** vs **AI Studio API key**.
- [ ] GCP project + **GKE** + **AlloyDB** + **Secret Manager** + **service account** (workload identity).
- [ ] **Postgres** (local Docker for dev; **AlloyDB** for prod)—schema design later.
- [ ] Document Drive **root folder ID**; service account access to full tree.
- [ ] Document finance **sheet ID** and column mapping.
- [ ] Finance: new columns **`contract_ref`**, link status, **“Link to contract”** checkbox.
- [ ] Decide Slack link message destination (channel vs DM).
- [ ] Decide extend **ian-bot** vs second Slack app; allowlist back office + management.
- [ ] Apps Script Script Properties: ingest URL + secret (no secrets in public repo).

### Phase 1 — Database catalog

- [ ] Design tables: **contracts**, **payments**, **aliases** (TBD).
- [ ] **Drive file ID** as stable contract key.
- [ ] `schema.sql` + local dev setup.
- [ ] Verify payment totals vs sheet for 2–3 linked contracts.

### Phase 2 — Ingest service on GKE (`ianbot-api`)

- [ ] FastAPI app: `POST /ingest`, `POST /sync/sheet`, `GET /health`.
- [ ] Drive download (service account); PDF only; idempotent upsert.
- [ ] Gemini extraction → AlloyDB.
- [ ] Sheet sync including `contract_ref`.
- [ ] Deploy to GKE (Deployment + Ingress); wire Apps Script `pokeIngestWebhook`.

### Phase 2b — Link payments in Slack

- [ ] Checkbox → Slack message with 3–5 contract buttons + “None”.
- [ ] Button click → write **`contract_ref`** on sheet (service account or API).
- [ ] Allowlist finance users for linking actions.

### Phase 3 — Apps Script

- [x] Keep ian-bot alerts.
- [ ] Ingest poke after alert; debounce duplicate file IDs.
- [ ] **Daily** Apps Script time-driven trigger for `syncSheetToBackend` → `POST /sync/sheet`.
- [ ] Optional: ingest status in alert message.

### Phase 4 — Contract Q&A on Slack

- [ ] GKE Slack endpoints (via Ingress); allowlisted DMs.
- [ ] Answers from Postgres only; Gemini for wording; citations required.

### Phase 5 — Quality

- [ ] Aliases, golden questions, finance UAT on linking.

### Phase 6 — Go live

- [ ] Monitoring, DB backups, disclaimer, audit logging policy.

### Phase 7 — Later

- [ ] Full text search / OCR / optional web UI.

---

## Suggested build order

1. GKE `/ingest` stub + Apps Script poke (no DB, or fake response).
2. Postgres schema + real ingest + sheet sync.
3. Slack payment linking → `contract_ref`.
4. Q&A on ian-bot (or new app) for allowlisted users.
5. Aliases, golden tests, hardening.

---

## Decisions still open

| Topic | Choices | Decision |
|--------|---------|----------|
| Gemini | AI Studio for **local dev**; **Vertex AI** for prod (`GEMINI_BACKEND=vertex`, v0.0.5) | _dev: Studio; prod: Vertex when GCP + legal ready_ |
| GKE / AlloyDB | Namespace, Ingress host, AlloyDB instance (platform template?) | _TBD_ |
| Sheet sync schedule | **Apps Script daily trigger** (no Cloud Scheduler / CronJob for v1) | _decided_ |
| Slack | Extend **ian-bot** vs new bot | _TBD_ |
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
| ian-bot (Slack app) | |
| Second Slack app (if not extending ian-bot) | |
| GCP project | |
| Ingress URL (ianbot-api) | |
| AlloyDB instance | |
| GKE cluster / namespace | |

---

## Code folders

```text
bot/           # Slack + Telegram webhooks (A1 echo; Q&A/linking later)
ingest/        # FastAPI app (ianbot-api): /health, /ingest, /sync/sheet
core/          # config, auth, extract, db
db/            # schema.sql
docs/          # DEV.md, apps-script notes
deploy/        # GKE manifests (later)
tests/         # API smoke tests
```

**Local dev:** see [docs/DEV.md](docs/DEV.md).

---

## Versioning

**Current version:** `0.0.5` (also in [`VERSION`](VERSION), `pyproject.toml`, `readme.md` title, and `GET /health` → `version`).

| Bump | When | How |
|------|------|-----|
| **Patch** `0.0.1` → `0.0.2` | Every routine revision commit | Auto: enable [`.githooks/pre-commit`](.githooks/pre-commit) via `./scripts/setup-git-hooks.sh`, **or** run `./scripts/commit-revision.sh -m "your message"` |
| **Minor** `0.1.0` → `0.2.0` | Only when you explicitly want a minor release | `python3 scripts/bump_minor.py`, update changelog, then `git commit` (use `--no-verify` if hooks would patch-bump again) |
| **Major** `1.0.0` → `2.0.0` | Only when you explicitly want a major release | `python3 scripts/bump_major.py`, update changelog, then `git commit` |

**Commit messages:** include the version tag, e.g. `feat(v0.0.1): …` or `fix(v0.0.2): …`.

**Skip auto patch bump** (rare): `git commit --no-verify`.

After enabling hooks, each `git commit` bumps patch and stages `VERSION`, `pyproject.toml`, `ingest/api.py`, and the `readme.md` title (`# ianbot-skill-legal vX.X.X`) before the commit is created—add changelog notes in the same commit when you can.

---

## Changelog

### v0.0.7

- Bot A1: Slack and Telegram webhook adapters (`/webhooks/slack/events`, `/webhooks/slack/interactions` stub, `/webhooks/telegram/{secret}`).
- Echo handler: `ping` / `/ping` → `pong`; other text → `You said: …`. Idempotency via `bot_processed_events` or in-memory fallback.
- `GET /health` adds `bot_platforms`, `bot_slack_configured`, `bot_telegram_configured`. See `bot/README.md` and `docs/DEV.md`.

### v0.0.5

- Vertex Gemini extraction: `VertexGeminiClient` using `google-genai` with `vertexai=True`; config via `GOOGLE_CLOUD_PROJECT` and `GOOGLE_CLOUD_LOCATION`.
- `gemini_configured` and ingest error messages are backend-aware (studio vs vertex); `GET /health` includes `gemini_backend`.
- Docs: Vertex setup in `docs/DEV.md` and `.env.example`.

### v0.0.4

- Gemini extraction (dev): AI Studio API-key backend (`core/gemini_client.py`) wired into `core/extract.py`.
- `/ingest` now returns `status: error` when Gemini is enabled but missing Drive bytes or API key; `GET /health` includes `gemini_configured`.
- **Security note:** checked in with Gemini-enabled path for local testing; data-handling risks for confidential PDFs are **not fully verified**. Production is expected to move to **Vertex AI** after legal/IT sign-off (see “Gemini in v0.0.4” above).

### v0.0.3

- `/ingest` downloads contract PDFs from Drive in memory via service account (`core/drive.py`); `GET /health` reports `drive_configured`.
- Google client libraries added to project dependencies; Drive download errors return `status: error` with HTTP 200 for Apps Script pokes.

### v0.0.2

- Local dev: `scripts/wipe-local-db.sh` full Postgres reset (Docker volume + `schema.sql`); documented in `docs/DEV.md`.
- Phase 0 helpers: `scripts/test_drive_sa.py` and `test_drive_sa2.py` to validate service account folder list and PDF download.
- `.gitignore` rules for GCP service account JSON key downloads (keep keys out of the public repo).

### v0.0.1

- Initial **ianbot-api** scaffold: FastAPI (`/health`, `/ingest`, `/sync/sheet`), stub Gemini extraction, local Postgres schema via Docker Compose.
- Docs for DevOps (GKE + AlloyDB), finance (`contract_ref`), legal, and Apps Script ingest poke.
- API smoke tests; versioning scripts and optional git hook for patch bumps.
