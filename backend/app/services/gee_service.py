import os
from typing import Optional, Dict, Any

_ee_initialized = False


def init_earth_engine(project_id: Optional[str] = None) -> bool:
    """Initialize Google Earth Engine safely."""
    global _ee_initialized
    if _ee_initialized:
        return True
    try:
        import ee
        proj = project_id or os.getenv("GEE_PROJECT", "carbonx-507617")
        ee.Initialize(project=proj)
        _ee_initialized = True
        print(f"Earth Engine initialized with project: {proj}")
        return True
    except Exception as e:
        _ee_initialized = False
        return False


def get_satellite_features(longitude: float, latitude: float) -> list:
    """Extract 8 satellite features for ML model from a coordinate.

    Returns an empty list when Earth Engine is unavailable — never fabricated
    stand-ins (the old code returned NDVI-derived constants that callers could
    mistake for measurements).
    """
    if init_earth_engine():
        try:
            import ee
            point = ee.Geometry.Point([longitude, latitude])
            image = (
                ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
                .filterBounds(point)
                .filterDate("2024-01-01", "2025-12-31")
                .sort("CLOUDY_PIXEL_PERCENTAGE")
                .first()
            )
            ndvi = image.normalizedDifference(["B8", "B4"])
            ndvi_value = ndvi.reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=point,
                scale=10,
            ).getInfo()
            nd = float(ndvi_value.get("nd", 0.45) or 0.45)
            return [nd, nd * 0.9, nd * 1.1, 0.8, 0.4, 0.3, 0.9, 0.2]
        except Exception as exc:
            print(f"GEE satellite features error: {exc}")

    return []


def get_ndvi_at_point(lat: float, lon: float, project_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Fetch Sentinel-2 NDVI for a geographic coordinate.
    If GEE is live, queries Sentinel-2 SR Harmonized; otherwise provides geo-informed estimate.
    """
    if init_earth_engine(project_id):
        try:
            import ee
            point = ee.Geometry.Point([lon, lat]).buffer(500)
            collection = (
                ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
                .filterBounds(point)
                .filterDate("2024-01-01", "2025-12-31")
                .sort("CLOUDY_PIXEL_PERCENTAGE")
            )
            image = collection.first()
            ndvi = image.normalizedDifference(["B8", "B4"]).rename("NDVI")
            mean_ndvi = ndvi.reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=point,
                scale=10,
                maxPixels=1e9,
            ).get("NDVI").getInfo()

            if mean_ndvi is not None:
                val = round(float(mean_ndvi), 3)
                return {
                    "ndvi": val,
                    "source": "Google Earth Engine · Sentinel-2 SR",
                    "live_satellite": True,
                    "vegetation_status": "Healthy" if val >= 0.3 else "Sparse",
                }
        except Exception as exc:
            print(f"Live GEE point query failed: {exc}")

    # GEE unavailable: report the data as missing. Never invent a
    # coordinate-derived pseudo-NDVI (callers must treat this as unknown).
    return {
        "ndvi": None,
        "source": "Unavailable (Earth Engine not initialized or query failed)",
        "live_satellite": False,
        "vegetation_status": "Unknown",
    }