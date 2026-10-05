# CarbonX (GraminCarbon)

> Satellite-verified carbon + biodiversity credits for Indian smallholder farmers.
> **The phone is the MRV lab.**

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![CI](https://github.com/sreethan05/carbon-x/actions/workflows/ci.yml/badge.svg)](https://github.com/sreethan05/carbon-x/actions/workflows/ci.yml)
[![Status: Pilot-ready MVP](https://img.shields.io/badge/Status-Pilot--ready--MVP-orange)]()

---

## What it is

A platform where farmers get verified and paid for carbon-positive practices
using AI and free satellite data, FPOs bridge farmers who cannot self-onboard,
and transparent, hash-anchored credits are sold to corporate buyers — with the
**70% farmer floor enforced in code, not in a promise**.

The headline fact: India has 146 million farm holdings; agriculture emits
~14% of its greenhouse gases yet has received **~0.2% of its issued carbon
credits** — because verification costs more than smallholder credits earn.
CarbonX collapses verification from ₹2,000+ per soil test and 6–12-month
audits to **≈₹29/farm/year**, monitored every 5 days by Sentinel-2.

## The five-flow trust pipeline

1. **Register & Validate** — phone OTP, OCR of any land document (Aadhaar
   optional; only last-4 ever stored), map-drawn boundary; failed checks
   escalate to the FPO queue, never silently dropped.
2. **Verify (Stage 1)** — declared crop cross-checked against Sentinel-2 NDVI
   signatures; mismatch pauses for FPO/KVK human review.
3. **Calculate (Stage 2)** — VM0042-aligned five-step math: additionality,
   biomass proxy, IPCC-style soil factor — minus a 10–30% evidence-quality
   uncertainty deduction with a CI on every credit.
4. **Anchor & Monitor** — SHA-256 evidence chain per credit (Supabase
   `ledger_events`); 5-day NDVI cycle flags at-risk credits to FPO review.
5. **Sell & Split** — matching with farmer-level breakdown shown *before*
   payment; escrow → conditional split (farmer 70 / FPO 5 when involved /
   platform 25–30) → purchase = instant retirement → PDF certificate with
   batch hash.

Full detail: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) ·
[docs/MRV_METHODOLOGY.md](docs/MRV_METHODOLOGY.md) ·
[docs/MODEL_CARD.md](docs/MODEL_CARD.md)

## Honest boundaries — what's real vs roadmap

**Real & running (verifiable in this repo):** the full loop above, on live
Supabase — registration, boundary+satellite scan, Stage-1/2 verification,
hash ledger with public recompute, marketplace, conditional splits,
instant-retirement certificates as downloadable PDFs, FPO verification desk,
5-day monitoring, offline demo mode, 39 backend tests, CI.

**Simulated & labelled:** escrow (production = payment-gateway route/hold),
UPI payout (rails simulated), land registry (30 seeded parcels; production
path = Dharani/Bhu-Naksha integration).

**Roadmap:** ground-truth SOC calibration (table + eval endpoint already
built — needs field data), registry listing (Verra/GS), Polygon settlement
(service scaffolded), production SMS provider.

We retired our own first model for circular validation rather than show a
fake 99% — [docs/MODEL_CARD.md](docs/MODEL_CARD.md) explains.

## Differentiation

| vs incumbents | CarbonX |
|---|---|
| Verification by satellites-only or field agents | **Farmer's own device** + satellite corroboration + FPO human review |
| Opaque payouts, up to 70% diverted by intermediaries | Code-enforced 70% floor, per-credit auditable payout lines |
| Requires documents + digital literacy | Document-less FPO-assisted path with auto-escalation |
| Carbon-only | **Dual carbon + biodiversity score** on the same rails |

## Quickstart

```powershell
# 1. Frontend + backend deps
npm install
cd backend && pip install -r requirements.txt && cd ..

# 2. Configure (see .env.example and backend/.env)
#    Supabase URL + service-role key are the only hard requirements.

# 3. Seed demo data (idempotent)
python scripts/seed_marketplace_data.py
python scripts/seed_land_registry.py

# 4. Run
npm run dev                                  # frontend → http://localhost:5000
cd backend; python -m uvicorn app.main:app --port 8000   # API

# 5. Prove the trust story
python scripts/tamper_demo.py                # watch the ledger catch a tamper
python scripts/simulate_scale.py 100000      # throughput + unit economics
```

With credentials removed, the stack degrades honestly: demo mode (sample
marketplace data, demo farmer login), labelled heuristics instead of the ML
model, and every surface shows what it is running on.

## Tests & CI

```powershell
cd backend; python -m unittest discover tests   # 44 tests: split/ledger/credit/ML-serving
npm run lint && npm run build
```

CI runs lint + build + the backend suite on every push
(.github/workflows/ci.yml).

## Repository map

```
src/                    React 18 + Vite + Tailwind frontend (port 5000)
backend/app/            FastAPI (port 8000) — auth, farms, marketplace,
                        trust engine, splits, ledger, certificates, ops
backend/app/services/   split_engine · ledger · credit_engine ·
                        ml_service · trust_engine · fraud_engine · …
backend/src/            optional Polygon-minting service (port 3001, roadmap)
scripts/                seeding · scale simulation · tamper demo
docs/                   architecture · methodology · model card · economics ·
                        compliance · impact · demo script · roadmap · deployment
```

## License

MIT — see [LICENSE](LICENSE).
