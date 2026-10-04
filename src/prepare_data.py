import pandas as pd, numpy as np, joblib, os
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from config import DATA, ARTIFACTS, FEATURE_COLS, NDVI_MIN, NDVI_MAX, NDVI_STD_MIN

def norm(s): return (s - s.min()) / (s.max() - s.min() + 1e-8)

def prepare_data():
    df = pd.read_csv(f"{DATA}/satellite_features_v2.csv")
    df = df.dropna(subset=FEATURE_COLS + ["observation_count"])
    df = df[(df["NDVI"] >= NDVI_MIN) & (df["NDVI"] <= NDVI_MAX)]
    df = df[df["NDVI_STD"] > NDVI_STD_MIN]
    print(f"Rows after filter: {len(df)}")

    df["bio_index"] = (
        norm(df["NDVI_STD"]) * 0.35 +
        norm(df["B8_VAR"])   * 0.25 +
        norm(df["NDVI"])     * 0.20 +
        norm(df["NDWI"])     * 0.20
    )

    obs = df["observation_count"].values
    weights = 1 + 9 * (obs - obs.min()) / (obs.max() - obs.min() + 1e-8)

    X, y, w = df[FEATURE_COLS], df["bio_index"], weights

    X_train,X_temp,y_train,y_temp,w_train,w_temp = train_test_split(
        X, y, w, test_size=0.2, random_state=42)
    X_val,X_test,y_val,y_test,w_val,w_test = train_test_split(
        X_temp, y_temp, w_temp, test_size=0.5, random_state=42)

    print(f"Train:{len(X_train)} Val:{len(X_val)} Test:{len(X_test)}")

    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_val_s   = scaler.transform(X_val)
    X_test_s  = scaler.transform(X_test)

    os.makedirs(ARTIFACTS, exist_ok=True)
    joblib.dump(scaler, f"{ARTIFACTS}/feature_scaler.pkl")
    return X_train_s, X_val_s, X_test_s, y_train, y_val, y_test, w_train

if __name__ == "__main__":
    prepare_data()