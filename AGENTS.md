# AGENTS.md — CarbonX Project Context

Quick-reference for agents working on this repo. Update when setup/schema changes.

## Project Overview

CarbonX is an agri carbon + biodiversity credits marketplace. Farmers register via phone OTP, map farms with GEE satellite imagery, get AI-scanned credits, and list them on a marketplace where corporates/FPOs bid.

- Main app: repo root (`src/`), React 18 + Vite + Tailwind. `npm run dev` → port 5000.
- `backend/` — Python FastAPI (GEE satellite scan, ML, phone OTP auth, Supabase service-role access) → port 8000. Proxied via `/py-api`.
- `backend/` (Node) — blockchain minting API → port 3001. Proxied via `/bc-api`.
- `frontend/` — legacy standalone map UI (deprecated; GEE map is now `src/components/GEEMap.jsx`).
- Local schema SQL lives in `supabase/` (`01_sreethan_initial_schema.sql`, `02_hasini_merged_schema.sql`, `schema.sql`).

## Supabase (source of truth: remote DB)

- **Org:** hasini.four@gmail.com's Org — ID `ycenpzlqllsoddavsvpw`
  - Projects in org: CarbonX (`rbdyzeuucgqkhlikbpnd`), AquaSentinel (`eqrogkpwlmdmappphkvp`), cropdoc (`iachrjbkhgqvrvfntxwh`)
- **CarbonX project ref:** `rbdyzeuucgqkhlikbpnd` — region: Oceania (Sydney)
- **URL:** `https://rbdyzeuucgqkhlikbpnd.supabase.co`
- **Env vars:** root `.env` → `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`; `backend/.env` → `SUPABASE_URL`, `SUPABASE_KEY` (anon key), `SUPABASE_SERVICE_ROLE_KEY` (write access — required for backend writes; anon key alone can only SELECT profiles/farms/marketplace_listings and gets `permission denied` on fpos/corporates/otp_codes/kyc_verifications)
- CLI is installed (v2.116.0) and logged in on this machine; auth token is managed by the CLI itself (no `~/.supabase/access-token` file).
- Project is NOT linked locally (`supabase link` not run); always pass the ref explicitly.

### Working CLI commands (no password prompt — use CLI login role)

```powershell
supabase orgs list
supabase projects list
supabase inspect db table-stats --project-ref rbdyzeuucgqkhlikbpnd
supabase gen types typescript --project-id rbdyzeuucgqkhlikbpnd --schema public
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

## Commands

```powershell
npm run dev        # root app, port 5000
npm run build      # vite build
npm run lint       # eslint .
cd backend; uvicorn app.main:app --reload --port 8000   # Python API
python scripts/seed_marketplace_data.py                 # seed sample marketplace data
```

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
