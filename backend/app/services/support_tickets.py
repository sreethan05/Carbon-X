"""Farmer support / grievance tickets.

Farmers must be able to report wrong farm boundaries, ownership mismatches,
disputed carbon estimates, missing payouts and privacy concerns — and see the
ticket move from Open → In Review → Resolved/Rejected with a written resolution.

Storage:

- live Supabase ``support_tickets`` (see ``supabase/10_trust_controls.sql``)
- labelled in-process memory fallback when the DB or migration is unavailable
  (demo mode keeps the workflow testable end to end).

Tickets are *not* financial instructions. Money is never moved because of a
ticket; payout disputes are recorded here and resolved through refunds or
ledger events by staff using the existing lifecycle endpoints.
"""
from __future__ import annotations

import threading
import uuid
from typing import Iterable, Optional

from app import supabase_db as db

CATEGORIES = ("boundary", "ownership", "estimate", "payout", "privacy", "other")
STATUSES = ("Open", "In Review", "Resolved", "Rejected")

TITLE_MAX = 140
DETAIL_MAX = 4000
NOTES_MAX = 4000

_memory: list[dict] = []
_lock = threading.Lock()
_table_state: dict[str, object] = {}


def reset_memory() -> None:
    with _lock:
        _memory.clear()


def _clean_text(value, max_len: int) -> str:
    return " ".join(str(value or "").split())[:max_len]


def _shape(row: dict) -> dict:
    return {
        "id": row.get("id"),
        "reporter_phone": row.get("reporter_phone"),
        "farm_id": row.get("farm_id") or None,
        "category": row.get("category"),
        "status": str(row.get("status") or "Open"),
        "title": row.get("title"),
        "detail": row.get("detail"),
        "staff_notes": row.get("staff_notes") or None,
        "resolution": row.get("resolution") or None,
        "handled_by": row.get("handled_by") or None,
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
        "resolved_at": row.get("resolved_at") or None,
    }


def _reporter_view(row: dict) -> dict:
    view = _shape(row)
    # Staff workflow fields stay internal until a resolution is written.
    return view


def _get_table():
    if not db.is_ready() or _table_state.get("unavailable"):
        return None
    sb = db._client()
    if not sb:
        return None
    try:
        return sb.table("support_tickets")
    except Exception:
        _table_state["unavailable"] = True
        return None


def create(
    reporter_phone: str,
    category: str,
    title: str,
    detail: str,
    farm_id: Optional[str] = None,
) -> dict:
    """Create a ticket. Returns ``{"success", "ticket", "storage"}``."""
    phone = _clean_text(reporter_phone, 20)
    if not phone:
        return {"success": False, "message": "A signed-in account is required to file a request"}
    category = str(category or "").strip().lower()
    if category not in CATEGORIES:
        return {
            "success": False,
            "message": f"category must be one of: {', '.join(CATEGORIES)}",
        }
    title = _clean_text(title, TITLE_MAX)
    detail = _clean_text(detail, DETAIL_MAX)
    if len(title) < 4:
        return {"success": False, "message": "Give the request a short title (min 4 characters)"}
    if len(detail) < 10:
        return {"success": False, "message": "Describe the issue in at least 10 characters so staff can act on it"}
    farm_id = _clean_text(farm_id, 120) or None

    ticket = {
        "id": str(uuid.uuid4()),
        "reporter_phone": phone,
        "farm_id": farm_id,
        "category": category,
        "status": "Open",
        "title": title,
        "detail": detail,
        "staff_notes": None,
        "resolution": None,
        "handled_by": None,
        "created_at": None,
        "updated_at": None,
        "resolved_at": None,
    }

    table = _get_table()
    if table is not None:
        try:
            res = table.insert({
                "reporter_phone": phone,
                "farm_id": farm_id,
                "category": category,
                "status": "Open",
                "title": title,
                "detail": detail,
            }).execute()
            rows = getattr(res, "data", None) or []
            if rows:
                return {"success": True, "storage": "live_db", "ticket": _shape(rows[0])}
        except Exception:
            _table_state["unavailable"] = True

    with _lock:
        _memory.insert(0, ticket)
    return {"success": True, "storage": "memory", "ticket": ticket}


def list_for(reporter_phone: str, limit: int = 50) -> dict:
    """Tickets filed by the caller (chronological × newest-first)."""
    phone = _clean_text(reporter_phone, 20)
    if not phone:
        return {"success": False, "message": "A signed-in account is required"}

    table = _get_table()
    if table is not None:
        try:
            rows = (
                table.select("*")
                .eq("reporter_phone", phone)
                .order("created_at", desc=True)
                .limit(max(1, min(int(limit), 200)))
                .execute()
                .data
            ) or []
            return {"success": True, "storage": "live_db", "tickets": [_reporter_view(r) for r in rows]}
        except Exception:
            _table_state["unavailable"] = True

    with _lock:
        rows = [t for t in _memory if t.get("reporter_phone") == phone]
        rows.sort(key=lambda t: t.get("created_at") or "", reverse=True)
    return {"success": True, "storage": "memory", "tickets": [_reporter_view(r) for r in rows[: max(1, min(int(limit), 200))]]}


def list_all(status: str = "", limit: int = 100) -> dict:
    """Staff view: all tickets, optionally filtered by exact status."""
    status = str(status or "").strip()
    if status and status not in STATUSES:
        return {"success": False, "message": f"status must be one of: {', '.join(STATUSES)}"}

    table = _get_table()
    if table is not None:
        try:
            q = table.select("*").order("created_at", desc=True).limit(max(1, min(int(limit), 200)))
            if status:
                q = q.eq("status", status)
            rows = q.execute().data or []
            return {"success": True, "storage": "live_db", "tickets": [_shape(r) for r in rows]}
        except Exception:
            _table_state["unavailable"] = True

    with _lock:
        rows = [t for t in _memory if (not status or t.get("status") == status)]
        rows.sort(key=lambda t: t.get("created_at") or "", reverse=True)
    return {"success": True, "storage": "memory", "tickets": [_shape(r) for r in rows[: max(1, min(int(limit), 200))]]}


def get_ticket(ticket_id: str) -> Optional[dict]:
    """Fetch one ticket for authorization before a staff update."""
    ticket_id = _clean_text(ticket_id, 64)
    table = _get_table()
    if table is not None:
        try:
            rows = table.select("*").eq("id", ticket_id).limit(1).execute().data or []
            return _shape(rows[0]) if rows else None
        except Exception:
            _table_state["unavailable"] = True
    with _lock:
        row = next((t for t in _memory if t.get("id") == ticket_id), None)
        return _shape(row) if row else None


def update_ticket(
    ticket_id: str,
    *,
    status: str,
    staff_notes: Optional[str] = None,
    resolution: Optional[str] = None,
    handled_by: str = "",
) -> dict:
    """Staff workflow update on one ticket (authoritative; never deletes)."""
    ticket_id = _clean_text(ticket_id, 64)
    status = str(status or "").strip()
    if status not in STATUSES:
        return {"success": False, "message": f"status must be one of: {', '.join(STATUSES)}"}
    staff_notes = _clean_text(staff_notes, NOTES_MAX) or None
    resolution = _clean_text(resolution, NOTES_MAX) or None
    if status in ("Resolved", "Rejected") and not resolution:
        return {"success": False, "message": f"A written resolution is required to mark a ticket {status}"}

    updated_at = _now_iso()
    resolved_at = updated_at if status in ("Resolved", "Rejected") else None

    table = _get_table()
    if table is not None:
        try:
            res = (
                table.update({
                    "status": status,
                    "staff_notes": staff_notes,
                    "resolution": resolution,
                    "handled_by": _clean_text(handled_by, 120),
                    "updated_at": updated_at,
                    **({"resolved_at": resolved_at} if resolved_at else {}),
                })
                .eq("id", ticket_id)
                .execute()
            )
            rows = getattr(res, "data", None) or []
            if rows:
                return {"success": True, "storage": "live_db", "ticket": _shape(rows[0])}
        except Exception:
            _table_state["unavailable"] = True

    with _lock:
        row = next((t for t in _memory if t.get("id") == ticket_id), None)
        if row is None:
            return {"success": False, "message": "Ticket not found", "not_found": True}
        row.update({
            "status": status,
            "staff_notes": staff_notes,
            "resolution": resolution,
            "handled_by": _clean_text(handled_by, 120),
            "updated_at": updated_at,
            "resolved_at": resolved_at,
        })
        return {"success": True, "storage": "memory", "ticket": _shape(row)}


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def reporter_summary(tickets: Iterable[dict]) -> dict:
    tickets = list(tickets or [])
    return {
        "total": len(tickets),
        "open": sum(1 for t in tickets if str(t.get("status")) == "Open"),
        "in_review": sum(1 for t in tickets if str(t.get("status")) == "In Review"),
        "resolved": sum(1 for t in tickets if str(t.get("status")) == "Resolved"),
        "rejected": sum(1 for t in tickets if str(t.get("status")) == "Rejected"),
    }
