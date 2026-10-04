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
    }


@unittest.skipUnless(
    os.path.exists(os.path.join(ml_service.BASE_DIR, "ml", "models", "biodiversity_model.pkl")),
    "model artifacts not present",
)
class MLServingTests(unittest.TestCase):
    def test_artifacts_load(self):
        self.assertTrue(ml_service._load_models())
        self.assertIsNotNone(ml_service._model)

    def test_quality_gate_respected(self):
        """The v2 honesty model scored below the gate, so serving must use
        the labelled heuristic EVEN with real features supplied — the gate,
        not optimism, decides what serves."""
        ml_service._load_models()
        out = ml_service.predict_biodiversity(0.62, features=_realistic_features())
        card_path = os.path.join(ml_service.BASE_DIR, "ml", "models", "model_card.json")
        import json
        with open(card_path, encoding="utf-8") as fh:
            test_r2 = json.load(fh).get("test_r2", -9)
        if test_r2 < ml_service._MIN_SERVING_TEST_R2:
            self.assertIn("Heuristic", out["source"])
        else:
            self.assertIn("real Sentinel-2 features", out["source"])
        self.assertGreaterEqual(out["biodiversity_score"], 0)
        self.assertLessEqual(out["biodiversity_score"], 100)

    def test_no_features_means_heuristic_never_model(self):
        out = ml_service.predict_biodiversity(0.62, features=None)
        self.assertIn("Heuristic", out["source"])
        self.assertEqual(out["biodiversity_score"], ml_service._heuristic_score(0.62))

    def test_partial_features_fall_back(self):
        out = ml_service.predict_biodiversity(0.62, features={"NDVI": 0.62})  # missing 7
        self.assertIn("Heuristic", out["source"])

    def test_score_sane_and_status_label(self):
        out = ml_service.predict_biodiversity(0.62, features=_realistic_features())
        self.assertIn(out["status"], ("Low", "Moderate", "Good", "Excellent"))
        self.assertIsInstance(out["biodiversity_score"], float)


if __name__ == "__main__":
    unittest.main()
