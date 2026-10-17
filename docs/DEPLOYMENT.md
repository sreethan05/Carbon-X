# Deploying CarbonX

Three pieces: the React frontend (Vercel), the FastAPI backend (Railway or
Render), and Supabase (cloud-hosted, project `<your-project-ref>`).

## 1 · Supabase — source of truth
Project is live. Schema + demo data are seeded. Security posture: RLS enabled
on every table (anon/authenticated denied); the backend talks through the
`service_role` key only. Never expose that key client-side.

## 2 · Backend (FastAPI) — Railway / Render / Fly

1. Create a service from this repo, root directory `backend/`.
2. Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
3. Environment variables (copy from `backend/.env`, **never commit them**):
   - **Database & Auth**:
     - `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`
     - `JWT_SECRET_KEY` (a secure random string >= 32 characters)
     - `CORS_ORIGINS=https://your-frontend.vercel.app,http://localhost:5000`
   - **Cache & Rate-Limiting**:
     - `REDIS_URL` (e.g. `redis://...` for Redis Cloud or container)
   - **Payments & Escrow**:
     - `CARBONX_PAYMENTS_PROVIDER=simulated` (default instant settlement, or `razorpay`)
     - `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET`
   - **Vernacular Voice Agent (Sarvam AI)**:
     - `SARVAM_API_KEY`
     - `SARVAM_DEFAULT_LANGUAGE=te-IN` (supports `te-IN`, `hi-IN`, `en-IN`)
   - **Monitoring & Hardening**:
     - `CARBONX_MONITOR_SECRET` (bearer secret for `POST /monitor/run` external cron triggers)
     - `CARBONX_AUTO_MONITOR=1` (arms in-process 5-day cycle if external cron is not used)
     - `CARBONX_FORCE_HTTPS=1` (enables HSTS header in production)
     - `CARBONX_JSON_LOGS=1` (structured JSON logging for observability)
     - `CARBONX_ALLOW_DEV_OTP=0` (strictly 0 or unset in production)
   - **Earth Engine**:
     - `GEE_PROJECT`
4. Health check path: `/health` — should report `database.ready=true`.
5. Note: Earth Engine needs `earthengine authenticate` credentials or a service account on the host
   for live satellite scans; without them the app degrades to the offline
   estimator automatically.

## 3 · Frontend (Vercel)

1. Import the repo, framework **Vite** (build `npm run build`, output `dist`).
2. `vercel.json` already routes `/py-api/*` and `/bc-api/*` — replace the
   `REPLACE-WITH-YOUR-API` destinations with your Railway/Render URLs.
   (Alternatively skip rewrites and set `VITE_PY_API_BASE` /
   `VITE_BC_API_BASE` env vars to the absolute API URLs — the app supports
   both.)
3. Set the same `VITE_SUPABASE_URL` / `VITE_SUPABASE_ANON_KEY` values from the
   root `.env` (only used by the null-gated Supabase client; harmless).

## 4 · Post-deploy checklist

- `GET <api>/health` → `database.ready: true`, no dev-OTP flag in logs.
- Register a test farmer through the UI (real SMS provider configured, or
  briefly enable `CARBONX_ALLOW_DEV_OTP=1` then turn it off).
- Run a purchase → check `ledger_events` in Supabase and download the PDF
  certificate.
- `POST /monitor/run` once — the in-process scheduler then repeats every 5 days.
- GitHub Actions CI (`.github/workflows/ci.yml`) runs lint + build + the
  300+ test backend suite on every push.

## 5 · Blockchain service (backend/src, port 3001) — enabling the Amoy demo (optional)

`backend/src` (port 3001) mints credits on an EVM chain.

1. `cd blockchain && npm install`
2. Copy `blockchain/.env.example` to `blockchain/.env` → set a burner testnet key.
3. Deploy: `npx hardhat run scripts/deploy.js --network amoy`
4. Write the printed `CARBON_CREDIT_ADDRESS` + `MARKETPLACE_ADDRESS` into
   `backend/.env` (alongside `RPC_URL` and `MINTER_PRIVATE_KEY`), restart the
   Node service (port 3001, `/bc-api` proxy).
5. `GET /bc-api/health` should now report `blockchain: true`.

This is optional — the SHA-256 hash ledger remains the system of record until
on-chain settlement goes live (docs/ROADMAP.md Phase 2).
