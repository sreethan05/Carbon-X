import pandas as pd, numpy as np, joblib
from sklearn.preprocessing import MinMaxScaler
from config import DATA, ARTIFACTS, FEATURE_COLS

def build():
    model  = joblib.load(f"{ARTIFACTS}/biodiversity_model.pkl")
    scaler = joblib.load(f"{ARTIFACTS}/feature_scaler.pkl")
    df = pd.read_csv(f"{DATA}/satellite_features_v2_clean.csv").dropna(subset=FEATURE_COLS)
    preds  = model.predict(scaler.transform(df[FEATURE_COLS]))
    ss     = MinMaxScaler(feature_range=(0,100))
    ss.fit(preds.reshape(-1,1))
    joblib.dump(ss, f"{ARTIFACTS}/score_scaler.pkl")
    print("Score scaler saved.")

if __name__ == "__main__":
    build()