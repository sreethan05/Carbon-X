import warnings
import os
import numpy as np

warnings.filterwarnings("ignore", category=UserWarning)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

_model = None
_feature_scaler = None
_score_scaler = None
_model_loaded = False

def _load_models():
    global _model, _feature_scaler, _score_scaler, _model_loaded
    if _model_loaded:
        return _model is not None

    try:
        import sys
        try:
            import sklearn._loss._loss
            sys.modules.setdefault('_loss', sklearn._loss._loss)
        except Exception:
            pass

        import joblib
        model_path = os.path.join(BASE_DIR, "ml/models/biodiversity_model.pkl")
        scaler_path = os.path.join(BASE_DIR, "ml/models/feature_scaler.pkl")
        score_scaler_path = os.path.join(BASE_DIR, "ml/models/score_scaler.pkl")

        if not os.path.exists(model_path) or not os.path.exists(scaler_path):
            print(f"ML models not found at {model_path}")
            _model_loaded = True
            return False

        _model = joblib.load(model_path)
        _feature_scaler = joblib.load(scaler_path)
        if os.path.exists(score_scaler_path):
            _score_scaler = joblib.load(score_scaler_path)
        _model_loaded = True
        print(f"ML model loaded: {type(_model).__name__}")
        return True
    except Exception as e:
        print(f"ML model load error: {e}")
        _model_loaded = True
        return False

def predict_biodiversity(ndvi: float, evi: float = None, area_ha: float = 1.0) -> dict:
    """
    Predict biodiversity score from vegetation indices.
    Returns dict with score (0-100), confidence, and status label.
    """
    if evi is None:
        evi = ndvi * 0.85

    # Feature vector matching training schema:
    # ['NDVI', 'NDWI', 'SAVI', 'NDVI_STD', 'B4', 'B8', 'B11', 'B8_VAR']
    nd = float(ndvi or 0.45)
    ndwi = round(nd * 0.4 - 0.45, 4)
    savi = round(nd * 1.4 + 0.05, 4)
    ndvi_std = round(0.06 + (nd * 0.05), 4)
    b4 = round(1500 + (1 - nd) * 800)
    b8 = round(2500 + nd * 1800)
    b11 = round(2800 + (1 - nd) * 700)
    b8_var = round(500000 + nd * 300000)

    features = np.array([[nd, ndwi, savi, ndvi_std, b4, b8, b11, b8_var]])

    if _load_models() and _model is not None and _feature_scaler is not None:
        try:
            scaled = _feature_scaler.transform(features)
            raw_score = float(_model.predict(scaled)[0])
            if _score_scaler is not None:
                bio_score = round(float(_score_scaler.transform([[raw_score]])[0][0]), 1)
            else:
                bio_score = round(min(max(raw_score * 100, 0), 100), 1)
            bio_score = min(max(bio_score, 10.0), 98.0)
            source = "ML GradientBoosting"
        except Exception as e:
            print(f"ML predict error: {e}")
            bio_score = _heuristic_score(nd)
            source = "Heuristic fallback"
    else:
        bio_score = _heuristic_score(nd)
        source = "Heuristic (model unavailable)"

    status = (
        "Excellent" if bio_score >= 80
        else "Good" if bio_score >= 60
        else "Moderate" if bio_score >= 40
        else "Low"
    )

    confidence = round(min(75 + ndvi * 30, 99.5), 1)

    return {
        "biodiversity_score": bio_score,
        "status": status,
        "confidence": confidence,
        "source": source
    }

def _heuristic_score(ndvi: float) -> float:
    """Simple NDVI-based heuristic when model is unavailable."""
    return round(min(max(ndvi * 95 + 10, 20), 96), 1)
