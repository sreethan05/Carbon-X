"""Polygon helpers: area, approximate village square, overlap (no PostGIS)."""
import json
import math
from typing import Any, Optional


def as_geojson_feature(geom: Any) -> Optional[dict]:
    """Normalize registry geom / client geojson into a Feature with Polygon geometry."""
    if geom is None:
        return None
    if isinstance(geom, str):
        text = geom.strip()
        if text.startswith("{") or text.startswith("["):
            try:
                geom = json.loads(text)
            except json.JSONDecodeError:
                return None
        elif text.upper().startswith("POLYGON"):
            return _wkt_polygon_to_feature(text)
        else:
            return None
    if not isinstance(geom, dict):
        return None
    if geom.get("type") == "Feature":
        geometry = geom.get("geometry") or {}
        if geometry.get("type") == "Polygon":
            return geom
        return None
    if geom.get("type") == "Polygon":
        return {"type": "Feature", "properties": {}, "geometry": geom}
    if geom.get("type") == "FeatureCollection":
        for feat in geom.get("features") or []:
            converted = as_geojson_feature(feat)
            if converted:
                return converted
    if geom.get("geometry"):
        return as_geojson_feature(geom["geometry"])
    return None


def _wkt_polygon_to_feature(wkt: str) -> Optional[dict]:
    inner = wkt[wkt.find("(") :].replace("(", " ").replace(")", " ")
    coords = []
    for pair in inner.split(","):
        parts = pair.split()
        if len(parts) >= 2:
            try:
                coords.append([float(parts[0]), float(parts[1])])
            except ValueError:
                continue
    if len(coords) < 3:
        return None
    if coords[0] != coords[-1]:
        coords.append(coords[0])
    return {"type": "Feature", "properties": {}, "geometry": {"type": "Polygon", "coordinates": [coords]}}


def ring_from_geojson(geojson: dict) -> list[list[float]]:
    feature = as_geojson_feature(geojson)
    if not feature:
        return []
    rings = (feature.get("geometry") or {}).get("coordinates") or []
    ring = list(rings[0]) if rings else []
    if len(ring) >= 3 and ring[0] != ring[-1]:
        ring.append(ring[0])
    return ring


def polygon_area_hectares(geojson: dict) -> float:
    ring = ring_from_geojson(geojson)
    if len(ring) < 4:
        return 0.0
    lat_mid = sum(float(p[1]) for p in ring[:-1]) / (len(ring) - 1)
    meters_per_degree_lng = 111320 * math.cos(math.radians(lat_mid))
    meters_per_degree_lat = 110540
    projected = [
        (float(lng) * meters_per_degree_lng, float(lat) * meters_per_degree_lat)
        for lng, lat in ring
    ]
    area_m2 = 0.0
    for i in range(len(projected) - 1):
        x1, y1 = projected[i]
        x2, y2 = projected[i + 1]
        area_m2 += x1 * y2 - x2 * y1
    return round(abs(area_m2) / 20000, 4)


def bbox(ring: list[list[float]]) -> Optional[tuple[float, float, float, float]]:
    if len(ring) < 3:
        return None
    xs = [float(p[0]) for p in ring]
    ys = [float(p[1]) for p in ring]
    return min(xs), min(ys), max(xs), max(ys)


def bboxes_overlap(a, b) -> bool:
    if not a or not b:
        return False
    return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])


def polygons_overlap(geojson_a: dict, geojson_b: dict) -> bool:
    """Conservative overlap: bounding-box intersection (no PostGIS required)."""
    return bboxes_overlap(bbox(ring_from_geojson(geojson_a)), bbox(ring_from_geojson(geojson_b)))


def approximate_square(lat: float, lon: float, area_hectares: float) -> dict:
    """Build a square polygon around a point whose area matches area_hectares."""
    area_m2 = max(float(area_hectares or 0.25), 0.05) * 10000
    half = math.sqrt(area_m2) / 2.0
    meters_per_degree_lat = 110540
    meters_per_degree_lng = 111320 * math.cos(math.radians(lat)) or 1.0
    dlat = half / meters_per_degree_lat
    dlng = half / meters_per_degree_lng
    ring = [
        [lon - dlng, lat - dlat],
        [lon + dlng, lat - dlat],
        [lon + dlng, lat + dlat],
        [lon - dlng, lat + dlat],
        [lon - dlng, lat - dlat],
    ]
    return {"type": "Feature", "properties": {"source": "approximate"}, "geometry": {"type": "Polygon", "coordinates": [ring]}}


def area_delta_pct(claimed: Optional[float], measured: Optional[float]) -> Optional[float]:
    if not claimed or not measured or claimed <= 0:
        return None
    return round(abs(measured - claimed) / claimed * 100.0, 2)
