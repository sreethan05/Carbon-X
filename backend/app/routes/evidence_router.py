"""Farm evidence routes: practice photos + geotags (see evidence_service).

Registered by the orchestrator in ``app/main.py``. Endpoints:

- ``POST /farms/{farm_id}/evidence/photo``      multipart photo upload (auth)
- ``POST /farms/{farm_id}/evidence/geotag``     explicit coordinate record (auth)
- ``GET  /farms/{farm_id}/evidence``            open listing (transparency, like /passport)
"""
import glob
import io
import math
import os
import re
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
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
        from app.services.access_policy import is_fpo_for_farm
        # Resolve the officer's FPO server-side and support legacy farm rows
        # linked through the owner's profile. Missing scope fails closed.
        if not is_fpo_for_farm(current_user, farm):
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


def _caller_can_view_full(
    farm: Optional[dict],
    current_user: Optional[dict],
    farm_id: Optional[str] = None,
) -> bool:
    """Owner/staff and the farm's own FPO may see exact GPS and all metadata."""
    if not current_user:
        return False
    role = str(current_user.get("role") or "farmer").lower()
    if role in ("admin", "verifier"):
        return True
    phone = current_user.get("phone")
    if farm and phone and farm.get("owner_phone") == phone:
        return True
    if role == "fpo" and farm and phone and db.is_ready():
        from app.services.access_policy import is_fpo_for_farm
        return is_fpo_for_farm(current_user, farm)
    # Demo/offline mode has no farm table to prove ownership from.  The
    # uploader recorded on the evidence row is the only available proof, so
    # grant them full access to their own farm's evidence.
    if not farm and farm_id and phone and not db.is_ready():
        rows = evidence.list_records(farm_id)
        return any(r.get("created_by") == phone for r in rows)
    return False


def _photo_without_exif(filepath: str, mime: str) -> Response:
    """Serve a public photo with all EXIF (including GPS) removed."""
    try:
        from PIL import Image
        with Image.open(filepath) as img:
            # copy() drops EXIF/ICC metadata; save() receives no exif argument.
            clean = img.copy()
            buf = io.BytesIO()
            clean.save(buf, format={"image/png": "PNG", "image/webp": "WEBP"}.get(mime, "JPEG"))
            return Response(content=buf.getvalue(), media_type=mime)
    except Exception:
        # Never fall back to the original bytes (they may contain GPS).
        raise HTTPException(status_code=503, detail="Public photo could not be sanitised")


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
    """Evidence presence is public; exact GPS and private files are not.

    Public callers get counts, verification booleans and only photos the
    farmer explicitly marked public.  Exact coordinates, creator phone numbers
    and private metadata stay with owner/FPO/verifier and staff.
    """
    safe_id = _safe_farm_id(farm_id)
    flags = evidence.evidence_flags(safe_id)
    listing = evidence.list_evidence(safe_id)
    farm = _load_farm(safe_id)
    full = _caller_can_view_full(farm, current_user, farm_id=safe_id)

    if full:
        photos = [{k: v for k, v in dict(p).items() if not str(k).startswith("_")}
                  for p in listing.get("photos", [])]
        geotags = [{k: v for k, v in dict(g).items() if not str(k).startswith("_")}
                   for g in listing.get("geotags", [])]
    else:
        photos = []
        for p in listing.get("photos", []):
            if not p.get("is_public"):
                continue
            photos.append({
                "sha256": p.get("sha256"),
                "mime": p.get("mime"),
                "size_bytes": p.get("size_bytes"),
                "captured_at": p.get("captured_at"),
                "inside_boundary": p.get("inside_boundary"),
                "is_public": True,
            })
        # No geotag record is public: a geotag is exact farm location.
        geotags = []

    return {
        "success": True,
        "farm_id": safe_id,
        "demo_mode": flags["demo_mode"],
        "access": {
            "level": "full" if full else "public",
            "exact_coordinates": bool(full),
            "private_photos": bool(full),
        },
        "components": {
            "practice_photo": flags["practice_photo"],
            "geotag_inside_boundary": flags["geotag_inside_boundary"],
        },
        "photo_count": flags["photo_count"],
        "geotag_count": flags["geotag_count"],
        "last_photo_at": flags["last_photo_at"],
        "photos": photos,
        "geotags": geotags,
        "public_redaction_note": (
            None if full else
            "Only public-consent photos are listed without GPS/creator metadata. "
            "Geotag coordinates are private."
        ),
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
    farm = _load_farm(safe_id)
    is_creator = bool(caller_phone and photo_rec and photo_rec.get("created_by") == caller_phone)
    is_authorized = _caller_can_view_full(farm, current_user) or is_creator

    if not is_public and not is_authorized:
        raise HTTPException(
            status_code=403,
            detail="Evidence photo is private. Farm owner or verifier authorization required.",
        )

    ext = os.path.splitext(filepath)[1].lower().lstrip(".")
    mime_map = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}
    mime = mime_map.get(ext, "image/jpeg")
    if is_public and not is_authorized:
        # Public consent covers the practice photo, not the GPS embedded in it.
        return _photo_without_exif(filepath, mime)
    return FileResponse(filepath, media_type=mime)

