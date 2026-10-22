# CarbonX — Product Requirements Document (PRD)

> PRD = WHAT + WHY. Architecture lives in [docs/ARCHITECTURE.md](ARCHITECTURE.md);
> how it looks lives in [docs/DESIGN.md](DESIGN.md). Structure follows the
> 8-section MVP-PRD convention (problem → users → goal → workflow → scope →
> non-goals → acceptance criteria → constraints/risks). Update this document in
> the same PR that changes behaviour.

## 1. Problem statement

Smallholder farmers in Telangana (and similar Indian districts) cannot monetize
carbon and biodiversity improvements on their land. Formal MRV (measurement,
reporting, verification) is expensive, paper-bound, and English-coded, so their
soil/vegetation improvements stay invisible to credit markets. Corporates that
want credible agri credits face unverifiable supply: no auditable digital
record of who farmed what, on which parcel, with what satellite evidence.

- **Who has the problem:** smallholder farmers; FPOs aggregating them; corporate buyers.
- **What they are doing today:** farmers get almost nothing from carbon programs
  (paper pahani records, agents, cash sales of credits at low percentages);
  FPOs verify land via physical visits; corporates buy credits without parcel-level evidence.
- **Cost:** lost income for farmers, inflated/low-integrity credits for buyers,
  no audit trail for anyone.

## 2. Target user

- **Primary:** the smallholder farmer — phone-first (Android, sometimes shared
  devices), Telugu/Hindi speaking, low English, OTP-only identity via phone.
- **Secondary:** FPO officer (aggregates + verifies member farms), corporate
  buyer (procures credits with evidence), and platform ops (pilot oversight,
  monitoring, ground-truth calibration).

## 3. Goal and success metric

v1 tests the assumption that **a farmer can go from phone number to a credibly
labelled, sold carbon credit payout without owning a computer**.

Success for v1 = a farmer completes the full core workflow (§4) end to end,
with every trust gate passing and the payout split recorded in the ledger —
in a supervised pilot. Pilot KPIs (enrollment, retention, income) are defined
in [docs/IMPACT_MODEL.md](IMPACT_MODEL.md); it deliberately does not
precise-launch targets here.

## 4. Core workflow (the product in nine steps)

1. Farmer registers/logs in with **phone OTP** (no email, no passwords).
2. Farmer maps the farm boundary on a satellite map (GEE-backed) / FPO officer
   onboards and confirms the farm.
3. System scans forest/vegetation (NDVI/EVI, soil moisture, tree cover) and
   runs **Stage-1 verification** (declared crop vs per-crop NDVI signature).
   Mismatch → PENDING with credits blocked → FPO queue (never auto-reject).
4. Farmer adds **ground evidence** (practice photos with EXIF GPS, geotags
   inside the parcel boundary) — evidence quality lowers the uncertainty deduction.
5. System estimates credits with the canonical 5-step formula
   (`FORMULA_VERSION -r2`), exposing `ci90` and provenance.
6. Farmer lists credits on the marketplace.
7. A corporate buyer purchases → escrow → **conditional split**
   (farmer 70% floor, FPO 5% when involvement is proven, rest platform) →
   hash-chain ledger events → credits **instantly retired** (full buys).
8. Buyer receives a traceable certificate (JSON/CSV/PDF) with a unique id.
9. Ops run the **5-day NDVI monitoring cycle**; drops ≥ 0.15 flag the farm
   and write a ledger event. Farmer grievances go to the support desk.

## 5. v1 scope (built)

- Phone-OTP registration/login, roles: farmer, fpo, corporate (demo corporate
  login available); demo mode only when DB unconfigured.
- Farm mapping + GEE satellite scan + land-registry tiers (30 Telangana parcels).
- Stage-1 crop verification, KYC document verification (SHA-256 dedup,
  perceptual hash), evidence pipeline (photo/geotag + boundary ray-casting).
- Canonical credit engine + earnings calculator (open endpoint).
- Marketplace: listings, filters, cursor pagination, CAS bidding, buy →
  escrow → split → ledger → retirement; auto-match.
- Payments: simulated checkout and Razorpay orders with signature-verified
  webhooks; conflict → refund ledger entries.
- Trust program: validation labels (`proxy_unvalidated` until ≥30 verified
  annual-rate samples), privacy consent/export/erasure, certificate lifecycle
  (refunds/disputes/corrections), wallet reconciliation, public redaction policy,
  support tickets.
- Passport (public, redacted), WebSocket ledger live updates, certificate PDFs,
  PWA-lite, voice agent (Telugu/Hindi/English) with role-guarded tools.

## 6. Non-goals (explicitly OUT of v1)

- **On-chain settlement is NOT live.** The live ledger is the SHA-256 hash
  chain; Polygon/Amoy minting is a production-roadmap item (`backend/src/` is
  kept and documented, but is not in the verification or payout path).
- Native mobile application (PWA-lite covers installability; Playwright E2E is
  a backlog item, not a v1 gate).
- Own machine-learning beyond the honesty-gated biodiversity/SOC serving layer;
  every model output is labelled and gated (refusing to serve failed models).
- Social feed, gamification, AI tutor.
- Any money flow without an explicit provider mode: simulated payments are
  demo-only and production requires Razorpay credentials or an explicit
  `CARBONX_ACCEPT_SIMULATED_PAYMENTS=1` opt-in.
- Unlabelled estimates: never claim field validation that does not exist
  (`proxy_unvalidated` is the honest status until field data lands).

## 7. Acceptance criteria (Given / When / Then)

- **US-1 Farmer onboarding:** Given a phone number, when the farmer verifies
  the OTP, then a profile exists and further OTP sends are rate-limited.
- **US-2 Farm mapping:** Given a drawn GeoJSON polygon, when it is outside
  India, unclosed, or >10,000 ha, then it is rejected with a precise error
  (no scan, no fabricated values when GEE is offline).
- **US-3 Estimate:** Given any scan, then the estimate carries
  `formula_version`, `ci90`, and provenance; an unverified crop label means the
  farm seats PENDING and cannot list.
- **US-4 Marketplace purchase:** Given an active listing, when a buyer buys
  all credits, then the listing becomes Retired, split lines sum to the gross
  amount (integer paise), ledger events verify as a chain, and the wallet
  totals match the ledger.
- **US-5 Conflict:** Given two concurrent buys racing the last credits, then
  exactly one wins (CAS race), and a payment that cannot settle produces
  an explicit refund event (not silent money).
- **US-6 Purchases privacy:** Given a public viewer, then the passport/ledger
  show placeholders, not farmer identities or coordinates.

## 8. Constraints, risks, open questions

- **Constraint:** RLS denies anon/authenticated on all tables; the backend uses
  `service_role`. DDL for `supabase/10_trust_controls.sql` must be applied by a
  human in the Supabase SQL editor before considering live pilots (backend
  runs with labelled in-memory fallbacks until then).
- **Risk:** carbon estimates are satellite/biomass proxies until ≥30 verified
  field samples exist (`proxy_unvalidated`) — mitigated by pre-registered
  thresholds, public labels and honest claims ([docs/VALIDATION_PROTOCOL.md](VALIDATION_PROTOCOL.md)).
- **Risk:** SMS/OTP gateway limits; dev-OTP exposure flag must never be set in
  production (`CARBONX_ALLOW_DEV_OTP`), startup config blocks unsafe
  combinations ([docs/DEPLOYMENT.md](DEPLOYMENT.md)).
- **Open question (external):** independent MRV/agronomy and privacy reviews are
  NOT obtained — tracked in [docs/INDEPENDENT_REVIEW.md](INDEPENDENT_REVIEW.md).
