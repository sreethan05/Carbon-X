# CarbonX MRV Methodology (v1.0 — implementation-aligned)

This document states exactly how CarbonX measures, reports and verifies soil
carbon and biodiversity gains, aligned to the structure of Verra's VM0042
(Methodology for Improved Agricultural Land Management) and IPCC Tier 1
guidance. Every equation here is implemented in
`backend/app/services/credit_engine.py` — nothing in this document is
aspirational.

## 0. Status and honesty

- **What this is**: a working, conservative implementation of the VM0042
  structure at demonstration scale, with every intermediate number exposed
  for hand-verification.
- **What this is not**: registry-listed methodology (Verra/Gold Standard
  listing is the Phase-2 roadmap, see docs/ROADMAP.md), and not a claim of
  lab-grade SOC measurement. The uncertainty deduction is the honest bridge
  until ground-truth calibration data exists (`ground_truth_samples` table +
  `GET /ops/ground-truth/eval`).

## 1. Proxy chain (why NDVI is legitimate, and its limits)

The causal chain the methodology leans on:

> Sentinel-2 red/NIR → **NDVI** (canopy greenness) → proxy for **fPAR**
> (fraction of absorbed photosynthetically active radiation) → **GPP/NPP**
> (light-use-efficiency: Monteith 1972; running GPP models such as MOD17 and
> CASA use exactly this fPAR × LUE form) → net primary production allocated
> to roots/residue → **soil organic carbon (SOC)** change under conservation
> practices.

NDVI is a **productivity proxy**, not a direct carbon measurement. The
methodology therefore: (a) uses practice-specific factors for the SOC term
rather than NDVI alone; (b) deducts 10–30% for uncertainty; (c) requires
ground-truth calibration before any claim of measured accuracy.

## 2. Additionality (baseline vs project)

    Δ_NDVI = max(0, NDVI_project − NDVI_baseline)

Baseline = pre-enrollment NDVI (historical composite). Only the delta the
farmer created is creditable. Implemented as Step 1 in `estimate_credits`.

## 3. Above-ground biomass proxy (Step 2)

    Biomass_proxy(tCO2e/ha) = Base_crop × (0.7·NDVI + 0.3·(NDVI + Δ_NDVI)) / 0.75

- `Base_crop` per-crop factor (tCO₂e/ha/yr at reference NDVI 0.75) — see
  table below. The 0.47 dry-biomass carbon fraction and 3.67 CO₂→C mass
  ratio (IPCC 2006 GLs, Vol. 4 Ch. 4) are folded into the crop
  calibration and stated here explicitly.
- Practice signal: 30% of the biomass term is the improvement delta, so
  better practices raise the estimate without letting standing vegetation
  alone claim credit.

## 4. Soil organic carbon delta (Step 3)

Declared practice → SOC accumulation factor from a Tier-1-style lookup
(tCO₂e/ha/yr). Publication values used as reference points: IPCC 2006 GLs
Vol. 4 Table 6.2 (SOC stock change factors for land-use/management) and
IPCC 2019 Refinement; India-specific cropland factors from ICAR-CRIDA
(Srinivasarao et al. 2014). Current implementation factors (per crop):

| Crop | Biomass base | SOC factor | Reference basis |
|---|---|---|---|
| Rice/Paddy | 30 | 4.0 | flooded-rice SOC literature; low residue incorporation |
| Sugarcane | 58 | 6.0 | high biomass trash return |
| Cotton | 33 | 3.5 | — |
| Maize | 40 | 3.0 | — |
| Millets | 21 | 2.0 | low-input rainfed |
| Turmeric | 46 | 4.0 | — |
| Chilli | 27 | 2.5 | — |
| Default | 32 | 3.0 | mixed cropping |

These are **implementation factors for the demonstration build** — the
calibration study that replaces them with measured, region-specific values
is Phase 0 of the roadmap (docs/ROADMAP.md). The factors, their version,
and every input are anchored to each credit's ledger hash.

## 5. Combination (Step 4)

    Raw(tCO2e) = Area_ha × (Biomass_proxy + SOC_factor)

## 6. Uncertainty deduction & confidence interval (Step 5)

Evidence-quality score (0–1) over five components: practice photo (0.25),
geotag-inside-boundary (0.25), FPO/registry verification (0.25), current
satellite NDVI (0.15), established baseline (0.10).

    Uncertainty% = clamp(30 − 20 × quality, 10, 30)
    Credits      = Raw × (1 − Uncertainty%)
    CI90         = Credits ± 1.64 × (Uncertainty%) × Credits

Lower-quality evidence earns a smaller credit with a wider interval —
conservative by construction so buyers are never over-sold. Perfect
evidence still keeps a 10% honesty margin.

## 7. Biodiversity co-benefit model

Separate model (see docs/MODEL_CARD.md): GBIF species richness per 0.02°
cell, trained on real GBIF occurrences with real Sentinel-2 features
extracted via Earth Engine. Served as a relative 0–100 index, never
presented as a species census.

## 8. Satellite QA

- Cloud masking: images filtered to `CLOUDY_PIXEL_PERCENTAGE < 20`.
- Compositing: median composite over the window (robust to residual cloud).
- Time-series dispersion (NDVI_STD, B8_VAR) computed across the filtered
  collection — these are model features, not QA Theatre.
- Lineage: each scan records the Sentinel-2 scene id (`s2_scene`,
  `system:index`), satellite source, and model provenance
  (`ml_source`) in the API response and the ledger's ISSUE snapshot.
- Known gap: monsoon gap-filling is partially handled by the median
  composite; a documented multi-temporal gap-fill routine is roadmap
  (Phase 1).

## 9. Monitoring & permanence

Every 5 days (Sentinel-2 revisit), each farm's NDVI is compared to its last
snapshot; a drop ≥ 0.15 flags the credits at-risk → farm status `Flagged` →
FPO review queue, with a MONITOR event on the farm's hash chain. Retirement
at purchase removes resale/reversal ambiguity for buyers.

## 10. Data lineage & audit

Every credit's chain: ISSUE (evidence snapshot incl. scene id) → SALE →
SPLIT → RETIRE → MONITOR…, `sha256(seq|entity|type|payload|prev_hash)`.
Anyone can recompute: `GET /ledger/{farm_id}`. Tamper detection is
demonstrable: `python scripts/tamper_demo.py`.
