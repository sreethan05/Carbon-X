# CarbonX (GraminCarbon)

> Satellite-verified carbon credits that Indian smallholder farmers can actually reach — **the phone is the MRV lab.**

[![Status: MVP](https://img.shields.io/badge/Status-MVP-orange)]()
[![Tests](https://img.shields.io/badge/Tests-42%20passing%20%C2%B7%206%20integration-brightgreen)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## What this is

CarbonX is a phone-first carbon-credit platform for Indian smallholders. A farmer photographs a
field practice; the platform verifies it against satellite data and the declared farm boundary;
a simplified VM0042-style calculation turns the verified activity into carbon credits; and when a
buyer purchases, a transparent, hash-anchored split pays the farmer directly.

It exists because the market does not reach the people who could supply it. India has **146 million
operational holdings averaging 1.08 ha** (Agriculture Census 2015-16; 86.1% small & marginal).
Traditional verification needs physical soil sampling and field audits — 6–12 months per
verification, ₹2,000+ per soil test — which costs more than the credits a small plot produces.
Agriculture emits ~14% of India's GHGs but has received only ~0.2% of its issued carbon credits
(till Dec 2023). CarbonX attacks the cost and speed of MRV, and the opacity of the payout.

**What it is not:** not a trading exchange, not a registry, not a claim of lab-grade measurement.
It is the missing on-ramp — the MRV and payment-distribution layer.

---

## How it works

### Three roles

| Role | Interface | Does | Earns / pays |
|---|---|---|---|
| **Farmer** (supply) | Phone app (PWA, voice-first) | Self-onboards or is onboarded by an FPO officer; captures practice evidence (works offline); holds a **Carbon Passport** | **70% floor** of every sale, via UPI/bank |
| **FPO** (bridge / verifier) | Web dashboard | Assisted (Meeseva-style) onboarding; resolves the auto-flagged verification queue | **5% only when involvement is proven** — no work, no cut |
| **Cooperative / corporate** (demand) | Web dashboard | States a volume target; sees the farmer-level breakdown **before** paying; purchases | Pays the credit price |

The platform retains **25%** when an FPO was involved (4-way split) and **30%** when not (3-way).
All split arithmetic runs in **integer paise**, so rounding can never dilute the farmer floor.

### Farmer flow

```
FARMER
  └─ Self-onboard? ──NO──► FPO-assisted onboarding (officer enters data)
       │ YES
  FARM ONBOARDING — land + identity (OCR, any document) + declared crop/practice
  VALIDATION GATE — OCR confidence · geotag-inside-boundary · no boundary overlap
       └─ error ──► auto-escalation to the nearest FPO (ladder: automatic → FPO → KVK)
  TRUST ENGINE STAGE 1 — declared crop/practice vs the plot's Sentinel-2 NDVI signature
       └─ mismatch ──► record PAUSED for FPO/KVK review (never auto-rejected)
  TRUST ENGINE STAGE 2 — the 5-step credit calculation (below)
  CREDIT ISSUED — record + SHA-256 evidence hash (ledger ISSUE event)
  CARBON PASSPORT — credits, status, expected earnings
  EVERY 5 DAYS — Sentinel-2 NDVI re-check → drop ⇒ credits AT-RISK ⇒ FPO queue
```

### Credit calculation (Stage 2)

Mirrors the structure of Verra **VM0042**, deliberately simplified. Every intermediate number is
returned so a farmer or buyer can recompute it by hand:

1. **Additionality** — historical NDVI (pre-enrollment) vs current; only the farmer-created delta is credited.
2. **Aboveground biomass** — crop-calibrated base scaled by NDVI (the 0.47 carbon fraction and 3.67 CO₂e ratio are folded into the calibration).
3. **Soil organic carbon** — declared practice → IPCC Tier-1-style factor lookup.
4. **Combine** — `area × (biomass proxy + soil factor)` = raw tCO₂e.
5. **Uncertainty deduction** — **10–30%** by evidence quality (photo, geotag, FPO/registry check, current NDVI, known baseline).

**One engine, one number.** All credits come from `backend/app/services/credits.py` →
`credit_engine`. No endpoint re-implements the maths, and when live satellite data is unavailable
the API issues **no credit at all** rather than inventing one.

### Trust & ledger

- Every credit anchors a **SHA-256 hash of its evidence snapshot**; each subsequent event
  (ISSUE, LIST, SALE, SPLIT, RETIRE, MONITOR) hashes the previous state into the new one —
  an internal chain anyone can recompute (`GET /ledger/{farm_id}` verifies it).
- Stored in Supabase `ledger_events` (`payload_json` keeps hashes byte-exact), with a local-file
  fallback. No gas fees, no wallets.
- Escrow is **simulated and clearly labelled**; production moves to a payment-gateway escrow.
- Production roadmap: settlement moves to Polygon — the architecture is identical, only the
  settlement substrate changes.

### Verification tiers

Land records resolve to tiers/badges that gate marketplace eligibility:
`1A` (registry geometry + owner/area match) → badge `REGISTRY`; `1B` → `REGISTRY_DOC`;
`2` (not in registry) → `DOCUMENT`; FPO path → `FPO` after officer confirmation. Any hard fraud
failure (Aadhaar checksum, OCR readability, EXIF, geocode, duplicate document, name match, polygon
overlap) → status `FLAGGED`, badge stripped, routed to the FPO.

---

## Architecture

```
        ANDROID PHONE (Farmer, PWA)              WEB APP (React/Vite)
   on-device OCR · Sarvam voice · camera    voice assistant · Leaflet map ·
   GPS · offline shell (service worker)     FPO + corporate dashboards
                  |                                        |
                  |  REST (/py-api)                        |
                  v                                        v
        SUPABASE — the backbone  <-------------------------+
   Auth (OTP/JWT) · Postgres · Storage · Realtime · Edge logic
   Tables: profiles · farms · fpos · corporates · land_registry ·
   fpo_members · kyc_verifications · marketplace_listings ·
   otp_codes · ledger_events
   Credits anchored with SHA-256 hash (tamper-evident)
          |                              |
   NDVI / satellite                 role-based access
          v                              v
  GOOGLE EARTH ENGINE /         TRUST LAYER (backend/app/services/)
  Sentinel-2 NDVI               split_engine · ledger · credit_engine ·
  (free tier, 5-day revisit)    fraud_engine · trust_engine · market_store
```

Every layer runs on a free tier: Supabase free tier, Earth Engine developer access, open Sentinel-2
data. A district pilot needs no capital expenditure.

---

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | React 18, Vite, Tailwind CSS, Leaflet, PWA service worker (offline shell) |
| Backend | Python FastAPI (`backend/app`, served under `/py-api`) |
| Database / auth / storage | Supabase (Postgres + row-level security, OTP/JWT auth, Storage, Realtime) |
| Satellite | Google Earth Engine → Sentinel-2 SR (`COPERNICUS/S2_SR_HARMONIZED`), NDVI/EVI, 5-day revisit |
| Voice | Sarvam AI (STT `saaras:v3`, TTS `bulbul:v3`, chat `sarvam-105b-conversations`), default `te-IN`; Android TTS offline fallback |
| Documents | Tesseract OCR + Azure Document Intelligence (`prebuilt-layout`), Telangana **Pahani/Adangal** parser |
| OTP | Textplate SMS API, codes held in Redis with a 3-minute TTL |
| ML | scikit-learn biodiversity model (co-benefit indicator) |
| Certificates | reportlab (Verra-style A4 landscape PDF, batch hash) |
| Ledger | SHA-256 hash chain in Supabase `ledger_events` (Polygon on the roadmap) |

> **Legacy:** the old Node/Express + Solidity path (`backend/src/`, `blockchain/`) is kept only for
> history under `legacy/` and is **not** part of the running system. Production settlement is the
> hash ledger.

---

## Repository layout

```
src/                  React app (farmer, FPO, corporate dashboards; voice agent; PWA)
backend/app/          FastAPI service
  services/           credit_engine · split_engine · ledger · trust_engine ·
                      fraud_engine · kyc_service · pahani_parser · ml_service · …
  voice_agent/        Sarvam voice routes
  tests/              hermetic + integration suites
supabase/             schema + incremental migrations
scripts/              seed + demo-data generators
docs/                 ARCHITECTURE.md · DEPLOYMENT.md
public/               PWA manifest + service worker
legacy/               retired Express + Solidity code (not used)
```

---

## Getting started

```bash
# 1) Environment
cp .env.example .env                      # root: Supabase URL + anon key
cp .env.example backend/.env              # backend: add service-role key + the rest

# 2) Frontend
npm install && npm run dev                # http://localhost:5000

# 3) Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000  # proxied at /py-api
```

Optional but recommended for a full local run: a Supabase project, a Google Earth Engine service
account, and a Sarvam API key. Without them the app still starts and degrades honestly — see below.

---

## API reference (selected)

**Auth** — `POST /send-otp` · `POST /register/verify-otp` · `POST /register` · `POST /login` · `POST /corporate/login`
**Onboarding** — `POST /auto-draw` · `POST /check-farmland` · `POST /verify-aadhaar` · `POST /verify-land` · `GET /kyc/status/{phone}`
**Satellite & credits** — `POST /analyze` · `GET /predict` · `POST /save-farm` · `GET /farm/{farm_id}/ndvi-history` · `POST /farms/earnings-calculator`
**FPO** — `GET /fpo/pending` · `GET /fpo/flagged` · `POST /fpo/confirm/{farm_id}` · `POST /fpo/review/{farm_id}` · `POST /fpo/onboard`
**Marketplace** — `GET|POST /marketplace/listings` · `POST /marketplace/buy` · `POST /marketplace/auto-match`
**Certificates & ledger** — `GET /certificates` · `GET /certificates/{id}/pdf` · `POST /certificates/{id}/retire` · `GET /passport/{farm_id}` · `GET /wallet` · `GET /ledger/{farm_id}`

---

## Testing

```bash
cd backend
python -m unittest discover tests -v
```

- **Hermetic (always run):** trust layer — split arithmetic, hash ledger (incl. tamper detection),
  credit engine (5 steps, determinism, uncertainty bounds), Stage-1 verification, Aadhaar
  validation, ML inference, `/analyze` and `/predict` contracts.
- **Integration (skip when Supabase is unconfigured):** registration/login, profile, save-farm,
  marketplace, KYC — marked with `@requires_supabase`, so CI (which blanks credentials) stays green.

Current status: **42 passing · 6 integration skipped** without live services.

---

## Design principles

1. **Never invent data.** If live satellite data is unavailable, the API issues no credit and says
   so — it does not fabricate an NDVI to make a number appear.
2. **One credit maths.** Every credit figure comes from the canonical engine.
3. **The farmer's floor is sacred.** 70% is guaranteed; split arithmetic cannot dilute it.
4. **Conservative by design.** A 10–30% uncertainty deduction means buyers are never over-sold.
5. **Transparency over promises.** The farmer sees price, split, recipients and the verification
   hash — in one screen.

---

## Honest limitations

- Full VM0042-grade precision needs field trials; the calculation mirrors the methodology's
  structure, simplified, and claims no lab-grade accuracy.
- The NDVI→biomass proxy needs region-specific calibration; the uncertainty deduction is the
  honest bridge until pilot data replaces it.
- No universal cultivation-proof document exists in India; FPO/community attestation covers it
  rather than a fictional solved system.
- Under current CCTS rules, offset credits serve **voluntary** buyers; a compliance linkage is a
  later-phase upside, not today's demand.
- Escrow is simulated in this build; production requires a gateway escrow arrangement.

---

## Roadmap

**Phase 0** — one district, one FPO, 200–500 farmers; calibrate the NDVI proxy. →
**Phase 1** — first cooperative purchase; gateway escrow. →
**Phase 2** — Polygon settlement; third-party audit of the calculation engine. →
**Phase 3** — state-scale via FPO federations; water and biodiversity instruments on the same rails.

---

## License

MIT — see [LICENSE](LICENSE).
