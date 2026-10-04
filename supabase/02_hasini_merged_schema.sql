-- ==============================================================================
-- 2. HASINI'S MERGED SCHEMA (FPO & Corporate Portal Architecture)
-- Author: Hasini
-- Includes: fpos, corporates, profiles (with fpo_id), farms, marketplace_listings, otp_codes
-- ==============================================================================

-- Extensions
create extension if not exists pgcrypto;

-- 1. FPOS TABLE (Farmer Producer Organizations)
create table if not exists public.fpos (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  registration_no text unique,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- 2. CORPORATES TABLE (Corporate Buyers & ESG Partners)
create table if not exists public.corporates (
  c_id uuid primary key default gen_random_uuid(),
  name text not null,
  password_hash text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- 3. PROFILES TABLE (with FPO Linkage)
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

-- 4. OTP CODES TABLE
create table if not exists public.otp_codes (
  phone text primary key,
  otp text not null,
  expires_at timestamptz not null,
  created_at timestamptz not null default now()
);

-- 5. FARMS TABLE
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

-- 6. MARKETPLACE LISTINGS TABLE (Corporate & Buyer Listings)
create table if not exists public.marketplace_listings (
  id uuid primary key default gen_random_uuid(),
  farm_id uuid references public.farms(id) on delete set null,
  price_per_credit numeric not null default 520,
  status text not null default 'Active',
  tx_hash text,
  expires_at timestamptz,
  created_at timestamptz not null default now()
);

-- 7. SECURITY & PERMISSIONS
alter table public.fpos enable row level security;
alter table public.corporates enable row level security;
alter table public.profiles enable row level security;
alter table public.otp_codes enable row level security;
alter table public.farms enable row level security;
alter table public.marketplace_listings enable row level security;

grant usage on schema public to service_role;
grant select, insert, update, delete on table
  public.fpos,
  public.corporates,
  public.profiles,
  public.otp_codes,
  public.farms,
  public.marketplace_listings
to service_role;
