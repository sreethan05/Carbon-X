import joblib, pandas as pd, json
from config import ARTIFACTS, FEATURE_COLS

model        = joblib.load(f"{ARTIFACTS}/biodiversity_model.pkl")
scaler       = joblib.load(f"{ARTIFACTS}/feature_scaler.pkl")
score_scaler = joblib.load(f"{ARTIFACTS}/score_scaler.pkl")

def predict_biodiversity_score(features: dict) -> float:
    df     = pd.DataFrame([features])[FEATURE_COLS]
    scaled = scaler.transform(df)
    raw    = model.predict(scaled)
    score  = score_scaler.transform(raw.reshape(-1,1))[0][0]
    return round(float(score), 1)

if __name__ == "__main__":
    test = {"NDVI":0.45,"NDWI":-0.20,"SAVI":0.41,
            "NDVI_STD":0.09,"B4":0.03,"B8":0.25,"B11":0.18,"B8_VAR":0.001}
    print(f"Score: {predict_biodiversity_score(test)}/100")