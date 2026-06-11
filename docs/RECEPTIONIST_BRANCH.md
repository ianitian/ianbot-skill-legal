# feature-receptionist branch

Experimental **receptionist** orchestration: rapidfuzz proposes FAQ candidates; Vertex (Phase 2) decides whether a canned FAQ answer is sufficient or generates a natural reply.

**Branch:** `feature-receptionist`  
**Main** continues the standard ladder unchanged until this is merged.

## Architecture

```text
echo → receptionist (if BOT_RECEPTIONIST_ENABLED)
         ├─ Phase 1 scaffold: stub reply + fuzzy candidate metadata
         └─ Phase 2: Vertex JSON decision → use_faq | generate | decline
       OR legacy (flag off): faq → fallback
```

Indexed DB and Drive Q&A are **disabled** on this branch until B1 is merged from `main`.

## Env flags

```bash
BOT_RECEPTIONIST_ENABLED=false      # default; same behavior as main
BOT_RECEPTIONIST_FAST_FAQ_SCORE=95  # Phase 2: skip Vertex when fuzzy score very high
BOT_RECEPTIONIST_GRAY_LOW=40        # Phase 2: gray-zone gating
BOT_RECEPTIONIST_CANDIDATE_LIMIT=3  # top FAQ candidates sent to receptionist
```

Requires `GEMINI_ENABLED` + Vertex/Studio config for `bot_receptionist_configured: true` in `/health` (live gate is Phase 2).

## Phase 1 (scaffold — current)

- `match_top_candidates()` in `core/bot_faq.py`
- `handle_receptionist()` stub in `bot/handlers/receptionist.py`
- `BOT_RECEPTIONIST_ENABLED=true` returns a scaffold message (no Vertex call)
- `BOT_RECEPTIONIST_ENABLED=false` matches `main` dispatch (faq → fallback)

## Phase 2 (not implemented yet)

1. `generate_json()` in `core/gemini_client.py` (text-only chat)
2. Wire `core/bot_receptionist.decide()` to Vertex using `core/prompts/receptionist.txt`
3. Fast-path / gray-zone rules from env
4. On `use_faq`, return deterministic YAML answer (not Vertex paraphrase)
5. Telegram manual test; then merge criteria to `main`

## Keep branch synced with main

```bash
git checkout feature-receptionist
git fetch origin && git merge origin/main
pytest tests/ -q
git push
```

Conflict-prone files: `bot/handlers/dispatch.py`, `core/config.py`, `bot/schemas.py`, `.env.example`. Prefer adding logic in new modules (`core/bot_receptionist.py`, `bot/handlers/receptionist.py`).

## A/B testing later

- Same deployment, toggle `BOT_RECEPTIONIST_ENABLED`
- Or two envs: `main` image vs `feature-receptionist` image

Compare `handler` and `handler_metadata` in logs (`faq` vs `receptionist`).
