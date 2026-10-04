# Disaster Recovery Runbook

RTO target: 1 hour. RPO: Supabase PITR (see below) + daily ledger export.

## Assets and where they live

| Asset | Primary store | Backup |
|---|---|---|
| Profiles, farms, listings, ledger_events | Supabase Postgres | Supabase dashboard → Database → Backups (daily; PITR on Pro plans) |
| Hash ledger (redundant) | Supabase `ledger_events` | `backend/data/ledger.json` mirror (local file; written by fallback path + migration) |
| Field photos / KYC docs | Supabase Storage | Supabase backups (bucket-level) |
| Code + infra config | GitHub `sreethan05/carbon-x` | — |

## Recovery drills (quarterly — schedule it)

### 1. Supabase PITR restore test
1. Create a scratch Supabase project (free tier).
2. Dashboard → Database → Backups → restore latest to the scratch project
   (or `supabase db dump` via CLI into it).
3. Point a local backend at the scratch project (`SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY`
   in a throwaway `backend/.env`).
4. Verify: `GET /health` → `database.ready=true`; `GET /ledger/<farm-id>` →
   `verified: true` on a known farm; one login OTP flow.
5. Note total wall-clock time — that is your measured RTO. Update this file.

### 2. Ledger file backup/restore test
1. `copy backend\data\ledger.json backups\ledger-<date>.json`
2. Simulate loss: empty the table (`delete from public.ledger_events;`)
3. Restore: the ledger service auto-migrates a present local file on next
   boot — restart the backend and confirm `GET /ops/summary` shows the
   expected `ledger_events` count and `/ledger/<id>` still verifies.
4. Reverse drill: lose the local file, confirm Supabase remains the source
   of truth and `GET /ledger/<id>` still verifies.

### 3. Frontend/backend redeploy drill
1. `npm ci && npm run build` from a clean clone; deploy to Vercel per
   docs/DEPLOYMENT.md.
2. Redeploy backend service from `backend/` (Railway/Render auto-deploys on
   push; verify `/health`).

## Non-negotiables during an incident
- Never hand-edit `ledger_events` rows to "fix" state — a tamper breaks the
  chain visibly by design. Correct forward with new events.
- If Supabase is down: the app degrades to demo mode automatically; do not
  attempt purchases manually until restored (demo store is in-memory).
