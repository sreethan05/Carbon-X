"""Tests for the trust & transparency core: split engine, hash ledger,
credit engine (Stage 2), and Stage 1 crop verification.

Run: python -m unittest discover backend/tests -v   (from repo root)
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services import credit_engine, split_engine  # noqa: E402
from app.services import ledger as ledger_module  # noqa: E402
from app.services import certificate_pdf  # noqa: E402


class SplitEngineTests(unittest.TestCase):
    def test_four_way_split_exact_shares(self):
        split = split_engine.compute_split(1000.0, fpo_involved=True, fpo_name="Test FPO")
        self.assertEqual(split["model"], "4-way")
        self.assertEqual(split["farmer_amount_inr"], 700.0)
        self.assertEqual(split["fpo_amount_inr"], 50.0)
        self.assertEqual(split["platform_amount_inr"], 250.0)
        self.assertAlmostEqual(sum(l["amount_inr"] for l in split["lines"]), 1000.0, places=2)

    def test_three_way_split_when_no_fpo(self):
        split = split_engine.compute_split(1000.0, fpo_involved=False)
        self.assertEqual(split["model"], "3-way")
        self.assertEqual(split["farmer_amount_inr"], 700.0)
        self.assertEqual(split["fpo_amount_inr"], 0.0)
        self.assertEqual(split["platform_amount_inr"], 300.0)
        self.assertFalse(split["fpo_involved"])

    def test_paise_rounding_never_loses_a_rupee(self):
        # 70% and 5% of odd amounts floor; platform absorbs the residue.
        split = split_engine.compute_split(0.03, fpo_involved=True)
        total = sum(l["amount_inr"] for l in split["lines"])
        self.assertEqual(total, 0.03)

    def test_farmer_floor_never_diluted_by_rounding(self):
        # Farmer gets exactly floor(gross_paise * 0.70) — never a paise less.
        import math

        for gross in (1.0, 7.77, 10800.55, 0.07, 999999.99):
            gross_paise = int(round(gross * 100))
            expected_farmer = math.floor(gross_paise * 0.70) / 100
            split = split_engine.compute_split(gross, fpo_involved=True)
            self.assertEqual(split["farmer_amount_inr"], expected_farmer)
            self.assertAlmostEqual(
                split["farmer_amount_inr"] + split["fpo_amount_inr"] + split["platform_amount_inr"],
                round(gross, 2), places=2,
            )

    def test_zero_amount_is_safe(self):
        split = split_engine.compute_split(0, fpo_involved=True)
        self.assertEqual(split["farmer_amount_inr"], 0.0)
        self.assertEqual(len(split["lines"]), 3)

    def test_negative_gross_clamped_to_zero(self):
        split = split_engine.compute_split(-50.0, fpo_involved=True)
        self.assertEqual(split["gross_inr"], 0.0)
        self.assertEqual(split["farmer_amount_inr"], 0.0)
        self.assertEqual(split["fpo_amount_inr"], 0.0)
        self.assertEqual(split["platform_amount_inr"], 0.0)


class LedgerTests(unittest.TestCase):
    """Forced onto the local-file path (CARBONX_LEDGER_PATH sandbox + Supabase
    stubbed out) so tests are hermetic regardless of local credentials."""

    def setUp(self):
        self.tmp = os.path.join(os.path.dirname(__file__), "_test_ledger.json")
        os.environ["CARBONX_LEDGER_PATH"] = self.tmp
        ledger_module._PATH = self.tmp
        ledger_module._CHAINS = {}
        self._orig_sb = ledger_module._sb
        ledger_module._sb = lambda: None
        if os.path.exists(self.tmp):
            os.remove(self.tmp)

    def tearDown(self):
        ledger_module._sb = self._orig_sb
        if os.path.exists(self.tmp):
            os.remove(self.tmp)

    def _events(self, entity):
        return ledger_module.get_chain(entity)

    def test_chain_appends_and_verifies(self):
        e0 = ledger_module.append_event("farm-t", "ISSUE", {"n": 1})
        e1 = ledger_module.append_event("farm-t", "SALE", {"n": 2})
        self.assertEqual(e0["seq"], 0)
        self.assertEqual(e1["prev_hash"], e0["hash"])
        check = ledger_module.verify_chain("farm-t")
        self.assertTrue(check["valid"])
        self.assertEqual(check["length"], 2)

    def test_tampering_is_detected(self):
        ledger_module.append_event("farm-x", "ISSUE", {"amount": 10})
        ledger_module.append_event("farm-x", "SALE", {"amount": 20})
        # Mutate a stored payload in place, as a tamper would.
        ledger_module._CHAINS["farm-x"][0]["payload"]["amount"] = 999
        check = ledger_module.verify_chain("farm-x")
        self.assertFalse(check["valid"])
        self.assertEqual(check["broken_at"], 0)

    def test_genesis_is_idempotent(self):
        ledger_module.ensure_genesis("farm-g", {"snapshot": True})
        again = ledger_module.ensure_genesis("farm-g", {"snapshot": True})
        self.assertEqual(again["seq"], 0)
        self.assertEqual(len(ledger_module.get_chain("farm-g")), 1)

    def test_hash_is_deterministic(self):
        a = ledger_module.append_event("farm-d", "ISSUE", {"k": "v"})
        ledger_module._CHAINS["farm-d"] = []
        b = ledger_module.append_event("farm-d", "ISSUE", {"k": "v"})
        self.assertEqual(a["hash"], b["hash"])

    def test_sequence_continuity_tamper_detected(self):
        ledger_module.append_event("farm-seq", "ISSUE", {"k": 1})
        ledger_module.append_event("farm-seq", "SALE", {"k": 2})
        # Alter sequence number of second event
        ledger_module._CHAINS["farm-seq"][1]["seq"] = 99
        check = ledger_module.verify_chain("farm-seq")
        self.assertFalse(check["valid"])
        self.assertEqual(check["broken_at"], 99)

    def test_listener_subscribe_and_unsubscribe(self):
        received = []
        def on_event(ev):
            received.append(ev)

        ledger_module.subscribe("farm-sub", on_event)
        ev1 = ledger_module.append_event("farm-sub", "ISSUE", {"x": 10})
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0]["hash"], ev1["hash"])

        ledger_module.unsubscribe("farm-sub", on_event)
        ledger_module.append_event("farm-sub", "SALE", {"x": 20})
        self.assertEqual(len(received), 1, "Unsubscribed listener must not receive further events")

    def test_summary_structure(self):
        ledger_module.append_event("farm-sum", "ISSUE", {"credits": 50})
        ledger_module.append_event("farm-sum", "SALE", {"credits": 50})
        s = ledger_module.summary("farm-sum")
        self.assertEqual(s["events"], 2)
        self.assertTrue(s["verified"])
        self.assertIsNotNone(s["tail_hash"])
        self.assertEqual(s["types"], ["ISSUE", "SALE"])
        self.assertIsNotNone(s["first_ts"])
        self.assertIsNotNone(s["last_ts"])


class CreditEngineTests(unittest.TestCase):
    def test_five_steps_present_and_ordered(self):
        est = credit_engine.estimate_credits(2.0, "Rice", 0.78, quality_score=1.0)
        self.assertEqual([s["step"] for s in est["steps"]], [1, 2, 3, 4, 5])
        self.assertEqual(est["crop"], "Rice")

    def test_uncertainty_within_10_to_30(self):
        for score in (0.0, 0.25, 0.5, 0.75, 1.0):
            pct = credit_engine.uncertainty_pct(score)
            self.assertGreaterEqual(pct, 10.0)
            self.assertLessEqual(pct, 30.0)
        self.assertEqual(credit_engine.uncertainty_pct(1.0), 10.0)
        self.assertEqual(credit_engine.uncertainty_pct(0.0), 30.0)

    def test_uncertainty_deduction_reduces_credits(self):
        full = credit_engine.estimate_credits(2.0, "Rice", 0.78, quality_score=1.0)
        poor = credit_engine.estimate_credits(2.0, "Rice", 0.78, quality_score=0.2)
        self.assertGreater(full["credits_tco2e"], poor["credits_tco2e"])

    def test_determinism_same_inputs_same_output(self):
        a = credit_engine.estimate_credits(1.7, "Cotton", 0.66, quality_score=0.8)
        b = credit_engine.estimate_credits(1.7, "Cotton", 0.66, quality_score=0.8)
        self.assertEqual(a, b)

    def test_additionality_baseline_bounds_delta(self):
        high = credit_engine.estimate_credits(1.0, "Rice", 0.9, baseline_ndvi=0.5, quality_score=1.0)
        low = credit_engine.estimate_credits(1.0, "Rice", 0.9, baseline_ndvi=0.85, quality_score=1.0)
        self.assertGreater(high["credits_tco2e"], low["credits_tco2e"])

    def test_income_projection_brackets_expected(self):
        inc = credit_engine.income_projection(100, "REGISTRY")
        self.assertLess(inc["range_inr"]["min"], inc["expected_income_inr"])
        self.assertGreater(inc["range_inr"]["max"], inc["expected_income_inr"])
        self.assertEqual(inc["farmer_share_pct"], 70.0)

    def test_unknown_crop_uses_default_factor(self):
        est = credit_engine.estimate_credits(1.0, "Dragonfruit", 0.7, quality_score=1.0)
        self.assertEqual(est["crop"], "Mixed cropping")

    def test_pulses_crop_factor(self):
        est = credit_engine.estimate_credits(2.0, "Pulses", 0.65, quality_score=1.0)
        self.assertEqual(est["crop"], "Pulses")
        # Step 3 soil factor for Pulses is 0.30 tCO2e/ha
        soil_step = next(s for s in est["steps"] if s["step"] == 3)
        self.assertEqual(soil_step["value"], 0.30)

    def test_none_quality_score_is_handled_safely(self):
        est = credit_engine.estimate_credits(1.5, "Rice", 0.75, quality_score=None)
        self.assertIn("credits_tco2e", est)
        self.assertGreater(est["credits_tco2e"], 0)

    def test_malformed_model_quantiles_safely_falls_back_to_heuristic(self):
        est = credit_engine.estimate_credits(
            1.0, "Rice", 0.8,
            model_quantiles={"p10": None, "p50": None, "p90": None},
        )
        self.assertEqual(est["ci90_source"], "heuristic")
        self.assertGreater(est["ci90"]["high"], est["ci90"]["low"])

    def test_quick_scan_estimate_handles_none_values_and_caching(self):
        # features containing None values must not crash string formatting
        features = {"NDVI": 0.72, "SAVI": None, "B4": 0.08}
        res1 = credit_engine.quick_scan_estimate(2.5, "Cotton", 0.72, features=features)
        self.assertIn("credits_tco2e", res1)
        # Second call hits cache
        res2 = credit_engine.quick_scan_estimate(2.5, "Cotton", 0.72, features=features)
        self.assertEqual(res1["credits_tco2e"], res2["credits_tco2e"])

    def test_credit_split_non_negative(self):
        split = credit_engine.credit_split(-10.0, -50.0)
        self.assertEqual(split["carbon_credits"], 0.0)
        self.assertEqual(split["biodiversity_credits"], 0.0)
        self.assertEqual(split["total_credits"], 0.0)


class Stage1VerificationTests(unittest.TestCase):
    def test_match_inside_window(self):
        r = credit_engine.stage1_verification("Rice", 0.78)
        self.assertEqual(r["status"], "MATCH")
        self.assertTrue(r["match"])

    def test_mismatch_outside_window(self):
        r = credit_engine.stage1_verification("Rice", 0.36)
        self.assertEqual(r["status"], "MISMATCH")
        self.assertFalse(r["match"])
        self.assertIn("FPO/KVK review", r["reason"])

    def test_boundaries_are_inclusive(self):
        lo, hi = credit_engine._CROP_NDVI_WINDOWS["rice"]
        self.assertEqual(credit_engine.stage1_verification("Rice", lo)["status"], "MATCH")
        self.assertEqual(credit_engine.stage1_verification("Rice", hi)["status"], "MATCH")

    def test_unknown_crop_unreviewed_not_rejected(self):
        r = credit_engine.stage1_verification("Dragonfruit", 0.2)
        self.assertEqual(r["status"], "UNREVIEWED")
        self.assertTrue(r["match"])

    def test_crop_windows_for_key_crops(self):
        # Verify Paddy, Cotton, Maize, Pulses, Sugarcane bounds
        crops_to_check = {
            "Paddy": (0.55, 0.95),
            "Cotton": (0.40, 0.90),
            "Maize": (0.45, 0.92),
            "Pulses": (0.35, 0.85),
            "Sugarcane": (0.60, 0.95),
        }
        for crop, (lo, hi) in crops_to_check.items():
            mid = round((lo + hi) / 2, 2)
            match_res = credit_engine.stage1_verification(crop, mid)
            self.assertEqual(match_res["status"], "MATCH", f"Failed match for {crop} at {mid}")
            self.assertEqual(match_res["expected_range"], [lo, hi])

            mismatch_res = credit_engine.stage1_verification(crop, lo - 0.1)
            self.assertEqual(mismatch_res["status"], "MISMATCH", f"Failed mismatch for {crop}")

    def test_crop_token_matching(self):
        # Real-world declarations with qualifiers should match their base crop window
        res = credit_engine.stage1_verification("Paddy (Kharif)", 0.75)
        self.assertEqual(res["status"], "MATCH")
        self.assertEqual(res["crop"], "Paddy")

        res_cotton = credit_engine.stage1_verification("Bt Cotton", 0.65)
        self.assertEqual(res_cotton["status"], "MATCH")
        self.assertEqual(res_cotton["crop"], "Cotton")

class CertificatePdfTests(unittest.TestCase):
    def setUp(self):
        certificate_pdf.clear_certificate_pdf_cache()

    def test_pdf_generation_retired(self):
        cert = {
            "id": "CX-2026-CERT-A1B2C3D4",
            "buyer": "Telangana Sustainable Agro Pvt Ltd",
            "farmer_name": "Ramesh Kumar",
            "crop": "Paddy",
            "volume": 25.5,
            "value": 38250.0,
            "location": "Siddipet, Telangana",
            "issued_date": "2026-10-15",
            "retired_date": "2026-10-16",
            "status": "RETIRED",
            "batch_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        }
        pdf = certificate_pdf.render_certificate_pdf(cert)
        self.assertIsInstance(pdf, bytes)
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertGreater(len(pdf), 2000)

    def test_pdf_generation_escrow(self):
        cert = {
            "id": "CX-2026-CERT-ESCROW01",
            "buyer": "Global Green Corp",
            "farmer_name": "Sita Devi",
            "crop": "Cotton",
            "volume": 10.0,
            "value": 15000.0,
            "location": "Warangal, Telangana",
            "issued_date": "2026-10-15",
            "status": "HELD_IN_ESCROW",
            "batch_hash": "7f83b1657ff1fc53b92dc18148a1d65dfc2d4b1fa3d677284addd200126d9069",
        }
        pdf = certificate_pdf.render_certificate_pdf(cert)
        self.assertIsInstance(pdf, bytes)
        self.assertTrue(pdf.startswith(b"%PDF"))

    def test_pdf_handles_very_long_fields(self):
        cert = {
            "id": "CX-2026-CERT-LONG0001",
            "buyer": "A" * 200,
            "farmer_name": "B" * 200,
            "crop": "C" * 150,
            "volume": 999999.99,
            "value": 999999999.0,
            "location": "D" * 300,
            "issued_date": "2026-10-15",
            "status": "RETIRED",
            "batch_hash": "a" * 64,
        }
        # Must not raise an error even with extremely long strings
        pdf = certificate_pdf.render_certificate_pdf(cert)
        self.assertTrue(pdf.startswith(b"%PDF"))

    def test_lru_cache_and_invalidation(self):
        cert = {
            "id": "CX-2026-CERT-CACHE01",
            "buyer": "Test Buyer",
            "farmer_name": "Test Farmer",
            "crop": "Rice",
            "volume": 5.0,
            "value": 5000.0,
            "location": "Hyderabad",
            "issued_date": "2026-10-15",
            "status": "RETIRED",
            "batch_hash": "b" * 64,
        }
        pdf1 = certificate_pdf.render_certificate_pdf(cert)
        # Direct cache hit
        cached = certificate_pdf.get_cached_certificate_pdf("CX-2026-CERT-CACHE01")
        self.assertEqual(cached, pdf1)

        # Invalidation
        certificate_pdf.invalidate_certificate_pdf("CX-2026-CERT-CACHE01")
        self.assertIsNone(certificate_pdf.get_cached_certificate_pdf("CX-2026-CERT-CACHE01"))

    def test_lru_eviction(self):
        cache = certificate_pdf.CertificatePdfCache(maxsize=3)
        cache.set("c1", b"pdf1")
        cache.set("c2", b"pdf2")
        cache.set("c3", b"pdf3")
        self.assertEqual(len(cache), 3)

        # Access c1 to make c2 the LRU
        self.assertEqual(cache.get("c1"), b"pdf1")

        # Insert c4, should evict c2
        cache.set("c4", b"pdf4")
        self.assertEqual(len(cache), 3)
        self.assertIsNone(cache.get("c2"), "c2 should have been evicted")
        self.assertIsNotNone(cache.get("c1"), "c1 was recently accessed and should remain")
        self.assertIsNotNone(cache.get("c3"))
        self.assertIsNotNone(cache.get("c4"))


if __name__ == "__main__":
    unittest.main()
