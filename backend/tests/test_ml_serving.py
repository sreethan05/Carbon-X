"""Tests for the ML serving contract (no fabricated features, honest labels).

Run from backend/: python -m unittest tests.test_ml_serving -v
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services import ml_service  # noqa: E402


def _realistic_features(ndvi=0.62):
    """A feature vector in the training distribution (test input only —
    production gets these from Earth Engine, never synthesised)."""
    return {
        "NDVI": ndvi,
        "NDWI": -0.18,
        "SAVI": 0.42,
        "NDVI_STD": 0.09,
        "B4": 1200.0,
        "B8": 3100.0,
        "B11": 2200.0,
        "B8_VAR": 620000.0,
        # Additional features for v3 (red-edge, SAR, GEDI, etc.)
        "NDRE": 0.45,
        "IRECI": 0.38,
        "CIre": 0.22,
        "KHARIF_NDVI": 0.65,
        "RABI_NDVI": 0.55,
        "SEASONAL_CONTRAST": 0.10,
        "NDVI_RANGE": 0.25,
        "NDVI_AMPLITUDE": 0.30,
        "NDVI_INTEGRAL": 120.0,
        "SOS_DOY": 150.0,
        "EOS_DOY": 300.0,
        "ELEVATION": 400.0,
        "SLOPE": 2.5,
        "ASPECT": 180.0,
        "S1_VV": -12.0,
        "S1_VH": -18.0,
        "S1_VV_VH_RATIO": 0.67,
        "S1_VV_STD": 1.5,
        "GEDI_RH98": 25.0,
        "GEDI_AGBD": 150.0,
        "SOILGRIDS_SOC_MEAN": 15.0,
        "SOILGRIDS_SOC_STOCK": 50.0,
        "SOILGRIDS_SOC_Q05": 10.0,
        "SOILGRIDS_SOC_Q50": 15.0,
        "SOILGRIDS_SOC_Q95": 20.0,
    }


class MLServingTests(unittest.TestCase):
    def test_model_status_endpoint(self):
        """Test that get_model_status returns expected structure."""
        status = ml_service.get_model_status()
        self.assertIn("models_loaded", status)
        self.assertIn("biodiversity_serving", status)
        self.assertIn("soc_serving", status)
        self.assertIn("bio_quantiles_loaded", status)
        self.assertIn("soc_quantiles_loaded", status)
        self.assertIn("quality_gate_threshold", status)

    def test_quality_gate_respected(self):
        """The v2 honesty model scored below the gate, so serving must use
        the labelled heuristic EVEN with real features supplied — the gate,
        not optimism, decides what serves."""
        ml_service._load_models()
        out = ml_service.predict_biodiversity(0.62, features=_realistic_features())
        # Since model is below quality gate, should fall back to heuristic
        self.assertIn("Heuristic", out["source"])
        self.assertEqual(out["biodiversity_score"], ml_service._heuristic_score(0.62))

    def test_no_features_means_heuristic_never_model(self):
        out = ml_service.predict_biodiversity(0.62, features=None)
        self.assertIn("Heuristic", out["source"])
        self.assertEqual(out["biodiversity_score"], ml_service._heuristic_score(0.62))

    def test_partial_features_fall_back(self):
        out = ml_service.predict_biodiversity(0.62, features={"NDVI": 0.62})  # missing required features
        self.assertIn("Heuristic", out["source"])

    def test_score_sane_and_status_label(self):
        out = ml_service.predict_biodiversity(0.62, features=_realistic_features())
        self.assertIn(out["status"], ("Low", "Moderate", "Good", "Excellent"))
        self.assertIsInstance(out["biodiversity_score"], float)
        self.assertGreaterEqual(out["biodiversity_score"], 0)
        self.assertLessEqual(out["biodiversity_score"], 100)

    def test_ml_source_present(self):
        """Every prediction must carry ml_source label."""
        out = ml_service.predict_biodiversity(0.62, features=_realistic_features())
        self.assertIn("ml_source", out)
        self.assertIsInstance(out["ml_source"], str)

    def test_quantiles_returned_when_model_serves(self):
        """If model serves (quality gate passed), quantiles should be in response."""
        # Force load to check structure
        ml_service._load_models()
        out = ml_service.predict_biodiversity(0.62, features=_realistic_features())
        # Currently falls back to heuristic, so no quantiles
        # When model serves, quantiles dict should be present
        if "quantiles" in out:
            self.assertIn("log_richness_p10", out["quantiles"])
            self.assertIn("log_richness_p50", out["quantiles"])
            self.assertIn("log_richness_p90", out["quantiles"])

    def test_soc_prediction_structure(self):
        """SOC prediction should return proper structure."""
        ml_service._load_models()
        out = ml_service.predict_soc(_realistic_features())
        self.assertIn("soc_tco2e_ha", out)
        self.assertIn("p10", out)
        self.assertIn("p50", out)
        self.assertIn("p90", out)
        self.assertIn("ml_source", out)


if __name__ == "__main__":
    unittest.main()