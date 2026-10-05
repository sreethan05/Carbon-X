# AGENTS.md — CarbonX project context

Quick reference for anyone (human or agent) working in this repo. Keep it updated when setup or
schema changes.

> **Note:** this file intentionally contains **no** project references, credentials, tokens,
> account emails or infrastructure identifiers. Use placeholders and your own `.env` files.

## Project overview

CarbonX (also referred to as GraminCarbon) is an agri carbon-credit platform. Farmers register via
phone OTP, map their farm boundary, get satellite-verified credits through a simplified VM0042-style
calculation, and list them on a marketplace where corporates/FPOs buy. FPOs bridge farmers who
cannot self-onboard and resolve the verification queue.

## Where things live

| Path | What it is | Port / entry |
|---|---|---|
| `src/` | Main app — React 18 + Vite + Tailwind. **This is the primary frontend.** | `npm run dev` → 5000 |
| `backend/app/` | Python FastAPI service (satellite scan, ML, OTP auth, Supabase access, trust layer) | `uvicorn app.main:app` → 8000, proxied at `/py-api` |
| `supabase/` | Schema + incremental migrations (apply in order) | — |
| `scripts/` | Seed and demo-data generators | — |
| `docs/` | `ARCHITECTURE.md` (canonical design), `DEPLOYMENT.md` | — |
| `legacy/` | Retired Node/Express + Solidity code. **Not part of the running system.** | — |

## Running locally

```bash
cp .env.example .env              # root: Supabase URL + anon key
cp .env.example backend/.env      # backend: service-role key, JWT secret, integrations
npm install && npm run dev        # frontend on :5000
cd backend && pip install -r requirements.txt && uvicorn app.main:app --reload --port 8000
```

## Configuration

All configuration is environment-driven; see `.env.example` for the full list. Key groups:

- **Supabase** — `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` (backend), `VITE_SUPABASE_URL` + `VITE_SUPABASE_ANON_KEY` (frontend).
- **Satellite** — `GEE_PROJECT`, `GEE_KEY_PATH` (Google Earth Engine service account).
- **Voice** — `SARVAM_API_KEY`, `SARVAM_DEFAULT_LANGUAGE` (default `te-IN`), `SARVAM_*_MODEL`.
- **OTP** — `TEXTPLATE_API_TOKEN`, `TEXTPLATE_TEMPLATE_ID`, `REDIS_URL`.
- **Dev only** — `CARBONX_ALLOW_DEV_OTP=1` returns the OTP in the API response and sends no SMS. **Never set in production.**

Never commit real credentials, private keys, service-account files or tokens. `.gitignore` already
excludes `.env`, key files and credential JSON — keep it that way.

## Database

Ten tables (see `supabase/schema.sql` and the numbered migrations):

`profiles`, `farms`, `fpos`, `corporates`, `land_registry`, `fpo_members`,
`kyc_verifications`, `marketplace_listings`, `otp_codes`, `ledger_events`.

`ledger_events` stores the hash chain; `payload_json` holds the exact canonical text the hash
covers, so verification is byte-exact. Backend access uses the service-role key; the frontend uses
the anon key.

## Trust layer (do not duplicate)

- **Credit maths lives in exactly one place:** `backend/app/services/credits.py` →
  `credit_engine`. Do not add a second formula anywhere.
- **No fabricated data.** If satellite data is unavailable, the API returns
  `credits_available: false` and issues no credit. Never invent an NDVI.
- **Splits** — `split_engine.py` runs in integer paise; the farmer 70% floor can never be diluted.
- **Ledger** — append only via `ledger.append_event(...)`; verify with `ledger.verify_chain(...)`.

## Testing

```bash
cd backend && python -m unittest discover tests -v
```

Hermetic tests (trust layer, Aadhaar, ML, endpoint contracts) run anywhere. Integration tests are
decorated `@requires_supabase` and skip cleanly when Supabase is not configured — this keeps CI
green with credentials blanked. CI (`.github/workflows/ci.yml`) runs frontend lint+build and the
backend suite.

## Conventions

- Python: FastAPI + pydantic models; services are pure functions where possible.
- Frontend: functional components, hooks, Tailwind; API calls centralised in `src/services/api.js`.
- Response keys (`carbon_credits`, `biodiversity_credits`, `total_credits`) are kept for frontend
  compatibility — `total_credits` is always the canonical engine's number; `biodiversity_credits`
  is a co-benefit indicator and is **not** added to the total.
- Keep `docs/ARCHITECTURE.md` and `README.md` in sync with the code. If a number changes in one,
  change it everywhere.
