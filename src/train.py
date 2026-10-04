"""Honest biodiversity model training — REAL species richness target.

Key differences from the v1 (circular) training (archived as
train_v1_circular_backup.py.bak):
- Target is `species_count` (actual GBIF species richness per 0.02-degree
  cell, log1p-transformed) — NOT a synthetic composite of the input features.
- NDVI filter widened to the app operating range (0.02-0.95); v1 trained on
  0.15-0.65 while the app serves up to 0.95 (distribution skew).
- Metrics on a held-out test set are the honest generalisation numbers;
  a model_card.json is written next to the artifacts.
"""
import json
import os
import time

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

from config import ARTIFACTS, DATA, FEATURE_COLS

NDVI_MIN, NDVI_MAX = 0.02, 0.95  # app operating range, not a convenience filter


def prepare_data():
    df = pd.read_csv(f"{DATA}/satellite_features_v2.csv")
    df = df.dropna(subset=FEATURE_COLS + ["species_count", "observation_count"])
    df = df[(df["NDVI"] >= NDVI_MIN) & (df["NDVI"] <= NDVI_MAX)]
    df = df[df["species_count"] > 1]
    print(f"Rows after filter: {len(df)}")

    # log1p tames the long richness tail so RMSE is not dominated by hotspots.
    y = np.log1p(df["species_count"].values)
    obs = df["observation_count"].values
    w = 1 + 9 * (obs - obs.min()) / (obs.max() - obs.min() + 1e-8)

    X_tr, X_tmp, y_tr, y_tmp, w_tr, w_tmp = train_test_split(
        df[FEATURE_COLS].values, y, w, test_size=0.2, random_state=42)
    X_val, X_te, y_val, y_te, w_val, w_te = train_test_split(
        X_tmp, y_tmp, w_tmp, test_size=0.5, random_state=42)

    os.makedirs(ARTIFACTS, exist_ok=True)
    scaler = StandardScaler().fit(X_tr)
    joblib.dump(scaler, f"{ARTIFACTS}/feature_scaler.pkl")
    return (scaler.transform(X_tr), scaler.transform(X_val), scaler.transform(X_te),
            y_tr, y_val, y_te, w_tr)


def train():
    X_tr, X_val, X_te, y_tr, y_val, y_te, w_tr = prepare_data()

    experiments = [
        ("rf_baseline", "rf", dict(n_estimators=200, min_samples_leaf=2)),
        ("rf_shallow", "rf", dict(n_estimators=300, max_depth=8, min_samples_leaf=3)),
        ("gb_baseline", "gb", dict(n_estimators=200, max_depth=3, learning_rate=0.05)),
        ("gb_slow", "gb", dict(n_estimators=400, max_depth=3, learning_rate=0.03, subsample=0.9)),
    ]
    best = (-9e9, None, None, None)
    for name, mtype, params in experiments:
        model = (RandomForestRegressor(**params, random_state=42, n_jobs=-1)
                 if mtype == "rf" else GradientBoostingRegressor(**params, random_state=42))
        model.fit(X_tr, y_tr, sample_weight=w_tr)
        vp = model.predict(X_val)
        vr2 = r2_score(y_val, vp)
        print(f"{name}: Val R2={vr2:.3f} MAE(log)={mean_absolute_error(y_val, vp):.3f}")
        if vr2 > best[0]:
            best = (vr2, model, name, params)

    val_r2, model, name, params = best
    tp = model.predict(X_te)
    test_r2 = r2_score(y_te, tp)
    test_mae_log = mean_absolute_error(y_te, tp)
    mae_species = float(np.mean(np.abs(np.expm1(tp) - np.expm1(y_te))))
    print(f"BEST={name} | Val R2={val_r2:.3f} | Test R2={test_r2:.3f} | "
          f"Test MAE(log)={test_mae_log:.3f} | Test MAE={mae_species:.1f} species")

    # Score scaler: map predicted log-richness to 0-100 on TRAINING spread.
    from sklearn.preprocessing import MinMaxScaler
    ss = MinMaxScaler(feature_range=(0, 100)).fit(model.predict(X_tr).reshape(-1, 1))
    joblib.dump(ss, f"{ARTIFACTS}/score_scaler.pkl")
    joblib.dump(model, f"{ARTIFACTS}/biodiversity_model.pkl")

    card = {
        "model": name,
        "params": params,
        "target": "log1p(GBIF species richness per 0.02-degree cell)",
        "features": FEATURE_COLS,
        "trained_at": time.strftime("%Y-%m-%d"),
        "n_train": int(len(y_tr)), "n_val": int(len(y_val)), "n_test": int(len(y_te)),
        "val_r2": round(float(val_r2), 3),
        "test_r2": round(float(test_r2), 3),
        "test_mae_log": round(float(test_mae_log), 3),
        "test_mae_species": round(mae_species, 1),
        "feature_importance": {k: round(float(v), 3) for k, v in
                               zip(FEATURE_COLS, model.feature_importances_)},
        "honest_limitations": [
            "GBIF citizen-science richness is sampling-biased; observation-count "
            "weights partially compensate, field validation still required.",
            "Regional model (India, Sentinel-2 2023): recalibrate for other regions/years.",
            "R2 well below 1.0 is expected and honest — richness is only partially "
            "explained by 10m vegetation indices.",
        ],
    }
    with open(f"{ARTIFACTS}/model_card.json", "w", encoding="utf-8") as fh:
        json.dump(card, fh, indent=2)
    print("Model + scalers + model_card.json saved to artifacts/")


if __name__ == "__main__":
    train()
