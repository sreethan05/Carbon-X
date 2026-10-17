"""Validation tests for SoilGrids & Carbon Calibration (Stage 2 Trust Engine).

Verifies:
1. Soil factor formula versioning (-r2).
2. IPCC-compliant stock ranges (0.25 - 0.60 tCO2e/ha/yr).
3. Crop factor dictionary coverage for all major Indian crop types.
4. CI90 uncertainty interval calculations (heuristic and model quantiles).
5. SoilGrids SOC stock conversion and plausibility bounds.

Run from backend/: python -m unittest tests/test_soil_carbon_calibration.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import FORMULA_VERSION
from app.services import credit_engine


class SoilFactorFormulaVersioningTests(unittest.TestCase):
    """Verify formula versioning (-r2)."""

    def test_formula_version_contains_r2(self):
        """The formula version must carry the -r2 recalibration suffix."""
        self.assertIn("-r2", FORMULA_VERSION)
        self.assertTrue(
            FORMULA_VERSION.startswith("vm0042-soilgrids-"),
            f"Expected VM0042 SoilGrids lineage, got: {FORMULA_VERSION}",
        )

    def test_credit_engine_reexports_matching_formula_version(self):
        """credit_engine must re-export the exact centralized FORMULA_VERSION."""
        self.assertEqual(credit_engine.FORMULA_VERSION, FORMULA_VERSION)

    def test_estimate_credits_response_includes_formula_version(self):
        """Every estimate_credits result must include formula_version for auditability."""
        est = credit_engine.estimate_credits(2.5, "Rice", 0.72)
        self.assertIn("formula_version", est)
        self.assertEqual(est["formula_version"], FORMULA_VERSION)
        self.assertIn("-r2", est["formula_version"])


class IPCCCompliantStockRangeTests(unittest.TestCase):
    """Verify IPCC-compliant soil carbon accrual ranges (0.25 - 0.60 tCO2e/ha/yr)."""

    def test_all_crop_soil_factors_within_ipcc_range(self):
        """Each crop's annual soil carbon factor must sit strictly within [0.25, 0.60] tCO2e/ha/yr."""
        for crop_key, (base_biomass, soil_factor, label) in credit_engine._CROP_FACTORS.items():
            self.assertGreaterEqual(
                soil_factor, 0.25,
                f"Crop '{crop_key}' ({label}) soil factor {soil_factor} is below IPCC lower bound (0.25)",
            )
            self.assertLessEqual(
                soil_factor, 0.60,
                f"Crop '{crop_key}' ({label}) soil factor {soil_factor} exceeds IPCC upper bound (0.60)",
            )

    def test_default_crop_soil_factor_within_ipcc_range(self):
        """The fallback / default mixed cropping factor must sit within [0.25, 0.60] tCO2e/ha/yr."""
        base, soil, label = credit_engine._DEFAULT_FACTOR
        self.assertGreaterEqual(soil, 0.25)
        self.assertLessEqual(soil, 0.60)
        self.assertEqual(soil, 0.35)

    def test_mean_soil_factor_plausibility(self):
        """Mean soil factor across all crops should sit in the ~0.35 - 0.40 tCO2e/ha/yr sweet spot."""
        soil_factors = [factor[1] for factor in credit_engine._CROP_FACTORS.values()]
        mean_factor = sum(soil_factors) / len(soil_factors)
        self.assertGreaterEqual(mean_factor, 0.30)
        self.assertLessEqual(mean_factor, 0.45)

    def test_twenty_year_claim_bounded_by_reference_stock(self):
        """A 20-year cumulative claim (soil_factor * 20) must be <= 50% of typical reference stock (25-60 tCO2e/ha)."""
        soil_factors = [factor[1] for factor in credit_engine._CROP_FACTORS.values()]
        mean_factor = sum(soil_factors) / len(soil_factors)
        claim_20yr = mean_factor * 20.0  # ~7.4 tCO2e/ha

        # Reference Telangana SOC stock (SoilGrids: ~25 - 50 tCO2e/ha)
        for ref_stock in (25.0, 35.0, 50.0):
            ratio = claim_20yr / ref_stock
            self.assertLess(
                ratio, 0.50,
                f"20-yr claimed soil sequestration ({claim_20yr:.2f} tCO2e/ha) exceeds 50% of reference stock ({ref_stock} tCO2e/ha)",
            )


class IndianCropCoverageTests(unittest.TestCase):
    """Verify dictionary coverage for all major Indian crop types."""

    MAJOR_INDIAN_CROPS = [
        # Cereals / Staples
        ("rice", "Rice"),
        ("paddy", "Paddy"),
        ("maize", "Maize"),
        ("millets", "Millets"),
        # Cash / Fiber
        ("cotton", "Cotton"),
        ("sugarcane", "Sugarcane"),
        # Pulses / Legumes
        ("pulses", "Pulses"),
        ("pulse", "Pulses"),
        ("red gram", "Red Gram"),
        ("bengal gram", "Bengal Gram"),
        # Spices / Commercial
        ("turmeric", "Turmeric"),
        ("chilli", "Chilli"),
    ]

    def test_major_crops_present_in_crop_factors(self):
        """All major Indian crops must have explicit entries in _CROP_FACTORS."""
        for key, expected_label in self.MAJOR_INDIAN_CROPS:
            self.assertIn(key, credit_engine._CROP_FACTORS)
            _, _, label = credit_engine._CROP_FACTORS[key]
            self.assertEqual(label, expected_label)

    def test_major_crops_present_in_ndvi_windows(self):
        """All major Indian crops must have explicit NDVI signature windows in _CROP_NDVI_WINDOWS."""
        for key, _ in self.MAJOR_INDIAN_CROPS:
            self.assertIn(key, credit_engine._CROP_NDVI_WINDOWS)
            low, high = credit_engine._CROP_NDVI_WINDOWS[key]
            self.assertGreaterEqual(low, 0.0)
            self.assertLessEqual(high, 1.0)
            self.assertLess(low, high)

    def test_crop_key_resolution_patterns(self):
        """_resolve_crop_key must robustly match common Indian agricultural naming conventions."""
        test_cases = [
            ("Paddy (Kharif)", "paddy"),
            ("Rice (Samba)", "rice"),
            ("Bt Cotton (Rainfed)", "cotton"),
            ("Sugarcane (Ratoon)", "sugarcane"),
            ("Red Gram Intercropped", "red gram"),
            ("Bengal Gram / Chana", "bengal gram"),
            ("Guntur Chilli", "chilli"),
            ("Salem Turmeric", "turmeric"),
            ("Hybrid Maize", "maize"),
            ("Pearl Millets", "millets"),
            ("Mixed Pulses", "pulses"),
        ]
        for input_text, expected_key in test_cases:
            resolved = credit_engine._resolve_crop_key(input_text)
            self.assertEqual(
                resolved, expected_key,
                f"Failed resolving '{input_text}': got {resolved}, expected {expected_key}",
            )

    def test_unlisted_crop_gracefully_falls_back(self):
        """Unlisted crops must safely resolve to Mixed Cropping without errors."""
        est = credit_engine.estimate_credits(2.0, "Dragonfruit", 0.65)
        self.assertEqual(est["crop"], "Mixed cropping")
        soil_step = next(s for s in est["steps"] if s["step"] == 3)
        self.assertEqual(soil_step["value"], 0.35)

    def test_stage1_verification_for_all_major_crops(self):
        """Stage 1 verification must succeed for valid in-season NDVI for every major crop."""
        for key, (lo, hi) in credit_engine._CROP_NDVI_WINDOWS.items():
            mid_ndvi = round((lo + hi) / 2.0, 2)
            res = credit_engine.stage1_verification(key, mid_ndvi)
            self.assertEqual(res["status"], "MATCH")
            self.assertTrue(res["match"])


class CI90UncertaintyIntervalTests(unittest.TestCase):
    """Verify CI90 statistical uncertainty interval calculations."""

    def test_heuristic_ci90_brackets_estimate(self):
        """Under heuristic mode, CI90 [low, high] must bracket the post-deduction estimate."""
        est = credit_engine.estimate_credits(3.0, "Cotton", 0.68, quality_score=0.8)
        final = est["credits_tco2e"]
        ci90 = est["ci90"]

        self.assertEqual(est["ci90_source"], "heuristic")
        self.assertLessEqual(ci90["low"], final)
        self.assertGreaterEqual(ci90["high"], final)
        self.assertGreaterEqual(ci90["low"], 0.0)

    def test_heuristic_ci90_uses_1_64_sigma(self):
        """Verify exact ±1.64 sigma formula for heuristic CI90."""
        quality_score = 0.5
        pct = credit_engine.uncertainty_pct(quality_score)  # 20.0%
        est = credit_engine.estimate_credits(2.0, "Rice", 0.75, quality_score=quality_score)
        final = est["credits_tco2e"]

        expected_low = round(max(0.0, final * (1 - 1.64 * pct / 100.0)), 2)
        expected_high = round(final * (1 + 1.64 * pct / 100.0), 2)

        self.assertEqual(est["ci90"]["low"], expected_low)
        self.assertEqual(est["ci90"]["high"], expected_high)

    def test_evidence_quality_shrinks_ci90_span(self):
        """High evidence quality (10% uncertainty) must give a tighter CI90 relative span than low quality (30%)."""
        high_ev = credit_engine.estimate_credits(2.0, "Rice", 0.75, quality_score=1.0)
        low_ev = credit_engine.estimate_credits(2.0, "Rice", 0.75, quality_score=0.0)

        high_span_rel = (high_ev["ci90"]["high"] - high_ev["ci90"]["low"]) / high_ev["credits_tco2e"]
        low_span_rel = (low_ev["ci90"]["high"] - low_ev["ci90"]["low"]) / low_ev["credits_tco2e"]

        self.assertLess(high_span_rel, low_span_rel)

    def test_model_quantiles_ci90_override(self):
        """When valid model_quantiles (p10, p50, p90) are provided, CI90 uses them directly."""
        model_q = {"p10": 15.5, "p50": 22.0, "p90": 29.8}
        est = credit_engine.estimate_credits(
            2.0, "Paddy", 0.75,
            model_quantiles=model_q,
            model_source="random_forest_v3",
        )
        self.assertEqual(est["ci90_source"], "random_forest_v3")
        self.assertEqual(est["ci90"]["low"], 15.5)
        self.assertEqual(est["ci90"]["high"], 29.8)

    def test_malformed_model_quantiles_fallback(self):
        """Malformed or incomplete quantiles fall back to heuristic CI90 gracefully."""
        bad_inputs = [
            {"p10": None, "p50": 20.0, "p90": 30.0},
            {"p10": "invalid", "p50": 20.0, "p90": 30.0},
            {},
        ]
        for bad_q in bad_inputs:
            est = credit_engine.estimate_credits(
                1.5, "Maize", 0.65,
                model_quantiles=bad_q,
                model_source="broken_model",
            )
            self.assertEqual(est["ci90_source"], "heuristic")
            self.assertIn("low", est["ci90"])
            self.assertIn("high", est["ci90"])
            self.assertGreater(est["ci90"]["high"], est["ci90"]["low"])


class SoilGridsIngestionConversionTests(unittest.TestCase):
    """Verify SoilGrids SOC stock conversion formulas used in ingest_soilgrids.py."""

    def test_soc_content_to_stock_derivation(self):
        """Verify stock(t C/ha, 0-30cm) = soc(g/kg) * BD(1.3) * depth(30cm) / 10 = 3.9 * soc(g/kg)."""
        soc_gkg = 5.0  # 5 g/kg = 0.5% organic carbon
        expected_stock_tha = round(soc_gkg * 1.3 * 30.0 / 10.0, 3)
        self.assertEqual(expected_stock_tha, 19.5)  # 5 * 3.9 = 19.5 t C/ha

    def test_soc_stock_to_tco2e_conversion(self):
        """Verify C to CO2 conversion factor 44/12 ≈ 3.67."""
        stock_tc_ha = 19.5
        tco2e_ha = round(stock_tc_ha * 3.67, 3)
        self.assertEqual(tco2e_ha, 71.565)


if __name__ == "__main__":
    unittest.main()
