-- ==============================================================================
-- 3. ALL-IN-ONE UNIFIED SCHEMA (Sreethan Core MRV)
-- Unified Master Database Migration for CarbonX
-- Safe to run on any new or existing Supabase project. Zero destructive operations.
-- Includes the active tables used by the current app:
--   1. profiles
--   2. otp_codes
--   3. farms
--   4. marketplace_listings
--   5. kyc_verifications
-- ============================================================================== 

-- 1. EXTENSIONS
create extension if not exists pgcrypto;

-- 2. FPOS TABLE (Farmer Producer Organizations - Hasini)
create table if not exists public.fpos (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  registration_no text unique,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- 3. CORPORATES TABLE (Corporate Buyers & ESG - Hasini)
create table if not exists public.corporates (
  c_id uuid primary key default gen_random_uuid(),
  name text not null,
  password_hash text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- 4. PROFILES TABLE (Combined Sreethan & Hasini)
create table if not exists public.profiles (
  id uuid primary key default gen_random_uuid(),
  phone text not null unique,
  name text not null default '',
  state text default '',
  district text default '',
  village text default '',
  upi text default '',
  aadhaar_last4 text default '',
  role text not null default 'farmer' check (role in ('farmer', 'buyer', 'fpo', 'verifier', 'admin')),
  wallet_address text,
  preferred_language text not null default 'en',
  fpo_id uuid references public.fpos(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists profiles_fpo_id_idx
  on public.profiles(fpo_id);

alter table public.profiles add column if not exists role text not null default 'farmer';
alter table public.profiles add column if not exists preferred_language text not null default 'en';
alter table public.profiles add column if not exists wallet_address text;
alter table public.profiles add column if not exists upi text default '';
alter table public.profiles add column if not exists aadhaar_last4 text default '';
-- 5. OTP CODES TABLE (Phone Verification)
create table if not exists public.otp_codes (
  phone text primary key,
  otp text not null,
  expires_at timestamptz not null,
  created_at timestamptz not null default now()
);

-- 6. FARMS TABLE (Satellite MRV, NDVI, EVI & Credits - Sreethan)
create table if not exists public.farms (
  id uuid primary key default gen_random_uuid(),
  owner_phone text not null references public.profiles(phone) on delete cascade,
  name text not null default 'My Farm',
  crop_type text default 'Mixed Crop',
  irrigation text default 'Drip',
  geojson jsonb not null default '{}'::jsonb,
  area_hectares numeric not null default 0,
  ndvi numeric default 0,
  evi numeric default 0,
  carbon_tonnes numeric default 0,
  biodiversity_score numeric default 0,
  biodiversity_credits numeric default 0,
  total_credits numeric default 0,
  tree_cover numeric default 0,
  soil_moisture numeric default 0,
  vegetation_health text default '',
  ai_confidence numeric default 0,
  satellite_source text default '',
  status text not null default 'Verified',
  token_id text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.farms add column if not exists owner_phone text references public.profiles(phone) on delete cascade;
alter table public.farms add column if not exists name text not null default 'My Farm';
alter table public.farms add column if not exists crop_type text default 'Mixed Crop';
alter table public.farms add column if not exists irrigation text default 'Drip';
alter table public.farms add column if not exists geojson jsonb not null default '{}'::jsonb;
alter table public.farms add column if not exists area_hectares numeric not null default 0;
alter table public.farms add column if not exists ndvi numeric default 0;
alter table public.farms add column if not exists evi numeric default 0;
alter table public.farms add column if not exists carbon_tonnes numeric default 0;
alter table public.farms add column if not exists biodiversity_score numeric default 0;
alter table public.farms add column if not exists biodiversity_credits numeric default 0;
alter table public.farms add column if not exists total_credits numeric default 0;
alter table public.farms add column if not exists tree_cover numeric default 0;
alter table public.farms add column if not exists soil_moisture numeric default 0;
alter table public.farms add column if not exists vegetation_health text default '';
alter table public.farms add column if not exists ai_confidence numeric default 0;
alter table public.farms add column if not exists satellite_source text default '';
alter table public.farms add column if not exists status text not null default 'Verified';
alter table public.farms add column if not exists token_id text;
alter table public.farms add column if not exists updated_at timestamptz not null default now();

create index if not exists farms_owner_phone_idx
  on public.farms(owner_phone);

-- 7. MARKETPLACE LISTINGS TABLE (Full Unified Trading)
create table if not exists public.marketplace_listings (
  id uuid primary key default gen_random_uuid(),
  farmer_phone text not null references public.profiles(phone) on delete cascade,
  farm_id uuid references public.farms(id) on delete set null,
  farmer_name text not null default '',
  location text default '',
  crop text default 'Mixed Crop',
  size_label text default '',
  carbon_credits numeric not null default 0,
  biodiversity_credits numeric not null default 0,
  total_credits numeric not null default 0,
  price_per_credit numeric not null default 520,
  current_bid numeric not null default 0,
  bids_count integer not null default 0,
  status text not null default 'Active',
  listing_model text default '',
  token_id text,
  tx_hash text,
  image_url text,
  expires_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.marketplace_listings add column if not exists farmer_phone text references public.profiles(phone) on delete cascade;
alter table public.marketplace_listings add column if not exists farm_id uuid references public.farms(id) on delete set null;
alter table public.marketplace_listings add column if not exists farmer_name text not null default '';
alter table public.marketplace_listings add column if not exists location text default '';
alter table public.marketplace_listings add column if not exists crop text default 'Mixed Crop';
alter table public.marketplace_listings add column if not exists size_label text default '';
alter table public.marketplace_listings add column if not exists carbon_credits numeric not null default 0;
alter table public.marketplace_listings add column if not exists biodiversity_credits numeric not null default 0;
alter table public.marketplace_listings add column if not exists total_credits numeric not null default 0;
alter table public.marketplace_listings add column if not exists price_per_credit numeric not null default 520;
alter table public.marketplace_listings add column if not exists current_bid numeric not null default 0;
alter table public.marketplace_listings add column if not exists bids_count integer not null default 0;
alter table public.marketplace_listings add column if not exists status text not null default 'Active';
alter table public.marketplace_listings add column if not exists listing_model text default '';
alter table public.marketplace_listings add column if not exists token_id text;
alter table public.marketplace_listings add column if not exists tx_hash text;
alter table public.marketplace_listings add column if not exists image_url text;
alter table public.marketplace_listings add column if not exists expires_at timestamptz;
alter table public.marketplace_listings add column if not exists updated_at timestamptz not null default now();

create index if not exists marketplace_listings_farmer_phone_idx
  on public.marketplace_listings(farmer_phone);
create index if not exists marketplace_listings_status_idx
  on public.marketplace_listings(status);

-- 8. KYC VERIFICATIONS TABLE (Land Document Verification - Sreethan)
create table if not exists public.kyc_verifications (
  id uuid primary key default gen_random_uuid(),
  owner_phone text not null references public.profiles(phone) on delete cascade,
  status text not null check (status in ('VERIFIED', 'FLAGGED', 'PENDING')),
  reasons jsonb not null default '[]'::jsonb,
  checks jsonb not null default '{}'::jsonb,
  extracted_fields jsonb not null default '{}'::jsonb,
  document_name text not null default 'document.png',
  document_sha256 text not null,
  perceptual_hash text,
  created_at timestamptz not null default now()
);

alter table public.kyc_verifications add column if not exists document_name text not null default 'document.png';
alter table public.kyc_verifications add column if not exists reasons jsonb not null default '[]'::jsonb;
alter table public.kyc_verifications add column if not exists checks jsonb not null default '{}'::jsonb;
alter table public.kyc_verifications add column if not exists extracted_fields jsonb not null default '{}'::jsonb;

create index if not exists kyc_verifications_owner_phone_idx
  on public.kyc_verifications(owner_phone, created_at desc);
create index if not exists kyc_verifications_document_sha256_idx
  on public.kyc_verifications(document_sha256);

-- 9. ROW LEVEL SECURITY (RLS)
alter table public.profiles enable row level security;
alter table public.otp_codes enable row level security;
alter table public.farms enable row level security;
alter table public.marketplace_listings enable row level security;
alter table public.kyc_verifications enable row level security;

-- 10. FULL SERVICE ROLE & CLIENT ACCESS
grant usage on schema public to service_role;
grant select, insert, update, delete on table
  public.profiles,
  public.otp_codes,
  public.farms,
  public.marketplace_listings,
  public.kyc_verifications
to service_role;

grant usage on schema public to anon, authenticated;
grant select on table
  public.profiles,
  public.farms,
  public.marketplace_listings
to anon, authenticated;

-- 11. COMPLETION
do $$
begin
  raise notice 'CarbonX all-in-one unified schema applied successfully!';
end $$;
