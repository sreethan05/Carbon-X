"""Ops routes: operational snapshots, ground-truth calibration, monitoring."""
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict
from typing import Literal, Optional
from datetime import datetime, timezone

from app.security import get_current_user, get_current_user_optional, require_role
from app import supabase_db as db
from app import config as app_config
from app.services import credit_engine, ledger

router = APIRouter(prefix="/ops", tags=["ops"])


# ─── Models ───

class GroundTruthModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    farm_id: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    measured_soc_tco2e_ha: Optional[float] = None
    measured_species_count: Optional[int] = None
    source: str = "field_survey"
    measured_at: Optional[str] = None
    notes: Optional[str] = None


# ─── Endpoints ───

@router.get("/summary")
def ops_summary(current_user: dict = Depends(require_role("admin", "verifier", "fpo"))):
    sb = db._client()
    if not sb:
        return {"success": False, "message": "Database not configured", "mode": "demo"}
    try:
        def count(table, query=None):
            q = sb.table(table).select("*", count="exact")
            if query:
                q = q.eq(*query)
            return q.execute().count or 0
        def icount(table, status: str):
            # Farm statuses are stored with mixed casing (PENDING/Flagged);
            # match case-insensitively so ops never shows a false zero.
            return (sb.table(table).select("*", count="exact")
                    .ilike("status", status).execute().count or 0)
        farms_flagged = icount("farms", "flagged")
        farms_pending = icount("farms", "pending")
        summary = {
            "success": True,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "profiles": count("profiles"),
            "farms_total": count("farms"),
            "farms_pending_review": farms_pending,
            "farms_flagged_at_risk": farms_flagged,
            "listings_active": count("marketplace_listings", ("status", "Active")),
            "listings_retired": count("marketplace_listings", ("status", "Retired")),
            "kyc_verifications": count("kyc_verifications"),
            "ground_truth_samples": count("ground_truth_samples"),
            "ledger_events": count("ledger_events"),
        }
        return summary
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.post("/ground-truth")
def add_ground_truth(data: GroundTruthModel,
                     current_user: dict = Depends(require_role("admin", "verifier", "fpo"))):
    sb = db._client()
    if not sb:
        return {"success": False, "message": "Database not configured"}
    try:
        row = {k: v for k, v in data.model_dump().items() if v is not None}
        res = sb.table("ground_truth_samples").insert(row).execute()
        return {"success": True, "sample": (res.data or [None])[0]}
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.get("/ground-truth/eval")
def evaluate_ground_truth(current_user: Optional[dict] = Depends(get_current_user_optional)):
    sb = db._client()
    if not sb:
        return {"success": False, "message": "Database not configured"}
    try:
        samples = (sb.table("ground_truth_samples").select("*").execute().data) or []
        linked = [s for s in samples if s.get("farm_id") and s.get("measured_soc_tco2e_ha")]
        comparisons = []
        for s in linked:
            farm = db.get_farm(s["farm_id"])
            if not farm:
                continue
            est = credit_engine.estimate_credits(
                float(farm.get("area_hectares") or 0), farm.get("crop_type") or "",
                farm.get("ndvi") or 0, quality_score=1.0)
            per_ha = est["credits_tco2e"] / max(float(farm.get("area_hectares") or 1), 0.01)
            measured = float(s["measured_soc_tco2e_ha"])
            comparisons.append({
                "farm_id": s["farm_id"],
                "estimated_tco2e_ha": round(per_ha, 2),
                "measured_tco2e_ha": measured,
                "error_pct": round(abs(per_ha - measured) / max(measured, 1e-6) * 100, 1),
                "source": s.get("source"),
            })
        n = len(comparisons)
        summary = {
            "samples_total": len(samples),
            "samples_linked_to_farms": n,
            "mae_pct": round(sum(c["error_pct"] for c in comparisons) / n, 1) if n else None,
        }
        if not n:
            summary["status"] = ("NO FARM-LINKED CALIBRATION DATA YET — estimates are proxy-based "
                                 "(NDVI productivity proxy); enter measured SOC via "
                                 "POST /ops/ground-truth to produce a real error figure.")

        # Stock-basis plausibility check (soilgrids_v2 reference points):
        # SoilGrids gives a SOC *stock* (tCO2e/ha, 0-30cm); our estimates are
        # annual *rates*. The honest comparison is a bound: our claimed
        # cumulative 20-yr soil sequestration (soil factor x 20) must stay
        # well below the measured stock (IPCC: improved management moves
        # <=~30% of initial stock over 20y -> flag ratio > 0.5).
        soilgrids = [s for s in samples if s.get("source") == "soilgrids_v2"
                     and s.get("measured_soc_tco2e_ha")]
        if soilgrids:
            soil_factor_mean = sum(f[1] for f in credit_engine._CROP_FACTORS.values()) / len(credit_engine._CROP_FACTORS)
            claim_20yr = soil_factor_mean * 20
            ratios = []
            exceed = 0
            for s in soilgrids:
                stock = float(s["measured_soc_tco2e_ha"])
                ratio = claim_20yr / max(stock, 1e-6)
                ratios.append(ratio)
                if ratio > 0.5:
                    exceed += 1
            ratios.sort()
            summary["stock_plausibility"] = {
                "n": len(soilgrids),
                "note": ("Bound check, not rate validation: claimed 20-yr cumulative "
                         f"soil sequestration (mean soil factor {soil_factor_mean:.2f} tCO2e/ha/yr x 20) vs "
                         "SoilGrids SOC stock. Rates need field samples."),
                "median_claim_over_stock": round(ratios[len(ratios) // 2], 3),
                "share_exceeding_0p5_bound": round(exceed / len(soilgrids), 3),
                "verdict": ("PLAUSIBLE — claimed cumulative sequestration stays within "
                            "IPCC stock-change bounds on the reference points"
                            if exceed / len(soilgrids) < 0.1 else
                            "REVIEW — a material share of reference points cannot absorb "
                            "the claimed sequestration; revisit _CROP_FACTORS"),
            }
        return {"success": True, "summary": summary, "comparisons": comparisons}
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.post("/ground-truth/calibrate")
def calibrate_crop_factors(current_user: dict = Depends(require_role("admin", "verifier"))):
    sb = db._client()
    if not sb:
        return {"success": False, "message": "Database not configured"}
    try:
        samples = (sb.table("ground_truth_samples").select("*").execute().data) or []
        linked = [s for s in samples if s.get("farm_id") and s.get("measured_soc_tco2e_ha")]
        by_crop: dict = {}
        for s in linked:
            farm = db.get_farm(s["farm_id"])
            if not farm:
                continue
            est = credit_engine.estimate_credits(
                float(farm.get("area_hectares") or 0), farm.get("crop_type") or "",
                farm.get("ndvi") or 0, quality_score=1.0)
            per_ha = est["credits_tco2e"] / max(float(farm.get("area_hectares") or 1), 0.01)
            measured = float(s["measured_soc_tco2e_ha"])
            crop = (farm.get("crop_type") or "Unknown").strip()
            by_crop.setdefault(crop, []).append((per_ha, measured))
        n_total = sum(len(v) for v in by_crop.values())
        if n_total < 30:
            return {"success": True,
                    "eligible": False,
                    "message": f"Calibration needs >=30 linked samples (have {n_total}). Collect Phase-0 plots first.",
                    "samples_linked": n_total}
        suggestions = {}
        errors = []
        for crop, pairs in by_crop.items():
            ratios = [m / max(e, 1e-6) for e, m in pairs]
            mean_ratio = sum(ratios) / len(ratios)
            suggestions[crop] = {
                "n": len(pairs),
                "mean_ratio_measured_over_estimated": round(mean_ratio, 3),
                "suggested_biomass_base_multiplier": round(mean_ratio, 3),
            }
            errors.extend(abs(m - e) / max(m, 1e-6) * 100 for e, m in pairs)
        mae_pct = sum(errors) / len(errors)
        return {"success": True, "eligible": mae_pct < 15, "overall_mae_pct": round(mae_pct, 1),
                "suggestions": suggestions,
                "note": "Apply via methodology review — update _CROP_FACTORS and bump FORMULA_VERSION."}
    except Exception as e:
        return {"success": False, "message": str(e)}


NDVI_DROP_ALERT = app_config.NDVI_DROP_ALERT


