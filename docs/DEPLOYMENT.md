# Deploying CarbonX

Three pieces: the React frontend (Vercel), the FastAPI backend (Railway or
Render), and Supabase (already cloud-hosted, project `ihyqhisxgdwxudnxksts`).

## 1 · Supabase — nothing to deploy
Project is live. Schema + demo data are seeded. Security posture: RLS enabled
on every table (anon/authenticated denied); the backend talks through the
`service_role` key only. Never expose that key client-side.

## 2 · Backend (FastAPI) — Railway / Render / Fly

1. Create a service from this repo, root directory `backend/`.
2. Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
3. Environment variables (copy from `backend/.env`, **never commit them**):
   - `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`
   - `JWT_SECRET_KEY` (the long random value already in your `.env`)
   - `CORS_ORIGINS=https://your-frontend.vercel.app,http://localhost:5000`
   - Optional: `GEE_PROJECT`, `CARBONX_ALLOW_DEV_OTP=0` (keep OTP exposure off in prod)
   - Optional: `CARBONX_AUTO_MONITOR=1` (default) arms the 5-day NDVI cycle
4. Health check path: `/health` — should report `database.ready=true`.
5. Note: Earth Engine needs `earthengine authenticate` credentials on the host
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
  39-test backend suite on every push.

## 5 · Blockchain (optional, roadmap)

`backend/src` (port 3001) mints credits on an EVM chain. Set `RPC_URL`
(Polygon Amoy testnet), deployed contract addresses, and minter keys to
enable it. Nothing else depends on it — the hash ledger is the system of
record until on-chain settlement goes live.
