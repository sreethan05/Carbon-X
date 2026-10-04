"""Auth routes: phone OTP registration/login, JWT sessions, demo login."""
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, field_validator
from typing import Literal, Optional
import time
import uuid
from datetime import datetime, timedelta, timezone
import os

from app.security import (
    create_access_token,
    decode_token,
    get_current_user,
    get_current_user_optional,
    require_role,
    verify_password,
)
from app.phone_service import generate_otp, send_phone_otp
from app import supabase_db as db
from app import redis_store
from app import config as app_config
from app.services import credit_engine, ledger, market_store, split_engine
from app.services.kyc_service import analyse_document, validate_aadhaar

router = APIRouter(prefix="/auth", tags=["auth"])


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


def _save_user(user: dict):
    _require_database()
    db.upsert_profile(user)


def _get_user_farms(phone: str):
    _require_database()
    return db.get_farms(phone)


def _save_farm(farm: dict):
    _require_database()
    return db.insert_farm(farm)


def _store_otp(phone: str, otp: str):
    redis_store.store_otp(phone, otp)


def _verify_otp(phone: str, otp: str) -> bool:
    return redis_store.verify_otp(phone, otp)


def _clear_otp(phone: str):
    redis_store.clear_otp(phone)


def _polygon_area_hectares(geojson: dict) -> float:
    """Deprecated alias — canonical implementation is polygon_service.polygon_area_hectares."""
    from app.services.polygon_service import polygon_area_hectares as _canonical
    import math

    geometry = geojson.get("geometry", {})
    if geometry.get("type") != "Polygon":
        raise ValueError("GeoJSON must be a Polygon")
    rings = geometry.get("coordinates") or []
    ring = rings[0] if rings else []
    if len(ring) < 4:
        raise ValueError("Polygon must have at least 3 points")
    if ring[0] != ring[-1]:
        ring = [*ring, ring[0]]
    lat_mid = sum(float(point[1]) for point in ring[:-1]) / (len(ring) - 1)
    meters_per_degree_lng = 111320 * math.cos(math.radians(lat_mid))
    meters_per_degree_lat = 110540
    area_m2 = 0
    projected = [
        (float(lng) * meters_per_degree_lng, float(lat) * meters_per_degree_lat)
        for lng, lat in ring
    ]
    for i in range(len(projected) - 1):
        x1, y1 = projected[i]
        x2, y2 = projected[i + 1]
        area_m2 += x1 * y2 - x2 * y1
    return round(abs(area_m2) / 20000, 2)


def _sms_ready() -> bool:
    try:
        from app.phone_service import sms_configured
        return sms_configured()
    except Exception:
        return False


def _twilio_ready() -> bool:
    return _sms_ready()


def _env_bool(name: str, default: bool = True) -> bool:
    val = os.getenv(name, "").strip().lower()
    if val in ("0", "false", "no", ""):
        return False
    if val in ("1", "true", "yes"):
        return True
    return default


_OTP_SEND_WINDOW_SECONDS = 600
_OTP_SEND_MAX_PER_WINDOW = 3
_otp_send_log: dict = {}


def _otp_rate_limited(phone: str) -> bool:
    now = time.monotonic()
    hits = [t for t in _otp_send_log.get(phone, []) if now - t < _OTP_SEND_WINDOW_SECONDS]
    if len(hits) >= _OTP_SEND_MAX_PER_WINDOW:
        _otp_send_log[phone] = hits
        return True
    hits.append(now)
    _otp_send_log[phone] = hits
    return False


def _send_otp_flow(phone: str):
    if _otp_rate_limited(phone):
        return {
            "success": False,
            "message": "Too many OTP requests for this number. Please wait 10 minutes and try again.",
        }
    otp = generate_otp()
    _store_otp(phone, otp)
    sms_sent, msg = send_phone_otp(phone, otp)
    if sms_sent:
        return {"success": True, "message": "OTP sent to your phone via SMS"}
    dev_otp_allowed = _env_bool("CARBONX_ALLOW_DEV_OTP", False)
    if _sms_ready() or _twilio_ready():
        if dev_otp_allowed:
            return {
                "success": True,
                "message": f"SMS dispatch failed — exposing dev OTP: {msg}",
                "dev_otp": otp,
                "sms_error": msg,
            }
        return {"success": False, "message": msg}
    return {"success": True, "message": "OTP generated (dev mode)", "dev_otp": otp}


def _user_response(user: dict, phone: str):
    return {
        "phone": phone,
        "name": user.get("name", ""),
        "role": user.get("role", "farmer"),
        "state": user.get("state", ""),
        "district": user.get("district", ""),
        "village": user.get("village", ""),
        "upi": user.get("upi", ""),
        "email": user.get("email", ""),
        "aadhaar_last4": user.get("aadhaar_last4") or user.get("aadhaar", ""),
        "fpo_id": user.get("fpo_id"),
        "preferred_language": user.get("preferred_language", "en"),
    }


# ─── Models ───

class SendOtpModel(BaseModel):
    phone: str


class RegisterModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    phone: str
    otp: str
    name: str
    aadhaar: str
    state: str
    district: str
    village: str
    upi: str = ""
    email: Optional[str] = ""
    role: Optional[Literal["farmer", "buyer", "fpo", "verifier", "admin"]] = "farmer"
    preferred_language: Optional[str] = "en"
    otp_verification_token: Optional[str] = ""


class LoginOtpModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    phone: str
    otp: str


class RegistrationOtpVerifyModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    phone: str
    otp: str


class CorporateLoginModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    password: str


# ─── Endpoints ───

@router.post("/send-otp")
def send_otp(data: SendOtpModel):
    try:
        phone = data.phone.strip().replace(" ", "")
        if len(phone) != 10 or not phone.isdigit():
            return {"success": False, "message": "Enter a valid 10-digit phone number"}
        return _send_otp_flow(phone)
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.post("/register/verify-otp")
def verify_registration_otp(data: RegistrationOtpVerifyModel):
    try:
        phone = data.phone.strip().replace(" ", "")
        otp = data.otp.strip()
        if len(phone) != 10 or not phone.isdigit():
            return {"success": False, "message": "Enter a valid 10-digit phone number"}
        if len(otp) != 6 or not otp.isdigit():
            return {"success": False, "message": "Enter the complete 6-digit OTP"}
        if not _verify_otp(phone, otp):
            return {"success": False, "message": "Invalid or expired OTP"}

        verification_token = create_access_token(
            {
                "phone": phone,
                "purpose": "registration_otp_verified",
            },
            expires_delta=timedelta(minutes=30),
        )
        return {
            "success": True,
            "message": "OTP verified",
            "verification_token": verification_token,
        }
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.post("/register")
def register(data: RegisterModel):
    try:
        phone = data.phone.strip().replace(" ", "")
        if not validate_aadhaar(data.aadhaar):
            return {"success": False, "message": "Enter a valid 12-digit Aadhaar number"}
        token_payload = decode_token(data.otp_verification_token) if data.otp_verification_token else None
        token_verified = bool(
            token_payload
            and token_payload.get("purpose") == "registration_otp_verified"
            and token_payload.get("phone") == phone
        )
        if not token_verified and not _verify_otp(phone, data.otp):
            return {"success": False, "message": "Invalid or expired OTP"}
        existing = _get_user(phone)
        lang = (data.preferred_language or "en")[:2]
        role = data.role or "farmer"
        if existing:
            profile_fields = {
                "name": data.name or existing.get("name"),
                "state": data.state,
                "district": data.district,
                "village": data.village,
                "upi": data.upi,
                "aadhaar_last4": data.aadhaar[-4:],
                "preferred_language": lang,
                "role": role,
            }
            if data.email:
                profile_fields["email"] = data.email.strip().lower()
            db.update_profile(phone, profile_fields)
            user = _get_user(phone)
            token = create_access_token({"phone": phone, "name": user.get("name", ""), "role": user.get("role", "farmer")})
            return {
                "success": True,
                "message": "Profile updated, logged in",
                "token": token,
                "user": _user_response(user, phone),
            }
        user = {
            "phone": phone,
            "name": data.name,
            "aadhaar_last4": data.aadhaar[-4:],
            "state": data.state,
            "district": data.district,
            "village": data.village,
            "upi": data.upi,
            "preferred_language": lang,
            "role": role,
        }
        if data.email:
            user["email"] = data.email.strip().lower()
        _save_user(user)
        token = create_access_token({"phone": phone, "name": data.name, "role": role})
        return {
            "success": True,
            "message": "Registration successful",
            "token": token,
            "user": _user_response(user, phone),
        }
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.post("/login/send-otp")
def login_send_otp(data: SendOtpModel):
    try:
        phone = data.phone.strip().replace(" ", "")
        existing = _get_user(phone)
        if not existing:
            return {"success": False, "message": "Phone not registered. Please sign up first."}
        result = _send_otp_flow(phone)
        if result.get("success"):
            result["message"] = "OTP sent"
        return result
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.post("/login")
def login(data: LoginOtpModel):
    try:
        phone = data.phone.strip().replace(" ", "")
        if not _verify_otp(phone, data.otp):
            return {"success": False, "message": "Invalid or expired OTP"}
        user = _get_user(phone)
        if not user:
            return {"success": False, "message": "Phone not registered"}
        token = create_access_token({"phone": phone, "name": user.get("name", ""), "role": user.get("role", "farmer")})
        return {"success": True, "token": token, "user": _user_response(user, phone)}
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.post("/corporate/login")
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
            "success": True,
            "token": token,
            "user": {"name": row.get("name"), "role": "buyer", "c_id": row.get("c_id")},
        }
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.post("/fpo/login")
def fpo_login(data: dict):
    """FPO desk sign-in: registration_no → OTP to linked officer's phone."""
    from pydantic import BaseModel
    
    class FpoLoginModel(BaseModel):
        model_config = ConfigDict(extra="forbid")
        registration_no: str
    
    fpo_data = FpoLoginModel(**data)
    sb = db._client()
    if not sb:
        return {"success": False, "message": "Database not configured"}
    try:
        reg = fpo_data.registration_no.strip()
        fpos = (sb.table("fpos").select("id,name").eq("registration_no", reg).execute().data) or []
        if not fpos:
            return {"success": False, "message": "No FPO found for that registration number"}
        fpo = fpos[0]
        officers = (sb.table("profiles").select("phone,name")
                    .eq("role", "fpo").eq("fpo_id", fpo["id"]).execute().data) or []
        if not officers:
            return {"success": False, "message": "No verification officer is linked to this FPO yet. Ask the platform admin to link one."}
        officer = officers[0]
        flow = _send_otp_flow(officer["phone"])
        if not flow.get("success"):
            return {"success": False, "message": flow.get("message") or "Could not send OTP to the officer's phone"}
        masked = officer["phone"][:2] + "xxxxxx" + officer["phone"][-3:]
        return {
            "success": True,
            "message": f"OTP sent to the registered officer's phone ({masked}). Verify it on the farmer login to enter the FPO desk.",
            "fpo_name": fpo["name"],
            "officer_phone_masked": masked,
            "next": "login",
        }
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.post("/demo/login")
def demo_login(data: dict = None):
    if db.is_ready():
        return {"success": False, "message": "Demo login is only available in demo mode (database not configured)"}
    body = data or {}
    phone = str(body.get("phone") or "9000000001")
    from app import sample_data
    farmer = sample_data.FARMERS.get(phone)
    if not farmer:
        return {"success": False, "message": "Unknown demo farmer"}
    token = create_access_token({"phone": phone, "name": farmer["name"], "role": "farmer", "demo": True})
    return {
        "success": True,
        "demo_mode": True,
        "token": token,
        "user": {
            "phone": phone,
            "name": farmer["name"],
            "role": "farmer",
            "district": farmer.get("district"),
            "village": farmer.get("village"),
            "upi": farmer.get("upi"),
            "demo": True,
        },
        "message": f"Demo session started for {farmer['name']}",
    }


@router.get("/me")
def get_me(current_user: dict = Depends(get_current_user)):
    phone = current_user.get("phone")
    user = _get_user(phone)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    farms = _get_user_farms(phone)
    kyc = db.get_kyc_status(phone) if db.is_ready() else None
    return {"success": True, "user": _user_response(user, phone), "farms": farms, "kyc": kyc}


@router.patch("/profile")
def update_profile(
    name: Optional[str] = None,
    state: Optional[str] = None,
    district: Optional[str] = None,
    village: Optional[str] = None,
    upi: Optional[str] = None,
    role: Optional[Literal["farmer", "buyer", "fpo", "verifier", "admin"]] = None,
    preferred_language: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    try:
        phone = current_user.get("phone")
        fields = {k: v for k, v in {
            "name": name, "state": state, "district": district,
            "village": village, "upi": upi, "role": role,
            "preferred_language": preferred_language[:2] if preferred_language else None,
        }.items() if v is not None}
        if not fields:
            return {"success": False, "message": "No fields to update"}
        updated = db.update_profile(phone, fields)
        if not updated:
            return {"success": False, "message": "Profile update failed"}
        return {"success": True, "user": _user_response(updated, phone)}
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.get("/fpos")
def list_fpos(current_user: dict = Depends(get_current_user)):
    _require_database()
    return {"success": True, "fpos": db.list_fpos()}