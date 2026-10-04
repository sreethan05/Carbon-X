"""Corporate routes: corporate login, credit analysis."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from typing import Optional

from app.security import create_access_token, verify_password
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
    sb = db._client()
    if not sb:
        return {"success": False, "message": "Database unavailable"}
    try:
        rows = (sb.table("corporates").select("*").ilike("name", data.name.strip()).execute().data) or []
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