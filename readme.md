# ian-bot-legal — contract & payment assistant

A plan to build an **internal Slack assistant** that answers questions about:

- **Signed contracts** (PDFs in a Google Drive folder tree), and
- **Payments** (rows in a finance Google Sheet).

The system keeps a **searchable catalog in Postgres** (a normal database) and uses **Google Gemini** to read contracts once and to write answers—but we are **not training a custom AI model**. When new files or rows appear, we **refresh the catalog**; that is not “training.”

---

## What we’re building (big picture)

| Piece | What it does |
|--------|----------------|
| **Google Drive** | Official home for signed PDFs (inbox + subfolders). Each file has a permanent **file ID** that stays the same when the file is moved between folders. |
| **Finance Google Sheet** | Official log of payments (date, amount, payee, etc.). Each row can link to one contract via **`contract_ref`**. |
| **Existing Apps Script** | Already watches Drive and sends **alerts** in Slack when a new PDF shows up. We will extend it to **tell the catalog service to index** new files. |
| **Catalog / ingest service** | Backend that reads a PDF, asks Gemini to pull out key fields, and saves everything to Postgres. Also copies sheet rows into Postgres. |
| **Slack — payment linking** | When finance marks a row “ready to link,” Slack shows **a few likely contracts as buttons**. Finance picks one; the sheet’s **`contract_ref`** is filled in. |
| **Slack — Q&A bot (new app)** | A **separate** bot for questions like “How much did we pay on the ABC deal?” Answers use **only** Postgres + short Gemini summaries, with links back to Drive. |

```text
  Drive (PDFs)
       |
       v
  Apps Script ----alert----> Existing Slack bot (unchanged idea)
       |
       +---- "index this file" ---> Ingest + Gemini ---> Postgres

  Finance Sheet
       |
       |  finance checks "link to contract"
       v
  Slack message with buttons ---> finance picks ---> contract_ref on sheet
       |
       v
  Sheet sync ---> Postgres

  New Q&A Slack bot ---> reads Postgres + Gemini ---> answers in DM
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
6. The sheet column **`contract_ref`** is updated (Drive link or file ID).
7. The next **sheet sync** copies that link into Postgres so the Q&A bot can add up payments correctly.

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
- [ ] Add sheet columns: **`contract_ref`**, link **status**, and a **“Link to contract”** checkbox (or similar).
- [ ] Decide where Slack link messages go (finance channel vs direct messages).
- [ ] Create a **service account** that can only access the contract folder and the finance sheet (sheet needs write access for `contract_ref`).
- [ ] Store passwords/tokens safely: Slack bots, Gemini, database URL, webhook secret.

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

- [ ] Keep today’s behavior: new PDF → **alert** in Slack (existing bot).
- [ ] After the file is in the tree, call the ingest service with its **file ID**.
- [ ] Protect the webhook (shared secret).
- [ ] Avoid indexing the same file twice in a row (debounce).
- [ ] Optional: add “catalog updated” or “index failed” to the alert.
- [ ] When finance checks “link to contract,” trigger the Slack linking flow (from script or backend).
- [ ] Remember: moving a PDF between subfolders **does not change** its file ID.

### Phase 4 — New Slack bot for questions (Q&A)

- [ ] New Slack app, separate from the alert bot (and clarify if linking uses the same app or another).
- [ ] Connect the app to our server; handle button clicks for linking and messages for Q&A.
- [ ] Start with **direct messages only**; only allow specific Slack users.
- [ ] Look up contracts and payments in Postgres; add up payments in the database (not in AI).
- [ ] Ask Gemini to write a clear answer **only from that data**; include contract name and Drive link.
- [ ] If data is missing or unlinked, say so—don’t invent contract terms.

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
5. **Q&A Slack bot** in DMs.
6. Aliases, golden questions, production deploy.

---

## Decisions still open

| Topic | Choices | Decision |
|--------|---------|----------|
| Gemini | API key vs Vertex (company cloud) | _TBD_ |
| Hosting | Cloud Run vs small server | _TBD_ |
| Slack apps | One app for linking + Q&A vs two | _TBD_ |
| Link messages | Finance channel vs DM | _TBD_ |

---

## IDs to fill in later

| What | ID |
|------|-----|
| Drive root folder | |
| Finance sheet | |
| Slack workspace | |
| Q&A Slack app | |
| Alert / linking Slack app(s) | |

---

## Code folders (target)

```text
bot/           # Slack: questions + button clicks for linking
ingest/        # Drive, sheet, Gemini, ingest API
core/          # Database, prompts, matching payments to contracts
db/            # schema.sql
docs/          # extra notes if needed
```
