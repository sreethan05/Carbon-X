# Deploying CarbonX to Production

This guide covers production deployment for the CarbonX platform across three core tiers:
1. **Frontend**: React 18 SPA hosted on Vercel or Cloudflare Pages.
2. **Backend**: Python FastAPI service hosted on Railway, Render, Fly.io, or AWS ECS.
3. **Database & Storage**: Remote Cloud Supabase PostgreSQL + Redis cache.

---

## 1. Domain & Network Architecture

```
                  ┌───────────────────────────────┐
                  │ DNS / Cloudflare (SSL/TLS)    │
                  └──────────────┬────────────────┘
                                 │
           ┌─────────────────────┴─────────────────────┐
           ▼                                           ▼
┌─────────────────────────┐                 ┌─────────────────────────┐
│ Frontend SPA (Vercel)   │                 │ Backend API (FastAPI)   │
│ Host: app.carbonx.ag    │ ──────────────> │ Host: api.carbonx.ag    │
│ Origin: Vercel Edge CDN │ HTTPS API calls │ Port: 8000 / $PORT      │
└─────────────────────────┘                 └────────────┬────────────┘
                                                         │
                                        ┌────────────────┴────────────────┐
                                        ▼                                 ▼
                         ┌─────────────────────────────┐   ┌─────────────────────────────┐
                         │ Database (Supabase)         │   │ Cache & Locks (Redis Cloud) │
                         │ Remote Postgres + RLS       │   │ Pub/Sub + Rate Limiting     │
                         └─────────────────────────────┘   └─────────────────────────────┘
```

### Domain Configuration
- **Web App**: `https://app.carbonx.ag` (or `https://<project>.vercel.app`)
- **API Endpoint**: `https://api.carbonx.ag` (or `https://<service>.railway.app`)
- **CORS Setup**: Set `CORS_ORIGINS=https://app.carbonx.ag` on the backend service.

---

## 2. Supabase Database & Security Posture

- **Project Ref**: `ihyqhisxgdwxudnxksts` (source of truth).
- **Row-Level Security (RLS)**: Enabled across all tables. Public anonymous and standard authenticated requests are denied at the database perimeter. The FastAPI backend communicates exclusively using the `SUPABASE_SERVICE_ROLE_KEY`, ensuring that business logic, access scoping, and role enforcement happen centrally in the application service.
- **Seeding Verification**:
  ```powershell
  python scripts/seed_marketplace_data.py
  ```
  Ensures FPO (`FPO-TG-001`), Corporate Buyer (`Telangana Sustainable Agro Pvt Ltd`), Admin (`9000000000`), FPO Officer (`9000000001`), and sample parcels exist.

---

## 3. Backend Deployment (FastAPI on Railway / Render / Fly.io)

### Container & Process Settings
- **Root Directory**: `backend/`
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 4`

### Production Environment Variables

| Variable | Required | Description |
|---|---|---|
| `CARBONX_ENVIRONMENT` | **Yes** | Set to `production` (enforces strict startup validation) |
| `SUPABASE_URL` | **Yes** | Remote Supabase project URL (`https://<project-ref>.supabase.co`) |
| `SUPABASE_SERVICE_ROLE_KEY` | **Yes** | High-privilege service-role key for backend operations |
| `JWT_SECRET_KEY` | **Yes** | Secure random key (>= 32 chars, e.g. `openssl rand -hex 32`) |
| `CORS_ORIGINS` | **Yes** | Comma-separated list of exact `https://` frontend origins only (e.g. `https://app.carbonx.ag`). Wildcards, empty values and plain-http origins are rejected at startup |
| `REDIS_URL` | **Yes** | Managed Redis URI (`redis://...`) for distributed locks, OTP rate limiting and token revocation. The `localhost` default is rejected at startup in production — a single-worker in-memory fallback does not protect a multi-worker deployment |
| `CARBONX_ALLOW_DEV_OTP` | **Must be 0** | **Strictly 0 or unset in production** (startup blocks if enabled) |
| `CARBONX_PAYMENTS_PROVIDER` | **Yes** | `razorpay` for live payments (or `simulated` for a closed pilot) |
| `CARBONX_ACCEPT_SIMULATED_PAYMENTS` | Conditional | **Must be `1` when the provider is `simulated` in production.** Simulated (no-money) settlement is never the silent default; with Razorpay it is rejected outright |
| `RAZORPAY_KEY_ID` | Conditional | Required when `CARBONX_PAYMENTS_PROVIDER=razorpay` |
| `RAZORPAY_KEY_SECRET` | Conditional | Required when `CARBONX_PAYMENTS_PROVIDER=razorpay` |
| `RAZORPAY_WEBHOOK_SECRET` | Conditional | **Required** when `CARBONX_PAYMENTS_PROVIDER=razorpay` (webhook HMAC cannot verify without it) |
| `CARBONX_FORCE_HTTPS` | Recommended | `1` (enforces HTTP Strict Transport Security header) |
| `CARBONX_JSON_LOGS` | Recommended | `1` (formats all server logs as structured JSON) |
| `CARBONX_MONITOR_SECRET` | Recommended | Bearer secret for external monitoring cron triggers |
| `SARVAM_API_KEY` | Optional | Voice assistant API key for Telugu/Hindi/English speech recognition |
| `GEE_PROJECT` | Optional | Google Earth Engine project ID (`carbonx-507617`) |

---

## 4. Frontend Deployment (React on Vercel)

1. Connect the GitHub repository in Vercel.
2. Select Framework Preset: **Vite**.
3. **Build Command**: `npm run build`
4. **Output Directory**: `dist`
5. **Environment Variables**:
   - `VITE_PY_API_BASE`: The full public URL of your backend API (e.g., `https://api.carbonx.ag`).
6. **Routing (`vercel.json`)**:
   `vercel.json` provides clean single-page application (SPA) client-side routing fallback:
   ```json
   {
     "$schema": "https://openapi.vercel.sh/vercel.json",
     "framework": "vite",
     "rewrites": [
       { "source": "/(.*)", "destination": "/index.html" }
     ]
   }
   ```
   No unresolvable placeholder hosts are present in the configuration.

---

## 5. Post-Deployment Verification Checklist

1. **Health Check**:
   `GET https://api.carbonx.ag/health`
   Verify:
   - `database.ready`: `true`
   - `redis.ready`: `true`
   - `dev_otp`: `false` (dev OTP disabled)
2. **Authentication & Role Scoping**:
   - Attempt login with valid phone OTP. Confirm response does not leak `dev_otp`.
   - Access role-guarded endpoints (`/fpo/dashboard`, `/admin/dashboard`, `/corporate/dashboard`).
3. **Marketplace & Escrow**:
   - Browse listings on `GET /marketplace/listings`. Verify `farmer_phone` is redacted for third-party callers.
   - Confirm the payment mode is intentional: `GET /payments/config` must show
     the provider you expect. In a Razorpay deployment a test order must settle
     only through the **signature-verified webhook** (browser redirects prove
     authorization only); in a pilot deployment `simulated` must match
     `CARBONX_ACCEPT_SIMULATED_PAYMENTS=1` and be labelled as simulated in the UI.
   - Execute purchase and download certificate PDF from `GET /certificates/{cert_id}/pdf`.
4. **Monitoring Cycle**:
   - Trigger `POST /monitor/run` with `X-Monitor-Secret: <CARBONX_MONITOR_SECRET>`. Verify 200 OK.
5. **Staging smoke suite**:
   - `python scripts/staging_smoke.py --base https://staging-api.<domain> [--token <JWT>]`
     checks health/dev-OTP state, public redaction on listings + certificate CSV,
     validation labels/claims, privacy policy, `/metrics` and websocket route
     behaviour. Wire this into a 5-minute synthetic cron once staging exists —
     `/metrics` thresholds and alert wiring are defined in `docs/OPS_TARGETS.md`.

Startup behaviour summary: in `CARBONX_ENVIRONMENT=production` the process
**refuses to start** unless `JWT_SECRET_KEY` (>=32 chars, not a placeholder),
`SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY`, a managed `REDIS_URL`, https-only
`CORS_ORIGINS`, and an explicit payment mode (`razorpay` with all three
Razorpay credentials, or `simulated` with `CARBONX_ACCEPT_SIMULATED_PAYMENTS=1`)
are configured, and unless `CARBONX_ALLOW_DEV_OTP` is disabled.

Dependency/supply-chain updates follow `docs/SECURITY_UPDATES.md` (Dependabot +
the weekly report-only audit workflow; severity-triaged, no silent bumps).
