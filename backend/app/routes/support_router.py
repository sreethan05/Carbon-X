"""Farmer support / grievance routes.

Farmers file bound-check, ownership, estimate, payout and privacy issues with a
title + description (optionally tied to one farm). Signed-in callers see only
their own tickets; FPO/verifier/admin staff see the queue and write the
resolution. A ticket never moves money or edits credits/ledger directly.
"""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from app.security import get_current_user, require_role
from app import supabase_db as db
from app.services import support_tickets as tickets

router = APIRouter(prefix="/support", tags=["support", "farmers"])


# ─── Models ───

class SupportTicketCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: Literal["boundary", "ownership", "estimate", "payout", "privacy", "other"]
    title: str = Field(min_length=4, max_length=140)
    detail: str = Field(min_length=10, max_length=4000)
    farm_id: Optional[str] = Field(default=None, max_length=120)


class SupportTicketUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["Open", "In Review", "Resolved", "Rejected"]
    staff_notes: Optional[str] = Field(default=None, max_length=4000)
    resolution: Optional[str] = Field(default=None, max_length=4000)


def _phone(user: dict) -> str:
    phone = str((user or {}).get("phone") or "")
    if not phone:
        raise HTTPException(status_code=401, detail="A signed-in account is required")
    return phone


def _fpo_scope(user: dict) -> tuple[set[str], set[str]]:
    """Resolve one request's member/farm scope for an FPO officer."""
    phone = str((user or {}).get("phone") or "")
    profile = db.get_profile(phone) if db.is_ready() and phone else None
    fpo_id = (profile or {}).get("fpo_id")
    if not fpo_id:
        return set(), set()
    try:
        sb = db._client()
        members = (sb.table("profiles").select("phone").eq("fpo_id", fpo_id).execute().data) or []
        member_phones = {str(row.get("phone")) for row in members if row.get("phone")}
        farms = (sb.table("farms").select("id,owner_phone").eq("fpo_id", fpo_id).execute().data) or []
        # Include legacy farm rows linked through profiles.fpo_id.
        if member_phones:
            farms.extend(
                (sb.table("farms").select("id,owner_phone").in_("owner_phone", list(member_phones)).execute().data) or []
            )
        return (
            member_phones,
            {str(row.get("id")) for row in farms if row.get("id")},
        )
    except Exception:
        return set(), set()


def _fpo_can_access_ticket(ticket: dict, scope: tuple[set[str], set[str]]) -> bool:
    """FPO officers can only handle their linked farm/member grievances."""
    member_phones, farm_ids = scope
    farm_id = str(ticket.get("farm_id") or "")
    reporter_phone = str(ticket.get("reporter_phone") or "")
    return bool((farm_id and farm_id in farm_ids) or (reporter_phone and reporter_phone in member_phones))


# ─── Endpoints ───

@router.post("/tickets")
def create_ticket(data: SupportTicketCreate, current_user: dict = Depends(get_current_user)):
    """File a support request. The reporter sees it instantly with status Open."""
    reporter_phone = _phone(current_user)
    if data.farm_id:
        farm = db.get_farm(data.farm_id)
        if not farm:
            raise HTTPException(status_code=404, detail="Farm not found")
        if str(farm.get("owner_phone") or "") != reporter_phone:
            raise HTTPException(status_code=403, detail="You can only attach a request to your own farm")
    result = tickets.create(
        reporter_phone=reporter_phone,
        category=data.category,
        title=data.title,
        detail=data.detail,
        farm_id=data.farm_id,
    )
    if not result.get("success"):
        raise HTTPException(status_code=422, detail=result.get("message") or "Invalid request")
    return result


@router.get("/tickets")
def my_tickets(
    limit: int = Query(default=50, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
):
    """The caller's own tickets with live status; anonymous callers get 401."""
    result = tickets.list_for(_phone(current_user), limit=limit)
    return {
        **result,
        "summary": tickets.reporter_summary(result.get("tickets") or []),
        "dispute_note": (
            "For money already settled, payouts correctness is enforced by the "
            "ledger; a payout ticket is handled by finance with a refund or a "
            "ledger correction — never by editing history."
        )
        if any(str(t.get("category")) == "payout" for t in result.get("tickets") or [])
        else None,
    }


@router.get("/staff/queue")
def staff_queue(
    status: str = Query(default=""),
    limit: int = Query(default=100, ge=1, le=200),
    current_user: dict = Depends(require_role("fpo", "verifier", "admin")),
):
    """All tickets with the requester phone visible to staff for contact-out."""
    result = tickets.list_all(status=status, limit=limit)
    if str(current_user.get("role") or "").lower() == "fpo":
        scope = _fpo_scope(current_user)
        result["tickets"] = [
            ticket for ticket in result.get("tickets", [])
            if _fpo_can_access_ticket(ticket, scope)
        ]
    return result


@router.post("/tickets/{ticket_id}/update")
def staff_update(
    ticket_id: str,
    data: SupportTicketUpdate,
    current_user: dict = Depends(require_role("fpo", "verifier", "admin")),
):
    """Move a ticket through the workflow; Resolved/Rejected need a resolution."""
    if str(current_user.get("role") or "").lower() == "fpo":
        ticket = tickets.get_ticket(ticket_id)
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found")
        if not _fpo_can_access_ticket(ticket, _fpo_scope(current_user)):
            raise HTTPException(status_code=403, detail="Ticket is outside your FPO scope")
    result = tickets.update_ticket(
        ticket_id,
        status=data.status,
        staff_notes=data.staff_notes,
        resolution=data.resolution,
        handled_by=f"{current_user.get('role') or 'staff'}:{current_user.get('phone') or current_user.get('name') or current_user.get('c_id')}",
    )
    if not result.get("success"):
        raise HTTPException(
            status_code=404 if result.get("not_found") else 422,
            detail=result.get("message") or "Update failed",
        )
    return result
