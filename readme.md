# ian-bot-legal — contract & payment assistant

**Base document** for product, engineering, DevOps, finance, and legal. Describes what we plan to build, how pieces connect, and what each group needs to decide or provide.

An **internal Slack assistant** that answers questions about:

- **Signed contracts** (PDFs in a Google Drive folder tree), and
- **Payments** (rows in a finance Google Sheet).

The system keeps a **searchable catalog in Postgres** (a normal database) and uses **Google Gemini** to read contracts once and to write answers—we are **not training a custom AI model**. When new files or rows appear, we **refresh the catalog**; that is not “training.”

**Usage:** Low volume (back office and management, a few times per month). Architecture stays small: one backend on **Google Cloud Run**, **no dedicated cron server**.

Slack today: our existing bot is **ian-bot** (Drive alerts and related messages). Contract Q&A and payment linking may live on **ian-bot** (extended) or on a **new** Slack app—we have not decided yet (see below).

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

- [ ] Agree to the new columns above on the existing payment sheet.
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

---

## For DevOps and engineering

### Services map (minimal footprint)

We want **one Cloud Run service**, **one Postgres (Cloud SQL)**, **Apps Script as triggers**, **no cron VM**, **no Kubernetes**.

```text
┌─────────────────────────────────────────────────────────────┐
│  Google Workspace (no servers we manage)                    │
│  • Apps Script — Drive watch, Slack alerts, timed triggers  │
│  • Drive — signed PDFs (folder tree)                        │
│  • Sheet — payments + contract_ref                          │
└───────────────┬─────────────────────────────┬───────────────┘
                │ HTTPS                       │ Google APIs
                v                             v
┌───────────────────────────────┐   ┌─────────────────────────┐
│  Cloud Run: ianbot-api         │   │  Gemini API             │
│  /ingest, /sync/sheet, /health │   │  (Google)               │
│  later: /slack/events          │   └─────────────────────────┘
└───────────────┬───────────────┘
                │
                v
┌───────────────────────────────┐
│  Cloud SQL: Postgres           │
└───────────────────────────────┘

┌───────────────────────────────┐
│  Slack                         │
│  • Incoming webhook — ian-bot alerts (today)                 │
│  • Events API → Cloud Run (linking buttons, Q&A later)       │
└───────────────────────────────┘
```

| Component | Role | Hosted by |
|-----------|------|-----------|
| **Apps Script** | New PDF → Slack alert + `POST /ingest`; optional daily `POST /sync/sheet` | Google |
| **Cloud Run** | Ingest PDF, sync sheet, Slack interactivity, Q&A logic | GCP |
| **Cloud SQL** | Catalog (contracts, payments)—schema TBD | GCP |
| **Secret Manager** | API keys, DB URL, ingest secret, Slack secrets | GCP |
| **Service account** | Robot Google identity for Drive + Sheet API access | GCP |
| **Gemini** | Extract fields from PDF; compose answers from catalog | Google |
| **ian-bot (Slack)** | Alerts today; may add Q&A + linking later | Slack |

### Ingest service (wireframe)

**Not** the Slack bot. A small **Python (FastAPI)** API that fills Postgres.

| Endpoint | Called by | Purpose |
|----------|-----------|---------|
| `POST /ingest` | Apps Script after new PDF | Body: `drive_file_id`. Download PDF → Gemini → upsert contract. |
| `POST /sync/sheet` | Apps Script daily trigger **or** Cloud Scheduler | Copy finance sheet → Postgres (including `contract_ref`). |
| `GET /health` | Monitoring | Liveness check. |

**`POST /ingest` steps:** validate shared secret header → download PDF via service account → skip if not PDF or unchanged → Gemini JSON extraction → upsert by `drive_file_id` → return 200 or error.

**Security:** `X-Ingest-Secret` (or similar) on `/ingest` and `/sync/sheet`; not open anonymous internet. Real values in **Secret Manager**, not in this public repo.

**Later (same Cloud Run app):** Slack Events API + interactivity for payment linking and Q&A.

### Scheduling: no cron server

We do **not** need a VM whose only job is cron.

| Job | Recommended trigger |
|-----|---------------------|
| New PDF alert + index | Existing Apps Script timer → `checkForNewFiles` → Slack + `pokeIngestWebhook` |
| Daily sheet → Postgres | **Apps Script time-driven trigger** → `POST /sync/sheet` |
| Optional Drive catch-up | Apps Script weekly **or** Cloud Scheduler → backend rescan endpoint |

**Apps Script** = doorbell and timers. **Cloud Run** = heavy work (Gemini, DB, Slack buttons).

### Google Cloud pieces (plain English)

#### Cloud Run

Runs our application as an **HTTPS URL** without managing a server. Google starts containers on demand; can **scale to zero** when idle (low cost for rare usage).

- Deploy one service (e.g. `ianbot-api`) from a Docker image.
- Apps Script calls `https://….run.app/ingest`.
- Later, Slack sends button clicks and DMs to the same URL.

#### Cloud SQL

Managed **Postgres** for the catalog. Separate product from Cloud Run; connected over the network with credentials from Secret Manager. **Database table design is deferred**—this doc only assumes contracts + payments + optional aliases.

#### Secret Manager

A **vault** for sensitive strings (Gemini key, database password, ingest webhook secret, Slack signing secret, bot tokens). Cloud Run reads them at runtime. **Do not commit secrets to this public GitHub repo.**

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

- Cloud Run runs as this identity (or uses its credentials).
- **Share** the contract Drive folder and finance sheet with this email (like sharing with a colleague).
- **Never** commit the JSON key file to the public repo; prefer workload identity on Cloud Run in production.

#### Other GCP terms (reference)

| Term | Meaning |
|------|---------|
| **GCP project** | Billing + container for Run, SQL, secrets |
| **Region** | Where resources run (e.g. `us-central1`) |
| **IAM** | Who can deploy, who can read secrets |
| **Cloud Scheduler** | Optional GCP cron hitting a URL—use **or** Apps Script timers, not both unless intentional |
| **Vertex AI** | Enterprise Gemini path in GCP (legal may require this) |

### Slack: two connection types

| Pattern | Used for | Points to |
|---------|----------|-----------|
| **Incoming webhook** | ian-bot “new file” alerts today | Slack URL; Apps Script posts JSON |
| **Events API + interactivity** | Payment link buttons, Q&A later | **Cloud Run** HTTPS (Slack signing secret) |

### DevOps setup checklist

- [ ] GCP **project** for ian-bot-legal.
- [ ] **Service account** + share Drive contract folder + finance sheet (write for `contract_ref`).
- [ ] **Secret Manager** entries; grant Cloud Run runtime read access.
- [ ] **Cloud SQL** Postgres (when schema is ready); network access from Cloud Run.
- [ ] **Cloud Run** deploy from container; env from secrets.
- [ ] Provide **ingest URL** for Apps Script Script Properties.
- [ ] Confirm **Gemini**: Vertex vs AI Studio.
- [ ] (Optional) **Cloud Scheduler** for `/sync/sheet` if not using Apps Script daily trigger only.
- [ ] Public repo: no real tokens in Git; rotate any secrets ever pasted into chat or commits.

### Suggested DevOps one-liner

> One **Cloud Run** service and **Cloud SQL Postgres**; **Apps Script** for Drive alerts and HTTP triggers to ingest; **Secret Manager** for credentials; **service account** for Drive/Sheet; **Slack** webhooks for alerts today and Cloud Run for interactivity later. No VMs, no Kubernetes, scale to zero.

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
| **Apps Script** | Alerts via **ian-bot**; poke ingest on new PDF; optional daily sheet sync trigger. |
| **Cloud Run (ingest API)** | Index PDFs, sync sheet, later Slack handlers. |
| **Postgres** | Catalog for Q&A and payment totals. |
| **Gemini** | Extract contract fields; write answers from catalog only. |

```text
  Drive (PDFs)
       |
       v
  Apps Script ----alert----> ian-bot (existing webhook)
       |
       +---- POST /ingest ---> Cloud Run + Gemini ---> Postgres

  Finance Sheet (+ contract_ref)
       |
       |  "Link to contract" -> Slack buttons -> contract_ref filled
       v
  Apps Script (daily) or Scheduler ---> POST /sync/sheet ---> Postgres

  ian-bot (later) ---> Cloud Run ---> Postgres + Gemini (Q&A, allowlisted)
```

---

## Apps Script (existing + planned)

**Today:** `checkForNewFiles` scans the Drive folder, sends Slack alert for new files.

**Added (foundation):** `pokeIngestWebhook(file)` after each alert—`POST` to Cloud Run `/ingest` with `drive_file_id`, using URL and secret from **Script Properties** (skips if URL not set).

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
- [ ] GCP project + **Cloud Run** + **Secret Manager** + **service account**.
- [ ] **Postgres** (local Docker for dev; **Cloud SQL** for prod)—schema design later.
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

### Phase 2 — Ingest service on Cloud Run

- [ ] FastAPI app: `POST /ingest`, `POST /sync/sheet`, `GET /health`.
- [ ] Drive download (service account); PDF only; idempotent upsert.
- [ ] Gemini extraction → Postgres.
- [ ] Sheet sync including `contract_ref`.
- [ ] Deploy to Cloud Run; wire Apps Script `pokeIngestWebhook`.

### Phase 2b — Link payments in Slack

- [ ] Checkbox → Slack message with 3–5 contract buttons + “None”.
- [ ] Button click → write **`contract_ref`** on sheet (service account or API).
- [ ] Allowlist finance users for linking actions.

### Phase 3 — Apps Script

- [ ] Keep ian-bot alerts.
- [ ] Ingest poke after alert; debounce duplicate file IDs.
- [ ] Daily trigger for `/sync/sheet` (unless Cloud Scheduler owned by DevOps).
- [ ] Optional: ingest status in alert message.

### Phase 4 — Contract Q&A on Slack

- [ ] Cloud Run Slack endpoints; allowlisted DMs.
- [ ] Answers from Postgres only; Gemini for wording; citations required.

### Phase 5 — Quality

- [ ] Aliases, golden questions, finance UAT on linking.

### Phase 6 — Go live

- [ ] Monitoring, DB backups, disclaimer, audit logging policy.

### Phase 7 — Later

- [ ] Full text search / OCR / optional web UI.

---

## Suggested build order

1. Cloud Run `/ingest` stub + Apps Script poke (no DB, or fake response).
2. Postgres schema + real ingest + sheet sync.
3. Slack payment linking → `contract_ref`.
4. Q&A on ian-bot (or new app) for allowlisted users.
5. Aliases, golden tests, hardening.

---

## Decisions still open

| Topic | Choices | Decision |
|--------|---------|----------|
| Gemini | API key vs Vertex (company cloud) | _TBD_ |
| Hosting | **Cloud Run** (recommended) vs small VM | _TBD_ |
| Sheet sync schedule | Apps Script daily vs **Cloud Scheduler** | _TBD_ |
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
| Cloud Run service URL | |
| Cloud SQL instance | |

---

## Code folders (target)

```text
bot/           # Slack: questions + button clicks for linking
ingest/        # Drive, sheet, Gemini, FastAPI routes
core/          # DB access, orchestrator, prompts
db/            # schema.sql (later)
docs/          # extra notes if needed
```
