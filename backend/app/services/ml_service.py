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

FEATURE_ORDER = ["NDVI", "NDWI", "SAVI", "NDVI_STD", "B4", "B8", "B11", "B8_VAR"]


def predict_biodiversity(ndvi: float, evi: float = None, area_ha: float = 1.0, features: dict = None) -> dict:
    """Predict a biodiversity score for a plot.

    features: OPTIONAL dict of real Sentinel-2 features (NDVI, NDWI, SAVI,
    NDVI_STD, B4, B8, B11, B8_VAR) as computed by the Earth Engine pipeline —
    the same derivation used in training. When they are not available we DO
    NOT fabricate them: a model fed synthetic stand-ins for real satellite
    features produces garbage with a confident face. The NDVI-only heuristic
    is used instead, clearly labelled.
    """
    nd = float(ndvi or 0.45)

    model_ready = _load_models() and _model is not None and _feature_scaler is not None
    if model_ready and features:
        try:
            vector = [float(features[k]) for k in FEATURE_ORDER]
            scaled = _feature_scaler.transform(np.array([vector]))
            raw_score = float(_model.predict(scaled)[0])
            if _score_scaler is not None:
                bio_score = round(float(_score_scaler.transform([[raw_score]])[0][0]), 1)
            else:
                bio_score = round(min(max(raw_score * 100, 0), 100), 1)
            bio_score = min(max(bio_score, 5.0), 98.0)
            return _package(bio_score, nd, source=f"ML {type(_model).__name__} (real Sentinel-2 features)")
        except KeyError as e:
            print(f"ML predict: missing feature {e} — falling back to heuristic")
        except Exception as e:
            print(f"ML predict error: {e}")

    source = "Heuristic (NDVI-only)" if not model_ready else "Heuristic (real features unavailable)"
    return _package(_heuristic_score(nd), nd, source=source)


def _package(bio_score: float, ndvi: float, source: str) -> dict:
    status = (
        "Excellent" if bio_score >= 80
        else "Good" if bio_score >= 60
        else "Moderate" if bio_score >= 40
        else "Low"
    )
    return {
        "biodiversity_score": round(float(bio_score), 1),
        "status": status,
        "confidence": round(min(75 + ndvi * 30, 99.5), 1),
        "source": source,
    }

def _heuristic_score(ndvi: float) -> float:
    """Simple NDVI-based heuristic when model is unavailable."""
    return round(min(max(ndvi * 95 + 10, 20), 96), 1)
