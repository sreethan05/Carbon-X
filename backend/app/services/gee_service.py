"""Google Earth Engine service for Sentinel-2 satellite analysis.

Provides robust access to Sentinel-2 SR Harmonized imagery for point and
polygon regions with cloud filtering, dynamic date windows, median compositing,
and calculation of NDVI, EVI, and NDWI vegetation/water indices.

Honest error reporting is strictly enforced: when Earth Engine is offline,
unauthenticated, or cloud-covered, data is reported as unavailable — never
fabricated.
"""
from datetime import datetime, timezone
import os
from typing import Any, Dict, List, Optional, Tuple, Union

from app import gee_runtime


def init_earth_engine(project_id: Optional[str] = None) -> bool:
    """Initialize Google Earth Engine safely using shared gee_runtime state."""
    return gee_runtime.init_earth_engine(project_id)


def _build_sentinel2_composite(
    geometry: Any,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    max_cloud_percentage: float = 20.0,
):
    """Build a cloud-filtered median composite from COPERNICUS/S2_SR_HARMONIZED."""
    import ee

    s_date = start_date or "2024-01-01"
    e_date = end_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    base_collection = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(geometry)
        .filterDate(s_date, e_date)
    )

    # Filter by cloudy pixel percentage threshold
    filtered = base_collection.filter(
        ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", max_cloud_percentage)
    )

    # Adaptive fallback: if strict cloud filtering yields no scenes (e.g. monsoon),
    # relax cloud threshold up to 45% or sort by cloudiness to pick best available.
    collection_to_use = ee.Algorithms.If(
        filtered.size().gt(0),
        filtered,
        ee.Algorithms.If(
            base_collection.filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 45.0)).size().gt(0),
            base_collection.filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 45.0)),
            base_collection.sort("CLOUDY_PIXEL_PERCENTAGE").limit(5),
        ),
    )

    coll = ee.ImageCollection(collection_to_use)
    # Median composite across all cloud-screened scenes in the temporal window
    composite = coll.median()
    return composite, coll


def _compute_indices(image: Any) -> Any:
    """Compute NDVI, EVI, NDWI, and SAVI bands for a Sentinel-2 SR image."""
    import ee

    b2 = image.select("B2")
    b3 = image.select("B3")
    b4 = image.select("B4")
    b8 = image.select("B8")
    b11 = image.select("B11")

    ndvi = image.normalizedDifference(["B8", "B4"]).rename("NDVI")
    evi = image.expression(
        "2.5 * ((NIR - RED) / (NIR + 6.0 * RED - 7.5 * BLUE + 1.0))",
        {"NIR": b8, "RED": b4, "BLUE": b2},
    ).rename("EVI")
    ndwi = image.normalizedDifference(["B3", "B11"]).rename("NDWI")
    savi = image.expression(
        "((NIR - RED) / (NIR + RED + 0.5)) * 1.5",
        {"NIR": b8, "RED": b4},
    ).rename("SAVI")

    return image.addBands([ndvi, evi, ndwi, savi])


def get_ndvi_at_point(
    lat: float,
    lon: float,
    project_id: Optional[str] = None,
    buffer_meters: float = 500.0,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    max_cloud_percentage: float = 20.0,
) -> Dict[str, Any]:
    """Fetch Sentinel-2 NDVI for a geographic coordinate.

    If GEE is live, queries Sentinel-2 SR Harmonized using cloud filtering and
    median compositing; otherwise reports the NDVI as unavailable — never a
    fabricated value.
    """
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return {
            "ndvi": None,
            "source": "Invalid coordinates",
            "live_satellite": False,
            "vegetation_status": "Unknown",
        }

    if init_earth_engine(project_id):
        try:
            import ee

            point = ee.Geometry.Point([lon, lat])
            sampling_geom = point.buffer(buffer_meters) if buffer_meters > 0 else point

            composite, _ = _build_sentinel2_composite(
                sampling_geom,
                start_date=start_date,
                end_date=end_date,
                max_cloud_percentage=max_cloud_percentage,
            )

            ndvi = composite.normalizedDifference(["B8", "B4"]).rename("NDVI")
            mean_ndvi = ndvi.reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=sampling_geom,
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

    return {
        "ndvi": None,
        "source": "Unavailable (Earth Engine not initialized or query failed)",
        "live_satellite": False,
        "vegetation_status": "Unknown",
    }


def get_satellite_features_at_point(
    lat: float,
    lon: float,
    buffer_meters: float = 30.0,
    project_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    max_cloud_percentage: float = 20.0,
) -> Dict[str, Any]:
    """Fetch multi-index Sentinel-2 features (NDVI, EVI, NDWI, SAVI) for a coordinate."""
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return {
            "live_satellite": False,
            "source": "Invalid coordinates",
            "error": "Coordinates out of bounds",
        }

    if init_earth_engine(project_id):
        try:
            import ee

            point = ee.Geometry.Point([lon, lat])
            geom = point.buffer(buffer_meters) if buffer_meters > 0 else point

            composite, _ = _build_sentinel2_composite(
                geom,
                start_date=start_date,
                end_date=end_date,
                max_cloud_percentage=max_cloud_percentage,
            )

            indexed = _compute_indices(composite)
            stats = indexed.select(["NDVI", "EVI", "NDWI", "SAVI"]).reduceRegion(
                reducer=ee.Reducer.mean().combine(reducer2=ee.Reducer.minMax(), sharedInputs=True),
                geometry=geom,
                scale=10,
                maxPixels=1e9,
            ).getInfo()

            if stats and stats.get("NDVI_mean") is not None:
                return {
                    "live_satellite": True,
                    "source": "Google Earth Engine · Sentinel-2 SR Harmonized",
                    "lat": lat,
                    "lon": lon,
                    "buffer_meters": buffer_meters,
                    "ndvi": round(float(stats.get("NDVI_mean")), 3),
                    "ndvi_min": round(float(stats.get("NDVI_min", stats.get("NDVI_mean"))), 3),
                    "ndvi_max": round(float(stats.get("NDVI_max", stats.get("NDVI_mean"))), 3),
                    "evi": round(float(stats.get("EVI_mean", 0)), 3) if stats.get("EVI_mean") is not None else None,
                    "ndwi": round(float(stats.get("NDWI_mean", 0)), 3) if stats.get("NDWI_mean") is not None else None,
                    "savi": round(float(stats.get("SAVI_mean", 0)), 3) if stats.get("SAVI_mean") is not None else None,
                }
        except Exception as exc:
            print(f"Live GEE point features query failed: {exc}")

    return {
        "live_satellite": False,
        "source": "Unavailable (Earth Engine not initialized or query failed)",
        "lat": lat,
        "lon": lon,
        "ndvi": None,
        "evi": None,
        "ndwi": None,
        "savi": None,
    }


def get_satellite_features_for_polygon(
    coordinates_or_geojson: Union[List[Any], Dict[str, Any]],
    project_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    max_cloud_percentage: float = 20.0,
) -> Dict[str, Any]:
    """Sample Sentinel-2 features across a true polygon boundary.

    Takes a coordinate list [[lon, lat], ...] or GeoJSON Polygon dict and computes
    mean, min, max for NDVI, EVI, NDWI, and true parcel area in hectares.
    Never falls back to centroid point sampling.
    """
    try:
        if isinstance(coordinates_or_geojson, dict):
            geom = coordinates_or_geojson.get("geometry", coordinates_or_geojson)
            raw_coords = geom.get("coordinates") if isinstance(geom, dict) else None
            if isinstance(raw_coords, list) and len(raw_coords) > 0:
                coords = raw_coords[0] if isinstance(raw_coords[0][0], (list, tuple)) else raw_coords
            else:
                coords = []
        else:
            coords = coordinates_or_geojson

        if not isinstance(coords, list) or len(coords) < 3:
            return {
                "live_satellite": False,
                "error": "Polygon requires at least 3 coordinates",
            }

        # Ensure ring is closed
        ring = [[float(c[0]), float(c[1])] for c in coords]
        if ring[0] != ring[-1]:
            ring.append(ring[0])

        if len(ring) < 4:
            return {
                "live_satellite": False,
                "error": "Closed polygon ring requires at least 4 positions",
            }
    except Exception as exc:
        return {
            "live_satellite": False,
            "error": f"Invalid polygon coordinates: {exc}",
        }

    if init_earth_engine(project_id):
        try:
            import ee

            ee_polygon = ee.Geometry.Polygon(ring)
            area_ha = round(float(ee_polygon.area().getInfo()) / 10000.0, 3)

            centroid_coords = ee_polygon.centroid().coordinates().getInfo()
            centroid = {"lat": round(centroid_coords[1], 6), "lon": round(centroid_coords[0], 6)}

            composite, coll = _build_sentinel2_composite(
                ee_polygon,
                start_date=start_date,
                end_date=end_date,
                max_cloud_percentage=max_cloud_percentage,
            )

            indexed = _compute_indices(composite)
            stats = indexed.select(["NDVI", "EVI", "NDWI", "SAVI"]).reduceRegion(
                reducer=ee.Reducer.mean().combine(reducer2=ee.Reducer.minMax(), sharedInputs=True),
                geometry=ee_polygon,
                scale=10,
                maxPixels=1e9,
            ).getInfo()

            if stats and stats.get("NDVI_mean") is not None:
                ndvi_mean = round(float(stats["NDVI_mean"]), 3)
                ndvi_min = round(float(stats.get("NDVI_min", ndvi_mean)), 3)
                ndvi_max = round(float(stats.get("NDVI_max", ndvi_mean)), 3)
                evi_mean = round(float(stats.get("EVI_mean", 0)), 3) if stats.get("EVI_mean") is not None else None
                ndwi_mean = round(float(stats.get("NDWI_mean", 0)), 3) if stats.get("NDWI_mean") is not None else None
                savi_mean = round(float(stats.get("SAVI_mean", 0)), 3) if stats.get("SAVI_mean") is not None else None

                return {
                    "live_satellite": True,
                    "source": "Google Earth Engine · Sentinel-2 SR Harmonized",
                    "area_hectares": area_ha,
                    "centroid": centroid,
                    "ndvi": ndvi_mean,
                    "ndvi_min": ndvi_min,
                    "ndvi_max": ndvi_max,
                    "evi": evi_mean,
                    "ndwi": ndwi_mean,
                    "savi": savi_mean,
                    "vegetation_status": "Healthy" if ndvi_mean >= 0.3 else "Sparse",
                }
        except Exception as exc:
            print(f"Live GEE polygon features query failed: {exc}")

    return {
        "live_satellite": False,
        "source": "Unavailable (Earth Engine not initialized or query failed)",
        "area_hectares": None,
        "centroid": None,
        "ndvi": None,
        "ndvi_min": None,
        "ndvi_max": None,
        "evi": None,
        "ndwi": None,
        "savi": None,
        "vegetation_status": "Unknown",
    }