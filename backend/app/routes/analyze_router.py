"""Root-level scan endpoints: /predict (biodiversity probe) and /analyze.

Both refuse to fabricate satellite values: without live Earth Engine data
they return an honest unknown/empty result rather than inventing an NDVI or
a credit number. The /analyze cache is shared via redis_store (Redis when
configured, per-worker memory otherwise).
"""
import hashlib
import json
import math
import os
import time
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, field_validator

from app import config as app_config
from app import gee_runtime
from app import redis_store
from app.security import get_current_user_optional
from app.services import credit_engine
from app.services.polygon_service import (
    polygon_area_hectares as _polygon_area_hectares,
    validate_polygon_geojson as _validate_polygon_geojson,
)

router = APIRouter()

_ANALYZE_CACHE_TTL = app_config.ANALYZE_CACHE_TTL_SECONDS
_ANALYZE_CACHE_NAMESPACE = "analyze:"
_RATE_WINDOW_SECONDS = 60
_RATE_MAX_REQUESTS = 12
_rate_buckets: dict[str, list[float]] = {}


def _enforce_scan_rate_limit(user: Optional[dict] = None) -> None:
    """Small in-process safety valve; Redis/cache absorbs normal repeats."""
    if not user:
        return
    key = str(user.get("phone") or user.get("sub") or "unknown")
    now = time.time()
    bucket = [stamp for stamp in _rate_buckets.get(key, []) if now - stamp < _RATE_WINDOW_SECONDS]
    if len(bucket) >= _RATE_MAX_REQUESTS:
        raise HTTPException(status_code=429, detail="Satellite scan rate limit reached; retry in one minute")
    bucket.append(now)
    _rate_buckets[key] = bucket


def _analyze_cache_key(geojson: dict, crop_type: Optional[str]) -> str:
    material = json.dumps([geojson, crop_type], sort_keys=True, default=str)
    return _ANALYZE_CACHE_NAMESPACE + hashlib.sha1(material.encode("utf-8")).hexdigest()


def _with_ee_backoff(fn, *, attempts=3, base_delay=1.5):
    """Earth Engine call with exponential backoff — quota blips and
    transient timeouts retry instead of failing the scan."""
    last_err = None
    for attempt in range(attempts):
        try:
            return fn()
        except Exception as e:
            last_err = e
            if attempt < attempts - 1:
                delay = base_delay * (2 ** attempt)
                print(f"[ee] call failed ({type(e).__name__}), retry in {delay}s")
                time.sleep(delay)
    raise last_err


@router.get("/predict")
def predict(longitude: float, latitude: float, current_user: Optional[dict] = Depends(get_current_user_optional)):
    if current_user:
        _enforce_scan_rate_limit(current_user)
    try:
        if not (math.isfinite(latitude) and math.isfinite(longitude)):
            return {"success": False, "message": "Latitude and longitude must be finite numbers"}
        from app.services.polygon_service import is_in_india
        if not is_in_india(latitude, longitude):
            return {
                "success": False,
                "message": f"Coordinates ({latitude:.2f}, {longitude:.2f}) are outside India — CarbonX only supports locations within India",
            }
        from app.services.ml_service import predict_biodiversity

        ndvi = None
        ndvi_source = "unavailable (no live satellite data)"
        if gee_runtime.earth_engine_ready:
            try:
                from app.services.gee_service import get_ndvi_at_point

                sat = get_ndvi_at_point(latitude, longitude)
                if sat.get("live_satellite"):
                    ndvi = float(sat.get("ndvi"))
                    ndvi_source = str(sat.get("source"))
            except Exception as exc:
                print(f"/predict GEE point query failed: {exc}")
        if ndvi is None:
            # No live satellite data: NEVER fabricate an NDVI. A made-up index
            # would flow into the biodiversity score and read as evidence.
            # Report honestly instead (ml_source stays present for clients).
            return {
                "success": True,
                "location": {"longitude": longitude, "latitude": latitude},
                "ndvi": None,
                "ndvi_source": ndvi_source,
                "biodiversity_score": None,
                "status": "Unknown",
                "biodiversity_credits": 0.0,
                "total_credits": 0.0,
                "ml_source": None,
                "satellite_live": False,
                "message": "Live satellite data is unavailable — no NDVI estimate or credit issued.",
            }
        result = predict_biodiversity(ndvi=ndvi)
        # /predict is a biodiversity probe only — it does not estimate carbon,
        # so no carbon credit line is invented here (single source of truth).
        credits = credit_engine.credit_split(0, result["biodiversity_score"])
        return {
            "success": True,
            "location": {"longitude": longitude, "latitude": latitude},
            "ndvi": ndvi,
            "ndvi_source": ndvi_source,
            "biodiversity_score": result["biodiversity_score"],
            "status": result["status"],
            "biodiversity_credits": credits["biodiversity_credits"],
            "total_credits": credits["total_credits"],
            "ml_source": result.get("ml_source"),
        }
    except Exception as e:
        return {"success": False, "message": str(e)}


# ── /analyze models ───
class GeoJSONPolygon(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["Feature"] = "Feature"
    geometry: dict

    @field_validator("geometry")
    @classmethod
    def _validate_polygon(cls, geom):
        ok, err = _validate_polygon_geojson({"type": "Feature", "geometry": geom})
        if not ok:
            raise ValueError(err)
        return geom


class AnalyzeModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    geojson: GeoJSONPolygon
    farm_name: Optional[str] = "My Farm"
    crop_type: Optional[str] = "Mixed Crop"
    irrigation: Optional[str] = "Drip"


# ── /analyze endpoint (core endpoint at root level) ───
@router.post("/analyze")
def analyze(data: AnalyzeModel, current_user: Optional[dict] = Depends(get_current_user_optional)):
    if current_user:
        _enforce_scan_rate_limit(current_user)
    try:
        geojson = data.geojson.model_dump()
        ok, err = _validate_polygon_geojson(geojson)
        if not ok:
            return {"success": False, "message": err}

        cache_key = _analyze_cache_key(geojson, data.crop_type)
        cached = redis_store.cache_get(cache_key)
        if cached is not None:
            try:
                return json.loads(cached)
            except ValueError:
                pass  # corrupt cache entry — recompute

        ml_result = None
        s2_scene = None
        scan_est = None
        max_area = app_config.ANALYZE_MAX_AREA_HECTARES
        try:
            approx_area = _polygon_area_hectares(geojson)
            if approx_area > max_area:
                return {"success": False,
                        "message": f"Parcel area {approx_area:,.0f} ha exceeds the {max_area:,} ha scan limit — redraw the boundary"}
        except Exception:
            pass
        if gee_runtime.earth_engine_ready:
            from concurrent.futures import ThreadPoolExecutor
            import ee
            coordinates = geojson["geometry"]["coordinates"]
            polygon = ee.Geometry.Polygon(coordinates)
            from datetime import datetime, timezone
            s2_start = os.getenv("CARBONX_GEE_START_DATE", "2024-01-01")
            s2_end = os.getenv("CARBONX_GEE_END_DATE") or datetime.now(timezone.utc).strftime("%Y-%m-%d")
            collection = (
                ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
                .filterBounds(polygon)
                .filterDate(s2_start, s2_end)
                .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 20))
            )
            image = collection.median()
            ndvi = image.normalizedDifference(["B8", "B4"]).rename("NDVI")
            evi = image.expression(
                "2.5 * ((NIR - RED) / (NIR + 6 * RED - 7.5 * BLUE + 1))",
                {"NIR": image.select("B8"), "RED": image.select("B4"), "BLUE": image.select("B2")},
            )

            B4, B8, B3, B11 = (image.select("B4"), image.select("B8"),
                               image.select("B3"), image.select("B11"))
            stack = (ndvi.rename("NDVI")
                     .addBands(image.normalizedDifference(["B3", "B11"]).rename("NDWI"))
                     .addBands(image.expression("((NIR-RED)/(NIR+RED+0.5))*1.5",
                                {"NIR": B8, "RED": B4}).rename("SAVI"))
                     .addBands(B4.rename("B4"))
                     .addBands(B8.rename("B8"))
                     .addBands(B11.rename("B11"))
                     .addBands(collection.map(lambda i: i.normalizedDifference(["B8", "B4"]))
                               .reduce(ee.Reducer.stdDev()).rename("NDVI_STD"))
                     .addBands(collection.map(lambda i: i.select("B8"))
                               .reduce(ee.Reducer.variance()).rename("B8_VAR")))

            with ThreadPoolExecutor(max_workers=5) as executor:
                f_ndvi = executor.submit(
                    _with_ee_backoff,
                    lambda: ndvi.reduceRegion(
                        reducer=ee.Reducer.mean(), geometry=polygon, scale=10, maxPixels=1e13,
                    ).get("NDVI").getInfo()
                )
                f_evi = executor.submit(
                    _with_ee_backoff,
                    lambda: evi.reduceRegion(
                        reducer=ee.Reducer.mean(), geometry=polygon, scale=10, maxPixels=1e13,
                    ).values().get(0).getInfo()
                )
                f_area = executor.submit(
                    _with_ee_backoff,
                    lambda: polygon.area().getInfo()
                )
                f_feat = executor.submit(
                    lambda: stack.reduceRegion(
                        reducer=ee.Reducer.mean(), geometry=polygon, scale=10, maxPixels=1e9,
                    ).getInfo()
                )
                f_scene = executor.submit(
                    lambda: collection.first().get("system:index").getInfo()
                )

                ndvi_value = f_ndvi.result()
                evi_value = f_evi.result()
                area_hectares = round(_polygon_area_hectares(geojson), 2)
                try:
                    raw_area = f_area.result()
                    if raw_area is not None:
                        area_hectares = round(float(raw_area) / 10000, 2)
                except Exception:
                    pass

            if ndvi_value is None or evi_value is None:
                return {
                    "success": True,
                    "ndvi": None,
                    "evi": None,
                    "tree_cover": 0.0,
                    "soil_moisture": 0.0,
                    "carbon_tonnes": 0.0,
                    "carbon_credits": 0.0,
                    "biodiversity_credits": 0.0,
                    "total_credits": 0.0,
                    "area_hectares": area_hectares,
                    "vegetation_health": "Unknown",
                    "biodiversity_score": None,
                    "ml_source": None,
                    "ai_confidence": None,
                    "confidence_basis": "Not reported — no calibrated model confidence.",
                    "credits_basis": "not_estimated",
                    "validation_status": "no_data",
                    "satellite_source": "unavailable (no cloud-free Sentinel-2 data)",
                    "satellite_live": False,
                    "credits_available": False,
                    "s2_scene": None,
                    "scan_estimate": None,
                    "stage1": None,
                    "message": ("Live satellite data was not available for this parcel (no cloud-free scenes). "
                                "Retry later or route this record to FPO review."),
                }

            try:
                feat_values = f_feat.result()
                real_features = {k: feat_values.get(k) for k in
                                 ("NDVI", "NDWI", "SAVI", "NDVI_STD", "B4", "B8", "B11", "B8_VAR")}
                if any(v is None for v in real_features.values()):
                    real_features = None
            except Exception as e:
                print(f"[analyze] real feature extraction failed: {e}")
                real_features = None

            try:
                from app.services.ml_service import predict_biodiversity
                ml_result = predict_biodiversity(ndvi=ndvi_value, evi=evi_value,
                                                 area_ha=area_hectares, features=real_features)
                biodiversity_score = ml_result["biodiversity_score"]
            except Exception as e:
                # One canonical fallback (ml_service heuristic), labelled in
                # ml_source — never an ad-hoc formula that disagrees with it.
                print(f"[analyze] biodiversity prediction failed: {e}")
                from app.services.ml_service import _heuristic_score
                biodiversity_score = _heuristic_score(ndvi_value)
                ml_result = {
                    "biodiversity_score": biodiversity_score,
                    "source": "Heuristic (prediction error)",
                    "ml_source": "heuristic_ndvi",
                }
            satellite_source = "Google Earth Engine · Sentinel-2 SR"
            try:
                s2_scene = f_scene.result()
            except Exception:
                s2_scene = None

            scan_est = credit_engine.quick_scan_estimate(area_hectares, data.crop_type, ndvi_value, features=real_features)
            carbon_tonnes = scan_est["credits_tco2e"]
        else:
            # No live satellite data: NEVER fabricate an NDVI, and never turn a
            # made-up index into a credit. Without imagery there is no evidence,
            # so the scan returns an honest empty result and the record is routed
            # to FPO review instead of inventing a number.
            area_hectares = _polygon_area_hectares(geojson)
            return {
                "success": True,
                "ndvi": None,
                "evi": None,
                "tree_cover": 0.0,
                "soil_moisture": 0.0,
                "carbon_tonnes": 0.0,
                "carbon_credits": 0.0,
                "biodiversity_credits": 0.0,
                "total_credits": 0.0,
                "area_hectares": area_hectares,
                "vegetation_health": "Unknown",
                "biodiversity_score": None,
                "ml_source": None,
                "ai_confidence": None,
                "confidence_basis": "Not reported — no calibrated model confidence.",
                "credits_basis": "not_estimated",
                "validation_status": "no_data",
                "satellite_source": "unavailable (no live Sentinel-2 data)",
                "satellite_live": False,
                "credits_available": False,
                "s2_scene": None,
                "scan_estimate": None,
                "stage1": None,
                "message": ("Live satellite data is unavailable, so no credit can be issued. "
                            "Retry when Earth Engine is reachable, or route this record to FPO review."),
            }

        tree_cover = round(min(max(ndvi_value * 100, 0), 100), 2)
        soil_moisture = round(min(max(evi_value * 25, 0), 100), 2)
        credits = credit_engine.credit_split(carbon_tonnes, biodiversity_score)
        stage1 = credit_engine.stage1_verification(data.crop_type, ndvi_value)
        veg_health = (
            "Excellent" if ndvi_value >= 0.7 else "Good" if ndvi_value >= 0.5
            else "Moderate" if ndvi_value >= 0.3 else "Low"
        )
        ml_source = ml_result.get("source") if isinstance(ml_result, dict) else None
        response = {
            "success": True,
            "ndvi": round(ndvi_value, 3),
            "evi": round(evi_value, 3),
            "tree_cover": tree_cover,
            "soil_moisture": soil_moisture,
            "carbon_tonnes": carbon_tonnes,
            "carbon_credits": credits["carbon_credits"],
            "biodiversity_credits": credits["biodiversity_credits"],
            "total_credits": credits["total_credits"],
            "area_hectares": area_hectares,
            "vegetation_health": veg_health,
            "biodiversity_score": biodiversity_score,
            "ml_source": ml_source,
            # The old ``85 + NDVI*20`` figure was an invented confidence
            # number. There is no calibrated probability behind it, so we
            # report nothing and expose evidence quality instead.
            "ai_confidence": None,
            "confidence_basis": "Not reported — no calibrated model confidence.",
            "evidence_quality": scan_est.get("evidence_quality"),
            "credits_basis": scan_est.get("basis", "proxy_estimate"),
            "validation_status": (scan_est.get("validation") or {}).get("status", "proxy_unvalidated"),
            "validation_label": (scan_est.get("validation") or {}).get("label"),
            "satellite_source": satellite_source,
            "s2_scene": s2_scene,
            "scan_estimate": {
                "method": "credit_engine.quick_scan_estimate (single source of truth)",
                "evidence_quality": scan_est.get("evidence_quality"),
                "ci90": scan_est.get("ci90"),
                "basis": scan_est.get("basis"),
                "validation": scan_est.get("validation"),
                "formula_version": scan_est.get("formula_version"),
            },
            "stage1": stage1,
        }
        try:
            redis_store.cache_set(cache_key, json.dumps(response, default=str), _ANALYZE_CACHE_TTL)
        except (TypeError, ValueError):
            pass  # caching is best-effort; the response is already computed
        return response
    except Exception as e:
        return {"success": False, "message": str(e)}
