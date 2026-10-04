import logging
import warnings
import os
import numpy as np

warnings.filterwarnings("ignore", category=UserWarning)
logger = logging.getLogger("carbonx.ml")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

_model = None
_feature_scaler = None
_score_scaler = None
_model_loaded = False
_serving_enabled = False
_MIN_SERVING_TEST_R2 = 0.2

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
            logger.warning("ML models not found at %s", model_path)
            _model_loaded = True
            return False

        # Quality gate: a model may only serve if its held-out test R^2 clears
        # the threshold recorded in its model card. The v2 honesty retrain
        # (real GBIF richness) scored below it, so the app currently serves
        # the labelled heuristic until a passing model is trained. This gate
        # is the difference between honest ML and confident garbage.
        global _serving_enabled
        card_path = os.path.join(os.path.dirname(model_path), "model_card.json")
        try:
            import json
            with open(card_path, "r", encoding="utf-8") as fh:
                card = json.load(fh)
            _serving_enabled = float(card.get("test_r2", -9)) >= _MIN_SERVING_TEST_R2
        except Exception:
            _serving_enabled = False
        if not _serving_enabled:
            logger.warning("ML model below quality gate (test_r2 in %s < %s) — serving labelled heuristic", card_path, _MIN_SERVING_TEST_R2)

        _model = joblib.load(model_path)
        _feature_scaler = joblib.load(scaler_path)
        if os.path.exists(score_scaler_path):
            _score_scaler = joblib.load(score_scaler_path)
        _model_loaded = True
        logger.info("ML model loaded: %s", type(_model).__name__)
        return True
    except Exception as e:
        logger.error("ML model load error: %s", e)
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

    model_ready = _load_models() and _model is not None and _feature_scaler is not None and _serving_enabled
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
            logger.warning("ML predict: missing feature %s — falling back to heuristic", e)
        except Exception as e:
            logger.error("ML predict error: %s", e)

    if model_ready:
        source = "Heuristic (real features unavailable)"
    elif _model is not None:
        source = "Heuristic (model below quality gate — see model card)"
    else:
        source = "Heuristic (NDVI-only)"
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
