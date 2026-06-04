# ian-bot-legal — bot enhancement plan

An idea for upgrading our existing bot so that it answers questions about signed commercial contracts (Google Drive) and payments (Google Sheet). Uses a Postgres catalog and Google Gemini for extraction and answers. **No custom model training.**

## Architecture (short)

- **Drive** (folder tree + subfolders): source of truth for signed PDFs; stable **file ID** per document.
- **Finance Sheet**: source of truth for payment rows.
- **Apps Script** (existing): alerts via current Slack bot; later triggers ingest per new file.
- **Ingest service**: downloads PDF → Gemini extraction → Postgres; syncs sheet → Postgres.
- **Q&A Slack bot** (new app): allowlisted users → Postgres facts → Gemini answer with citations.

---

## Project to-do

### Phase 0 — Foundations & access

- [ ] Confirm with IT/legal: Gemini via **Vertex AI** vs **AI Studio API key** for confidential PDFs.
- [ ] Create GCP project (or use existing) for ingest + Q&A service and secrets.
- [ ] Create **Postgres** database (local Docker for dev; managed e.g. Cloud SQL for prod).
- [ ] Document Drive **root folder ID** and confirm Apps Script + service account can read the full tree (inbox + subfolders).
- [ ] Document finance **Google Sheet ID** and column layout.
- [ ] Ask finance to add **`contract_ref`** column (Drive file ID or link) on payment rows.
- [ ] Create Google **service account** with access only to contract folder + finance sheet.
- [ ] Store secrets: Slack (Q&A bot), Slack (alert bot — existing), Gemini, DB URL, ingest webhook secret.

### Phase 1 — Database catalog

- [ ] Define schema: `contracts`, `payments`, `aliases` (optional), ingest metadata (`ingested_at`, `drive_modified_time`).
- [ ] Use **Drive file ID** as primary stable key for contracts (not folder path).
- [ ] Add migration or `schema.sql` and seed script for local dev.
- [ ] Verify payment totals in SQL match finance sheet manually (golden checks for 2–3 contracts).

### Phase 2 — Ingest service (backend “kitchen”)

- [ ] Create minimal ingest API (e.g. Cloud Run): `POST /ingest` with `{ drive_file_id }` + auth.
- [ ] Implement Drive download by file ID (handle PDF only; skip non-PDF).
- [ ] Implement Gemini **extraction** prompt + structured JSON (counterparty, dates, value, summary, watch-outs).
- [ ] Upsert contract row in Postgres on success; store raw extraction JSON for debugging.
- [ ] Implement **sheet sync** job (full or incremental): upsert `payments`, link via `contract_ref`.
- [ ] Implement idempotency: same file ID → update, not duplicate.
- [ ] Add scheduled **full sheet sync** (daily) and optional weekly Drive reconciliation scan.
- [ ] Log ingest success/failure; expose `ingested_at` for bot footers.

### Phase 3 — Apps Script re-wire (existing monitor)

- [ ] Keep current behavior: detect new PDF in tree → **alert** via existing Slack bot.
- [ ] After file is stable (same ID, whether in top folder or subfolder), call ingest webhook with **file ID**.
- [ ] Add webhook authentication (shared secret header or similar).
- [ ] Avoid double-ingest: debounce or “already queued” flag per file ID if script fires twice.
- [ ] (Optional) Add ingest status to alert message: “catalog updated” / “indexing failed”.
- [ ] Document script trigger order: alert vs ingest call relative to subfolder moves (ID unchanged).

### Phase 4 — Q&A Slack bot (new app)

- [ ] Create new Slack app (separate from alert bot).
- [ ] Enable **Socket Mode** or HTTPS endpoint for events.
- [ ] Restrict to **DM** first; configure allowlist `ALLOWED_SLACK_USER_IDS`.
- [ ] Implement message handler: resolve company name → contract(s) via Postgres + aliases.
- [ ] Compute **total paid** in Postgres (not in LLM).
- [ ] Call Gemini with **context-only** prompt; require citations (filename, dates, totals).
- [ ] Reply format: short bullets + Drive link; footer “Data as of {ingested_at}”.
- [ ] Handle “not found” without hallucinating.

### Phase 5 — Aliases & quality

- [ ] Add `aliases` table or sheet tab: “ABCâon set** (10–20 real questions) for manual regression after ingest changes.
- [ ] Tune extraction prompt on 5 representative contracts (MSA, amendment, non-English if any).
- [ ] Align with finance on payee vs counterparty naming mismatches.

### Phase 6 — Deploy & ops (low traffic)

- [ ] Deploy ingest + Q&A bot to single host (e.g. Cloud Run).
- [ ] Configure health check and basic uptime monitoring.
- [ ] Backup Postgres; document restore drill.
- [ ] Add disclaimer in bot welcome text (decision support, not legal advice).
- [ ] Define audit policy: log user ID + contract IDs used (optional: omit full question text).

### Phase 7 — Later (only if needed)

- [ ] Store full extracted text per contract for long PDFs.
- [ ] Add pgvector chunk search for clause-level questions.
- [ ] OCR path for scanned PDFs if extraction quality is poor.
- [ ] Internal web UI (optional); reuse same orchestrator as Slack.

---

## Open decisions

| Topic | Options | Decision |
|-------|---------|----------|
| Gemini h | AI Studio vs Vertex | _TBD_ |
| Bot hosting | Cloud Run vs VM | _TBD_ |
| Sheet ↔ contract link | `contract_ref` column vs name match only | _TBD_ |

---

## Repo layout (target)

```text
bot/           # Slack Q&A (Bolt)
ingest/        # Drive, Sheet, Gemini extract, API
core/          # DB access, orchestrator, prompts
db/            # schema.sql, migrations
docs/          # architecture notes
