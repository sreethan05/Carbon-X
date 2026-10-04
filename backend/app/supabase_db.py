import os
from datetime import datetime, timezone
from typing import List, Optional, TypedDict, Any


class ListingRow(TypedDict, total=False):
    id: str
    farm_id: str
    farmer_phone: str
    farmer_name: str
    location: str
    crop: str
    size_label: str
    listing_model: str
    price_per_credit: float
    current_bid: float
    bids_count: int
    total_credits: float
    carbon_credits: float
    biodiversity_credits: float
    status: str
    token_id: Optional[str]
    tx_hash: Optional[str]
    image_url: Optional[str]
    expires_at: Optional[str]
    created_at: str
    updated_at: str


class FarmRow(TypedDict, total=False):
    id: str
    owner_phone: str
    name: str
    crop_type: str
    irrigation: str
    geojson: dict
    area_hectares: float
    ndvi: float
    evi: float
    carbon_tonnes: float
    biodiversity_score: float
    total_credits: float
    status: str
    badge: Optional[str]
    fpo_id: Optional[str]
    token_id: Optional[str]
    last_monitor_ndvi: Optional[float]
    last_monitored_at: Optional[str]
    created_at: str
    updated_at: str


class ProfileRow(TypedDict, total=False):
    id: str
    phone: str
    name: str
    role: str
    state: Optional[str]
    district: Optional[str]
    village: Optional[str]
    upi: Optional[str]
    aadhaar_last4: Optional[str]
    fpo_id: Optional[str]
    preferred_language: Optional[str]
    created_at: str
    updated_at: str


class FpoRow(TypedDict, total=False):
    id: str
    name: str
    registration_no: str
    created_at: str
    updated_at: str


class CorporateRow(TypedDict, total=False):
    c_id: str
    name: str
    password_hash: Optional[str]
    created_at: str
    updated_at: str


class KycVerificationRow(TypedDict, total=False):
    id: str
    owner_phone: str
    status: str
    reasons: Any
    checks: Any
    extracted_fields: Any
    document_name: str
    document_sha256: str
    perceptual_hash: Optional[str]
    created_at: str


class LedgerEventRow(TypedDict, total=False):
    id: str
    entity_id: str
    seq: int
    event_type: str
    payload: Any
    payload_json: str
    ts: str
    prev_hash: str
    hash: str


class GroundTruthSampleRow(TypedDict, total=False):
    id: str
    farm_id: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    measured_soc_tco2e_ha: Optional[float]
    measured_species_count: Optional[int]
    source: str
    measured_at: Optional[str]
    notes: Optional[str]
    created_at: str


class LandRegistryRow(TypedDict, total=False):
    id: str
    survey_number: str
    owner_name: str
    area_ha: float
    village: str
    mandal: str
    district: str
    tier: str
    registry_geometry_available: bool
    geojson: Optional[dict]
    created_at: str
    updated_at: str


class FpoMemberRow(TypedDict, total=False):
    id: str
    fpo_id: str
    farmer_phone: str
    joined_at: str


_supabase = None
_ready = False


def _client():
    global _supabase, _ready
    if _supabase is not None:
        return _supabase
    url = os.getenv("SUPABASE_URL", "").strip() or os.getenv("VITE_SUPABASE_URL", "").strip()
    key = (
        os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        or os.getenv("SUPABASE_ANON_KEY", "").strip()
        or os.getenv("VITE_SUPABASE_ANON_KEY", "").strip()
    )
    if not url or not key:
        print("Supabase not configured (SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY)")
        _ready = False
        return None
    try:
        from supabase import create_client
        _supabase = create_client(url, key)
        _ready = True
        print("Supabase connected")
        return _supabase
    except Exception as e:
        print(f"Supabase init failed: {e}")
        _ready = False
        return None


def is_ready() -> bool:
    return _client() is not None


def health_check() -> dict:
    sb = _client()
    if not sb:
        return {"ready": False, "tables": {}, "message": "Supabase client is not configured"}
    tables = {}
    for table in (
        "profiles",
        "fpos",
        "corporates",
        "farms",
        "marketplace_listings",
        "otp_codes",
        "kyc_verifications",
    ):
        try:
            sb.table(table).select("*").limit(1).execute()
            tables[table] = True
        except Exception as e:
            tables[table] = False
            print(f"Supabase health check failed for {table}: {e}")
    return {"ready": all(tables.values()), "tables": tables}


def get_profile(phone: str) -> Optional[ProfileRow]:
    sb = _client()
    if not sb:
        return None
    res = sb.table("profiles").select("*").eq("phone", phone).limit(1).execute()
    rows = res.data or []
    return rows[0] if rows else None


def upsert_profile(profile: dict) -> bool:
    sb = _client()
    if not sb:
        return False
    profile["updated_at"] = datetime.now(timezone.utc).isoformat()
    sb.table("profiles").upsert(profile, on_conflict="phone").execute()
    return True


def update_profile(phone: str, fields: dict) -> Optional[dict]:
    sb = _client()
    if not sb:
        return None
    fields["updated_at"] = datetime.now(timezone.utc).isoformat()
    res = sb.table("profiles").update(fields).eq("phone", phone).execute()
    rows = res.data or []
    if rows:
        return rows[0]
    return get_profile(phone)


def get_document_hashes() -> list[str]:
    sb = _client()
    if not sb:
        return []
    res = sb.table("kyc_verifications").select("document_sha256").execute()
    return [row["document_sha256"] for row in (res.data or []) if row.get("document_sha256")]


def insert_kyc_verification(record: dict) -> Optional[dict]:
    sb = _client()
    if not sb:
        return None
    res = sb.table("kyc_verifications").insert(record).execute()
    rows = res.data or []
    return rows[0] if rows else None


def get_kyc_status(phone: str) -> Optional[dict]:
    """Fetch the most recent KYC verification record for a phone number."""
    sb = _client()
    if not sb:
        return None
    res = (
        sb.table("kyc_verifications")
        .select("*")
        .eq("owner_phone", phone)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    rows = res.data or []
    return rows[0] if rows else None


def store_otp(phone: str, otp: str, expires_at: datetime) -> bool:
    sb = _client()
    if not sb:
        return False
    sb.table("otp_codes").upsert({
        "phone": phone,
        "otp": otp,
        "expires_at": expires_at.isoformat(),
    }, on_conflict="phone").execute()
    return True


def verify_otp_db(phone: str, otp: str) -> bool:
    sb = _client()
    if not sb:
        return False
    res = sb.table("otp_codes").select("*").eq("phone", phone).limit(1).execute()
    rows = res.data or []
    if not rows:
        return False
    row = rows[0]
    exp = datetime.fromisoformat(row["expires_at"].replace("Z", "+00:00"))
    if datetime.now(timezone.utc) > exp:
        sb.table("otp_codes").delete().eq("phone", phone).execute()
        return False
    if row["otp"] != otp:
        return False
    sb.table("otp_codes").delete().eq("phone", phone).execute()
    return True


def clear_otp(phone: str) -> bool:
    sb = _client()
    if not sb:
        return False
    sb.table("otp_codes").delete().eq("phone", phone).execute()
    return True


def get_farms(phone: str) -> list:
    sb = _client()
    if not sb:
        return []
    res = (
        sb.table("farms")
        .select("*")
        .eq("owner_phone", phone)
        .order("created_at", desc=True)
        .execute()
    )
    return res.data or []


def insert_farm(farm: dict) -> Optional[dict]:
    sb = _client()
    if not sb:
        return None
    try:
        res = sb.table("farms").insert(farm).execute()
        rows = res.data or []
        return rows[0] if rows else None
    except Exception as e:
        print(f"Supabase insert_farm failed: {e}")
        return None


def update_farm(farm_id: str, fields: dict) -> Optional[dict]:
    sb = _client()
    if not sb:
        return None
    fields["updated_at"] = datetime.now(timezone.utc).isoformat()
    res = sb.table("farms").update(fields).eq("id", farm_id).execute()
    rows = res.data or []
    return rows[0] if rows else None


def get_listings(status: Optional[str] = "Active") -> List[ListingRow]:
    sb = _client()
    if not sb:
        return []
    q = sb.table("marketplace_listings").select("*").order("created_at", desc=True)
    if status:
        q = q.eq("status", status)
    res = q.execute()
    return res.data or []


LISTING_SORT_COLUMNS = {
    "created_at",
    "updated_at",
    "price_per_credit",
    "total_credits",
    "carbon_credits",
    "biodiversity_credits",
    "expires_at",
}


def get_listings_filtered(
    status: Optional[str] = "Active",
    crop: Optional[str] = None,
    location: Optional[str] = None,
    farmer_phone: Optional[str] = None,
    farm_id: Optional[str] = None,
    listing_model: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    min_credits: Optional[float] = None,
    max_credits: Optional[float] = None,
    search: Optional[str] = None,
    sort: str = "created_at",
    order: str = "desc",
    limit: int = 50,
    offset: int = 0,
) -> dict:
    sb = _client()
    if not sb:
        return {"total": 0, "listings": []}

    q = sb.table("marketplace_listings").select("*", count="exact")

    if status and status.strip().lower() != "all":
        q = q.eq("status", status)
    if crop:
        q = q.ilike("crop", f"*{crop}*")
    if location:
        q = q.ilike("location", f"*{location}*")
    if farmer_phone:
        q = q.eq("farmer_phone", farmer_phone)
    if farm_id:
        q = q.eq("farm_id", farm_id)
    if listing_model:
        q = q.ilike("listing_model", f"*{listing_model}*")
    if min_price is not None:
        q = q.gte("price_per_credit", min_price)
    if max_price is not None:
        q = q.lte("price_per_credit", max_price)
    if min_credits is not None:
        q = q.gte("total_credits", min_credits)
    if max_credits is not None:
        q = q.lte("total_credits", max_credits)
    if search:
        clean = "".join(ch for ch in search if ch not in ",()*")
        if clean:
            pattern = f"*{clean}*"
            q = q.or_(
                f"farmer_name.ilike.{pattern},crop.ilike.{pattern},location.ilike.{pattern}"
            )

    sort_col = sort if sort in LISTING_SORT_COLUMNS else "created_at"
    descending = str(order).lower() != "asc"
    limit = max(1, limit)
    res = q.order(sort_col, desc=descending).range(offset, offset + limit - 1).execute()

    return {"total": res.count, "listings": res.data or []}


def insert_listing(listing: dict) -> Optional[dict]:
    sb = _client()
    if not sb:
        return None
    res = sb.table("marketplace_listings").insert(listing).execute()
    rows = res.data or []
    return rows[0] if rows else listing


def compute_credits(carbon_tonnes: float, biodiversity_score: float) -> dict:
    """Deprecated shim — canonical implementation is credit_engine.credit_split."""
    from app.services.credit_engine import credit_split
    return credit_split(carbon_tonnes, biodiversity_score)


def get_land_registry(survey_number: str) -> Optional[dict]:
    sb = _client()
    if not sb:
        return None
    try:
        res = (
            sb.table("land_registry")
            .select("*")
            .ilike("survey_number", survey_number.strip())
            .limit(1)
            .execute()
        )
    except Exception as exc:
        msg = str(exc)
        if "permission denied" in msg.lower() or "42501" in msg:
            raise PermissionError(
                "permission denied for table land_registry. "
                "Run: GRANT SELECT ON public.land_registry TO service_role;"
            ) from exc
        raise
    rows = res.data or []
    return rows[0] if rows else None


def get_farm(farm_id: str) -> Optional[FarmRow]:
    sb = _client()
    if not sb:
        return None
    res = sb.table("farms").select("*").eq("id", farm_id).limit(1).execute()
    rows = res.data or []
    return rows[0] if rows else None


def list_fpos() -> list:
    sb = _client()
    if not sb:
        return []
    try:
        res = sb.table("fpos").select("id,name,registration_no,created_at").order("name").execute()
        return res.data or []
    except Exception as exc:
        print(f"list_fpos failed: {exc}")
        return []


def list_farms_by_status(status: str, owner_phones: Optional[list] = None) -> list:
    sb = _client()
    if not sb:
        return []
    q = sb.table("farms").select("*").eq("status", status).order("created_at", desc=True)
    if owner_phones:
        q = q.in_("owner_phone", owner_phones)
    res = q.execute()
    return res.data or []


def list_profiles_by_fpo(fpo_id: str) -> list:
    sb = _client()
    if not sb:
        return []
    res = sb.table("profiles").select("*").eq("fpo_id", fpo_id).execute()
    return res.data or []


def farm_geojsons_except(owner_phone: str) -> list:
    sb = _client()
    if not sb:
        return []
    res = sb.table("farms").select("id,geojson,owner_phone").neq("owner_phone", owner_phone).execute()
    return [row.get("geojson") for row in (res.data or []) if row.get("geojson")]


def insert_farm_safe(farm: dict) -> Optional[dict]:
    """Insert a farm, dropping unknown columns (badge) if the DB rejects them."""
    saved = insert_farm(farm)
    if saved:
        return saved
    stripped = {k: v for k, v in farm.items() if k != "badge"}
    if stripped != farm:
        return insert_farm(stripped)
    return None