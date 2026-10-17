"""Tests for polygon_service, analyze_router concurrency, and farms_router polygon/area validation."""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

for _k in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "VITE_SUPABASE_URL", "VITE_SUPABASE_ANON_KEY"):
    os.environ.pop(_k, None)
os.environ["SUPABASE_URL"] = ""
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = ""

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402
from app import supabase_db as _db  # noqa: E402
from app.services import polygon_service as poly  # noqa: E402
from app.security import create_access_token  # noqa: E402

# hermetic db reset
_db._supabase = None
_db._ready = False

client = TestClient(app)


class PolygonServiceTests(unittest.TestCase):
    def test_polygon_area_hectares_standard(self):
        # 0.01 deg x 0.01 deg near lat 0 -> ~111320 * 110540 * 1e-4 m^2 / 10000 ha
        geojson = {
            "type": "Polygon",
            "coordinates": [[[0.0, 0.0], [0.01, 0.0], [0.01, 0.01], [0.0, 0.01], [0.0, 0.0]]],
        }
        area = poly.polygon_area_hectares(geojson)
        self.assertGreater(area, 100)
        self.assertLess(area, 150)

    def test_polygon_area_with_3d_coordinates(self):
        # Coordinates with altitude [lon, lat, elevation] must not crash unpack
        geojson = {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [[78.48, 17.38, 500.0], [78.49, 17.38, 505.0], [78.49, 17.39, 510.0], [78.48, 17.39, 502.0], [78.48, 17.38, 500.0]]
                ],
            },
        }
        area = poly.polygon_area_hectares(geojson)
        self.assertGreater(area, 0.0)

    def test_polygon_area_degenerate(self):
        self.assertEqual(poly.polygon_area_hectares({}), 0.0)
        self.assertEqual(poly.polygon_area_hectares({"type": "Polygon", "coordinates": []}), 0.0)
        self.assertEqual(poly.polygon_area_hectares({"type": "Polygon", "coordinates": [[[0, 0], [1, 1]]]}), 0.0)

    def test_validate_polygon_geojson_checks(self):
        # Non-dict
        ok, msg = poly.validate_polygon_geojson("not a dict")
        self.assertFalse(ok)
        self.assertIn("object", msg)

        # Invalid geometry type
        ok, msg = poly.validate_polygon_geojson({"type": "Point", "coordinates": [0, 0]})
        self.assertFalse(ok)
        self.assertIn("Polygon", msg)

        # Too few positions (<4)
        ok, msg = poly.validate_polygon_geojson({"type": "Polygon", "coordinates": [[[0, 0], [1, 1], [0, 0]]]})
        self.assertFalse(ok)
        self.assertIn("at least 4", msg)

        # Non-finite coordinates
        ok, msg = poly.validate_polygon_geojson({
            "type": "Polygon",
            "coordinates": [[[0, 0], [float("nan"), 1], [1, 0], [0, 0]]],
        })
        self.assertFalse(ok)
        self.assertIn("Invalid coordinate", msg)

        # Out of WGS84 range
        ok, msg = poly.validate_polygon_geojson({
            "type": "Polygon",
            "coordinates": [[[0, 0], [200, 10], [1, 0], [0, 0]]],
        })
        self.assertFalse(ok)
        self.assertIn("WGS84", msg)

        # Unclosed ring
        ok, msg = poly.validate_polygon_geojson({
            "type": "Polygon",
            "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1]]],
        })
        self.assertFalse(ok)
        self.assertIn("closed", msg)

        # Span >= 60 degrees
        ok, msg = poly.validate_polygon_geojson({
            "type": "Polygon",
            "coordinates": [[[0, 0], [61, 0], [61, 1], [0, 1], [0, 0]]],
        })
        self.assertFalse(ok)
        self.assertIn("scan limit", msg)

        # Valid polygon (Feature)
        ok, msg = poly.validate_polygon_geojson({
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[78.48, 17.38], [78.49, 17.38], [78.49, 17.39], [78.48, 17.39], [78.48, 17.38]]],
            },
        })
        self.assertTrue(ok)
        self.assertEqual(msg, "")

    def test_ray_casting_containment(self):
        # Square with a hole in the center
        # Outer ring: [0, 0] to [10, 10]
        # Hole: [3, 3] to [7, 7]
        poly_with_hole = {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]],
                    [[3, 3], [7, 3], [7, 7], [3, 7], [3, 3]],
                ],
            },
        }

        # Point inside outer ring but outside hole: (1, 1) -> inside
        self.assertTrue(poly.point_in_polygon(latitude=1.0, longitude=1.0, geojson=poly_with_hole))

        # Point inside hole: (5, 5) -> outside
        self.assertFalse(poly.point_in_polygon(latitude=5.0, longitude=5.0, geojson=poly_with_hole))

        # Point outside outer ring: (15, 15) -> outside
        self.assertFalse(poly.point_in_polygon(latitude=15.0, longitude=15.0, geojson=poly_with_hole))

        # Point on boundary: (5, 0) -> inside
        self.assertTrue(poly.point_in_polygon(latitude=0.0, longitude=5.0, geojson=poly_with_hole))

        # verify_inside_boundary
        inside, reason = poly.verify_inside_boundary(1.0, 1.0, poly_with_hole)
        self.assertTrue(inside)
        self.assertIn("verified inside", reason)

        inside_hole, reason_hole = poly.verify_inside_boundary(5.0, 5.0, poly_with_hole)
        self.assertFalse(inside_hole)
        self.assertIn("outside", reason_hole)


class FarmEnrollmentValidationTests(unittest.TestCase):
    def setUp(self):
        self.token = create_access_token({"phone": "9999999999", "role": "farmer", "name": "Farmer Test"})
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def test_save_farm_rejects_unclosed_polygon(self):
        unclosed = {
            "name": "Bad Farm",
            "crop_type": "Rice",
            "geojson": {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[78.48, 17.38], [78.49, 17.38], [78.49, 17.39], [78.48, 17.39]]],
                },
            },
        }
        res = client.post("/save-farm", json={"farm": unclosed}, headers=self.headers)
        body = res.json()
        self.assertFalse(body["success"])
        self.assertIn("closed", body["message"])

    def test_save_farm_rejects_oversized_area(self):
        # 12,000 ha area
        oversized = {
            "name": "Giant Farm",
            "crop_type": "Rice",
            "area_hectares": 12000.0,
            "geojson": {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[78.48, 17.38], [78.49, 17.38], [78.49, 17.39], [78.48, 17.39], [78.48, 17.38]]],
                },
            },
        }
        res = client.post("/save-farm", json={"farm": oversized}, headers=self.headers)
        body = res.json()
        self.assertFalse(body["success"])
        self.assertIn("exceeds the 10,000 ha limit", body["message"])

    def test_save_farm_rejects_zero_or_negative_area(self):
        zero_area = {
            "name": "Zero Farm",
            "crop_type": "Rice",
            "area_hectares": -5.0,
            "geojson": {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[78.48, 17.38], [78.49, 17.38], [78.49, 17.39], [78.48, 17.39], [78.48, 17.38]]],
                },
            },
        }
        res = client.post("/save-farm", json={"farm": zero_area}, headers=self.headers)
        body = res.json()
        self.assertFalse(body["success"])
        self.assertIn("greater than zero", body["message"])


class AnalyzeRouteConcurrencyAndFallbackTests(unittest.TestCase):
    def test_analyze_rejects_unclosed_polygon(self):
        bad_poly = {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[78.48, 17.38], [78.49, 17.38], [78.49, 17.39], [78.48, 17.39]]],
            },
        }
        res = client.post("/analyze", json={"geojson": bad_poly, "crop_type": "Rice"})
        body = res.json()
        self.assertFalse(body["success"])
        self.assertIn("closed", body["message"])

    def test_analyze_handles_fallback_when_satellite_unavailable(self):
        good_poly = {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[78.48, 17.38], [78.49, 17.38], [78.49, 17.39], [78.48, 17.39], [78.48, 17.38]]],
            },
        }
        res = client.post("/analyze", json={"geojson": good_poly, "crop_type": "Rice"})
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body["success"])
        # Either live satellite values or honest fallback empty fields
        self.assertIn("ndvi", body)
        self.assertIn("area_hectares", body)
        self.assertIn("total_credits", body)


if __name__ == "__main__":
    unittest.main()
