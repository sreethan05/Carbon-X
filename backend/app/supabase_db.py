import os
import re
import secrets
import logging
from datetime import datetime, timezone
from typing import List, Optional, TypedDict, Any

logger = logging.getLogger("carbonx.supabase_db")


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
    biodiversity_credits: Optional[float]
    soil_moisture: Optional[float]
    tree_cover: Optional[float]
    vegetation_health: Optional[str]
    satellite_source: Optional[str]
    ai_confidence: Optional[float]
    credits_ci90_low: Optional[float]
    credits_ci90_high: Optional[float]
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
    wallet_address: Optional[str]
    created_at: str
    updated_at: str


class FpoRow(TypedDict, total=False):
    id: str
    name: str
    registration_no: str
    created_at: str
    updated_at: str


class CorporateRow(TypedDict, total=False):
    c_id: Any
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
_logged_unconfigured = False


def _client():
    global _supabase, _ready, _logged_unconfigured
    if _supabase is not None:
        return _supabase
    url = os.getenv("SUPABASE_URL", "").strip() or os.getenv("VITE_SUPABASE_URL", "").strip()
    key = (
        os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        or os.getenv("SUPABASE_ANON_KEY", "").strip()
        or os.getenv("VITE_SUPABASE_ANON_KEY", "").strip()
    )
    if not url or not key:
        if not _logged_unconfigured:
            print("Supabase not configured (SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY)")
            _logged_unconfigured = True
        _ready = False
        return None
    try:
        from supabase import create_client
        _supabase = create_client(url, key)
        _ready = True
        _logged_unconfigured = False
        print("Supabase connected")
        return _supabase
    except Exception as e:
        print(f"Supabase init failed: {e}")
        _ready = False
        return None


def is_ready() -> bool:
    return _client() is not None


# Tables (and the columns within them) every feature needs.  The probe is
# deliberately stricter than the row-level health check above: a deployment
# where a migration was never applied must NOT report healthy while its
# privacy / lifecycle / validation features would fail at runtime.
_REQUIRED_SCHEMA: dict[str, tuple[str, ...]] = {
    "profiles": ("phone", "role", "fpo_id", "name"),
    "fpos": ("name", "registration_no"),
    "corporates": ("name", "password_hash"),
    "farms": ("owner_phone", "fpo_id", "badge", "carbon_tonnes",
              "credits_ci90_low", "credits_ci90_high", "last_monitor_ndvi"),
    "marketplace_listings": ("farmer_phone", "farm_id", "total_credits",
                             "credits_sold", "lifecycle_state", "dispute_status"),
    "kyc_verifications": ("owner_phone", "document_sha256", "document_deleted_at"),
    "otp_codes": (),
    "ledger_events": ("entity_id", "seq", "event_type", "hash", "prev_hash"),
    "land_registry": ("survey_number", "tier"),
    "fpo_members": ("fpo_id", "farmer_phone"),
    "ground_truth_samples": ("measurement_type", "estimate_snapshot",
                             "verification_status", "verified_by"),
    "farm_evidence": ("farm_id", "kind", "sha256", "deleted_at"),
    "consent_records": ("phone", "purpose", "granted"),
    "privacy_requests": ("phone", "kind", "status"),
    "corporate_settings": ("c_id", "target_credits"),
    "support_tickets": ("ticket_id", "reporter_phone", "category", "status",
                        "resolution"),
}

_migration_status_cache: Optional[tuple[float, dict]] = None
_MIGRATION_CACHE_TTL_SECONDS = 60.0


def _required_schema_snapshot() -> dict[str, set[str]]:
    """Fetch the live PostgREST OpenAPI schema (one request) as
    {table: {column, ...}}.  Raises on failure — callers degrade honestly."""
    import httpx

    url = (os.getenv("SUPABASE_URL", "").strip()
           or os.getenv("VITE_SUPABASE_URL", "").strip()).rstrip("/")
    key = (os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
           or os.getenv("SUPABASE_ANON_KEY", "").strip()
           or os.getenv("VITE_SUPABASE_ANON_KEY", "").strip())
    if not url or not key:
        raise RuntimeError("Supabase not configured")
    res = httpx.get(f"{url}/rest/v1/", headers={"apikey": key, "Authorization": f"Bearer {key}"},
                    timeout=10.0)
    res.raise_for_status()
    definitions = (res.json() or {}).get("definitions") or {}
    out: dict[str, set[str]] = {}
    for table, spec in definitions.items():
        out[table] = set(((spec or {}).get("properties") or {}).keys())
    return out


def migration_status() -> dict:
    """Which required tables/columns are missing from the live database?

    Cached for a minute so /health stays cheap.  ``checked`` is False when
    the database is unreachable or unconfigured — never a silent "looks fine".
    """
    global _migration_status_cache
    now = datetime.now(timezone.utc).timestamp()
    if _migration_status_cache and now - _migration_status_cache[0] < _MIGRATION_CACHE_TTL_SECONDS:
        cached = dict(_migration_status_cache[1])
        return cached
    result: dict = {
        "checked": False, "ok": None,
        "missing_tables": [], "missing_columns": {},
        "note": "Schema probe unavailable — database may be unconfigured or unreachable",
    }
    sb = _client()
    if sb:
        try:
            live = _required_schema_snapshot()
        except Exception as e:
            result["error"] = str(e)
        else:
            missing_tables = sorted(t for t in _REQUIRED_SCHEMA if t not in live)
            missing_columns: dict[str, list] = {}
            for table, cols in _REQUIRED_SCHEMA.items():
                if table not in live:
                    continue
                absent = [c for c in cols if c and c not in live[table]]
                if absent:
                    missing_columns[table] = absent
            ok = not missing_tables and not missing_columns
            result = {
                "checked": True, "ok": ok,
                "missing_tables": missing_tables,
                "missing_columns": missing_columns,
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }
            _migration_status_cache = (now, result)
            return dict(result)
    return result


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
        "fpo_members",
        "ground_truth_samples",
        "ledger_events",
        "land_registry",
        "farm_evidence",
        "consent_records",
        "privacy_requests",
        "corporate_settings",
        "support_tickets",
    ):
        try:
            sb.table(table).select("*").limit(1).execute()
            tables[table] = True
        except Exception as e:
            tables[table] = False
            print(f"Supabase health check failed for {table}: {e}")
    migrations = migration_status()
    if migrations.get("checked") and not migrations.get("ok"):
        print(
            "[health] MISSING REQUIRED DATABASE MIGRATIONS — "
            f"tables={migrations.get('missing_tables')} "
            f"columns={migrations.get('missing_columns')}"
        )
    return {
        "ready": all(tables.values()),
        "tables": tables,
        "migrations": migrations,
        "migrations_ok": migrations.get("ok"),
    }


def get_profile(phone: str) -> Optional[ProfileRow]:
    sb = _client()
    if not sb or not phone:
        return None
    try:
        res = sb.table("profiles").select("*").eq("phone", phone.strip()).limit(1).execute()
        rows = res.data or []
        return rows[0] if rows else None
    except Exception as e:
        logger.warning(f"get_profile failed for {phone}: {e}")
        return None


def get_corporate_by_id(c_id: Any) -> Optional[dict]:
    sb = _client()
    if not sb or c_id is None:
        return None
    try:
        c_str = str(c_id).strip()
        if not re.match(r"^[0-9a-fA-F-]{32,36}$", c_str):
            return None
        res = sb.table("corporates").select("*").eq("c_id", c_str).limit(1).execute()
        rows = res.data or []
        return rows[0] if rows else None
    except Exception as e:
        logger.warning(f"get_corporate_by_id failed for {c_id}: {e}")
        return None


def upsert_profile(profile: dict) -> bool:
    sb = _client()
    if not sb or not profile:
        return False
    try:
        data = {**profile, "updated_at": datetime.now(timezone.utc).isoformat()}
        sb.table("profiles").upsert(data, on_conflict="phone").execute()
        return True
    except Exception as e:
        logger.warning(f"upsert_profile failed: {e}")
        return False


def update_profile(phone: str, fields: dict) -> Optional[dict]:
    sb = _client()
    if not sb or not phone or not fields:
        return None
    try:
        data = {**fields, "updated_at": datetime.now(timezone.utc).isoformat()}
        res = sb.table("profiles").update(data).eq("phone", phone.strip()).execute()
        rows = res.data or []
        if rows:
            return rows[0]
        return get_profile(phone)
    except Exception as e:
        logger.warning(f"update_profile failed for {phone}: {e}")
        return None


def get_document_hashes() -> list[str]:
    sb = _client()
    if not sb:
        return []
    try:
        res = sb.table("kyc_verifications").select("document_sha256").execute()
        return [row["document_sha256"] for row in (res.data or []) if row.get("document_sha256")]
    except Exception as e:
        logger.warning(f"get_document_hashes failed: {e}")
        return []


def insert_kyc_verification(record: dict) -> Optional[dict]:
    sb = _client()
    if not sb or not record:
        return None
    try:
        res = sb.table("kyc_verifications").insert(record).execute()
        rows = res.data or []
        return rows[0] if rows else None
    except Exception as e:
        logger.warning(f"insert_kyc_verification failed: {e}")
        return None


def get_kyc_status(phone: str) -> Optional[dict]:
    """Fetch the most recent KYC verification record for a phone number."""
    sb = _client()
    if not sb or not phone:
        return None
    try:
        res = (
            sb.table("kyc_verifications")
            .select("*")
            .eq("owner_phone", phone.strip())
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        rows = res.data or []
        return rows[0] if rows else None
    except Exception as e:
        logger.warning(f"get_kyc_status failed for {phone}: {e}")
        return None


def store_otp(phone: str, otp: str, expires_at: datetime) -> bool:
    sb = _client()
    if not sb or not phone or not otp:
        return False
    try:
        exp_iso = expires_at.isoformat() if hasattr(expires_at, "isoformat") else str(expires_at)
        sb.table("otp_codes").upsert({
            "phone": phone.strip(),
            "otp": str(otp),
            "expires_at": exp_iso,
        }, on_conflict="phone").execute()
        return True
    except Exception as e:
        logger.warning(f"store_otp failed for {phone}: {e}")
        return False


def verify_otp_db(phone: str, otp: str) -> bool:
    sb = _client()
    if not sb or not phone or not otp:
        return False
    try:
        res = sb.table("otp_codes").select("*").eq("phone", phone.strip()).limit(1).execute()
        rows = res.data or []
        if not rows:
            return False
        row = rows[0]
        exp_raw = str(row.get("expires_at", ""))
        try:
            exp = datetime.fromisoformat(exp_raw.replace("Z", "+00:00"))
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) > exp:
                sb.table("otp_codes").delete().eq("phone", phone.strip()).execute()
                return False
        except (ValueError, TypeError):
            sb.table("otp_codes").delete().eq("phone", phone.strip()).execute()
            return False

        if not secrets.compare_digest(str(row.get("otp", "")), str(otp)):
            return False
        sb.table("otp_codes").delete().eq("phone", phone.strip()).execute()
        return True
    except Exception as e:
        logger.warning(f"verify_otp_db failed for {phone}: {e}")
        return False


def clear_otp(phone: str) -> bool:
    sb = _client()
    if not sb or not phone:
        return False
    try:
        sb.table("otp_codes").delete().eq("phone", phone.strip()).execute()
        return True
    except Exception as e:
        logger.warning(f"clear_otp failed for {phone}: {e}")
        return False


def get_farms(phone: str) -> List[FarmRow]:
    sb = _client()
    if not sb or not phone:
        return []
    try:
        res = (
            sb.table("farms")
            .select("*")
            .eq("owner_phone", phone.strip())
            .order("created_at", desc=True)
            .execute()
        )
        return res.data or []
    except Exception as e:
        logger.warning(f"get_farms failed for {phone}: {e}")
        return []


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
    if not sb or not farm_id or not fields:
        return None
    try:
        data = {**fields, "updated_at": datetime.now(timezone.utc).isoformat()}
        res = sb.table("farms").update(data).eq("id", farm_id.strip()).execute()
        rows = res.data or []
        return rows[0] if rows else None
    except Exception as e:
        logger.warning(f"update_farm failed for {farm_id}: {e}")
        return None


def get_listings(status: Optional[str] = "Active") -> List[ListingRow]:
    sb = _client()
    if not sb:
        return []
    try:
        q = sb.table("marketplace_listings").select("*").order("created_at", desc=True)
        if status:
            q = q.eq("status", status)
        res = q.execute()
        return res.data or []
    except Exception as e:
        logger.warning(f"get_listings failed: {e}")
        return []


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

    try:
        q = sb.table("marketplace_listings").select("*", count="exact")

        if status and status.strip().lower() != "all":
            clean_status = re.sub(r"[^\w\s-]", "", status).strip()
            if clean_status:
                q = q.eq("status", clean_status)
        if crop:
            clean_crop = re.sub(r"[^\w\s-]", "", crop).strip()
            if clean_crop:
                q = q.ilike("crop", f"*{clean_crop}*")
        if location:
            clean_loc = re.sub(r"[^\w\s-]", "", location).strip()
            if clean_loc:
                q = q.ilike("location", f"*{clean_loc}*")
        if farmer_phone:
            clean_phone = re.sub(r"[^\w\s+-]", "", farmer_phone).strip()
            if clean_phone:
                q = q.eq("farmer_phone", clean_phone)
        if farm_id:
            clean_farm_id = re.sub(r"[^\w\s-]", "", farm_id).strip()
            if clean_farm_id:
                q = q.eq("farm_id", clean_farm_id)
        if listing_model:
            clean_model = re.sub(r"[^\w\s-]", "", listing_model).strip()
            if clean_model:
                q = q.ilike("listing_model", f"*{clean_model}*")
        if min_price is not None:
            q = q.gte("price_per_credit", min_price)
        if max_price is not None:
            q = q.lte("price_per_credit", max_price)
        if min_credits is not None:
            q = q.gte("total_credits", min_credits)
        if max_credits is not None:
            q = q.lte("total_credits", max_credits)
        if search:
            clean = re.sub(r"[^\w\s-]", " ", search).strip()
            if clean:
                pattern = f"*{clean}*"
                q = q.or_(
                    f"farmer_name.ilike.{pattern},crop.ilike.{pattern},location.ilike.{pattern}"
                )

        sort_col = sort if sort in LISTING_SORT_COLUMNS else "created_at"
        descending = str(order).lower() != "asc"
        limit = max(1, limit)
        offset = max(0, offset)
        res = q.order(sort_col, desc=descending).range(offset, offset + limit - 1).execute()

        total = res.count if res.count is not None else len(res.data or [])
        return {"total": total, "listings": res.data or []}
    except Exception as e:
        logger.warning(f"get_listings_filtered failed: {e}")
        return {"total": 0, "listings": []}


def insert_listing(listing: dict) -> Optional[dict]:
    sb = _client()
    if not sb or not listing:
        return None
    try:
        res = sb.table("marketplace_listings").insert(listing).execute()
        rows = res.data or []
        return rows[0] if rows else listing
    except Exception as e:
        logger.warning(f"insert_listing failed: {e}")
        return None


def compute_credits(carbon_tonnes: float, biodiversity_score: float) -> dict:
    """Deprecated shim — canonical implementation is credit_engine.credit_split."""
    from app.services.credit_engine import credit_split
    return credit_split(carbon_tonnes, biodiversity_score)


def get_land_registry(survey_number: str) -> Optional[dict]:
    sb = _client()
    if not sb or not survey_number or not isinstance(survey_number, str):
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
    if not sb or not farm_id:
        return None
    try:
        res = sb.table("farms").select("*").eq("id", farm_id.strip()).limit(1).execute()
        rows = res.data or []
        return rows[0] if rows else None
    except Exception as e:
        logger.warning(f"get_farm failed for {farm_id}: {e}")
        return None


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
    try:
        if owner_phones is not None and not owner_phones:
            return []
        q = sb.table("farms").select("*").ilike("status", status).order("created_at", desc=True)
        if owner_phones is not None:
            q = q.in_("owner_phone", owner_phones)
        res = q.execute()
        return res.data or []
    except Exception as e:
        logger.warning(f"list_farms_by_status failed for status={status}: {e}")
        return []


def list_profiles_by_fpo(fpo_id: str) -> list:
    sb = _client()
    if not sb or not fpo_id:
        return []
    try:
        res = sb.table("profiles").select("*").eq("fpo_id", fpo_id.strip()).execute()
        return res.data or []
    except Exception as e:
        logger.warning(f"list_profiles_by_fpo failed for fpo_id={fpo_id}: {e}")
        return []


def farm_geojsons_except(owner_phone: str) -> list:
    sb = _client()
    if not sb:
        return []
    try:
        res = sb.table("farms").select("id,geojson,owner_phone").neq("owner_phone", owner_phone or "").execute()
        return [row.get("geojson") for row in (res.data or []) if row.get("geojson")]
    except Exception as e:
        logger.warning(f"farm_geojsons_except failed for phone={owner_phone}: {e}")
        return []


def insert_farm_safe(farm: dict) -> Optional[dict]:
    """Insert a farm, dropping unknown columns (badge) if the DB rejects them."""
    saved = insert_farm(farm)
    if saved:
        return saved
    stripped = {k: v for k, v in farm.items() if k != "badge"}
    if stripped != farm:
        return insert_farm(stripped)
    return None
