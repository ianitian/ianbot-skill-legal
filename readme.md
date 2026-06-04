# ian-bot-legal — contract & payment assistant

A plan to build an **internal Slack assistant** that answers questions about:

- **Signed contracts** (PDFs in a Google Drive folder tree), and
- **Payments** (rows in a finance Google Sheet).

The system keeps a **searchable catalog in Postgres** (a normal database) and uses **Google Gemini** to read contracts once and to write answers—but we are **not training a custom AI model**. When new files or rows appear, we **refresh the catalog**; that is not “training.”

Slack today: our existing bot is **ian-bot** (Drive alerts and related messages). Contract Q&A and payment linking may live on **ian-bot** (extended) or on a **new** Slack app—we have not decided yet (see below).

---

## Finance sheet: new `contract_ref` column

The finance Google Sheet already has payment fields (date, amount, payee, etc.). We will add a **new column** called **`contract_ref`**.

| What | Explanation |
|------|-------------|
| **What it holds** | A link to the signed contract in Drive (URL), or the Drive **file ID** for that PDF. |
| **Who fills it** | Usually **not typed by hand**. After finance marks a row for linking, **ian-bot** (or our backend) posts options in Slack; finance clicks the right contract, and the script **writes this column** for that row. |
| **Why we need it** | Payments and contracts are separate lists. This column is the official “this payment belongs to **that** contract” so totals and Q&A stay correct. |
| **Related columns** | Likely also: link **status** (e.g. needs link / linked / none) and a **“Link to contract”** checkbox to start the Slack flow. |

Until `contract_ref` is set for a row, the Q&A side may answer contract questions but should treat that payment as **not linked** (no reliable “how much paid on this deal” for that row).

---

## Slack: ian-bot today vs contract features

| | **Today (ian-bot)** | **Planned add-ons** |
|--|---------------------|---------------------|
| **Role** | Alerts when new signed PDFs land in Drive (via Apps Script). | (1) **Payment linking**—buttons to fill `contract_ref` on the sheet. (2) **Contract Q&A**—questions about deals and payments using Postgres + Gemini. |
| **Who sees it** | Whatever channels/users already get alerts. | **Back office and management only** (allowlist of Slack users—not open to the whole company). |
| **How to build it** | Keep as-is for alerts. | **Option A:** Extend **ian-bot** with new commands / DMs / button handlers. **Option B:** Create a **second** Slack bot only for linking + Q&A; ian-bot stays alerts-only. |

**Option A (one bot)** — Simpler for users: one name in Slack. Need clear separation inside the code (alerts vs linking vs Q&A) and careful permissions so only allowlisted users can ask contract questions or click link buttons.

**Option B (two bots)** — ian-bot unchanged; new bot for sensitive features. Slightly more setup, but alerts and “legal/finance assistant” are clearly separated.

Access control either way: maintain a list of allowed Slack user IDs (back office + management). Everyone else can still get Drive alerts if they do today; they should **not** get Q&A or payment-linking actions unless we explicitly add them.

---

## What we’re building (big picture)

| Piece | What it does |
|--------|----------------|
| **Google Drive** | Official home for signed PDFs (inbox + subfolders). Each file has a permanent **file ID** that stays the same when the file is moved between folders. |
| **Finance Google Sheet** | Official log of payments (date, amount, payee, etc.). New column **`contract_ref`** links each row to one contract (filled via Slack, not manual hunt in Drive). |
| **Existing Apps Script** | Already watches Drive and sends **alerts** through **ian-bot**. We will extend it to **tell the catalog service to index** new files. |
| **Catalog / ingest service** | Backend that reads a PDF, asks Gemini to pull out key fields, and saves everything to Postgres. Also copies sheet rows (including `contract_ref`) into Postgres. |
| **Slack — payment linking** | When finance marks a row “ready to link,” **ian-bot** (or a new bot) shows **likely contracts as buttons**. Finance picks one; the new **`contract_ref`** column is updated on the sheet. |
| **Slack — contract Q&A** | Allowlisted users (back office, management) ask questions like “How much did we pay on the ABC deal?” Answers use **only** Postgres + Gemini, with links back to Drive. |

```text
  Drive (PDFs)
       |
       v
  Apps Script ----alert----> ian-bot (existing)
       |
       +---- "index this file" ---> Ingest + Gemini ---> Postgres

  Finance Sheet (+ new contract_ref column)
       |
       |  finance checks "link to contract"
       v
  ian-bot (or new bot): buttons ---> finance picks ---> contract_ref on sheet
       |
       v
  Sheet sync ---> Postgres

  ian-bot (or new bot): Q&A for allowlisted users ---> Postgres + Gemini
```

---

## Linking payments to contracts (Slack)

**Problem:** Contracts live in Drive; payments live in the sheet. To answer “how much have we paid **on this contract**?”, we need an explicit link—not a guess from similar company names.

**Plan:**

1. Finance enters a payment row as usual.
2. They check something like **“Link to contract”** (or set a status to “needs link”).
3. Our system finds **a short list of likely PDFs** (from the contract catalog: names, parties, filenames, past picks for the same payee).
4. **Slack** sends finance a message with **clickable options** (and something like “None of these”).
5. Finance chooses the right contract.
6. The **new sheet column `contract_ref`** is updated on that row (Drive link or file ID).
7. The next **sheet sync** copies that link into Postgres so contract Q&A can add up payments correctly.

**Rules we care about:**

- **Always confirm in Slack**—no silent auto-linking (wrong link = wrong totals).
- Prefer storing **file ID** in the database even if the sheet shows a URL.
- If nothing matches, finance can skip until the contract PDF exists in Drive.

---

## Project to-do

### Phase 0 — Setup and access

- [ ] Confirm with IT/legal whether Gemini must run through **Vertex AI** (company Google Cloud) or can use an **API key** (AI Studio).
- [ ] Set up a Google Cloud project (or use an existing one) for hosting and secrets.
- [ ] Create **Postgres** (simple local database for development; managed database for production).
- [ ] Write down the Drive **root folder ID**; confirm the script and service account can read the whole tree.
- [ ] Write down the finance **sheet ID** and which columns mean date, amount, payee, etc.
- [ ] Add **new** sheet columns on the finance tab: **`contract_ref`** (link or file ID), link **status**, and **“Link to contract”** checkbox (or similar).
- [ ] Brief finance on the new column: it is filled by Slack after they confirm a match, not by pasting Drive links by default.
- [ ] Decide where Slack link messages go (finance channel vs direct messages).
- [ ] Decide **ian-bot extended** vs **second Slack bot**; define allowlist for **back office + management**.
- [ ] Create a **service account** that can only access the contract folder and the finance sheet (sheet needs write access for `contract_ref`).
- [ ] Store passwords/tokens safely: ian-bot / Slack, Gemini, database URL, webhook secret.

### Phase 1 — Database catalog

- [ ] Design tables for **contracts**, **payments**, optional **aliases** (nicknames for companies), and **last updated** timestamps.
- [ ] Treat **Drive file ID** as the main ID for a contract (not folder path or filename alone).
- [ ] Add `schema.sql` (and a simple way to create tables locally).
- [ ] Manually check 2–3 contracts: payment totals in the database match the sheet when `contract_ref` is set.

### Phase 2 — Ingest service (“the kitchen”)

- [ ] Small web service with a secure endpoint: “index this file ID.”
- [ ] Download PDF from Drive; skip non-PDFs.
- [ ] Use Gemini once per file to extract: company name, dates, deal value, short summary, “things to watch out for.”
- [ ] Save or update the contract in Postgres (same file ID = update, not duplicate).
- [ ] **Sync the finance sheet** into Postgres; attach payments to contracts using `contract_ref`.
- [ ] Run sheet sync on a schedule (e.g. daily); optional weekly scan of Drive for anything missed.
- [ ] Log success/failure; Q&A answers can say “data as of …”
- [ ] Keep a **contract list** good enough to suggest links in Slack (from Postgres or a sheet tab).

### Phase 2b — Link payments in Slack

- [ ] When “Link to contract” is checked, mark the row as **waiting for link**.
- [ ] Rank likely contracts (payee vs contract name, catalog, past choices).
- [ ] Post a Slack message with **3–5 buttons** (plus “None of these”).
- [ ] When finance clicks a button, write **`contract_ref`** on the correct row.
- [ ] Update status to **linked** or **none**; don’t send duplicate prompts for the same row.
- [ ] Optional: remember payee → contract for better suggestions next time (still require a click).
- [ ] After linking, refresh Postgres (sync sheet) so the Q&A bot sees the link.

### Phase 3 — Update existing Apps Script (Drive monitor)

- [ ] Keep today’s behavior: new PDF → **alert** in Slack via **ian-bot**.
- [ ] After the file is in the tree, call the ingest service with its **file ID**.
- [ ] Protect the webhook (shared secret).
- [ ] Avoid indexing the same file twice in a row (debounce).
- [ ] Optional: add “catalog updated” or “index failed” to the alert.
- [ ] When finance checks “link to contract,” trigger the Slack linking flow (from script or backend).
- [ ] Remember: moving a PDF between subfolders **does not change** its file ID.

### Phase 4 — Contract Q&A on Slack (ian-bot or new bot)

- [ ] Choose: extend **ian-bot** vs register a **new** Slack app (linking + Q&A).
- [ ] Connect the app to our server; handle button clicks for linking and messages for Q&A.
- [ ] Restrict contract Q&A and linking actions to **allowlisted** Slack users (back office + management).
- [ ] Keep existing **ian-bot** Drive alerts working for current channels/users.
- [ ] Prefer **DMs** for contract Q&A first; keep answers out of public channels.
- [ ] Look up contracts and payments in Postgres; add up payments in the database (not in AI).
- [ ] Ask Gemini to write a clear answer **only from that data**; include contract name and Drive link.
- [ ] If data is missing or `contract_ref` empty, say so—don’t invent contract terms.

### Phase 5 — Quality and edge cases

- [ ] **Aliases**: map “ABC”, “ABC Corp”, etc. to the same contract.
- [ ] **Golden questions**: 10–20 real questions we test after each change.
- [ ] Tune extraction on a few sample contracts (MSA, amendment, etc.).
- [ ] Walk finance through 5 real **Slack linking** flows and fix UX issues.

### Phase 6 — Go live (low usage)

- [ ] Deploy ingest + bots to one place (e.g. Cloud Run).
- [ ] Basic health check / “is it up?” monitoring.
- [ ] Database backups.
- [ ] Short disclaimer: helper tool, not legal advice.
- [ ] Decide what we log (who asked, which contracts were used—not necessarily full chat text).

### Phase 7 — Later (only if we need it)

- [ ] Store full contract text for very long PDFs.
- [ ] Search inside contracts by paragraph (vectors in Postgres).
- [ ] Better handling for scanned PDFs (OCR).
- [ ] Optional web page (same logic as Slack).

---

## Suggested build order

1. Database + a few contracts and payments linked by hand → check totals.
2. Ingest service + Gemini extraction + sheet sync.
3. Apps Script calls ingest when a new PDF appears.
4. **Slack linking** → finance picks contract → `contract_ref` on sheet.
5. **Contract Q&A** on ian-bot (or new bot) in DMs for allowlisted users.
6. Aliases, golden questions, production deploy.

---

## Decisions still open

| Topic | Choices | Decision |
|--------|---------|----------|
| Gemini | API key vs Vertex (company cloud) | _TBD_ |
| Hosting | Cloud Run vs small server | _TBD_ |
| Slack | Extend **ian-bot** vs new bot for linking + Q&A | _TBD_ |
| Who can use Q&A / linking | Allowlist: back office + management | _TBD (exact user list)_ |
| Link messages | Finance channel vs DM | _TBD_ |

---

## IDs to fill in later

| What | ID |
|------|-----|
| Drive root folder | |
| Finance sheet | |
| Slack workspace | |
| ian-bot (Slack app) | |
| Second Slack app (if not extending ian-bot) | |

---

## Code folders (target)

```text
bot/           # Slack: questions + button clicks for linking
ingest/        # Drive, sheet, Gemini, ingest API
core/          # Database, prompts, matching payments to contracts
db/            # schema.sql
docs/          # extra notes if needed
```
