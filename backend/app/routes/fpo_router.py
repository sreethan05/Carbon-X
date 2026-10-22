"""FPO routes: pending/flagged farms, farmer roster, credit pooling, onboarding."""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from typing import Optional
import re

from app.security import require_role
from app import supabase_db as db
from app.services.polygon_service import polygon_area_hectares as _polygon_area_hectares

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


def _fpo_scope_ok(role: str, reviewer: dict, farm: dict) -> bool:
    """May this officer act on the farm? Platform verifiers/admins: yes.
    FPO officers: only farms whose owner (or farm row) is in their FPO."""
    if role in ("verifier", "admin"):
        return True
    fpo_id = str((reviewer or {}).get("fpo_id") or "")
    if not fpo_id:
        return False
    if str(farm.get("fpo_id") or "") == fpo_id:
        return True
    owner = db.get_profile(farm.get("owner_phone") or "") or {}
    return str(owner.get("fpo_id") or "") == fpo_id


# ─── Endpoints ───

@router.get("/farms")
def fpo_farms(
    status: str = Query("PENDING"),
    current_user: dict = Depends(require_role("fpo", "verifier", "admin")),
):
    _require_database()
    reviewer = _get_user(current_user.get("phone")) or {}
    role = current_user.get("role", "fpo")
    fpo_id = reviewer.get("fpo_id")
    phones = None
    if fpo_id:
        phones = [p.get("phone") for p in db.list_profiles_by_fpo(fpo_id) if p.get("phone")]
        if not phones:
            return {"success": True, "status": status, "farms": []}
    elif role not in ("verifier", "admin"):
        # Officer not linked to an FPO yet — show nothing rather than all farms.
        return {"success": True, "status": status, "farms": [], "message": "Your account is not linked to an FPO yet"}
    farms = db.list_farms_by_status(status, owner_phones=phones)
    return {"success": True, "status": status, "farms": farms}


@router.post("/confirm/{farm_id}")
def fpo_confirm_farm(farm_id: str, current_user: dict = Depends(require_role("fpo", "verifier", "admin"))):
    from app.services.trust_engine import fpo_confirmed_result

    _require_database()
    farm = db.get_farm(farm_id)
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found")
    reviewer = _get_user(current_user.get("phone")) or {}
    if not _fpo_scope_ok(current_user.get("role", "fpo"), reviewer, farm):
        raise HTTPException(status_code=403, detail="Farm is outside your FPO's jurisdiction")
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
    reviewer = _get_user(current_user.get("phone")) or {}
    if not _fpo_scope_ok(current_user.get("role", "fpo"), reviewer, farm):
        raise HTTPException(status_code=403, detail="Farm is outside your FPO's jurisdiction")
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
    fields = {"status": status, "badge": badge}
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
def get_fpo_farmers(current_user: dict = Depends(require_role("fpo", "verifier", "admin"))):
    _require_database()
    sb = db._client()
    if not sb:
        return {"success": False, "message": "Database unavailable", "farmers": []}
    try:
        reviewer = _get_user(current_user.get("phone")) or {}
        role = current_user.get("role", "fpo")
        fpo_id = reviewer.get("fpo_id")
        if not fpo_id and role not in ("verifier", "admin"):
            return {
                "success": True, "fpo_id": None, "total_farmers": 0,
                "total_acreage": 0, "pooled_credits": 0, "farmers": [],
                "message": "Your account is not linked to an FPO yet",
            }
        query = sb.table("profiles").select("*")
        if fpo_id:
            query = query.eq("fpo_id", fpo_id)
        profiles = (query.execute().data) or []
        member_phones = [p.get("phone") for p in profiles if p.get("phone")]

        if fpo_id and not member_phones:
            farms = []
        else:
            farms_q = sb.table("farms").select("owner_phone,area_hectares,total_credits,status,badge,crop_type")
            if fpo_id:
                farms_q = farms_q.in_("owner_phone", member_phones)
            farms = (farms_q.execute().data) or []

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
                "area_hectares": round(sum(float(f.get("area_hectares") or 0) for f in active), 2),
                "credits": round(sum(float(f.get("total_credits") or 0) for f in active), 2),
                "badge": next((f.get("badge") for f in pfarms if f.get("badge")), None) or ("REGISTRY" if pfarms else "NONE"),
                "status": "FLAGGED" if any(str(f.get("status", "")).lower() == "flagged" for f in pfarms) else ("VERIFIED" if pfarms else "PENDING"),
            })
        return {
            "success": True, "fpo_id": fpo_id,
            "total_farmers": len(farmers),
            "total_hectares": round(sum(f["area_hectares"] for f in farmers), 2),
            "pooled_credits": round(sum(f["credits"] for f in farmers), 2),
            "farmers": farmers,
        }
    except Exception as e:
        return {"success": False, "message": str(e), "farmers": []}


@router.post("/onboard")
def fpo_onboard_farmer(data: FpoOnboardModel, current_user: dict = Depends(require_role("fpo", "verifier", "admin"))):
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

        reviewer = _get_user(current_user.get("phone")) or {}
        role = current_user.get("role", "fpo")
        fpo_id = reviewer.get("fpo_id")
        if not fpo_id and role not in ("verifier", "admin"):
            return {"success": False, "message": "Your account is not linked to an FPO yet — ask the platform admin to link it."}

        existing = db.get_profile(phone)
        if existing and existing.get("fpo_id") and str(existing.get("fpo_id")) != str(fpo_id) and role not in ("verifier", "admin"):
            raise HTTPException(status_code=403, detail="Farmer is already registered with another FPO")
        profile_fields = {
            "phone": phone, "name": data.name.strip(),
            "village": data.village.strip(), "fpo_id": fpo_id,
        }
        if existing:
            # Preserve existing privileged role if any; only set farmer if no role exists
            if not existing.get("role"):
                profile_fields["role"] = "farmer"
            db.update_profile(phone, {k: v for k, v in profile_fields.items() if v is not None})
            profile = db.get_profile(phone)
        else:
            profile_fields["role"] = "farmer"
            db.upsert_profile(profile_fields)
            profile = db.get_profile(phone)

        farm_record = {
            "owner_phone": phone,
            "name": f"{data.name.strip()}'s Parcel ({data.survey_number.strip()})",
            "crop_type": "Mixed Crop",
            "area_hectares": data.acreage,
            "status": "VERIFIED",
            "badge": "FPO",
            "fpo_id": fpo_id,
            "satellite_source": "FPO attestation",
        }
        if data.geojson and isinstance(data.geojson, dict) and data.geojson.get("geometry"):
            farm_record["geojson"] = data.geojson
            measured = _polygon_area_hectares(data.geojson)
            farm_record["area_hectares"] = measured if measured > 0 else data.acreage
        else:
            farm_record["geojson"] = {
                "type": "Feature",
                "properties": {
                    "mandal": data.mandal.strip(),
                    "village": data.village.strip(),
                    "survey_number": data.survey_number.strip(),
                },
            }
        saved_farm = db.insert_farm_safe(farm_record)
        if not saved_farm:
            return {"success": False, "message": "Failed to save farm record in database"}

        return {
            "success": True, "message": f"Farmer {data.name} onboarded under FPO attestation",
            "badge": "FPO",
            "farmer": {
                "id": (profile or {}).get("id"), "name": data.name.strip(), "phone": phone,
                "survey": data.survey_number.strip(), "area_hectares": data.acreage, "badge": "FPO", "status": "VERIFIED",
            },
            "farm_id": (saved_farm or {}).get("id"),
        }
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.get("/pending")
def get_fpo_pending(current_user: dict = Depends(require_role("fpo", "verifier", "admin"))):
    sb = db._client()
    if not sb:
        return {"success": False, "message": "Database unavailable", "pending": []}
    try:
        reviewer = _get_user(current_user.get("phone")) or {}
        role = current_user.get("role", "fpo")
        fpo_id = reviewer.get("fpo_id")
        member_phones = None
        if fpo_id:
            member_phones = [p.get("phone") for p in db.list_profiles_by_fpo(fpo_id) if p.get("phone")]
        elif role not in ("verifier", "admin"):
            return {"success": True, "pending": [], "message": "Your account is not linked to an FPO yet"}

        farms_q = sb.table("farms").select("*").ilike("status", "pending")
        if member_phones is not None:
            if not member_phones:
                return {"success": True, "pending": []}
            farms_q = farms_q.in_("owner_phone", member_phones)
        farms = (farms_q.execute().data) or []
        phones = list({f.get("owner_phone") for f in farms if f.get("owner_phone")})
        owners = {}
        if phones:
            owners = {p.get("phone"): p for p in (sb.table("profiles").select("phone,name,village").in_("phone", phones).execute().data or [])}
        pending = []
        for f in farms:
            owner_info = owners.get(f.get("owner_phone")) or {}
            gj = f.get("geojson")
            gj_props = gj.get("properties", {}) if isinstance(gj, dict) else {}
            pending.append({
                "id": f.get("id"),
                "name": owner_info.get("name") or "Unknown Farmer",
                "phone": f.get("owner_phone"),
                "village": gj_props.get("village") or owner_info.get("village"),
                "farm_name": f.get("name"),
                "crop": f.get("crop_type"),
                "area_hectares": f.get("area_hectares"),
                "date": (f.get("created_at") or "")[:10],
            })
        return {"success": True, "pending": pending}
    except Exception as e:
        return {"success": False, "message": str(e), "pending": []}


@router.get("/flagged")
def get_fpo_flagged(current_user: dict = Depends(require_role("fpo", "verifier", "admin"))):
    sb = db._client()
    if not sb:
        return {"success": False, "message": "Database unavailable", "flagged": []}
    try:
        reviewer = _get_user(current_user.get("phone")) or {}
        role = current_user.get("role", "fpo")
        fpo_id = reviewer.get("fpo_id")
        member_phones = None
        if fpo_id:
            member_phones = [p.get("phone") for p in db.list_profiles_by_fpo(fpo_id) if p.get("phone")]
        elif role not in ("verifier", "admin"):
            return {"success": True, "flagged": [], "message": "Your account is not linked to an FPO yet"}

        farms_q = sb.table("farms").select("*").ilike("status", "flagged")
        if member_phones is not None:
            if not member_phones:
                return {"success": True, "flagged": []}
            farms_q = farms_q.in_("owner_phone", member_phones)
        farms = (farms_q.execute().data) or []
        phones = list({f.get("owner_phone") for f in farms if f.get("owner_phone")})
        owners = {}
        if phones:
            owners = {p.get("phone"): p for p in (sb.table("profiles").select("phone,name,village").in_("phone", phones).execute().data or [])}
        flagged = []
        for f in farms:
            owner_info = owners.get(f.get("owner_phone")) or {}
            curr_ndvi = float(f["ndvi"]) if f.get("ndvi") is not None else None
            last_ndvi = float(f["last_monitor_ndvi"]) if f.get("last_monitor_ndvi") is not None else None
            drop = round(last_ndvi - curr_ndvi, 3) if (last_ndvi is not None and curr_ndvi is not None) else None
            is_ndvi_alert = drop is not None and drop >= 0.15
            issue = (
                f"Sentinel-2 drop of {drop:.2f} (threshold ≥ 0.15 breached) — canopy loss alert"
                if is_ndvi_alert
                else "Flagged for review — check the farm's monitoring history and KYC records"
            )
            flagged.append({
                "id": f.get("id"),
                "farmer_name": owner_info.get("name") or "Unknown Farmer",
                "phone": f.get("owner_phone"),
                "farm_name": f.get("name"),
                "village": owner_info.get("village"),
                "area_hectares": f.get("area_hectares"),
                "crop": f.get("crop_type"),
                "ndvi": curr_ndvi,
                "last_monitor_ndvi": last_ndvi,
                "drop": drop,
                "threshold": 0.15,
                "issue": issue,
                "status": "FLAGGED",
                "date": (f.get("updated_at") or f.get("created_at") or "")[:10],
            })
        return {"success": True, "flagged": flagged}
    except Exception as e:
        return {"success": False, "message": str(e), "flagged": []}