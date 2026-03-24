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
