"""Field-validation status for carbon estimates.

CarbonX estimates are *proxy* estimates: satellite NDVI plus crop/soil
factors.  They must not be presented as measured or field-validated until
independent field samples exist.  This module is the single place that turns
ground-truth samples into an honest validation verdict:

- ``proxy_unvalidated``          no usable field samples yet
- ``proxy_insufficient_data``    samples exist, below the decision threshold
- ``field_validated_limited``    enough samples and error metrics pass
- ``field_validation_failed``    enough samples but the proxy is outside bounds

The thresholds are deliberately conservative and public.  A model that fails
them is reported as failed, not quietly relabelled.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Callable, Iterable, Optional

# At least 30 independent field plots, spread over seasons/crops, before the
# proxy can be called "field validated".  This mirrors the calibration gate in
# ``/ops/ground-truth/calibrate``.
MIN_VALIDATION_SAMPLES = 30
# A proxy may be called "limited validation" only when mean absolute
# percentage error is <= 30%, absolute bias <= 20%, and at least half of the
# measured values fall inside the estimate's 90% interval.
MAX_VALIDATION_MAPE = 30.0
MAX_VALIDATION_BIAS = 20.0
MIN_CI90_COVERAGE = 50.0

VERIFIED_MEASUREMENT_STATUSES = {"lab_verified", "field_verified", "verified"}
RATE_UNITS = "tCO2e/ha/yr"
STOCK_UNITS = "tCO2e/ha (0-30cm)"

PUBLIC_LABEL = (
    "Proxy estimate — calculated from satellite NDVI and published crop/soil "
    "factors. Not validated against field measurements."
)
PUBLIC_LABEL_VALIDATED = (
    "Field-validated proxy — independent field samples met the published "
    "validation thresholds. See the validation report for scope and limits."
)
PUBLIC_LABEL_FAILED = (
    "Validation failed — field samples do not support the current proxy "
    "estimate. Do not use this figure for credit-grade claims without review."
)

SUPPORTED_CLAIMS = [
    "The figure is a transparent, reproducible proxy for annual soil/ biomass "
    "carbon change at the enrolled parcel.",
    "The figure carries an explicit uncertainty interval and evidence-quality "
    "deduction.",
    "The calculation inputs and formula version are recorded for audit.",
]

UNSUPPORTED_CLAIMS = [
    "The figure is a direct measurement of soil organic carbon.",
    "The figure is equivalent to a registry-issued VCU or a Verra/Gold "
    "Standard certified credit.",
    "The figure has been validated for the current crop, season and region "
    "unless the validation report says so.",
    "Biodiversity credits are a species census; they are a relative index.",
]


def _f(value, default=None):
    try:
        if value is None or value == "":
            return default
        number = float(value)
        if not math.isfinite(number):
            return default
        return number
    except (TypeError, ValueError):
        return default


def measurement_type(sample: dict) -> str:
    raw = str((sample or {}).get("measurement_type") or "").strip().lower()
    if raw in ("stock", "soc_stock", "stock_0_30cm"):
        return "stock"
    if raw in ("rate", "annual_rate", "soc_rate"):
        return "rate"
    # Legacy SoilGrids reference rows are stocks; every other legacy row is
    # treated as an annual rate (the original intent of the table).
    if str((sample or {}).get("source") or "").lower().startswith("soilgrids"):
        return "stock"
    return "rate"


def is_verified(sample: dict) -> bool:
    status = str((sample or {}).get("verification_status") or "unverified").lower()
    return status in VERIFIED_MEASUREMENT_STATUSES


def _safe_pct_error(estimated: float, measured: float) -> float:
    return abs(estimated - measured) / max(abs(measured), 1e-9) * 100.0


def _read_estimate_from_farm(farm: dict, estimate_fn: Callable) -> Optional[dict]:
    if not farm:
        return None
    area = _f(farm.get("area_hectares"), 0)
    if area <= 0:
        return None
    try:
        est = estimate_fn(
            area,
            farm.get("crop_type") or "",
            _f(farm.get("ndvi"), 0) or 0,
            quality_score=1.0,
        )
    except Exception:
        return None
    per_ha = float(est.get("credits_tco2e") or 0) / max(area, 1e-9)
    ci = est.get("ci90") or {}
    return {
        "estimated_tco2e_ha": round(per_ha, 4),
        # The estimate's interval is an absolute total; report it per hectare
        # so CI90 coverage is compared in the same units as the field rate.
        "ci90_low": round(float(ci["low"]) / area, 4) if _f(ci.get("low")) is not None else None,
        "ci90_high": round(float(ci["high"]) / area, 4) if _f(ci.get("high")) is not None else None,
        "formula_version": est.get("formula_version"),
    }


def _sample_estimate(sample: dict, farm: Optional[dict], estimate_fn: Optional[Callable]) -> Optional[dict]:
    """Snapshot first (what the model said at sampling time), live fallback."""
    snapshot = sample.get("estimate_snapshot")
    if isinstance(snapshot, dict):
        est = _f(snapshot.get("estimated_tco2e_ha"))
        if est is not None:
            return {
                "estimated_tco2e_ha": est,
                "ci90_low": _f(snapshot.get("ci90_low")),
                "ci90_high": _f(snapshot.get("ci90_high")),
                "formula_version": snapshot.get("formula_version"),
                "source": "snapshot_at_sampling",
            }
    direct = _f(sample.get("estimated_tco2e_ha"))
    if direct is not None:
        return {
            "estimated_tco2e_ha": direct,
            "ci90_low": _f(sample.get("estimated_ci90_low")),
            "ci90_high": _f(sample.get("estimated_ci90_high")),
            "formula_version": sample.get("estimate_formula_version"),
            "source": "sample_record",
        }
    if estimate_fn:
        live = _read_estimate_from_farm(farm or {}, estimate_fn)
        if live:
            live["source"] = "live_recompute"
        return live
    return None


def _metrics(pairs: list[dict]) -> dict:
    n = len(pairs)
    if not n:
        return {
            "n": 0,
            "mae_tco2e_ha": None,
            "mape_pct": None,
            "rmse_tco2e_ha": None,
            "bias_tco2e_ha": None,
            "bias_pct": None,
            "ci90_coverage_pct": None,
        }
    errors = [p["estimated"] - p["measured"] for p in pairs]
    abs_errors = [abs(e) for e in errors]
    pct_errors = [_safe_pct_error(p["estimated"], p["measured"]) for p in pairs]
    bias = sum(errors) / n
    mean_measured = sum(p["measured"] for p in pairs) / n
    covered = [
        p for p in pairs
        if p.get("ci90_low") is not None and p.get("ci90_high") is not None
        and float(p["ci90_low"]) <= p["measured"] <= float(p["ci90_high"])
    ]
    return {
        "n": n,
        "mae_tco2e_ha": round(sum(abs_errors) / n, 4),
        "mape_pct": round(sum(pct_errors) / n, 1),
        "rmse_tco2e_ha": round(math.sqrt(sum(e * e for e in errors) / n), 4),
        "bias_tco2e_ha": round(bias, 4),
        "bias_pct": round(bias / max(abs(mean_measured), 1e-9) * 100.0, 1),
        "ci90_coverage_pct": round(len(covered) / n * 100.0, 1),
    }


def evaluate_samples(
    samples: Iterable[dict],
    farm_lookup: Optional[Callable[[str], Optional[dict]]] = None,
    estimate_fn: Optional[Callable] = None,
) -> dict:
    """Build the validation report from ground-truth samples.

    ``farm_lookup(farm_id)`` and ``estimate_fn`` are injectable so this module
    has no database or credit-engine import cycle.
    """
    samples = list(samples or [])
    farm_lookup = farm_lookup or (lambda _fid: None)

    rate_pairs = []
    stock_rows = []
    pending = 0
    rejected = 0
    comparisons = []
    per_crop: dict[str, list[dict]] = {}

    for sample in samples:
        if not isinstance(sample, dict):
            continue
        mtype = measurement_type(sample)
        measured = _f(sample.get("measured_soc_tco2e_ha"))
        if measured is None or measured <= 0:
            rejected += 1
            continue
        if not is_verified(sample):
            pending += 1

        farm_id = sample.get("farm_id")
        farm = farm_lookup(farm_id) if farm_id else None

        if mtype == "stock":
            stock_rows.append({**sample, "measured": measured, "farm": farm})
            continue

        est = _sample_estimate(sample, farm, estimate_fn)
        if not est or _f(est.get("estimated_tco2e_ha")) is None:
            rejected += 1
            continue

        comparison = {
            "sample_id": sample.get("id"),
            "farm_id": farm_id,
            "crop": (farm or {}).get("crop_type") or sample.get("crop") or "Unknown",
            "measured_tco2e_ha": round(measured, 4),
            "estimated_tco2e_ha": round(float(est["estimated_tco2e_ha"]), 4),
            "ci90_low": est.get("ci90_low"),
            "ci90_high": est.get("ci90_high"),
            "error_tco2e_ha": round(float(est["estimated_tco2e_ha"]) - measured, 4),
            "error_pct": round(_safe_pct_error(float(est["estimated_tco2e_ha"]), measured), 1),
            "verified": is_verified(sample),
            "lab_reference": sample.get("lab_reference"),
            "sampled_at": sample.get("sampled_at") or sample.get("measured_at"),
            "estimate_source": est.get("source"),
            "formula_version": est.get("formula_version"),
        }
        comparisons.append(comparison)
        if is_verified(sample):
            item = {
                "estimated": float(est["estimated_tco2e_ha"]),
                "measured": measured,
                "ci90_low": est.get("ci90_low"),
                "ci90_high": est.get("ci90_high"),
            }
            rate_pairs.append(item)
            per_crop.setdefault(comparison["crop"], []).append(item)

    overall = _metrics(rate_pairs)
    crop_metrics = {
        crop: _metrics(pairs) for crop, pairs in sorted(per_crop.items())
    }

    if overall["n"] == 0:
        status = "proxy_unvalidated"
        label = PUBLIC_LABEL
        reason = "No verified field-rate samples are linked to parcels yet."
    elif overall["n"] < MIN_VALIDATION_SAMPLES:
        status = "proxy_insufficient_data"
        label = PUBLIC_LABEL
        reason = (
            f"{overall['n']} verified field-rate sample(s); "
            f"{MIN_VALIDATION_SAMPLES} are required before any validation claim."
        )
    elif (
        overall["mape_pct"] is not None
        and overall["mape_pct"] <= MAX_VALIDATION_MAPE
        and abs(overall["bias_pct"] or 0) <= MAX_VALIDATION_BIAS
        and (overall["ci90_coverage_pct"] or 0) >= MIN_CI90_COVERAGE
    ):
        status = "field_validated_limited"
        label = PUBLIC_LABEL_VALIDATED
        reason = "Verified field samples meet the published validation thresholds."
    else:
        status = "field_validation_failed"
        label = PUBLIC_LABEL_FAILED
        reason = (
            "Verified field samples exist but the proxy exceeds the published "
            "error/bias/coverage thresholds."
        )

    stock_plausibility = None
    if stock_rows:
        # The proxy produces an annual rate; compare 20-year cumulative soil
        # sequestration against measured stock as a physical plausibility
        # bound only. This is not rate validation.
        try:
            from app.services import credit_engine
            factors = [v[1] for v in credit_engine._CROP_FACTORS.values()]
            mean_soil_factor = sum(factors) / len(factors)
        except Exception:
            mean_soil_factor = 0.35
        claim_20yr = mean_soil_factor * 20
        ratios = [claim_20yr / max(row["measured"], 1e-9) for row in stock_rows]
        exceed = sum(1 for r in ratios if r > 0.5)
        ratios.sort()
        stock_plausibility = {
            "n": len(stock_rows),
            "basis": "physical plausibility bound, not rate validation",
            "mean_soil_factor_tco2e_ha_yr": round(mean_soil_factor, 3),
            "claimed_20yr_cumulative_tco2e_ha": round(claim_20yr, 2),
            "median_claim_over_stock": round(ratios[len(ratios) // 2], 3),
            "share_exceeding_0p5_bound": round(exceed / len(stock_rows), 3),
            "verdict": (
                "PLAUSIBLE" if exceed / len(stock_rows) < 0.1 else "REVIEW"
            ),
        }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "method_version": "field-validation-v1",
        "status": status,
        "public_label": label,
        "reason": reason,
        "proxy_estimate": status != "field_validated_limited",
        "thresholds": {
            "min_verified_samples": MIN_VALIDATION_SAMPLES,
            "max_mape_pct": MAX_VALIDATION_MAPE,
            "max_abs_bias_pct": MAX_VALIDATION_BIAS,
            "min_ci90_coverage_pct": MIN_CI90_COVERAGE,
        },
        "samples_total": len(samples),
        "verified_rate_samples": overall["n"],
        "pending_verification_samples": pending,
        "rejected_samples": rejected,
        "stock_reference_samples": len(stock_rows),
        "metrics": overall,
        "per_crop": crop_metrics,
        "stock_plausibility": stock_plausibility,
        "supported_claims": list(SUPPORTED_CLAIMS),
        "unsupported_claims": list(UNSUPPORTED_CLAIMS),
        "comparisons": comparisons,
    }


def current_report() -> dict:
    """Load the live report from the ops store (DB or in-memory fallback).

    Imported lazily to keep the service dependency-free for unit tests.
    """
    from app.routes.ops_router import _validation_report
    return _validation_report()


def current_status() -> dict:
    """Small status block safe to embed in passports, certificates and UI."""
    report = current_report()
    return {
        "status": report["status"],
        "label": report["public_label"],
        "proxy_estimate": report["proxy_estimate"],
        "verified_samples": report["verified_rate_samples"],
        "required_samples": report["thresholds"]["min_verified_samples"],
        "report_url": "/validation/status",
        "generated_at": report["generated_at"],
    }


def public_view(report: dict) -> dict:
    """Strip row-level farm ids/lab refs for unauthenticated callers."""
    public = dict(report or {})
    comparisons = public.pop("comparisons", [])
    public["comparison_count"] = len(comparisons)
    public["per_crop"] = {
        crop: {k: v for k, v in metrics.items() if k in ("n", "mape_pct", "bias_pct")}
        for crop, metrics in (public.get("per_crop") or {}).items()
    }
    return public
