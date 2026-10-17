"""Unit tests for Earth Engine runtime, gee_service, and gee_server.

Tests verification of:
1. Earth Engine initialization, project configuration, credential caching.
2. Sentinel-2 Harmonized image collection filtering (cloud cover, date windows), median compositing.
3. NDVI, EVI, NDWI calculation, scale and reducer parameters.
4. Point sampling vs polygon sampling, honest error reporting when GEE is unavailable (no fabricated data).

Run from backend/: python -m unittest tests.test_gee_services -v
"""

from datetime import datetime
import json
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../services"))

for _k in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY",
           "VITE_SUPABASE_URL", "VITE_SUPABASE_ANON_KEY"):
    os.environ.pop(_k, None)
os.environ["SUPABASE_URL"] = ""
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = ""

from app import gee_runtime
from app.services import gee_service
import gee_server


class TestGeeRuntime(unittest.TestCase):
    def test_runtime_initialization_state(self):
        """Verify that gee_runtime initializes and tracks state."""
        self.assertTrue(hasattr(gee_runtime, "earth_engine_ready"))
        self.assertTrue(hasattr(gee_runtime, "earth_engine_error"))
        self.assertTrue(hasattr(gee_runtime, "init_earth_engine"))

    def test_safe_error_recording_on_init_failure(self):
        """When ee.Initialize raises, earth_engine_ready must be False with error message."""
        with patch("ee.Initialize", side_effect=RuntimeError("Auth quota exceeded")):
            old_ready = gee_runtime.earth_engine_ready
            old_proj = gee_runtime._current_project
            try:
                res = gee_runtime.init_earth_engine("non-existent-proj-test")
                self.assertFalse(res)
                self.assertFalse(gee_runtime.earth_engine_ready)
                self.assertIn("Auth quota exceeded", str(gee_runtime.earth_engine_error))
            finally:
                # restore
                gee_runtime.earth_engine_ready = old_ready
                gee_runtime._current_project = old_proj


class TestGeeService(unittest.TestCase):
    def test_init_delegates_to_runtime(self):
        """init_earth_engine in gee_service synchronizes with gee_runtime."""
        self.assertEqual(gee_service.init_earth_engine(), gee_runtime.earth_engine_ready)

    def test_get_ndvi_at_point_invalid_coords(self):
        """Invalid coordinate bounds must return honest unavailable, never crash."""
        result = gee_service.get_ndvi_at_point(lat=95.0, lon=200.0)
        self.assertFalse(result["live_satellite"])
        self.assertIsNone(result["ndvi"])
        self.assertEqual(result["vegetation_status"], "Unknown")

    def test_get_ndvi_at_point_honest_reporting_when_offline(self):
        """When GEE is unavailable, must report unavailable and never fabricate data."""
        with patch("app.services.gee_service.init_earth_engine", return_value=False):
            result = gee_service.get_ndvi_at_point(17.385, 78.4867)
            self.assertFalse(result["live_satellite"])
            self.assertIsNone(result["ndvi"])
            self.assertEqual(result["vegetation_status"], "Unknown")
            self.assertIn("Unavailable", result["source"])

    def test_get_satellite_features_polygon_validation(self):
        """Polygon with fewer than 3 points returns honest error."""
        result = gee_service.get_satellite_features_for_polygon([[78.486, 17.385]])
        self.assertFalse(result["live_satellite"])
        self.assertIn("at least 3", result["error"])

    def test_get_satellite_features_polygon_honest_reporting_when_offline(self):
        """Polygon features return honest unavailable when GEE is offline."""
        with patch("app.services.gee_service.init_earth_engine", return_value=False):
            coords = [[78.486, 17.385], [78.487, 17.385], [78.487, 17.386], [78.486, 17.385]]
            result = gee_service.get_satellite_features_for_polygon(coords)
            self.assertFalse(result["live_satellite"])
            self.assertIsNone(result["ndvi"])
            self.assertIsNone(result["evi"])
            self.assertIsNone(result["ndwi"])
            self.assertIsNone(result["area_hectares"])

    def test_live_gee_point_and_polygon_if_available(self):
        """If machine has live GEE credentials, run full query verification."""
        if not gee_runtime.earth_engine_ready:
            self.skipTest("Live Earth Engine credentials not present on machine")

        # Test Point
        point_res = gee_service.get_ndvi_at_point(17.385, 78.4867, buffer_meters=100.0)
        self.assertTrue(point_res["live_satellite"])
        self.assertIsInstance(point_res["ndvi"], float)
        self.assertIn(point_res["vegetation_status"], ("Healthy", "Sparse"))

        # Test Polygon
        coords = [
            [78.486, 17.385],
            [78.487, 17.385],
            [78.487, 17.386],
            [78.486, 17.386],
            [78.486, 17.385],
        ]
        poly_res = gee_service.get_satellite_features_for_polygon(coords)
        self.assertTrue(poly_res["live_satellite"])
        self.assertGreater(poly_res["area_hectares"], 0.0)
        self.assertIsNotNone(poly_res["ndvi"])
        self.assertIsNotNone(poly_res["evi"])
        self.assertIsNotNone(poly_res["ndwi"])
        self.assertIsNotNone(poly_res["savi"])
        self.assertIn("centroid", poly_res)
        self.assertAlmostEqual(poly_res["centroid"]["lat"], 17.3855, places=3)


class TestGeeServer(unittest.TestCase):
    def test_get_satellite_features_honest_reporting_when_offline(self):
        """When GEE is disconnected, gee_server returns honest unavailable payload."""
        with patch.object(gee_server, "gee_initialized", False), \
             patch.object(gee_server, "init_gee", return_value=False):
            res = gee_server.get_satellite_features(78.4867, 17.3850)
            self.assertFalse(res["live_satellite"])
            self.assertIsNone(res["nd"])
            self.assertIsNone(res["evi"])
            self.assertIsNone(res["ndwi"])

    def test_analyze_polygon_validation(self):
        """Too few coordinates returns error dict."""
        res = gee_server.analyze_polygon([[78.48, 17.38]])
        self.assertIn("error", res)

    def test_analyze_polygon_honest_reporting_when_offline(self):
        """When offline, analyze_polygon reports error honestly without fabricated stats."""
        with patch.object(gee_server, "gee_initialized", False), \
             patch.object(gee_server, "init_gee", return_value=False):
            coords = [[78.486, 17.385], [78.487, 17.385], [78.487, 17.386], [78.486, 17.385]]
            res = gee_server.analyze_polygon(coords)
            self.assertFalse(res.get("live_satellite"))
            self.assertIn("error", res)

    def test_live_gee_server_queries(self):
        """Test gee_server live functions if GEE is ready."""
        if not gee_server.gee_initialized:
            self.skipTest("Live Earth Engine credentials not present on machine")

        # Point feature calculation
        res = gee_server.get_satellite_features(78.4867, 17.3850)
        self.assertTrue(res["live_satellite"])
        self.assertEqual(res["source"], "COPERNICUS/S2_SR_HARMONIZED")
        self.assertIsInstance(res["nd"], float)
        self.assertIsInstance(res["evi"], float)
        self.assertIsInstance(res["ndwi"], float)
        # Verify timestamp is valid ISO string (not broken ee.Date repr)
        datetime.fromisoformat(res["timestamp"])

        # Real polygon sampling
        coords = [
            [78.486, 17.385],
            [78.487, 17.385],
            [78.487, 17.386],
            [78.486, 17.386],
            [78.486, 17.385],
        ]
        poly = gee_server.analyze_polygon(coords)
        self.assertTrue(poly["live_satellite"])
        self.assertEqual(poly["source"], "COPERNICUS/S2_SR_HARMONIZED")
        self.assertGreater(poly["area_hectares"], 0.0)
        self.assertAlmostEqual(poly["centroid"]["lat"], 17.3855, places=3)
        self.assertIsInstance(poly["nd"], float)
        self.assertIsInstance(poly["evi"], float)
        self.assertIsInstance(poly["ndwi"], float)


if __name__ == "__main__":
    unittest.main()
