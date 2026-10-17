import os
import joblib
import numpy as np
import pandas as pd

try:
    from config import ARTIFACTS, FEATURE_COLS
except ImportError:
    from src.config import ARTIFACTS, FEATURE_COLS

model_path = os.path.join(ARTIFACTS, "biodiversity_quantile_0.5.pkl")
scaler_path = os.path.join(ARTIFACTS, "feature_scaler.pkl")
score_scaler_path = os.path.join(ARTIFACTS, "biodiversity_score_scaler.pkl")

model = joblib.load(model_path) if os.path.exists(model_path) else None
scaler = joblib.load(scaler_path) if os.path.exists(scaler_path) else None
score_scaler = joblib.load(score_scaler_path) if os.path.exists(score_scaler_path) else None


def predict_biodiversity_score(features: dict) -> float:
    if model is None or scaler is None:
        # Fallback to NDVI heuristic if model not loaded
        ndvi = float(features.get("NDVI", 0.45) if features.get("NDVI") is not None else 0.45)
        return round(min(max(ndvi * 95 + 10, 20), 96), 1)
    
    # Fill any missing features with 0.0 to match the 33-feature contract
    row = [float(features.get(k) if features.get(k) is not None else 0.0) for k in FEATURE_COLS]
    scaled = scaler.transform(np.array([row]))
    raw = model.predict(scaled)
    if score_scaler is not None:
        score = score_scaler.transform(raw.reshape(-1, 1))[0][0]
    else:
        score = min(max(np.expm1(np.clip(raw[0], -1.0, 10.0)) * 10, 0), 100)
    score = min(max(score, 5.0), 98.0)
    return round(float(score), 1)


if __name__ == "__main__":
    test = {"NDVI": 0.45, "NDWI": -0.20, "SAVI": 0.41,
            "NDVI_STD": 0.09, "B4": 1200.0, "B8": 3100.0, "B11": 2200.0, "B8_VAR": 620000.0}
    print(f"Score: {predict_biodiversity_score(test)}/100")