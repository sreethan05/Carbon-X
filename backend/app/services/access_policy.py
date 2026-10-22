"""One public-access policy for passports, certificates, evidence and ledgers.

Rules (mirrored in docs/PUBLIC_ACCESS.md):

Public, unauthenticated
  - certificate id, crop, credit quantity, issue/retirement dates, status,
    district/state, ledger event type/sequence/ts/hash, formula version,
    validation status and uncertainty.
  - retired certificates are public; held-in-escrow certificates are not.

Owner / buyer of record
  - their own full record: farmer name/phone, buyer name, value, split,
    village-level location, evidence metadata, lifecycle timeline.

FPO (scoped, never global)
  - full records only for farms/certificates that belong to their own FPO
    (farm.fpo_id == the caller profile's fpo_id).  An FPO account is NOT
    staff: a different FPO is treated as the public.

Admin / verifier (global staff)
  - full records for every farm and certificate.

Never public
  - phone numbers, full farmer names, buyer identities, rupee values,
    payout splits, exact coordinates/GeoJSON, evidence bytes, dispute free
    text, KYC/Aadhaar data, and OTPs.

The immutable ledger may contain historical free text.  Redaction happens at
the boundary; hashes are never rewritten.
"""
from __future__ import annotations

from typing import Iterable, Optional

# Ledger payload keys that are safe for an unauthenticated reader.  Everything
# else (money, identities, free-text reasons) is dropped.
PUBLIC_LEDGER_KEYS = {
    "certificate_id",
    "listing_id",
    "sale_seq",
    "credits",
    "credits_retired",
    "model",
    "batch_hash",
    "formula_version",
    "scope",
    "decision",
    "restored_credits",
    "balance_after",
}

PUBLIC_EVENT_KEYS = ("seq", "type", "ts", "hash", "prev_hash")

# Global staff: sees every farm/certificate regardless of scope.
GLOBAL_STAFF_ROLES = ("admin", "verifier")
FPO_ROLE = "fpo"


def is_staff(caller: Optional[dict]) -> bool:
    """Whether the caller has global staff access.

    FPO officers are intentionally excluded: their access is scoped to farms
    linked to their own FPO and must be checked with ``can_access_farm``.
    """
    return str((caller or {}).get("role") or "").lower() in ("admin", "verifier")


def is_owner(caller: Optional[dict], farmer_phone: Optional[str]) -> bool:
    phone = (caller or {}).get("phone")
    return bool(phone and farmer_phone and str(phone) == str(farmer_phone))


def is_fpo(caller: Optional[dict]) -> bool:
    return str((caller or {}).get("role") or "").lower() == FPO_ROLE


def fpo_scope_matches(caller_fpo_id: Optional[str], farm: Optional[dict]) -> bool:
    """Pure FPO scope check: the caller's fpo_id must equal the farm's fpo_id."""
    if not caller_fpo_id or not farm:
        return False
    farm_fpo_id = str(farm.get("fpo_id") or "").strip()
    return bool(farm_fpo_id) and farm_fpo_id == str(caller_fpo_id).strip()


def caller_fpo_id(caller: Optional[dict]) -> Optional[str]:
    """Resolve an FPO officer's own fpo_id.

    The embedded token value wins; otherwise the officer's profile row is
    looked up.  Fail-closed: returns None for non-FPO callers, callers with
    no fpo_id anywhere, or when the database is unavailable — an FPO role is
    never a global-staff fallback.
    """
    caller = caller or {}
    if str(caller.get("role") or "").lower() != FPO_ROLE:
        return None
    embedded = caller.get("fpo_id")
    if embedded and str(embedded).strip() not in ("", "None"):
        return str(embedded).strip()
    try:
        from app import supabase_db as db
        if not db.is_ready():
            return None
        profile = db.get_profile(str(caller.get("phone") or "")) or {}
        value = profile.get("fpo_id")
        return str(value).strip() if value else None
    except Exception:
        return None


def is_fpo_for_farm(caller: Optional[dict], farm: Optional[dict]) -> bool:
    """Check FPO scope against the officer's resolved fpo_id; fail closed."""
    fpo_id = caller_fpo_id(caller)
    if not fpo_id or not farm:
        return False
    farm_fpo = str(farm.get("fpo_id") or "").strip()
    if farm_fpo:
        return fpo_id == farm_fpo
    # Older farm rows may rely on the owner's profile link instead of having
    # farms.fpo_id populated. Preserve that relationship without widening
    # access to other FPOs.
    try:
        from app import supabase_db as db
        owner = db.get_profile(str(farm.get("owner_phone") or "")) or {}
        return str(owner.get("fpo_id") or "").strip() == fpo_id
    except Exception:
        return False


def can_access_farm(caller: Optional[dict], farm: Optional[dict]) -> bool:
    """Full farm-level access for global staff, owner, or scoped FPO officer."""
    return bool(
        is_staff(caller)
        or (farm and is_owner(caller, farm.get("owner_phone")))
        or is_fpo_for_farm(caller, farm)
    )


def ledger_event_public(event: dict) -> dict:
    out = {k: event.get(k) for k in PUBLIC_EVENT_KEYS if k in event}
    payload = event.get("payload") or {}
    out["payload"] = {
        k: payload.get(k) for k in PUBLIC_LEDGER_KEYS
        if payload.get(k) is not None
    }
    return out


def ledger_event_for(event: dict, full_access: bool) -> dict:
    event = {k: v for k, v in (event or {}).items() if not str(k).startswith("_")}
    if full_access:
        return event
    return ledger_event_public(event)


def ledger_events_for(events: Iterable[dict], full_access: bool) -> list[dict]:
    return [ledger_event_for(e, full_access) for e in events or []]


def passport_identity(farm: dict, owner: Optional[dict], caller: Optional[dict]) -> dict:
    """Owner/staff see the farmer; the public sees a coarse, non-identifying label."""
    if can_access_farm(caller, farm):
        return {
            "owner_name": (owner or {}).get("name") or "Registered Farmer",
            "phone": farm.get("owner_phone"),
            "district": (owner or {}).get("district"),
            "village": (owner or {}).get("village"),
            "location_precision": "village",
        }
    return {
        "owner_name": "Verified smallholder",
        "phone": None,
        "district": (owner or {}).get("district"),
        "village": None,
        "location_precision": "district",
    }


def public_location(location: Optional[str]) -> Optional[str]:
    """Drop village, keep district/state for unauthenticated readers."""
    if not location:
        return location
    parts = [p.strip() for p in str(location).split(",") if p.strip()]
    if len(parts) >= 3:
        return ", ".join(parts[-2:])
    if len(parts) == 2:
        return parts[-1]
    return "Telangana, India"


def evidence_public(flags: dict) -> dict:
    """Evidence presence, never bytes, GPS points or file names."""
    return {
        "practice_photo": bool((flags or {}).get("practice_photo")),
        "geotag_inside_boundary": bool((flags or {}).get("geotag_inside_boundary")),
        "photo_count": int((flags or {}).get("photo_count") or 0),
        "geotag_count": int((flags or {}).get("geotag_count") or 0),
        "last_photo_at": (flags or {}).get("last_photo_at"),
        "demo_mode": bool((flags or {}).get("demo_mode")),
    }
