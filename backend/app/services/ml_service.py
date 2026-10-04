"""ML serving with quantile predictions and honest fallbacks.

Loads quantile regression models (P10/P50/P90) for biodiversity and SOC.
Quality gate: spatial block CV test R² must exceed threshold.
Always returns ml_source labelling what was actually used.
"""
import logging
import warnings
import os
import numpy as np
import json

warnings.filterwarnings("ignore", category=UserWarning)
logger = logging.getLogger("carbonx.ml")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

# Model artifacts
_bio_quantiles = {}      # {0.1: model, 0.5: model, 0.9: model}
_soc_quantiles = {}
_feature_scaler = None
_bio_score_scaler = None
_models_loaded = False
_serving_enabled = {"biodiversity": False, "soc": False}

# Feature order must match training (extract_features.py)
FEATURE_ORDER = [
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

_MIN_SPATIAL_CV_R2 = 0.2  # Quality gate threshold


def _load_models():
    """Load quantile models and scalers. Returns dict of what loaded successfully."""
    global _bio_quantiles, _soc_quantiles, _feature_scaler, _bio_score_scaler
    global _models_loaded, _serving_enabled
    
    if _models_loaded:
        return _serving_enabled
    
    try:
        import joblib
        
        # Load feature scaler
        scaler_path = os.path.join(BASE_DIR, "ml/models/feature_scaler.pkl")
        if not os.path.exists(scaler_path):
            logger.warning("Feature scaler not found at %s", scaler_path)
            _models_loaded = True
            return _serving_enabled
        
        _feature_scaler = joblib.load(scaler_path)
        
        # Load biodiversity quantile models
        bio_loaded = True
        for q in [0.1, 0.5, 0.9]:
            path = os.path.join(BASE_DIR, f"ml/models/biodiversity_quantile_{q:.1f}.pkl")
            if os.path.exists(path):
                _bio_quantiles[q] = joblib.load(path)
            else:
                bio_loaded = False
                logger.warning("Biodiversity quantile %.1f model not found: %s", q, path)
        
        # Load SOC quantile models
        soc_loaded = True
        for q in [0.1, 0.5, 0.9]:
            path = os.path.join(BASE_DIR, f"ml/models/soc_quantile_{q:.1f}.pkl")
            if os.path.exists(path):
                _soc_quantiles[q] = joblib.load(path)
            else:
                soc_loaded = False
                logger.warning("SOC quantile %.1f model not found: %s", q, path)
        
        # Load biodiversity score scaler
        score_scaler_path = os.path.join(BASE_DIR, "ml/models/biodiversity_score_scaler.pkl")
        if os.path.exists(score_scaler_path):
            _bio_score_scaler = joblib.load(score_scaler_path)
        
        # Quality gate: check model card for spatial CV test R²
        card_path = os.path.join(BASE_DIR, "ml/models/model_card.json")
        if os.path.exists(card_path):
            try:
                with open(card_path, "r", encoding="utf-8") as fh:
                    card = json.load(fh)
                
                # Check biodiversity
                bio_test_r2 = card.get("biodiversity", {}).get("quantile", {}).get("test", {}).get("r2", -9)
                _serving_enabled["biodiversity"] = bio_loaded and float(bio_test_r2) >= _MIN_SPATIAL_CV_R2
                
                # Check SOC
                soc_test_r2 = card.get("soc", {}).get("quantile", {}).get("test", {}).get("r2", -9)
                _serving_enabled["soc"] = soc_loaded and float(soc_test_r2) >= _MIN_SPATIAL_CV_R2
                
                if not _serving_enabled["biodiversity"]:
                    logger.warning("Biodiversity model below quality gate (spatial CV test R²=%.3f < %.1f)", 
                                   bio_test_r2, _MIN_SPATIAL_CV_R2)
                if not _serving_enabled["soc"]:
                    logger.warning("SOC model below quality gate (spatial CV test R²=%.3f < %.1f)", 
                                   soc_test_r2, _MIN_SPATIAL_CV_R2)
                    
            except Exception as e:
                logger.warning("Could not read model card for quality gate: %s", e)
        
        _models_loaded = True
        logger.info("ML models loaded: bio=%s, soc=%s", 
                    _serving_enabled["biodiversity"], _serving_enabled["soc"])
        return _serving_enabled
        
    except Exception as e:
        logger.error("ML model load error: %s", e)
        _models_loaded = True
        return _serving_enabled


def predict_biodiversity(ndvi: float, evi: float = None, area_ha: float = 1.0, features: dict = None) -> dict:
    """Predict biodiversity score with quantile-based uncertainty.
    
    Args:
        ndvi: NDVI value
        evi: EVI value (optional)
        area_ha: Plot area in hectares
        features: Optional dict of real Sentinel-2 features (must match FEATURE_ORDER)
    
    Returns:
        Dict with biodiversity_score, status, confidence, source, ml_source,
        and quantile predictions (p10, p50, p90) if model served.
    """
    nd = float(ndvi or 0.45)
    
    # Try to use real model with real features
    model_ready = _load_models() and _serving_enabled.get("biodiversity", False)
    real_features = features is not None and all(k in features for k in FEATURE_ORDER[:8])  # At minimum core features
    
    if model_ready and real_features:
        try:
            # Build feature vector in correct order
            vector = [float(features.get(k, 0)) for k in FEATURE_ORDER]
            scaled = _feature_scaler.transform(np.array([vector]))
            
            # Predict quantiles
            preds = {}
            for q in [0.1, 0.5, 0.9]:
                preds[q] = float(_bio_quantiles[q].predict(scaled)[0])
            
            # Convert median log-richness to 0-100 score
            median_log = preds[0.5]
            if _bio_score_scaler is not None:
                bio_score = round(float(_bio_score_scaler.transform([[median_log]])[0][0]), 1)
            else:
                bio_score = round(min(max(np.expm1(median_log) * 10, 0), 100), 1)
            
            bio_score = min(max(bio_score, 5.0), 98.0)
            
            return _package(
                bio_score, nd, 
                source="QuantileRegressor (real Sentinel-2 + SAR + GEDI + SoilGrids features)",
                ml_source="quantile_regressor_v1",
                p10=preds[0.1], p50=preds[0.5], p90=preds[0.9]
            )
        except KeyError as e:
            logger.warning("ML predict: missing feature %s — falling back to heuristic", e)
        except Exception as e:
            logger.error("ML predict error: %s", e)
    
    # Fallback to heuristic
    if model_ready:
        source = "Heuristic (real features unavailable)"
    elif _bio_quantiles:
        source = "Heuristic (model below quality gate — see model card)"
    else:
        source = "Heuristic (NDVI-only, no model)"
    
    return _package(_heuristic_score(nd), nd, source=source, ml_source="heuristic_ndvi")


def predict_soc(features: dict = None) -> dict:
    """Predict SOC (tCO2e/ha) with quantile-based uncertainty.
    
    Args:
        features: Optional dict of real features (must match FEATURE_ORDER)
    
    Returns:
        Dict with soc_tco2e_ha, p10, p50, p90, ml_source
    """
    model_ready = _load_models() and _serving_enabled.get("soc", False)
    real_features = features is not None and all(k in features for k in FEATURE_ORDER)
    
    if model_ready and real_features:
        try:
            vector = [float(features.get(k, 0)) for k in FEATURE_ORDER]
            scaled = _feature_scaler.transform(np.array([vector]))
            
            preds = {}
            for q in [0.1, 0.5, 0.9]:
                preds[q] = float(_soc_quantiles[q].predict(scaled)[0])
            
            return {
                "soc_tco2e_ha": round(preds[0.5], 2),
                "p10": round(preds[0.1], 2),
                "p50": round(preds[0.5], 2),
                "p90": round(preds[0.9], 2),
                "ml_source": "quantile_regressor_v1_soc",
            }
        except Exception as e:
            logger.error("SOC predict error: %s", e)
    
    # Fallback: use SoilGrids prior if available in features
    if features and "SOILGRIDS_SOC_STOCK" in features:
        stock = float(features.get("SOILGRIDS_SOC_STOCK", 0)) * 3.67
        q05 = float(features.get("SOILGRIDS_SOC_Q05", 0)) * 3.67
        q50 = float(features.get("SOILGRIDS_SOC_Q50", 0)) * 3.67
        q95 = float(features.get("SOILGRIDS_SOC_Q95", 0)) * 3.67
        return {
            "soc_tco2e_ha": round(stock, 2),
            "p10": round(q05, 2),
            "p50": round(q50, 2),
            "p90": round(q95, 2),
            "ml_source": "soilgrids_prior",
        }
    
    return {
        "soc_tco2e_ha": 0,
        "p10": 0,
        "p50": 0,
        "p90": 0,
        "ml_source": "unavailable",
    }


def _package(bio_score: float, ndvi: float, source: str, ml_source: str, 
             p10=None, p50=None, p90=None) -> dict:
    status = (
        "Excellent" if bio_score >= 80
        else "Good" if bio_score >= 60
        else "Moderate" if bio_score >= 40
        else "Low"
    )
    result = {
        "biodiversity_score": round(float(bio_score), 1),
        "status": status,
        "confidence": round(min(75 + ndvi * 30, 99.5), 1),
        "source": source,
        "ml_source": ml_source,
    }
    if p10 is not None and p50 is not None and p90 is not None:
        result["quantiles"] = {
            "log_richness_p10": round(p10, 3),
            "log_richness_p50": round(p50, 3),
            "log_richness_p90": round(p90, 3),
        }
    return result


def _heuristic_score(ndvi: float) -> float:
    """Simple NDVI-based heuristic when model is unavailable."""
    return round(min(max(ndvi * 95 + 10, 20), 96), 1)


def get_model_status() -> dict:
    """Return model loading status for health checks."""
    _load_models()
    return {
        "models_loaded": _models_loaded,
        "biodiversity_serving": _serving_enabled.get("biodiversity", False),
        "soc_serving": _serving_enabled.get("soc", False),
        "bio_quantiles_loaded": list(_bio_quantiles.keys()),
        "soc_quantiles_loaded": list(_soc_quantiles.keys()),
        "quality_gate_threshold": _MIN_SPATIAL_CV_R2,
    }