"""Consent, access/export, correction and erasure controls (DPDP-aligned).

Design rules:

- Consent is purpose-specific and versioned.  Withdrawal is a new record, not
  a destructive update, so the platform can prove what was agreed when.
- Data export is a single JSON archive of the farmer's own operational data.
  Third-party personal data (buyer contact details) is redacted.
- Erasure is *blocked* while credits are still on sale or a dispute is open.
  When allowed, the profile is scrubbed in place into an inactive tombstone
  (phone retained only as an account-lock/FK anchor) and farm boundaries,
  names, UPI/Aadhaar suffix and evidence are erased.  Financial/ledger
  integrity survives.
- The immutable hash ledger can contain historical free-text farm/crop names.
  That residual is disclosed in the privacy notice and DR runbook; the chain
  is never silently rewritten.
"""
from __future__ import annotations

import hashlib
import re
import secrets
import threading
import uuid
from datetime import datetime, timezone
from typing import Optional

from app import supabase_db as db

POLICY_VERSION = "2026-10-22"
DATA_CONTROLLER = "CarbonX"
CONTACT = "privacy@carbonx.example"

PURPOSES = {
    "platform_service": {
        "label": "Create and operate my CarbonX account",
        "required": True,
        "description": "Phone OTP login, farm records, MRV passport and support.",
    },
    "mrv_evidence": {
        "label": "Process farm photos, geotags and field evidence",
        "required": False,
        "description": "Used to verify practices and reduce estimate uncertainty.",
    },
    "payouts": {
        "label": "Process payouts and share transaction records",
        "required": False,
        "description": "Needed to pay farmers/FPOs and satisfy financial audit duties.",
    },
    "public_passport": {
        "label": "Show a public farm passport and certificate",
        "required": False,
        "description": (
            "Shows district/village-level information and aggregate credits. "
            "Exact coordinates and contact details stay private by default."
        ),
    },
    "research": {
        "label": "Use de-identified data for methodology research",
        "required": False,
        "description": "Only aggregated or de-identified data; never public farm locations.",
    },
    "marketing": {
        "label": "Send marketing messages",
        "required": False,
        "description": "Optional and never bundled with service access.",
    },
}

RETENTION = [
    {
        "data": "Account profile (name, phone, location, UPI, Aadhaar last-4)",
        "period": "While the account is active; erased/anonymised after a verified deletion request.",
        "basis": "Consent + contract",
    },
    {
        "data": "Farm boundaries and satellite/MRV records",
        "period": (
            "While credits are active and for 8 years after the last sale for "
            "audit and dispute resolution; then anonymised or deleted."
        ),
        "basis": "Contract, legitimate audit, legal claims",
    },
    {
        "data": "KYC hashes and verification outcome",
        "period": "8 years after the last transaction (financial audit). Aadhaar images are never stored.",
        "basis": "Legal obligation / fraud prevention",
    },
    {
        "data": "Practice photos and geotags",
        "period": "While the farm is enrolled; deleted on erasure unless a sale/dispute requires retention.",
        "basis": "Consent",
    },
    {
        "data": "Consent and privacy-request records",
        "period": "8 years after the request is closed (proof of compliance).",
        "basis": "Legal obligation",
    },
    {
        "data": "Immutable ledger events (hashes + event payloads)",
        "period": (
            "Retained for audit integrity. Historical free-text payloads may "
            "contain farm/crop names; new payloads exclude phone numbers and "
            "third-party buyer details."
        ),
        "basis": "Audit integrity / legal claims",
    },
    {
        "data": "OTP codes",
        "period": "10 minutes (Redis TTL), 5 attempts; never written to the database.",
        "basis": "Security",
    },
]

_MEMORY_LOCK = threading.RLock()
_MEMORY_CONSENTS: list[dict] = []
_MEMORY_REQUESTS: list[dict] = []
_MEMORY_DELETED: set[str] = set()


def reset_memory() -> None:
    with _MEMORY_LOCK:
        _MEMORY_CONSENTS.clear()
        _MEMORY_REQUESTS.clear()
        _MEMORY_DELETED.clear()


def policy() -> dict:
    return {
        "policy_version": POLICY_VERSION,
        "controller": DATA_CONTROLLER,
        "contact": CONTACT,
        "purposes": PURPOSES,
        "retention": RETENTION,
        "rights": {
            "consent": "Grant or withdraw each optional purpose at any time.",
            "access_export": "Download a JSON archive of your operational data.",
            "correction": "Request a correction; staff review before it is applied.",
            "erasure": (
                "Request deletion. Active listings and open disputes must be "
                "closed first so credits and payouts stay consistent."
            ),
            "grievance": f"Contact {CONTACT}; we acknowledge within 7 days.",
        },
        "aadhaar": {
            "stored": "Last 4 digits only; never the full number or image.",
            "purpose": "Identity matching for land/KYC verification.",
            "masking": "API and UI always mask the first 8 digits.",
        },
        "legal_note": (
            "This notice is an operational draft aligned to India's DPDP Act "
            "2023. It requires review by qualified privacy counsel before a "
            "production launch; see docs/PRIVACY_DPIA.md."
        ),
    }


def normalize_phone(phone: str) -> str:
    return re.sub(r"\D", "", str(phone or ""))[-10:]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _db_ready() -> bool:
    return db.is_ready()


def record_consent(
    phone: str,
    purpose: str,
    granted: bool,
    *,
    policy_version: str = POLICY_VERSION,
    language: str = "en",
    method: str = "app_checkbox",
    evidence: Optional[dict] = None,
) -> dict:
    phone = normalize_phone(phone)
    if purpose not in PURPOSES:
        raise ValueError(f"Unknown consent purpose: {purpose}")
    if not phone:
        raise ValueError("phone is required")
    row = {
        "id": str(uuid.uuid4()),
        "phone": phone,
        "purpose": purpose,
        "policy_version": policy_version,
        "granted": bool(granted),
        "language": (language or "en")[:16],
        "method": (method or "app_checkbox")[:64],
        "evidence": evidence or {},
        "captured_at": _now(),
    }
    if _db_ready():
        try:
            res = db._client().table("consent_records").insert(row).execute()
            return (res.data or [row])[0]
        except Exception as e:
            print(f"[privacy] consent DB insert failed ({e}); using memory")
    with _MEMORY_LOCK:
        _MEMORY_CONSENTS.append(row)
    return dict(row)


def list_consents(phone: str) -> list[dict]:
    phone = normalize_phone(phone)
    rows: list[dict] = []
    if _db_ready():
        try:
            rows = (
                db._client().table("consent_records").select("*")
                .eq("phone", phone).order("captured_at", desc=True).execute().data
            ) or []
        except Exception as e:
            print(f"[privacy] consent DB read failed ({e}); using memory")
    with _MEMORY_LOCK:
        rows = rows + [dict(r) for r in _MEMORY_CONSENTS if r.get("phone") == phone]
    rows.sort(key=lambda r: r.get("captured_at") or "", reverse=True)
    return rows


def current_consents(phone: str) -> dict[str, dict]:
    """Latest decision per purpose (plus a default for required purposes)."""
    latest: dict[str, dict] = {}
    for row in list_consents(phone):
        if row.get("purpose") not in latest:
            latest[row["purpose"]] = row
    for purpose, meta in PURPOSES.items():
        if purpose not in latest:
            latest[purpose] = {
                "purpose": purpose,
                "granted": bool(meta.get("required")),
                "default": True,
                "policy_version": POLICY_VERSION,
                "captured_at": None,
            }
    return latest


def _save_request(phone: str, request_type: str, status: str, details: dict,
                  resolution_note: Optional[str] = None) -> dict:
    row = {
        "id": str(uuid.uuid4()),
        "phone": phone,
        "request_type": request_type,
        "status": status,
        "details": details,
        "resolution_note": resolution_note,
        "created_at": _now(),
        "resolved_at": _now() if status in ("completed", "rejected") else None,
    }
    if _db_ready():
        try:
            res = db._client().table("privacy_requests").insert(row).execute()
            return (res.data or [row])[0]
        except Exception as e:
            print(f"[privacy] request DB insert failed ({e}); using memory")
    with _MEMORY_LOCK:
        _MEMORY_REQUESTS.append(row)
    return dict(row)


def list_requests(phone: str, request_type: Optional[str] = None) -> list[dict]:
    phone = normalize_phone(phone)
    rows: list[dict] = []
    if _db_ready():
        try:
            q = db._client().table("privacy_requests").select("*").eq("phone", phone)
            if request_type:
                q = q.eq("request_type", request_type)
            rows = (q.order("created_at", desc=True).execute().data) or []
        except Exception as e:
            print(f"[privacy] request DB read failed ({e}); using memory")
    with _MEMORY_LOCK:
        rows = rows + [
            dict(r) for r in _MEMORY_REQUESTS
            if r.get("phone") == phone
            and (not request_type or r.get("request_type") == request_type)
        ]
    rows.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    return rows


def deletion_blockers(phone: str, listings: list[dict]) -> list[dict]:
    phone = normalize_phone(phone)
    blockers = []
    for row in listings or []:
        if str(row.get("farmer_phone") or "") != phone:
            continue
        status = str(row.get("status") or "").lower()
        remaining = float(row.get("total_credits") or 0)
        dispute = str(row.get("dispute_status") or "NONE").upper()
        if status in ("active", "partially sold", "partially_sold") and remaining > 0:
            blockers.append({
                "type": "active_listing",
                "listing_id": row.get("id"),
                "message": (
                    f"Listing {row.get('id')} still has {remaining:g} credits for sale. "
                    "Delist or sell them before deleting the account."
                ),
            })
        if dispute not in ("NONE", "RESOLVED", "REJECTED"):
            blockers.append({
                "type": "open_dispute",
                "listing_id": row.get("id"),
                "message": (
                    f"Listing {row.get('id')} has an open dispute ({dispute}). "
                    "Wait for the dispute decision before deleting the account."
                ),
            })
    return blockers


def tombstone_phone(original_phone: str) -> str:
    seed = f"{normalize_phone(original_phone)}:{secrets.token_hex(16)}"
    return "deleted-" + hashlib.sha256(seed.encode()).hexdigest()[:24]


def _update_where(table: str, match_column: str, match_value: str, fields: dict) -> int:
    """Best-effort bulk update; returns affected row count (0 if unavailable)."""
    sb = db._client()
    if not sb:
        return 0
    try:
        res = sb.table(table).update(fields).eq(match_column, match_value).execute()
        return len(res.data or [])
    except Exception as e:
        print(f"[privacy] update {table} failed: {e}")
        return 0


def _delete_memory_evidence(farm_ids: list[str]) -> int:
    """Remove evidence photo files for the farmer's farms."""
    import os
    import shutil
    from app.services import evidence_service
    root = evidence_service.evidence_dir()
    deleted = 0
    for farm_id in farm_ids:
        safe = evidence_service.sanitize_farm_id(farm_id)
        if not safe:
            continue
        path = os.path.join(str(root), safe)
        if os.path.isdir(path):
            try:
                shutil.rmtree(path)
                deleted += 1
            except OSError as e:
                print(f"[privacy] could not remove evidence dir {path}: {e}")
    return deleted


def _db_anonymize(phone: str, profile: dict, farms: list[dict], listings: list[dict]) -> dict:
    """Scrub the profile in place into an inactive tombstone.

    The phone number is retained *only* as an account-lock and foreign-key
    anchor; name, UPI, Aadhaar suffix, wallet address, village and farm
    boundary are erased.  This is disclosed in the privacy notice because a
    phone number is still personal data, and the alternative (deleting the row)
    would cascade-delete ledger-linked farms and KYC history.
    """
    sb = db._client()
    now = _now()
    scrubbed_profile = {
        "name": "Deleted User",
        "role": "farmer",
        "fpo_id": None,
        "state": "",
        "district": "",
        "village": "",
        "upi": "",
        "wallet_address": "",
        "aadhaar_last4": "",
        "preferred_language": "en",
        "is_active": False,
        "deletion_requested_at": now,
        "anonymized_at": now,
        "deleted_at": now,
        "consent_version": POLICY_VERSION,
    }
    try:
        sb.table("profiles").update(scrubbed_profile).eq("phone", phone).execute()
    except Exception as e:
        return {"success": False, "message": f"Could not anonymise the profile: {e}"}

    updated = {}
    updated["farms"] = _update_where(
        "farms", "owner_phone", phone,
        {"name": "Anonymized farm", "geojson": None, "deleted_at": now},
    )
    updated["listings"] = _update_where(
        "marketplace_listings", "farmer_phone", phone,
        {"farmer_name": "Anonymized farmer", "location": "Telangana, India"},
    )
    updated["kyc"] = _update_where(
        "kyc_verifications", "owner_phone", phone,
        {
            "document_name": "deleted",
            "document_sha256": None,
            "perceptual_hash": None,
            "checks": {},
            "extracted_fields": {},
            "reasons": {},
            "document_deleted_at": now,
        },
    )
    try:
        updated["fpo_members"] = _update_where(
            "fpo_members", "farmer_phone", phone, {"status": "removed"},
        )
    except Exception:
        updated["fpo_members"] = 0
    _update_where(
        "farm_evidence", "created_by", phone,
        {"created_by": "deleted-account", "deleted_at": now},
    )

    farm_ids = [str(f.get("id")) for f in farms or [] if f.get("id")]
    files_removed = _delete_memory_evidence(farm_ids)

    return {
        "success": True,
        "mode": "database",
        "original_phone_erased": False,
        "phone_retained_as_account_lock": True,
        "reassigned": updated,
        "records_updated": updated,
        "evidence_directories_removed": files_removed,
        "retained": (
            "The phone number is retained only as an inactive account lock and "
            "foreign-key anchor. Name, UPI, Aadhaar last-4, wallet address, "
            "village and farm boundary were erased. Financial/ledger hashes are "
            "retained for audit; the number cannot be used to log in."
        ),
        "ledger_residual_note": (
            "Immutable historical ledger payloads may still contain the farm "
            "name/crop recorded before erasure; they are not rewritten."
        ),
    }


def anonymize(phone: str, profile: dict, farms: list[dict], listings: list[dict]) -> dict:
    phone = normalize_phone(phone)
    blockers = deletion_blockers(phone, listings)
    if blockers:
        request = _save_request(
            phone, "deletion", "blocked", {"blockers": blockers}
        )
        return {
            "success": False,
            "code": "DELETION_BLOCKED",
            "message": "Close active listings and disputes before deleting the account.",
            "blockers": blockers,
            "request": request,
        }
    if not _db_ready():
        # Demo/offline mode: never mutate the shared sample fixtures. A
        # synthetic non-fixture phone can be tombstoned in-process.
        with _MEMORY_LOCK:
            _MEMORY_DELETED.add(phone)
        request = _save_request(phone, "deletion", "completed", {"mode": "memory"})
        return {
            "success": True,
            "mode": "memory",
            "message": (
                "Demo/offline mode: the account was marked deleted in this "
                "process only. No live database was changed."
            ),
            "request": request,
        }
    result = _db_anonymize(phone, profile, farms, listings)
    if result.get("success"):
        with _MEMORY_LOCK:
            _MEMORY_DELETED.add(phone)
        result["request"] = _save_request(phone, "deletion", "completed", result)
    return result


def deleted_in_session(phone: str) -> bool:
    """True when this process has completed an erasure (covers demo mode)."""
    with _MEMORY_LOCK:
        return normalize_phone(phone) in _MEMORY_DELETED


def is_deleted(phone: str) -> bool:
    with _MEMORY_LOCK:
        if normalize_phone(phone) in _MEMORY_DELETED:
            return True
    if _db_ready():
        profile = db.get_profile(phone)
        if profile and (profile.get("deleted_at") or profile.get("anonymized_at")):
            return True
        if profile is None:
            return True
    return False


def submit_correction(phone: str, field: str, current_value, requested_value,
                      reason: str = "", evidence_url: str = "") -> dict:
    phone = normalize_phone(phone)
    allowed = {"name", "state", "district", "village", "preferred_language", "upi"}
    if field not in allowed:
        raise ValueError(
            "Corrections are accepted for: " + ", ".join(sorted(allowed))
            + ". Aadhaar changes require a fresh KYC verification."
        )
    details = {
        "field": field,
        "current_value": current_value,
        "requested_value": requested_value,
        "reason": (reason or "")[:1000],
        "evidence_url": (evidence_url or "")[:1000],
    }
    return _save_request(phone, "correction", "in_review", details)


def resolve_correction(request_id: str, decision: str, note: str,
                       resolved_by: str = "") -> dict:
    """Apply or reject a correction request (staff only)."""
    if decision not in ("applied", "rejected"):
        raise ValueError("decision must be 'applied' or 'rejected'")
    sb = db._client()
    row = None
    if sb:
        try:
            res = sb.table("privacy_requests").select("*").eq("id", request_id).limit(1).execute()
            row = (res.data or [None])[0]
        except Exception as e:
            print(f"[privacy] correction read failed: {e}")
    if row is None:
        with _MEMORY_LOCK:
            row = next((r for r in _MEMORY_REQUESTS if r.get("id") == request_id), None)
    if not row:
        raise LookupError("Correction request not found")
    if row.get("request_type") != "correction":
        raise ValueError("Request is not a correction")

    applied = False
    if decision == "applied":
        details = row.get("details") or {}
        field = details.get("field")
        if field in {"name", "state", "district", "village", "preferred_language", "upi"}:
            updated = db.update_profile(row["phone"], {field: details.get("requested_value")})
            applied = updated is not None
            if not applied and not _db_ready():
                applied = True

    status = "completed" if decision == "applied" else "rejected"
    update = {
        "status": status,
        "resolution_note": f"{note} (by {resolved_by or 'staff'})"[:2000],
        "resolved_at": _now(),
    }
    if sb:
        try:
            sb.table("privacy_requests").update(update).eq("id", request_id).execute()
        except Exception as e:
            print(f"[privacy] correction update failed: {e}")
    with _MEMORY_LOCK:
        for r in _MEMORY_REQUESTS:
            if r.get("id") == request_id:
                r.update(update)
    return {"success": True, "applied": applied, "request": {**row, **update}}


def redact_third_party(value: Optional[str]) -> Optional[str]:
    """Buyer names are third-party data in a farmer's export."""
    if not value:
        return None
    if re.search(r"(corp|company|ltd|limited|pvt|llp|bank|fund)", str(value), re.I):
        return str(value)
    return "Third-party buyer (redacted)"
