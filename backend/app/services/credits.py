"""Single canonical credit arithmetic for the whole platform.

Every credit number a farmer, buyer or judge sees must come from ONE place.
That place is ``credit_engine`` (the VM0042-style 5-step calculation:
additionality → biomass proxy → IPCC Tier-1-style soil factor → combine →
uncertainty deduction).

This module is the thin adapter that the API layer calls, so no endpoint
re-implements credit maths. Response keys are kept compatible with the
existing frontend (``carbon_credits`` / ``biodiversity_credits`` /
``total_credits``), but the TOTAL is the canonical engine's number and the
biodiversity figure is a co-benefit indicator only — it is never added to
the credit total (that double-counting is exactly what this module removes).
"""

from app.services import credit_engine

ENGINE_NAME = "vm0042-simplified"

# Biodiversity is a reported co-benefit, not a tradeable credit unit.
BIODIVERSITY_COBENEFIT_DIVISOR = 40.0


def canonical_credits(
    *,
    area_ha: float,
    crop: str = "",
    ndvi: float = None,
    baseline_ndvi: float = None,
    quality_score: float = 1.0,
    biodiversity_score: float = None,
) -> dict:
    """Return the one canonical credit result for a plot.

    When ``ndvi`` is None no credit is produced (``credits_available: False``):
    the platform never invents satellite evidence to make a number appear.
    """
    if ndvi is None:
        return {
            "engine": ENGINE_NAME,
            "credits_available": False,
            "carbon_credits": 0.0,
            "biodiversity_credits": 0.0,
            "total_credits": 0.0,
            "uncertainty_pct": None,
            "steps": [],
            "biodiversity_in_total": False,
            "note": "No satellite NDVI available — no credit issued.",
        }

    est = credit_engine.estimate_credits(
        area_hectares=area_ha,
        crop=crop,
        ndvi=ndvi,
        baseline_ndvi=baseline_ndvi,
        quality_score=quality_score,
    )
    bio = round(float(biodiversity_score or 0) / BIODIVERSITY_COBENEFIT_DIVISOR, 2)
    total = est["credits_tco2e"]
    return {
        "engine": ENGINE_NAME,
        "credits_available": True,
        "carbon_credits": total,
        "biodiversity_credits": bio,          # co-benefit indicator, NOT added to total
        "biodiversity_in_total": False,
        "total_credits": total,               # canonical engine number
        "uncertainty_pct": est["uncertainty_pct"],
        "raw_tco2e": est["raw_tco2e"],
        "steps": est["steps"],
        "crop": est["crop"],
    }
