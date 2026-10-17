"""Corporate routes: corporate login, credit analysis."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from app.security import create_access_token, require_role, verify_password
from app import supabase_db as db

router = APIRouter(prefix="/corporate", tags=["corporate"])


# ─── Models ───

class CorporateLoginModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    password: str


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


@router.get("/credit-analysis")
def corporate_credit_analysis(current_user: dict = Depends(require_role("buyer", "corporate", "admin"))):
    """Corporate credit portfolio analysis and decarbonization reporting desk."""
    return {
        "success": True,
        "analysis": "Institutional portfolio decarbonization & ESG credit analysis",
        "c_id": current_user.get("c_id"),
        "name": current_user.get("name"),
    }