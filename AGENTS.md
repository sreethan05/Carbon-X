# AGENTS.md — CarbonX Project Context

Quick-reference for agents working on this repo. Update when setup/schema changes.

## Project Overview

CarbonX is an agri carbon + biodiversity credits marketplace. Farmers register via phone OTP, map farms with GEE satellite imagery, get AI-scanned credits, and list them on a marketplace where corporates/FPOs bid.

- Main app: repo root (`src/`), React 18 + Vite + Tailwind. `npm run dev` → port 5000.
- `backend/` — Python FastAPI (GEE satellite scan, ML, phone OTP auth, Supabase service-role access) → port 8000. Proxied via `/py-api`.
- `backend/` (Node) — blockchain minting API → port 3001. Proxied via `/bc-api`.
- Local schema SQL lives in `supabase/` (`01_sreethan_initial_schema.sql`, `02_hasini_merged_schema.sql`, `schema.sql`).

## Supabase (source of truth: remote DB)

**ACTIVE PROJECT (since 2026-10-04): sreethan05's own "CarbonX" — ref `ihyqhisxgdwxudnxksts`, region Southeast Asia (Singapore), org `qdjrdxufhdhzqpavnvpt` (own org, alongside "Agri").**

- **URL:** `https://ihyqhisxgdwxudnxksts.supabase.co`
- Env vars: root `.env` → `VITE_SUPABASE_URL` + `VITE_SUPABASE_ANON_KEY`; `backend/.env` → `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` (write access). Keys are fetched via `npx supabase projects api-keys --project-ref ihyqhisxgdwxudnxksts` (CLI logged in on this machine, token in Windows Credential Manager under `Supabase CLI:supabase`).
- Schema completed 2026-10-04 (10 tables): the 7 core tables plus `fpos`, `corporates`, `land_registry` (empty — old 30 Telangana parcels were in the old project), `fpo_members`, `ledger_events` (hash-chain store, service_role granted).
- Demo data seeded via `python scripts/seed_marketplace_data.py` (defaults to this ref; override with `SUPABASE_PROJECT_REF`).

**LEGACY PROJECT (do not use): `rbdyzeuucgqkhlikbpnd`** — old "CarbonX" in hasini.four@gmail.com's org (Sydney). Kept here only for history.

### Working CLI commands (no password prompt — use CLI login role)

```powershell
supabase orgs list
supabase projects list
supabase inspect db table-stats --project-ref ihyqhisxgdwxudnxksts
supabase gen types typescript --project-id ihyqhisxgdwxudnxksts --schema public
```

CLI quirks:

- `gen types` uses `--project-id`, NOT `--project-ref`.
- `supabase db dump` HANGS on this machine (no local `pg_dump` installed). Use `gen types` or `inspect db` commands instead to inspect the remote schema.
- `remote-schema-info` subcommand does not exist in v2.116.0.

## Database Schema (public schema, verified 2026-09-10 via `supabase gen types`)

7 tables, no views, no enums, no custom functions. IDs are uuid (text); timestamps are timestamptz. No RLS noted on any table (service-role access used by backend).

### profiles
Farmers/users. PK `id`. Unique: `phone` (identity key across the app).
Columns: `id`, `phone` (unique), `name`, `role`, `fpo_id` (FK → `fpos.id`), `upi`, `aadhaar_last4`, `state`, `district`, `village`, `preferred_language`, `wallet_address`, `created_at`, `updated_at`
Indexes: `profiles_pkey`, `profiles_phone_key`, `profiles_fpo_id_idx`

### fpos
Farmer Producer Organizations. PK `id`. Unique: `registration_no`. (No `password` column — see OTP storage notes below.)
Columns: `id`, `name`, `registration_no` (unique), `password`, `created_at`, `updated_at`
Indexes: `fpos_pkey`, `fpos_registration_no_key`

### farms
Farm boundaries + satellite/AI credit estimates. PK `id`. FK `owner_phone` → `profiles.phone`.
Columns: `id`, `name`, `owner_phone`, `status`, `crop_type`, `area_hectares`, `ndvi`, `evi`, `soil_moisture`, `tree_cover`, `vegetation_health`, `satellite_source`, `ai_confidence`, `carbon_tonnes`, `total_credits`, `biodiversity_credits`, `biodiversity_score`, `token_id`, `geojson` (Json), `irrigation`, `created_at`, `updated_at`
Indexes: `farms_pkey`, `idx_farms_owner`

### kyc_verifications
KYC document verification log. PK `id`. FK `owner_phone` → `profiles.phone`.
Columns: `id`, `owner_phone`, `document_name`, `document_sha256`, `perceptual_hash`, `status`, `checks` (Json), `extracted_fields` (Json), `reasons` (Json), `created_at`
Indexes: `kyc_verifications_pkey`, `kyc_verifications_owner_phone_idx` (owner_phone, created_at), `kyc_verifications_document_sha256_idx`

### marketplace_listings
Credit listings for sale. PK `id`. FKs: `farm_id` → `farms.id`, `farmer_phone` → `profiles.phone`.
Columns: `id`, `farm_id`, `farmer_phone`, `farmer_name`, `crop`, `location`, `size_label`, `listing_model`, `price_per_credit`, `current_bid`, `bids_count`, `total_credits`, `carbon_credits`, `biodiversity_credits`, `status`, `expires_at`, `image_url`, `token_id`, `tx_hash`, `created_at`, `updated_at`
Indexes: `marketplace_listings_pkey`, `idx_listings_status`, `marketplace_listings_status_idx`, `marketplace_listings_farmer_phone_idx`

### OTP storage
Phone OTPs are stored in Redis at runtime under `carbonx:otp:<phone>` with a
10-minute TTL and a 5-attempt limit; if Redis is unreachable an in-process
memory fallback is used. The legacy `otp_codes` Supabase table remains in the
schema for compatibility but is not used by the authentication pipeline.

`backend/.env` (gitignored) supports `CARBONX_ALLOW_DEV_OTP=1`: when the SMS
provider is configured but delivery fails (trial/blocked gateway), the real
stored OTP is returned in the send-otp response so local flows stay testable.
Never set this in production.

### corporates
Corporate buyers. PK `c_id` (auto int).
Columns: `c_id`, `name`, `password_hash` (bcrypt), `created_at`, `updated_at`
Index: `corporates_pkey`
Seeded demo account: "Telangana Sustainable Agro Pvt Ltd" / "Corporate@2026"
(via `POST /corporate/login`).

### Other live tables (verified 2026-10-03 via PostgREST OpenAPI)
- `land_registry` — 30 rows of Telangana survey parcels (survey_number,
  owner_name, area_ha, village, mandal, tier, registry_geometry_available).
- `farms.badge` and `farms.fpo_id` exist.
- `fpos` has NO `password` column (older docs claimed one): FPO officers log in
  through the farmer phone-OTP pipeline; a profile with `role='fpo'` unlocks
  the FPO desk. Demo officer profile: phone `9000000001`.
- There are NO `orders` or `certificates` tables (and no Supabase CLI token on
  this machine, so DDL is not possible). Purchases are persisted by updating
  `marketplace_listings` (status Sold/Retired, `tx_hash` escrow ref,
  `current_bid`), and certificate ids are derived deterministically from the
  listing id (`CX-<year>-CERT-<first 8 hex chars>`).

### Relationship map

```
profiles (phone) ←── farms.owner_phone
profiles (phone) ←── kyc_verifications.owner_phone
profiles (phone) ←── marketplace_listings.farmer_phone
profiles (fpo_id) ──→ fpos (id)
farms (id) ←── marketplace_listings.farm_id
```

## Trust & transparency layer (added 2026-10-04)

Core payout/trust services live in `backend/app/services/`:

- `split_engine.py` — conditional split: farmer 70% floor, FPO 5% only when
  involvement is proven (farm `fpo_id` live / `fpo` on sample farmers),
  platform keeps the rest (25% with FPO / 30% without). Integer-paise math.
- `ledger.py` — tamper-evident SHA-256 hash chain per farm
  (ISSUE → SALE → SPLIT → RETIRE). Persists to `backend/data/ledger.json`
  (gitignored; `CARBONX_LEDGER_PATH` overrides). `GET /ledger/{farm_id}`
  returns + verifies the chain.
- `credit_engine.py` — VM0042-style 5-step estimate (additionality delta,
  biomass proxy, IPCC-style soil factor, raw total, 10–30% uncertainty
  deduction from evidence quality). Powers `POST /farms/earnings-calculator`
  (open, no auth) and the passport `trust` block.
- `market_store.py` — in-memory listings store seeded from `sample_data`;
  the fallback for buy/auto-match/wallet/certificates when the DB is off.

Endpoints: `POST /marketplace/buy` now runs escrow → conditional split →
ledger events → **instant retirement** (full buys mark listings `Retired`,
not `Sold`) and returns the split lines + `batch_hash`. `/wallet` returns
`farmer_share_total` / `fpo_share_total` / `platform_share_total` + per-tx
`ledger_hash`. `/passport/{id}` adds `expected_earnings`, `trust`, `ledger`
and serves a demo farm for any unknown id when the DB is off.
`POST /demo/login` issues a demo farmer JWT **only when the DB is
unconfigured**; the farmer login page shows a demo button in that state.

Frontend: Marketplace buy modal shows a purchase-proof screen (split + hash);
`CarbonWallet` has split columns + demo-session entry;
`DetailedFarmAnalytics` has the Trust Engine & Ledger card;
`EarningsCalculator` component is on the farmer dashboard.

## Production hardening (added 2026-10-04, late)

- **Trust Engine Stage 1** lives in `credit_engine.stage1_verification`:
  declared crop vs per-crop NDVI signature windows; mismatch saves the farm
  PENDING with credits blocked (FPO queue) — never auto-reject. Enforced
  server-side in `/analyze` (returns `stage1`) and `/save-farm`.
- **5-day monitoring**: `POST /monitor/run` compares `farms.ndvi` vs
  `last_monitor_ndvi` (drop >= 0.15 -> status Flagged + ledger MONITOR event).
  An in-process scheduler (`CARBONX_AUTO_MONITOR=1`, default) runs it at boot
  (+90s) and every 5 days. Passport exposes a `monitoring` block.
- **Certificate PDFs**: `GET /certificates/{cert_id}/pdf` renders a
  Verra-style PDF (reportlab, `app/services/certificate_pdf.py`).
- **Security**: real random `JWT_SECRET_KEY` in `backend/.env`; OTP sends
  rate-limited (3 per phone / 10 min, in-process — move to Redis for
  multi-worker); RLS enabled on ALL tables (anon/authenticated denied —
  backend uses service_role which bypasses RLS; nothing client-side reads
  Supabase directly).
- **Tests**: `backend/tests/test_trust_layer.py` (39 tests total) covers
  split math, ledger tamper-detection, credit engine, Stage 1. Run from
  `backend/`: `python -m unittest discover tests`. CI (`.github/workflows/ci.yml`)
  runs frontend lint+build and the backend suite on every push.
- **Land registry**: 30 Telangana parcels seeded via
  `scripts/seed_land_registry.py` (idempotent, deterministic).
- **PWA-lite**: manifest + conservative service worker (app shell offline;
  API calls always network-only), registered in production builds only.
- **Deploy**: `vercel.json` (rewrites `/py-api/*` — replace placeholder) +
  `docs/DEPLOYMENT.md`. API bases are env-aware (`VITE_PY_API_BASE`).


## Scientific/ops layer (added 2026-10-04, latest)

- **Canonical carbon formula**: `credit_engine.quick_scan_estimate` is the
  single source of truth — `/analyze` uses it (scan-only evidence quality);
  the old ad-hoc `area x tree_cover x 0.12` formula was removed. Every
  estimate now carries `ci90` (statistical interval from the uncertainty
  fraction) plus provenance (`s2_scene` system:index, `ml_source`).
- **Ground-truth calibration**: `ground_truth_samples` table +
  `POST /ops/ground-truth` + `GET /ops/ground-truth/eval` (estimate-vs-
  measured error; honest empty state until field data exists).
- **Ops**: `GET /ops/summary` (read-only counts, no PII).
- **Scripts**: `scripts/tamper_demo.py` (ledger tamper-detection demo),
  `scripts/simulate_scale.py` (throughput + unit economics),
  `scripts/seed_land_registry.py`.
- **Docs suite**: docs/{MRV_METHODOLOGY, MODEL_CARD, ECONOMICS, COMPLIANCE,
  IMPACT_MODEL, DEMO_SCRIPT, ROADMAP, DEPLOYMENT, PILOT_MOU_TEMPLATE, ARCHITECTURE}.md.
  README rewritten (was stale/Express claims); LICENSE (MIT) + CONTRIBUTING added.
- **Biodiversity model v2 (honest)**: trained on real GBIF species richness
  (log1p) with real Sentinel-2 features via Earth Engine; v1 was circular
  (label = formula of its own features) and retired — see docs/MODEL_CARD.md.
  Serving refuses fabricated features (NDVI-only heuristic fallback, labelled
  via `ml_source`). Retrain: src/{download_gbif,aggregate_richness,
  extract_sampled,train}.py then copy artifacts/* to backend/ml/models/.


## Production audit hardening (2026-10-04, latest — 35-item audit)

- **Schema**: `supabase/07_production_schema.sql` (idempotent, applied live):
  ground_truth_samples, hot-path indexes, pg_trgm GIN indexes for
  marketplace ilike search, soft-delete columns, monitor snapshot columns,
  RLS posture note.
- **Security**: CSP/X-Frame/nosniff headers + optional HSTS
  (`CARBONX_FORCE_HTTPS=1`); distributed OTP limiting via Redis ZSET
  (`redis_store.otp_send_rate_limited`, memory fallback); `/monitor/run`
  accepts `X-Monitor-Secret` (`CARBONX_MONITOR_SECRET`) for external cron —
  `.github/workflows/monitor.yml` runs the 5-day cycle when deployed
  (in-process scheduler stays the no-config default).
- **Reliability**: EE calls have exponential backoff + 10-min analyze cache +
  strict GeoJSON polygon validation; ledger migration is race-safe
  (`on_conflict ignore_duplicates`, retry-until-success); certificate PDFs
  cached in memory; uniform error envelope on ALL failures (incl. 404/422);
  Prometheus `/metrics`; `X-Request-ID` on every response; JSON logging for
  `carbonx.*` loggers (`app/logging_setup.py`).
- **New endpoint**: `POST /fpo/login` — registration_no -> OTP to the linked
  officer's phone (step 2 is the standard OTP login).
- **Tests**: 48 total, hermetic (tests force demo mode POST-IMPORT because
  `load_dotenv(override=True)` re-reads backend/.env — see the reset block in
  test files; `CARBONX_TEST_LIVE_DB=1` opts the old DB-coupled suite into a
  live run). 15 API integration tests cover buy->split->ledger->retire,
  validation envelopes, error shapes.
- **Ops**: `load-tests/k6_carbonx.js`, `docs/DR_RUNBOOK.md`, passport CSV
  export, SW stale-while-revalidate for public listings only (money paths
  stay network-only), Dependabot, `blockchain/.env.example` + Amoy deploy
  steps in docs/DEPLOYMENT.md.
- **Deferred with rationale**: docs/BACKLOG.md (#16 /v1, #18 React Query,
  #19 Zod, #20 full i18n, #27 monsoon gap-fill, #28 registry listing,
  #29 mobile, #35 corporate portfolio).


## Code-quality audit round (2026-10-04, latest)

- Error envelope now carries machine codes (`UNAUTHORIZED`/`FORBIDDEN`/
  `NOT_FOUND`/`BAD_CURSOR`/…) for frontend routing; `X-Request-ID` is in
  every `carbonx.*` JSON log record (contextvar set by middleware).
- `/analyze`: GeoJSONPolygon Pydantic model (`extra=forbid` + field_validator),
  early >10,000 ha scan guard, parallel EVI/feature/area EE queries
  (ThreadPoolExecutor), `quick_scan_estimate` TTL cache, FORMULA_VERSION
  recorded in estimates and ledger ISSUE snapshots.
- `/marketplace/listings`: opaque `cursor`/`next_cursor` pagination
  (base64 offset — keyset upgrade documented); `/predict` and `/analyze`
  always include `ml_source`; `/marketplace/buy` rejects listings whose farm
  no longer exists (no ledger writes against phantom farms).
- `WebSocket /ws/ledger/{farm_id}`: in-process pub-sub in the ledger pushes
  events to the passport instantly (frontend falls back to 15s polling);
  vite proxy has `ws: true`.
- `POST /ops/ground-truth/calibrate`: per-crop factor suggestions when
  N>=30 (never auto-applies — governance decision).
- `farms.credits_ci90_low/high` persist the statistical interval at
  enrollment; passport exposes `credits_ci90`.
- `app/config.py` centralizes constants; `app/supabase_db.py` has TypedDict
  row shapes; sample_data is lazy (production paths never import it);
  `_polygon_area_hectares` delegates to polygon_service; `extra=forbid` on
  money models; backend `pyproject.toml` + `py.typed`.
- Removed: `frontend/` (deprecated legacy UI), `src/lib/supabase.js`,
  `backend/src/routes/farms.js`. Kept `backend/src/` (standalone optional
  Amoy minting service, documented — NOT dead) and the `.kilo` gitignore
  line (defensive against tool recreation).
- Deferred: main.py router split (2.9k lines, pure churn without behavior
  gain at this stage — trigger: second backend contributor).

## Commands

```powershell
npm run dev        # root app, port 5000
npm run build      # vite build
npm run lint       # eslint .
cd backend; uvicorn app.main:app --reload --port 8000   # Python API
python scripts/seed_marketplace_data.py                 # seed sample marketplace data
```

## Running with credentials removed (verified 2026-10-04)

With `VITE_SUPABASE_*`, `SUPABASE_*`, and SMS/OTP provider vars blank, the full
stack still boots and degrades cleanly (verified end-to-end):

- `GET /health` reports `database.ready=false`, SMS unconfigured; Earth Engine
  still initializes from this machine's cached `earthengine` credentials.
- `GET /marketplace/listings` serves fallback sample data (`source=fallback`);
  the Marketplace UI shows a "SAMPLE DATA (DB offline)" badge.
- `POST /send-otp` works in dev mode (returns `dev_otp` when
  `CARBONX_ALLOW_DEV_OTP=1`); `POST /login/send-otp` returns 503 with a clear
  message (it needs the DB to check the profile exists), and the login UI shows
  "Failed to send OTP" — expected until Supabase creds are re-added.
- Node blockchain API (port 3001) starts and returns explicit 503-style errors
  until `RPC_URL`/contract addresses/private keys are set.
- CORS: the frontend origin is port **5000**; the `CORS_ORIGINS` default in
  `backend/app/main.py` and `backend/.env` include 5173/3000/5000 (5000 was
  missing before 2026-10-04 — direct browser→:8000 calls were blocked).
- ESLint config ignores `backend`, `blockchain`, `.kilo`; `.kilo/`
  (leftover AI-tool worktrees) is gitignored too. `src/lib/supabase.js` exports
  a null-gated client but nothing imports it — frontend auth goes through
  `/py-api` only. `backend/src/routes/farms.js` routes are not mounted in
  `backend/src/index.js` and nothing calls them (dead code).

## Key API endpoint: GET /marketplace/listings

Open (no auth) dashboard endpoint. Primary source: live Supabase DB; if the DB is
unreachable it serves built-in sample data from `backend/app/sample_data.py`
and prints the source to the terminal (`source=live_db|fallback` in the JSON too).

Filters (query params): `status` (default `Active`; `all` for everything), `crop`,
`location`, `farmer_phone`, `farm_id`, `listing_model` (partial/case-insensitive),
`min_price`/`max_price`, `min_credits`/`max_credits`, `search` (farmer_name/crop/location),
`sort` (+ `order=asc|desc`), `limit` (≤200), `offset`.
Response: `{success, source, total, count, filters, listings}`.

Seeding: `scripts/seed_marketplace_data.py` seeds the canonical demo data
(4 farmers, 7 farms, 10 listings) via live DB REST first, falling back to the
Supabase Management API SQL endpoint (CLI access token from Windows Credential
Manager, runs as postgres). Idempotent — safe to re-run.
