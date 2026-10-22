"""Ops routes: operational snapshots, ground-truth calibration, monitoring."""
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict
from typing import Literal, Optional
from datetime import datetime, timezone
import threading
import uuid

from app.security import get_current_user, get_current_user_optional, require_role
from app import supabase_db as db
from app import config as app_config
from app.services import credit_engine, ledger, validation

router = APIRouter(prefix="/ops", tags=["ops"])


# ─── Ground-truth store ───
# The DB is the system of record, but field data collection must also work in
# demo/offline mode (and in tests) without inventing accuracy numbers.  The
# in-memory fallback is explicit and never written to a public claim.
_MEMORY_SAMPLES: list[dict] = []
_MEMORY_LOCK = threading.RLock()


def reset_ground_truth_memory() -> None:
    with _MEMORY_LOCK:
        _MEMORY_SAMPLES.clear()


def _memory_add(row: dict) -> dict:
    with _MEMORY_LOCK:
        stored = dict(row)
        stored.setdefault("id", str(uuid.uuid4()))
        stored.setdefault("created_at", datetime.now(timezone.utc).isoformat())
        _MEMORY_SAMPLES.append(stored)
        return dict(stored)


def _sample_rows() -> list[dict]:
    sb = db._client()
    if sb:
        try:
            rows = (sb.table("ground_truth_samples").select("*").execute().data) or []
            return rows
        except Exception as e:
            print(f"[ground-truth] DB read failed ({e}) — using in-memory samples")
    with _MEMORY_LOCK:
        return [dict(r) for r in _MEMORY_SAMPLES]


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
    # Field-validation protocol fields.  ``measurement_type`` distinguishes an
    # annual sequestration rate from a standing SOC stock: a stock can only
    # bound plausibility, never validate a rate claim.
    measurement_type: Literal["rate", "stock"] = "rate"
    depth_cm: Optional[float] = None
    bulk_density_g_cm3: Optional[float] = None
    lab_method: Optional[str] = None
    lab_reference: Optional[str] = None
    sampling_protocol: Optional[str] = None
    sample_design: Optional[str] = None
    verification_status: Literal[
        "unverified", "pending_lab", "lab_verified", "field_verified", "rejected"
    ] = "unverified"
    verified_by: Optional[str] = None
    consent_ref: Optional[str] = None
    crop: Optional[str] = None


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


def _estimate_snapshot(farm_id: Optional[str]) -> Optional[dict]:
    """Freeze the estimate at sampling time so later formula changes cannot
    retroactively flatter the validation result."""
    if not farm_id:
        return None
    if db.is_ready():
        farm = db.get_farm(farm_id)
    else:
        # Offline/demo mode must still freeze a real estimate for demo farms;
        # an arbitrary id with no farm record is rejected rather than guessed.
        from app import sample_data
        farm = None
        for item in sample_data.FARMS:
            if sample_data._fallback_farm_id(item["key"]) == farm_id:
                farm = {
                    "id": farm_id,
                    "area_hectares": item.get("area"),
                    "crop_type": item.get("crop"),
                    "ndvi": item.get("ndvi"),
                }
                break
    if not farm:
        return None
    try:
        est = credit_engine.estimate_credits(
            float(farm.get("area_hectares") or 0), farm.get("crop_type") or "",
            farm.get("ndvi") or 0, quality_score=1.0)
    except Exception:
        return None
    area = max(float(farm.get("area_hectares") or 0), 1e-9)
    ci = est.get("ci90") or {}
    return {
        "estimated_tco2e_ha": round(float(est.get("credits_tco2e") or 0) / area, 4),
        # Store the interval per hectare too, so it is directly comparable to
        # a measured tCO2e/ha/yr rate.
        "ci90_low": round(float(ci.get("low")) / area, 4) if ci.get("low") is not None else None,
        "ci90_high": round(float(ci.get("high")) / area, 4) if ci.get("high") is not None else None,
        "formula_version": est.get("formula_version"),
        "captured_at": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/ground-truth")
def add_ground_truth(data: GroundTruthModel,
                     current_user: dict = Depends(require_role("admin", "verifier", "fpo"))):
    """Record a field measurement (rate or stock) with provenance.

    A rate sample is only usable for validation when it is verified; the
    snapshot of the model's estimate at sampling time is stored alongside it.
    """
    try:
        if data.measured_soc_tco2e_ha is None and data.measured_species_count is None:
            return {
                "success": False,
                "message": "measured_soc_tco2e_ha or measured_species_count is required",
            }
        if data.measured_soc_tco2e_ha is not None and float(data.measured_soc_tco2e_ha) <= 0:
            return {"success": False, "message": "Measured SOC must be greater than zero"}
        row = {k: v for k, v in data.model_dump().items() if v is not None}
        row.setdefault("measurement_type", "rate")
        row["verification_status"] = row.get("verification_status") or "unverified"
        row["source"] = row.get("source") or "field_survey"
        row["created_at"] = datetime.now(timezone.utc).isoformat()
        snapshot = _estimate_snapshot(data.farm_id)
        if snapshot:
            row["estimate_snapshot"] = snapshot

        sb = db._client()
        if not sb:
            stored = _memory_add(row)
            return {
                "success": True,
                "sample": stored,
                "mode": "memory",
                "note": "Database not configured — sample kept in memory for this process.",
            }

        try:
            res = sb.table("ground_truth_samples").insert(row).execute()
            stored = (res.data or [None])[0]
        except Exception as e:
            # Pre-migration compatibility: retry with the original columns.
            legacy_keys = {
                "farm_id", "latitude", "longitude", "measured_soc_tco2e_ha",
                "measured_species_count", "source", "measured_at", "notes",
                "created_at",
            }
            try:
                res = sb.table("ground_truth_samples").insert(
                    {k: v for k, v in row.items() if k in legacy_keys}
                ).execute()
                stored = (res.data or [None])[0]
                if stored:
                    stored["_note"] = (
                        "Stored with legacy columns; apply supabase/10_trust_controls.sql "
                        "to persist verification and protocol metadata."
                    )
            except Exception:
                raise e
        return {"success": True, "sample": stored, "mode": "database"}
    except Exception as e:
        return {"success": False, "message": str(e)}


def _validation_report() -> dict:
    samples = _sample_rows()
    return validation.evaluate_samples(
        samples,
        farm_lookup=db.get_farm if db.is_ready() else (lambda _fid: None),
        estimate_fn=credit_engine.estimate_credits,
    )


@router.get("/ground-truth/eval")
def evaluate_ground_truth(current_user: Optional[dict] = Depends(get_current_user_optional)):
    """Calibration report. Public callers get aggregate metrics only."""
    try:
        report = _validation_report()
        is_staff = str((current_user or {}).get("role") or "").lower() in (
            "admin", "verifier", "fpo"
        )
        body = dict(report)
        if not is_staff:
            body = validation.public_view(body)
        # Backwards-compatible summary keys.
        metrics = report.get("metrics") or {}
        summary = dict(body)
        summary.update({
            "samples_linked_to_farms": metrics.get("n", 0),
            "mae_pct": metrics.get("mape_pct"),
            "status": report.get("status"),
            "label": report.get("public_label"),
        })
        comparisons = report.get("comparisons") if is_staff else []
        legacy_comparisons = [{
            "farm_id": c.get("farm_id"),
            "sample_id": c.get("sample_id"),
            "estimated_tco2e_ha": c.get("estimated_tco2e_ha"),
            "measured_tco2e_ha": c.get("measured_tco2e_ha"),
            "error_pct": c.get("error_pct"),
            "source": c.get("estimate_source"),
            "verified": c.get("verified"),
        } for c in (comparisons or [])]
        return {
            "success": True,
            "mode": "database" if db.is_ready() else "memory",
            "summary": summary,
            "report": body,
            "comparisons": legacy_comparisons,
        }
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.post("/ground-truth/calibrate")
def calibrate_crop_factors(current_user: dict = Depends(require_role("admin", "verifier"))):
    """Suggest factor corrections from verified rate samples. Never auto-applies."""
    try:
        report = _validation_report()
        comparisons = [
            c for c in report.get("comparisons") or []
            if c.get("verified") and c.get("measured_tco2e_ha")
        ]
        if len(comparisons) < validation.MIN_VALIDATION_SAMPLES:
            return {
                "success": True,
                "eligible": False,
                "message": (
                    f"Calibration needs >={validation.MIN_VALIDATION_SAMPLES} verified "
                    f"rate samples (have {len(comparisons)}). Collect field plots first."
                ),
                "samples_linked": len(comparisons),
            }
        by_crop: dict = {}
        for c in comparisons:
            by_crop.setdefault(c.get("crop") or "Unknown", []).append(c)
        suggestions = {}
        errors = []
        for crop, rows in by_crop.items():
            ratios = [
                float(r["measured_tco2e_ha"]) / max(float(r["estimated_tco2e_ha"]), 1e-9)
                for r in rows
            ]
            mean_ratio = sum(ratios) / len(ratios)
            suggestions[crop] = {
                "n": len(rows),
                "mean_ratio_measured_over_estimated": round(mean_ratio, 3),
                "suggested_biomass_base_multiplier": round(mean_ratio, 3),
            }
            errors.extend(float(r["error_pct"]) for r in rows)
        mae_pct = sum(errors) / len(errors)
        return {
            "success": True,
            "eligible": mae_pct < 15,
            "overall_mae_pct": round(mae_pct, 1),
            "suggestions": suggestions,
            "note": (
                "Apply via independent methodology review — update _CROP_FACTORS, "
                "bump FORMULA_VERSION, and re-run validation. Never auto-apply."
            ),
        }
    except Exception as e:
        return {"success": False, "message": str(e)}


NDVI_DROP_ALERT = app_config.NDVI_DROP_ALERT


