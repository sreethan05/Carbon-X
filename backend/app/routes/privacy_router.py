"""Privacy routes: consent, export, correction, erasure and staff review."""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.security import get_current_user, require_role, revoke_token
from app import supabase_db as db
from app.services import evidence_service, ledger, market_store, privacy

router = APIRouter(prefix="/privacy", tags=["privacy"])
ops_router = APIRouter(prefix="/ops/privacy", tags=["ops", "privacy"])


# ─── Helpers ───

def _phone(user: dict) -> str:
    phone = privacy.normalize_phone(user.get("phone") or "")
    if not phone:
        raise HTTPException(status_code=401, detail="A farmer phone session is required")
    return phone


def _demo_profile(phone: str) -> dict:
    from app import sample_data
    info = sample_data.FARMERS.get(phone) or {}
    return {
        "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"carbonx:demo-profile:{phone}")),
        "phone": phone,
        "name": info.get("name") or "Pilot Farmer",
        "role": "farmer",
        "state": info.get("state") or "Telangana",
        "district": info.get("district") or "",
        "village": info.get("village") or "",
        "upi": info.get("upi") or "",
        "aadhaar_last4": "",
        "preferred_language": "en",
        "created_at": "2026-09-10T12:00:00+00:00",
        "demo_mode": True,
    }


def _profile_for(phone: str) -> dict:
    if db.is_ready():
        profile = db.get_profile(phone)
        if not profile:
            raise HTTPException(status_code=401, detail="Account no longer exists")
        return profile
    return _demo_profile(phone)


def _farms_for(phone: str) -> list[dict]:
    if db.is_ready():
        return db.get_farms(phone) or []
    from app import sample_data
    rows = []
    for farm in sample_data.FARMS:
        if farm.get("phone") != phone:
            continue
        rows.append({
            "id": sample_data._fallback_farm_id(farm["key"]),
            "name": farm.get("name"),
            "owner_phone": phone,
            "crop_type": farm.get("crop"),
            "area_hectares": farm.get("area"),
            "ndvi": farm.get("ndvi"),
            "evi": farm.get("evi"),
            "biomass_score": farm.get("score"),
            "status": "verified",
            "demo_mode": True,
        })
    return rows


def _listings_for(phone: str) -> list[dict]:
    if db.is_ready():
        return (db.get_listings_filtered(status="all", farmer_phone=phone, limit=200) or {}).get(
            "listings", []
        ) or []
    rows = [
        r for r in market_store.all_rows()
        if str(r.get("farmer_phone") or "") == phone
    ]
    return rows


def _masked_kyc(phone: str) -> Optional[dict]:
    if not db.is_ready():
        return None
    row = db.get_kyc_status(phone)
    if not row:
        return None
    safe = {
        k: row.get(k) for k in (
            "id", "document_name", "status", "checks", "created_at",
            "document_deleted_at",
        )
    }
    extracted = dict(row.get("extracted_fields") or {})
    for key in list(extracted):
        if "aadhaar" in key.lower():
            raw = str(extracted.get(key) or "")
            digits = "".join(ch for ch in raw if ch.isdigit())
            extracted[key] = f"XXXX XXXX {digits[-4:]}" if len(digits) >= 4 else "redacted"
    safe["extracted_fields"] = extracted
    # Hashes are retained in the export (the farmer can check them) but the
    # raw document is never stored by CarbonX.
    safe["document_sha256"] = row.get("document_sha256")
    return safe


def _redact_ledger_event(event: dict) -> dict:
    out = {k: v for k, v in event.items() if not str(k).startswith("_")}
    payload = dict(out.get("payload") or {})
    if "buyer" in payload:
        payload["buyer"] = privacy.redact_third_party(payload.get("buyer"))
    if "buyer_name" in payload:
        payload["buyer_name"] = privacy.redact_third_party(payload.get("buyer_name"))
    out["payload"] = payload
    return out


def _build_archive(phone: str) -> dict:
    profile = _profile_for(phone)
    farms = _farms_for(phone)
    listings = _listings_for(phone)
    evidence = {}
    chains = {}
    for farm in farms:
        farm_id = str(farm.get("id") or "")
        if not farm_id:
            continue
        evidence[farm_id] = evidence_service.list_evidence(farm_id)
        chains[farm_id] = {
            "verified": ledger.verify_chain(farm_id) if hasattr(ledger, "verify_chain") else None,
            "events": [_redact_ledger_event(e) for e in ledger.get_chain(farm_id)],
        }
    archive = {
        "schema_version": "carbonx-privacy-export-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "policy_version": privacy.POLICY_VERSION,
        "controller": privacy.DATA_CONTROLLER,
        "data_subject": {"phone": phone},
        "account": profile,
        "farms": farms,
        "marketplace_listings": listings,
        "kyc": _masked_kyc(phone),
        "evidence": evidence,
        "ledger": chains,
        "consent": privacy.list_consents(phone),
        "privacy_requests": privacy.list_requests(phone),
        "retention": privacy.RETENTION,
        "notes": [
            "This archive contains your operational CarbonX data.",
            "Third-party buyer names are redacted.",
            "Aadhaar is represented by the stored last 4 digits only; CarbonX never stores the card image.",
            "The hash ledger is immutable: historical payloads are exported as recorded.",
        ],
    }
    privacy._save_request(
        phone, "export", "completed",
        {"schema_version": archive["schema_version"]},
        resolution_note="JSON archive generated",
    )
    return archive


# ─── Models ───

class ConsentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    purposes: dict[str, bool] = Field(min_length=1)
    language: str = "en"
    method: str = "app_checkbox"
    policy_version: str = privacy.POLICY_VERSION

    @field_validator("purposes")
    @classmethod
    def _known_purposes(cls, value):
        unknown = set(value) - set(privacy.PURPOSES)
        if unknown:
            raise ValueError(f"Unknown consent purpose(s): {', '.join(sorted(unknown))}")
        if value.get("platform_service") is False:
            raise ValueError(
                "platform_service consent cannot be withdrawn while the account is active; "
                "use POST /privacy/delete to close the account."
            )
        return value


class DeleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm: str
    reason: Optional[str] = None

    @field_validator("confirm")
    @classmethod
    def _confirm(cls, value):
        if str(value).strip().upper() != "DELETE":
            raise ValueError('Type "DELETE" to confirm account erasure')
        return value


class CorrectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: Literal["name", "state", "district", "village", "preferred_language", "upi"]
    current_value: Optional[str] = ""
    requested_value: str
    reason: str = ""
    evidence_url: str = ""


class CorrectionDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["applied", "rejected"]
    note: str = ""


# ─── Public policy ───

@router.get("/policy")
def get_policy():
    return {"success": True, **privacy.policy()}


# ─── Consent ───

@router.get("/consent")
def get_consent(current_user: dict = Depends(get_current_user)):
    phone = _phone(current_user)
    return {
        "success": True,
        "phone": phone,
        "current": privacy.current_consents(phone),
        "history": privacy.list_consents(phone),
        "policy_version": privacy.POLICY_VERSION,
    }


@router.post("/consent")
def set_consent(
    data: ConsentUpdate,
    current_user: dict = Depends(get_current_user),
    authorization: Optional[str] = Header(None),
):
    phone = _phone(current_user)
    recorded = []
    for purpose, granted in data.purposes.items():
        recorded.append(privacy.record_consent(
            phone, purpose, granted,
            policy_version=data.policy_version,
            language=data.language,
            method=data.method,
            evidence={"source": "api", "user_agent_family": "web"},
        ))
    return {
        "success": True,
        "recorded": recorded,
        "current": privacy.current_consents(phone),
        "policy_version": privacy.POLICY_VERSION,
    }


@router.post("/consent/withdraw/{purpose}")
def withdraw_consent(
    purpose: str,
    current_user: dict = Depends(get_current_user),
):
    phone = _phone(current_user)
    if purpose not in privacy.PURPOSES:
        raise HTTPException(status_code=404, detail="Unknown consent purpose")
    if privacy.PURPOSES[purpose].get("required"):
        raise HTTPException(
            status_code=409,
            detail="Required service consent cannot be withdrawn; use POST /privacy/delete to close the account.",
        )
    row = privacy.record_consent(phone, purpose, False, method="withdraw")
    return {"success": True, "withdrawn": row, "current": privacy.current_consents(phone)}


# ─── Export ───

@router.get("/export")
def export_my_data(current_user: dict = Depends(get_current_user)):
    phone = _phone(current_user)
    archive = _build_archive(phone)
    return {"success": True, "archive": archive}


@router.get("/export/download")
def download_my_data(current_user: dict = Depends(get_current_user)):
    phone = _phone(current_user)
    archive = _build_archive(phone)
    payload = json.dumps(archive, indent=2, default=str).encode("utf-8")
    filename = f"carbonx-data-export-{datetime.now(timezone.utc).strftime('%Y%m%d')}.json"
    return Response(
        content=payload,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Content-SHA256": hashlib.sha256(payload).hexdigest(),
        },
    )


# ─── Erasure ───

@router.post("/delete")
def delete_my_account(
    data: DeleteRequest,
    current_user: dict = Depends(get_current_user),
    authorization: Optional[str] = Header(None),
):
    phone = _phone(current_user)
    profile = _profile_for(phone)
    farms = _farms_for(phone)
    listings = _listings_for(phone)
    result = privacy.anonymize(phone, profile, farms, listings)
    if result.get("success"):
        # Kill the current session immediately; the profile is gone, so all
        # other tokens for this phone fail the live-profile check too.
        if authorization and authorization.lower().startswith("bearer "):
            revoke_token(authorization.split(None, 1)[1], ttl_seconds=90000)
        return {"success": True, **result, "reason": data.reason}
    if result.get("code") == "DELETION_BLOCKED":
        return {"success": False, **result}
    raise HTTPException(status_code=500, detail=result.get("message") or "Erasure failed")


@router.get("/deletion-check")
def deletion_check(current_user: dict = Depends(get_current_user)):
    phone = _phone(current_user)
    listings = _listings_for(phone)
    blockers = privacy.deletion_blockers(phone, listings)
    return {
        "success": True,
        "can_delete": not blockers,
        "blockers": blockers,
        "retention": privacy.RETENTION,
    }


# ─── Correction ───

@router.post("/corrections")
def create_correction(
    data: CorrectionRequest,
    current_user: dict = Depends(get_current_user),
):
    phone = _phone(current_user)
    try:
        row = privacy.submit_correction(
            phone, data.field, data.current_value, data.requested_value,
            data.reason, data.evidence_url,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"success": True, "request": row}


@router.get("/requests")
def my_requests(
    request_type: Optional[Literal["export", "deletion", "correction"]] = None,
    current_user: dict = Depends(get_current_user),
):
    phone = _phone(current_user)
    return {
        "success": True,
        "requests": privacy.list_requests(phone, request_type),
    }


# ─── Staff review ───

@ops_router.get("/requests")
def staff_list_requests(
    status: Optional[Literal["received", "blocked", "in_review", "completed", "rejected"]] = None,
    request_type: Optional[Literal["export", "deletion", "correction"]] = None,
    limit: int = Query(100, ge=1, le=500),
    current_user: dict = Depends(require_role("admin", "verifier")),
):
    sb = db._client()
    rows = []
    if sb:
        try:
            q = sb.table("privacy_requests").select("*")
            if status:
                q = q.eq("status", status)
            if request_type:
                q = q.eq("request_type", request_type)
            rows = (q.order("created_at", desc=True).limit(limit).execute().data) or []
        except Exception as e:
            print(f"[privacy] staff request list failed: {e}")
    with privacy._MEMORY_LOCK:
        rows = rows + [
            dict(r) for r in privacy._MEMORY_REQUESTS
            if (not status or r.get("status") == status)
            and (not request_type or r.get("request_type") == request_type)
        ]
    # Phones are personal data but staff need to action the request; mask in
    # the list view and expose the full value only on the detail record.
    for row in rows:
        if row.get("phone"):
            digits = privacy.normalize_phone(row["phone"])
            row["phone"] = f"{digits[:3]}****{digits[-2:]}" if len(digits) >= 10 else "***"
    return {"success": True, "requests": rows[:limit]}


@ops_router.post("/corrections/{request_id}/resolve")
def staff_resolve_correction(
    request_id: str,
    data: CorrectionDecision,
    current_user: dict = Depends(require_role("admin", "verifier")),
):
    try:
        result = privacy.resolve_correction(
            request_id, data.decision, data.note,
            resolved_by=str(current_user.get("phone") or current_user.get("sub") or "staff"),
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="Correction request not found")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"success": True, **result}
