#!/usr/bin/env python3
"""
GEE Microservice - standalone optional helper (legacy / standalone runner)
Run this to enable real GEE analysis: python gee_server.py

Project: read from GEE_PROJECT (defaults to carbonx-507617)
"""

from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import os
import sys
from urllib.parse import urlparse, parse_qs

# GEE state tracking
gee_initialized = False
gee_error = None
gee_project = os.getenv("GEE_PROJECT", "carbonx-507617")


def init_gee(project_id=None):
    """Safely initialize Google Earth Engine."""
    global gee_initialized, gee_error, gee_project
    proj = project_id or os.getenv("GEE_PROJECT", "carbonx-507617")
    try:
        import ee
        ee.Initialize(project=proj)
        gee_initialized = True
        gee_error = None
        gee_project = proj
        print(f"Earth Engine initialized with project: {proj}")
        return True
    except Exception as e:
        gee_initialized = False
        gee_error = str(e)
        print(f"Earth Engine initialization failed: {e}")
        return False


# Attempt startup initialization
init_gee(gee_project)


def _build_composite(geometry, max_cloud=20.0):
    """Build a cloud-filtered median composite from S2 SR Harmonized."""
    import ee

    collection = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(geometry)
        .filterDate("2024-01-01", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    )

    filtered = collection.filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", max_cloud))

    # Adaptive fallback if heavy cloud cover (e.g. monsoon)
    coll_to_use = ee.Algorithms.If(
        filtered.size().gt(0),
        filtered,
        ee.Algorithms.If(
            collection.filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 45.0)).size().gt(0),
            collection.filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 45.0)),
            collection.sort("CLOUDY_PIXEL_PERCENTAGE").limit(5),
        ),
    )

    return ee.ImageCollection(coll_to_use).median()


def get_satellite_features(longitude, latitude):
    """Real Sentinel-2 NDVI, EVI, and NDWI stats for a coordinate.

    Uses COPERNICUS/S2_SR_HARMONIZED with cloud filtering and median compositing.
    Never fabricates values: returns None if GEE is unavailable or query fails.
    """
    if not gee_initialized and not init_gee():
        return {
            "nd": None,
            "ndMin": None,
            "ndMax": None,
            "evi": None,
            "ndwi": None,
            "live_satellite": False,
            "source": f"Unavailable: {gee_error}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    try:
        import ee

        point = ee.Geometry.Point([longitude, latitude])
        sample_geom = point.buffer(20)  # 20m buffer covers ~1 Sentinel-2 10m pixel diameter

        image = _build_composite(sample_geom)

        ndvi = image.normalizedDifference(["B8", "B4"]).rename("nd")
        evi = image.expression(
            "2.5 * ((NIR - RED) / (NIR + 6.0 * RED - 7.5 * BLUE + 1.0))",
            {"NIR": image.select("B8"), "RED": image.select("B4"), "BLUE": image.select("B2")},
        ).rename("evi")
        ndwi = image.normalizedDifference(["B3", "B11"]).rename("ndwi")

        stacked = ndvi.addBands([evi, ndwi])

        stats = stacked.reduceRegion(
            reducer=ee.Reducer.mean().combine(reducer2=ee.Reducer.minMax(), sharedInputs=True),
            geometry=sample_geom,
            scale=10,
            maxPixels=1e9,
        ).getInfo()

        if stats and stats.get("nd_mean") is not None:
            return {
                "nd": round(float(stats.get("nd_mean")), 3),
                "ndMin": round(float(stats.get("nd_min", stats.get("nd_mean"))), 3),
                "ndMax": round(float(stats.get("nd_max", stats.get("nd_mean"))), 3),
                "evi": round(float(stats.get("evi_mean", 0)), 3) if stats.get("evi_mean") is not None else None,
                "ndwi": round(float(stats.get("ndwi_mean", 0)), 3) if stats.get("ndwi_mean") is not None else None,
                "live_satellite": True,
                "source": "COPERNICUS/S2_SR_HARMONIZED",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
    except Exception as exc:
        print(f"get_satellite_features error: {exc}")

    return {
        "nd": None,
        "ndMin": None,
        "ndMax": None,
        "evi": None,
        "ndwi": None,
        "live_satellite": False,
        "source": "Unavailable (query failed)",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def analyze_polygon(coordinates):
    """Analyze a polygon using true geometric reduction across Sentinel-2 pixels."""
    if not coordinates or len(coordinates) < 3:
        return {"error": "Need at least 3 coordinates"}

    if not gee_initialized and not init_gee():
        return {
            "error": f"Earth Engine unavailable: {gee_error}",
            "live_satellite": False,
        }

    try:
        import ee

        ring = [[float(c[0]), float(c[1])] for c in coordinates]
        if ring[0] != ring[-1]:
            ring.append(ring[0])

        if len(ring) < 4:
            return {"error": "Polygon ring requires at least 4 closed points"}

        ee_polygon = ee.Geometry.Polygon(ring)
        area_ha = round(float(ee_polygon.area().getInfo()) / 10000.0, 3)

        centroid_coords = ee_polygon.centroid().coordinates().getInfo()
        centroid_lat = round(float(centroid_coords[1]), 6)
        centroid_lng = round(float(centroid_coords[0]), 6)

        image = _build_composite(ee_polygon)

        ndvi = image.normalizedDifference(["B8", "B4"]).rename("nd")
        evi = image.expression(
            "2.5 * ((NIR - RED) / (NIR + 6.0 * RED - 7.5 * BLUE + 1.0))",
            {"NIR": image.select("B8"), "RED": image.select("B4"), "BLUE": image.select("B2")},
        ).rename("evi")
        ndwi = image.normalizedDifference(["B3", "B11"]).rename("ndwi")

        stacked = ndvi.addBands([evi, ndwi])

        stats = stacked.reduceRegion(
            reducer=ee.Reducer.mean().combine(reducer2=ee.Reducer.minMax(), sharedInputs=True),
            geometry=ee_polygon,
            scale=10,
            maxPixels=1e9,
        ).getInfo()

        if stats and stats.get("nd_mean") is not None:
            return {
                "nd": round(float(stats.get("nd_mean")), 3),
                "ndMin": round(float(stats.get("nd_min", stats.get("nd_mean"))), 3),
                "ndMax": round(float(stats.get("nd_max", stats.get("nd_mean"))), 3),
                "evi": round(float(stats.get("evi_mean", 0)), 3) if stats.get("evi_mean") is not None else None,
                "ndwi": round(float(stats.get("ndwi_mean", 0)), 3) if stats.get("ndwi_mean") is not None else None,
                "area_hectares": area_ha,
                "centroid": {"lat": centroid_lat, "lng": centroid_lng},
                "coordinates_count": len(coordinates),
                "live_satellite": True,
                "source": "COPERNICUS/S2_SR_HARMONIZED",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
    except Exception as exc:
        print(f"analyze_polygon error: {exc}")
        return {"error": str(exc), "live_satellite": False}

    return {
        "nd": None,
        "ndMin": None,
        "ndMax": None,
        "evi": None,
        "ndwi": None,
        "area_hectares": None,
        "live_satellite": False,
        "error": "Failed to extract polygon statistics",
    }


class GEEHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length <= 0:
                self.send_json({"error": "Empty request body"}, status_code=400)
                return

            body = self.rfile.read(content_length)
            data = json.loads(body.decode("utf-8"))

            if self.path == "/analyze/point":
                lat = data.get("latitude")
                lng = data.get("longitude")
                if lat is None or lng is None:
                    self.send_json({"error": "latitude and longitude required"}, status_code=400)
                    return
                result = get_satellite_features(float(lng), float(lat))
                self.send_json(result)

            elif self.path == "/analyze/polygon":
                coords = data.get("coordinates", [])
                if not coords:
                    self.send_json({"error": "coordinates required"}, status_code=400)
                    return
                result = analyze_polygon(coords)
                self.send_json(result)

            else:
                self.send_json({"error": "Endpoint not found"}, status_code=404)
        except Exception as exc:
            self.send_json({"error": f"Internal server error: {exc}"}, status_code=500)

    def do_GET(self):
        if self.path == "/health":
            if gee_initialized:
                self.send_json({"status": "ok", "gee": "connected", "project": gee_project}, status_code=200)
            else:
                self.send_json(
                    {"status": "degraded", "gee": "disconnected", "error": gee_error},
                    status_code=503,
                )
        else:
            self.send_json({"error": "Not found"}, status_code=404)

    def send_json(self, data, status_code=200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        print(f"[GEE] {format % args}")


if __name__ == "__main__":
    port = 5001
    server = HTTPServer(("localhost", port), GEEHandler)
    print(f"Earth Engine Microservice running on http://localhost:{port}")
    print(f"   POST /analyze/point - Analyze single point")
    print(f"   POST /analyze/polygon - Analyze polygon boundary")
    print(f"   GET /health - Health check")
    server.serve_forever()
