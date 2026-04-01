# MEMORY.md — Session Log

This file is updated at the end of every Claude Code session.
It serves as a running log of all changes, decisions, and context built up over time.

---

## Session 1 — 2026-03-23

### Architecture decisions
- Chose **separate Vercel repo per client** over single multi-tenant deployment. Simpler, each client is fully independent. Shared Supabase DB with `client_id` scoping.
- WhatsApp tokens: temporary tokens expire in 24h. Permanent tokens must be generated via Meta Business Manager → System Users (never from the API Setup page).
- Vercel env vars are independent from `.env` — updating `.env` locally does NOT update production. Must update in Vercel dashboard.

### DB changes
- Added `clients` table to `scripts/setup_supabase.sql` — stores all business config per client (credentials, services, hours, bot personality, barbers).
- Added `client_id UUID` foreign key to `conversations` and `appointments` tables.
- `UNIQUE(customer_phone)` on conversations replaced with `UNIQUE(client_id, customer_phone)`.
- Created `scripts/migrate_add_clients.sql` — migration script for existing deployments that already have conversations/appointments tables.

### Code changes
- `api/config.py` — added `CLIENT_ID = os.getenv("CLIENT_ID")`. This UUID ties a Vercel deployment to a row in the `clients` table.
- `api/conversation.py` — all reads/writes now filter and include `client_id` when set.
- `api/appointments.py` — inserts now include `client_id` when set.
- `api/dashboard.py` — `/api/conversations` and `/api/appointments` routes filter by `client_id`. Dashboard title now dynamic via `BUSINESS_NAME` env var (replaces hardcoded "Family Barber").
- `.env.example` — added `CLIENT_ID` field.

### Onboarding flow for new clients
1. Insert row into `clients` table in Supabase with business config.
2. Copy the generated UUID.
3. Duplicate the repo (or use as template).
4. Update `config.py` with client-specific values.
5. Create new Vercel project from that repo.
6. Set all env vars in Vercel including `CLIENT_ID`.
7. Point Meta webhook to new Vercel URL.

---

## Session 2 — 2026-03-23

### Architecture decisions
- Confirmed: **separate repo per client** is the right approach at current scale. One template repo, duplicated per client, each with its own Vercel project and `config.py`. All share one Supabase DB isolated by `client_id`.
- The AI system prompt IS the business logic — different clients don't need different code, they need a different prompt built from their config. No separate repo needed just for AI behavior differences.
- `MEMORY.md` established as the session log for this project. Must be updated at the end of every Claude Code session. Rule added to `CLAUDE.md` under "END OF SESSION".

### New files
- `MEMORY.md` — session log, committed to git so it persists across machines and collaborators.
- `scripts/migrate_add_clients.sql` — migration for existing Supabase deployments to add `clients` table and `client_id` columns to existing tables, with backfill for Family Barber.
- `CLIENT_ONBOARDING_QUESTIONS.md` — gitignored. 22 questions in Spanish (2 sections: technical credentials + business profile) ready to copy into Google Forms for new clients.

### CLAUDE.md changes
- Added **END OF SESSION** section with format template for updating `MEMORY.md` at the end of every session.

### .gitignore changes
- Added `CLIENT_ONBOARDING_QUESTIONS.md`.

### Pending / next steps
- Run `scripts/migrate_add_clients.sql` in Supabase SQL Editor for Family Barber (fill in real credentials before running).
- Add `CLIENT_ID` env var in Vercel dashboard for the Family Barber deployment.
- Future: update `ai_agent.py` to build system prompt dynamically from `clients` table row (currently still reads from hardcoded `config.py`).

---

## Session 3 — 2026-03-30

### Bugs fixed
- **Vercel background tasks killed**: `background_tasks.add_task()` in FastAPI is not reliable on Vercel serverless — the process is frozen after response is sent. Fixed by processing the webhook synchronously in `webhook.py` before returning 200.
- **WhatsApp API version outdated**: Updated from v18.0 to v21.0 in `whatsapp.py`.
- **Wrong WHATSAPP_PHONE_ID**: Old phone ID `1053080334546599` was in `.env`. Correct ID is `1082286704960206` — updated in `.env` and Vercel.
- **Mexico phone number format**: WhatsApp API uses `521XXXXXXXXXX` (with `1` after country code) for Mexican mobile numbers. The allowed list in Meta must use this format (`+5214448023870`), not `524448013870`.
- **Silent WhatsApp send failures**: Added logging to `send_message` to surface API errors with status code, response body, and recipient number.

### Code changes
- `api/webhook.py` — removed BackgroundTasks, process message synchronously; added logging for signature failures and incoming messages.
- `api/whatsapp.py` — updated API version to v21.0; added error logging on send failure; added phone_id/token debug log.

### Architecture notes
- Bot is now fully working end-to-end for test numbers.
- To message any number (real customers), WhatsApp Business Verification must be completed in Meta Business Manager to remove the test recipient restriction.

### Pending / next steps
- Complete WhatsApp Business Verification in Meta Business Manager to go fully live.
- Remove debug logging (phone_id/token prefix) from `whatsapp.py` once confirmed stable.

---

## Session 4 — 2026-03-31

### Bugs fixed
- **Conversations and appointments had no client_id**: `CLIENT_ID` env var was never set in `.env` or Vercel. The old code had a fallback that omitted `client_id` from records and fell back to `on_conflict="customer_phone"`. The DB constraint is `UNIQUE(client_id, customer_phone)` — not unique on `customer_phone` alone. Result: every message inserted a new orphan row with `client_id = NULL` instead of upserting, so conversation history was never loaded and the bot had no memory.

### Architecture decisions
- `client_manager.py` resolves CLIENT_ID in priority order: (1) env var, (2) DB lookup by WHATSAPP_PHONE_ID, (3) auto-create client row from config.py on first run. Cached module-level — one DB round-trip per cold start max.
- Removed all "no CLIENT_ID" fallback paths from conversation.py, appointments.py, dashboard.py. client_id is now always required and always present.

### New files
- `api/client_manager.py` — auto-resolves and caches the CLIENT_ID UUID.

### Code changes
- `api/conversation.py` — always uses `get_client_id()`, upsert always on `client_id,customer_phone`.
- `api/appointments.py` — always includes `client_id` in inserts via `get_client_id()`.
- `api/dashboard.py` — always filters by `client_id` via `get_client_id()`.
- `SKILLS.md` — updated Skill 6 and Skill 9 code snippets; added Skill 13 (client_manager).
- `.env` — added `CLIENT_ID=` placeholder with explanation comment.

### Pending / next steps
- After deploying, check Vercel logs for `[client_manager] Created new client row: <uuid>`.
- Run in Supabase SQL Editor to backfill existing demo data (DO NOT delete — needed for sales demos):
  ```sql
  UPDATE conversations SET client_id = '<uuid>' WHERE client_id IS NULL;
  UPDATE appointments  SET client_id = '<uuid>' WHERE client_id IS NULL;
  ```
- Set `CLIENT_ID=<uuid>` in Vercel env vars to skip the DB lookup on cold starts.
