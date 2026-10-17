"""In-memory marketplace store for offline/demo mode.

When the live Supabase DB is unreachable, purchases still need to *do*
something: this store seeds itself from the canonical sample listings and
serves as the mutable database for the buy -> escrow -> split -> retire
flow. State lives for the process lifetime (listings the API serves in
fallback mode come from here too, so purchases are visible everywhere).
"""
import threading
import uuid
from typing import Optional, Tuple

from app import sample_data

_LOCK = threading.RLock()
_ROWS: dict = {}


def _seed():
    if _ROWS:
        return
    for row in sample_data.FALLBACK_LISTINGS:
        _ROWS[row["id"]] = dict(row)


def reset():
    with _LOCK:
        _ROWS.clear()
        _seed()


def all_rows() -> list:
    with _LOCK:
        _seed()
        return [dict(r) for r in _ROWS.values()]


def get(listing_id: str):
    with _LOCK:
        _seed()
        row = _ROWS.get(listing_id)
        return dict(row) if row else None


def insert(listing: dict) -> dict:
    with _LOCK:
        _seed()
        row = dict(listing)
        if not row.get("id"):
            row["id"] = str(uuid.uuid4())
        _ROWS[row["id"]] = row
        return dict(row)


def update(listing_id: str, fields: dict):
    with _LOCK:
        _seed()
        row = _ROWS.get(listing_id)
        if not row:
            return None
        row.update(fields)
        return dict(row)


def update_cas(listing_id: str, fields: dict, expected_credits: float) -> bool:
    """Compare-and-swap update for purchases.

    Applies ``fields`` only if the listing is still active and still holds
    ``expected_credits`` — the same guard ``/marketplace/buy`` enforces on the
    live DB, so a concurrent purchase can never double-spend a listing.
    """
    with _LOCK:
        _seed()
        row = _ROWS.get(listing_id)
        if not row:
            return False
        if str(row.get("status") or "Active").lower() not in ("active", ""):
            return False
        if abs(float(row.get("total_credits") or 0) - float(expected_credits)) > 1e-9:
            return False
        row.update(fields)
        return True


def place_bid_cas(listing_id: str, bid_amount: float, expected_bid: float) -> Tuple[bool, str, Optional[dict]]:
    """Compare-and-swap update for bids in offline/demo mode."""
    with _LOCK:
        _seed()
        row = _ROWS.get(listing_id)
        if not row:
            return False, "Listing not found", None
        if str(row.get("status") or "Active").lower() not in ("active", ""):
            return False, f"Bidding closed (listing status: {row.get('status')})", None
        curr = float(row.get("current_bid") or 0)
        if abs(curr - expected_bid) > 1e-9:
            return False, "A higher or concurrent bid was placed — refresh and try again", None
        if bid_amount <= 0:
            return False, "Bid amount must be greater than zero", None
        if curr > 0 and bid_amount <= curr:
            return False, f"Bid must exceed current standing bid of ₹{curr:,.0f}", None
        row["current_bid"] = round(bid_amount, 2)
        row["bids_count"] = int(row.get("bids_count") or 0) + 1
        return True, "Bid placed successfully", dict(row)


def fpo_for_phone(phone: str) -> str:
    """FPO linked to a sample farmer (drives the conditional 4-way split)."""
    farmer = sample_data.FARMERS.get(phone) or {}
    return farmer.get("fpo") or ""


def farmer_farm_id(phone: str):
    with _LOCK:
        _seed()
        for row in _ROWS.values():
            if row.get("farmer_phone") == phone:
                return row.get("farm_id")
    return None

