"""Comprehensive edge-case tests for GeoSpatial & MRV Boundary validation.

Covers:
1. Complex polygons:
   - Unclosed rings (auto-closure verification in polygon service, WKT, Pahani)
   - Clockwise vs counter-clockwise coordinates (area invariance, containment parity)
   - Degenerate geometries (<3 unique points, collinear / collapsed segments)
2. Coordinate bounds:
   - India geofencing (6.0 <= lat <= 38.5, 68.0 <= lon <= 98.5)
   - Coordinates far outside India (Atlantic Ocean, poles, WGS84 overflow) properly rejected
3. Area limits:
   - Massive polygons (>10,000 ha) rejected early before processing
   - Early scan guards in /analyze and /save-farm
4. Ray-casting point-in-polygon edge cases:
   - Points exactly on vertices
   - Points on edges (horizontal and vertical)
   - Points in exterior rings vs interior holes
   - MultiPolygons and GeometryCollections
5. EXIF parsing in evidence:
   - Hemisphere signs (N/S, E/W, lowercase, bytes)
   - Missing GPS data (no EXIF, missing IFD, missing coordinates, missing ref)
   - Corrupt EXIF headers (division by zero, malformed types, NaN/Inf, out-of-range)

Run from backend/: python -m unittest tests/test_geospatial_deep.py
"""
import io
import math
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Hermetic environment: clear database variables
for _k in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "VITE_SUPABASE_URL", "VITE_SUPABASE_ANON_KEY"):
    os.environ.pop(_k, None)
os.environ["SUPABASE_URL"] = ""
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = ""

_TMP_EVIDENCE = tempfile.mkdtemp(prefix="carbonx_geospatial_test_")
os.environ["CARBONX_EVIDENCE_DIR"] = _TMP_EVIDENCE

from PIL import Image  # noqa: E402
from PIL.TiffImagePlugin import IFDRational  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app import supabase_db as _db  # noqa: E402
from app import gee_runtime  # noqa: E402
from app.services import polygon_service as poly  # noqa: E402
from app.services import evidence_service as evidence  # noqa: E402
from app.security import create_access_token  # noqa: E402

# Hermetic DB reset
_db._supabase = None
_db._ready = False

# Ensure GEE does not attempt network calls during hermetic testing
gee_runtime.earth_engine_ready = False

client = TestClient(app)


def tearDownModule():
    shutil.rmtree(_TMP_EVIDENCE, ignore_errors=True)


def _dms(value: float) -> tuple[int, int, float]:
    val = abs(value)
    deg = int(val)
    min_float = (val - deg) * 60
    minute = int(min_float)
    sec = round((min_float - minute) * 60, 4)
    return (deg, minute, sec)


def make_test_jpeg(gps: tuple = None) -> bytes:
    """Create test JPEG with optional EXIF GPS tuple: (lat, lon, lat_ref, lon_ref)."""
    img = Image.new("RGB", (16, 16), color="green")
    buf = io.BytesIO()
    if gps is not None:
        lat, lon, lat_ref, lon_ref = gps
        exif = Image.Exif()
        exif[34853] = {
            1: lat_ref,
            2: _dms(lat),
            3: lon_ref,
            4: _dms(lon),
        }
        img.save(buf, format="JPEG", exif=exif)
    else:
        img.save(buf, format="JPEG")
    return buf.getvalue()


class FakeExifObj:
    """Mock EXIF object for simulating corrupt or custom IFDs."""
    def __init__(self, gps_dict):
        self._gps = gps_dict

    def get_ifd(self, tag):
        if tag == 34853:
            return self._gps
        return {}


# ═════════════════════════════════════════════════════════════════════
# 1. Complex Polygons: Auto-Closure, Clockwise/CCW, Degenerate Geometries
# ═════════════════════════════════════════════════════════════════════

class ComplexPolygonEdgeCaseTests(unittest.TestCase):
    def test_unclosed_ring_auto_closure_in_ring_from_geojson(self):
        """ring_from_geojson must auto-close an unclosed 3-point triangle."""
        unclosed = {
            "type": "Polygon",
            "coordinates": [[[78.48, 17.38], [78.49, 17.38], [78.49, 17.39]]],
        }
        closed_ring = poly.ring_from_geojson(unclosed)
        self.assertEqual(len(closed_ring), 4)
        self.assertEqual(closed_ring[0], closed_ring[-1])
        self.assertEqual(closed_ring[-1], [78.48, 17.38])

    def test_unclosed_ring_auto_closure_in_wkt(self):
        """WKT polygon parsing must auto-close coordinates when first != last."""
        wkt = "POLYGON((78.48 17.38, 78.49 17.38, 78.49 17.39))"
        feat = poly.as_geojson_feature(wkt)
        self.assertIsNotNone(feat)
        coords = feat["geometry"]["coordinates"][0]
        self.assertEqual(len(coords), 4)
        self.assertEqual(coords[0], coords[-1])

    def test_unclosed_ring_area_matches_explicitly_closed_ring(self):
        """polygon_area_hectares must compute the exact same area whether ring is closed or unclosed."""
        unclosed = {
            "type": "Polygon",
            "coordinates": [[[78.48, 17.38], [78.49, 17.38], [78.49, 17.39], [78.48, 17.39]]],
        }
        closed = {
            "type": "Polygon",
            "coordinates": [[[78.48, 17.38], [78.49, 17.38], [78.49, 17.39], [78.48, 17.39], [78.48, 17.38]]],
        }
        area_unclosed = poly.polygon_area_hectares(unclosed)
        area_closed = poly.polygon_area_hectares(closed)
        self.assertGreater(area_closed, 0.0)
        self.assertEqual(area_unclosed, area_closed)

    def test_unclosed_ring_rejected_by_strict_validator(self):
        """GeoJSON specification requires explicit ring closure for API payload schemas."""
        unclosed = {
            "type": "Polygon",
            "coordinates": [[[78.48, 17.38], [78.49, 17.38], [78.49, 17.39], [78.48, 17.39]]],
        }
        ok, msg = poly.validate_polygon_geojson(unclosed)
        self.assertFalse(ok)
        self.assertIn("closed", msg)

    def test_clockwise_vs_counterclockwise_area_invariance(self):
        """Shoelace formula must produce positive, identical areas regardless of winding order."""
        ccw = {
            "type": "Polygon",
            "coordinates": [[[78.48, 17.38], [78.49, 17.38], [78.49, 17.39], [78.48, 17.39], [78.48, 17.38]]],
        }
        # Reverse coordinates to make it clockwise
        cw = {
            "type": "Polygon",
            "coordinates": [[[78.48, 17.38], [78.48, 17.39], [78.49, 17.39], [78.49, 17.38], [78.48, 17.38]]],
        }
        area_ccw = poly.polygon_area_hectares(ccw)
        area_cw = poly.polygon_area_hectares(cw)
        self.assertGreater(area_ccw, 0.0)
        self.assertEqual(area_ccw, area_cw)

    def test_clockwise_vs_counterclockwise_containment_invariance(self):
        """Ray casting must produce identical containment verdicts for CW and CCW polygons."""
        ccw = {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[78.48, 17.38], [78.49, 17.38], [78.49, 17.39], [78.48, 17.39], [78.48, 17.38]]],
            },
        }
        cw = {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[78.48, 17.38], [78.48, 17.39], [78.49, 17.39], [78.49, 17.38], [78.48, 17.38]]],
            },
        }
        center_lat, center_lon = 17.385, 78.485
        outside_lat, outside_lon = 17.400, 78.485
        edge_lat, edge_lon = 17.380, 78.485

        self.assertTrue(poly.point_in_polygon(center_lat, center_lon, ccw))
        self.assertTrue(poly.point_in_polygon(center_lat, center_lon, cw))
        self.assertFalse(poly.point_in_polygon(outside_lat, outside_lon, ccw))
        self.assertFalse(poly.point_in_polygon(outside_lat, outside_lon, cw))
        self.assertTrue(poly.point_in_polygon(edge_lat, edge_lon, ccw))
        self.assertTrue(poly.point_in_polygon(edge_lat, edge_lon, cw))

    def test_degenerate_single_point_repeated(self):
        """A ring where all vertices are the same point (<3 unique points) must be rejected."""
        single_point = {
            "type": "Polygon",
            "coordinates": [[[78.48, 17.38], [78.48, 17.38], [78.48, 17.38], [78.48, 17.38]]],
        }
        ok, msg = poly.validate_polygon_geojson(single_point)
        self.assertFalse(ok)
        self.assertIn("unique", msg.lower())
        self.assertEqual(poly.polygon_area_hectares(single_point), 0.0)
        self.assertIsNone(poly.bbox(poly.ring_from_geojson(single_point)))
        self.assertFalse(poly.point_in_polygon(17.38, 78.48, single_point))

    def test_degenerate_two_points_collapsed_line_segment(self):
        """A ring with only 2 unique points (collapsed into a 1D line) must be rejected."""
        two_points = {
            "type": "Polygon",
            "coordinates": [[[78.48, 17.38], [78.49, 17.39], [78.48, 17.38], [78.48, 17.38]]],
        }
        ok, msg = poly.validate_polygon_geojson(two_points)
        self.assertFalse(ok)
        self.assertIn("unique", msg.lower())
        self.assertEqual(poly.polygon_area_hectares(two_points), 0.0)
        self.assertFalse(poly.point_in_polygon(17.385, 78.485, two_points))


# ═════════════════════════════════════════════════════════════════════
# 2. Coordinate Bounds & India Geofencing
# ═════════════════════════════════════════════════════════════════════

class CoordinateBoundsEdgeCaseTests(unittest.TestCase):
    def setUp(self):
        self.token = create_access_token({"phone": "9999999999", "role": "farmer", "name": "Geospatial Tester"})
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def test_is_in_india_bounds_coverage(self):
        """Check known valid locations in India vs points far outside."""
        # Inside India
        self.assertTrue(poly.is_in_india(17.38, 78.48))   # Hyderabad (Telangana)
        self.assertTrue(poly.is_in_india(28.61, 77.20))   # New Delhi
        self.assertTrue(poly.is_in_india(11.94, 79.80))   # Puducherry (South)
        self.assertTrue(poly.is_in_india(34.08, 74.79))   # Srinagar (North)
        self.assertTrue(poly.is_in_india(23.02, 72.57))   # Ahmedabad (West)
        self.assertTrue(poly.is_in_india(27.47, 94.91))   # Assam (East)

        # Far outside India
        self.assertFalse(poly.is_in_india(15.0, -30.0))   # Atlantic Ocean
        self.assertFalse(poly.is_in_india(85.0, 0.0))     # Arctic / North Pole
        self.assertFalse(poly.is_in_india(-85.0, 0.0))    # Antarctica / South Pole
        self.assertFalse(poly.is_in_india(37.77, -122.41)) # San Francisco, USA
        self.assertFalse(poly.is_in_india(51.50, -0.12))   # London, UK
        self.assertFalse(poly.is_in_india(float("nan"), 78.48))
        self.assertFalse(poly.is_in_india(17.38, float("inf")))

    def test_validate_polygon_rejects_atlantic_ocean_polygon(self):
        """A farm polygon in the Atlantic Ocean must be rejected with an India-boundary message."""
        atlantic_poly = {
            "type": "Polygon",
            "coordinates": [[[-30.0, 15.0], [-29.9, 15.0], [-29.9, 15.1], [-30.0, 15.1], [-30.0, 15.0]]],
        }
        ok, msg = poly.validate_polygon_geojson(atlantic_poly)
        self.assertFalse(ok)
        self.assertIn("outside India", msg)

    def test_validate_polygon_rejects_polar_polygons(self):
        """Polygons at the North Pole or South Pole must be rejected."""
        north_pole = {
            "type": "Polygon",
            "coordinates": [[[0.0, 85.0], [0.1, 85.0], [0.1, 85.1], [0.0, 85.1], [0.0, 85.0]]],
        }
        ok, msg = poly.validate_polygon_geojson(north_pole)
        self.assertFalse(ok)
        self.assertIn("outside India", msg)

        south_pole = {
            "type": "Polygon",
            "coordinates": [[[0.0, -85.0], [0.1, -85.0], [0.1, -84.9], [0.0, -84.9], [0.0, -85.0]]],
        }
        ok, msg = poly.validate_polygon_geojson(south_pole)
        self.assertFalse(ok)
        self.assertIn("outside India", msg)

    def test_predict_endpoint_rejects_coordinates_outside_india(self):
        """GET /predict with coordinates in Atlantic Ocean or poles must return error without fabricating."""
        res_atlantic = client.get("/predict?latitude=15.0&longitude=-30.0")
        self.assertEqual(res_atlantic.status_code, 200)
        body = res_atlantic.json()
        self.assertFalse(body["success"])
        self.assertIn("outside India", body["message"])

        res_pole = client.get("/predict?latitude=88.0&longitude=0.0")
        self.assertFalse(res_pole.json()["success"])
        self.assertIn("outside India", res_pole.json()["message"])

    def test_save_farm_rejects_polygon_outside_india(self):
        """POST /save-farm with an Atlantic Ocean boundary must be rejected."""
        farm_data = {
            "name": "Atlantic Plot",
            "crop_type": "Rice",
            "geojson": {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[-30.0, 15.0], [-29.9, 15.0], [-29.9, 15.1], [-30.0, 15.1], [-30.0, 15.0]]],
                },
            },
        }
        res = client.post("/save-farm", json={"farm": farm_data}, headers=self.headers)
        body = res.json()
        self.assertFalse(body["success"])
        self.assertIn("outside India", body["message"])

    def test_analyze_rejects_polygon_outside_india(self):
        """POST /analyze with coordinates outside India must be rejected early."""
        bad_geojson = {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[-30.0, 15.0], [-29.9, 15.0], [-29.9, 15.1], [-30.0, 15.1], [-30.0, 15.0]]],
            },
        }
        res = client.post("/analyze", json={"geojson": bad_geojson, "crop_type": "Cotton"})
        # Fails at Pydantic validator or router check
        if res.status_code == 200:
            self.assertFalse(res.json()["success"])
            self.assertIn("outside India", res.json()["message"])
        else:
            self.assertEqual(res.status_code, 422)


# ═════════════════════════════════════════════════════════════════════
# 3. Area Limits (>10,000 ha) Early Rejection
# ═════════════════════════════════════════════════════════════════════

class AreaLimitEdgeCaseTests(unittest.TestCase):
    def setUp(self):
        self.token = create_access_token({"phone": "9999999999", "role": "farmer", "name": "Area Tester"})
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def test_validate_polygon_area_helper(self):
        """validate_polygon_area helper enforces positive area and <= 10,000 ha ceiling."""
        small_poly = {
            "type": "Polygon",
            "coordinates": [[[78.48, 17.38], [78.49, 17.38], [78.49, 17.39], [78.48, 17.39], [78.48, 17.38]]],
        }
        ok, msg = poly.validate_polygon_area(small_poly, max_area_ha=10000.0)
        self.assertTrue(ok)
        self.assertEqual(msg, "")

        # Massive 0.5 deg x 0.5 deg polygon (~300,000 ha)
        giant_poly = {
            "type": "Polygon",
            "coordinates": [[[78.0, 17.0], [78.5, 17.0], [78.5, 17.5], [78.0, 17.5], [78.0, 17.0]]],
        }
        ok_giant, msg_giant = poly.validate_polygon_area(giant_poly, max_area_ha=10000.0)
        self.assertFalse(ok_giant)
        self.assertIn("exceeds the 10,000 ha limit", msg_giant)

    def test_save_farm_rejects_calculated_massive_polygon(self):
        """Even if area_hectares is not explicitly passed, save_farm must calculate area and reject >10k ha."""
        giant_poly = {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[78.0, 17.0], [78.5, 17.0], [78.5, 17.5], [78.0, 17.5], [78.0, 17.0]]],
            },
        }
        res = client.post("/save-farm", json={"farm": {"name": "Megaplot", "geojson": giant_poly}}, headers=self.headers)
        body = res.json()
        self.assertFalse(body["success"])
        self.assertIn("exceeds the 10,000 ha limit", body["message"])

    def test_analyze_rejects_massive_polygon_early(self):
        """POST /analyze must reject parcels > 10,000 ha early before invoking Earth Engine."""
        giant_poly = {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[78.0, 17.0], [78.5, 17.0], [78.5, 17.5], [78.0, 17.5], [78.0, 17.0]]],
            },
        }
        res = client.post("/analyze", json={"geojson": giant_poly, "crop_type": "Wheat"})
        body = res.json()
        self.assertFalse(body["success"])
        self.assertIn("exceeds the 10,000 ha scan limit", body["message"])


# ═════════════════════════════════════════════════════════════════════
# 4. Ray-Casting Point-in-Polygon: Vertices, Edges, Holes
# ═════════════════════════════════════════════════════════════════════

class RayCastingEdgeCaseTests(unittest.TestCase):
    def setUp(self):
        # 10m x 10m square near Hyderabad: lon [78.480, 78.490], lat [17.380, 17.390]
        self.square = {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [[78.480, 17.380], [78.490, 17.380], [78.490, 17.390], [78.480, 17.390], [78.480, 17.380]]
                ],
            },
        }
        # Donut polygon with an interior hole
        self.donut = {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    # Exterior ring: [78.0, 17.0] to [78.4, 17.4]
                    [[78.0, 17.0], [78.4, 17.0], [78.4, 17.4], [78.0, 17.4], [78.0, 17.0]],
                    # Interior hole: [78.1, 17.1] to [78.3, 17.3]
                    [[78.1, 17.1], [78.3, 17.1], [78.3, 17.3], [78.1, 17.3], [78.1, 17.1]],
                ],
            },
        }

    def test_points_exactly_on_vertices(self):
        """Every vertex of the polygon must be recognized as inside the boundary."""
        vertices = [
            (17.380, 78.480),  # bottom-left
            (17.380, 78.490),  # bottom-right
            (17.390, 78.490),  # top-right
            (17.390, 78.480),  # top-left
        ]
        for lat, lon in vertices:
            self.assertTrue(poly.point_in_polygon(lat, lon, self.square), f"Failed for vertex ({lat}, {lon})")
            inside, _ = poly.verify_inside_boundary(lat, lon, self.square)
            self.assertTrue(inside, f"verify_inside_boundary failed for vertex ({lat}, {lon})")

    def test_points_on_horizontal_and_vertical_edges(self):
        """Midpoints along horizontal and vertical boundary edges must count as inside."""
        edge_points = [
            (17.380, 78.485),  # bottom horizontal edge
            (17.390, 78.485),  # top horizontal edge
            (17.385, 78.480),  # left vertical edge
            (17.385, 78.490),  # right vertical edge
        ]
        for lat, lon in edge_points:
            self.assertTrue(poly.point_in_polygon(lat, lon, self.square), f"Failed for edge point ({lat}, {lon})")
            inside, _ = poly.verify_inside_boundary(lat, lon, self.square)
            self.assertTrue(inside, f"verify_inside_boundary failed for edge point ({lat}, {lon})")

    def test_points_interior_vs_exterior(self):
        """Points clearly inside must return True; points outside must return False."""
        self.assertTrue(poly.point_in_polygon(17.385, 78.485, self.square))
        self.assertFalse(poly.point_in_polygon(17.375, 78.485, self.square))  # South
        self.assertFalse(poly.point_in_polygon(17.395, 78.485, self.square))  # North
        self.assertFalse(poly.point_in_polygon(17.385, 78.475, self.square))  # West
        self.assertFalse(poly.point_in_polygon(17.385, 78.495, self.square))  # East

    def test_interior_hole_exclusion(self):
        """Points inside the exterior ring but outside the hole are inside; points in hole are excluded."""
        # Inside exterior ring, outside hole
        self.assertTrue(poly.point_in_polygon(17.05, 78.05, self.donut))
        self.assertTrue(poly.point_in_polygon(17.35, 78.35, self.donut))

        # Strictly inside the hole
        self.assertFalse(poly.point_in_polygon(17.20, 78.20, self.donut))
        self.assertFalse(poly.point_in_polygon(17.15, 78.25, self.donut))

        # Outside the entire polygon
        self.assertFalse(poly.point_in_polygon(17.50, 78.50, self.donut))

    def test_multipolygon_two_parcels(self):
        """MultiPolygon parcels must independently test positive for containment."""
        multi = {
            "type": "MultiPolygon",
            "coordinates": [
                [[[78.0, 17.0], [78.1, 17.0], [78.1, 17.1], [78.0, 17.1], [78.0, 17.0]]],
                [[[79.0, 18.0], [79.1, 18.0], [79.1, 18.1], [79.0, 18.1], [79.0, 18.0]]],
            ],
        }
        self.assertTrue(poly.point_in_polygon(17.05, 78.05, multi))  # parcel 1
        self.assertTrue(poly.point_in_polygon(18.05, 79.05, multi))  # parcel 2
        self.assertFalse(poly.point_in_polygon(17.50, 78.50, multi)) # gap between parcels

    def test_ray_casting_non_finite_inputs(self):
        """NaN and Inf coordinates must be cleanly handled and never cause an unhandled exception."""
        inside, reason = poly.verify_inside_boundary(float("nan"), 78.485, self.square)
        self.assertFalse(inside)
        self.assertIn("finite", reason.lower())

        inside_inf, reason_inf = poly.verify_inside_boundary(17.385, float("inf"), self.square)
        self.assertFalse(inside_inf)
        self.assertIn("finite", reason_inf.lower())


# ═════════════════════════════════════════════════════════════════════
# 5. EXIF Parsing in Evidence: Hemisphere Signs, Missing & Corrupt GPS
# ═════════════════════════════════════════════════════════════════════

class EvidenceExifDeepTests(unittest.TestCase):
    def test_hemisphere_north_east_positive(self):
        """N and E hemisphere tags must result in positive coordinates."""
        data = make_test_jpeg((17.38, 78.48, "N", "E"))
        coords = evidence.extract_exif_gps(data)
        self.assertIsNotNone(coords)
        self.assertAlmostEqual(coords["latitude"], 17.38, places=4)
        self.assertAlmostEqual(coords["longitude"], 78.48, places=4)

    def test_hemisphere_south_west_negative(self):
        """S and W hemisphere tags must result in signed negative coordinates."""
        data = make_test_jpeg((17.38, 78.48, "S", "W"))
        coords = evidence.extract_exif_gps(data)
        self.assertIsNotNone(coords)
        self.assertAlmostEqual(coords["latitude"], -17.38, places=4)
        self.assertAlmostEqual(coords["longitude"], -78.48, places=4)

    def test_hemisphere_south_east_and_north_west(self):
        """Mixed hemisphere references must accurately sign the respective axis."""
        data_se = make_test_jpeg((12.5, 45.5, "S", "E"))
        coords_se = evidence.extract_exif_gps(data_se)
        self.assertAlmostEqual(coords_se["latitude"], -12.5, places=4)
        self.assertAlmostEqual(coords_se["longitude"], 45.5, places=4)

        data_nw = make_test_jpeg((35.0, 110.0, "N", "W"))
        coords_nw = evidence.extract_exif_gps(data_nw)
        self.assertAlmostEqual(coords_nw["latitude"], 35.0, places=4)
        self.assertAlmostEqual(coords_nw["longitude"], -110.0, places=4)

    def test_hemisphere_bytes_and_lowercase_handling(self):
        """Pillow raw byte tags (e.g. b'S') and lowercase 's'/'w' must be normalized."""
        fake = FakeExifObj({
            1: b"S",
            2: (17, 22, 48),
            3: b"w",
            4: (78, 28, 48),
        })
        coords = evidence.parse_exif_gps(fake)
        self.assertIsNotNone(coords)
        self.assertLess(coords["latitude"], 0)
        self.assertLess(coords["longitude"], 0)

    def test_missing_hemisphere_tag_refused(self):
        """An unlabelled coordinate must never be guessed as N/E — must return None."""
        fake = FakeExifObj({
            2: (17, 22, 48),
            4: (78, 28, 48),
        })
        self.assertIsNone(evidence.parse_exif_gps(fake))

    def test_missing_gps_data_in_image(self):
        """Image without any GPS IFD or tags must safely return None without error."""
        data_no_gps = make_test_jpeg(None)
        self.assertIsNone(evidence.extract_exif_gps(data_no_gps))

        photo = evidence.inspect_photo(data_no_gps)
        self.assertEqual(photo["mime"], "image/jpeg")
        self.assertIsNone(photo["exif"])

    def test_corrupt_exif_zero_division(self):
        """IFDRational with denominator 0 must be caught safely as None."""
        fake = FakeExifObj({
            1: "N",
            2: (IFDRational(17, 0), IFDRational(20, 1), IFDRational(0, 1)),
            3: "E",
            4: (IFDRational(78, 1), IFDRational(30, 1), IFDRational(0, 1)),
        })
        self.assertIsNone(evidence.parse_exif_gps(fake))

    def test_corrupt_exif_non_numeric_and_malformed_types(self):
        """Non-numeric string values or corrupt objects in GPS IFD must not raise."""
        fake = FakeExifObj({
            1: "N",
            2: "corrupt_latitude_string",
            3: "E",
            4: None,
        })
        self.assertIsNone(evidence.parse_exif_gps(fake))

    def test_corrupt_exif_nan_and_inf(self):
        """NaN and Inf coordinates inside EXIF IFD must be rejected."""
        fake = FakeExifObj({
            1: "N",
            2: (float("nan"), 0, 0),
            3: "E",
            4: (float("inf"), 0, 0),
        })
        self.assertIsNone(evidence.parse_exif_gps(fake))

    def test_exif_coordinates_out_of_wgs84_range(self):
        """Coordinates exceeding WGS84 range (>90 lat or >180 lon) must return None."""
        fake = FakeExifObj({
            1: "N",
            2: (95.0, 0, 0),
            3: "E",
            4: (195.0, 0, 0),
        })
        self.assertIsNone(evidence.parse_exif_gps(fake))

    def test_inspect_photo_empty_and_garbage_bytes(self):
        """inspect_photo must raise EvidenceImageError on empty or non-image bytes."""
        with self.assertRaises(evidence.EvidenceImageError):
            evidence.inspect_photo(b"")

        with self.assertRaises(evidence.EvidenceImageError):
            evidence.inspect_photo(b"RIFF....corrupt_data")


if __name__ == "__main__":
    unittest.main()
