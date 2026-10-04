# Model Card — CarbonX Biodiversity Model (v2, honest)

## What it predicts
Species richness (number of unique species) for a 0.02° (~2 km) grid cell in
India, inferred from Sentinel-2 satellite features. Served to farmers as a
relative **biodiversity score (0–100)** scaled from the model's predicted
log-richness.

## Training data
- **Occurrences**: 5,868 GBIF human observations in India
  (api.gbif.org, pulled 2026-10-04, CC-licensed citizen science).
- **Grid**: 0.02° cells → 451 cells with ≥3 unique species.
- **Features**: 320 cells sampled evenly across 8 richness strata; real
  Sentinel-2 SR statistics extracted via Google Earth Engine
  (median composite 2023, cloud-filtered <20%): NDVI, NDWI, SAVI, B4, B8,
  B11 (means), NDVI_STD and B8_VAR (time-series dispersion).
- **Target**: `log1p(species_count)`; samples weighted by observation count
  (more observations → more reliable richness estimate).

## Model
Gradient Boosting / Random Forest (best by validation R²), scikit-learn.
Artifacts: `backend/ml/models/{biodiversity_model,feature_scaler,score_scaler}.pkl`
+ `model_card.json` (generated at train time by `src/train.py`).

## Honest performance (measured 2026-10-04, real GBIF data)

**v2 result: test R² = −0.165, MAE ≈ 4.0 species** (n_test = 32, 315 filtered
cells). The honest conclusion: **Sentinel-2 vegetation indices alone do not
predict GBIF citizen-science species richness** for this sample — a model
that generalises worse than predicting the mean. It is trained, versioned,
and archived with its true metrics (`ml/models/model_card.json`), and a
**quality gate** (`ml_service._MIN_SERVING_TEST_R2 = 0.2`) refuses to serve
any model below threshold — so the app currently serves the labelled
NDVI-only heuristic, and will automatically serve the model only when a
retrain clears the gate (planned: elevation, habitat-heterogeneity and
seasonal-contrast features; ground-truth plot data).

The previous v1 model's 0.989 "R²" was circular — its label was a
deterministic formula of its own input features. That model was retired.
Expecting R² near 1.0 on a genuine ecological target is the smell; the
uncertainty is priced into credits (10–30% deduction + CI).

## Why not 100% accuracy
100% classification accuracy (or R²=1) on a genuine ecological target means
one of three things: label leakage, a synthetic target, or an overfit test
set. None of those are quality. The uncertainty is priced into the platform:
credits already carry a 10–30% uncertainty deduction, so model imperfection
is visible and conservative rather than hidden.

## Serving contract (anti-skew guarantees)
1. **Single source of truth for features**: `/analyze` computes the 8
   features in Earth Engine using the exact same derivation as
   `src/extract_features.py` (indices, band means, collection variance) and
   passes them to the model.
2. **No fabricated inputs**: when real features are unavailable (Earth Engine
   offline, missing bands), the service refuses to invent them and falls back
   to an NDVI-only heuristic, clearly labelled in the response
   (`ml_source: "Heuristic (…)"`). The v1 behaviour — synthesising the other
   7 features from NDVI with made-up formulas — is removed.
3. **Range honesty**: training covers NDVI 0.02–0.95, matching the operating
   range of real farmland scans (v1 trained on 0.15–0.65 only).

## Retraining
```
cd src
python download_gbif.py        # or the bounded 6k variant used for v2
python aggregate_richness.py
python extract_sampled.py 320  # stratified, checkpointed EE extraction
python train.py                # honest target, writes model_card.json
# then copy artifacts/* to backend/ml/models/ and refresh feature_config.json
```

## Known limitations
- GBIF sampling bias (roads, parks, birders' routes) — richness is a floor,
  not a census; field validation remains necessary before credit-grade claims.
- Regional (India) and temporal (2023 composite) scope.
- The 0–100 score is a **relative index**, not a species census; never present
  it as an absolute count to farmers or buyers.
