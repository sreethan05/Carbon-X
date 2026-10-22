-- 10_trust_controls.sql — field validation, privacy controls, credit lifecycle
-- (2026-10-22). Safe to re-run (idempotent).
--
-- Apply this migration before enabling the corresponding API endpoints in a
-- live deployment. The backend degrades to explicit in-memory fallbacks when
-- the columns/tables are absent, but a production system must persist them.

-- ─── 1. Field validation metadata ───────────────────────────────────────────
-- A rate (tCO2e/ha/yr) can validate the proxy; a stock (tCO2e/ha, 0-30 cm)
-- can only check physical plausibility. Mixing them was the original bug.
alter table public.ground_truth_samples
  add column if not exists measurement_type text not null default 'rate';
alter table public.ground_truth_samples
  add column if not exists depth_cm numeric;
alter table public.ground_truth_samples
  add column if not exists bulk_density_g_cm3 numeric;
alter table public.ground_truth_samples
  add column if not exists lab_method text;
alter table public.ground_truth_samples
  add column if not exists lab_reference text;
alter table public.ground_truth_samples
  add column if not exists sampling_protocol text;
alter table public.ground_truth_samples
  add column if not exists sample_design text;
alter table public.ground_truth_samples
  add column if not exists verification_status text not null default 'unverified';
alter table public.ground_truth_samples
  add column if not exists verified_by text;
alter table public.ground_truth_samples
  add column if not exists consent_ref text;
alter table public.ground_truth_samples
  add column if not exists crop text;
-- Snapshot of the model's estimate at sampling time. This prevents a later
-- formula change from retroactively improving the validation result.
alter table public.ground_truth_samples
  add column if not exists estimate_snapshot jsonb;
alter table public.ground_truth_samples
  add column if not exists estimated_tco2e_ha numeric;
alter table public.ground_truth_samples
  add column if not exists estimated_ci90_low numeric;
alter table public.ground_truth_samples
  add column if not exists estimated_ci90_high numeric;
create index if not exists ground_truth_samples_type_verified_idx
  on public.ground_truth_samples(measurement_type, verification_status);
create index if not exists ground_truth_samples_farm_idx
  on public.ground_truth_samples(farm_id);

-- ─── 2. Consent records ─────────────────────────────────────────────────────
-- Append-only consent log. Each row is a versioned decision for one purpose;
-- withdrawal is a new row with granted=false, never an update that erases the
-- original decision.
create table if not exists public.consent_records (
  id uuid primary key default gen_random_uuid(),
  phone text not null,
  purpose text not null,
  policy_version text not null,
  granted boolean not null,
  language text not null default 'en',
  method text not null default 'app_checkbox',
  evidence jsonb,
  captured_at timestamptz not null default now()
);
create index if not exists consent_records_phone_idx
  on public.consent_records(phone, captured_at desc);
create unique index if not exists consent_records_one_current_idx
  on public.consent_records(phone, purpose, policy_version, granted)
  where granted = true;

-- ─── 3. Privacy requests (export / deletion / correction) ───────────────────
create table if not exists public.privacy_requests (
  id uuid primary key default gen_random_uuid(),
  phone text not null,
  request_type text not null check (request_type in ('export', 'deletion', 'correction')),
  status text not null default 'received'
    check (status in ('received', 'blocked', 'in_review', 'completed', 'rejected')),
  details jsonb,
  resolution_note text,
  created_at timestamptz not null default now(),
  resolved_at timestamptz
);
create index if not exists privacy_requests_phone_idx
  on public.privacy_requests(phone, created_at desc);
create index if not exists privacy_requests_status_idx
  on public.privacy_requests(status);

-- ─── 4. Profile deletion / restriction markers ──────────────────────────────
alter table public.profiles add column if not exists is_active boolean not null default true;
alter table public.profiles add column if not exists deletion_requested_at timestamptz;
alter table public.profiles add column if not exists anonymized_at timestamptz;
alter table public.profiles add column if not exists consent_version text;
create index if not exists profiles_active_idx on public.profiles(is_active);

-- ─── 5. Credit lifecycle fields ─────────────────────────────────────────────
-- credits_sold is informational; the balance remains total_credits (remaining).
alter table public.marketplace_listings
  add column if not exists credits_sold numeric not null default 0;
alter table public.marketplace_listings
  add column if not exists refunded_credits numeric not null default 0;
alter table public.marketplace_listings
  add column if not exists dispute_status text not null default 'NONE';
alter table public.marketplace_listings
  add column if not exists dispute_reason text;
alter table public.marketplace_listings
  add column if not exists dispute_opened_at timestamptz;
alter table public.marketplace_listings
  add column if not exists dispute_resolved_at timestamptz;
alter table public.marketplace_listings
  add column if not exists lifecycle_state text not null default 'Active';
create index if not exists marketplace_listings_dispute_idx
  on public.marketplace_listings(dispute_status)
  where dispute_status <> 'NONE';

-- ─── 6. Evidence deletion marker (privacy erasure) ──────────────────────────
alter table public.farm_evidence add column if not exists deleted_at timestamptz;
create index if not exists farm_evidence_live_idx
  on public.farm_evidence(farm_id, created_at desc)
  where deleted_at is null;

-- ─── 7. KYC document retention marker ───────────────────────────────────────
-- The app never stores the uploaded Aadhaar image; it stores hashes and
-- extracted fields. This marker documents when those derived fields were
-- erased in response to a deletion request.
alter table public.kyc_verifications add column if not exists document_deleted_at timestamptz;

-- ─── 8. Access posture ──────────────────────────────────────────────────────
-- RLS stays enabled with no anon/authenticated policies: only the backend's
-- service_role can read/write these tables.
alter table public.consent_records enable row level security;
alter table public.privacy_requests enable row level security;
revoke all on public.consent_records from anon, authenticated;
revoke all on public.privacy_requests from anon, authenticated;
grant select, insert, update on public.consent_records to service_role;
grant select, insert, update on public.privacy_requests to service_role;

-- ─── 9. Corporate account preferences (server-side buyer targets) ───────────
-- Self-declared decarbonization targets must survive device and browser
-- changes, so they live server-side, keyed to the corporate account.
create table if not exists corporate_settings (
  c_id              bigint not null primary key,
  target_offsets_mt numeric not null default 1000 check (target_offsets_mt > 0),
  preferences       jsonb not null default '{}'::jsonb,
  updated_at        timestamptz not null default now()
);
alter table public.corporate_settings enable row level security;
revoke all on public.corporate_settings from anon, authenticated;
grant select, insert, update, delete on public.corporate_settings to service_role;

-- ─── 10. Farmer support / grievance tickets ─────────────────────────────────
-- Farmers must be able to report wrong boundaries, ownership mismatches,
-- disputed estimates and missing payouts, and follow resolution in the app.
create extension if not exists pgcrypto;
create table if not exists support_tickets (
  id             uuid primary key default gen_random_uuid(),
  reporter_phone text not null,
  farm_id        text,
  category       text not null check (category in
                   ('boundary', 'ownership', 'estimate', 'payout', 'privacy', 'other')),
  status         text not null default 'Open' check (status in
                   ('Open', 'In Review', 'Resolved', 'Rejected')),
  title          text not null,
  detail         text not null,
  staff_notes    text,
  resolution     text,
  handled_by     text,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),
  resolved_at    timestamptz
);
create index if not exists support_tickets_reporter_idx
  on public.support_tickets(reporter_phone, created_at desc);
create index if not exists support_tickets_open_idx
  on public.support_tickets(status, created_at desc)
  where status in ('Open', 'In Review');
alter table public.support_tickets enable row level security;
revoke all on public.support_tickets from anon, authenticated;
grant select, insert, update on public.support_tickets to service_role;
