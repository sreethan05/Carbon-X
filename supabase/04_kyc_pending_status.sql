-- Fix: allow PENDING status for FPO-path KYC records.
-- The trust engine writes status=PENDING until an FPO confirms the farm
-- (see backend/app/services/trust_engine.py:apply_fraud + backend/app/main.py:verify_land_document).
-- The original schema.sql only allowed ('VERIFIED','FLAGGED'), causing 23514 on FPO submissions.
alter table public.kyc_verifications drop constraint if exists kyc_verifications_status_check;
alter table public.kyc_verifications
  add constraint kyc_verifications_status_check
  check (status in ('VERIFIED', 'FLAGGED', 'PENDING'));
