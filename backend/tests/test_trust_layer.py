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


if __name__ == "__main__":
    unittest.main()
