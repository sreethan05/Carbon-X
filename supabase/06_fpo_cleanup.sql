-- Align FPO storage with the application:
-- FPO reviewers are profiles with role=fpo linked through profiles.fpo_id.
-- FPO passwords were unused by the OTP-based auth flow and were stored in plaintext.

alter table public.profiles
  drop constraint if exists profiles_role_check;

alter table public.profiles
  add constraint profiles_role_check
  check (role in ('farmer', 'buyer', 'fpo', 'verifier', 'admin'));

alter table public.fpos
  drop column if exists password;

create index if not exists profiles_fpo_id_idx
  on public.profiles(fpo_id);
