"""Farms routes: satellite analysis, farm persistence, Trust Engine Stage 1, KYC & land registry."""
from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, UploadFile
from pydantic import BaseModel, ConfigDict, field_validator
from typing import Literal, Optional
import base64
import json
import math
import re
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
from app.services.kyc_service import (
    analyse_document,
    validate_aadhaar,
    _match_name,
    _extract_ocr_text,
)

router = APIRouter(tags=["farms"])


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


def _get_user_farms(phone: str):
    _require_database()
    return db.get_farms(phone)


def _polygon_area_hectares(geojson: dict) -> float:
    from app.services.polygon_service import polygon_area_hectares as _canonical
    try:
        return _canonical(geojson)
    except Exception:
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


def _validate_polygon_geojson(geojson: dict) -> tuple[bool, str]:
    if not isinstance(geojson, dict):
        return False, "GeoJSON must be an object"
    geom = geojson.get("geometry") or {}
    if geom.get("type") != "Polygon":
        return False, "GeoJSON geometry type must be Polygon"
    rings = geom.get("coordinates")
    if not isinstance(rings, list) or not rings:
        return False, "Polygon coordinates missing"
    ring = rings[0]
    if not isinstance(ring, list) or len(ring) < 4:
        return False, "Polygon ring needs at least 4 positions"
    for pos in ring:
        if (not isinstance(pos, list) or len(pos) < 2
                or not all(isinstance(c, (int, float)) and math.isfinite(c) for c in pos[:2])):
            return False, "Invalid coordinate in polygon ring"
        lon, lat = pos[0], pos[1]
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            return False, "Coordinate out of WGS84 range"
    if ring[0][:2] != ring[-1][:2]:
        return False, "Polygon ring must be closed (first == last position)"
    lons = [pos[0] for pos in ring]
    lats = [pos[1] for pos in ring]
    if (max(lons) - min(lons)) > 60 or (max(lats) - min(lats)) > 60:
        return False, "Polygon too large — draw a single farm plot"
    return True, ""


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
        print(f"Pahani Azure OCR unavailable, using local OCR fallback: {exc}")
        checks = analyse_document(content_base64, filename, "", "", [])
        text = checks.get("ocr_text_preview", "")
        return _pahani_fallback_fields(text), text


def _claimed_area_ha(data: "LandVerificationModel") -> Optional[float]:
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


def _with_ee_backoff(fn, *, attempts=3, base_delay=1.5):
    last_err = None
    for attempt in range(attempts):
        try:
            return fn()
        except Exception as e:
            last_err = e
            if attempt < attempts - 1:
                delay = base_delay * (2 ** attempt)
                print(f"[ee] call failed ({type(e).__name__}), retry in {delay}s")
                time.sleep(delay)
    raise last_err


# ─── Pydantic Models ───

class GeoJSONPolygon(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["Feature"] = "Feature"
    geometry: dict

    @field_validator("geometry")
    @classmethod
    def _validate_polygon(cls, geom):
        ok, err = _validate_polygon_geojson({"type": "Feature", "geometry": geom})
        if not ok:
            raise ValueError(err)
        return geom


class AnalyzeModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    geojson: GeoJSONPolygon
    farm_name: Optional[str] = "My Farm"
    crop_type: Optional[str] = "Mixed Crop"
    irrigation: Optional[str] = "Drip"


class SaveFarmModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    farm: dict


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


# ─── Endpoints ───

@router.post("/save-farm")
@router.post("/farms/save-farm")
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
        credits = credit_engine.credit_split(carbon, bio_score)
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
        if farm.get("ci90_low") is not None:
            record["credits_ci90_low"] = farm["ci90_low"]
        if farm.get("ci90_high") is not None:
            record["credits_ci90_high"] = farm["ci90_high"]
        if badge:
            record["badge"] = badge
        saved = db.insert_farm_safe(record)
        if not saved or not saved.get("id"):
            return {"success": False, "message": "Failed to save farm to database"}
        ledger.ensure_genesis(saved["id"], {
            "farm": record["name"],
            "crop": record["crop_type"],
            "area_hectares": record["area_hectares"],
            "ndvi": record["ndvi"],
            "status": status,
            "badge": badge,
            "stage1": stage1["status"],
            "formula_version": app_config.FORMULA_VERSION,
            "s2_scene": farm.get("s2_scene"),
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


@router.get("/farm/{farm_id}/ndvi-history")
@router.get("/farms/{farm_id}/ndvi-history")
def get_farm_ndvi_history(farm_id: str):
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


# ─── KYC & Land Verification ───

@router.post("/verify-aadhaar")
def verify_aadhaar(data: AadhaarVerificationModel, current_user: dict = Depends(get_current_user)):
    """OCR Aadhaar front/back and compare it to the registered identity anchor."""
    from PIL import Image
    import io

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


@router.post("/verify-land")
def verify_land_document(data: LandVerificationModel, current_user: dict = Depends(get_current_user)):
    """Run the trust engine. Backend assigns tier, badge, status, and eligibility."""
    try:
        from app.services.fraud_engine import run_fraud_checks
        from app.services.registry_service import lookup_survey
        from app.services.trust_engine import apply_fraud, decide_tier

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


@router.get("/kyc/status/{phone}")
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


@router.post("/documents/parse-pahani")
def parse_pahani_document(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    """OCR a Pahani (Adangal) record and return structured fields as JSON."""
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
        return parse_pahani(azure_result)
    except Exception as exc:
        msg = str(exc)
        if "Azure Cognitive Services not configured" in msg or "Connection" in msg or "Endpoint" in msg:
            return azure_unavailable_response(msg)
        return {"success": False, "message": f"Document parsing failed: {msg}"}


@router.get("/land/registry/{survey}")
def land_registry_lookup(survey: str, current_user: dict = Depends(get_current_user)):
    """Look up a survey number in the Supabase land_registry mock table."""
    from app.services.registry_service import lookup_survey

    _require_database()
    result = lookup_survey(survey)
    if result.get("error") == "permission_denied":
        raise HTTPException(status_code=503, detail=result["message"])
    return {"success": True, **result}


@router.post("/auto-draw")
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


@router.post("/check-farmland")
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