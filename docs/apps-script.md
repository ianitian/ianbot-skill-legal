# Google Apps Script

The Drive monitor and Slack alert script lives in the **Apps Script editor** (not committed here—may contain org-specific URLs).

## Ingest poke

After `sendSlackAlert`, call `pokeIngestWebhook(file)` which `POST`s to:

- URL: Script Property `INGEST_WEBHOOK_URL` (GKE Ingress `/ingest` in prod; ngrok in dev)
- Header: `X-Ingest-Secret` from Script Property `INGEST_WEBHOOK_SECRET`
- Body: `{ drive_file_id, file_name, mime_type, source, triggered_at }`

## Daily sheet sync (planned)

Time-driven trigger → `syncSheetToBackend()` → `POST /sync/sheet` with the same secret header.

See internal script source for full implementation.
