"""FPO routes: pending/flagged farms, farmer roster, credit pooling, onboarding."""
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from typing import Literal, Optional
import re

from app.security import get_current_user, get_current_user_optional, require_role
from app import supabase_db as db
from app import config as app_config
from app.services import credit_engine, ledger, split_engine

router = APIRouter(prefix="/fpo", tags=["fpo"])


# ─── Models ───

class FpoReviewModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: str
    notes: Optional[str] = ""


class FpoOnboardModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    phone: str
    survey_number: str
    acreage: float
    mandal: str
    village: str
    geojson: Optional[dict] = None


# ─── Helpers ───

def _require_database():
    if not db.is_ready():
        raise HTTPException(
            status_code=503,
            detail="Database is not configured. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in backend/.env.",
        )


def _get_user(phone: str):
    _require_database()
    return db.get_profile(phone)


def _patch_farm(farm_id: Optional[str], fields: dict):
    if not farm_id:
        return None
    try:
        return db.update_farm(farm_id, fields)
    except Exception:
        fields.pop("badge", None)
        try:
            return db.update_farm(farm_id, fields)
        except Exception as exc:
            print(f"farm patch failed: {exc}")
            return None


def _resolve_fpo_link(farm: Optional[dict], farmer_phone: str) -> str:
    if farm and farm.get("fpo_id"):
        fpos = db.list_fpos() if db.is_ready() else []
        match = next((f for f in fpos if f.get("id") == farm.get("fpo_id")), None)
        return (match or {}).get("name") or "Linked FPO"
    if farm and farm.get("fpo"):
        return farm["fpo"]
    return ""


# ─── Endpoints ───

@router.get("/farms")
def fpo_farms(
    status: str = Query("PENDING"),
    current_user: dict = Depends(require_role("fpo", "verifier", "admin")),
):
    _require_database()
    reviewer = _get_user(current_user.get("phone")) or {}
    fpo_id = reviewer.get("fpo_id")
    phones = None
    if fpo_id:
        phones = [p.get("phone") for p in db.list_profiles_by_fpo(fpo_id) if p.get("phone")]
    farms = db.list_farms_by_status(status, owner_phones=phones)
    return {"success": True, "status": status, "farms": farms}


@router.post("/confirm/{farm_id}")
def fpo_confirm_farm(farm_id: str, current_user: dict = Depends(require_role("fpo", "verifier", "admin"))):
    from app.services.trust_engine import fpo_confirmed_result

    _require_database()
    farm = db.get_farm(farm_id)
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found")
    trust = fpo_confirmed_result()
    updated = _patch_farm(farm_id, {"status": trust["status"], "badge": trust["badge"]})
    db.insert_kyc_verification({
        "owner_phone": farm.get("owner_phone"),
        "status": trust["status"], "reasons": [],
        "checks": {"reviewed_by": current_user.get("phone"), "action": "confirm"},
        "extracted_fields": {**trust, "farm_id": farm_id, "reviewed_by": current_user.get("phone")},
        "document_name": "fpo-confirm",
        "document_sha256": f"fpo-confirm-{farm_id}",
        "perceptual_hash": None,
    })
    return {"success": True, **trust, "farm": updated or farm}


@router.post("/review/{farm_id}")
def fpo_review_farm(
    farm_id: str, data: FpoReviewModel,
    current_user: dict = Depends(require_role("fpo", "verifier", "admin")),
):
    from app.services.trust_engine import fpo_confirmed_result

    _require_database()
    farm = db.get_farm(farm_id)
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found")
    action = (data.action or "").strip().lower()
    if action not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="action must be approve or reject")
    if action == "approve":
        trust = fpo_confirmed_result()
        status, badge = trust["status"], trust["badge"]
    else:
        trust = {
            "tier": None, "badge": None, "risk": "HIGH", "status": "FLAGGED",
            "failed_checks": ["fpo_rejected"], "marketplace_eligible": False, "credits_blocked": True,
        }
        status, badge = "FLAGGED", None
    fields = {"status": status}
    if badge:
        fields["badge"] = badge
    updated = _patch_farm(farm_id, fields)
    db.insert_kyc_verification({
        "owner_phone": farm.get("owner_phone"), "status": status,
        "reasons": [data.notes] if data.notes else [],
        "checks": {"reviewed_by": current_user.get("phone"), "action": action},
        "extracted_fields": {**trust, "farm_id": farm_id, "reviewed_by": current_user.get("phone"), "notes": data.notes},
        "document_name": f"fpo-review-{action}",
        "document_sha256": f"fpo-review-{action}-{farm_id}",
        "perceptual_hash": None,
    })
    return {"success": True, **trust, "action": action, "farm": updated or farm}


@router.get("/farmers")
def get_fpo_farmers(current_user: Optional[dict] = Depends(get_current_user_optional)):
    sb = db._client()
    if not sb:
        return {"success": False, "message": "Database unavailable", "farmers": []}
    try:
        fpo_id = (current_user or {}).get("fpo_id")
        query = sb.table("profiles").select("*")
        if fpo_id:
            query = query.eq("fpo_id", fpo_id)
        profiles = (query.execute().data) or []
        farms = (sb.table("farms").select("owner_phone,area_hectares,total_credits,status,badge,crop_type").execute().data) or []
        farms_by_phone: dict = {}
        for f in farms:
            farms_by_phone.setdefault(f.get("owner_phone"), []).append(f)

        farmers = []
        for p in profiles:
            pfarms = farms_by_phone.get(p.get("phone"), [])
            active = [f for f in pfarms if str(f.get("status", "")).lower() not in ("flagged",)]
            farmers.append({
                "id": p.get("id"), "name": p.get("name") or "Unnamed Farmer",
                "phone": p.get("phone"), "village": p.get("village"),
                "district": p.get("district"), "fpo_id": p.get("fpo_id"),
                "farm_count": len(pfarms),
                "acres": round(sum(float(f.get("area_hectares") or 0) for f in active), 2),
                "credits": round(sum(float(f.get("total_credits") or 0) for f in active), 2),
                "badge": next((f.get("badge") for f in pfarms if f.get("badge")), None) or ("REGISTRY" if pfarms else "NONE"),
                "status": "FLAGGED" if any(str(f.get("status", "")).lower() == "flagged" for f in pfarms) else ("VERIFIED" if pfarms else "PENDING"),
            })
        return {
            "success": True, "fpo_id": fpo_id,
            "total_farmers": len(farmers),
            "total_acreage": round(sum(f["acres"] for f in farmers), 2),
            "pooled_credits": round(sum(f["credits"] for f in farmers), 2),
            "farmers": farmers,
        }
    except Exception as e:
        return {"success": False, "message": str(e), "farmers": []}


@router.post("/onboard")
def fpo_onboard_farmer(data: FpoOnboardModel, current_user: Optional[dict] = Depends(get_current_user_optional)):
    sb = db._client()
    if not sb:
        return {"success": False, "message": "Database unavailable"}
    try:
        phone = re.sub(r"\D", "", data.phone or "")
        if len(phone) > 10:
            phone = phone[-10:]
        if len(phone) != 10:
            return {"success": False, "message": "Enter a valid 10-digit phone number"}
        if data.acreage is None or data.acreage <= 0:
            return {"success": False, "message": "Acreage must be greater than zero"}

        fpo_id = (current_user or {}).get("fpo_id")
        if not fpo_id:
            fpos = (sb.table("fpos").select("id").limit(1).execute().data) or []
            fpo_id = fpos[0].get("id") if fpos else None

        existing = db.get_profile(phone)
        profile_fields = {
            "phone": phone, "name": data.name, "role": "farmer",
            "village": data.village, "fpo_id": fpo_id,
        }
        if existing:
            db.update_profile(phone, {k: v for k, v in profile_fields.items() if v})
            profile = db.get_profile(phone)
        else:
            db.upsert_profile(profile_fields)
            profile = db.get_profile(phone)

        farm_record = {
            "owner_phone": phone, "name": f"{data.name}'s Parcel ({data.survey_number})",
            "crop_type": "Mixed Crop", "area_hectares": data.acreage,
            "status": "Verified", "badge": "FPO", "fpo_id": fpo_id,
            "satellite_source": "FPO attestation",
        }
        if data.geojson and data.geojson.get("geometry"):
            farm_record["geojson"] = data.geojson
            farm_record["area_hectares"] = data.acreage or _polygon_area_hectares(data.geojson)
        saved_farm = db.insert_farm_safe(farm_record)

        return {
            "success": True, "message": f"Farmer {data.name} onboarded under FPO attestation",
            "badge": "FPO",
            "farmer": {
                "id": (profile or {}).get("id"), "name": data.name, "phone": phone,
                "survey": data.survey_number, "acres": data.acreage, "badge": "FPO", "status": "VERIFIED",
            },
            "farm_id": (saved_farm or {}).get("id"),
        }
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.get("/pending")
def get_fpo_pending():
    sb = db._client()
    if not sb:
        return {"success": False, "message": "Database unavailable", "pending": []}
    try:
        farms = (sb.table("farms").select("*").ilike("status", "pending").execute().data) or []
        phones = list({f.get("owner_phone") for f in farms if f.get("owner_phone")})
        owners = {}
        if phones:
            owners = {p.get("phone"): p for p in (sb.table("profiles").select("phone,name,village").in_("phone", phones).execute().data or [])}
        pending = [{
            "id": f.get("id"), "name": (owners.get(f.get("owner_phone")) or {}).get("name") or "Unknown Farmer",
            "phone": f.get("owner_phone"),
            "village": f.get("geojson", {}).get("properties", {}).get("village") or (owners.get(f.get("owner_phone")) or {}).get("village"),
            "farm_name": f.get("name"), "crop": f.get("crop_type"),
            "acres": f.get("area_hectares"), "date": (f.get("created_at") or "")[:10],
        } for f in farms]
        return {"success": True, "pending": pending}
    except Exception as e:
        return {"success": False, "message": str(e), "pending": []}


@router.get("/flagged")
def get_fpo_flagged():
    sb = db._client()
    if not sb:
        return {"success": False, "message": "Database unavailable", "flagged": []}
    try:
        farms = (sb.table("farms").select("*").ilike("status", "flagged").execute().data) or []
        phones = list({f.get("owner_phone") for f in farms if f.get("owner_phone")})
        owners = {}
        if phones:
            owners = {p.get("phone"): p for p in (sb.table("profiles").select("phone,name,village").in_("phone", phones).execute().data or [])}
        flagged = [{
            "id": f.get("id"), "farmer_name": (owners.get(f.get("owner_phone")) or {}).get("name") or "Unknown Farmer",
            "farm_name": f.get("name"), "village": (owners.get(f.get("owner_phone")) or {}).get("village"),
            "claimed_acres": f.get("area_hectares"),
            "issue": "Flagged by fraud engine — ownership/geometry discrepancy",
            "status": "FLAGGED", "date": (f.get("updated_at") or f.get("created_at") or "")[:10],
        } for f in farms]
        return {"success": True, "flagged": flagged}
    except Exception as e:
        return {"success": False, "message": str(e), "flagged": []}