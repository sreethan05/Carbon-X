-- ==============================================================================
-- 1. SREETHAN'S INITIAL SCHEMA (CarbonX Core MRV & Marketplace)
-- Author: Sreethan
-- Includes: profiles, otp_codes, farms, marketplace_listings, kyc_verifications
-- ==============================================================================

-- Extensions
create extension if not exists pgcrypto;

-- 1. PROFILES TABLE (Farmer & User Profiles)
create table if not exists public.profiles (
  id uuid primary key default gen_random_uuid(),
  phone text not null unique,
  name text not null default '',
  state text default '',
  district text default '',
  village text default '',
  upi text default '',
  aadhaar_last4 text default '',
  role text not null default 'farmer' check (role in ('farmer', 'buyer', 'verifier', 'admin')),
  wallet_address text,
  preferred_language text not null default 'en',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- 2. OTP CODES TABLE (Phone Authentication)
create table if not exists public.otp_codes (
  phone text primary key,
  otp text not null,
  expires_at timestamptz not null,
  created_at timestamptz not null default now()
);

-- 3. FARMS TABLE (Satellite MRV, NDVI, EVI & Credits)
create table if not exists public.farms (
  id uuid primary key default gen_random_uuid(),
  owner_phone text not null references public.profiles(phone) on delete cascade,
  name text not null default 'My Farm',
  crop_type text default 'Mixed Crop',
  irrigation text default 'Drip',
  geojson jsonb not null,
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

create index if not exists farms_owner_phone_idx
  on public.farms(owner_phone);

-- 4. MARKETPLACE LISTINGS TABLE (Carbon Credit Trading)
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

create index if not exists marketplace_listings_farmer_phone_idx
  on public.marketplace_listings(farmer_phone);
create index if not exists marketplace_listings_status_idx
  on public.marketplace_listings(status);

-- 5. KYC VERIFICATIONS TABLE (Land Document Verification)
create table if not exists public.kyc_verifications (
  id uuid primary key default gen_random_uuid(),
  owner_phone text not null references public.profiles(phone) on delete cascade,
  status text not null check (status in ('VERIFIED', 'FLAGGED')),
  reasons jsonb not null default '[]'::jsonb,
  checks jsonb not null default '{}'::jsonb,
  extracted_fields jsonb not null default '{}'::jsonb,
  document_name text not null default 'document.png',
  document_sha256 text not null,
  perceptual_hash text,
  created_at timestamptz not null default now()
);

create index if not exists kyc_verifications_owner_phone_idx
  on public.kyc_verifications(owner_phone, created_at desc);
create index if not exists kyc_verifications_document_sha256_idx
  on public.kyc_verifications(document_sha256);

-- 6. SECURITY & PERMISSIONS
alter table public.profiles enable row level security;
alter table public.otp_codes enable row level security;
alter table public.farms enable row level security;
alter table public.marketplace_listings enable row level security;
alter table public.kyc_verifications enable row level security;

grant usage on schema public to service_role;
grant select, insert, update, delete on table
  public.profiles,
  public.otp_codes,
  public.farms,
  public.marketplace_listings,
  public.kyc_verifications
to service_role;
