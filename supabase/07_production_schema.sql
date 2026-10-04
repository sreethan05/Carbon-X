-- 07_production_schema.sql — production migrations (2026-10-04)
-- Ground-truth calibration, performance indexes, soft-delete columns.
-- Safe to re-run (idempotent). Also applied to the live project via the
-- Management API on 2026-10-04.

-- 1. Ground-truth calibration samples (referenced by /ops/ground-truth)
create table if not exists public.ground_truth_samples (
  id uuid primary key default gen_random_uuid(),
  farm_id uuid references public.farms(id) on delete set null,
  latitude numeric,
  longitude numeric,
  measured_soc_tco2e_ha numeric,
  measured_species_count integer,
  source text not null default 'field_survey',
  measured_at date,
  notes text,
  created_at timestamptz not null default now()
);
alter table public.ground_truth_samples enable row level security;
grant select, insert, update, delete on public.ground_truth_samples to anon, authenticated, service_role;

-- 2. Performance indexes for the hot paths
create index if not exists farms_status_idx on public.farms(status);
create index if not exists marketplace_listings_farmer_status_idx
  on public.marketplace_listings(farmer_phone, status);
create index if not exists kyc_verifications_owner_created_idx
  on public.kyc_verifications(owner_phone, created_at desc);
create index if not exists profiles_phone_idx on public.profiles(phone);
create index if not exists ledger_events_entity_seq_idx on public.ledger_events(entity_id, seq);

-- 2b. Trigram search for marketplace ilike filters (pg_trgm extension)
create extension if not exists pg_trgm;
create index if not exists marketplace_listings_farmer_name_trgm
  on public.marketplace_listings using gin (farmer_name gin_trgm_ops);
create index if not exists marketplace_listings_crop_trgm
  on public.marketplace_listings using gin (crop gin_trgm_ops);
create index if not exists marketplace_listings_location_trgm
  on public.marketplace_listings using gin (location gin_trgm_ops);

-- 3. Soft-delete columns (no delete endpoints exist yet; columns ready
--    before any are written — see docs/DEPLOYMENT.md operations notes)
alter table public.profiles add column if not exists deleted_at timestamptz;
alter table public.farms add column if not exists deleted_at timestamptz;
alter table public.marketplace_listings add column if not exists deleted_at timestamptz;

-- 4. Monitoring snapshot columns (5-day cycle — see /monitor/run)
alter table public.farms add column if not exists last_monitor_ndvi numeric;
alter table public.farms add column if not exists last_monitored_at timestamptz;

-- 5. RLS posture (applied to the live project on 2026-10-04):
--    RLS is ENABLED on every table with NO anon/authenticated policies —
--    deny-by-default for client-side access. The backend uses service_role
--    which bypasses RLS. If direct client-side Supabase access is ever
--    added, write explicit policies here FIRST — do not disable RLS.
--    Reference permissive-read policy shape (enable per table as needed):
--
--    create policy "public read listings" on public.marketplace_listings
--      for select to anon using (true);
