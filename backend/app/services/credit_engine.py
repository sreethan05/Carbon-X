"""Trust Engine Stage 2 — VM0042-style credit calculation (deliberately simplified).

Five transparent steps, mirroring the methodology family used by Verra VM0042:

1. Additionality (baseline vs project): only the NDVI delta the farmer created
   is creditable.
2. Aboveground biomass proxy from NDVI (crop-calibrated).
3. Soil organic carbon delta from an IPCC Tier 1-style practice lookup.
4. Combine into a raw tCO2e estimate.
5. Uncertainty deduction (10-30%) driven by evidence quality — conservative by
   design so buyers are never over-sold.

The crop factors are calibrated to the platform's canonical demo farms so the
calculator's output lands near the values farmers already see in their
passports. All math is exposed step-by-step in the response: every number a
farmer or buyer sees can be recomputed by hand.
"""

# Formula version for auditability — bump when crop factors or methodology change
FORMULA_VERSION = "vm0042-soilgrids-v1-r2-2026-10-04"

# (base tCO2e/ha/yr at NDVI 0.75, soil tCO2e/ha/yr, label)
# Soil factors recalibrated 2026-10-04 against the SoilGrids stock reference
# (287 Telangana points, /ops/ground-truth/eval plausibility check): the
# original 2-6 tCO2e/ha/yr soil components implied 20-yr sequestration ~3x the
# measured SOC stock — physically impossible. IPCC Tier-1 improved-cropland
# rates on degraded soils are ~0.1-0.5 tC/ha/yr (0.37-1.8 tCO2e/ha/yr); we sit
# at the upper edge (degraded -> improved transition = our additionality claim).
_CROP_FACTORS = {
    "rice": (30.0, 0.45, "Rice"),
    "paddy": (30.0, 0.45, "Paddy"),
    "sugarcane": (58.0, 0.60, "Sugarcane"),
    "cotton": (33.0, 0.40, "Cotton"),
    "maize": (40.0, 0.35, "Maize"),
    "millets": (21.0, 0.25, "Millets"),
    "turmeric": (46.0, 0.40, "Turmeric"),
    "chilli": (27.0, 0.30, "Chilli"),
}
_DEFAULT_FACTOR = (32.0, 0.35, "Mixed cropping")
NDVI_REFERENCE = 0.75
DEFAULT_BASELINE_GAP = 0.10  # baseline NDVI assumed this far below current when unknown

# Benchmark INR price per credit by verification badge (matches the passport).
BENCHMARK_PRICE = {"REGISTRY": 340, "REGISTRY_DOC": 320, "FPO": 300, "DOCUMENT": 310}
PRICE_FLOOR = 400.0   # conservative voluntary-market range shown to farmers
PRICE_CEILING = 650.0
FARMER_FLOOR_SHARE = 0.70

# Trust Engine Stage 1 — in-season NDVI signature windows per declared crop.
# A mismatch never auto-rejects: the record pauses for FPO/KVK human review.
_CROP_NDVI_WINDOWS = {
    "rice": (0.55, 0.95), "paddy": (0.55, 0.95),
    "sugarcane": (0.60, 0.95),
    "cotton": (0.40, 0.90),
    "maize": (0.45, 0.92),
    "millets": (0.30, 0.80),
    "turmeric": (0.45, 0.90),
    "chilli": (0.35, 0.85),
}


def stage1_verification(crop: str, ndvi) -> dict:
    """Declared crop/practice cross-checked against the plot's NDVI signature.

    MATCH advances the record; MISMATCH pauses it for human review rather
    than auto-rejecting — satellite evidence checks declarations, it does not
    replace human judgment.
    """
    ndvi = round(float(ndvi or 0), 3)
    key = str(crop or "").strip().lower()
    window = _CROP_NDVI_WINDOWS.get(key)
    label = _CROP_FACTORS.get(key, (0, 0, crop or "Mixed Crop"))[2]
    if not window:
        return {
            "status": "UNREVIEWED",
            "match": True,
            "crop": label,
            "ndvi": ndvi,
            "expected_range": None,
            "reason": f"No NDVI signature window for {label} yet — accepted without satellite cross-check",
        }
    lo, hi = window
    if lo <= ndvi <= hi:
        return {
            "status": "MATCH",
            "match": True,
            "crop": label,
            "ndvi": ndvi,
            "expected_range": [lo, hi],
            "reason": f"NDVI {ndvi:.2f} sits inside the {label} in-season signature ({lo}–{hi})",
        }
    return {
        "status": "MISMATCH",
        "match": False,
        "crop": label,
        "ndvi": ndvi,
        "expected_range": [lo, hi],
        "reason": f"NDVI {ndvi:.2f} is outside the {label} in-season signature ({lo}–{hi}) — paused for FPO/KVK review",
    }


def evidence_quality(
    *,
    has_photo: bool = True,
    geotag_ok: bool = True,
    fpo_or_registry: bool = False,
    ndvi_current: bool = True,
    baseline_known: bool = False,
) -> dict:
    """0-1 evidence-quality score feeding the uncertainty deduction."""
    components = {
        "practice_photo": (0.25, bool(has_photo)),
        "geotag_inside_boundary": (0.25, bool(geotag_ok)),
        "fpo_or_registry_verified": (0.25, bool(fpo_or_registry)),
        "current_satellite_ndvi": (0.15, bool(ndvi_current)),
        "baseline_established": (0.10, bool(baseline_known)),
    }
    score = sum(w for w, ok in components.values() if ok)
    return {
        "score": round(score, 2),
        "components": {k: {"weight": w, "passed": ok} for k, (w, ok) in components.items()},
    }


def uncertainty_pct(quality_score: float) -> float:
    """10-30% deduction; perfect evidence still keeps a 10% honesty margin."""
    return round(max(10.0, min(30.0, 30.0 - 20.0 * float(quality_score))), 1)


def estimate_credits(
    area_hectares: float,
    crop: str = "",
    ndvi: float = 0.7,
    baseline_ndvi: float = None,
    quality_score: float = 1.0,
    model_quantiles: dict = None,  # {"p10": float, "p50": float, "p90": float} in tCO2e for the plot
    model_source: str = None,
) -> dict:
    """Run the 5-step calculation and return every intermediate number.
    
    If model_quantiles is provided (from ML serving), use them for CI90
    instead of the heuristic uncertainty deduction. The quantiles should be
    on the same scale as credits_tco2e (i.e., total tCO2e for the plot).
    """
    area = max(0.0, float(area_hectares or 0))
    ndvi = max(0.0, min(1.0, float(ndvi or 0)))
    base, soil, label = _CROP_FACTORS.get(str(crop or "").strip().lower(), _DEFAULT_FACTOR)
    baseline = float(baseline_ndvi) if baseline_ndvi is not None else max(0.0, ndvi - DEFAULT_BASELINE_GAP)
    baseline = max(0.0, min(1.0, baseline))

    # 1. Additionality — only the farmer-created delta is creditable.
    additionality_delta = max(0.0, ndvi - baseline)
    # 2. Biomass proxy: 70% standing vegetation + 30% of the improvement delta.
    biomass_proxy = base * (0.7 * ndvi + 0.3 * (ndvi + additionality_delta)) / NDVI_REFERENCE
    # 3. Soil organic carbon delta from the practice lookup.
    # 4. Raw combined estimate.
    raw_per_ha = biomass_proxy + soil
    raw_total = area * raw_per_ha
    # 5. Uncertainty deduction + statistical interval.
    pct = uncertainty_pct(quality_score)
    final = raw_total * (1 - pct / 100.0)
    
    # CI90: prefer model quantiles if provided, else heuristic
    if model_quantiles and all(k in model_quantiles for k in ("p10", "p50", "p90")):
        ci90 = {
            "low": round(max(0.0, float(model_quantiles["p10"])), 2),
            "high": round(float(model_quantiles["p90"]), 2),
        }
        ci90_source = model_source or "model_quantiles"
    else:
        # Treat the uncertainty fraction as ~1 sigma: a 90% interval is ±1.64 sigma.
        ci90 = {
            "low": round(max(0.0, final * (1 - 1.64 * pct / 100.0)), 2),
            "high": round(final * (1 + 1.64 * pct / 100.0), 2),
        }
        ci90_source = "heuristic"

    return {
        "crop": label,
        "area_hectares": round(area, 2),
        "ndvi": round(ndvi, 3),
        "baseline_ndvi": round(baseline, 3),
        "steps": [
            {
                "step": 1,
                "name": "Additionality (baseline vs project)",
                "detail": f"NDVI {ndvi:.2f} vs baseline {baseline:.2f} → creditable delta {additionality_delta:.2f}",
                "value": round(additionality_delta, 3),
            },
            {
                "step": 2,
                "name": "Aboveground biomass proxy",
                "detail": f"{label} base {base} tCO2e/ha scaled by NDVI → {biomass_proxy:.1f} tCO2e/ha",
                "value": round(biomass_proxy, 2),
            },
            {
                "step": 3,
                "name": "Soil organic carbon delta",
                "detail": f"IPCC Tier 1-style practice factor → {soil} tCO2e/ha",
                "value": soil,
            },
            {
                "step": 4,
                "name": "Raw combined estimate",
                "detail": f"{area} ha × ({biomass_proxy:.1f} + {soil}) = {raw_total:.1f} tCO2e",
                "value": round(raw_total, 2),
            },
            {
                "step": 5,
                "name": "Uncertainty deduction",
                "detail": f"Evidence quality {quality_score:.2f} → −{pct}% (conservative by design)",
                "value": -pct,
            },
        ],
        "raw_tco2e": round(raw_total, 2),
        "uncertainty_pct": pct,
        "credits_tco2e": round(final, 2),
        "ci90": ci90,
        "ci90_source": ci90_source,
        "formula_version": FORMULA_VERSION,
    }


def credit_split(carbon_tonnes: float, biodiversity_score: float) -> dict:
    """Canonical carbon-vs-biodiversity credit decomposition.

    THE single source of truth for how a farm's estimate becomes credit
    lines (previously a shim lived in supabase_db.compute_credits and an
    ad-hoc `ndvi * 10` variant existed in /predict). Biodiversity credits
    are a linear index conversion of the biodiversity score (score/40),
    calibrated so demo farms land on their historical values.
    """
    carbon = round(float(carbon_tonnes or 0), 2)
    bio = round(float(biodiversity_score or 0) / 40.0, 2)
    return {
        "carbon_credits": carbon,
        "biodiversity_credits": bio,
        "total_credits": round(carbon + bio, 2),
    }


_quick_scan_cache: dict = {}
_QUICK_SCAN_TTL = 600  # seconds — same composite inputs give identical outputs


def quick_scan_estimate(area_hectares: float, crop: str, ndvi: float, features: dict = None) -> dict:
    import time as _time

    # Cache key includes features hash if provided
    if features:
        import hashlib
        feat_str = "|".join(f"{k}={features.get(k, 0):.4f}" for k in sorted(features.keys()))
        feat_hash = hashlib.md5(feat_str.encode()).hexdigest()[:8]
    else:
        feat_hash = "nofeat"
    key = (round(float(area_hectares), 4), str(crop).strip().lower(), round(float(ndvi), 4), feat_hash)
    
    hit = _quick_scan_cache.get(key)
    if hit and _time.time() - hit[0] < _QUICK_SCAN_TTL:
        import logging
        logging.getLogger("carbonx.credit_engine").info("quick_scan cache hit")
        return dict(hit[1])
    result = _quick_scan_estimate_uncached(area_hectares, crop, ndvi, features)
    if len(_quick_scan_cache) > 512:
        _quick_scan_cache.clear()
    _quick_scan_cache[key] = (_time.time(), result)
    return dict(result)


def _quick_scan_estimate_uncached(area_hectares: float, crop: str, ndvi: float, 
                                   features: dict = None) -> dict:
    """Canonical carbon estimate for enrollment scans.

    THE single source of truth — /analyze must use this, never its own
    formula. It is Trust Engine Stage 2 evaluated at scan-only evidence
    quality (satellite scan exists; no photo/geotag/FPO check yet), so the
    preview is deliberately conservative: farmers see earnings *rise* as
    their evidence quality improves.
    
    If features are provided, attempt to get ML quantiles for CI90.
    """
    quality = evidence_quality(
        has_photo=False, geotag_ok=False, fpo_or_registry=False,
        ndvi_current=True, baseline_known=False,
    )
    
    # Try to get model quantiles for CI90
    model_quantiles = None
    model_source = None
    if features:
        try:
            from app.services.ml_service import predict_soc
            soc_pred = predict_soc(features)
            if soc_pred.get("ml_source") != "unavailable":
                # SOC quantiles are per hectare; scale by area
                area = max(0.01, float(area_hectares or 0))
                model_quantiles = {
                    "p10": soc_pred.get("p10", 0) * area,
                    "p50": soc_pred.get("p50", 0) * area,
                    "p90": soc_pred.get("p90", 0) * area,
                }
                model_source = soc_pred.get("ml_source")
        except Exception:
            pass
    
    est = estimate_credits(
        area_hectares, crop, ndvi, 
        quality_score=quality["score"],
        model_quantiles=model_quantiles,
        model_source=model_source,
    )
    est["evidence_quality"] = quality["score"]
    est["note"] = ("Scan-only preview at scan-only evidence quality — "
                    "add photo, geotag and FPO verification to reduce the deduction.")
    return est


def income_projection(credits_tco2e: float, badge: str = "DOCUMENT") -> dict:
    """Translate verified credits into expected rupees the farmer would keep."""
    credits = max(0.0, float(credits_tco2e or 0))
    benchmark = BENCHMARK_PRICE.get(badge, BENCHMARK_PRICE["DOCUMENT"])
    return {
        "badge": badge,
        "benchmark_price_per_credit": benchmark,
        "expected_income_inr": round(credits * benchmark * FARMER_FLOOR_SHARE, 0),
        "range_inr": {
            "min": round(credits * benchmark * 0.85 * FARMER_FLOOR_SHARE, 0),
            "max": round(credits * benchmark * 1.30 * FARMER_FLOOR_SHARE, 0),
        },
        "farmer_share_pct": FARMER_FLOOR_SHARE * 100,
        "note": "70% farmer floor; actual price set at sale, FPO 5% only when involved",
    }