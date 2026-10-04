import unittest

from app.services.trust_engine import apply_fraud, decide_tier, farm_may_list, fpo_confirmed_result
from app.services.polygon_service import approximate_square, polygon_area_hectares, polygons_overlap


class TestTrustEngine(unittest.TestCase):
    def test_fpo_path(self):
        d = decide_tier(fpo_path=True)
        self.assertEqual(d["path"], "fpo")
        trust = apply_fraud(d, {})
        self.assertEqual(trust["status"], "PENDING")
        self.assertIsNone(trust["badge"])
        self.assertTrue(trust["credits_blocked"])

    def test_tier_1a_registry_geom(self):
        registry = {
            "found": True,
            "registry_geometry_available": True,
            "geojson": {"type": "Polygon", "coordinates": []},
            "owner_name": "Ramesh Kumar",
            "area_ha": 2.15,
        }
        d = decide_tier(
            fpo_path=False,
            survey_number="101/A",
            registry=registry,
            owner_name="Ramesh Kumar",
            claimed_area_ha=2.15,
        )
        self.assertEqual(d["tier"], "1A")
        self.assertEqual(d["badge"], "REGISTRY")

    def test_tier_1b_no_geom(self):
        registry = {
            "found": True,
            "registry_geometry_available": False,
            "geojson": None,
            "owner_name": "Ramesh Kumar",
            "area_ha": 2.15,
        }
        d = decide_tier(fpo_path=False, survey_number="101/A", registry=registry, owner_name="Ramesh Kumar")
        self.assertEqual(d["tier"], "1B")
        self.assertEqual(d["badge"], "REGISTRY_DOC")

    def test_tier_2_not_found(self):
        d = decide_tier(fpo_path=False, survey_number="999/Z", registry={"found": False}, owner_name="X")
        self.assertEqual(d["tier"], "2")
        self.assertEqual(d["badge"], "DOCUMENT")

    def test_fraud_strips_badge(self):
        d = decide_tier(fpo_path=False, survey_number="101/A", registry={"found": False})
        trust = apply_fraud(d, {"status": "FLAGGED", "risk": "HIGH", "failed_checks": ["exif_validation"]})
        self.assertEqual(trust["status"], "FLAGGED")
        self.assertIsNone(trust["badge"])
        self.assertFalse(trust["marketplace_eligible"])

    def test_fpo_confirm(self):
        r = fpo_confirmed_result()
        self.assertEqual(r["badge"], "FPO")
        self.assertTrue(r["marketplace_eligible"])

    def test_farm_may_list(self):
        ok, _ = farm_may_list({"status": "PENDING"})
        self.assertFalse(ok)
        ok, _ = farm_may_list({"status": "VERIFIED", "badge": "REGISTRY"})
        self.assertTrue(ok)

    def test_approximate_area(self):
        poly = approximate_square(17.97, 79.61, 2.15)
        area = polygon_area_hectares(poly)
        self.assertGreater(area, 1.5)
        self.assertLess(area, 2.8)
        self.assertTrue(polygons_overlap(poly, poly))


if __name__ == "__main__":
    unittest.main()
