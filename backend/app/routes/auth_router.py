"""Auth routes: phone OTP registration/login, JWT sessions, demo login."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from typing import Literal, Optional
from datetime import timedelta
import os
import re

from app.security import (
    create_access_token,
    decode_token,
    get_current_user,
)
from app.phone_service import generate_otp, send_phone_otp
from app import supabase_db as db
from app import redis_store
from app import config as app_config
from app.services.kyc_service import validate_aadhaar

router = APIRouter(tags=["auth"])


# ─── Helpers ───

def _require_database():
    if not db.is_ready():
        raise HTTPException(
            status_code=503,
            detail="Database is not configured. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in backend/.env.",
        )


def _normalize_phone(phone: str) -> str:
    """Normalize phone number to 10 digits (strips +91, 0 prefix, spaces, symbols)."""
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) > 10:
        digits = digits[-10:]
    return digits


def _get_user(phone: str):
    _require_database()
    return db.get_profile(phone)


def _save_user(user: dict):
    _require_database()
    db.upsert_profile(user)


def _get_user_farms(phone: str):
    _require_database()
    return db.get_farms(phone)


def _store_otp(phone: str, otp: str):
    redis_store.store_otp(phone, otp)


def _verify_otp(phone: str, otp: str) -> bool:
    return redis_store.verify_otp(phone, otp)


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


def _otp_rate_limited(phone: str) -> bool:
    """Distributed sliding-window OTP-send limiter (Redis ZSET with in-process
    memory fallback) — one implementation shared with redis_store."""
    return redis_store.otp_send_rate_limited(
        phone,
        max_sends=app_config.OTP_SEND_MAX_PER_WINDOW,
        window_seconds=app_config.OTP_SEND_WINDOW_SECONDS,
    )


def _send_otp_flow(phone: str):
    if _otp_rate_limited(phone):
        return {
            "success": False,
            "message": ("Too many OTP requests for this number. Please wait "
                        f"{app_config.OTP_SEND_WINDOW_SECONDS // 60} minutes and try again."),
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
    model_config = ConfigDict(extra="forbid")
    phone: str


class RegisterModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    phone: str
    otp: Optional[str] = ""
    name: str
    aadhaar: str
    state: str
    district: str
    village: str
    upi: str = ""
    email: Optional[str] = ""
    # Self-registration is farmer-only: privileged roles (fpo/verifier/admin)
    # are never assignable through the public API. Keep the field so existing
    # clients that send role="farmer" don't break, but reject anything else.
    role: Optional[Literal["farmer"]] = "farmer"
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


class FpoLoginModel(BaseModel):
    model_config = ConfigDict(extra="ignore")
    registration_no: str
    password: Optional[str] = None


class DemoLoginModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    phone: Optional[str] = "9000000001"


class UpdateProfileModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Optional[str] = None
    state: Optional[str] = None
    district: Optional[str] = None
    village: Optional[str] = None
    upi: Optional[str] = None
    email: Optional[str] = None
    # NOTE: no role field — role changes require an admin-managed process,
    # never a self-service PATCH.
    preferred_language: Optional[str] = None


# ─── Endpoints ───

@router.post("/send-otp")
def send_otp(data: SendOtpModel):
    try:
        phone = _normalize_phone(data.phone)
        if len(phone) != 10:
            return {"success": False, "message": "Enter a valid 10-digit phone number"}
        return _send_otp_flow(phone)
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.post("/register/verify-otp")
def verify_registration_otp(data: RegistrationOtpVerifyModel):
    try:
        phone = _normalize_phone(data.phone)
        otp = data.otp.strip()
        if len(phone) != 10:
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
        phone = _normalize_phone(data.phone)
        if len(phone) != 10:
            return {"success": False, "message": "Enter a valid 10-digit phone number"}
        clean_aadhaar = re.sub(r"\D", "", data.aadhaar or "")
        if not validate_aadhaar(clean_aadhaar):
            return {"success": False, "message": "Enter a valid 12-digit Aadhaar number"}
        token_payload = decode_token(data.otp_verification_token) if data.otp_verification_token else None
        token_verified = bool(
            token_payload
            and token_payload.get("purpose") == "registration_otp_verified"
            and token_payload.get("phone") == phone
        )
        if not token_verified and not _verify_otp(phone, (data.otp or "").strip()):
            return {"success": False, "message": "Invalid or expired OTP"}
        existing = _get_user(phone)
        lang = (data.preferred_language or "en")[:2]
        if existing:
            profile_fields = {
                "name": data.name.strip() if data.name else existing.get("name"),
                "state": data.state.strip() if data.state else existing.get("state"),
                "district": data.district.strip() if data.district else existing.get("district"),
                "village": data.village.strip() if data.village else existing.get("village"),
                "upi": (data.upi or "").strip(),
                "aadhaar_last4": clean_aadhaar[-4:],
                "preferred_language": lang,
                # NOTE: role intentionally not updated on re-registration —
                # privileged roles (fpo/verifier/admin) must never be
                # overwritten (or granted) by the public register endpoint.
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
            "name": data.name.strip(),
            "aadhaar_last4": clean_aadhaar[-4:],
            "state": data.state.strip(),
            "district": data.district.strip(),
            "village": data.village.strip(),
            "upi": (data.upi or "").strip(),
            "preferred_language": lang,
            "role": "farmer",
        }
        if data.email:
            user["email"] = data.email.strip().lower()
        _save_user(user)
        token = create_access_token({"phone": phone, "name": user["name"], "role": "farmer"})
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
        phone = _normalize_phone(data.phone)
        if len(phone) != 10:
            return {"success": False, "message": "Enter a valid 10-digit phone number"}
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
        phone = _normalize_phone(data.phone)
        otp = data.otp.strip()
        if len(phone) != 10:
            return {"success": False, "message": "Enter a valid 10-digit phone number"}
        if not _verify_otp(phone, otp):
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


@router.post("/fpo/login")
def fpo_login(data: FpoLoginModel):
    """FPO desk sign-in: registration_no → OTP to linked officer's phone.

    Accepts extra fields (older clients send password) — only the
    registration number is used; auth happens through the standard OTP step.
    """
    reg = data.registration_no.strip()
    if not reg:
        return {"success": False, "message": "Registration number is required"}
    sb = db._client()
    if not sb:
        # Demo fallback when database is not configured
        if reg.lower() in ("fpo-tg-001", "fpo-khammam", "khammam fpo", "fpo001"):
            demo_phone = "9000000001"
            flow = _send_otp_flow(demo_phone)
            masked = demo_phone[:2] + "xxxxxx" + demo_phone[-3:]
            return {
                "success": True,
                "message": f"OTP sent to the registered officer's phone ({masked}). Verify it on the farmer login to enter the FPO desk.",
                "fpo_name": "Khammam Farmer Producer Org",
                "officer_phone_masked": masked,
                "next": "login",
                "dev_otp": flow.get("dev_otp"),
            }
        return {"success": False, "message": "Database not configured"}
    try:
        fpos = (sb.table("fpos").select("id,name").ilike("registration_no", reg).execute().data) or []
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
        phone = officer.get("phone", "")
        masked = (phone[:2] + "xxxxxx" + phone[-3:]) if len(phone) >= 5 else "xxxxxx"
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
def demo_login(data: Optional[DemoLoginModel] = None):
    if db.is_ready():
        return {"success": False, "message": "Demo login is only available in demo mode (database not configured)"}
    phone = _normalize_phone((data.phone if data else None) or "9000000001")
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
    role = current_user.get("role", "farmer")
    if role == "buyer":
        c_id = current_user.get("c_id")
        name = current_user.get("name", "Corporate Buyer")
        return {
            "success": True,
            "user": {"name": name, "role": "buyer", "c_id": c_id},
            "farms": [],
            "kyc": None,
        }
    if current_user.get("demo") or not db.is_ready():
        phone = current_user.get("phone") or "9000000001"
        from app import sample_data
        farmer = sample_data.FARMERS.get(phone) or {"name": current_user.get("name", "Demo Farmer")}
        sample_farms = [
            {
                "id": f["key"],
                "name": f["name"],
                "owner_phone": phone,
                "crop_type": f["crop"],
                "area_hectares": f["area"],
                "carbon_tonnes": f["carbon"],
                "biodiversity_score": f["score"],
                "total_credits": round(float(f["carbon"]) * 0.8 + float(f["score"]) * 0.02, 2),
                "ndvi": f["ndvi"],
                "evi": f["evi"],
                "status": "Verified",
                "badge": "REGISTRY",
                "geojson": sample_data.farm_geojson(),
            }
            for f in sample_data.FARMS if f["phone"] == phone
        ]
        return {
            "success": True,
            "user": {
                "phone": phone,
                "name": farmer.get("name", "Demo Farmer"),
                "role": role,
                "district": farmer.get("district", "Khammam"),
                "village": farmer.get("village", "Bonakal"),
                "upi": farmer.get("upi"),
                "demo": True,
            },
            "farms": sample_farms,
            "kyc": {"status": "VERIFIED", "extracted_fields": {"badge": "REGISTRY"}},
        }
    phone = current_user.get("phone")
    if not phone:
        raise HTTPException(status_code=404, detail="User not found")
    user = _get_user(phone)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    farms = _get_user_farms(phone)
    kyc = db.get_kyc_status(phone) if db.is_ready() else None
    return {"success": True, "user": _user_response(user, phone), "farms": farms, "kyc": kyc}


@router.patch("/profile")
def update_profile(data: UpdateProfileModel, current_user: dict = Depends(get_current_user)):
    try:
        phone = current_user.get("phone")
        if not phone:
            return {"success": False, "message": "User phone not found in session"}
        fields = {k: v for k, v in data.model_dump().items() if v is not None}
        if not fields:
            return {"success": False, "message": "No fields to update"}
        if "preferred_language" in fields and fields["preferred_language"]:
            fields["preferred_language"] = fields["preferred_language"][:2]
        if "email" in fields and fields["email"]:
            fields["email"] = fields["email"].strip().lower()
        if "name" in fields and fields["name"]:
            fields["name"] = fields["name"].strip()
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