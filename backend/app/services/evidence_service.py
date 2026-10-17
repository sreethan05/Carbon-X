"""Farm evidence capture: practice photos, EXIF GPS geotags, boundary checks.

This is the real capture pipeline behind the passport's evidence-quality
components ``practice_photo`` / ``geotag_inside_boundary`` (see
``credit_engine.evidence_quality``). Nothing here ever fabricates a coordinate
or an inside-boundary verdict: every flag is derived from stored records.

Storage
-------
- Files: ``backend/data/evidence/{safe_farm_id}/{sha256[:16]}.{ext}``.
  Override the base dir with ``CARBONX_EVIDENCE_DIR`` (tests use a tmpdir).
- Metadata: the Supabase ``farm_evidence`` table when the live DB is ready
  (``supabase/08_farm_evidence.sql``); otherwise an in-memory store keyed by
  farm id (process lifetime, like ``market_store``). Responses and
  ``evidence_flags`` carry ``demo_mode`` whenever only the memory fallback
  was written — the caller must not present that as durable persistence.
"""
import hashlib
import io
import math
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from typing import Optional

from PIL import Image

from app import supabase_db as db

MAX_PHOTO_BYTES = 8 * 1024 * 1024
ALLOWED_MIME_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})

_FORMAT_INFO = {
    "JPEG": ("image/jpeg", "jpg"),
    "PNG": ("image/png", "png"),
    "WEBP": ("image/webp", "webp"),
}
_SAFE_FARM_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")

# evidence_flags / GET scan at most this many newest records per farm.
_FLAGS_LIST_LIMIT = 500

# Fields safe to expose on the open GET /farms/{id}/evidence listing
# (created_by is deliberately omitted: it is the uploader's phone number).
_PUBLIC_FIELDS = (
    "id",
    "kind",
    "sha256",
    "mime",
    "size_bytes",
    "latitude",
    "longitude",
    "inside_boundary",
    "captured_at",
    "created_at",
)

_LOCK = threading.RLock()
_MEMORY: dict = {}


# ─── Errors ───

class EvidenceImageError(ValueError):
    """Uploaded bytes are not a real JPEG/PNG/WebP image."""


class PhotoTooLargeError(EvidenceImageError):
    """Upload exceeds :data:`MAX_PHOTO_BYTES`."""


# ─── Paths & memory fallback ───

def evidence_dir() -> str:
    """Base directory for stored evidence files (env-overridable for tests)."""
    override = os.getenv("CARBONX_EVIDENCE_DIR", "").strip()
    if override:
        return override
    backend_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(backend_root, "data", "evidence")


def sanitize_farm_id(farm_id: str) -> Optional[str]:
    """Return the id when it only contains [A-Za-z0-9_-], else ``None``.

    Blocks path separators, "..", and anything else unsafe for a directory
    name; the router turns ``None`` into a 400 envelope.
    """
    text = str(farm_id or "").strip()
    if not text or not _SAFE_FARM_ID_RE.match(text):
        return None
    return text


def reset_memory():
    """Clear the in-memory fallback store (tests / process hygiene)."""
    with _LOCK:
        _MEMORY.clear()


def _memory_append(row: dict):
    with _LOCK:
        _MEMORY.setdefault(row["farm_id"], []).append(dict(row))


def _memory_rows(farm_id: str) -> list:
    with _LOCK:
        return [dict(r) for r in _MEMORY.get(farm_id, [])]


# ─── Hashing ───

def sha256_hex(data: bytes) -> str:
    """Stable content hash used as the evidence pointer on disk and in DB."""
    return hashlib.sha256(data).hexdigest()


# ─── Image validation & EXIF GPS ───

def _rational_to_float(value) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    return number if math.isfinite(number) else None


def _gps_coord_to_degrees(value) -> Optional[float]:
    """Convert (deg, min, sec) — Pillow floats/IFDRationals — or scalar degrees."""
    if value is None:
        return None
    if isinstance(value, (tuple, list)):
        parts = [_rational_to_float(v) for v in list(value)[:3]]
        if not parts or any(p is None for p in parts):
            return None
        degrees = abs(parts[0])
        minutes = abs(parts[1]) if len(parts) > 1 else 0.0
        seconds = abs(parts[2]) if len(parts) > 2 else 0.0
        return degrees + minutes / 60.0 + seconds / 3600.0
    val = _rational_to_float(value)
    return abs(val) if val is not None else None


def _gps_ref(value) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, bytes):
        value = value.decode("ascii", "ignore")
    text = str(value).strip().upper()
    return text[:1] or None


def _apply_hemisphere(value: float, ref: Optional[str], positive: str, negative: str) -> Optional[float]:
    """Sign a coordinate from its hemisphere reference; refuse to guess."""
    if ref == positive:
        return abs(value)
    if ref == negative:
        return -abs(value)
    return None


def parse_exif_gps(exif) -> Optional[dict]:
    """Extract (latitude, longitude) from a Pillow ``Image.Exif`` GPS IFD.

    Returns ``{"latitude": float, "longitude": float}`` or ``None`` when the
    IFD is missing/incomplete, the values are unreadable or out of WGS84
    range, or a hemisphere reference is absent (an unlabelled coordinate is
    never guessed as N/E). Never raises and never fabricates a value.
    """
    if exif is None:
        return None
    try:
        gps = exif.get_ifd(34853)
    except Exception:
        return None
    if not gps:
        return None
    lat = _gps_coord_to_degrees(gps.get(2))
    lon = _gps_coord_to_degrees(gps.get(4))
    if lat is None or lon is None:
        return None
    latitude = _apply_hemisphere(lat, _gps_ref(gps.get(1)), "N", "S")
    longitude = _apply_hemisphere(lon, _gps_ref(gps.get(3)), "E", "W")
    if latitude is None or longitude is None:
        return None
    if not (-90.0 <= latitude <= 90.0 and -180.0 <= longitude <= 180.0):
        return None
    return {"latitude": round(latitude, 7), "longitude": round(longitude, 7)}


def extract_exif_gps(data: bytes) -> Optional[dict]:
    """Pull GPS coordinates from image bytes; ``None`` when absent/invalid."""
    try:
        with Image.open(io.BytesIO(data)) as image:
            exif = image.getexif()
    except Exception:
        return None
    return parse_exif_gps(exif)


def inspect_photo(data: bytes) -> dict:
    """Validate a real image upload and read its EXIF GPS.

    Returns ``{"mime": str, "ext": str, "exif": {"latitude","longitude"} | None}``.
    Raises :class:`PhotoTooLargeError` / :class:`EvidenceImageError` — the
    format is derived from the actual bytes via Pillow, never from the
    declared content type alone.
    """
    if not data:
        raise EvidenceImageError("Uploaded file is empty")
    if len(data) > MAX_PHOTO_BYTES:
        raise PhotoTooLargeError("Photo exceeds the 8 MB limit")
    try:
        with Image.open(io.BytesIO(data)) as image:
            fmt = str(image.format or "").upper()
            # verify() must run directly after open (Pillow requirement for
            # some formats, e.g. PNG); EXIF is read from a second open below.
            image.verify()
    except EvidenceImageError:
        raise
    except Exception as exc:
        raise EvidenceImageError("Uploaded file is not a valid image") from exc
    if fmt not in _FORMAT_INFO:
        raise EvidenceImageError("Only JPEG, PNG, or WebP photos are accepted")
    # extract_exif_gps never raises: a corrupt EXIF block must not reject an
    # otherwise valid photo, it just means no geotag.
    exif = extract_exif_gps(data)
    mime, ext = _FORMAT_INFO[fmt]
    return {"mime": mime, "ext": ext, "exif": exif}


def store_photo_file(farm_id: str, data: bytes, sha256: str, ext: str) -> str:
    """Write original bytes to the evidence tree; returns the stored path."""
    safe = sanitize_farm_id(farm_id)
    if safe is None:
        raise ValueError("farm_id may only contain [A-Za-z0-9_-]")
    folder = os.path.join(evidence_dir(), safe)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"{sha256[:16]}.{ext}")
    with open(path, "wb") as handle:
        handle.write(data)
    return path


# ─── Point-in-polygon (pure Python ray casting) ───
from app.services.polygon_service import (
    _extract_polygons,
    _ring_points,
    _point_on_segment,
    _ring_contains,
    point_in_polygon,
    verify_inside_boundary,
)


# ─── Record persistence & reads ───

def persist_record(record: dict) -> bool:
    """Insert one evidence record.

    Live DB ready -> ``farm_evidence`` insert (``False`` when the write
    fails — the caller must surface that error rather than pretend it was
    persisted). DB off -> in-memory fallback (``demo_mode`` everywhere).
    """
    if db.is_ready():
        sb = db._client()
        if sb is None:
            return False
        try:
            sb.table("farm_evidence").insert(record).execute()
            return True
        except Exception as exc:
            print(f"farm_evidence insert failed: {exc}")
            return False
    row = dict(record)
    row.setdefault("id", uuid.uuid4().hex)
    row.setdefault("created_at", datetime.now(timezone.utc).isoformat())
    _memory_append(row)
    return True


def list_records(farm_id: str, limit: int = _FLAGS_LIST_LIMIT) -> list:
    """Stored evidence records for a farm, newest first (DB when ready)."""
    safe_id = sanitize_farm_id(farm_id)
    if safe_id is None:
        return []
    cap = max(1, int(limit))
    if db.is_ready():
        sb = db._client()
        if sb is None:
            return []
        try:
            response = (
                sb.table("farm_evidence")
                .select("*")
                .eq("farm_id", safe_id)
                .order("created_at", desc=True)
                .limit(cap)
                .execute()
            )
            return response.data or []
        except Exception as exc:
            print(f"farm_evidence read failed: {exc}")
            return []
    rows = _memory_rows(safe_id)
    rows.sort(key=lambda row: (str(row.get("created_at") or ""), str(row.get("id") or "")), reverse=True)
    return rows[:cap]


def _record_public(row: dict) -> dict:
    return {field: row.get(field) for field in _PUBLIC_FIELDS}


def list_evidence(farm_id: str, per_kind: int = 20) -> dict:
    """Public GET listing: newest-first photos and coordinate records, capped.

    ``geotags`` includes explicit geotag records and photos whose EXIF/form
    coordinates were stored — anything with a real coordinate pair.
    """
    rows = list_records(farm_id)
    photos = [_record_public(row) for row in rows if row.get("kind") == "photo"]
    geotags = [
        _record_public(row)
        for row in rows
        if row.get("latitude") is not None and row.get("longitude") is not None
    ]
    return {"photos": photos[:per_kind], "geotags": geotags[:per_kind]}


def evidence_flags(farm_id: str) -> dict:
    """Evidence flags for ``credit_engine.evidence_quality``.

    Returns::

        {"practice_photo": bool, "geotag_inside_boundary": bool,
         "demo_mode": bool, "photo_count": int, "geotag_count": int,
         "last_photo_at": str | None}

    ``practice_photo`` is True iff at least one accepted photo record is
    stored. ``geotag_inside_boundary`` is True iff at least one stored
    coordinate record (EXIF GPS or explicit geotag) was verified inside the
    farm boundary at capture time and recorded as such. Both are derived from
    stored records only; counts scan the newest ``_FLAGS_LIST_LIMIT`` records.
    """
    rows = list_records(farm_id)
    photos = [row for row in rows if row.get("kind") == "photo"]
    coordinate_rows = [
        row for row in rows
        if row.get("latitude") is not None and row.get("longitude") is not None
    ]
    last_photo_at = None
    for row in photos:
        created = str(row.get("created_at") or "")
        if created and (last_photo_at is None or created > last_photo_at):
            last_photo_at = created
    return {
        "practice_photo": bool(photos),
        "geotag_inside_boundary": any(bool(row.get("inside_boundary")) for row in coordinate_rows),
        "demo_mode": not db.is_ready(),
        "photo_count": len(photos),
        "geotag_count": len(coordinate_rows),
        "last_photo_at": last_photo_at,
    }
