-- Required for GET /land/registry/{survey} (service role currently gets 42501).
grant select on public.land_registry to service_role;

-- Optional columns used by the verification engine. Apply when ready.
alter table public.farms add column if not exists badge text;
alter table public.farms add column if not exists fpo_id uuid references public.fpos(id);

-- Optional membership table (profiles.fpo_id already exists as a shortcut).
create table if not exists public.fpo_members (
  id uuid primary key default gen_random_uuid(),
  fpo_id uuid not null references public.fpos(id),
  farmer_phone text not null references public.profiles(phone),
  status text not null default 'pending',
  farm_id uuid references public.farms(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
