"""One public-access policy for passports, certificates, evidence and ledgers.

Rules (mirrored in docs/PUBLIC_ACCESS_POLICY.md):

Public, unauthenticated
  - certificate id, crop, credit quantity, issue/retirement dates, status,
    district/state, ledger event type/sequence/ts/hash, formula version,
    validation status and uncertainty.
  - retired certificates are public; held-in-escrow certificates are not.

Owner / buyer of record / FPO / staff
  - their own full record: farmer name/phone, buyer name, value, split,
    village-level location, evidence metadata, lifecycle timeline.

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
    "escrow_ref",
    "sale_seq",
    "credits",
    "credits_retired",
    "model",
    "batch_hash",
    "formula_version",
    "scope",
    "decision",
    "refund_ref",
    "restored_credits",
    "balance_after",
    "farm_id",
}

PUBLIC_EVENT_KEYS = ("seq", "type", "ts", "hash", "prev_hash")


def is_staff(caller: Optional[dict]) -> bool:
    return str((caller or {}).get("role") or "").lower() in ("admin", "fpo", "verifier")


def is_owner(caller: Optional[dict], farmer_phone: Optional[str]) -> bool:
    phone = (caller or {}).get("phone")
    return bool(phone and farmer_phone and str(phone) == str(farmer_phone))


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
    if is_staff(caller) or is_owner(caller, farm.get("owner_phone")):
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
