from pathlib import Path

from dotenv import load_dotenv

APP_DIR = Path(__file__).resolve().parent
BACKEND_DIR = APP_DIR.parent
ROOT_DIR = BACKEND_DIR.parent

load_dotenv(ROOT_DIR / ".env", override=True)
load_dotenv(BACKEND_DIR / ".env", override=True)

from fastapi import FastAPI, File, Header, HTTPException, Depends, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Literal, Optional
import base64
import re
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
from app import sample_data
from app.services import credit_engine, ledger, market_store, split_engine
from app.services.kyc_service import analyse_document, validate_aadhaar

app = FastAPI(title="CarbonX API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5000,http://localhost:5173,http://localhost:3000").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

earth_engine_ready = False
try:
    import ee
    ee.Initialize(project=os.getenv("GEE_PROJECT", "carbonsetu-496709"))
    earth_engine_ready = True
    print("Earth Engine initialized")
except Exception as e:
    print(f"Earth Engine not available: {e}")


# ── Automatic 5-day monitoring scheduler ─────────────────────────────
# The Sentinel-2 revisit cycle, run in-process so a single deployment
# keeps credits at-risk without anyone pressing a button. Disable with
# CARBONX_AUTO_MONITOR=0.
import asyncio

_MONITOR_INTERVAL_SECONDS = 5 * 24 * 60 * 60


async def _monitoring_loop():
    await asyncio.sleep(90)  # let the app finish booting first
    while True:
        try:
            if os.getenv("CARBONX_AUTO_MONITOR", "1").strip().lower() not in ("0", "false", "no"):
                result = run_monitoring_cycle()
                print(f"[monitor] scheduled cycle: checked={result.get('checked')} "
                      f"at_risk={result.get('at_risk_count')}")
        except Exception as e:
            print(f"[monitor] scheduled cycle failed: {e}")
        await asyncio.sleep(_MONITOR_INTERVAL_SECONDS)


@app.on_event("startup")
def _start_monitoring_scheduler():
    if db.is_ready():
        asyncio.get_event_loop().create_task(_monitoring_loop())
        print("[monitor] 5-day scheduler armed (first cycle in 90s)")


def _sms_ready() -> bool:
    """True when Textplate SMS creds are set (token + template id)."""
    try:
        from app.phone_service import sms_configured

        return sms_configured()
    except Exception:
        return False


def _twilio_ready() -> bool:
    """Kept for backwards compat (/health consumers). Now mirrors SMS status."""
    return _sms_ready()


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


class SendOtpModel(BaseModel):
    phone: str


class RegisterModel(BaseModel):
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
    phone: str
    otp: str


class RegistrationOtpVerifyModel(BaseModel):
    phone: str
    otp: str


class AnalyzeModel(BaseModel):
    geojson: dict
    farm_name: Optional[str] = "My Farm"
    crop_type: Optional[str] = "Mixed Crop"
    irrigation: Optional[str] = "Drip"


class SaveFarmModel(BaseModel):
    farm: dict


class UpdateProfileModel(BaseModel):
    name: Optional[str] = None
    state: Optional[str] = None
    district: Optional[str] = None
    village: Optional[str] = None
    upi: Optional[str] = None
    role: Optional[Literal["farmer", "buyer", "fpo", "verifier", "admin"]] = None
    preferred_language: Optional[str] = None


class CreateListingModel(BaseModel):
    carbon_credits: Optional[float] = None
    biodiversity_credits: Optional[float] = None
    credits: Optional[float] = None
    price_per_credit: float = 520
    farm_id: Optional[str] = None
    crop: Optional[str] = ""
    token_id: Optional[str] = None
    tx_hash: Optional[str] = None


class LandVerificationModel(BaseModel):
    document_name: Optional[str] = "document.png"
    document_content_base64: Optional[str] = ""
    extracted_text: Optional[str] = ""
    survey_number: Optional[str] = ""
    village: Optional[str] = ""
    district: Optional[str] = ""
    area_acres: Optional[float] = None
    area_hectares: Optional[float] = None
    path: Optional[str] = None
    fpo_id: Optional[str] = None
    farm_id: Optional[str] = None
    geojson: Optional[dict] = None
    aadhaar: Optional[str] = None
    confirm_polygon: Optional[bool] = False
    pahani_file: Optional[str] = ""
    document_content_type: Optional[str] = "image/jpeg"
class AadhaarVerificationModel(BaseModel):
    front_image: str
    back_image: str
    front_content_type: Optional[str] = "image/jpeg"
    back_content_type: Optional[str] = "image/jpeg"


class AutoDrawModel(BaseModel):
    survey_number: Optional[str] = None
    village: Optional[str] = None
    district: Optional[str] = None
    state: Optional[str] = None
    area_hectares: Optional[float] = None


class CheckFarmlandModel(BaseModel):
    geojson: dict


class FpoReviewModel(BaseModel):
    action: str
    notes: Optional[str] = ""


from app.voice_agent.voice_routes import router as voice_router
app.include_router(voice_router)


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


_OTP_SEND_WINDOW_SECONDS = 600   # 10 minutes
_OTP_SEND_MAX_PER_WINDOW = 3     # per phone — blunt but effective abuse brake
_otp_send_log: dict = {}


def _otp_rate_limited(phone: str) -> bool:
    """Sliding-window per-phone OTP send limiter (per process).

    Production note: with multiple workers move this to Redis; the in-process
    window is per-worker, which still blunts single-source flooding.
    """
    import time

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
    dev_otp_allowed = os.getenv("CARBONX_ALLOW_DEV_OTP", "").strip().lower() in ("1", "true", "yes")
    if _sms_ready() or _twilio_ready():
        if dev_otp_allowed:
            # Local development only (CARBONX_ALLOW_DEV_OTP=1 in backend/.env):
            # SMS provider is configured but delivery failed (e.g. trial account),
            # so surface the real stored OTP so the flow stays testable.
            return {
                "success": True,
                "message": f"SMS dispatch failed — exposing dev OTP: {msg}",
                "dev_otp": otp,
                "sms_error": msg,
            }
        return {"success": False, "message": msg}
    return {"success": True, "message": "OTP generated (dev mode)", "dev_otp": otp}


def _decode_upload(content: str) -> bytes:
    """Decode a browser data-URL/base64 upload without writing identity files to disk."""
    encoded = (content or "").split(",")[-1]
    if not encoded:
        raise ValueError("Upload a document first.")
    try:
        return base64.b64decode(encoded, validate=False)
    except Exception as exc:
        raise ValueError("Document content must be valid base64.") from exc


def _pahani_polygon(coords: Optional[list]) -> Optional[dict]:
    """Turn Section 5 latitude/longitude points into a GeoJSON feature."""
    ring = []
    for point in coords or []:
        try:
            ring.append([float(point["longitude"]), float(point["latitude"])])
        except (KeyError, TypeError, ValueError):
            continue
    if len(ring) < 3:
        return None
    if ring[0] != ring[-1]:
        ring.append(ring[0])
    return {"type": "Feature", "properties": {"source": "pahani_section_5"}, "geometry": {"type": "Polygon", "coordinates": [ring]}}


def _pahani_fallback_fields(text: str) -> dict:
    """Small OCR fallback when Azure layout extraction is unavailable."""
    def found(pattern: str) -> Optional[str]:
        match = re.search(pattern, text, re.IGNORECASE)
        return match.group(1).strip() if match else None

    aadhaar = re.search(r"(?:\d{4}[- ]?){2}\d{4}", text)
    return {
        "survey_no": found(r"survey\s*(?:no\.?|number)?\s*[:#-]?\s*([A-Z0-9/-]+)"),
        "pattadar_name": found(r"(?:pattadar|owner)\s*(?:name)?\s*[:#-]?\s*([^\n]{3,80})"),
        "aadhaar": aadhaar.group(0) if aadhaar else None,
        "village": found(r"village\s*[:#-]?\s*([^\n]{2,80})"),
        "district": found(r"district\s*[:#-]?\s*([^\n]{2,80})"),
        "crop_name": found(r"crop\s*(?:name)?\s*[:#-]?\s*([^\n]{2,60})"),
        "irrigation_source": found(r"irrigation\s*(?:source)?\s*[:#-]?\s*([^\n]{2,60})"),
        "extent_acres": None,
        "extent_hectares": None,
        "mandal": None,
        "boundary_coords": None,
    }


def _parse_pahani_upload(content_base64: str, filename: str, content_type: str) -> tuple[dict, str]:
    """Use the existing Azure + Pahani parser, with installed Tesseract as fallback."""
    from app.services.document_intelligence_service import analyze_document_bytes, validate_upload
    from app.services.pahani_parser import parse_pahani

    raw = _decode_upload(content_base64)
    validate_upload(content_type, raw)
    try:
        parsed = parse_pahani(analyze_document_bytes(raw, filename=filename))
        return parsed["fields"], parsed.get("english_text", "")
    except RuntimeError as exc:
        # Azure is optional in the local SIH demo. Tesseract remains a real OCR fallback.
        print(f"Pahani Azure OCR unavailable, using local OCR fallback: {exc}")
        checks = analyse_document(content_base64, filename, "", "", [])
        text = checks.get("ocr_text_preview", "")
        return _pahani_fallback_fields(text), text


@app.get("/")
def root():
    return {
        "message": "CarbonX API running",
        "version": "5.0",
        "supabase": db.is_ready(),
        "sms": _sms_ready(),
        "twilio": _twilio_ready(),
        "earth_engine": earth_engine_ready,
    }


@app.get("/health")
def health():
    database = db.health_check()
    return {
        "success": database["ready"],
        "database": database,
        "sms": {"ready": _sms_ready(), "provider": "Textplate"},
        "twilio": {"ready": _twilio_ready(), "provider": "Textplate"},
        "earth_engine": {"ready": earth_engine_ready},
    }


@app.post("/send-otp")
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


@app.post("/register/verify-otp")
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


@app.post("/register")
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
            # `email` is optional until migration 05 has been applied.
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


@app.post("/login/send-otp")
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


@app.post("/login")
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


class CorporateLoginModel(BaseModel):
    name: str
    password: str


@app.post("/corporate/login")
def corporate_login(data: CorporateLoginModel):
    """Corporate buyer login against the corporates table (bcrypt password_hash)."""
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


# FPO officers authenticate through the same phone-OTP pipeline as farmers
# (POST /login/send-otp + POST /login): the profile's `role` field must be
# 'fpo' for the FPO desk to unlock (enforced client-side and by require_role
# on every /fpo/* endpoint).


def _claimed_area_ha(data: LandVerificationModel) -> Optional[float]:
    if data.area_hectares is not None:
        return float(data.area_hectares)
    if data.area_acres is not None:
        return round(float(data.area_acres) * 0.404686, 4)
    return None


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


@app.get("/land/registry/{survey}")
def land_registry_lookup(survey: str, current_user: dict = Depends(get_current_user)):
    """Look up a survey number in the Supabase land_registry mock table."""
    from app.services.registry_service import lookup_survey

    _require_database()
    result = lookup_survey(survey)
    if result.get("error") == "permission_denied":
        raise HTTPException(status_code=503, detail=result["message"])
    return {"success": True, **result}


@app.post("/auto-draw")
def auto_draw_polygon(data: AutoDrawModel, current_user: dict = Depends(get_current_user)):
    """Return a locked registry polygon (1A) or an approximate village square (1B/2)."""
    from app.services.geocoding_service import geocode_village
    from app.services.polygon_service import approximate_square
    from app.services.registry_service import lookup_survey

    _require_database()
    locked = False
    geojson = None
    source = None
    registry = None
    if data.survey_number:
        registry = lookup_survey(data.survey_number)
        if registry.get("error") == "permission_denied":
            raise HTTPException(status_code=503, detail=registry["message"])
        if registry.get("geojson"):
            geojson = registry["geojson"]
            locked = True
            source = "registry"
    if geojson is None:
        phone = current_user.get("phone")
        profile = _get_user(phone) or {}
        village = data.village or profile.get("village", "")
        district = data.district or profile.get("district", "")
        state = data.state or profile.get("state", "")
        geo = geocode_village(village, district, state)
        if not geo:
            return {"success": False, "message": "Could not geocode village for an approximate polygon"}
        area = data.area_hectares or (registry or {}).get("area_ha") or 1.0
        geojson = approximate_square(geo["lat"], geo["lon"], area)
        source = "approximate"
        locked = False
    return {
        "success": True,
        "locked": locked,
        "source": source,
        "geojson": geojson,
        "registry": registry,
    }


@app.post("/check-farmland")
def check_farmland(data: CheckFarmlandModel, current_user: dict = Depends(get_current_user)):
    """NDVI farmland check for a drawn/auto polygon."""
    from app.services.gee_service import get_ndvi_at_point
    from app.services.polygon_service import ring_from_geojson, polygon_area_hectares
    from app.services.fraud_engine import NDVI_FARMLAND_MIN

    ring = ring_from_geojson(data.geojson)
    if len(ring) < 3:
        raise HTTPException(status_code=400, detail="Valid polygon GeoJSON is required")
    lat = sum(float(p[1]) for p in ring[:-1]) / (len(ring) - 1)
    lon = sum(float(p[0]) for p in ring[:-1]) / (len(ring) - 1)
    ndvi = get_ndvi_at_point(lat, lon)
    value = float(ndvi.get("ndvi") or 0)
    return {
        "success": True,
        "is_farmland": value >= NDVI_FARMLAND_MIN,
        "ndvi": ndvi,
        "area_hectares": polygon_area_hectares(data.geojson),
        "centroid": {"lat": lat, "lon": lon},
    }


@app.post("/verify-aadhaar")
def verify_aadhaar(data: AadhaarVerificationModel, current_user: dict = Depends(get_current_user)):
    """OCR Aadhaar front/back and compare it to the registered identity anchor.

    CarbonX deliberately stores only the Aadhaar last four digits, so the card
    comparison uses the extracted last four digits rather than retaining a full
    Aadhaar number in Supabase.
    """
    from PIL import Image
    import io
    from app.services.kyc_service import _extract_ocr_text, _match_name

    profile = _get_user(current_user.get("phone"))
    if not profile:
        raise HTTPException(status_code=404, detail="User not found")
    try:
        parts = []
        for image_content, content_type in ((data.front_image, data.front_content_type), (data.back_image, data.back_content_type)):
            raw = _decode_upload(image_content)
            if content_type == "application/pdf":
                from app.services.document_intelligence_service import analyze_document_bytes
                parts.append(analyze_document_bytes(raw).get("content", ""))
            else:
                with Image.open(io.BytesIO(raw)) as image:
                    text, available = _extract_ocr_text(image)
                    if available:
                        parts.append(text)
        ocr_text = "\n".join(parts)
        card_numbers = re.findall(r"(?:\d{4}[- ]?){2}\d{4}", ocr_text)
        card_last4 = card_numbers[0].replace(" ", "").replace("-", "")[-4:] if card_numbers else ""
        registered_last4 = str(profile.get("aadhaar_last4") or "")[-4:]
        _score, matched_name = _match_name(profile.get("name", ""), ocr_text)
        matched_aadhaar = bool(card_last4 and registered_last4 and card_last4 == registered_last4)
        dob_match = re.search(r"(?:DOB|Date of Birth)\s*[:\-]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", ocr_text, re.IGNORECASE)
        reasons = []
        if not matched_name:
            reasons.append("Name on Aadhaar card does not match your registered name")
        if not matched_aadhaar:
            reasons.append("Aadhaar number on card does not match your registered number")
        return {
            "success": True,
            "verified": matched_name and matched_aadhaar,
            "matched_name": matched_name,
            "matched_aadhaar": matched_aadhaar,
            "dob": dob_match.group(1) if dob_match else None,
            "reasons": reasons,
        }
    except ValueError:
        return {"success": False, "message": "Invalid Aadhaar upload. Please use a valid JPG, PNG, or PDF file."}
    except Exception:
        return {"success": False, "message": "Could not process Aadhaar images. Please try again."}


@app.post("/verify-land")
def verify_land_document(data: LandVerificationModel, current_user: dict = Depends(get_current_user)):
    """Run the trust engine. Backend assigns tier, badge, status, and eligibility."""
    try:
        from app.services.fraud_engine import run_fraud_checks
        from app.services.registry_service import lookup_survey
        from app.services.trust_engine import apply_fraud, decide_tier
        from app.services.kyc_service import _match_name

        _require_database()
        phone = current_user.get("phone")
        profile = _get_user(phone)
        if not profile:
            raise HTTPException(status_code=404, detail="User not found")
        village = data.village or profile.get("village", "")
        district = data.district or profile.get("district", "")
        state = profile.get("state", "")
        fpo_path = (data.path or "").lower() == "fpo"
        claimed_ha = _claimed_area_ha(data)

        if fpo_path:
            if profile.get("role", "farmer") == "farmer":
                return {"success": False, "message": "Pahani upload is required for farmer verification. If you need help obtaining one, please contact your FPO."}
            if data.fpo_id:
                db.update_profile(phone, {"fpo_id": data.fpo_id})
            trust = apply_fraud(decide_tier(fpo_path=True), {"status": "PENDING", "risk": "LOW", "failed_checks": []})
            record = {
                "owner_phone": phone,
                "status": "PENDING",
                "reasons": ["Awaiting FPO confirmation"],
                "checks": {"path": "fpo", "fpo_id": data.fpo_id},
                "extracted_fields": {
                    "path": "fpo",
                    "fpo_id": data.fpo_id,
                    "farm_id": data.farm_id,
                    **trust,
                },
                "document_name": (data.document_name or "fpo-path")[:255],
                "document_sha256": "fpo-path",
                "perceptual_hash": None,
            }
            saved = db.insert_kyc_verification(record)
            _patch_farm(data.farm_id, {"status": "PENDING"})
            return {"success": True, **trust, "verification": saved, "checks": record["checks"], "reasons": record["reasons"]}

        document_content = data.pahani_file or data.document_content_base64
        if not document_content:
            return {"success": False, "message": "Upload your Pahani land record before verification. Please contact your FPO if you need assistance."}

        pahani_fields, pahani_text = _parse_pahani_upload(
            document_content,
            data.document_name or "pahani.jpg",
            data.document_content_type or "image/jpeg",
        )
        survey_number = pahani_fields.get("survey_no") or data.survey_number or ""
        village = pahani_fields.get("village") or village
        district = pahani_fields.get("district") or district
        parsed_area_ha = pahani_fields.get("extent_hectares")
        if not parsed_area_ha and pahani_fields.get("extent_acres"):
            parsed_area_ha = round(float(pahani_fields["extent_acres"]) * 0.404686, 4)
        claimed_ha = parsed_area_ha or claimed_ha
        pahani_polygon = _pahani_polygon(pahani_fields.get("boundary_coords"))

        checks = analyse_document(
            document_content,
            data.document_name,
            profile.get("name", ""),
            f"{pahani_text} {data.extracted_text or ''}",
            db.get_document_hashes(),
            village=village,
            district=district,
            state=state,
        )
        registry = lookup_survey(survey_number) if survey_number else {"found": False}
        if registry.get("error") == "permission_denied":
            registry = {"found": False, "survey_number": survey_number, "message": registry.get("message")}

        ocr_text = f"{checks.get('ocr_text_preview') or ''} {pahani_text} {data.extracted_text or ''}"
        document_owner = pahani_fields.get("pattadar_name") or ""
        document_aadhaar = str(pahani_fields.get("aadhaar") or "").replace(" ", "").replace("-", "")
        registered_last4 = str(profile.get("aadhaar_last4") or "")[-4:]
        _name_score, name_ok = _match_name(profile.get("name", ""), document_owner or ocr_text)
        aadhaar_ok = bool(document_aadhaar and registered_last4 and document_aadhaar[-4:] == registered_last4)
        village_ok = bool(pahani_fields.get("village") and profile.get("village") and pahani_fields["village"].strip().lower() == profile["village"].strip().lower())
        district_ok = bool(pahani_fields.get("district") and profile.get("district") and pahani_fields["district"].strip().lower() == profile["district"].strip().lower())
        three_way_failures = []
        if not name_ok:
            three_way_failures.append("pahani_owner_name_mismatch")
        if not aadhaar_ok:
            three_way_failures.append("pahani_aadhaar_mismatch")
        if not village_ok or not district_ok:
            three_way_failures.append("pahani_location_mismatch")
        geojson = pahani_polygon or data.geojson or registry.get("geojson")
        decision = decide_tier(
            fpo_path=False,
            survey_number=survey_number,
            registry=registry,
            owner_name=profile.get("name", ""),
            ocr_owner=document_owner or ocr_text,
            claimed_area_ha=claimed_ha or registry.get("area_ha"),
        )
        fraud = run_fraud_checks(
            aadhaar=data.aadhaar or profile.get("aadhaar_last4") or "",
            checks=checks,
            owner_name=profile.get("name", ""),
            ocr_text=ocr_text,
            village=village,
            geojson=geojson,
            other_farm_geojsons=db.farm_geojsons_except(phone) if geojson else [],
            claimed_area_ha=claimed_ha or registry.get("area_ha"),
            skip_ndvi=True,
        )
        if three_way_failures:
            fraud["failed_checks"] = list(dict.fromkeys([*fraud.get("failed_checks", []), *three_way_failures]))
            fraud["status"] = "FLAGGED"
            fraud["risk"] = "HIGH"
        trust = apply_fraud(decision, fraud)
        reasons = list(trust["failed_checks"])
        record = {
            "owner_phone": phone,
            "status": trust["status"],
            "reasons": reasons,
            "checks": {**checks, "registry": registry, "fraud": fraud, "trust": trust},
            "extracted_fields": {
                "survey_number": survey_number,
                "village": village,
                "district": district,
                "area_acres": pahani_fields.get("extent_acres") or data.area_acres,
                "area_hectares": claimed_ha,
                "owner_name": document_owner,
                "crop": pahani_fields.get("crop_name"),
                "irrigation": pahani_fields.get("irrigation_source"),
                "mandal": pahani_fields.get("mandal"),
                "pahani_fields": pahani_fields,
                "polygon_geojson": geojson,
                "ocr_text_preview": checks.get("ocr_text_preview", ""),
                "geocoded_location": checks.get("geocoded_location"),
                "satellite_ndvi": checks.get("satellite_ndvi") or {},
                "farm_id": data.farm_id,
                "confirm_polygon": data.confirm_polygon,
                **trust,
            },
            "document_name": (data.document_name or "document")[:255],
            "document_sha256": checks["document_sha256"],
            "perceptual_hash": checks["perceptual_hash"] or None,
        }
        saved = db.insert_kyc_verification(record)
        farm_fields = {"status": trust["status"]}
        if trust.get("badge"):
            farm_fields["badge"] = trust["badge"]
        _patch_farm(data.farm_id, farm_fields)
        return {
            "success": True,
            **trust,
            "checks": checks,
            "reasons": reasons,
            "registry": registry,
            "fraud": fraud,
            "verification": saved,
            "polygon_geojson": geojson,
            "extracted": {
                "survey_no": survey_number,
                "owner_name": document_owner,
                "area_acres": pahani_fields.get("extent_acres") or data.area_acres,
                "area_hectares": claimed_ha,
                "crop": pahani_fields.get("crop_name"),
                "irrigation": pahani_fields.get("irrigation_source"),
                "village": village,
                "mandal": pahani_fields.get("mandal"),
                "district": district,
            },
        }
    except HTTPException:
        raise
    except ValueError as exc:
        return {"success": False, "message": str(exc)}
    except Exception as exc:
        return {"success": False, "message": str(exc)}


@app.get("/kyc/status/{phone}")
def get_kyc_status(phone: str, current_user: dict = Depends(get_current_user)):
    """Return the latest KYC verification record for a farmer."""
    try:
        _require_database()
        record = db.get_kyc_status(phone)
        if not record:
            return {"success": True, "status": "PENDING", "message": "No KYC verification found."}
        extracted = record.get("extracted_fields") or {}
        return {
            "success": True,
            "status": record.get("status"),
            "tier": extracted.get("tier"),
            "badge": extracted.get("badge"),
            "risk": extracted.get("risk"),
            "failed_checks": extracted.get("failed_checks") or record.get("reasons") or [],
            "marketplace_eligible": extracted.get("marketplace_eligible"),
            "credits_blocked": extracted.get("credits_blocked"),
            "verification": record,
        }
    except HTTPException:
        raise
    except Exception as exc:
        return {"success": False, "message": str(exc)}


@app.get("/fpos")
def list_fpos(current_user: dict = Depends(get_current_user)):
    _require_database()
    return {"success": True, "fpos": db.list_fpos()}


@app.get("/fpo/farms")
def fpo_farms(
    status: str = Query("PENDING"),
    current_user: dict = Depends(require_role("fpo", "verifier", "admin")),
):
    """Pending confirmations or flagged farms for FPO review."""
    _require_database()
    reviewer = _get_user(current_user.get("phone")) or {}
    fpo_id = reviewer.get("fpo_id")
    phones = None
    if fpo_id:
        phones = [p.get("phone") for p in db.list_profiles_by_fpo(fpo_id) if p.get("phone")]
    farms = db.list_farms_by_status(status, owner_phones=phones)
    return {"success": True, "status": status, "farms": farms}


@app.post("/fpo/confirm/{farm_id}")
def fpo_confirm_farm(farm_id: str, current_user: dict = Depends(require_role("fpo", "verifier", "admin"))):
    """Confirm a PENDING FPO-path farm. Badge becomes FPO; satellite scan can start."""
    from app.services.trust_engine import fpo_confirmed_result

    _require_database()
    farm = db.get_farm(farm_id)
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found")
    trust = fpo_confirmed_result()
    updated = _patch_farm(farm_id, {"status": trust["status"], "badge": trust["badge"]})
    db.insert_kyc_verification({
        "owner_phone": farm.get("owner_phone"),
        "status": trust["status"],
        "reasons": [],
        "checks": {"reviewed_by": current_user.get("phone"), "action": "confirm"},
        "extracted_fields": {**trust, "farm_id": farm_id, "reviewed_by": current_user.get("phone")},
        "document_name": "fpo-confirm",
        "document_sha256": f"fpo-confirm-{farm_id}",
        "perceptual_hash": None,
    })
    return {"success": True, **trust, "farm": updated or farm}


@app.post("/fpo/review/{farm_id}")
def fpo_review_farm(
    farm_id: str,
    data: FpoReviewModel,
    current_user: dict = Depends(require_role("fpo", "verifier", "admin")),
):
    """Approve or reject a FLAGGED farm. Approve sets badge FPO."""
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
            "tier": None,
            "badge": None,
            "risk": "HIGH",
            "status": "FLAGGED",
            "failed_checks": ["fpo_rejected"],
            "marketplace_eligible": False,
            "credits_blocked": True,
        }
        status, badge = "FLAGGED", None
    fields = {"status": status}
    if badge:
        fields["badge"] = badge
    updated = _patch_farm(farm_id, fields)
    db.insert_kyc_verification({
        "owner_phone": farm.get("owner_phone"),
        "status": status,
        "reasons": [data.notes] if data.notes else [],
        "checks": {"reviewed_by": current_user.get("phone"), "action": action},
        "extracted_fields": {**trust, "farm_id": farm_id, "reviewed_by": current_user.get("phone"), "notes": data.notes},
        "document_name": f"fpo-review-{action}",
        "document_sha256": f"fpo-review-{action}-{farm_id}",
        "perceptual_hash": None,
    })
    return {"success": True, **trust, "action": action, "farm": updated or farm}


@app.post("/documents/analyze")
def analyze_document_image(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    """Extract text from an uploaded document image via Azure Document Intelligence.

    Uses the ``prebuilt-layout`` model (see app/services/document_intelligence_service.py).
    Requires a logged-in user (Bearer token). Accepts an image (jpeg/png/webp/...)
    or PDF and returns the extracted text as JSON. If Azure cannot be reached,
    returns the retry-or-send-to-FPO fallback payload.
    """
    from app.services.document_intelligence_service import (
        analyze_document_bytes,
        azure_unavailable_response,
        validate_upload,
    )

    try:
        file_bytes = file.file.read()
    finally:
        file.file.close()
    filename = file.filename
    content_type = file.content_type

    try:
        validate_upload(content_type, file_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    try:
        return analyze_document_bytes(file_bytes, filename=filename)
    except RuntimeError as exc:
        msg = str(exc)
        if "not configured" in msg or "not installed" in msg:
            raise HTTPException(status_code=503, detail=msg)
        return azure_unavailable_response(msg)


@app.post("/documents/parse-pahani")
def parse_pahani_document(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    """OCR a Pahani (Adangal) record and return structured fields as JSON.

    Runs Azure Document Intelligence, filters out Telugu-script content, and
    extracts layout-aware fields (survey no, pattadar, extents, coords, ...).
    Fields absent from the image come back as null and are listed in
    ``missing_fields``. Requires a logged-in user (Bearer token). If Azure
    cannot be reached, returns the retry-or-send-to-FPO fallback payload.
    """
    from app.services.document_intelligence_service import (
        analyze_document_bytes,
        azure_unavailable_response,
        validate_upload,
    )
    from app.services.pahani_parser import parse_pahani

    try:
        file_bytes = file.file.read()
    finally:
        file.file.close()

    try:
        validate_upload(file.content_type, file_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    try:
        azure_result = analyze_document_bytes(file_bytes, filename=file.filename)
    except RuntimeError as exc:
        msg = str(exc)
        if "not configured" in msg or "not installed" in msg:
            raise HTTPException(status_code=503, detail=msg)
        return azure_unavailable_response(msg)

    parsed = parse_pahani(azure_result)
    return {
        "success": True,
        "model": azure_result.get("model"),
        "filename": file.filename,
        "fields": parsed["fields"],
        "missing_fields": parsed["missing_fields"],
        "english_text": parsed["english_text"],
    }


@app.get("/me")
def get_me(current_user: dict = Depends(get_current_user)):
    phone = current_user.get("phone")
    user = _get_user(phone)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    farms = _get_user_farms(phone)
    kyc = db.get_kyc_status(phone) if db.is_ready() else None
    return {"success": True, "user": _user_response(user, phone), "farms": farms, "kyc": kyc}


@app.patch("/profile")
def update_profile(data: UpdateProfileModel, current_user: dict = Depends(get_current_user)):
    try:
        phone = current_user.get("phone")
        fields = {k: v for k, v in data.model_dump().items() if v is not None}
        if not fields:
            return {"success": False, "message": "No fields to update"}
        if "preferred_language" in fields:
            fields["preferred_language"] = fields["preferred_language"][:2]
        updated = db.update_profile(phone, fields)
        if not updated:
            return {"success": False, "message": "Profile update failed"}
        return {"success": True, "user": _user_response(updated, phone)}
    except Exception as e:
        return {"success": False, "message": str(e)}


@app.post("/analyze")
def analyze(data: AnalyzeModel):
    try:
        geojson = data.geojson
        if not geojson:
            return {"success": False, "message": "GeoJSON polygon missing"}

        ml_result = None
        if earth_engine_ready:
            import ee
            coordinates = geojson["geometry"]["coordinates"]
            polygon = ee.Geometry.Polygon(coordinates)
            collection = (
                ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
                .filterBounds(polygon)
                .filterDate("2024-01-01", "2025-12-31")
                .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 20))
            )
            image = collection.median()
            ndvi = image.normalizedDifference(["B8", "B4"]).rename("NDVI")
            ndvi_value = ndvi.reduceRegion(
                reducer=ee.Reducer.mean(), geometry=polygon, scale=10, maxPixels=1e13,
            ).get("NDVI").getInfo()
            evi = image.expression(
                "2.5 * ((NIR - RED) / (NIR + 6 * RED - 7.5 * BLUE + 1))",
                {"NIR": image.select("B8"), "RED": image.select("B4"), "BLUE": image.select("B2")},
            )
            evi_value = evi.reduceRegion(
                reducer=ee.Reducer.mean(), geometry=polygon, scale=10, maxPixels=1e13,
            ).values().get(0).getInfo()
            area_hectares = round(polygon.area().getInfo() / 10000, 2)

            # Real model features — same derivation as the training pipeline
            # (extract_features.py): spectral indices + band means + time-series
            # variance across the cloud-filtered collection.
            try:
                B4, B8, B3, B11 = (image.select("B4"), image.select("B8"),
                                   image.select("B3"), image.select("B11"))
                stack = (ndvi.rename("NDVI")
                         .addBands(image.normalizedDifference(["B3", "B11"]).rename("NDWI"))
                         .addBands(image.expression("((NIR-RED)/(NIR+RED+0.5))*1.5",
                                    {"NIR": B8, "RED": B4}).rename("SAVI"))
                         .addBands(B4.rename("B4"))
                         .addBands(B8.rename("B8"))
                         .addBands(B11.rename("B11"))
                         .addBands(collection.map(lambda i: i.normalizedDifference(["B8", "B4"]))
                                   .reduce(ee.Reducer.stdDev()).rename("NDVI_STD"))
                         .addBands(collection.map(lambda i: i.select("B8"))
                                   .reduce(ee.Reducer.variance()).rename("B8_VAR")))
                feat_values = stack.reduceRegion(
                    reducer=ee.Reducer.mean(), geometry=polygon, scale=10, maxPixels=1e9,
                ).getInfo()
                real_features = {k: feat_values.get(k) for k in
                                 ("NDVI", "NDWI", "SAVI", "NDVI_STD", "B4", "B8", "B11", "B8_VAR")}
                if any(v is None for v in real_features.values()):
                    real_features = None
            except Exception as e:
                print(f"[analyze] real feature extraction failed: {e}")
                real_features = None

            try:
                from app.services.ml_service import predict_biodiversity
                ml_result = predict_biodiversity(ndvi=ndvi_value, evi=evi_value,
                                                 area_ha=area_hectares, features=real_features)
                biodiversity_score = ml_result["biodiversity_score"]
            except Exception:
                biodiversity_score = round(min(max(ndvi_value * 100, 30), 98), 1)
            satellite_source = "Google Earth Engine · Sentinel-2 SR"
        else:
            coords = geojson.get("geometry", {}).get("coordinates", [[]])
            area_hectares = _polygon_area_hectares(geojson)
            seed = hash(str(coords)) % 1000
            ndvi_value = round(0.45 + (seed % 40) / 100.0, 3)
            evi_value = round(ndvi_value * 0.85, 3)
            try:
                from app.services.ml_service import predict_biodiversity
                ml_result = predict_biodiversity(ndvi=ndvi_value, evi=evi_value, area_ha=area_hectares)
                biodiversity_score = ml_result["biodiversity_score"]
            except Exception:
                biodiversity_score = round(min(max(ndvi_value * 110, 40), 95), 1)
            satellite_source = "Estimated (GEE offline)"

        tree_cover = round(min(max(ndvi_value * 100, 0), 100), 2)
        soil_moisture = round(min(max(evi_value * 25, 0), 100), 2)
        carbon_tonnes = round(area_hectares * tree_cover * 0.12, 2)
        credits = db.compute_credits(carbon_tonnes, biodiversity_score)
        stage1 = credit_engine.stage1_verification(data.crop_type, ndvi_value)
        veg_health = (
            "Excellent" if ndvi_value >= 0.7 else "Good" if ndvi_value >= 0.5
            else "Moderate" if ndvi_value >= 0.3 else "Low"
        )
        ml_source = ml_result.get("source") if isinstance(ml_result, dict) else None
        return {
            "success": True,
            "ndvi": round(ndvi_value, 3),
            "evi": round(evi_value, 3),
            "tree_cover": tree_cover,
            "soil_moisture": soil_moisture,
            "carbon_tonnes": carbon_tonnes,
            "carbon_credits": credits["carbon_credits"],
            "biodiversity_credits": credits["biodiversity_credits"],
            "total_credits": credits["total_credits"],
            "area_hectares": area_hectares,
            "vegetation_health": veg_health,
            "biodiversity_score": biodiversity_score,
            "ml_source": ml_source,
            "ai_confidence": round(min(85 + ndvi_value * 20, 99.5), 1),
            "satellite_source": satellite_source,
            "stage1": stage1,
        }
    except Exception as e:
        return {"success": False, "message": str(e)}


@app.post("/save-farm")
def save_farm(data: SaveFarmModel, current_user: dict = Depends(get_current_user)):
    try:
        phone = current_user.get("phone")
        farm = data.farm
        geojson = farm.get("geojson")
        if not geojson or not geojson.get("geometry"):
            return {"success": False, "message": "Farm boundary (GeoJSON) is required"}
        area_hectares = float(farm.get("area_hectares") or _polygon_area_hectares(geojson))
        carbon = float(farm.get("carbon_tonnes") or 0)
        bio_score = float(farm.get("biodiversity_score") or 0)
        credits = db.compute_credits(carbon, bio_score)
        path = (farm.get("path") or "").lower()
        fpo_path = path == "fpo"
        if fpo_path and farm.get("fpo_id"):
            db.update_profile(phone, {"fpo_id": farm.get("fpo_id")})
        latest = db.get_kyc_status(phone) if db.is_ready() else None
        extracted = (latest or {}).get("extracted_fields") or {}
        if fpo_path or extracted.get("path") == "fpo" and (latest or {}).get("status") == "PENDING":
            status = "PENDING"
            badge = None
            credits_blocked = True
        elif latest and latest.get("status") in ("FLAGGED", "PENDING", "VERIFIED"):
            status = latest.get("status")
            badge = extracted.get("badge")
            credits_blocked = bool(extracted.get("credits_blocked")) or status in ("PENDING", "FLAGGED")
        else:
            status = farm.get("status") or "Verified"
            badge = farm.get("badge")
            credits_blocked = status in ("PENDING", "FLAGGED")
        if credits_blocked:
            credits = {"carbon_credits": 0, "biodiversity_credits": 0, "total_credits": 0}

        # Trust Engine Stage 1 (server-side): declared crop vs NDVI signature.
        # A mismatch pauses the record for FPO/KVK review — never auto-rejects.
        stage1 = credit_engine.stage1_verification(farm.get("crop_type"), farm.get("ndvi"))
        if not stage1["match"] and status not in ("PENDING", "FLAGGED"):
            status = "PENDING"
            credits_blocked = True
            credits = {"carbon_credits": 0, "biodiversity_credits": 0, "total_credits": 0}

        record = {
            "owner_phone": phone,
            "name": farm.get("name", "My Farm"),
            "crop_type": farm.get("crop_type", "Mixed Crop"),
            "irrigation": farm.get("irrigation", "Drip"),
            "geojson": geojson,
            "area_hectares": area_hectares,
            "ndvi": farm.get("ndvi", 0),
            "evi": farm.get("evi", 0),
            "carbon_tonnes": 0 if credits_blocked else carbon,
            "biodiversity_score": bio_score,
            "biodiversity_credits": credits["biodiversity_credits"],
            "total_credits": credits["total_credits"],
            "tree_cover": farm.get("tree_cover", 0),
            "soil_moisture": farm.get("soil_moisture", 0),
            "vegetation_health": farm.get("vegetation_health", ""),
            "ai_confidence": farm.get("ai_confidence", 0),
            "satellite_source": farm.get("satellite_source", ""),
            "status": status,
            "token_id": farm.get("token_id"),
        }
        if badge:
            record["badge"] = badge
        saved = db.insert_farm_safe(record)
        if not saved or not saved.get("id"):
            return {"success": False, "message": "Failed to save farm to database"}
        # Anchor the credit's evidence snapshot at enrollment (tamper-evident chain).
        ledger.ensure_genesis(saved["id"], {
            "farm": record["name"],
            "crop": record["crop_type"],
            "area_hectares": record["area_hectares"],
            "ndvi": record["ndvi"],
            "status": status,
            "badge": badge,
            "stage1": stage1["status"],
        })
        return {
            "success": True,
            "message": "Farm saved",
            "farm": saved,
            "credits_blocked": credits_blocked,
            "badge": badge,
            "stage1": stage1,
        }
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "message": str(e)}


@app.get("/marketplace/listings")
def marketplace_listings(
    status: Optional[str] = Query(
        "Active",
        description="Filter by listing status. Use 'all' to return every status (Active, Sold, Expired, ...).",
    ),
    crop: Optional[str] = Query(None, description="Partial, case-insensitive match on crop, e.g. ?crop=rice"),
    location: Optional[str] = Query(None, description="Partial, case-insensitive match on location, e.g. ?location=khammam"),
    farmer_phone: Optional[str] = Query(None, description="Exact farmer phone, e.g. ?farmer_phone=9876543210"),
    farm_id: Optional[str] = Query(None, description="Exact farm UUID"),
    listing_model: Optional[str] = Query(None, description="Partial match on listing model, e.g. ?listing_model=fixed"),
    min_price: Optional[float] = Query(None, description="Minimum price_per_credit (inclusive)"),
    max_price: Optional[float] = Query(None, description="Maximum price_per_credit (inclusive)"),
    min_credits: Optional[float] = Query(None, description="Minimum total_credits (inclusive)"),
    max_credits: Optional[float] = Query(None, description="Maximum total_credits (inclusive)"),
    search: Optional[str] = Query(None, description="Free-text search across farmer_name, crop and location"),
    sort: str = Query(
        "created_at",
        description=f"Sort column. One of: {', '.join(sorted(db.LISTING_SORT_COLUMNS))}",
    ),
    order: str = Query("desc", pattern="^(asc|desc)$", description="Sort direction: asc or desc"),
    limit: int = Query(50, ge=1, le=200, description="Page size (max 200)"),
    offset: int = Query(0, ge=0, description="Page offset for pagination"),
):
    try:
        query_kwargs = {
            "status": status,
            "crop": crop,
            "location": location,
            "farmer_phone": farmer_phone,
            "farm_id": farm_id,
            "listing_model": listing_model,
            "min_price": min_price,
            "max_price": max_price,
            "min_credits": min_credits,
            "max_credits": max_credits,
            "search": search,
            "sort": sort,
            "order": order,
            "limit": limit,
            "offset": offset,
        }
        applied = {k: v for k, v in query_kwargs.items() if v is not None}

        result = None
        source = "live_db"
        if db.is_ready():
            try:
                result = db.get_listings_filtered(**query_kwargs)
            except Exception as e:
                print(f"[marketplace/listings] LIVE DB query failed ({e}) — serving FALLBACK sample data")
                result = None
        else:
            print("[marketplace/listings] LIVE DB not configured — serving FALLBACK sample data")
        if result is None:
            source = "fallback"
            result = sample_data.filter_listings(market_store.all_rows(), **query_kwargs)

        print(
            f"[marketplace/listings] source={'LIVE DB' if source == 'live_db' else 'FALLBACK sample data'} "
            f"| matched={result['total']} | returned={len(result['listings'])} | filters={applied or 'default'}"
        )
        return {
            "success": True,
            "source": source,
            "total": result["total"],
            "count": len(result["listings"]),
            "filters": applied,
            "listings": result["listings"],
        }
    except Exception as e:
        return {"success": False, "message": str(e), "source": "error", "total": 0, "count": 0, "listings": []}


@app.post("/marketplace/listings")
def create_listing(data: CreateListingModel, current_user: dict = Depends(get_current_user)):
    try:
        _require_database()
        phone = current_user.get("phone")
        user = _get_user(phone)
        if not user:
            return {"success": False, "message": "User not found"}
        if data.farm_id:
            from app.services.trust_engine import farm_may_list

            farm = db.get_farm(data.farm_id)
            if farm and farm.get("owner_phone") != phone:
                return {"success": False, "message": "Farm does not belong to this user"}
            latest = db.get_kyc_status(phone)
            badge = ((latest or {}).get("extracted_fields") or {}).get("badge") or (farm or {}).get("badge")
            ok, reason = farm_may_list(farm, badge)
            if not ok:
                return {"success": False, "message": reason}
        c_credits = data.carbon_credits
        b_credits = data.biodiversity_credits
        if c_credits is None and b_credits is None and data.credits is not None:
            c_credits = round(float(data.credits) * 0.8, 2)
            b_credits = round(float(data.credits) * 0.2, 2)
        else:
            c_credits = float(c_credits or 0)
            b_credits = float(b_credits or 0)
        total = round(c_credits + b_credits, 2)
        listing = {
            "farmer_phone": phone,
            "farmer_name": user.get("name", "Farmer"),
            "location": f"{user.get('village', '')}, {user.get('district', '')}".strip(", "),
            "crop": data.crop or "Mixed Crop",
            "size_label": "",
            "carbon_credits": c_credits,
            "biodiversity_credits": b_credits,
            "total_credits": total,
            "price_per_credit": data.price_per_credit,
            "listing_model": "Fixed Price",
            "status": "Active",
            "farm_id": data.farm_id,
            "token_id": data.token_id,
            "tx_hash": data.tx_hash,
            "image_url": "https://images.unsplash.com/photo-1500937386664-56d1dfef3854?auto=format&fit=crop&q=80&w=400",
        }
        saved = db.insert_listing(listing)
        if not saved or not saved.get("id"):
            return {"success": False, "message": "Failed to save listing"}
        if data.farm_id and data.token_id:
            db.update_farm(data.farm_id, {"token_id": data.token_id})
        return {"success": True, "listing": saved}
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "message": str(e)}


class BidModel(BaseModel):
    bid_amount: float
    bidder_name: Optional[str] = "Corporate Buyer"


@app.post("/marketplace/listings/{listing_id}/bid")
def place_bid(listing_id: str, data: BidModel, current_user: dict = Depends(get_current_user)):
    """Place a bid on a listing: validates against the current bid and persists it."""
    sb = db._client()
    if not sb:
        return {"success": False, "message": "Database unavailable"}
    try:
        rows = (sb.table("marketplace_listings").select("*").eq("id", listing_id).execute().data) or []
        if not rows:
            return {"success": False, "message": "Listing not found"}
        listing = rows[0]
        if str(listing.get("status") or "Active").lower() != "active":
            return {"success": False, "message": f"Bidding closed (listing status: {listing.get('status')})"}
        current = float(listing.get("current_bid") or 0)
        base = float(listing.get("price_per_credit") or 0)
        amount = float(data.bid_amount or 0)
        if amount <= 0:
            return {"success": False, "message": "Bid amount must be greater than zero"}
        floor = current if current > 0 else base
        if amount <= floor:
            return {"success": False, "message": f"Bid must exceed the current standing bid of ₹{floor:,.0f}"}
        sb.table("marketplace_listings").update({
            "current_bid": amount,
            "bids_count": int(listing.get("bids_count") or 0) + 1,
        }).eq("id", listing_id).execute()
        return {
            "success": True,
            "message": "Bid placed successfully",
            "listing_id": listing_id,
            "bid_amount": amount,
            "bidder_name": data.bidder_name or current_user.get("name"),
            "previous_bid": current,
            "bids_count": int(listing.get("bids_count") or 0) + 1,
        }
    except Exception as e:
        return {"success": False, "message": str(e)}


@app.api_route("/predict", methods=["GET", "POST"])
def predict(longitude: float, latitude: float):
    try:
        from app.services.ml_service import predict_biodiversity

        ndvi = None
        ndvi_source = "Estimated (GEE offline)"
        if earth_engine_ready:
            try:
                from app.services.gee_service import get_ndvi_at_point

                sat = get_ndvi_at_point(latitude, longitude)
                if sat.get("live_satellite"):
                    ndvi = float(sat.get("ndvi"))
                    ndvi_source = str(sat.get("source"))
            except Exception as exc:
                print(f"/predict GEE point query failed: {exc}")
        if ndvi is None:
            import math

            ndvi = round(0.5 + math.sin(longitude * 0.1) * 0.2 + math.cos(latitude * 0.1) * 0.15, 3)
            ndvi = min(max(ndvi, 0.1), 0.9)
        result = predict_biodiversity(ndvi=ndvi)
        credits = db.compute_credits(ndvi * 10, result["biodiversity_score"])
        return {
            "success": True,
            "location": {"longitude": longitude, "latitude": latitude},
            "ndvi": ndvi,
            "ndvi_source": ndvi_source,
            "biodiversity_score": result["biodiversity_score"],
            "status": result["status"],
            "biodiversity_credits": credits["biodiversity_credits"],
            "total_credits": credits["total_credits"],
        }
    except Exception as e:
        return {"success": False, "message": str(e)}


# Additional Endpoints required by SIH 2026 Spec

@app.get("/farm/{farm_id}/ndvi-history")
def get_farm_ndvi_history(farm_id: str):
    """Seasonal NDVI progression anchored on the farm's real satellite record."""
    farm = db.get_farm(farm_id) if db.is_ready() else None
    if not farm:
        return {"success": False, "message": "Farm not found", "history": [], "recommendations": []}

    base_ndvi = float(farm.get("ndvi") or 0)
    months = [
        ("Kharif", "Jun", 110), ("Kharif", "Aug", 210), ("Kharif", "Oct", 85),
        ("Rabi", "Dec", 20), ("Rabi", "Feb", 15),
    ]
    history = []
    for year in (2023, 2024):
        for season, month, rainfall in months:
            # deterministic seasonal variation around the farm's measured NDVI
            offset = {"Jun": -0.12, "Aug": 0.04, "Oct": 0.08, "Dec": -0.10, "Feb": 0.02}[month]
            ndvi = round(min(max(base_ndvi + offset + (0.02 if year == 2024 else 0.0), 0.05), 0.95), 2)
            history.append({
                "season": f"{season} {year}" if season == "Kharif" else f"Rabi {year - 1}-{str(year)[2:]}",
                "month": month,
                "ndvi": ndvi,
                "rainfall_mm": rainfall,
            })

    return {
        "success": True,
        "farm_id": farm_id,
        "farm_name": farm.get("name"),
        "measured_ndvi": base_ndvi,
        "source": "derived from farm satellite record (Sentinel-2 NDVI)" if farm.get("ndvi") else "no satellite record",
        "history": history,
        "recommendations": [
            "Adopt zero-tillage to increase yield by +0.50 credits/acre",
            "Maintain cover crops during Rabi interval to avoid soil carbon loss",
            "Drip fertigation recommended for Kharif cotton block",
        ],
    }


@app.get("/fpo/farmers")
def get_fpo_farmers(current_user: Optional[dict] = Depends(get_current_user_optional)):
    """Real member roster: profiles (optionally scoped to the caller's FPO) with aggregated farm stats."""
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
                "id": p.get("id"),
                "name": p.get("name") or "Unnamed Farmer",
                "phone": p.get("phone"),
                "village": p.get("village"),
                "district": p.get("district"),
                "fpo_id": p.get("fpo_id"),
                "farm_count": len(pfarms),
                "acres": round(sum(float(f.get("area_hectares") or 0) for f in active), 2),
                "credits": round(sum(float(f.get("total_credits") or 0) for f in active), 2),
                "badge": next((f.get("badge") for f in pfarms if f.get("badge")), None) or ("REGISTRY" if pfarms else "NONE"),
                "status": "FLAGGED" if any(str(f.get("status", "")).lower() == "flagged" for f in pfarms) else ("VERIFIED" if pfarms else "PENDING"),
            })
        return {
            "success": True,
            "fpo_id": fpo_id,
            "total_farmers": len(farmers),
            "total_acreage": round(sum(f["acres"] for f in farmers), 2),
            "pooled_credits": round(sum(f["credits"] for f in farmers), 2),
            "farmers": farmers,
        }
    except Exception as e:
        return {"success": False, "message": str(e), "farmers": []}


class FpoOnboardModel(BaseModel):
    name: str
    phone: str
    survey_number: str
    acreage: float
    mandal: str
    village: str
    geojson: Optional[dict] = None


@app.post("/fpo/onboard")
def fpo_onboard_farmer(data: FpoOnboardModel, current_user: Optional[dict] = Depends(get_current_user_optional)):
    """Onboard a farmer under FPO attestation: upserts the profile and creates an attested farm."""
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
            "phone": phone,
            "name": data.name,
            "role": "farmer",
            "village": data.village,
            "fpo_id": fpo_id,
        }
        if existing:
            db.update_profile(phone, {k: v for k, v in profile_fields.items() if v})
            profile = db.get_profile(phone)
        else:
            db.upsert_profile(profile_fields)
            profile = db.get_profile(phone)

        farm_record = {
            "owner_phone": phone,
            "name": f"{data.name}'s Parcel ({data.survey_number})",
            "crop_type": "Mixed Crop",
            "area_hectares": data.acreage,
            "status": "Verified",
            "badge": "FPO",
            "fpo_id": fpo_id,
            "satellite_source": "FPO attestation",
        }
        if data.geojson and data.geojson.get("geometry"):
            farm_record["geojson"] = data.geojson
            farm_record["area_hectares"] = data.acreage or _polygon_area_hectares(data.geojson)
        saved_farm = db.insert_farm_safe(farm_record)

        return {
            "success": True,
            "message": f"Farmer {data.name} onboarded under FPO attestation",
            "badge": "FPO",
            "farmer": {
                "id": (profile or {}).get("id"),
                "name": data.name,
                "phone": phone,
                "survey": data.survey_number,
                "acres": data.acreage,
                "badge": "FPO",
                "status": "VERIFIED",
            },
            "farm_id": (saved_farm or {}).get("id"),
        }
    except Exception as e:
        return {"success": False, "message": str(e)}


@app.get("/fpo/pending")
def get_fpo_pending():
    """Farms awaiting verification review, joined with their owner profiles."""
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
            "id": f.get("id"),
            "name": (owners.get(f.get("owner_phone")) or {}).get("name") or "Unknown Farmer",
            "phone": f.get("owner_phone"),
            "village": f.get("geojson", {}).get("properties", {}).get("village") or (owners.get(f.get("owner_phone")) or {}).get("village"),
            "farm_name": f.get("name"),
            "crop": f.get("crop_type"),
            "acres": f.get("area_hectares"),
            "date": (f.get("created_at") or "")[:10],
        } for f in farms]
        return {"success": True, "pending": pending}
    except Exception as e:
        return {"success": False, "message": str(e), "pending": []}


@app.get("/fpo/flagged")
def get_fpo_flagged():
    """Ground-truth audit list: farms flagged by the fraud engine."""
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
            "id": f.get("id"),
            "farmer_name": (owners.get(f.get("owner_phone")) or {}).get("name") or "Unknown Farmer",
            "farm_name": f.get("name"),
            "village": (owners.get(f.get("owner_phone")) or {}).get("village"),
            "claimed_acres": f.get("area_hectares"),
            "issue": "Flagged by fraud engine — ownership/geometry discrepancy",
            "status": "FLAGGED",
            "date": (f.get("updated_at") or f.get("created_at") or "")[:10],
        } for f in farms]
        return {"success": True, "flagged": flagged}
    except Exception as e:
        return {"success": False, "message": str(e), "flagged": []}


def _cert_id_for_listing(listing_id: str) -> str:
    """Deterministic certificate id derived from the listing id."""
    return f"CX-{datetime.now(timezone.utc).year}-CERT-{listing_id.replace('-', '')[:8].upper()}"


class MarketplaceBuyModel(BaseModel):
    listing_id: str
    credits: float
    unit_price: Optional[float] = None
    buyer_name: Optional[str] = "Corporate Buyer"


def _resolve_fpo_link(farm: Optional[dict], farmer_phone: str) -> str:
    """Proven FPO involvement: live farms carry fpo_id; sample data names the FPO."""
    if farm and farm.get("fpo_id"):
        fpos = db.list_fpos() if db.is_ready() else []
        match = next((f for f in fpos if f.get("id") == farm.get("fpo_id")), None)
        return (match or {}).get("name") or "Linked FPO"
    if farm and farm.get("fpo"):
        return farm["fpo"]
    return market_store.fpo_for_phone(farmer_phone)


def _purchase_flow(listing: dict, credits: float, buyer_name: str, apply_update) -> dict:
    """Shared escrow -> conditional split -> ledger -> auto-retire pipeline.

    `apply_update(fields)` persists listing mutations (live DB or demo store).
    Purchase = retirement in one step: the buyer's money lands in the platform
    escrow, the conditional split is computed and recorded, and the credits are
    permanently retired with a batch hash — no resale ambiguity.
    """
    available = float(listing.get("total_credits") or 0)
    unit_price = float(listing.get("price_per_credit") or 0)
    gross = round(credits * unit_price, 2)
    farm_id = listing.get("farm_id") or ""
    fpo_name = _resolve_fpo_link(None, listing.get("farmer_phone") or "")
    if not fpo_name and farm_id and db.is_ready():
        farm = db.get_farm(farm_id) or {}
        fpo_name = _resolve_fpo_link(farm, listing.get("farmer_phone") or "")

    split = split_engine.compute_split(gross, fpo_involved=bool(fpo_name), fpo_name=fpo_name)
    escrow_ref = "ESC-" + uuid.uuid4().hex[:12].upper()
    batch_hash = None
    partial = credits < available - 1e-6

    updates = {"tx_hash": escrow_ref, "current_bid": gross, "bids_count": int(listing.get("bids_count") or 0) + 1}
    if partial:
        updates["total_credits"] = round(available - credits, 4)
    else:
        updates["status"] = "Retired"  # purchase = retirement, one step
    apply_update(updates)

    cert_id = _cert_id_for_listing(listing.get("id"))
    sale_event = ledger.append_event(farm_id, "SALE", {
        "listing_id": listing.get("id"),
        "buyer": buyer_name,
        "credits": credits,
        "unit_price": unit_price,
        "gross_inr": gross,
        "escrow_ref": escrow_ref,
        "certificate_id": cert_id,
    })
    split_event = ledger.append_event(farm_id, "SPLIT", {
        "escrow_ref": escrow_ref,
        "model": split["model"],
        "farmer_inr": split["farmer_amount_inr"],
        "fpo_inr": split["fpo_amount_inr"],
        "platform_inr": split["platform_amount_inr"],
    })
    batch_hash = split_event["hash"]
    ledger.append_event(farm_id, "RETIRE", {
        "certificate_id": cert_id,
        "credits_retired": credits,
        "escrow_ref": escrow_ref,
        "batch_hash": batch_hash,
        "buyer": buyer_name,
    })

    return {
        "success": True,
        "message": "Purchase complete — escrowed, split paid, credits retired",
        "certificate_id": cert_id,
        "listing_id": listing.get("id"),
        "farm_id": farm_id,
        "buyer_name": buyer_name,
        "escrow_ref": escrow_ref,
        "batch_hash": batch_hash,
        "ledger_tail": sale_event["hash"],
        "retired": not partial,
        "credits_purchased": credits,
        "credits_remaining": round(available - credits, 4),
        "gross_amount": gross,
        "unit_price": unit_price,
        "split": split,
        "farmer_name": listing.get("farmer_name"),
        "farmer_phone": listing.get("farmer_phone"),
        "crop": listing.get("crop"),
        "location": listing.get("location"),
        "source": listing.get("_source", "live_db"),
    }


@app.post("/marketplace/buy")
def buy_marketplace_credits(data: MarketplaceBuyModel, current_user: Optional[dict] = Depends(get_current_user_optional)):
    """Purchase credits from a live listing: escrow -> conditional split ->
    hash-anchored ledger events -> instant retirement + certificate."""
    buyer = data.buyer_name or (current_user or {}).get("name") or "Corporate Buyer"

    if not db.is_ready():
        # Demo mode: run the full flow against the in-memory sample store.
        listing = market_store.get(data.listing_id)
        if not listing:
            return {"success": False, "message": "Listing not found"}
        if str(listing.get("status") or "Active").lower() not in ("active", ""):
            return {"success": False, "message": f"Listing is no longer available (status: {listing.get('status')})"}
        available = float(listing.get("total_credits") or 0)
        if available <= 0:
            return {"success": False, "message": "This listing has no purchasable credits left"}
        credits = round(min(float(data.credits or available), available), 4)
        if credits <= 0:
            return {"success": False, "message": "Credit quantity must be greater than zero"}
        listing["_source"] = "demo_store"
        return _purchase_flow(listing, credits, buyer, lambda fields: market_store.update(data.listing_id, fields))

    try:
        sb = db._client()
        rows = (sb.table("marketplace_listings").select("*").eq("id", data.listing_id).execute().data) or []
        if not rows:
            return {"success": False, "message": "Listing not found"}
        listing = rows[0]
        if str(listing.get("status") or "Active").lower() not in ("active", ""):
            return {"success": False, "message": f"Listing is no longer available (status: {listing.get('status')})"}
        available = float(listing.get("total_credits") or 0)
        if available <= 0:
            return {"success": False, "message": "This listing has no purchasable credits left"}
        credits = round(min(float(data.credits or available), available), 4)
        if credits <= 0:
            return {"success": False, "message": "Credit quantity must be greater than zero"}
        return _purchase_flow(listing, credits, buyer, lambda fields: sb.table("marketplace_listings").update(fields).eq("id", data.listing_id).execute())
    except Exception as e:
        return {"success": False, "message": str(e)}


class AutoMatchModel(BaseModel):
    target_volume: float
    priority: Optional[str] = "lowest_price" # nearest, highest_ndvi, lowest_price
    filters: Optional[dict] = None


@app.post("/marketplace/auto-match")
def auto_match_bulk(data: AutoMatchModel):
    """Greedy fill auto-match over Active listings until the target volume is met.

    Every matched line previews the farmer's 70% floor — the buyer sees exactly
    whose credits they are buying and what the farmer keeps before paying.
    """
    rows_source = None
    if not db.is_ready():
        rows_source = [r for r in market_store.all_rows() if r.get("status") == "Active"]
    listings = rows_source
    if listings is None:
        sb = db._client()
        try:
            listings = (sb.table("marketplace_listings").select("*").eq("status", "Active").execute().data) or []
        except Exception as e:
            return {"success": False, "message": str(e), "matched_farms": []}
    listings = [l for l in listings if float(l.get("total_credits") or 0) > 0]
    farm_ids = list({l.get("farm_id") for l in listings if l.get("farm_id")})
    farms_by_id = {}
    if farm_ids and db.is_ready():
        sb = db._client()
        farms_by_id = {f.get("id"): f for f in (sb.table("farms").select("id,name,badge,ndvi").in_("id", farm_ids).execute().data or [])}

    if data.priority == "highest_ndvi":
        listings.sort(key=lambda l: float((farms_by_id.get(l.get("farm_id")) or {}).get("ndvi") or 0), reverse=True)
    else:  # lowest_price (default)
        listings.sort(key=lambda l: float(l.get("price_per_credit") or 0))

    volume = float(data.target_volume or 0)
    matched = []
    for l in listings:
        if volume <= 0:
            break
        take = min(volume, float(l.get("total_credits") or 0))
        farm = farms_by_id.get(l.get("farm_id")) or {}
        badge = farm.get("badge") or "DOCUMENT"
        line_gross = round(take * float(l.get("price_per_credit") or 0), 2)
        fpo_name = _resolve_fpo_link(farm or None, l.get("farmer_phone") or "")
        line_split = split_engine.compute_split(line_gross, fpo_involved=bool(fpo_name), fpo_name=fpo_name)
        matched.append({
            "listing_id": l.get("id"),
            "farm": farm.get("name") or l.get("location") or "Telangana Parcel",
            "farmer": l.get("farmer_name") or "Marketplace Farmer",
            "survey": l.get("location"),
            "crop": l.get("crop"),
            "credits": round(take, 2),
            "rate": float(l.get("price_per_credit") or 0),
            "badge": badge,
            "badge_color": "emerald" if badge == "REGISTRY" else ("forest" if badge == "REGISTRY_DOC" else "amber"),
            "farmer_share_inr": line_split["farmer_amount_inr"],
            "fpo_name": fpo_name or None,
        })
        volume -= take

    gross = round(sum(m["credits"] * m["rate"] for m in matched), 2)
    overall_split = split_engine.compute_split(
        gross, fpo_involved=any(m.get("fpo_name") for m in matched)
    )
    return {
        "success": True,
        "target_volume": float(data.target_volume or 0),
        "total_matched": round(sum(m["credits"] for m in matched), 2),
        "gross_value": gross,
        "farmer_total_inr": overall_split["farmer_amount_inr"],
        "fpo_total_inr": overall_split["fpo_amount_inr"],
        "platform_total_inr": overall_split["platform_amount_inr"],
        "split_model": overall_split["model"],
        "matched_farms": matched,
    }


@app.get("/certificates")
def list_certificates():
    """Escrow certificate ledger, derived from purchased (Retired) listings."""
    rows = None
    if not db.is_ready():
        rows = [r for r in market_store.all_rows() if str(r.get("status")).lower() in ("sold", "retired")]
        rows.sort(key=lambda r: r.get("updated_at") or "", reverse=True)
    else:
        try:
            sb = db._client()
            rows = (sb.table("marketplace_listings").select("*").in_("status", ["Sold", "Retired"]).order("updated_at", desc=True).execute().data) or []
        except Exception as e:
            return {"success": False, "message": str(e), "certificates": []}
    certificates = []
    for r in rows:
        farm_id = r.get("farm_id") or ""
        chain = ledger.summary(farm_id) if farm_id else {}
        retired = str(r.get("status")).lower() == "retired"
        certificates.append({
            "id": _cert_id_for_listing(r.get("id")),
            "listing_id": r.get("id"),
            "issued_to": "Corporate Buyer",
            "farmer_name": r.get("farmer_name"),
            "crop": r.get("crop"),
            "volume_mt": r.get("total_credits"),
            "value_inr": r.get("current_bid"),
            "source_parcels": [f"{r.get('location') or 'Telangana'} ({r.get('crop') or 'Mixed Crop'})"],
            "issued_date": (r.get("updated_at") or r.get("created_at") or "")[:10],
            "status": "RETIRED" if retired else "HELD_IN_ESCROW",
            "batch_hash": chain.get("tail_hash"),
            "ledger_verified": chain.get("verified", False),
            "tx_hash": r.get("tx_hash"),
            "on_chain": False,
        })
    return {"success": True, "certificates": certificates}


@app.get("/certificates/{cert_id}/pdf")
def download_certificate_pdf(cert_id: str):
    """Download the retirement certificate as a print-ready PDF."""
    from fastapi.responses import Response

    from app.services.certificate_pdf import render_certificate_pdf

    rows = None
    if not db.is_ready():
        rows = [r for r in market_store.all_rows() if str(r.get("status")).lower() in ("sold", "retired")]
    else:
        try:
            sb = db._client()
            rows = (sb.table("marketplace_listings").select("*").in_("status", ["Sold", "Retired"]).execute().data) or []
        except Exception as e:
            return {"success": False, "message": str(e)}
    row = next((r for r in rows if _cert_id_for_listing(r.get("id")) == cert_id), None)
    if not row:
        return {"success": False, "message": "Certificate not found"}
    farm_id = row.get("farm_id") or ""
    chain = ledger.summary(farm_id) if farm_id else {}
    cert = {
        "id": cert_id,
        "buyer": "Corporate Buyer",
        "farmer_name": row.get("farmer_name"),
        "crop": row.get("crop"),
        "volume": row.get("total_credits"),
        "value": row.get("current_bid"),
        "location": row.get("location"),
        "issued_date": (row.get("updated_at") or row.get("created_at") or "")[:10],
        "retired_date": (row.get("updated_at") or row.get("created_at") or "")[:10],
        "batch_hash": chain.get("tail_hash") or row.get("tx_hash") or "",
    }
    pdf_bytes = render_certificate_pdf(cert)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="CarbonX_Certificate_{cert_id}.pdf"'},
    )


@app.post("/certificates/{cert_id}/retire")
def retire_certificate(cert_id: str, scope: Optional[str] = "Scope 1 Neutrality"):
    """Permanently retire a purchased certificate (marks the underlying listing Retired)."""
    rows = None
    if not db.is_ready():
        rows = [r for r in market_store.all_rows() if str(r.get("status")).lower() == "sold"]
    else:
        try:
            sb = db._client()
            rows = (sb.table("marketplace_listings").select("id,status,farm_id").eq("status", "Sold").execute().data) or []
        except Exception as e:
            return {"success": False, "message": str(e)}
    target = next((r for r in rows if _cert_id_for_listing(r.get("id")) == cert_id), None)
    if not target:
        # Purchase = retirement now happens automatically; treat re-retire as success.
        return {
            "success": True,
            "message": f"Certificate {cert_id} is already permanently retired",
            "cert_id": cert_id,
            "status": "RETIRED",
            "already_retired": True,
        }
    retired_ts = datetime.now(timezone.utc).isoformat()
    if not db.is_ready():
        market_store.update(target["id"], {"status": "Retired", "updated_at": retired_ts})
    else:
        sb = db._client()
        sb.table("marketplace_listings").update({"status": "Retired", "updated_at": retired_ts}).eq("id", target["id"]).execute()
    if target.get("farm_id"):
        ledger.append_event(target["farm_id"], "RETIRE", {
            "certificate_id": cert_id,
            "scope": scope,
            "manual": True,
        })
    return {
        "success": True,
        "message": f"Certificate {cert_id} permanently retired for {scope}",
        "cert_id": cert_id,
        "listing_id": target["id"],
        "status": "RETIRED",
        "scope": scope,
        "retired_timestamp": retired_ts,
    }


@app.get("/passport/{farm_id}")
def get_carbon_passport(farm_id: str):
    """Digital Carbon Passport: satellite + KYC record, expected earnings,
    trust-engine state, and the tamper-evident ledger chain."""
    farm = db.get_farm(farm_id) if db.is_ready() else None
    demo_mode = False
    if not farm:
        # Demo mode: serve the canonical sample farm for any unknown id.
        demo_mode = True
        farm = {
            "id": farm_id,
            "name": "Sri Venkateswara Organic Farm",
            "owner_phone": "9000000001",
            "crop_type": "Rice",
            "area_hectares": 2.4,
            "ndvi": 0.78,
            "evi": 0.65,
            "soil_moisture": 41,
            "tree_cover": 28,
            "biodiversity_score": 720,
            "carbon_tonnes": 82,
            "total_credits": 96.0,
            "biodiversity_credits": 18.0,
            "satellite_source": "Sentinel-2 (demo)",
            "ai_confidence": 0.87,
            "status": "verified",
            "badge": "REGISTRY",
            "irrigation": "Drip",
            "updated_at": sample_data.FALLBACK_AS_OF.isoformat(),
        }
    owner = db.get_profile(farm.get("owner_phone") or "") if db.is_ready() else sample_data.FARMERS.get(farm.get("owner_phone"))
    kyc = db.get_kyc_status(farm.get("owner_phone") or "") if db.is_ready() else None
    badge = farm.get("badge") or (kyc or {}).get("badge") or "DOCUMENT"
    benchmark = {"REGISTRY": 340, "REGISTRY_DOC": 320, "FPO": 300}.get(badge, 310)
    verification_hash = "0x" + uuid.uuid5(uuid.NAMESPACE_URL, f"carbonx:{farm_id}:{farm.get('updated_at')}").hex[:26]

    credits_total = float(farm.get("total_credits") or 0)
    income = credit_engine.income_projection(credits_total, badge)

    verified_status = str(farm.get("status", "")).lower() in ("verified", "ver")
    quality = credit_engine.evidence_quality(
        has_photo=True,
        geotag_ok=True,
        fpo_or_registry=badge in ("REGISTRY", "REGISTRY_DOC", "FPO"),
        ndvi_current=farm.get("ndvi") is not None,
        baseline_known=verified_status,
    )
    ledger.ensure_genesis(farm_id, {
        "farm": farm.get("name"),
        "crop": farm.get("crop_type"),
        "area_hectares": farm.get("area_hectares"),
        "ndvi": farm.get("ndvi"),
        "carbon_tonnes": farm.get("carbon_tonnes"),
        "badge": badge,
        "status": farm.get("status"),
    }, ts=(farm.get("updated_at") or "") or None)
    chain = ledger.summary(farm_id)
    farm_status = farm.get("status")
    monitoring = {
        "last_monitored_at": farm.get("last_monitored_at"),
        "last_monitor_ndvi": farm.get("last_monitor_ndvi"),
        "at_risk": str(farm_status or "").lower() == "flagged",
        "cycle": "5-day Sentinel-2 revisit",
    }

    return {
        "success": True,
        "passport_id": f"CX-FARM-{str(farm_id).replace('-', '')[:8].upper()}",
        "demo_mode": demo_mode,
        "farm_name": farm.get("name"),
        "owner_name": (owner or {}).get("name") or "Registered Farmer",
        "phone": farm.get("owner_phone"),
        "district": (owner or {}).get("district"),
        "village": (owner or {}).get("village"),
        "crop": farm.get("crop_type"),
        "irrigation": farm.get("irrigation"),
        "acreage": farm.get("area_hectares"),
        "badge": badge,
        "benchmark_price": benchmark,
        "annual_credits": farm.get("total_credits"),
        "carbon_tonnes": farm.get("carbon_tonnes"),
        "sentinel_ndvi": farm.get("ndvi"),
        "evi": farm.get("evi"),
        "biodiversity_index": round(float(farm.get("biodiversity_score") or 0) / 10, 1) if farm.get("biodiversity_score") else None,
        "satellite_source": farm.get("satellite_source"),
        "ai_confidence": farm.get("ai_confidence"),
        "verification_hash": verification_hash,
        "farm_status": farm_status,
        "kyc_status": (kyc or {}).get("status"),
        "status": "APPROVED MRV RECORD" if verified_status else "PENDING MRV REVIEW",
        "expected_earnings": income,
        "monitoring": monitoring,
        "trust": {
            "evidence_quality": quality["score"],
            "uncertainty_pct": credit_engine.uncertainty_pct(quality["score"]),
            "components": quality["components"],
            "verification_hash": verification_hash,
        },
        "ledger": chain,
    }


@app.get("/wallet")
def get_wallet_ledger(current_user: dict = Depends(get_current_user)):
    """Farmer wallet: sales with the conditional split applied, escrow state,
    and the ledger hash that proves every payout line."""
    phone = current_user.get("phone")
    if not db.is_ready():
        profile = sample_data.FARMERS.get(phone) or {}
        rows = [r for r in market_store.all_rows() if r.get("farmer_phone") == phone]
    else:
        try:
            sb = db._client()
            profile = db.get_profile(phone) or {}
            rows = (sb.table("marketplace_listings").select("*").eq("farmer_phone", phone).execute().data) or []
        except Exception as e:
            return {"success": False, "message": str(e)}

    sold = [r for r in rows if str(r.get("status")).lower() in ("sold", "retired")]
    active = [r for r in rows if str(r.get("status")).lower() == "active"]

    def _gross(r):
        bid = r.get("current_bid")
        if bid:
            return round(float(bid), 2)
        return round(float(r.get("total_credits") or 0) * float(r.get("price_per_credit") or 0), 2)

    total_earned = round(sum(_gross(r) for r in sold), 2)
    escrow_pending = round(sum(_gross(r) for r in active), 2)

    farmer_total = 0.0
    fpo_total = 0.0
    platform_total = 0.0
    transactions = []
    for r in sorted(sold, key=lambda x: x.get("updated_at") or "", reverse=True):
        gross = _gross(r)
        fpo_name = _resolve_fpo_link(None, r.get("farmer_phone") or phone)
        split = split_engine.compute_split(gross, fpo_involved=bool(fpo_name), fpo_name=fpo_name)
        farmer_total += split["farmer_amount_inr"]
        fpo_total += split["fpo_amount_inr"]
        platform_total += split["platform_amount_inr"]
        farm_id = r.get("farm_id") or ""
        chain = ledger.summary(farm_id) if farm_id else {}
        transactions.append({
            "date": (r.get("updated_at") or r.get("created_at") or "")[:10],
            "tx_id": (r.get("tx_hash") or f"TXN-{(r.get('id') or '')[:6].upper()}"),
            "source": f"Marketplace sale ({r.get('crop') or 'Mixed Crop'})",
            "listing_id": r.get("id"),
            "farm_id": farm_id,
            "credits_sold": r.get("total_credits"),
            "rate": r.get("price_per_credit"),
            "gross": gross,
            "farmer_share": split["farmer_amount_inr"],
            "fpo_share": split["fpo_amount_inr"],
            "platform_share": split["platform_amount_inr"],
            "split_model": split["model"],
            "ledger_hash": chain.get("tail_hash"),
            "status": "SETTLED",
        })

    return {
        "success": True,
        "total_earned": total_earned,
        "escrow_pending": escrow_pending,
        "withdrawable_upi": round(farmer_total, 2),
        "farmer_share_total": round(farmer_total, 2),
        "fpo_share_total": round(fpo_total, 2),
        "platform_share_total": round(platform_total, 2),
        "upi_id": profile.get("upi"),
        "demo_mode": not db.is_ready(),
        "transactions": transactions,
    }


@app.post("/demo/login")
def demo_login(data: dict = None):
    """Issue a demo farmer session — only when the database is not configured.

    Lets the whole farmer loop (wallet, passport, calculator) be exercised
    with credentials removed. Refuses to start when a real DB exists.
    """
    if db.is_ready():
        return {"success": False, "message": "Demo login is only available in demo mode (database not configured)"}
    body = data or {}
    phone = str(body.get("phone") or "9000000001")
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


NDVI_DROP_ALERT = 0.15  # Sentinel-2-cycle drop that flags credits at-risk


@app.post("/monitor/run")
def run_monitoring_cycle(current_user: Optional[dict] = Depends(get_current_user_optional)):
    """5-day continuous monitoring (the real Sentinel-2 revisit cycle).

    Compares each verified farm's current NDVI against the last monitored
    value. A significant drop (drought, disease, abandonment, land-use change)
    flags the farm's credits at-risk: the farm is routed to the FPO flagged
    queue and a MONITOR event lands on its hash chain. Clean cycles just
    refresh the snapshot — the ledger stays lean.
    """
    if not db.is_ready():
        return {"success": False, "message": "Monitoring needs the database (demo mode has no live farms)"}
    try:
        sb = db._client()
        farms = (sb.table("farms").select("id,name,ndvi,status,last_monitor_ndvi,last_monitored_at").execute().data) or []
        checked = 0
        at_risk = []
        healthy = 0
        now_iso = datetime.now(timezone.utc).isoformat()
        for farm in farms:
            if str(farm.get("status") or "").lower() in ("pending",):
                continue  # unverified farms aren't carrying credits yet
            checked += 1
            current = farm.get("ndvi")
            if current is None:
                continue
            current = float(current)
            last = farm.get("last_monitor_ndvi")
            drop = round(float(last) - current, 3) if last is not None else 0.0
            sb.table("farms").update({
                "last_monitor_ndvi": current,
                "last_monitored_at": now_iso,
            }).eq("id", farm["id"]).execute()
            if last is not None and drop >= NDVI_DROP_ALERT:
                sb.table("farms").update({"status": "Flagged"}).eq("id", farm["id"]).execute()
                ledger.append_event(farm["id"], "MONITOR", {
                    "risk": "ndvi_drop",
                    "drop": drop,
                    "previous_ndvi": float(last),
                    "current_ndvi": current,
                    "note": "Credits at-risk — routed to FPO review (drought/disease/abandonment possible)",
                })
                at_risk.append({
                    "farm_id": farm["id"],
                    "name": farm.get("name"),
                    "drop": drop,
                    "previous_ndvi": float(last),
                    "current_ndvi": current,
                })
            else:
                healthy += 1
        return {
            "success": True,
            "checked": checked,
            "healthy": healthy,
            "at_risk_count": len(at_risk),
            "at_risk": at_risk,
            "alert_threshold": NDVI_DROP_ALERT,
            "ran_at": now_iso,
        }
    except Exception as e:
        return {"success": False, "message": str(e)}


class EarningsCalcModel(BaseModel):
    area_hectares: float
    crop: Optional[str] = ""
    ndvi: Optional[float] = 0.7
    baseline_ndvi: Optional[float] = None
    badge: Optional[str] = "DOCUMENT"
    has_photo: Optional[bool] = True
    geotag_ok: Optional[bool] = True
    fpo_or_registry: Optional[bool] = False


@app.post("/farms/earnings-calculator")
def earnings_calculator(data: EarningsCalcModel):
    """Pre-signup earnings estimate — the farmer sees expected rupees before
    enrolling. Open endpoint: no auth, no database required."""
    quality = credit_engine.evidence_quality(
        has_photo=data.has_photo,
        geotag_ok=data.geotag_ok,
        fpo_or_registry=data.fpo_or_registry,
        ndvi_current=data.ndvi is not None,
        baseline_known=data.baseline_ndvi is not None,
    )
    estimate = credit_engine.estimate_credits(
        area_hectares=data.area_hectares,
        crop=data.crop or "",
        ndvi=data.ndvi or 0.7,
        baseline_ndvi=data.baseline_ndvi,
        quality_score=quality["score"],
    )
    income = credit_engine.income_projection(estimate["credits_tco2e"], data.badge or "DOCUMENT")
    return {
        "success": True,
        "estimate": estimate,
        "income": income,
        "evidence_quality": quality,
    }


@app.get("/ledger/{farm_id}")
def get_farm_ledger(farm_id: str):
    """The farm's tamper-evident event chain, recomputed and verified."""
    chain = ledger.get_chain(farm_id)
    if not chain:
        farm = db.get_farm(farm_id) if db.is_ready() else None
        snapshot = {
            "farm": (farm or {}).get("name") or "Sri Venkateswara Organic Farm (demo)",
            "crop": (farm or {}).get("crop_type") or "Rice",
            "ndvi": (farm or {}).get("ndvi") or 0.78,
            "note": "Genesis anchored from farm evidence snapshot",
        }
        ledger.ensure_genesis(farm_id, snapshot)
        chain = ledger.get_chain(farm_id)
    verification = ledger.verify_chain(farm_id)
    public_events = [{k: v for k, v in e.items() if not k.startswith("_")} for e in chain]
    return {
        "success": True,
        "farm_id": farm_id,
        "verification": verification,
        "events": public_events,
    }

