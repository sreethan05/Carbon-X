import numpy as np, mlflow, mlflow.sklearn, joblib
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.metrics import r2_score, mean_squared_error, mean_absolute_error
from prepare_data import prepare_data
from config import ARTIFACTS, FEATURE_COLS

def train():
    X_train,X_val,X_test,y_train,y_val,y_test,w_train = prepare_data()
    mlflow.set_experiment("biodiversity_weighted")

    experiments = [
        ("rf_baseline",    "rf", dict(n_estimators=100,max_depth=None,min_samples_split=2)),
        ("rf_shallow",     "rf", dict(n_estimators=200,max_depth=8,   min_samples_split=5)),
        ("rf_conservative","rf", dict(n_estimators=300,max_depth=6,   min_samples_split=10)),
        ("gb_baseline",    "gb", dict(n_estimators=100,max_depth=3,   learning_rate=0.1)),
        ("gb_slow",        "gb", dict(n_estimators=300,max_depth=3,   learning_rate=0.05)),
    ]

    best_r2, best_model, best_name = -999, None, None

    for name, mtype, params in experiments:
        with mlflow.start_run(run_name=name):
            mlflow.log_params(params)
            model = (RandomForestRegressor(**params, random_state=42, n_jobs=-1)
                     if mtype=="rf"
                     else GradientBoostingRegressor(**params, random_state=42))
            model.fit(X_train, y_train, sample_weight=w_train)

            vp   = model.predict(X_val)
            vr2  = r2_score(y_val, vp)
            vrmse= np.sqrt(mean_squared_error(y_val, vp))
            vmae = mean_absolute_error(y_val, vp)
            imps = {k:round(v,3) for k,v in zip(FEATURE_COLS, model.feature_importances_)}

            mlflow.log_metrics({"val_r2":vr2,"val_rmse":vrmse,"val_mae":vmae})
            for f,v in imps.items(): mlflow.log_metric(f"imp_{f}",v)
            mlflow.sklearn.log_model(model,"model")

            print(f"{name}: Val R²={vr2:.3f} | RMSE={vrmse:.3f} | MAE={vmae:.3f}")
            print(f"  Importances: {imps}")

            if vr2 > best_r2:
                best_r2, best_model, best_name = vr2, model, name

    tp   = best_model.predict(X_test)
    tr2  = r2_score(y_test, tp)
    print(f"\nBest: {best_name} → Val R²={best_r2:.3f}")
    print(f"Test R²={tr2:.3f} | RMSE={np.sqrt(mean_squared_error(y_test,tp)):.3f}")

    joblib.dump(best_model, f"{ARTIFACTS}/biodiversity_model.pkl")
    print("Model saved.")

if __name__ == "__main__":
    train()