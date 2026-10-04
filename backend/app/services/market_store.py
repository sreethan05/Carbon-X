"""In-memory marketplace store for offline/demo mode.

When the live Supabase DB is unreachable, purchases still need to *do*
something: this store seeds itself from the canonical sample listings and
serves as the mutable database for the buy -> escrow -> split -> retire
flow. State lives for the process lifetime (listings the API serves in
fallback mode come from here too, so purchases are visible everywhere).
"""
import threading

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


def update(listing_id: str, fields: dict):
    with _LOCK:
        _seed()
        row = _ROWS.get(listing_id)
        if not row:
            return None
        row.update(fields)
        return dict(row)


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
