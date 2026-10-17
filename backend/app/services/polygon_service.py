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


INDIA_BBOX = {
    "min_lat": 6.0,
    "max_lat": 38.5,
    "min_lon": 68.0,
    "max_lon": 98.5,
}


def is_in_india(latitude: float, longitude: float) -> bool:
    """Check if a coordinate pair falls within India's geographic bounding box."""
    if not (math.isfinite(latitude) and math.isfinite(longitude)):
        return False
    return (
        INDIA_BBOX["min_lat"] <= latitude <= INDIA_BBOX["max_lat"]
        and INDIA_BBOX["min_lon"] <= longitude <= INDIA_BBOX["max_lon"]
    )


def polygon_area_hectares(geojson: Any) -> float:
    ring = ring_from_geojson(geojson)
    if len(ring) < 4:
        return 0.0
    if len({tuple(p[:2]) for p in ring}) < 3:
        return 0.0
    try:
        lat_mid = sum(float(p[1]) for p in ring[:-1]) / (len(ring) - 1)
        meters_per_degree_lng = 111320 * math.cos(math.radians(lat_mid))
        meters_per_degree_lat = 110540
        projected = [
            (float(p[0]) * meters_per_degree_lng, float(p[1]) * meters_per_degree_lat)
            for p in ring
        ]
        area_m2 = 0.0
        for i in range(len(projected) - 1):
            x1, y1 = projected[i]
            x2, y2 = projected[i + 1]
            area_m2 += x1 * y2 - x2 * y1
        return round(abs(area_m2) / 20000, 4)
    except (IndexError, TypeError, ValueError):
        return 0.0


def bbox(ring: list[list[float]]) -> Optional[tuple[float, float, float, float]]:
    if not ring or len(ring) < 3:
        return None
    if len({tuple(p[:2]) for p in ring}) < 3:
        return None
    try:
        xs = [float(p[0]) for p in ring]
        ys = [float(p[1]) for p in ring]
        return min(xs), min(ys), max(xs), max(ys)
    except (IndexError, TypeError, ValueError):
        return None


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


# ─── GeoJSON polygon validation ───

def validate_polygon_geojson(geojson: Any, check_india: bool = True) -> tuple[bool, str]:
    """Validate GeoJSON polygon: structure, coordinate bounds, ring closure, span, degenerate, India bounds."""
    if not isinstance(geojson, dict):
        return False, "GeoJSON must be an object"
    if geojson.get("type") == "Polygon" and "coordinates" in geojson:
        geom = geojson
    else:
        geom = geojson.get("geometry") or {}
    if geom.get("type") != "Polygon":
        return False, "GeoJSON geometry type must be Polygon"
    rings = geom.get("coordinates")
    if not isinstance(rings, list) or not rings:
        return False, "Polygon coordinates missing"
    ring = rings[0]
    if not isinstance(ring, list) or len(ring) < 4:
        return False, "Polygon ring needs at least 4 positions"
    for pos in ring:
        if (not isinstance(pos, (list, tuple)) or len(pos) < 2
                or not all(isinstance(c, (int, float)) and math.isfinite(c) for c in pos[:2])):
            return False, "Invalid coordinate in polygon ring"
        lon, lat = pos[0], pos[1]
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            return False, "Coordinate out of WGS84 range"
    if list(ring[0][:2]) != list(ring[-1][:2]):
        return False, "Polygon ring must be closed (first == last position)"
    unique_positions = {tuple(pos[:2]) for pos in ring}
    if len(unique_positions) < 3:
        return False, "Polygon ring must have at least 3 unique positions (degenerate geometry)"
    lons = [pos[0] for pos in ring]
    lats = [pos[1] for pos in ring]
    if (max(lons) - min(lons)) >= 60 or (max(lats) - min(lats)) >= 60:
        return False, "Polygon too large — exceeds scan limit, draw a single farm plot"
    if check_india:
        for pos in ring:
            lon, lat = pos[0], pos[1]
            if not is_in_india(lat, lon):
                return False, f"Coordinates ({lat:.2f}, {lon:.2f}) are outside India — CarbonX only supports farmland within India"
    return True, ""


def validate_polygon_area(geojson: Any, max_area_ha: float = 10000.0) -> tuple[bool, str]:
    """Validate that parcel area is positive and does not exceed max_area_ha."""
    area = polygon_area_hectares(geojson)
    if area <= 0.0:
        return False, "Parcel area must be greater than zero"
    if area > max_area_ha:
        return False, f"Parcel area {area:,.0f} ha exceeds the {max_area_ha:,.0f} ha limit — draw a single farm plot"
    return True, ""


# ─── Point-in-polygon (pure-Python ray casting) ───

def _extract_polygons(geojson: Any) -> list:
    """Normalize GeoJSON into a list of polygons (each: list of rings)."""
    if not isinstance(geojson, dict):
        return []
    if geojson.get("type") == "FeatureCollection":
        polygons = []
        for feature in geojson.get("features") or []:
            polygons.extend(_extract_polygons(feature))
        return polygons
    geometry = geojson
    if geojson.get("type") == "Feature":
        geometry = geojson.get("geometry") or {}
    if not isinstance(geometry, dict):
        return []
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates")
    if geometry_type == "Polygon" and isinstance(coordinates, list):
        return [coordinates]
    if geometry_type == "MultiPolygon" and isinstance(coordinates, list):
        return [polygon for polygon in coordinates if isinstance(polygon, list)]
    if geometry_type == "GeometryCollection":
        polygons = []
        for geom in geometry.get("geometries") or []:
            polygons.extend(_extract_polygons(geom))
        return polygons
    return []


def _ring_points(ring: Any) -> list:
    """(x=lon, y=lat) float pairs; ``[]`` when the ring is invalid/degenerate."""
    points = []
    for position in ring or []:
        try:
            longitude = float(position[0])
            latitude = float(position[1])
        except (TypeError, ValueError, IndexError, KeyError):
            return []
        if not (math.isfinite(longitude) and math.isfinite(latitude)):
            return []
        points.append((longitude, latitude))
    if len(points) >= 2 and points[0] == points[-1]:
        points = points[:-1]
    if len(set(points)) < 3:
        return []
    return points if len(points) >= 3 else []


def _point_on_segment(latitude: float, longitude: float, a: tuple, b: tuple, eps: float = 1e-9) -> bool:
    ax, ay = a
    bx, by = b
    if abs((longitude - ax) * (by - ay) - (latitude - ay) * (bx - ax)) > eps:
        return False
    return (
        min(ax, bx) - eps <= longitude <= max(ax, bx) + eps
        and min(ay, by) - eps <= latitude <= max(ay, by) + eps
    )


def _ring_contains(latitude: float, longitude: float, points: list) -> bool:
    """Ray-casting containment in one ring; boundary points count as inside."""
    count = len(points)
    if count < 3:
        return False
    for index in range(count):
        if _point_on_segment(latitude, longitude, points[index], points[(index + 1) % count]):
            return True
    inside = False
    previous = count - 1
    for index in range(count):
        xi, yi = points[index]
        xj, yj = points[previous]
        if (yi > latitude) != (yj > latitude):
            x_at = xi + (latitude - yi) * (xj - xi) / (yj - yi)
            if longitude < x_at:
                inside = not inside
        previous = index
    return inside


def point_in_polygon(latitude: float, longitude: float, geojson: Any) -> bool:
    """Ray-casting containment for a GeoJSON Polygon/MultiPolygon (holes respected)."""
    for polygon in _extract_polygons(geojson):
        if not polygon:
            continue
        exterior = _ring_points(polygon[0])
        if not exterior or not _ring_contains(latitude, longitude, exterior):
            continue
        if any(_ring_contains(latitude, longitude, _ring_points(hole)) for hole in polygon[1:]):
            continue  # point sits in a hole
        return True
    return False


def verify_inside_boundary(latitude: float, longitude: float, geojson: Any) -> tuple[bool, str]:
    """Return ``(inside, reason)``. Never True without a valid point + polygon."""
    if not (math.isfinite(latitude) and math.isfinite(longitude)):
        return False, "Coordinates must be finite numbers"
    if not isinstance(geojson, dict) or not geojson:
        return False, "No farm boundary on record — coordinates stored without an inside-boundary check"
    if not _extract_polygons(geojson):
        return False, "Farm boundary is not a valid Polygon/MultiPolygon — coordinates stored without an inside-boundary check"
    if point_in_polygon(latitude, longitude, geojson):
        return True, "Coordinates verified inside the farm boundary"
    return False, "Coordinates fall outside the farm boundary"

