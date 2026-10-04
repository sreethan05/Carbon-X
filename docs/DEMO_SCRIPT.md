# 3-Minute Demo Script + Judge-Question Armor

## The script (every step runs on the live system)

**0:00 — The number.** "India has 146 million farm holdings. Agriculture
emits 14% of the country's greenhouse gases — and has received **0.2% of its
own carbon credits**. Not because farmers don't sequester — because
verification costs more than their credits earn. Watch the whole loop,
live."

**0:25 — Register.** Farmer login on the phone: enter number, OTP arrives
(dev mode shown honestly), done. "No Aadhaar card needed — OCR reads
whatever land document they have. Only the last 4 digits are ever stored."

**0:50 — Scan.** Draw the boundary on the map, run the satellite scan:
Sentinel-2 NDVI/EVI, the Trust Engine's Stage-1 verdict (crop vs satellite
signature), Stage-2 five-step calculation with the uncertainty deduction
**shown line by line** — "every number on this screen can be recomputed by
hand; we tell farmers exactly why they got the score they got."

**1:20 — The passport.** Carbon Passport: credits, expected earnings in
rupees, evidence quality ("add a photo, earn more — the deduction shrinks"),
tamper-evident ledger tail hash, CHAIN VERIFIED.

**1:45 — Sell.** Switch to the corporate buyer: bulk auto-match 100 credits
— the farmer-level breakdown appears **before** money moves. Purchase →
escrow → **the split on screen: farmer 70% / FPO 5% / platform 25%** →
credits retired in the same step → certificate.

**2:15 — The proof.** Open the certificate PDF: buyer, volume, region,
**SHA-256 batch hash**. Then the greenwashing defense, live:
`python scripts/tamper_demo.py` — edit a ledger record, recompute, **watch
the chain break at the exact tampered event**. "This is what we mean by
hash-anchored. Not a slide — a recompute anyone can run."

**2:45 — Close.** "Verification cost per farm per year: about ₹29, versus
₹2,000+ for a single soil test. Break-even at 649 farms. One FPO clears
that in a season. The farmer keeps 70% — that's not a promise, it's an
invariant with unit tests."

**Backup:** a screen recording of this exact flow lives in `demo-assets/`
(record before every submission; see the checklist below).

## Judge-question armor

**"How do you know your carbon number is real?"** — Honest answer: today it
is a conservative proxy with visible uncertainty (10–30% deduction, CI on
every credit), calibrated on real GBIF data for biodiversity and designed
for SOC ground-truthing. The `ground_truth_samples` table + error report is
built for exactly this: soil-health-card or field-survey values go in,
"estimate vs measured error = X%" comes out. Phase 0 is 20–50 calibration
plots. We refuse to show a fake accuracy number — the previous version of
our own model had one and we retired it (see docs/MODEL_CARD.md).

**"Why blockchain? Why not just a database?"** — We don't use blockchain.
We use a SHA-256 hash chain in Postgres: tamper-evidence without gas fees
or wallets. The recompute demo you just saw is the whole point. Production
settlement can move to Polygon with identical architecture — only the
substrate changes.

**"Why would an FPO not become another extractor?"** — It earns 5% only
when the system proves verification work on that credit (farm linked to
FPO). No work, no cut. And the farmer's screen shows the full split —
opacity is what enabled legacy extraction.

**"Can a farmer claim a forest they didn't plant?"** — Three layers:
geotag-inside-boundary enforcement, boundary-overlap detection against all
other farms, and Stage-1 crop-vs-NDVI signature checks. Mismatches pause
for FPO/KVK human review — satellites check, humans judge.

**"What if the farmer's crop fails?"** — The 5-day NDVI cycle catches the
drop, flags credits at-risk, routes to FPO review before purchase — buyers
are protected, and honest farmers are protected by distinguishing genuine
reversals from data noise.

**"Is this CCTS-compliant demand?"** — No, and we say so: today's demand is
voluntary corporate buyers. The compliance linkage is upside as BEE's
offset market matures. Our evidence chain is built to registry standards so
that transition needs no re-architecture.

## Pre-demo checklist

- [ ] `npm run dev` + backend up; `GET /health` shows `database.ready: true`
- [ ] Seeded data present (`scripts/seed_marketplace_data.py`,
      `scripts/seed_land_registry.py`)
- [ ] Screen recording of the full flow saved to `demo-assets/`
- [ ] `python scripts/tamper_demo.py` rehearsed once
- [ ] One retired certificate ready to download as PDF
