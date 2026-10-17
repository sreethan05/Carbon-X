"""Honest biodiversity + SOC model training with spatial block CV + quantile regression.

Key improvements over v2:
1. **Spatial Block Cross-Validation** — leaves out entire spatial blocks (50km × 50km)
   to prevent spatial autocorrelation leakage that inflates R².
2. **Quantile Regression** — predicts P10/P50/P90 for uncertainty intervals
   that feed directly into credit_engine.ci90.
3. **Dual targets** — biodiversity (log1p species richness) + SOC (tCO2e/ha from SoilGrids).
4. **Model card** — honest metrics including spatial CV scores and quantile coverage.
"""
import json
import os
import time
import warnings
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import QuantileRegressor
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler, MinMaxScaler

# ─── Config ───
DATA_DIR = Path(__file__).resolve().parent / "data"
if not DATA_DIR.exists():
    DATA_DIR = Path(__file__).resolve().parents[1] / "data"
ARTIFACTS_DIR = Path(__file__).resolve().parents[1] / "backend" / "ml" / "models"
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

# Feature columns (must match extract_features.py output)
FEATURE_COLS = [
    # Core S2 (8)
    "NDVI", "NDWI", "SAVI", "B4", "B8", "B11", "NDVI_STD", "B8_VAR",
    # Red-edge (3)
    "NDRE", "IRECI", "CIre",
    # Seasonal (3)
    "KHARIF_NDVI", "RABI_NDVI", "SEASONAL_CONTRAST",
    # Heterogeneity (1)
    "NDVI_RANGE",
    # Phenology (4)
    "NDVI_AMPLITUDE", "NDVI_INTEGRAL", "SOS_DOY", "EOS_DOY",
    # Terrain (3)
    "ELEVATION", "SLOPE", "ASPECT",
    # SAR (4)
    "S1_VV", "S1_VH", "S1_VV_VH_RATIO", "S1_VV_STD",
    # GEDI (2)
    "GEDI_RH98", "GEDI_AGBD",
    # SoilGrids prior (5)
    "SOILGRIDS_SOC_MEAN", "SOILGRIDS_SOC_STOCK",
    "SOILGRIDS_SOC_Q05", "SOILGRIDS_SOC_Q50", "SOILGRIDS_SOC_Q95",
]

# Spatial block size for CV (degrees ≈ 50km at equator)
BLOCK_SIZE_DEG = 0.5
NDVI_MIN, NDVI_MAX = 0.02, 0.95

# Feature columns that were backfilled (with stand-in values) because the
# extraction CSV did not contain them. Recorded in the model card; the serving
# quality gate refuses models trained on backfilled inputs.
BACKFILLED: dict = {}


def spatial_block_split(df, block_size=BLOCK_SIZE_DEG, test_frac=0.2, val_frac=0.1, seed=42):
    """Split data by spatial blocks to prevent leakage.
    
    Args:
        df: DataFrame with 'latitude', 'longitude' columns
        block_size: Size of spatial blocks in degrees
        test_frac: Fraction of blocks for test
        val_frac: Fraction of blocks for validation
        seed: Random seed for block assignment
    
    Returns:
        train_idx, val_idx, test_idx (boolean masks)
    """
    np.random.seed(seed)
    
    # Assign each point to a block
    df = df.copy()
    df["block_lat"] = np.floor(df["latitude"] / block_size).astype(int)
    df["block_lon"] = np.floor(df["longitude"] / block_size).astype(int)
    df["block_id"] = df["block_lat"].astype(str) + "_" + df["block_lon"].astype(str)
    
    unique_blocks = df["block_id"].unique()
    n_blocks = len(unique_blocks)
    
    # Shuffle blocks
    shuffled = np.random.permutation(unique_blocks)
    
    n_test = max(1, int(n_blocks * test_frac))
    n_val = max(1, int(n_blocks * val_frac))
    
    test_blocks = set(shuffled[:n_test])
    val_blocks = set(shuffled[n_test:n_test + n_val])
    train_blocks = set(shuffled[n_test + n_val:])
    
    print(f"Spatial CV: {len(train_blocks)} train blocks, {len(val_blocks)} val blocks, {len(test_blocks)} test blocks")
    print(f"  Total blocks: {n_blocks}, block size: {block_size}° (~{block_size * 111:.0f} km)")
    
    train_mask = df["block_id"].isin(train_blocks)
    val_mask = df["block_id"].isin(val_blocks)
    test_mask = df["block_id"].isin(test_blocks)
    
    return train_mask, val_mask, test_mask


def prepare_data():
    """Load and prepare data for both biodiversity and SOC targets."""
    features_path = DATA_DIR / "satellite_features_v3.csv"
    if not features_path.exists():
        features_path = DATA_DIR / "satellite_features_v2.csv"
    if not features_path.exists():
        raise FileNotFoundError(f"Features file not found in {DATA_DIR}.")
    
    df = pd.read_csv(features_path)
    print(f"Loaded {len(df)} rows from {features_path}")

    # ─── Column provenance ───
    # v2 extraction produced 11 of the 33 contract features. Missing INPUT
    # columns are backfilled with stand-ins so the pipeline can still run on
    # v2 data, but every backfill is recorded in the model card and the
    # serving gate refuses models trained on backfilled inputs. Targets are
    # NEVER backfilled — deriving a label from a stand-in column is what made
    # the old SOC model circular (R²=1.0, MAE≈5e-14).
    def _backfill(col, value, note):
        if col not in df.columns:
            df[col] = value
            BACKFILLED[col] = note
        elif df[col].isna().any():
            df[col] = df[col].fillna(value)
            BACKFILLED[col] = note

    _backfill("NDRE", ((df["B8"] - df["B4"]) / (df["B8"] + df["B4"] + 1e-6) * 0.75).clip(-0.5, 0.95),
              "NDVI-family stand-in (no red-edge bands in CSV)")
    _backfill("IRECI", ((df["B8"] - df["B4"]) / (df["B11"] + 1e-4)).clip(-1.0, 5.0),
              "NDVI-family stand-in (no red-edge bands in CSV)")
    _backfill("CIre", (df["B8"] / (df["B4"] + 1e-4) - 1.0).clip(-1.0, 10.0),
              "NDVI-family stand-in (no red-edge bands in CSV)")
    _backfill("KHARIF_NDVI", (df["NDVI"] + df.get("SEASONAL_CONTRAST", 0.1) * 0.5).clip(0.02, 0.95),
              "NDVI stand-in (no seasonal composites in CSV)")
    _backfill("RABI_NDVI", (df["NDVI"] - df.get("SEASONAL_CONTRAST", 0.1) * 0.5).clip(0.02, 0.95),
              "NDVI stand-in (no seasonal composites in CSV)")
    _backfill("NDVI_AMPLITUDE", (df.get("NDVI_RANGE", 0.2) * 0.8).clip(0.01, 0.8),
              "NDVI-range stand-in (no phenology in CSV)")
    _backfill("NDVI_INTEGRAL", (df["NDVI"] * 365.0).clip(10.0, 350.0),
              "NDVI stand-in (no phenology in CSV)")
    _backfill("SOS_DOY", 160.0, "constant stand-in (no phenology in CSV)")
    _backfill("EOS_DOY", 310.0, "constant stand-in (no phenology in CSV)")
    _backfill("SLOPE", (1.5 + df.get("ELEVATION", 400.0) / 1000.0).clip(0.1, 45.0),
              "elevation-derived stand-in (no terrain slope in CSV)")
    _backfill("ASPECT", 180.0, "constant stand-in (no terrain aspect in CSV)")
    _backfill("S1_VV", (-14.0 + df["NDVI"] * 4.0).clip(-30.0, 0.0),
              "NDVI stand-in (no SAR in CSV)")
    _backfill("S1_VH", (-20.0 + df["NDVI"] * 5.0).clip(-35.0, 0.0),
              "NDVI stand-in (no SAR in CSV)")
    _backfill("S1_VV_VH_RATIO", 0.65, "constant stand-in (no SAR in CSV)")
    _backfill("S1_VV_STD", 1.2, "constant stand-in (no SAR in CSV)")
    _backfill("GEDI_RH98", (5.0 + df["NDVI"] * 25.0).clip(1.0, 50.0),
              "NDVI stand-in (no GEDI in CSV)")
    _backfill("GEDI_AGBD", (15.0 + df["NDVI"] * 110.0).clip(0.0, 300.0),
              "NDVI stand-in (no GEDI in CSV)")
    _backfill("SOILGRIDS_SOC_MEAN", (8.0 + df["NDVI"] * 15.0).clip(2.0, 50.0),
              "NDVI stand-in (no SoilGrids in CSV)")

    # SOC target availability is decided BEFORE any stand-in is added.
    soc_target_available = "SOILGRIDS_SOC_STOCK" in df.columns and df["SOILGRIDS_SOC_STOCK"].notna().any()
    _backfill("SOILGRIDS_SOC_STOCK", (35.0 + df["NDVI"] * 40.0).clip(10.0, 150.0),
              "linear NDVI stand-in — input feature only, NEVER usable as a target")
    _backfill("SOILGRIDS_SOC_Q05", (df["SOILGRIDS_SOC_STOCK"] * 0.6).clip(5.0, 100.0),
              "stock-derived stand-in (no SoilGrids quantiles in CSV)")
    _backfill("SOILGRIDS_SOC_Q50", df["SOILGRIDS_SOC_STOCK"],
              "stock-derived stand-in (no SoilGrids quantiles in CSV)")
    _backfill("SOILGRIDS_SOC_Q95", (df["SOILGRIDS_SOC_STOCK"] * 1.5).clip(15.0, 250.0),
              "stock-derived stand-in (no SoilGrids quantiles in CSV)")

    # Filter valid rows ONCE, before any target is derived, so features and
    # labels always share one index (the old code computed y_bio before a
    # later row filter and could silently misalign X with y).
    df = df.dropna(subset=FEATURE_COLS)
    df = df[(df["NDVI"] >= NDVI_MIN) & (df["NDVI"] <= NDVI_MAX)]
    if "species_count" in df.columns:
        df = df[df["species_count"] > 1]
    if soc_target_available:
        df = df[df["SOILGRIDS_SOC_STOCK"].notna()]
    print(f"After validity filter: {len(df)}")

    # Target 1: Biodiversity (log1p species richness) — real GBIF observations.
    if "species_count" in df.columns:
        y_bio = np.log1p(df["species_count"].values)
        obs = df.get("observation_count", pd.Series(1, index=df.index)).values
        w_bio = 1 + 9 * (obs - obs.min()) / (obs.max() - obs.min() + 1e-8)
        print(f"Biodiversity target: {len(y_bio)} samples, richness range [{df['species_count'].min()}, {df['species_count'].max()}]")
    else:
        y_bio = None
        w_bio = None

    # Target 2: SOC (tCO2e/ha) — ONLY from the real SoilGrids stock column.
    if soc_target_available:
        # SoilGrids stock is t C/ha → convert to tCO2e/ha
        y_soc = df["SOILGRIDS_SOC_STOCK"].values * 3.67
        w_soc = np.ones_like(y_soc)  # Equal weight for SOC
        print(f"SOC target: {len(y_soc)} samples, range [{y_soc.min():.1f}, {y_soc.max():.1f}] tCO2e/ha")
    else:
        y_soc = None
        w_soc = None
        print("SOC target SKIPPED: real SoilGrids SOC stock column absent from the features CSV")
    
    X = df[FEATURE_COLS].values
    
    # Spatial block split
    train_mask, val_mask, test_mask = spatial_block_split(df)
    
    X_train, X_val, X_test = X[train_mask], X[val_mask], X[test_mask]
    
    results = {
        "X_train": X_train, "X_val": X_val, "X_test": X_test,
        "train_mask": train_mask, "val_mask": val_mask, "test_mask": test_mask,
        "df_train": df[train_mask], "df_val": df[val_mask], "df_test": df[test_mask],
    }
    
    if y_bio is not None:
        results.update({
            "y_bio_train": y_bio[train_mask], "y_bio_val": y_bio[val_mask], "y_bio_test": y_bio[test_mask],
            "w_bio_train": w_bio[train_mask], "w_bio_val": w_bio[val_mask], "w_bio_test": w_bio[test_mask],
        })
    
    if y_soc is not None:
        results.update({
            "y_soc_train": y_soc[train_mask], "y_soc_val": y_soc[val_mask], "y_soc_test": y_soc[test_mask],
            "w_soc_train": w_soc[train_mask], "w_soc_val": w_soc[val_mask], "w_soc_test": w_soc[test_mask],
        })
    
    # Fit scaler on training data only
    scaler = StandardScaler().fit(X_train)
    joblib.dump(scaler, ARTIFACTS_DIR / "feature_scaler.pkl")
    
    results["X_train_scaled"] = scaler.transform(X_train)
    results["X_val_scaled"] = scaler.transform(X_val)
    results["X_test_scaled"] = scaler.transform(X_test)
    
    return results


def train_quantile_model(X_train, y_train, quantile, sample_weight=None):
    """Train a QuantileRegressor for a specific quantile."""
    # QuantileRegressor is more stable than GradientBoosting for quantiles
    model = QuantileRegressor(
        quantile=quantile,
        alpha=0.1,  # Light regularization
        solver="highs"
    )
    model.fit(X_train, y_train, sample_weight=sample_weight)
    return model


def evaluate_quantiles(models, X, y_true, prefix=""):
    """Evaluate quantile models: coverage, MAE, interval width."""
    preds = {}
    for q, model in models.items():
        preds[q] = model.predict(X)
    
    # Coverage: fraction of true values within [P10, P90]
    lower = preds[0.1]
    upper = preds[0.9]
    coverage = np.mean((y_true >= lower) & (y_true <= upper))
    
    # MAE at median
    mae = mean_absolute_error(y_true, preds[0.5])
    
    # Mean interval width
    width = np.mean(upper - lower)
    
    # R² at median
    r2 = r2_score(y_true, preds[0.5])
    
    print(f"  {prefix}Quantile eval: R²={r2:.3f}, MAE={mae:.3f}, "
          f"Coverage={coverage:.2%}, Mean width={width:.3f}")
    
    return {"r2": r2, "mae": mae, "coverage": coverage, "width": width}


def train_target(name, X_train, y_train, w_train, X_val, y_val, X_test, y_test):
    """Train quantile models for a single target."""
    print(f"\n{'='*60}")
    print(f"Training {name} quantile models")
    print(f"{'='*60}")
    print(f"Train: {len(y_train)}, Val: {len(y_val)}, Test: {len(y_test)}")
    
    # Train three quantiles: 0.1, 0.5, 0.9
    quantiles = [0.1, 0.5, 0.9]
    models = {}
    
    for q in quantiles:
        print(f"  Training quantile {q}...")
        models[q] = train_quantile_model(X_train, y_train, q, sample_weight=w_train)
    
    # Evaluate on validation
    print("Validation metrics:")
    val_metrics = evaluate_quantiles(models, X_val, y_val, "Val ")
    
    # Evaluate on test
    print("Test metrics:")
    test_metrics = evaluate_quantiles(models, X_test, y_test, "Test ")
    
    # Save models
    for q in quantiles:
        joblib.dump(models[q], ARTIFACTS_DIR / f"{name}_quantile_{q:.1f}.pkl")
    
    # Score scaler for biodiversity (map median prediction to 0-100)
    if name == "biodiversity":
        median_preds = models[0.5].predict(X_train)
        ss = MinMaxScaler(feature_range=(0, 100)).fit(median_preds.reshape(-1, 1))
        joblib.dump(ss, ARTIFACTS_DIR / "biodiversity_score_scaler.pkl")
    
    return models, {
        "val": val_metrics,
        "test": test_metrics,
        "n_train": int(len(y_train)),
        "n_val": int(len(y_val)),
        "n_test": int(len(y_test)),
    }


def train_comparison_models(X_train, y_train, w_train, X_val, y_val, name):
    """Train standard models for comparison (RandomForest, GradientBoosting)."""
    print(f"\nTraining comparison models for {name}...")
    
    models = {
        "rf": RandomForestRegressor(n_estimators=300, max_depth=10, min_samples_leaf=3, 
                                     random_state=42, n_jobs=-1),
        "gb": GradientBoostingRegressor(n_estimators=300, max_depth=4, learning_rate=0.03,
                                         subsample=0.9, random_state=42),
    }
    
    results = {}
    for mname, model in models.items():
        model.fit(X_train, y_train, sample_weight=w_train)
        val_pred = model.predict(X_val)
        val_r2 = r2_score(y_val, val_pred)
        val_mae = mean_absolute_error(y_val, val_pred)
        print(f"  {mname}: Val R²={val_r2:.3f}, MAE={val_mae:.3f}")
        joblib.dump(model, ARTIFACTS_DIR / f"{name}_{mname}.pkl")
        results[mname] = {"val_r2": val_r2, "val_mae": val_mae}
    
    return results


def main():
    print("=" * 70)
    print("CARBONX MODEL TRAINING — SPATIAL CV + QUANTILE REGRESSION")
    print("=" * 70)

    # Remove legacy v1 artifacts that the current pipeline never writes and no
    # serving code loads (pre-quantile single-model files). Leaving them in
    # the models dir misleads anyone inspecting what is actually served.
    for legacy in ("biodiversity_model.pkl", "score_scaler.pkl"):
        legacy_path = ARTIFACTS_DIR / legacy
        if legacy_path.exists():
            legacy_path.unlink()
            print(f"Removed legacy artifact: {legacy}")

    # Prepare data
    data = prepare_data()
    
    all_metrics = {
        "trained_at": time.strftime("%Y-%m-%d"),
        "feature_cols": FEATURE_COLS,
        "features_source": "extracted" if not BACKFILLED else "backfilled",
        "backfilled_features": BACKFILLED,
        "gate": {
            "min_spatial_cv_r2": 0.2,
            "requires_features_source": "extracted",
        },
    }
    if BACKFILLED:
        print(f"\nWARNING: {len(BACKFILLED)} feature(s) backfilled with stand-ins — "
              "models trained from this run will be recorded as 'backfilled' and "
              "the serving quality gate will refuse them until a real v3 "
              "extraction is used.")
    
    # Train biodiversity model (if target available)
    if "y_bio_train" in data:
        bio_models, bio_metrics = train_target(
            "biodiversity",
            data["X_train_scaled"], data["y_bio_train"], data["w_bio_train"],
            data["X_val_scaled"], data["y_bio_val"],
            data["X_test_scaled"], data["y_bio_test"]
        )
        bio_comparison = train_comparison_models(
            data["X_train_scaled"], data["y_bio_train"], data["w_bio_train"],
            data["X_val_scaled"], data["y_bio_val"], "biodiversity"
        )
        all_metrics["biodiversity"] = {
            "quantile": bio_metrics,
            "comparison": bio_comparison,
        }
    else:
        all_metrics["biodiversity"] = {
            "status": "not_trained",
            "reason": "species_count absent from the features CSV (run download_gbif.py + aggregate_richness.py first)",
        }
    
    # Train SOC model (if target available)
    if "y_soc_train" in data:
        soc_models, soc_metrics = train_target(
            "soc",
            data["X_train_scaled"], data["y_soc_train"], data["w_soc_train"],
            data["X_val_scaled"], data["y_soc_val"],
            data["X_test_scaled"], data["y_soc_test"]
        )
        soc_comparison = train_comparison_models(
            data["X_train_scaled"], data["y_soc_train"], data["w_soc_train"],
            data["X_val_scaled"], data["y_soc_val"], "soc"
        )
        all_metrics["soc"] = {
            "quantile": soc_metrics,
            "comparison": soc_comparison,
        }
    else:
        # Remove stale SOC artifacts from previous (circular-target) runs so
        # they can never be served: a model whose label was rebuilt from an
        # input column reports R²=1.0 while learning nothing.
        removed = []
        for pattern in ("soc_quantile_*.pkl", "soc_rf.pkl", "soc_gb.pkl"):
            for path in ARTIFACTS_DIR.glob(pattern):
                path.unlink()
                removed.append(path.name)
        all_metrics["soc"] = {
            "status": "not_trained",
            "reason": ("real SoilGrids SOC stock absent from the features CSV; "
                       "rebuilding the target from NDVI would be circular. "
                       "Run scripts/ingest_soilgrids.py and a real feature "
                       "extraction before training SOC."),
            "removed_stale_artifacts": removed,
        }
    
    # Write comprehensive model card
    with open(ARTIFACTS_DIR / "model_card.json", "w") as f:
        json.dump(all_metrics, f, indent=2, default=str)
    
    print("\n" + "=" * 70)
    print("TRAINING COMPLETE")
    print("=" * 70)
    print(f"Artifacts saved to: {ARTIFACTS_DIR}")
    print("  - feature_scaler.pkl")
    if "quantile" in all_metrics.get("biodiversity", {}):
        print("  - biodiversity_quantile_{0.1,0.5,0.9}.pkl + biodiversity_score_scaler.pkl")
    if "quantile" in all_metrics.get("soc", {}):
        print("  - soc_quantile_{0.1,0.5,0.9}.pkl")
    else:
        print(f"  - soc models NOT trained: {all_metrics['soc']['reason']}")
    print("  - model_card.json (honest metrics with spatial CV)")
    print("\nKey metrics:")
    for target in ["biodiversity", "soc"]:
        m = all_metrics.get(target, {})
        if "quantile" in m:
            t = m["quantile"]["test"]
            print(f"  {target}: Test R²={t['r2']:.3f}, MAE={t['mae']:.3f}, "
                  f"Coverage={t['coverage']:.1%}, Width={t['width']:.3f}")
        else:
            print(f"  {target}: NOT TRAINED ({m.get('reason', 'target unavailable')})")


if __name__ == "__main__":
    main()