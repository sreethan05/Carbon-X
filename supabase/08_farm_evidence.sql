-- 08_farm_evidence.sql — practice-photo & geotag evidence capture (2026-10-17)
-- Backs POST /farms/{farm_id}/evidence/photo, POST /farms/{farm_id}/evidence/geotag
-- and GET /farms/{farm_id}/evidence (see backend/app/routes/evidence_router.py).
-- Safe to re-run (idempotent).

-- 1. Raw evidence metadata. The photo/geotag bytes live on disk under
--    backend/data/evidence/<farm_id>/<sha256[:16]>.<ext>; this table holds
--    the tamper-evident pointer (sha256) plus the captured coordinates and
--    the boundary verdict computed at capture time. Coordinates are NULL when
--    the upload carried no EXIF GPS and no explicit geotag: never invented.
create table if not exists public.farm_evidence (
  id uuid primary key default gen_random_uuid(),
  farm_id text not null,
  kind text not null check (kind in ('photo', 'geotag')),
  sha256 text,
  mime text,
  size_bytes int,
  latitude double precision,
  longitude double precision,
  inside_boundary boolean not null default false,
  captured_at timestamptz,
  created_by text,
  created_at timestamptz not null default now()
);

-- 2. Hot path: newest-first evidence listing / flag derivation per farm.
create index if not exists farm_evidence_farm_created_idx
  on public.farm_evidence(farm_id, created_at desc);

-- 3. RLS posture: same as every other table (see 07_production_schema.sql §5)
--    RLS is ENABLED with NO anon/authenticated policies — deny-by-default for
--    client-side access; the backend uses service_role which bypasses RLS.
alter table public.farm_evidence enable row level security;
grant select, insert, update, delete on public.farm_evidence to anon, authenticated, service_role;
