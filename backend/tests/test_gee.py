"""Unit tests for the Google Earth Engine runtime and service.

Hermetic: mocks Earth Engine API (`ee`) calls so tests run without network access
or Google Cloud credentials. Validates initialization, point queries, polygon
feature extraction, boundary validations, vegetation health classification,
and honest fallbacks (never fabricates satellite data).

Run from backend/: python -m unittest tests.test_gee -v
"""
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Hermetic environment: prevent live DB or credential leakage
for _k in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY",
           "VITE_SUPABASE_URL", "VITE_SUPABASE_ANON_KEY"):
    os.environ.pop(_k, None)
os.environ["SUPABASE_URL"] = ""
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = ""

from app import gee_runtime
from app.services import gee_service


class GeeRuntimeTests(unittest.TestCase):
    def setUp(self):
        self._orig_ready = gee_runtime.earth_engine_ready
        self._orig_error = gee_runtime.earth_engine_error
        self._orig_proj = gee_runtime._current_project

    def tearDown(self):
        gee_runtime.earth_engine_ready = self._orig_ready
        gee_runtime.earth_engine_error = self._orig_error
        gee_runtime._current_project = self._orig_proj

    def test_init_success_updates_runtime_state(self):
        mock_ee = MagicMock()
        with patch.dict("sys.modules", {"ee": mock_ee}):
            result = gee_runtime.init_earth_engine(project_id="test-proj-ok")
            self.assertTrue(result)
            self.assertTrue(gee_runtime.earth_engine_ready)
            self.assertIsNone(gee_runtime.earth_engine_error)
            self.assertEqual(gee_runtime._current_project, "test-proj-ok")
            mock_ee.Initialize.assert_called_with(project="test-proj-ok")

    def test_init_idempotent_returns_true_without_reinit(self):
        gee_runtime.earth_engine_ready = True
        gee_runtime._current_project = "cached-project"
        mock_ee = MagicMock()
        with patch.dict("sys.modules", {"ee": mock_ee}):
            result = gee_runtime.init_earth_engine(project_id="cached-project")
            self.assertTrue(result)
            mock_ee.Initialize.assert_not_called()

    def test_init_failure_sets_error_and_returns_false(self):
        mock_ee = MagicMock()
        mock_ee.Initialize.side_effect = RuntimeError("GEE auth token expired")
        with patch.dict("sys.modules", {"ee": mock_ee}):
            result = gee_runtime.init_earth_engine(project_id="broken-proj")
            self.assertFalse(result)
            self.assertFalse(gee_runtime.earth_engine_ready)
            self.assertIn("GEE auth token expired", str(gee_runtime.earth_engine_error))


class GeePointQueryTests(unittest.TestCase):
    def test_invalid_coordinates_rejected_immediately(self):
        # Lat out of range
        res = gee_service.get_ndvi_at_point(95.0, 78.0)
        self.assertFalse(res["live_satellite"])
        self.assertIsNone(res["ndvi"])
        self.assertEqual(res["source"], "Invalid coordinates")

        # Lon out of range
        res2 = gee_service.get_ndvi_at_point(17.0, -190.0)
        self.assertFalse(res2["live_satellite"])
        self.assertIsNone(res2["ndvi"])
        self.assertEqual(res2["source"], "Invalid coordinates")

    def test_offline_fallback_never_fabricates_values(self):
        with patch.object(gee_service, "init_earth_engine", return_value=False):
            res = gee_service.get_ndvi_at_point(17.385, 78.486)
            self.assertFalse(res["live_satellite"])
            self.assertIsNone(res["ndvi"])
            self.assertEqual(res["vegetation_status"], "Unknown")
            self.assertIn("Unavailable", res["source"])

    def test_live_point_query_healthy_vegetation(self):
        mock_ee = MagicMock()
        # Mock Point buffer and reduceRegion return value of 0.65 (Healthy)
        mock_point = MagicMock()
        mock_ee.Geometry.Point.return_value = mock_point
        mock_point.buffer.return_value = mock_point

        mock_image = MagicMock()
        mock_collection = MagicMock()
        mock_ee.ImageCollection.return_value = mock_collection
        mock_collection.filterBounds.return_value = mock_collection
        mock_collection.filterDate.return_value = mock_collection
        mock_collection.filter.return_value = mock_collection
        mock_collection.size.return_value.gt.return_value = True

        mock_coll_inst = MagicMock()
        mock_ee.ImageCollection.side_effect = [mock_collection, mock_coll_inst]
        mock_coll_inst.median.return_value = mock_image

        mock_ndvi = MagicMock()
        mock_image.normalizedDifference.return_value = mock_ndvi
        mock_ndvi.rename.return_value = mock_ndvi
        mock_ndvi.reduceRegion.return_value.get.return_value.getInfo.return_value = 0.652

        with patch.object(gee_service, "init_earth_engine", return_value=True), \
             patch.dict("sys.modules", {"ee": mock_ee}):
            res = gee_service.get_ndvi_at_point(17.25, 79.15)
            self.assertTrue(res["live_satellite"])
            self.assertEqual(res["ndvi"], 0.652)
            self.assertEqual(res["vegetation_status"], "Healthy")
            self.assertIn("Sentinel-2", res["source"])

    def test_live_point_query_sparse_vegetation(self):
        mock_ee = MagicMock()
        mock_point = MagicMock()
        mock_ee.Geometry.Point.return_value = mock_point
        mock_point.buffer.return_value = mock_point

        mock_image = MagicMock()
        mock_coll = MagicMock()
        mock_ee.ImageCollection.side_effect = [mock_coll, mock_coll]
        mock_coll.filterBounds.return_value = mock_coll
        mock_coll.filterDate.return_value = mock_coll
        mock_coll.filter.return_value = mock_coll
        mock_coll.median.return_value = mock_image

        mock_ndvi = MagicMock()
        mock_image.normalizedDifference.return_value = mock_ndvi
        mock_ndvi.rename.return_value = mock_ndvi
        mock_ndvi.reduceRegion.return_value.get.return_value.getInfo.return_value = 0.185

        with patch.object(gee_service, "init_earth_engine", return_value=True), \
             patch.dict("sys.modules", {"ee": mock_ee}):
            res = gee_service.get_ndvi_at_point(17.25, 79.15)
            self.assertTrue(res["live_satellite"])
            self.assertEqual(res["ndvi"], 0.185)
            self.assertEqual(res["vegetation_status"], "Sparse")

    def test_live_point_query_null_ndvi_falls_back(self):
        mock_ee = MagicMock()
        mock_point = MagicMock()
        mock_ee.Geometry.Point.return_value = mock_point
        mock_point.buffer.return_value = mock_point

        mock_image = MagicMock()
        mock_coll = MagicMock()
        mock_ee.ImageCollection.side_effect = [mock_coll, mock_coll]
        mock_coll.filterBounds.return_value = mock_coll
        mock_coll.filterDate.return_value = mock_coll
        mock_coll.filter.return_value = mock_coll
        mock_coll.median.return_value = mock_image

        mock_ndvi = MagicMock()
        mock_image.normalizedDifference.return_value = mock_ndvi
        mock_ndvi.rename.return_value = mock_ndvi
        mock_ndvi.reduceRegion.return_value.get.return_value.getInfo.return_value = None

        with patch.object(gee_service, "init_earth_engine", return_value=True), \
             patch.dict("sys.modules", {"ee": mock_ee}):
            res = gee_service.get_ndvi_at_point(17.25, 79.15)
            self.assertFalse(res["live_satellite"])
            self.assertIsNone(res["ndvi"])
            self.assertEqual(res["vegetation_status"], "Unknown")

    def test_live_point_query_exception_handled_safely(self):
        mock_ee = MagicMock()
        mock_ee.Geometry.Point.side_effect = RuntimeError("GEE internal error")
        with patch.object(gee_service, "init_earth_engine", return_value=True), \
             patch.dict("sys.modules", {"ee": mock_ee}):
            res = gee_service.get_ndvi_at_point(17.25, 79.15)
            self.assertFalse(res["live_satellite"])
            self.assertIsNone(res["ndvi"])
            self.assertEqual(res["vegetation_status"], "Unknown")


class GeeFeaturesAtPointTests(unittest.TestCase):
    def test_invalid_coords(self):
        res = gee_service.get_satellite_features_at_point(91.0, 0.0)
        self.assertFalse(res["live_satellite"])
        self.assertIn("Invalid", res["source"])

    def test_offline_returns_none_indices(self):
        with patch.object(gee_service, "init_earth_engine", return_value=False):
            res = gee_service.get_satellite_features_at_point(17.25, 79.15)
            self.assertFalse(res["live_satellite"])
            self.assertIsNone(res["ndvi"])
            self.assertIsNone(res["evi"])
            self.assertIsNone(res["ndwi"])
            self.assertIsNone(res["savi"])

    def test_successful_features_extraction(self):
        mock_ee = MagicMock()
        mock_point = MagicMock()
        mock_ee.Geometry.Point.return_value = mock_point
        mock_point.buffer.return_value = mock_point

        mock_image = MagicMock()
        mock_coll = MagicMock()
        mock_ee.ImageCollection.side_effect = [mock_coll, mock_coll]
        mock_coll.filterBounds.return_value = mock_coll
        mock_coll.filterDate.return_value = mock_coll
        mock_coll.filter.return_value = mock_coll
        mock_coll.median.return_value = mock_image

        mock_indexed = MagicMock()
        mock_image.addBands.return_value = mock_indexed
        mock_indexed.select.return_value.reduceRegion.return_value.getInfo.return_value = {
            "NDVI_mean": 0.582,
            "NDVI_min": 0.410,
            "NDVI_max": 0.690,
            "EVI_mean": 0.421,
            "NDWI_mean": -0.150,
            "SAVI_mean": 0.380,
        }

        with patch.object(gee_service, "init_earth_engine", return_value=True), \
             patch.dict("sys.modules", {"ee": mock_ee}):
            res = gee_service.get_satellite_features_at_point(17.25, 79.15)
            self.assertTrue(res["live_satellite"])
            self.assertEqual(res["ndvi"], 0.582)
            self.assertEqual(res["ndvi_min"], 0.410)
            self.assertEqual(res["ndvi_max"], 0.690)
            self.assertEqual(res["evi"], 0.421)
            self.assertEqual(res["ndwi"], -0.150)
            self.assertEqual(res["savi"], 0.380)


class GeePolygonQueryTests(unittest.TestCase):
    def test_invalid_polygon_rejected(self):
        # Fewer than 3 points
        res = gee_service.get_satellite_features_for_polygon([[79.15, 17.25], [79.16, 17.25]])
        self.assertFalse(res["live_satellite"])
        self.assertIn("at least 3 coordinates", res["error"])

        # Bad structure
        res2 = gee_service.get_satellite_features_for_polygon({"bad": "geom"})
        self.assertFalse(res2["live_satellite"])

    def test_offline_polygon_returns_unavailable(self):
        polygon = [[79.15, 17.25], [79.16, 17.25], [79.16, 17.26], [79.15, 17.26], [79.15, 17.25]]
        with patch.object(gee_service, "init_earth_engine", return_value=False):
            res = gee_service.get_satellite_features_for_polygon(polygon)
            self.assertFalse(res["live_satellite"])
            self.assertIsNone(res["area_hectares"])
            self.assertIsNone(res["ndvi"])
            self.assertEqual(res["vegetation_status"], "Unknown")

    def test_successful_polygon_extraction(self):
        polygon = [[79.15, 17.25], [79.16, 17.25], [79.16, 17.26], [79.15, 17.26]]  # unclosed ring
        mock_ee = MagicMock()
        mock_poly = MagicMock()
        mock_ee.Geometry.Polygon.return_value = mock_poly
        mock_poly.area.return_value.getInfo.return_value = 245000.0  # 24.5 ha
        mock_poly.centroid.return_value.coordinates.return_value.getInfo.return_value = [79.155, 17.255]

        mock_image = MagicMock()
        mock_coll = MagicMock()
        mock_ee.ImageCollection.side_effect = [mock_coll, mock_coll]
        mock_coll.filterBounds.return_value = mock_coll
        mock_coll.filterDate.return_value = mock_coll
        mock_coll.filter.return_value = mock_coll
        mock_coll.median.return_value = mock_image

        mock_indexed = MagicMock()
        mock_image.addBands.return_value = mock_indexed
        mock_indexed.select.return_value.reduceRegion.return_value.getInfo.return_value = {
            "NDVI_mean": 0.710,
            "NDVI_min": 0.550,
            "NDVI_max": 0.820,
            "EVI_mean": 0.510,
            "NDWI_mean": -0.080,
            "SAVI_mean": 0.440,
        }

        with patch.object(gee_service, "init_earth_engine", return_value=True), \
             patch.dict("sys.modules", {"ee": mock_ee}):
            res = gee_service.get_satellite_features_for_polygon(polygon)
            self.assertTrue(res["live_satellite"])
            self.assertEqual(res["area_hectares"], 24.5)
            self.assertEqual(res["centroid"], {"lat": 17.255, "lon": 79.155})
            self.assertEqual(res["ndvi"], 0.710)
            self.assertEqual(res["vegetation_status"], "Healthy")


if __name__ == "__main__":
    unittest.main()
