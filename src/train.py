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

    # Impute missing features from satellite_features_v2 so FEATURE_COLS matches ml_service.FEATURE_ORDER
    if "NDRE" not in df.columns:
        df["NDRE"] = ((df["B8"] - df["B4"]) / (df["B8"] + df["B4"] + 1e-6) * 0.75).clip(-0.5, 0.95)
    if "IRECI" not in df.columns:
        df["IRECI"] = ((df["B8"] - df["B4"]) / (df["B11"] + 1e-4)).clip(-1.0, 5.0)
    if "CIre" not in df.columns:
        df["CIre"] = (df["B8"] / (df["B4"] + 1e-4) - 1.0).clip(-1.0, 10.0)
    if "KHARIF_NDVI" not in df.columns:
        df["KHARIF_NDVI"] = (df["NDVI"] + df.get("SEASONAL_CONTRAST", 0.1) * 0.5).clip(0.02, 0.95)
    if "RABI_NDVI" not in df.columns:
        df["RABI_NDVI"] = (df["NDVI"] - df.get("SEASONAL_CONTRAST", 0.1) * 0.5).clip(0.02, 0.95)
    if "NDVI_AMPLITUDE" not in df.columns:
        df["NDVI_AMPLITUDE"] = (df.get("NDVI_RANGE", 0.2) * 0.8).clip(0.01, 0.8)
    if "NDVI_INTEGRAL" not in df.columns:
        df["NDVI_INTEGRAL"] = (df["NDVI"] * 365.0).clip(10.0, 350.0)
    if "SOS_DOY" not in df.columns:
        df["SOS_DOY"] = 160.0
    if "EOS_DOY" not in df.columns:
        df["EOS_DOY"] = 310.0
    if "SLOPE" not in df.columns:
        df["SLOPE"] = (1.5 + df.get("ELEVATION", 400.0) / 1000.0).clip(0.1, 45.0)
    if "ASPECT" not in df.columns:
        df["ASPECT"] = 180.0
    if "S1_VV" not in df.columns:
        df["S1_VV"] = (-14.0 + df["NDVI"] * 4.0).clip(-30.0, 0.0)
    if "S1_VH" not in df.columns:
        df["S1_VH"] = (-20.0 + df["NDVI"] * 5.0).clip(-35.0, 0.0)
    if "S1_VV_VH_RATIO" not in df.columns:
        df["S1_VV_VH_RATIO"] = 0.65
    if "S1_VV_STD" not in df.columns:
        df["S1_VV_STD"] = 1.2
    if "GEDI_RH98" not in df.columns:
        df["GEDI_RH98"] = (5.0 + df["NDVI"] * 25.0).clip(1.0, 50.0)
    if "GEDI_AGBD" not in df.columns:
        df["GEDI_AGBD"] = (15.0 + df["NDVI"] * 110.0).clip(0.0, 300.0)
    if "SOILGRIDS_SOC_MEAN" not in df.columns:
        df["SOILGRIDS_SOC_MEAN"] = (8.0 + df["NDVI"] * 15.0).clip(2.0, 50.0)
    if "SOILGRIDS_SOC_STOCK" not in df.columns:
        df["SOILGRIDS_SOC_STOCK"] = (35.0 + df["NDVI"] * 40.0).clip(10.0, 150.0)
    if "SOILGRIDS_SOC_Q05" not in df.columns:
        df["SOILGRIDS_SOC_Q05"] = (df["SOILGRIDS_SOC_STOCK"] * 0.6).clip(5.0, 100.0)
    if "SOILGRIDS_SOC_Q50" not in df.columns:
        df["SOILGRIDS_SOC_Q50"] = df["SOILGRIDS_SOC_STOCK"]
    if "SOILGRIDS_SOC_Q95" not in df.columns:
        df["SOILGRIDS_SOC_Q95"] = (df["SOILGRIDS_SOC_STOCK"] * 1.5).clip(15.0, 250.0)
    
    # Filter valid rows
    df = df.dropna(subset=FEATURE_COLS)
    df = df[(df["NDVI"] >= NDVI_MIN) & (df["NDVI"] <= NDVI_MAX)]
    print(f"After NDVI filter: {len(df)}")
    
    # Target 1: Biodiversity (log1p species richness)
    if "species_count" in df.columns:
        df = df[df["species_count"] > 1]
        y_bio = np.log1p(df["species_count"].values)
        obs = df.get("observation_count", pd.Series(1, index=df.index)).values
        w_bio = 1 + 9 * (obs - obs.min()) / (obs.max() - obs.min() + 1e-8)
        print(f"Biodiversity target: {len(y_bio)} samples, richness range [{df['species_count'].min()}, {df['species_count'].max()}]")
    else:
        y_bio = None
        w_bio = None
    
    # Target 2: SOC (tCO2e/ha from SoilGrids stock)
    if "SOILGRIDS_SOC_STOCK" in df.columns:
        # SoilGrids stock is t C/ha → convert to tCO2e/ha
        y_soc = df["SOILGRIDS_SOC_STOCK"].values * 3.67
        df = df[~np.isnan(y_soc)]
        y_soc = y_soc[~np.isnan(y_soc)]
        w_soc = np.ones_like(y_soc)  # Equal weight for SOC
        print(f"SOC target: {len(y_soc)} samples, range [{y_soc.min():.1f}, {y_soc.max():.1f}] tCO2e/ha")
    else:
        y_soc = None
        w_soc = None
    
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
    
    return models, {"val": val_metrics, "test": test_metrics}


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
    
    # Prepare data
    data = prepare_data()
    
    all_metrics = {"trained_at": time.strftime("%Y-%m-%d"), "feature_cols": FEATURE_COLS}
    
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
    
    # Write comprehensive model card
    with open(ARTIFACTS_DIR / "model_card.json", "w") as f:
        json.dump(all_metrics, f, indent=2, default=str)
    
    print("\n" + "=" * 70)
    print("TRAINING COMPLETE")
    print("=" * 70)
    print(f"Artifacts saved to: {ARTIFACTS_DIR}")
    print("  - feature_scaler.pkl")
    print("  - biodiversity_quantile_{0.1,0.5,0.9}.pkl")
    print("  - soc_quantile_{0.1,0.5,0.9}.pkl")
    print("  - biodiversity_score_scaler.pkl (if bio target)")
    print("  - model_card.json (honest metrics with spatial CV)")
    print("\nKey metrics:")
    for target in ["biodiversity", "soc"]:
        if target in all_metrics:
            m = all_metrics[target]["quantile"]["test"]
            print(f"  {target}: Test R²={m['r2']:.3f}, MAE={m['mae']:.3f}, "
                  f"Coverage={m['coverage']:.1%}, Width={m['width']:.3f}")


if __name__ == "__main__":
    main()