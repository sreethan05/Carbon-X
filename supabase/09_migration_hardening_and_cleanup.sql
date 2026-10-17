-- ==============================================================================
-- 09_migration_hardening_and_cleanup.sql
-- CarbonX Database Hardening, Index Deduplication & Security Remediation
-- Idempotent script to deduplicate indexes, add high-value indexes, and harden RLS
-- ==============================================================================

-- 1. DROP REDUNDANT & DUPLICATE INDEXES
DROP INDEX IF EXISTS public.profiles_phone_idx;                 -- redundant with profiles_phone_key
DROP INDEX IF EXISTS public.ledger_events_entity_seq_idx;       -- redundant with ledger_events_entity_id_seq_key
DROP INDEX IF EXISTS public.kyc_verifications_owner_created_idx;-- duplicate of kyc_verifications_owner_phone_idx
DROP INDEX IF EXISTS public.marketplace_listings_farmer_phone_idx; -- covered by marketplace_listings_farmer_status_idx

-- 2. CREATE MISSING PERFORMANCE INDEXES
CREATE INDEX IF NOT EXISTS farms_fpo_id_idx
  ON public.farms(fpo_id);

CREATE INDEX IF NOT EXISTS marketplace_listings_status_created_idx
  ON public.marketplace_listings(status, created_at DESC);

CREATE INDEX IF NOT EXISTS farm_evidence_sha256_idx
  ON public.farm_evidence(sha256);

-- 3. HARDEN RLS & REVOKE UNNECESSARY ANON / AUTHENTICATED GRANTS
ALTER TABLE IF EXISTS public.fpo_members ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.ground_truth_samples FROM anon, authenticated;
REVOKE ALL ON TABLE public.farm_evidence FROM anon, authenticated;
REVOKE ALL ON TABLE public.profiles FROM anon, authenticated;
REVOKE ALL ON TABLE public.farms FROM anon, authenticated;
REVOKE ALL ON TABLE public.marketplace_listings FROM anon, authenticated;

-- Ensure service_role has required operational access
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE
  public.ground_truth_samples,
  public.farm_evidence,
  public.fpo_members
TO service_role;

-- 4. ENSURE CONSISTENT CHECK CONSTRAINTS (IDEMPOTENT RE-APPLICATION)
ALTER TABLE public.profiles
  DROP CONSTRAINT IF EXISTS profiles_role_check;
ALTER TABLE public.profiles
  ADD CONSTRAINT profiles_role_check
  CHECK (role IN ('farmer', 'buyer', 'fpo', 'verifier', 'admin'));

ALTER TABLE public.kyc_verifications
  DROP CONSTRAINT IF EXISTS kyc_verifications_status_check;
ALTER TABLE public.kyc_verifications
  ADD CONSTRAINT kyc_verifications_status_check
  CHECK (status IN ('VERIFIED', 'FLAGGED', 'PENDING'));
