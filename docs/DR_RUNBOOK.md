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

### 4. Automated Backup Utility
A complete snapshot of all remote Postgres tables, the local hash ledger, and
on-disk evidence photos can be generated and verified at any time:
```powershell
# Create timestamped tar.gz in backups/
python scripts/backup_data.py

# Verify archive integrity and manifest
python scripts/backup_data.py --verify backups/carbonx_backup_<timestamp>.tar.gz
```
Backups should be cron-scheduled daily or run prior to major schema migrations.

## Webhook & Background Job Monitoring

### 1. Payment Webhook Monitoring
Razorpay webhooks are processed at `POST /payments/webhook` with HMAC-SHA256 signature verification.
- **Log identifier**: `logger="carbonx.payments"`
- **Critical alarm**: Any log line matching `PAYMENT CONFLICT — captured payment <pay_id> for order <order_id> could not be settled` indicates that a listing was purchased or modified concurrently after payment capture.
- **Action**: The webhook handler logs conflict details and marks the order `conflict_refund_required`. Operations must issue a reversal via the Razorpay dashboard within 1 hour.
- **Health indicator**: `GET /health` reports Razorpay payment provider status.

### 2. 5-Day Monitoring Cycle
- The background Sentinel-2 revisit monitor runs via `CARBONX_AUTO_MONITOR=1` in-process or externally via GitHub Actions (`.github/workflows/monitor.yml`).
- If an Earth Engine query or database update fails, it logs `logger="carbonx.monitor"`.
- Verify the latest monitoring cycle: `GET /passport/{farm_id}` inspects the `monitoring.last_revisit_at` and `monitoring.status` fields.

## Incident Response Matrix & SLAs

| Incident Type | Primary Lead | Contact / Desk | Target Response | Target Resolution | Escalation Path |
|---|---|---|---|---|---|
| **P0: Complete Outage** (App or DB down) | DevOps / Infrastructure Lead | `oncall@carbonx.ag` | < 15 minutes | < 1 hour (RTO) | CTO / Co-founder |
| **P1: Payment / Checkout Dispute** (Failed capture, double charge) | Operations & Finance Desk | `payments@carbonx.ag` | < 1 hour | < 24 hours | Finance Lead |
| **P1: Data Privacy Incident** (DPDP Act 2023 breach or leak) | Data Protection Officer (DPO) | `privacy@carbonx.ag` | < 2 hours | < 72 hours (statutory DPBI notice) | Legal Counsel / Board |
| **P2: Degraded Satellite Scan** (Earth Engine quota / slow jobs) | ML & Remote Sensing Lead | `mrv@carbonx.ag` | < 4 hours | < 1 business day | Engineering Lead |

### Privacy Incident Protocol (DPDP Act 2023)
In the event of an unauthorized disclosure of farmer personal identifiable information (e.g. phone, full Aadhaar, or precise GPS):
1. **Containment**: Immediately revoke compromised API tokens via `POST /logout` or Redis flush, and restrict public access to affected endpoints.
2. **Impact Assessment**: Determine the exact scope of data principals affected within 24 hours.
3. **Statutory Notification**: If personal data of farmers is breached, notify the Data Protection Board of India (DPBI) and the affected data principals in writing within 72 hours as mandated by DPDP Act 2023.

## Non-negotiables during an incident
- Never hand-edit `ledger_events` rows to "fix" state — a tamper breaks the
  chain visibly by design. Correct forward with new events.
- If Supabase is down: the app degrades to demo mode automatically; do not
  attempt purchases manually until restored (demo store is in-memory).
