"""Corporate routes: login, profile, account settings, credit analysis."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.security import create_access_token, require_role, verify_password
from app import supabase_db as db
from app.services import corporate_settings as corporate_settings_service

router = APIRouter(prefix="/corporate", tags=["corporate"])


# ─── Models ───

class CorporateLoginModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    password: str


class CorporateSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_offsets_mt: float = Field(gt=0)


# ─── Endpoints ───

@router.post("/login")
def corporate_login(data: CorporateLoginModel):
    name = (data.name or "").strip()
    if not name or not data.password:
        return {"success": False, "message": "Corporate name and password are required"}

    sb = db._client()
    if not sb:
        # Demo mode fallback for seeded demo credentials when DB is unconfigured
        if name.lower() == "telangana sustainable agro pvt ltd" and data.password == "Corporate@2026":
            token = create_access_token({"c_id": 1, "name": "Telangana Sustainable Agro Pvt Ltd", "role": "buyer", "demo": True})
            return {
                "success": True,
                "token": token,
                "user": {"name": "Telangana Sustainable Agro Pvt Ltd", "role": "buyer", "c_id": 1, "demo": True},
            }
        return {"success": False, "message": "Database unavailable"}
    try:
        rows = (sb.table("corporates").select("*").ilike("name", name).execute().data) or []
        if not rows:
            return {"success": False, "message": "Unknown corporate account. Ask the platform admin to register your organisation."}
        row = rows[0]
        if not row.get("password_hash") or not verify_password(data.password, row["password_hash"]):
            return {"success": False, "message": "Incorrect password"}
        token = create_access_token({"c_id": row.get("c_id"), "name": row.get("name"), "role": "buyer"})
        return {
            "success": True, "token": token,
            "user": {"name": row.get("name"), "role": "buyer", "c_id": row.get("c_id")},
        }
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.get("/profile")
def corporate_profile(current_user: dict = Depends(require_role("buyer", "corporate", "admin"))):
    """Retrieve authenticated corporate organization profile."""
    return {
        "success": True,
        "corporate": {
            "c_id": current_user.get("c_id"),
            "name": current_user.get("name"),
            "role": current_user.get("role", "buyer"),
        },
    }


@router.get("/settings")
def get_corporate_settings(current_user: dict = Depends(require_role("buyer", "corporate", "admin"))):
    """Account-level preferences (decarbonization target) keyed to the buyer."""
    try:
        c_id = int(current_user.get("c_id") or 0)
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail="A corporate buyer session is required")
    if c_id <= 0:
        raise HTTPException(status_code=401, detail="A corporate buyer session is required")
    settings = corporate_settings_service.get_settings(c_id)
    return {
        "success": True,
        "settings": settings,
        "note": (
            "Self-declared target used for the buyer's progress view only. It is "
            "not a retirement or compliance record."
            if settings.get("storage") == "live_db"
            else "Database table not available; the target is stored in labelled in-memory demo storage until the migration is applied."
        ),
    }


@router.put("/settings")
def update_corporate_settings(
    data: CorporateSettingsUpdate,
    current_user: dict = Depends(require_role("buyer", "corporate", "admin")),
):
    """Persist account-level settings server-side across devices/sessions."""
    try:
        c_id = int(current_user.get("c_id") or 0)
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail="A corporate buyer session is required")
    if c_id <= 0:
        raise HTTPException(status_code=401, detail="A corporate buyer session is required")
    result = corporate_settings_service.set_settings(c_id, data.target_offsets_mt)
    if not result.get("success"):
        raise HTTPException(status_code=422, detail=result.get("message") or "Invalid settings")
    return {
        "success": True,
        "settings": {k: v for k, v in result.items() if k != "success"},
    }


@router.get("/credit-analysis")
def corporate_credit_analysis(current_user: dict = Depends(require_role("buyer", "corporate", "admin"))):
    """Corporate credit portfolio analysis and decarbonization reporting desk."""
    return {
        "success": True,
        "analysis": "Institutional portfolio decarbonization & ESG credit analysis",
        "c_id": current_user.get("c_id"),
        "name": current_user.get("name"),
    }