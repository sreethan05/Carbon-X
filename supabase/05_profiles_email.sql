-- Optional contact email collected during registration.
-- Safe to run once on the CarbonX Supabase project.
alter table public.profiles add column if not exists email text;

