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

## Honest performance
See `backend/ml/config/feature_config.json` for the current numbers
(`test_r2`, `test_mae_species`). Expect an R² well below 1.0 — **that is the
point**. Species richness is only partially explainable from 10 m vegetation
indices, and GBIF citizen-science data is sampling-biased (the observation
weights compensate only partially). The previous v2 model's 0.989 "R²" was
circular: its label was a deterministic formula of its own input features.
That model was retired.

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
