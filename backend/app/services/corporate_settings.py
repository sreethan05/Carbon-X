"""Server-side corporate account preferences.

Buyer targets must survive device/browser changes, so they are persisted
server-side. Storage:

- live Supabase ``corporate_settings`` (see ``supabase/10_trust_controls.sql``)
- explicit, labelled in-process memory fallback when the DB or the migration is
  unavailable, so a buyer can still use the dashboard in demo mode.

Targets are preferences, not financial records: they are self-declared
decarbonization volumes used for the buyer's own progress view.
"""
from __future__ import annotations

import threading
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from app import supabase_db as db

DEFAULT_TARGET_OFFSETS_MT = 1000.0
MAX_TARGET_OFFSETS_MT = 1_000_000.0

_memory: dict[int, dict[str, Any]] = {}
_memory_lock = threading.Lock()
_table_unavailable: set[int] = set()


def _clean_target(value) -> Optional[float]:
    """Coerce to a positive float rounded to 2 dp; None when invalid."""
    try:
        number = float(Decimal(str(value)))
    except (InvalidOperation, ValueError, TypeError):
        return None
    if not (number > 0) or number > MAX_TARGET_OFFSETS_MT:
        return None
    return round(number, 2)


def _shape(row: dict, source: str) -> dict:
    return {
        "c_id": row.get("c_id"),
        "target_offsets_mt": round(float(row.get("target_offsets_mt") or DEFAULT_TARGET_OFFSETS_MT), 2),
        "updated_at": row.get("updated_at"),
        "storage": source,
    }


def _table(sb):
    try:
        return sb.table("corporate_settings")
    except Exception:
        return None


def get_settings(c_id: int) -> dict:
    """Return the buyer's stored preferences, with a clear fallback source."""
    if not c_id or int(c_id) <= 0:
        return {"found": False, "storage": "unauthorized", "target_offsets_mt": DEFAULT_TARGET_OFFSETS_MT}

    if db.is_ready() and int(c_id) not in _table_unavailable:
        sb = db._client()
        table = _table(sb) if sb else None
        if table is not None:
            try:
                rows = (
                    table.select("*")
                    .eq("c_id", int(c_id))
                    .limit(1)
                    .execute()
                    .data
                ) or []
                if rows:
                    return {"found": True, **_shape(rows[0], "live_db")}
                return {
                    "found": False,
                    "storage": "live_db",
                    "target_offsets_mt": DEFAULT_TARGET_OFFSETS_MT,
                }
            except Exception:
                # Migration not applied yet or transient DB error -> memory.
                _table_unavailable.add(int(c_id))

    with _memory_lock:
        row = _memory.get(int(c_id))
    if row:
        return {"found": True, **_shape(row, "memory")}
    return {
        "found": False,
        "storage": "memory",
        "target_offsets_mt": DEFAULT_TARGET_OFFSETS_MT,
    }


def set_settings(c_id: int, target_offsets_mt) -> dict:
    """Upsert the buyer's target. Returns ``{"success": bool, storage}``."""
    target = _clean_target(target_offsets_mt)
    if target is None:
        return {
            "success": False,
            "message": (
                f"target_offsets_mt must be a positive number up to "
                f"{MAX_TARGET_OFFSETS_MT:,.0f} MT CO2e"
            ),
        }
    if not c_id or int(c_id) <= 0:
        return {"success": False, "message": "A signed-in buyer session is required"}

    row = {"c_id": int(c_id), "target_offsets_mt": target, "updated_at": None}

    if db.is_ready() and int(c_id) not in _table_unavailable:
        sb = db._client()
        table = _table(sb) if sb else None
        if table is not None:
            try:
                table.upsert(
                    {"c_id": int(c_id), "target_offsets_mt": target},
                    on_conflict="c_id",
                ).execute()
                return {"success": True, **_shape(row, "live_db")}
            except Exception:
                _table_unavailable.add(int(c_id))

    with _memory_lock:
        _memory[int(c_id)] = row
    return {"success": True, **_shape(row, "memory")}
