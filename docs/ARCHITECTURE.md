# CarbonX (GraminCarbon) — Architecture

> A platform where farmers get verified and paid for carbon-positive practices
> using AI and free satellite data, with FPOs bridging farmers who cannot
> self-onboard, and transparent, hash-anchored credits sold to corporate
> buyers with real climate commitments.
>
> Tagline: **"The phone is the MRV lab."**

This document is the implementation reference for this repository. The five
flows below match the code in `backend/app/` and `src/` — same numbers, same
split logic, same escalation rules.

---

## 1 · System Architecture

```
        ANDROID SMARTPHONE (Farmer)            WEB APP (React/Vite — this repo)
   on-device AI · OCR · Sarvam voice        voice assistant · Leaflet boundary
   camera · GPS · offline capture           map · dashboards · purchase flows
                  |                                        |
                  |  REST API calls (py-api)               |
                  v                                        v
        SUPABASE — the backbone  <-------------------------+
   Auth (OTP/JWT) · Postgres · Storage · Realtime
   Ten tables: profiles · farms · fpos · corporates ·
   land_registry · fpo_members · kyc_verifications ·
   marketplace_listings · otp_codes · ledger_events
   Credits anchored with SHA-256 hash (tamper-evident)
          |                              |
   NDVI / satellite                 role-based access,
   requests                         realtime state
          v                              v
  GOOGLE EARTH ENGINE /         TRUST LAYER (backend/app/services/)
  Sentinel-2 NDVI               split_engine · ledger (hash chain) ·
  (free tier, 5-day revisit)    credit_engine · fraud_engine ·
                                trust_engine · market_store
```

Every layer runs on a free tier: Supabase free tier, Earth Engine developer
access, Sentinel-2 open data. A district pilot needs no capital expenditure.

## 2 · Three Roles

```
  FARMER (supply)             FPO (bridge/verifier)        COOPERATIVE (demand/buyer)
  Generates carbon credits    Onboards farmers who cannot  Aggregates corporate buyers
  from verified practices     self-register; reviews the   with net-zero / ESG
        |                     flagged queue                      |
        +── onboarding & verification ──+                           |
        +─────── verified, hash-anchored carbon credits ───────────►+
        ◄─────── payments: transparent conditional split ───────────┘
```

- **Farmer** — self-onboards (voice-first, OCR of any land document, map-drawn
  boundary) or via an FPO officer; holds a **Carbon Passport** (credits,
  status, expected earnings, trust & ledger view); receives the **70% floor**.
- **FPO** — assisted onboarding + manual verification queue. Earns **5% only
  when involvement is proven** (farm linked to the FPO). No work, no cut.
- **Cooperative / Corporate** — states a volume target, the matching engine
  assembles the order with a farmer-level breakdown visible **before** paying.

## 3 · Farmer Flow

```
  FARMER
    v
  Self-onboard? --NO--> FPO-ASSISTED onboarding (officer enters data)
    | YES                      |
    v <----------------------- +
  FARM ONBOARDING — land + identity (OCR, any document) + declared crop/practice
    v
  Validation gate — OCR confidence / geotag-inside-boundary / no boundary overlap
    |-- error --> AUTO-ESCALATION: auto-tagged to nearest FPO -> manual queue
    |                     (ladder: automatic -> FPO manual -> KVK expert review)
    v <-------------------------------------------+
  TRUST ENGINE STAGE 1 — declared crop vs Sentinel-2 NDVI signature
    |-- MATCH    -> advance
    |-- MISMATCH -> record PAUSED for FPO/KVK human review (never auto-rejected)
    v
  TRUST ENGINE STAGE 2 — 5-step credit calculation (see section 4)
    v
  CREDIT ISSUED — Supabase row + SHA-256 evidence hash (ledger ISSUE event)
    v
  CARBON PASSPORT — credits, status, expected earnings, trust & ledger view
    v
  EVERY 5 DAYS — Sentinel-2 NDVI re-check
    drop >= 0.15 -> credits AT-RISK -> farm flagged -> FPO queue (MONITOR event)
```

## 4 · Credit Calculation (Trust Engine Stage 2)

Mirrors Verra VM0042's structure, deliberately simplified. Implemented in
`backend/app/services/credit_engine.py::estimate_credits` — every step is
returned to the caller so any number can be recomputed by hand.

```
  1  BASELINE vs PROJECT   historical NDVI vs current (additionality delta)
        v
  2  ABOVEGROUND BIOMASS   crop-calibrated base scaled by NDVI (0.47 C fraction,
        v                  3.67 CO2e ratio folded into the crop calibration)
  3  SOIL ORGANIC CARBON   declared practice -> IPCC Tier 1-style factor
        v
  4  COMBINE               area x (biomass proxy + soil factor) = raw tCO2e
        v
  5  UNCERTAINTY DEDUCTION 10-30% by evidence quality (photo, geotag, FPO/
        v                  registry check, current NDVI, known baseline)
  FINAL CREDIT AMOUNT (tCO2e) -> expected rupees at the 70% farmer floor
```

## 5 · Cooperative Flow (demand)

```
  COOPERATIVE / CORPORATE BUYER
    v
  LOGIN / REGISTER — corporate account
    v
  DASHBOARD — enters credits needed (e.g. 500 tCO2e)
    v
  SMART MATCHING ENGINE — approved + available credits by region/FPO/vintage
    (deliberately simple and inspectable — in a market whose disease is
     opacity, simple-and-auditable is a feature)
    v
  CALCULATION BREAKDOWN SHOWN — Farmer A: 120 · B: 200 · C: 180 -> 500
  (each line previews the farmer's 70% share)
    v
  PURCHASE
    v
  ESCROW — money lands in the platform wallet first (simulated, labelled;
           production: payment-gateway escrow e.g. Razorpay route/hold)
    v
  FPO involved? --YES--> 4-WAY SPLIT: farmer 70 / FPO 5 / platform 25
    | NO
    +------------------> 3-WAY SPLIT: farmer 70 / platform 30
    v
  AUTO-DISTRIBUTED — farmer via UPI/bank · FPO only if involved · platform keeps rest
    v
  CREDIT AUTO-RETIRED (purchase = retirement, one step)
    v
  CERTIFICATE AUTO-GENERATED — date, quantity, region, batch hash, buyer
  (aggregated — proves the climate action without exposing farmer identities;
   the batch hash links back through the ledger to plot-level evidence)
```

The farmer's sale screen reads: *Credit sold · price ₹1,800 · your share (70%)
₹1,260 · FPO (5%) ₹90 · platform (25%) ₹450 · verified record `sha256:3a7f…`*
— every rupee, every recipient, every hash, in one screen.

## 6 · Trust & Ledger Design

- Every credit anchors a **SHA-256 hash of its evidence snapshot** (ledger
  `ISSUE` event at enrollment).
- Every subsequent event — SALE, SPLIT, RETIRE, MONITOR — hashes the previous
  state into the new one: an internal chain anyone can recompute
  (`GET /ledger/{farm_id}` returns and verifies it).
- Stored in Supabase `ledger_events` (`payload_json` keeps hashes byte-exact);
  a local JSON file is the offline fallback. No gas fees, no wallets.
- Production roadmap: settlement moves to Polygon (Amoy testnet); the
  architecture is identical — only the settlement substrate changes.
- **Escrow is simulated and clearly labelled** in this build.

## 7 · Honest Limitations

- Full VM0042-grade precision needs field trials; the calculation mirrors the
  methodology's structure, simplified, and claims no lab-grade accuracy.
- The NDVI→biomass proxy needs region-specific calibration; the uncertainty
  deduction is the honest bridge until pilot data replaces it.
- No universal cultivation-proof document exists in India; FPO/community
  attestation covers it rather than a fictional solved system.
- Under current CCTS rules offset credits serve voluntary buyers; compliance
  linkage is later-phase upside, not today's demand.
