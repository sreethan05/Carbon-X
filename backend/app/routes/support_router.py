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


# ─── Endpoints ───

@router.post("/tickets")
def create_ticket(data: SupportTicketCreate, current_user: dict = Depends(get_current_user)):
    """File a support request. The reporter sees it instantly with status Open."""
    result = tickets.create(
        reporter_phone=str(current_user.get("phone") or ""),
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
    return result


@router.post("/tickets/{ticket_id}/update")
def staff_update(
    ticket_id: str,
    data: SupportTicketUpdate,
    current_user: dict = Depends(require_role("fpo", "verifier", "admin")),
):
    """Move a ticket through the workflow; Resolved/Rejected need a resolution."""
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
