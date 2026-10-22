"""Trust & transparency routes: certificates, wallet, passport, ledger, earnings calculator."""
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal, Optional
import csv
import hashlib
import io
import json
import uuid
from datetime import datetime, timezone

from app.security import (
    create_access_token,
    decode_token,
    get_current_user,
    get_current_user_optional,
    require_role,
    verify_password,
)
from app import supabase_db as db
from app import config as app_config
from app import redis_store
from app.services import (
    access_policy,
    credit_engine,
    credit_lifecycle,
    evidence_service,
    ledger,
    market_store,
    payouts,
    split_engine,
    validation,
)

router = APIRouter(tags=["trust"])


def _resolve_fpo_link(farm: Optional[dict], farmer_phone: str) -> str:
    if farm and farm.get("fpo_id"):
        fpos = db.list_fpos() if db.is_ready() else []
        match = next((f for f in fpos if f.get("id") == farm.get("fpo_id")), None)
        return (match or {}).get("name") or "Linked FPO"
    if farm and farm.get("fpo"):
        return farm["fpo"]
    # Sample-FPO fallback applies to demo listings only (farm is None).
    return market_store.fpo_for_phone(farmer_phone) if farm is None else ""


def _ledger_sales(farm_id: str, listing_id: str) -> dict:
    """Aggregate SALE proceeds booked in the hash ledger for one listing.

    The ledger is the money source of truth: ``current_bid`` on a listing row
    can also hold a standing per-credit bid (place_bid), so proceeds are read
    back from the tamper-evident SALE events instead.
    """
    gross = 0.0
    credits = 0.0
    found = False
    buyer = None
    for event in ledger.get_chain(farm_id or ""):
        if event.get("type") != "SALE":
            continue
        payload = event.get("payload") or {}
        if payload.get("listing_id") != listing_id:
            continue
        found = True
        gross += float(payload.get("gross_inr") or 0)
        credits += float(payload.get("credits") or 0)
        if payload.get("buyer"):
            buyer = payload.get("buyer")
    return {"gross_inr": round(gross, 2), "credits": round(credits, 4), "found": found, "buyer": buyer}


# ─── Helpers ───

def _require_database():
    if not db.is_ready():
        raise HTTPException(
            status_code=503,
            detail="Database is not configured. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in backend/.env.",
        )


def _get_user(phone: str):
    _require_database()
    return db.get_profile(phone)


def _cert_id_for_listing(listing_id: str) -> str:
    return f"CX-{datetime.now(timezone.utc).year}-CERT-{listing_id.replace('-', '')[:8].upper()}"


def _public_location(location: Optional[str]) -> Optional[str]:
    """Drop the village, keep district/state for public transparency."""
    return access_policy.public_location(location)


def _sanitize_certificate_for_caller(cert: dict, caller: Optional[dict]) -> dict:
    """One access policy for JSON, CSV, PDF and the UI.

    Public: certificate id, crop, volume, dates, status, hashes, validation
    label and district-level location. Private: farmer name/phone, buyer name,
    commercial value, payout split.
    """
    item = dict(cert)
    caller_phone = (caller or {}).get("phone")
    caller_role = str((caller or {}).get("role") or "").lower()
    is_farmer = bool(caller_phone and item.get("farmer_phone") and caller_phone == item.get("farmer_phone"))
    is_staff = caller_role in ("admin", "verifier") or (
        caller_role == "fpo" and _is_scoped_fpo_certificate(item, caller)
    )
    is_buyer = _caller_is_buyer(item, caller)

    item["public_view"] = not (is_farmer or is_staff or is_buyer)
    item["access"] = {
        "farmer": bool(is_farmer),
        "buyer": bool(is_buyer),
        "staff": bool(is_staff),
    }
    if not (is_farmer or is_staff):
        item["farmer_phone"] = None
    if not (is_farmer or is_staff or is_buyer):
        item["value_inr"] = None
        item["farmer_name"] = "Verified Telangana Smallholder"
        item["issued_to"] = "Held in Registry Escrow" if item.get("status") != "RETIRED" else "Verified corporate buyer"
        item["buyer"] = item["issued_to"]
        item["location"] = _public_location(item.get("location"))
        item["split"] = {}
        item["unit_price"] = None
    elif is_farmer or is_staff:
        # Farmer/staff see the full split and buyer name for reconciliation.
        pass
    elif is_buyer:
        item["split"] = {}
        item["farmer_name"] = "Verified Telangana Smallholder"
        item["farmer_phone"] = None
        item["location"] = _public_location(item.get("location"))
    if not (is_farmer or is_staff):
        # Correction events can contain a pre-correction name; expose only the
        # fact/field that was corrected.
        item["corrections_applied"] = [
            {k: c.get(k) for k in ("field", "at", "hash")}
            for c in item.get("corrections_applied") or []
        ]
    return item


def _is_scoped_fpo_certificate(cert: dict, caller: Optional[dict]) -> bool:
    """FPO staff access is limited to farms linked to the officer's FPO."""
    if str((caller or {}).get("role") or "").lower() != "fpo":
        return False
    farm = db.get_farm(str(cert.get("farm_id") or "")) if db.is_ready() else None
    return access_policy.is_fpo_for_farm(caller, farm)


# ─── Models ───

class EarningsCalcModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    area_hectares: float
    crop: Optional[str] = ""
    ndvi: Optional[float] = 0.7
    baseline_ndvi: Optional[float] = None
    badge: Optional[str] = "DOCUMENT"
    # Evidence flags default to NOT claimed: an unproven input must not earn
    # the user a smaller uncertainty deduction just because the caller omitted it.
    has_photo: Optional[bool] = False
    geotag_ok: Optional[bool] = False
    fpo_or_registry: Optional[bool] = False


class RefundRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=3, max_length=1000)
    reference: Optional[str] = None


class DisputeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=3, max_length=1000)
    detail: Optional[str] = Field(default=None, max_length=4000)


class DisputeResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["release", "refund", "reject"]
    note: str = Field(min_length=3, max_length=2000)


class CorrectionLifecycleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: Literal["farmer_name", "location", "crop"]
    corrected_value: str = Field(min_length=1, max_length=300)
    reason: str = Field(min_length=3, max_length=1000)


# ─── Endpoints ───

def _all_listing_rows() -> list[dict]:
    """All listing rows, including partially sold ones (status Active).

    Certificates are now derived from SALE events, not just from rows whose
    status is Sold/Retired.  Querying only terminal statuses would hide every
    partial sale's certificate.
    """
    if not db.is_ready():
        return market_store.all_rows()
    try:
        sb = db._client()
        return (
            sb.table("marketplace_listings").select("*")
            .order("created_at", desc=True).limit(2000).execute().data
        ) or []
    except Exception as e:
        print(f"[certificates] listing read failed ({e}) — using demo store")
        return market_store.all_rows()


def _derived_certificates() -> tuple[list[dict], dict]:
    rows = _all_listing_rows()
    chain_cache: dict[str, list] = {}

    def chain_for(farm_id: str) -> list:
        if farm_id not in chain_cache:
            chain_cache[farm_id] = ledger.get_chain(farm_id) if farm_id else []
        return chain_cache[farm_id]

    certs = credit_lifecycle.derive_certificates(rows, chain_for)
    status = validation.current_status()
    verify_cache: dict[str, dict] = {}
    for cert in certs:
        farm_id = cert.get("farm_id") or ""
        if farm_id not in verify_cache:
            try:
                verify_cache[farm_id] = ledger.verify_chain(farm_id)
            except Exception:
                verify_cache[farm_id] = {"verified": False, "error": "verification failed"}
        cert["ledger_verified"] = bool((verify_cache.get(farm_id) or {}).get("verified"))
        cert["credits_basis"] = "proxy_estimate"
        cert["validation"] = status
        cert["validation_status"] = status.get("status")
        cert["source_parcels"] = [
            f"{_public_location(cert.get('location')) or 'Telangana'} ({cert.get('crop') or 'Mixed'})"
        ]
    return certs, verify_cache


def _caller_is_buyer(cert: dict, caller: Optional[dict]) -> bool:
    """Buyer-of-record check.

    New live SALE records bind buyer access to the corporate account id.
    Historical demo records may use a display name, but live access never does.
    """
    if not caller or str(caller.get("role") or "").lower() != "buyer":
        return False
    c_id = caller.get("c_id")
    recorded_c_id = cert.get("buyer_c_id")
    if c_id is not None and recorded_c_id is not None:
        return str(c_id) == str(recorded_c_id)
    # Historical/demo records predate stable buyer ids. Name matching is only
    # acceptable in offline demo mode, never for live buyer records.
    if db.is_ready():
        return False
    name = str(caller.get("name") or "").strip().lower()
    legacy_name = str(cert.get("buyer") or cert.get("issued_to") or "").strip().lower()
    return bool(legacy_name and name == legacy_name)


def _can_see_held(cert: dict, caller: Optional[dict]) -> bool:
    phone = (caller or {}).get("phone")
    role = str((caller or {}).get("role") or "").lower()
    if role in ("admin", "verifier"):
        return True
    if role == "fpo":
        if not db.is_ready():
            return False
        profile = db.get_profile(phone or "") or {}
        farm = db.get_farm(cert.get("farm_id") or "") or {}
        return bool(
            profile.get("fpo_id")
            and farm.get("fpo_id")
            and str(profile.get("fpo_id")) == str(farm.get("fpo_id"))
        )
    if phone and cert.get("farmer_phone") == phone:
        return True
    return _caller_is_buyer(cert, caller)


def _visible_certificates(certs: list[dict], caller: Optional[dict]) -> list[dict]:
    """Public sees retired certificates; owners/buyers/staff also see held."""
    return [
        cert for cert in certs
        if str(cert.get("status")).upper() == "RETIRED" or _can_see_held(cert, caller)
    ]


def _certificate_or_404(cert_id: str, caller: Optional[dict]) -> dict:
    certs, _ = _derived_certificates()
    cert = next(
        (c for c in certs if str(c.get("id") or "").upper() == str(cert_id).strip().upper()),
        None,
    )
    if not cert:
        raise HTTPException(status_code=404, detail="Certificate not found")
    if str(cert.get("status")).upper() != "RETIRED" and not _can_see_held(cert, caller):
        # Do not leak the existence of a held certificate to the public.
        raise HTTPException(status_code=404, detail="Certificate not found")
    return cert


def _listing_row(listing_id: str) -> Optional[dict]:
    if not listing_id:
        return None
    if not db.is_ready():
        return market_store.get(listing_id)
    try:
        sb = db._client()
        rows = (
            sb.table("marketplace_listings").select("*")
            .eq("id", listing_id).limit(1).execute().data
        ) or []
        return rows[0] if rows else None
    except Exception:
        return None


def _statement_for(cert: dict) -> Optional[dict]:
    chain = ledger.get_chain(cert.get("farm_id") or "")
    statements = payouts.settlement_statements(chain, cert.get("listing_id"))
    return next(
        (s for s in statements if s.get("escrow_ref") == cert.get("escrow_ref")),
        None,
    )


def _certificate_dispute_lock(cert: dict):
    return f"listing:settle:{cert.get('listing_id')}"


_LIFECYCLE_OPTIONAL_COLUMNS = {
    "credits_sold", "lifecycle_state", "dispute_status", "dispute_reason",
    "dispute_opened_at", "dispute_resolved_at",
}


def _apply_listing_fields(listing_id: str, fields: dict) -> bool:
    if not db.is_ready():
        return market_store.update(listing_id, fields) is not None
    sb = db._client()
    try:
        res = (
            sb.table("marketplace_listings").update(fields)
            .eq("id", listing_id).execute()
        )
        return bool(res.data)
    except Exception as e:
        # Pre-migration deployments may not have the lifecycle columns yet.
        # Retry the core balance/status update rather than blocking refunds.
        core = {k: v for k, v in fields.items() if k not in _LIFECYCLE_OPTIONAL_COLUMNS}
        if core and core != fields:
            try:
                res = (
                    sb.table("marketplace_listings").update(core)
                    .eq("id", listing_id).execute()
                )
                return bool(res.data)
            except Exception as retry_error:
                print(f"[lifecycle] listing update failed for {listing_id}: {retry_error}")
                return False
        print(f"[lifecycle] listing update failed for {listing_id}: {e}")
        return False


def _refund_locked(cert: dict, reason: str, reference: Optional[str], actor_role: str) -> dict:
    """Execute a full-sale refund. Caller must hold the listing settle lock."""
    if str(cert.get("status")).upper() == "REFUNDED":
        return {
            "success": True,
            "already_refunded": True,
            "certificate_id": cert.get("id"),
            "message": "This sale was already refunded; no balance was changed again.",
        }
    statement = _statement_for(cert)
    if not statement:
        raise HTTPException(
            status_code=409,
            detail=(
                "This certificate has no ledger SALE/SPLIT record (legacy row). "
                "A refund cannot be derived safely; reconcile manually before changing balances."
            ),
        )
    listing = _listing_row(cert.get("listing_id") or "")
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found for this certificate")
    credits = float(statement.get("credits_sold") or 0)
    previous_remaining = float(listing.get("total_credits") or 0)
    restored_remaining = round(previous_remaining + credits, 4)
    # Derive net sold from the ledger, not a possibly-stale/missing
    # credits_sold column (pre-migration rows are common in the pilot).
    net_before = 0.0
    for event in ledger.get_chain(cert.get("farm_id") or ""):
        payload = event.get("payload") or {}
        if str(payload.get("listing_id") or "") != str(cert.get("listing_id")):
            continue
        if event.get("type") == "SALE":
            net_before += float(payload.get("credits") or 0)
        elif event.get("type") == "REFUND":
            net_before -= float(payload.get("credits") or 0)
    net_sold = max(0.0, net_before - credits)
    lifecycle_state = "Active" if net_sold <= 1e-9 else "Partially Sold"
    refund_ref = reference or credit_lifecycle.refund_reference(
        cert.get("id") or "", cert.get("escrow_ref")
    )
    now = datetime.now(timezone.utc).isoformat()
    fields = {
        "total_credits": restored_remaining,
        "credits_sold": round(net_sold, 4),
        "status": "Active",
        "lifecycle_state": lifecycle_state,
        "dispute_status": "RESOLVED" if str(listing.get("dispute_status") or "NONE").upper() != "NONE" else "NONE",
        "updated_at": now,
    }
    if not _apply_listing_fields(cert.get("listing_id") or "", fields):
        raise HTTPException(status_code=409, detail="Listing balance changed; refund not applied")
    event = ledger.append_event(cert.get("farm_id") or "", "REFUND", {
        "listing_id": cert.get("listing_id"),
        "certificate_id": cert.get("id"),
        "escrow_ref": cert.get("escrow_ref"),
        "refund_ref": refund_ref,
        "credits": round(credits, 4),
        "gross_inr": statement.get("gross_inr"),
        "farmer_inr": statement.get("farmer_inr"),
        "fpo_inr": statement.get("fpo_inr"),
        "platform_inr": statement.get("platform_inr"),
        "reason": reason[:1000],
        "refunded_by_role": actor_role,
        "restored_credits": round(credits, 4),
        "balance_after": restored_remaining,
    })
    try:
        from app.services.certificate_pdf import invalidate_certificate_pdf
        invalidate_certificate_pdf(cert.get("id") or "")
    except Exception:
        pass
    return {
        "success": True,
        "certificate_id": cert.get("id"),
        "listing_id": cert.get("listing_id"),
        "refund_ref": refund_ref,
        "refunded_inr": statement.get("gross_inr"),
        "reversed_split": {
            "farmer_inr": statement.get("farmer_inr"),
            "fpo_inr": statement.get("fpo_inr"),
            "platform_inr": statement.get("platform_inr"),
        },
        "credits_restored": round(credits, 4),
        "balance_after": restored_remaining,
        "lifecycle_state": lifecycle_state,
        "ledger_hash": event.get("hash"),
        "message": "Sale refunded; credits restored to the listing with a REFUND ledger event.",
    }


def _dispute_events(cert: dict) -> list[dict]:
    chain = ledger.get_chain(cert.get("farm_id") or "")
    return [
        e for e in chain
        if e.get("type") in ("DISPUTE", "DISPUTE_RESOLVED")
        and str((e.get("payload") or {}).get("certificate_id") or "") == str(cert.get("id"))
    ]


_CERT_CSV_FIELDS = [
    "id", "listing_id", "status", "crop", "volume_mt", "issued_date",
    "retired_at", "refunded_at", "batch_hash", "validation_status",
    "farmer_name", "issued_to", "value_inr", "location",
]


@router.get("/certificates")
def list_certificates(current_user: Optional[dict] = Depends(get_current_user_optional)):
    try:
        certs, _ = _derived_certificates()
    except Exception as e:
        return {"success": False, "message": str(e), "certificates": []}
    visible = _visible_certificates(certs, current_user)
    return {
        "success": True,
        "count": len(visible),
        "certificates": [
            _sanitize_certificate_for_caller(c, current_user) for c in visible
        ],
        "access_note": (
            "Public certificates are retired only and exclude buyer/farmer names, "
            "commercial value and payout splits. Owners, the buyer of record and "
            "staff see their own full record."
        ),
    }


@router.get("/certificates/export.csv")
def export_certificates_csv(current_user: Optional[dict] = Depends(get_current_user_optional)):
    """CSV export that obeys exactly the same access policy as JSON/PDF."""
    from fastapi.responses import Response
    certs, _ = _derived_certificates()
    visible = _visible_certificates(certs, current_user)
    safe = [_sanitize_certificate_for_caller(c, current_user) for c in visible]
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=_CERT_CSV_FIELDS, extrasaction="ignore")
    writer.writeheader()
    for cert in safe:
        writer.writerow({k: cert.get(k) for k in _CERT_CSV_FIELDS})
    payload = out.getvalue().encode("utf-8")
    return Response(
        content=payload,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="carbonx-certificates.csv"',
            "X-CarbonX-Access": "authenticated" if current_user else "public",
        },
    )


@router.get("/certificates/{cert_id}")
def get_certificate(cert_id: str, current_user: Optional[dict] = Depends(get_current_user_optional)):
    cert = _certificate_or_404(cert_id, current_user)
    return {
        "success": True,
        "certificate": _sanitize_certificate_for_caller(cert, current_user),
    }


@router.get("/certificates/{cert_id}/pdf")
def download_certificate_pdf(
    cert_id: str,
    current_user: Optional[dict] = Depends(get_current_user_optional),
):
    from fastapi.responses import Response
    from app.services.certificate_pdf import render_certificate_pdf

    raw = _certificate_or_404(cert_id, current_user)
    safe = _sanitize_certificate_for_caller(raw, current_user)
    access = "full" if not safe.get("public_view") else "public"

    cert = {
        "id": cert_id,
        "buyer": safe.get("issued_to") or "—",
        "farmer_name": safe.get("farmer_name"),
        "crop": safe.get("crop"),
        "volume": safe.get("volume_mt"),
        "value": safe.get("value_inr"),
        "location": safe.get("location"),
        "issued_date": safe.get("issued_date"),
        "retired_date": safe.get("retired_at"),
        "status": safe.get("status"),
        "dispute_status": safe.get("dispute_status"),
        "batch_hash": safe.get("batch_hash") or safe.get("ledger_hash") or "",
        "validation_label": (safe.get("validation") or {}).get("label"),
        "validation_status": safe.get("validation_status"),
        "credits_basis": safe.get("credits_basis"),
        "public_view": safe.get("public_view"),
    }
    pdf_bytes = render_certificate_pdf(cert)
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="CarbonX_Certificate_{cert_id}.pdf"',
            "X-CarbonX-Access": access,
        },
    )


@router.post("/certificates/{cert_id}/retire")
def retire_certificate(
    cert_id: str,
    scope: Optional[str] = "Scope 1 Neutrality",
    current_user: Optional[dict] = Depends(get_current_user_optional),
):
    """Permanently retire a held certificate (legacy rows) / confirm retirement.

    Purchases made through the escrow path are retired atomically at sale
    time; this endpoint remains for legacy ``Sold`` rows and returns an
    idempotent success for already-retired certificates.
    """
    if db.is_ready() and not current_user:
        raise HTTPException(status_code=401, detail="Sign in to retire a certificate")
    if db.is_ready() and str((current_user or {}).get("role", "")).lower() != "buyer":
        raise HTTPException(status_code=403, detail="Only the corporate buyer may retire a certificate")

    cert = _certificate_or_404(cert_id, current_user)
    if db.is_ready() and str(cert.get("status")).upper() == "RETIRED":
        return {
            "success": True, "message": f"Certificate {cert_id} is already permanently retired",
            "cert_id": cert_id, "listing_id": cert.get("listing_id"),
            "status": "RETIRED", "already_retired": True,
        }
    if str(cert.get("status")).upper() == "REFUNDED":
        raise HTTPException(status_code=409, detail="A refunded certificate cannot be retired")

    # Ledger-derived certificates are retired at sale time. Only a legacy row
    # (no SALE event) needs a manual retirement transition.
    if cert.get("source") == "ledger":
        return {
            "success": True,
            "message": f"Certificate {cert_id} is already permanently retired",
            "cert_id": cert_id,
            "listing_id": cert.get("listing_id"),
            "status": "RETIRED",
            "already_retired": True,
        }

    listing_id = cert.get("listing_id")
    lock_name = f"listing:retire:{listing_id}"
    if not redis_store.acquire_lock(lock_name, ttl_seconds=30):
        raise HTTPException(status_code=409, detail="Retirement already in progress; retry")
    try:
        retired_ts = datetime.now(timezone.utc).isoformat()
        if db.is_ready():
            sb = db._client()
            sb.table("marketplace_listings").update({
                "status": "Retired",
                "lifecycle_state": "Retired",
                "updated_at": retired_ts,
            }).eq("id", listing_id).execute()
        else:
            market_store.update(listing_id, {
                "status": "Retired", "lifecycle_state": "Retired",
                "updated_at": retired_ts,
            })
        if cert.get("farm_id"):
            ledger.append_event(cert["farm_id"], "RETIRE", {
                "certificate_id": cert_id,
                "listing_id": listing_id,
                "scope": scope,
                "manual": True,
            })
        from app.services.certificate_pdf import invalidate_certificate_pdf
        invalidate_certificate_pdf(cert_id)
        invalidate_certificate_pdf(f"{str(cert_id).strip().upper()}:full")
        invalidate_certificate_pdf(f"{str(cert_id).strip().upper()}:public")
        return {
            "success": True, "message": f"Certificate {cert_id} permanently retired for {scope}",
            "cert_id": cert_id, "listing_id": listing_id, "status": "RETIRED",
            "scope": scope, "retired_timestamp": retired_ts,
        }
    finally:
        redis_store.release_lock(lock_name)


@router.post("/certificates/{cert_id}/refund")
def refund_certificate(
    cert_id: str,
    data: RefundRequest,
    current_user: Optional[dict] = Depends(get_current_user_optional),
):
    """Refund one settled sale and restore its credits to the listing.

    Staff-only in production. The ledger gets an explicit REFUND event with
    the reversed split; the SALE/SPLIT/REFUND history is never deleted, and
    the certificate flips to REFUNDED while its id remains unique.
    """
    if db.is_ready():
        if not current_user:
            raise HTTPException(status_code=401, detail="Staff sign-in required for refunds")
        role = str(current_user.get("role") or "").lower()
        if role not in ("admin", "verifier"):
            raise HTTPException(status_code=403, detail="Only admin/verifier staff may refund a sale")
    cert = _certificate_or_404(cert_id, current_user)
    if cert.get("source") != "ledger":
        raise HTTPException(status_code=409, detail="Legacy certificate has no ledger sale to refund")
    listing_id = cert.get("listing_id")
    lock_name = _certificate_dispute_lock(cert)
    if not redis_store.acquire_lock(lock_name, ttl_seconds=60):
        raise HTTPException(status_code=409, detail="Settlement in progress; retry the refund")
    try:
        # Re-derive under the lock so two refund clicks cannot both restore credits.
        fresh = _certificate_or_404(cert_id, current_user)
        actor = str((current_user or {}).get("role") or "demo")
        return _refund_locked(fresh, data.reason, data.reference, actor)
    finally:
        redis_store.release_lock(lock_name)


@router.post("/certificates/{cert_id}/dispute")
def open_certificate_dispute(
    cert_id: str,
    data: DisputeRequest,
    current_user: Optional[dict] = Depends(get_current_user_optional),
):
    """Open a dispute on a sale, freezing the listing from further sales."""
    if db.is_ready() and not current_user:
        raise HTTPException(status_code=401, detail="Sign in to open a dispute")
    cert = _certificate_or_404(cert_id, current_user)
    if cert.get("source") != "ledger":
        raise HTTPException(status_code=409, detail="Disputes require a ledger sale record")
    role = str((current_user or {}).get("role") or "").lower()
    farmer_owner = bool((current_user or {}).get("phone") and cert.get("farmer_phone") == current_user.get("phone"))
    buyer = _caller_is_buyer(cert, current_user)
    if db.is_ready() and not (farmer_owner or buyer or role in ("admin", "verifier")):
        raise HTTPException(status_code=403, detail="Only the farmer, buyer of record or staff may dispute")
    if str(cert.get("status")).upper() == "REFUNDED":
        raise HTTPException(status_code=409, detail="A refunded certificate cannot be disputed")
    if str(cert.get("dispute_status")).upper() == "OPEN":
        raise HTTPException(status_code=409, detail="A dispute is already open for this certificate")

    lock_name = _certificate_dispute_lock(cert)
    if not redis_store.acquire_lock(lock_name, ttl_seconds=60):
        raise HTTPException(status_code=409, detail="Settlement in progress; retry the dispute")
    try:
        fresh = _certificate_or_404(cert_id, current_user)
        if str(fresh.get("dispute_status")).upper() == "OPEN":
            raise HTTPException(status_code=409, detail="A dispute is already open for this certificate")
        dispute_id = "DSP-" + uuid.uuid4().hex[:12].upper()
        now = datetime.now(timezone.utc).isoformat()
        event = ledger.append_event(fresh.get("farm_id") or "", "DISPUTE", {
            "dispute_id": dispute_id,
            "certificate_id": fresh.get("id"),
            "listing_id": fresh.get("listing_id"),
            "escrow_ref": fresh.get("escrow_ref"),
            "reason": data.reason[:1000],
            "detail_present": bool(data.detail),
            "opened_by_role": role or ("farmer" if farmer_owner else "buyer" if buyer else "demo"),
        })
        listing = _listing_row(fresh.get("listing_id") or "") or {}
        _apply_listing_fields(fresh.get("listing_id") or "", {
            "dispute_status": "OPEN",
            "dispute_reason": data.reason[:1000],
            "dispute_opened_at": now,
            "lifecycle_state": "Disputed",
        })
        return {
            "success": True,
            "dispute_id": dispute_id,
            "certificate_id": fresh.get("id"),
            "listing_id": fresh.get("listing_id"),
            "status": "OPEN",
            "opened_at": now,
            "ledger_hash": event.get("hash"),
            "affected_balance": {
                "credits_remaining": float(listing.get("total_credits") or 0),
                "listing_status": listing.get("status"),
            },
            "message": (
                "Dispute opened. The listing is frozen for new sales; refund and "
                "release decisions are recorded in the ledger."
            ),
        }
    finally:
        redis_store.release_lock(lock_name)


@router.post("/certificates/{cert_id}/dispute/resolve")
def resolve_certificate_dispute(
    cert_id: str,
    data: DisputeResolveRequest,
    current_user: Optional[dict] = Depends(get_current_user_optional),
):
    """Staff decision: release the sale, reject the dispute or refund it."""
    if db.is_ready():
        if not current_user:
            raise HTTPException(status_code=401, detail="Staff sign-in required")
        if str(current_user.get("role") or "").lower() not in ("admin", "verifier"):
            raise HTTPException(status_code=403, detail="Only admin/verifier staff may resolve a dispute")
    cert = _certificate_or_404(cert_id, current_user)
    if str(cert.get("dispute_status")).upper() != "OPEN":
        raise HTTPException(status_code=409, detail="No open dispute for this certificate")

    lock_name = _certificate_dispute_lock(cert)
    if not redis_store.acquire_lock(lock_name, ttl_seconds=60):
        raise HTTPException(status_code=409, detail="Settlement in progress; retry")
    try:
        fresh = _certificate_or_404(cert_id, current_user)
        if str(fresh.get("dispute_status")).upper() != "OPEN":
            raise HTTPException(status_code=409, detail="No open dispute for this certificate")
        dispute = next(
            (e for e in reversed(_dispute_events(fresh)) if e.get("type") == "DISPUTE"),
            None,
        )
        dispute_id = ((dispute or {}).get("payload") or {}).get("dispute_id")
        refund_result = None
        if data.decision == "refund":
            refund_result = _refund_locked(
                fresh, f"Dispute {dispute_id}: {data.note}", None,
                str((current_user or {}).get("role") or "demo"),
            )
        now = datetime.now(timezone.utc).isoformat()
        event = ledger.append_event(fresh.get("farm_id") or "", "DISPUTE_RESOLVED", {
            "dispute_id": dispute_id,
            "certificate_id": fresh.get("id"),
            "listing_id": fresh.get("listing_id"),
            "escrow_ref": fresh.get("escrow_ref"),
            "decision": data.decision,
            "note": data.note[:2000],
            "resolved_by_role": str((current_user or {}).get("role") or "demo"),
        })
        listing = _listing_row(fresh.get("listing_id") or "") or {}
        remaining = float((refund_result or {}).get("balance_after", listing.get("total_credits") or 0))
        if remaining <= 1e-9 and str(listing.get("status")).lower() == "retired":
            lifecycle = "Retired"
        elif remaining <= 1e-9:
            lifecycle = "Retired"
        elif float(listing.get("credits_sold") or 0) > 0:
            lifecycle = "Partially Sold"
        else:
            lifecycle = "Active"
        _apply_listing_fields(fresh.get("listing_id") or "", {
            "dispute_status": "REFUNDED" if data.decision == "refund" else "RESOLVED",
            "dispute_resolved_at": now,
            "lifecycle_state": lifecycle,
        })
        return {
            "success": True,
            "dispute_id": dispute_id,
            "certificate_id": fresh.get("id"),
            "decision": data.decision,
            "resolved_at": now,
            "refund": refund_result,
            "lifecycle_state": lifecycle,
            "ledger_hash": event.get("hash"),
        }
    finally:
        redis_store.release_lock(lock_name)


@router.post("/certificates/{cert_id}/correction")
def correct_certificate(
    cert_id: str,
    data: CorrectionLifecycleRequest,
    current_user: Optional[dict] = Depends(get_current_user_optional),
):
    """Correct non-financial certificate metadata with an audit event.

    Financial corrections (credits/value) must go through refund + reissue;
    changing money in place would make the certificate and ledger disagree.
    """
    if db.is_ready():
        if not current_user:
            raise HTTPException(status_code=401, detail="Staff sign-in required")
        if str(current_user.get("role") or "").lower() not in ("admin", "verifier"):
            raise HTTPException(status_code=403, detail="Only admin/verifier staff may correct a certificate")
    cert = _certificate_or_404(cert_id, current_user)
    if cert.get("source") != "ledger":
        raise HTTPException(status_code=409, detail="Corrections require a ledger sale record")
    if str(cert.get("status")).upper() == "REFUNDED":
        raise HTTPException(status_code=409, detail="Refunded certificates are not corrected in place")
    lock_name = _certificate_dispute_lock(cert)
    if not redis_store.acquire_lock(lock_name, ttl_seconds=30):
        raise HTTPException(status_code=409, detail="Settlement in progress; retry")
    try:
        old_value = cert.get(data.field)
        event = ledger.append_event(cert.get("farm_id") or "", "CORRECTION", {
            "certificate_id": cert.get("id"),
            "listing_id": cert.get("listing_id"),
            "escrow_ref": cert.get("escrow_ref"),
            "field": data.field,
            "old_value": old_value,
            "new_value": data.corrected_value,
            "reason": data.reason[:1000],
            "corrected_by_role": str((current_user or {}).get("role") or "demo"),
        })
        _apply_listing_fields(cert.get("listing_id") or "", {data.field: data.corrected_value})
        try:
            from app.services.certificate_pdf import invalidate_certificate_pdf
            invalidate_certificate_pdf(cert.get("id") or "")
        except Exception:
            pass
        return {
            "success": True,
            "certificate_id": cert.get("id"),
            "field": data.field,
            "old_value": old_value,
            "new_value": data.corrected_value,
            "ledger_hash": event.get("hash"),
            "financial_values_unchanged": True,
        }
    finally:
        redis_store.release_lock(lock_name)


@router.get("/certificates/{cert_id}/lifecycle")
def certificate_lifecycle(
    cert_id: str,
    current_user: Optional[dict] = Depends(get_current_user_optional),
):
    cert = _certificate_or_404(cert_id, current_user)
    listing = _listing_row(cert.get("listing_id") or "") or {}
    chain = ledger.get_chain(cert.get("farm_id") or "")
    snapshot = credit_lifecycle.lifecycle_snapshot(listing, chain)
    statement = _statement_for(cert)
    full_visibility = not _sanitize_certificate_for_caller(cert, current_user).get("public_view")
    disputes = []
    for event in chain:
        payload = event.get("payload") or {}
        if str(payload.get("certificate_id") or "") != str(cert.get("id")):
            continue
        if event.get("type") in ("DISPUTE", "DISPUTE_RESOLVED", "CORRECTION"):
            disputes.append({
                "type": event.get("type"),
                "at": event.get("ts"),
                "decision": payload.get("decision"),
                "field": payload.get("field"),
                "new_value": payload.get("new_value") if full_visibility else None,
                "hash": event.get("hash"),
            })
    return {
        "success": True,
        "certificate": _sanitize_certificate_for_caller(cert, current_user),
        "lifecycle": snapshot,
        "payout": {
            k: statement.get(k) for k in (
                "gross_inr", "farmer_inr", "fpo_inr", "platform_inr",
                "farmer_floor_met", "payout_status", "refunded", "refund_ref",
                "issues", "ledger_hash",
            )
        } if statement else None,
        "audit_events": disputes,
        "rules": {
            "issuance": "A certificate is created per sale (unique id, sale_seq) after escrow CAS.",
            "partial_sale": "Listing stays Active with lifecycle_state='Partially Sold'; each sale has its own certificate.",
            "retirement": "Full purchase retires the purchased credits atomically; refunds restore the balance.",
            "correction": "Non-financial fields are corrected with a CORRECTION event; money changes require refund + reissue.",
            "dispute": "An open dispute freezes new sales and must end in release, reject or refund.",
            "refund": "REFUND restores credits and reverses the split from the original SALE/SPLIT record.",
        },
    }


@router.get("/ops/certificates/reconciliation")
def certificates_reconciliation(
    current_user: dict = Depends(require_role("admin", "verifier")),
):
    certs, _ = _derived_certificates()
    ids = [c.get("id") for c in certs if c.get("id")]
    duplicates = sorted({c for c in ids if ids.count(c) > 1})
    listing_summaries = []
    issues = []
    for listing in _all_listing_rows():
        chain = ledger.get_chain(listing.get("farm_id") or "")
        statements = payouts.settlement_statements(chain, listing.get("id"))
        recon = payouts.reconcile(statements)
        snapshot = credit_lifecycle.lifecycle_snapshot(listing, chain)
        if recon.get("issues") or snapshot.get("duplicate_certificate_ids"):
            issues.append({
                "listing_id": listing.get("id"),
                "payout_issues": recon.get("issues"),
                "lifecycle": snapshot,
            })
        listing_summaries.append({
            "listing_id": listing.get("id"),
            "status": listing.get("status"),
            "lifecycle_state": snapshot.get("lifecycle_state"),
            "credits_remaining": snapshot.get("credits_remaining"),
            "credits_sold": snapshot.get("credits_sold"),
            "certificates": snapshot.get("certificate_count"),
            "reconciliation": recon.get("status"),
        })
    return {
        "success": True,
        "certificates_total": len(certs),
        "unique_certificate_ids": len(set(ids)),
        "duplicate_certificate_ids": duplicates,
        "listings": listing_summaries,
        "issues": issues,
        "status": "reconciled" if not duplicates and not issues else "issues_found",
        "note": (
            "Checks are derived from the ledger. Legacy rows without SALE events "
            "are reported as unreconciled rather than assumed correct."
        ),
    }


@router.get("/passport/{farm_id}")
def get_carbon_passport(farm_id: str, current_user: Optional[dict] = Depends(get_current_user_optional)):
    if db.is_ready():
        farm = db.get_farm(farm_id)
        if not farm:
            if farm_id == "demo":
                demo_mode = True
                farm = {
                    "id": farm_id, "name": "Sri Venkateswara Organic Farm",
                    "owner_phone": "9000000001", "crop_type": "Rice", "area_hectares": 2.4,
                    "ndvi": 0.78, "evi": 0.65, "soil_moisture": 41, "tree_cover": 28,
                    "biodiversity_score": 720, "carbon_tonnes": 82, "total_credits": 96.0,
                    "biodiversity_credits": 18.0, "satellite_source": "Sentinel-2 (demo)",
                    "ai_confidence": 0.87, "status": "verified", "badge": "REGISTRY",
                    "irrigation": "Drip", "updated_at": "2026-09-10T12:00:00+00:00",
                    "credits_ci90_low": 85.0, "credits_ci90_high": 107.0,
                    "formula_version": app_config.FORMULA_VERSION,
                    "s2_scene": "COPERNICUS/S2_SR_HARMONIZED/20231115T052631_20231115T052631_T43RGP",
                }
            else:
                return {"success": False, "code": "NOT_FOUND", "message": "Farm not found"}
        else:
            demo_mode = False
    else:
        # DB off: serve the documented demo farm for any id (clearly flagged)
        demo_mode = True
        farm = {
            "id": farm_id, "name": "Sri Venkateswara Organic Farm",
            "owner_phone": "9000000001", "crop_type": "Rice", "area_hectares": 2.4,
            "ndvi": 0.78, "evi": 0.65, "soil_moisture": 41, "tree_cover": 28,
            "biodiversity_score": 720, "carbon_tonnes": 82, "total_credits": 96.0,
            "biodiversity_credits": 18.0, "satellite_source": "Sentinel-2 (demo)",
            "ai_confidence": 0.87, "status": "verified", "badge": "REGISTRY",
            "irrigation": "Drip", "updated_at": "2026-09-10T12:00:00+00:00",
            "credits_ci90_low": 85.0, "credits_ci90_high": 107.0,
            "formula_version": app_config.FORMULA_VERSION,
            "s2_scene": "COPERNICUS/S2_SR_HARMONIZED/20231115T052631_20231115T052631_T43RGP",
        }
    owner = db.get_profile(farm.get("owner_phone") or "") if db.is_ready() else {}
    kyc = db.get_kyc_status(farm.get("owner_phone") or "") if db.is_ready() else None
    badge = farm.get("badge") or (kyc or {}).get("badge") or "DOCUMENT"
    benchmark = {"REGISTRY": 340, "REGISTRY_DOC": 320, "FPO": 300}.get(badge, 310)
    # A real content hash over the passport's core fields.  The old value was a
    # UUID5 of the id/timestamp dressed up as a verification hash; anyone can
    # now recompute this one from the fields returned in this response.
    hash_snapshot = {
        "passport_id": f"CX-FARM-{str(farm_id).replace('-', '')[:8].upper()}",
        "farm_id": farm_id,
        "crop": farm.get("crop_type"),
        "area_hectares": farm.get("area_hectares"),
        "ndvi": farm.get("ndvi"),
        "total_credits": farm.get("total_credits"),
        "formula_version": farm.get("formula_version") or app_config.FORMULA_VERSION,
        "updated_at": farm.get("updated_at"),
    }
    verification_hash = "0x" + hashlib.sha256(
        json.dumps(hash_snapshot, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()

    credits_total = float(farm.get("total_credits") or 0)
    income = credit_engine.income_projection(credits_total, badge)

    # Only evidence the platform actually holds counts: the badge is a real
    # verification fact, a stored NDVI is real current satellite evidence, and
    # practice photos / geotags come from the real capture pipeline
    # (evidence_service). No stored baseline NDVI series exists yet, so that
    # component stays unclaimed rather than being assumed.
    evidence = evidence_service.evidence_flags(farm_id)
    quality = credit_engine.evidence_quality(
        has_photo=evidence["practice_photo"], geotag_ok=evidence["geotag_inside_boundary"],
        fpo_or_registry=badge in ("REGISTRY", "REGISTRY_DOC", "FPO"),
        ndvi_current=farm.get("ndvi") is not None, baseline_known=False,
    )
    # Genesis only for real farm rows — never mint a hash-chain ISSUE event
    # for a phantom id (demo farms are clearly flagged and skip anchoring).
    if not demo_mode:
        ledger.ensure_genesis(farm_id, {
            "farm": farm.get("name"), "crop": farm.get("crop_type"),
            "area_hectares": farm.get("area_hectares"), "ndvi": farm.get("ndvi"),
            "carbon_tonnes": farm.get("carbon_tonnes"), "badge": badge, "status": farm.get("status"),
        }, ts=(farm.get("updated_at") or "") or None)
    chain = ledger.summary(farm_id)
    caller_is_full = access_policy.can_access_farm(current_user, farm)
    chain["history"] = access_policy.ledger_events_for(
        ledger.get_chain(farm_id), full_access=caller_is_full
    )
    chain["access"] = "full" if caller_is_full else "public"
    farm_status = farm.get("status")
    monitoring = {
        "last_monitored_at": farm.get("last_monitored_at"),
        "last_monitor_ndvi": farm.get("last_monitor_ndvi"),
        "at_risk": str(farm_status or "").lower() == "flagged",
        "cycle": "5-day Sentinel-2 revisit",
    }

    identity = access_policy.passport_identity(farm, owner or {}, current_user)
    validation_status = validation.current_status()
    top_status = (
        "FIELD-VALIDATED MRV RECORD (LIMITED)"
        if validation_status.get("status") == "field_validated_limited"
        else "MRV RECORD — PROXY ESTIMATE (NOT FIELD-VALIDATED)"
    )
    public_evidence = access_policy.evidence_public(evidence)

    return {
        "success": True, "passport_id": f"CX-FARM-{str(farm_id).replace('-', '')[:8].upper()}",
        "demo_mode": demo_mode,
        # Farm name is owner-visible only; the public record is identified by
        # passport id, crop, district and credits (no farmer name or phone).
        "farm_name": farm.get("name") if caller_is_full else "Verified smallholder farm",
        "owner_name": identity["owner_name"],
        "phone": identity["phone"],
        "district": identity["district"], "village": identity["village"],
        "location_precision": identity["location_precision"],
        "access": {
            "public_view": not caller_is_full,
            "owner": access_policy.is_owner(current_user, farm.get("owner_phone")),
            "staff": access_policy.is_staff(current_user)
                or access_policy.is_fpo_for_farm(current_user, farm),
        },
        "crop": farm.get("crop_type"), "irrigation": farm.get("irrigation"),
        "acreage": farm.get("area_hectares"), "badge": badge, "benchmark_price": benchmark,
        "annual_credits": farm.get("total_credits"), "carbon_tonnes": farm.get("carbon_tonnes"),
        "sentinel_ndvi": farm.get("ndvi"), "evi": farm.get("evi"),
        "biodiversity_index": round(float(farm.get("biodiversity_score") or 0) / 10, 1) if farm.get("biodiversity_score") else None,
        "satellite_source": farm.get("satellite_source"),
        # No calibrated model confidence exists; never present a heuristic as one.
        "ai_confidence": None,
        "confidence_basis": "Not reported — no calibrated model confidence.",
        "evidence_quality": quality["score"],
        "credits_basis": "proxy_estimate",
        "validation": validation_status,
        "verification_hash": verification_hash,
        "verification_hash_covers": sorted(hash_snapshot.keys()),
        "farm_status": farm_status,
        "kyc_status": (kyc or {}).get("status") if caller_is_full else None,
        "status": top_status,
        "biodiversity_index_label": "Relative index — not a species census",
        "expected_earnings": income if caller_is_full else None,
        "expected_earnings_note": (
            "Projected income visible to the farmer/staff only; the public record shows credits."
            if not caller_is_full else
            "Projection at the benchmark price, not a guaranteed payout."
        ),
        "credits_ci90": {"low": farm.get("credits_ci90_low"), "high": farm.get("credits_ci90_high")},
        "formula_version": farm.get("formula_version") or app_config.FORMULA_VERSION,
        "s2_scene": farm.get("s2_scene"),
        "monitoring": monitoring,
        "trust": {
            "evidence_quality": quality["score"],
            "uncertainty_pct": credit_engine.uncertainty_pct(quality["score"]),
            "components": quality["components"],
            "evidence": public_evidence,
            "evidence_access": "full" if caller_is_full else "presence_only",
            "verification_hash": verification_hash,
        },
        "ledger": chain,
    }


def _wallet_rows(phone: str) -> tuple[dict, list[dict]]:
    if not db.is_ready():
        from app import sample_data
        profile = sample_data.FARMERS.get(phone) or {}
        rows = [r for r in market_store.all_rows() if r.get("farmer_phone") == phone]
        return profile, rows
    sb = db._client()
    profile = db.get_profile(phone) or {}
    rows = (sb.table("marketplace_listings").select("*").eq("farmer_phone", phone).execute().data) or []
    return profile, rows


def _wallet_view(phone: str) -> dict:
    profile, rows = _wallet_rows(phone)
    active = [r for r in rows if str(r.get("status")).lower() in ("active", "partially sold", "partially_sold")]
    all_statements = []
    transactions = []
    legacy_sales = []

    for r in sorted(rows, key=lambda x: x.get("updated_at") or x.get("created_at") or "", reverse=True):
        farm_id = r.get("farm_id") or ""
        listing_id = r.get("id")
        chain = ledger.get_chain(farm_id) if farm_id else []
        statements = payouts.settlement_statements(chain, listing_id)
        if statements:
            all_statements.extend(statements)
            for s in statements:
                transactions.append({
                    "date": str(s.get("sale_at") or r.get("updated_at") or r.get("created_at") or "")[:10],
                    "tx_id": s.get("escrow_ref"),
                    "escrow_ref": s.get("escrow_ref"),
                    "certificate_id": s.get("certificate_id"),
                    "source": f"Marketplace sale ({r.get('crop') or 'Mixed Crop'})",
                    "listing_id": listing_id,
                    "farm_id": farm_id,
                    "credits_sold": s.get("credits_sold"),
                    "rate": s.get("unit_price") or None,
                    "gross": s.get("net_gross_inr"),
                    "farmer_share": round(s["farmer_inr"] - s["refund_farmer_inr"], 2),
                    "fpo_share": round(s["fpo_inr"] - s["refund_fpo_inr"], 2),
                    "platform_share": round(s["platform_inr"] - s["refund_platform_inr"], 2),
                    "split_model": s.get("split_model"),
                    "ledger_hash": s.get("ledger_hash"),
                    "status": (
                        "FAILED_RECONCILIATION" if s.get("failed") else
                        ("REFUNDED" if s.get("refunded") else "SETTLED")
                    ),
                    "payout_status": s.get("payout_status"),
                    "reconciled": not s.get("issues"),
                    "issues": s.get("issues") or [],
                    "farmer_floor_met": s.get("farmer_floor_met"),
                    "refund_ref": s.get("refund_ref"),
                })
            continue

        # Legacy row with no SALE/SPLIT events. This is an estimate, clearly
        # labelled; it is NOT presented as a final payout record.
        if str(r.get("status")).lower() in ("sold", "retired") or float(r.get("current_bid") or 0) > 0:
            gross = float(r.get("current_bid") or 0) or (
                float(r.get("total_credits") or 0) * float(r.get("price_per_credit") or 0)
            )
            farm = db.get_farm(farm_id) if farm_id and db.is_ready() else None
            fpo_name = _resolve_fpo_link(farm, r.get("farmer_phone") or phone)
            split = split_engine.compute_split(gross, fpo_involved=bool(fpo_name), fpo_name=fpo_name)
            legacy_sales.append((r, gross, split))
            transactions.append({
                "date": (r.get("updated_at") or r.get("created_at") or "")[:10],
                "tx_id": r.get("tx_hash") or f"TXN-{(listing_id or '')[:6].upper()}",
                "escrow_ref": None,
                "certificate_id": credit_lifecycle.certificate_id_for_sale(listing_id or "", 1),
                "source": f"Marketplace sale ({r.get('crop') or 'Mixed Crop'})",
                "listing_id": listing_id,
                "farm_id": farm_id,
                "credits_sold": r.get("total_credits"),
                "rate": float(r.get("price_per_credit") or 0) or None,
                "gross": round(gross, 2),
                "farmer_share": split["farmer_amount_inr"],
                "fpo_share": split["fpo_amount_inr"],
                "platform_share": split["platform_amount_inr"],
                "split_model": split["model"],
                "ledger_hash": None,
                "status": "LEGACY_ESTIMATE",
                "payout_status": "legacy_recomputed_estimate",
                "reconciled": False,
                "issues": ["no_sale_event_in_ledger"],
                "farmer_floor_met": True,
                "refund_ref": None,
            })

    recon = payouts.reconcile(all_statements)
    # Include legacy rows in the gross total, but never call them reconciled.
    legacy_gross = round(sum(g for _, g, _ in legacy_sales), 2)
    legacy_farmer = round(sum(s["farmer_amount_inr"] for _, _, s in legacy_sales), 2)
    legacy_fpo = round(sum(s["fpo_amount_inr"] for _, _, s in legacy_sales), 2)
    legacy_platform = round(sum(s["platform_amount_inr"] for _, _, s in legacy_sales), 2)

    total_earned = round(recon["net_gross_inr"] + legacy_gross, 2)
    farmer_total = round(recon["farmer_inr"] + legacy_farmer, 2)
    fpo_total = round(recon["fpo_inr"] + legacy_fpo, 2)
    platform_total = round(recon["platform_inr"] + legacy_platform, 2)
    escrow_pending = round(sum(
        float(r.get("total_credits") or 0) * float(r.get("price_per_credit") or 0)
        for r in active
    ), 2)

    return {
        "success": True,
        "total_earned": total_earned,
        "escrow_pending": escrow_pending,
        "withdrawable_upi": farmer_total,
        "farmer_share_total": farmer_total,
        "fpo_share_total": fpo_total,
        "platform_share_total": platform_total,
        "upi_id": profile.get("upi"),
        "demo_mode": not db.is_ready(),
        "transactions": transactions,
        "payout_status": "recorded_simulated_rails",
        "payout_note": (
            "Shares are read from the ledger's SPLIT/REFUND events. UPI/bank "
            "rails are simulated in this pilot; no bank settlement is claimed."
        ),
        "reconciliation": {
            **recon,
            "legacy_rows_included": len(legacy_sales),
            "legacy_gross_inr": legacy_gross,
            "net_total_inr": total_earned,
            "farmer_total_inr": farmer_total,
            "fpo_total_inr": fpo_total,
            "platform_total_inr": platform_total,
            "display_matches_ledger": recon["status"] == "reconciled" and not legacy_sales,
        },
    }


@router.get("/wallet")
def get_wallet_ledger(current_user: dict = Depends(get_current_user)):
    try:
        return _wallet_view(current_user.get("phone") or "")
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.get("/wallet/reconciliation")
def wallet_reconciliation(current_user: dict = Depends(get_current_user)):
    """Machine-checkable proof that displayed shares equal the ledger record."""
    view = _wallet_view(current_user.get("phone") or "")
    return {
        "success": True,
        "reconciliation": view.get("reconciliation"),
        "payout_status": view.get("payout_status"),
        "payout_note": view.get("payout_note"),
        "transactions": [
            {k: t.get(k) for k in (
                "escrow_ref", "certificate_id", "listing_id", "gross",
                "farmer_share", "fpo_share", "platform_share",
                "payout_status", "reconciled", "issues",
            )}
            for t in view.get("transactions", [])
        ],
    }


@router.post("/farms/earnings-calculator")
def earnings_calculator(data: EarningsCalcModel):
    quality = credit_engine.evidence_quality(
        has_photo=data.has_photo, geotag_ok=data.geotag_ok,
        fpo_or_registry=data.fpo_or_registry, ndvi_current=data.ndvi is not None,
        baseline_known=data.baseline_ndvi is not None,
    )
    estimate = credit_engine.estimate_credits(
        area_hectares=data.area_hectares, crop=data.crop or "",
        ndvi=data.ndvi or 0.7, baseline_ndvi=data.baseline_ndvi,
        quality_score=quality["score"],
    )
    income = credit_engine.income_projection(estimate["credits_tco2e"], data.badge or "DOCUMENT")
    return {
        "success": True,
        "estimate": estimate,
        "income": income,
        "evidence_quality": quality,
        "credits_basis": estimate.get("basis", "proxy_estimate"),
        "validation": validation.current_status(),
    }


@router.get("/ledger/{farm_id}")
def get_farm_ledger(farm_id: str, current_user: Optional[dict] = Depends(get_current_user_optional)):
    farm = None
    if db.is_ready():
        farm = db.get_farm(farm_id)
        if not farm:
            return {"success": False, "code": "NOT_FOUND", "message": "Farm not found"}
    chain = ledger.get_chain(farm_id)
    if not chain:
        # Anchor genesis only for a farm that actually exists: a real DB row,
        # or (demo mode) a known fallback listing — never a phantom id.
        if db.is_ready():
            snapshot = {
                "farm": farm.get("name"), "crop": farm.get("crop_type"),
                "ndvi": farm.get("ndvi"), "area_hectares": farm.get("area_hectares"),
                "note": "Genesis anchored from farm evidence snapshot",
            }
            ledger.ensure_genesis(farm_id, snapshot, ts=(farm.get("updated_at") or "") or None)
        else:
            row = next((r for r in market_store.all_rows() if r.get("farm_id") == farm_id), None)
            if row:
                snapshot = {
                    "farm": f"Fallback listing {row.get('id')}", "crop": row.get("crop"),
                    "ndvi": None,
                    "note": "Demo genesis (in-memory fallback listing, DB offline)",
                }
                ledger.ensure_genesis(farm_id, snapshot)
        chain = ledger.get_chain(farm_id)
    verification = ledger.verify_chain(farm_id)
    if db.is_ready() and farm:
        farmer_phone = farm.get("owner_phone")
    else:
        row = next((r for r in market_store.all_rows() if r.get("farm_id") == farm_id), None)
        farmer_phone = (row or {}).get("farmer_phone")
    full_access = bool(
        access_policy.is_staff(current_user)
        or access_policy.is_owner(current_user, farmer_phone)
        or (farm and access_policy.is_fpo_for_farm(current_user, farm))
    )
    return {
        "success": True,
        "farm_id": farm_id,
        "verification": verification,
        "access": "full" if full_access else "public_redacted",
        "redaction_note": (
            None if full_access else
            "Public ledger shows event type, sequence, time, hash and credit quantities. "
            "Buyer/farmer identities, rupee amounts, payout splits and free-text reasons are private."
        ),
        "events": access_policy.ledger_events_for(chain, full_access=full_access),
    }
