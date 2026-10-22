"""Farm evidence routes: practice photos + geotags (see evidence_service).

Registered by the orchestrator in ``app/main.py``. Endpoints:

- ``POST /farms/{farm_id}/evidence/photo``      multipart photo upload (auth)
- ``POST /farms/{farm_id}/evidence/geotag``     explicit coordinate record (auth)
- ``GET  /farms/{farm_id}/evidence``            open listing (transparency, like /passport)
"""
import glob
import math
import os
import re
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from app.security import get_current_user, get_current_user_optional
from app import supabase_db as db
from app.services import evidence_service as evidence

router = APIRouter(tags=["evidence"])

_MIME_ALIASES = {
    "image/jpg": "image/jpeg",
    "image/pjpeg": "image/jpeg",
    "image/x-png": "image/png",
}


# ─── Models ───

class GeotagModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    accuracy_m: Optional[float] = Field(default=None, ge=0)
    captured_at: Optional[datetime] = None


# ─── Helpers ───

def _safe_farm_id(farm_id: str) -> str:
    safe = evidence.sanitize_farm_id(farm_id)
    if safe is None:
        raise HTTPException(
            status_code=400,
            detail="farm_id may only contain letters, digits, '-' and '_'",
        )
    return safe


def _load_farm(farm_id: str) -> Optional[dict]:
    """Farm row lookup — module-level so tests can substitute a boundary.

    Demo mode (DB off) has no farm rows and returns ``None``: boundaries can
    never be invented, so inside-boundary stays False there.
    """
    if not db.is_ready():
        return None
    try:
        return db.get_farm(farm_id)
    except Exception as exc:
        print(f"evidence farm lookup failed: {exc}")
        return None


def _authorize_farm(farm_id: str, current_user: dict) -> Optional[dict]:
    """Load the farm and enforce ownership when the live DB is available."""
    farm = _load_farm(farm_id)
    if not db.is_ready():
        return farm  # demo mode: no farm rows to authorize against
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found")
    phone = (current_user or {}).get("phone")
    role = (current_user or {}).get("role", "farmer")
    if role in ("admin", "verifier"):
        return farm
    if farm.get("owner_phone") == phone:
        return farm
    if role == "fpo":
        profile = db.get_profile(phone) if db.is_ready() else {}
        user_fpo = (profile or {}).get("fpo_id")
        farm_fpo = farm.get("fpo_id")
        if user_fpo and farm_fpo and str(user_fpo) != str(farm_fpo):
            raise HTTPException(status_code=403, detail="You can only attach evidence to your own or FPO-scoped farms")
        return farm
    raise HTTPException(status_code=403, detail="You can only attach evidence to your own farms")


def _parse_form_coord(value: Optional[str], name: str, limit: float) -> Optional[float]:
    if value is None or not str(value).strip():
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail=f"{name} must be a number between -{limit:g} and {limit:g}")
    if not math.isfinite(number) or abs(number) > limit:
        raise HTTPException(status_code=400, detail=f"{name} must be a number between -{limit:g} and {limit:g}")
    return number


def _parse_form_captured_at(value: Optional[str]) -> Optional[str]:
    if value is None or not str(value).strip():
        return None
    try:
        parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status_code=400, detail="captured_at must be an ISO 8601 timestamp")
    return parsed.isoformat()


def _components(farm_id: str) -> dict:
    flags = evidence.evidence_flags(farm_id)
    return {
        "practice_photo": flags["practice_photo"],
        "geotag_inside_boundary": flags["geotag_inside_boundary"],
    }


# ─── Endpoints ───

@router.post("/farms/{farm_id}/evidence/photo")
async def upload_evidence_photo(
    farm_id: str,
    file: UploadFile = File(...),
    latitude: Optional[str] = Form(None),
    longitude: Optional[str] = Form(None),
    captured_at: Optional[str] = Form(None),
    public_consent: Optional[bool] = Form(False),
    current_user: dict = Depends(get_current_user),
):
    """Attach a practice photo (multipart ``file``, ≤8 MB, JPEG/PNG/WebP).

    Coordinates are taken from EXIF GPS first, else from explicit
    ``latitude``/``longitude`` form fields — never invented. When the farm
    boundary is available the coordinate is verified with pure-Python ray
    casting; otherwise the photo is still accepted and the geotag is stored
    with ``inside_boundary: false`` plus a reason.
    """
    safe_id = _safe_farm_id(farm_id)
    farm = _authorize_farm(farm_id, current_user)

    declared = (file.content_type or "").split(";")[0].strip().lower()
    declared = _MIME_ALIASES.get(declared, declared)
    if declared and declared not in evidence.ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=415, detail="Only JPEG, PNG, or WebP photos are accepted")

    chunks = []
    total_bytes = 0
    chunk_size = 64 * 1024
    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        total_bytes += len(chunk)
        if total_bytes > evidence.MAX_PHOTO_BYTES:
            await file.close()
            raise HTTPException(status_code=413, detail="Photo exceeds the 8 MB limit")
        chunks.append(chunk)
    await file.close()
    data = b"".join(chunks)

    try:
        photo = evidence.inspect_photo(data)
    except evidence.PhotoTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc))
    except evidence.EvidenceImageError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    captured = _parse_form_captured_at(captured_at)
    form_latitude = _parse_form_coord(latitude, "latitude", 90)
    form_longitude = _parse_form_coord(longitude, "longitude", 180)
    if (form_latitude is None) != (form_longitude is None):
        raise HTTPException(status_code=400, detail="latitude and longitude must be provided together")

    exif = photo["exif"]
    if exif:
        point = (float(exif["latitude"]), float(exif["longitude"]))
        source = "exif"
    elif form_latitude is not None and form_longitude is not None:
        point = (form_latitude, form_longitude)
        source = "request"
    else:
        point = None
        source = None

    geojson = (farm or {}).get("geojson")
    geotag = None
    if point is not None:
        inside, reason = evidence.verify_inside_boundary(point[0], point[1], geojson)
        geotag = {
            "latitude": point[0],
            "longitude": point[1],
            "source": source,
            "inside_boundary": inside,
            "reason": reason,
        }
        stored_latitude, stored_longitude, stored_inside = point[0], point[1], bool(inside)
    else:
        stored_latitude, stored_longitude, stored_inside = None, None, False

    digest = evidence.sha256_hex(data)
    try:
        evidence.store_photo_file(safe_id, data, digest, photo["ext"])
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=500, detail=f"Could not store the photo: {exc}")

    record = {
        "farm_id": safe_id,
        "kind": "photo",
        "sha256": digest,
        "mime": photo["mime"],
        "size_bytes": len(data),
        "latitude": stored_latitude,
        "longitude": stored_longitude,
        "inside_boundary": stored_inside,
        "captured_at": captured,
        "created_by": (current_user or {}).get("phone"),
        "is_public": bool(public_consent),
    }
    if not evidence.persist_record(record):
        raise HTTPException(
            status_code=503,
            detail="Evidence metadata could not be persisted — apply supabase/08_farm_evidence.sql and retry",
        )

    if geotag is None:
        photo_reason = (
            "No GPS coordinates in photo EXIF and none provided with the upload — "
            "photo stored without a geotag"
        )
    else:
        photo_reason = None

    return {
        "success": True,
        "farm_id": safe_id,
        "demo_mode": not db.is_ready(),
        "photo": {
            "accepted": True,
            "reason": photo_reason,
            "sha256": digest,
            "mime": photo["mime"],
            "size_bytes": len(data),
            "captured_at": captured,
            "geotag": geotag,
            "is_public": bool(public_consent),
        },
        "components": _components(safe_id),
    }


@router.post("/farms/{farm_id}/evidence/geotag")
def add_farm_geotag(
    farm_id: str,
    data: GeotagModel,
    current_user: dict = Depends(get_current_user),
):
    """Store an explicit geotag and verify it against the farm boundary.

    The point is stored as given; ``inside_boundary`` is only True when the
    farm's real polygon was available and ray casting confirmed containment.
    """
    safe_id = _safe_farm_id(farm_id)
    farm = _authorize_farm(safe_id, current_user)
    inside, reason = evidence.verify_inside_boundary(
        data.latitude, data.longitude, (farm or {}).get("geojson")
    )
    record = {
        "farm_id": safe_id,
        "kind": "geotag",
        "sha256": None,
        "mime": None,
        "size_bytes": None,
        "latitude": data.latitude,
        "longitude": data.longitude,
        "inside_boundary": bool(inside),
        "captured_at": data.captured_at.isoformat() if data.captured_at else None,
        "created_by": (current_user or {}).get("phone"),
    }
    if not evidence.persist_record(record):
        raise HTTPException(
            status_code=503,
            detail="Evidence metadata could not be persisted — apply supabase/08_farm_evidence.sql and retry",
        )
    return {
        "success": True,
        "farm_id": safe_id,
        "demo_mode": not db.is_ready(),
        "geotag": {
            "latitude": data.latitude,
            "longitude": data.longitude,
            "inside_boundary": inside,
            "reason": reason,
        },
        "components": _components(safe_id),
    }


@router.get("/farms/{farm_id}/evidence")
def get_farm_evidence(
    farm_id: str,
    current_user: Optional[dict] = Depends(get_current_user_optional),
):
    """Evidence listing: full metadata for owner/verifier; coarse/public for external callers."""
    safe_id = _safe_farm_id(farm_id)
    flags = evidence.evidence_flags(safe_id)
    listing = evidence.list_evidence(safe_id)

    # Check if caller has authorized access to exact coordinates and private photos
    caller_phone = (current_user or {}).get("phone")
    caller_role = (current_user or {}).get("role")
    farm = _load_farm(safe_id)
    is_owner = bool(farm and caller_phone and farm.get("owner_phone") == caller_phone)
    is_authorized = is_owner or (caller_role in ("admin", "fpo", "verifier"))

    sanitized_photos = []
    for p in listing.get("photos", []):
        p_item = dict(p)
        is_pub = bool(p_item.get("is_public", False))
        if not is_authorized and not is_pub:
            # Mask exact GPS and mark private for non-consented photos
            p_item["private"] = True
            if "latitude" in p_item:
                p_item["latitude"] = None
            if "longitude" in p_item:
                p_item["longitude"] = None
        sanitized_photos.append(p_item)

    sanitized_geotags = []
    for g in listing.get("geotags", []):
        g_item = dict(g)
        if not is_authorized:
            # Obfuscate exact sub-meter GPS for public callers; preserve boundary verification claim
            if "latitude" in g_item and g_item["latitude"] is not None:
                g_item["latitude"] = round(float(g_item["latitude"]), 2)
            if "longitude" in g_item and g_item["longitude"] is not None:
                g_item["longitude"] = round(float(g_item["longitude"]), 2)
            g_item["exact_coordinates_hidden"] = True
        sanitized_geotags.append(g_item)

    return {
        "success": True,
        "farm_id": safe_id,
        "demo_mode": flags["demo_mode"],
        "components": {
            "practice_photo": flags["practice_photo"],
            "geotag_inside_boundary": flags["geotag_inside_boundary"],
        },
        "photo_count": flags["photo_count"],
        "geotag_count": flags["geotag_count"],
        "last_photo_at": flags["last_photo_at"],
        "photos": sanitized_photos,
        "geotags": sanitized_geotags,
    }


@router.get("/farms/{farm_id}/evidence/photo/{sha256}")
def get_evidence_photo(
    farm_id: str,
    sha256: str,
    current_user: Optional[dict] = Depends(get_current_user_optional),
):
    """Retrieve an evidence photo file by farm_id and its SHA-256 hash.
    
    Access requires farm owner / verifier authorization unless the photo has explicit public consent.
    """
    safe_id = _safe_farm_id(farm_id)
    clean_sha = str(sha256).strip().lower()
    if not re.match(r"^[0-9a-f]{16,64}$", clean_sha):
        raise HTTPException(status_code=400, detail="Invalid sha256 identifier")

    folder = os.path.join(evidence.evidence_dir(), safe_id)
    pattern = os.path.join(folder, f"{clean_sha[:16]}.*")
    matches = [p for p in glob.glob(pattern) if os.path.isfile(p)]
    if not matches:
        raise HTTPException(status_code=404, detail="Photo not found")
    filepath = matches[0]
    real_path = os.path.realpath(filepath)
    real_folder = os.path.realpath(folder)
    if not (real_path.startswith(real_folder + os.sep) or real_path == real_folder):
        raise HTTPException(status_code=404, detail="Photo not found")

    # Consent and authorization check
    records = evidence.list_records(safe_id)
    photo_rec = next((r for r in records if r.get("sha256") and r.get("sha256", "").lower().startswith(clean_sha[:16])), None)
    is_public = bool(photo_rec and photo_rec.get("is_public"))

    caller_phone = (current_user or {}).get("phone")
    caller_role = (current_user or {}).get("role")
    farm = _load_farm(safe_id)
    is_owner = bool(farm and caller_phone and farm.get("owner_phone") == caller_phone)
    is_creator = bool(caller_phone and photo_rec and photo_rec.get("created_by") == caller_phone)
    is_authorized = is_owner or is_creator or (caller_role in ("admin", "fpo", "verifier"))

    if not is_public and not is_authorized:
        raise HTTPException(
            status_code=403,
            detail="Evidence photo is private. Farm owner or verifier authorization required.",
        )

    ext = os.path.splitext(filepath)[1].lower().lstrip(".")
    mime_map = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}
    return FileResponse(filepath, media_type=mime_map.get(ext, "image/jpeg"))

