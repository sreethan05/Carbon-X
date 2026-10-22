"""Deterministic credit lifecycle: issue → list → sale → retire → refund.

The marketplace row is an operational balance; the hash ledger is the
immutable event history. This module derives certificates and lifecycle state
from the ledger so that:

- every sale gets its own unique certificate id (partial sales of one listing
  no longer share/collide on a certificate id);
- a refund restores the listing balance and is visible as an explicit REFUND
  event rather than deleting history;
- a dispute freezes a listing without corrupting sold/remaining balances;
- the same derivation feeds the JSON API, PDF, CSV and UI.

State model (listing ``status`` remains the marketplace-facing field for
backwards compatibility; ``lifecycle_state`` carries the richer state):

    Active ──partial sale──> Active (lifecycle_state=Partially Sold)
      │                         │
      └────full sale───────────┴──> Retired
      │                              │
      ├──dispute──> Active/Retired + dispute_status=OPEN
      │                              │
      └──refund──> Active (credits restored) + certificate REFUNDED
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Callable, Iterable, Optional

CERT_PREFIX = "CX"
LIFECYCLE_STATES = (
    "Active",
    "Partially Sold",
    "Retired",
    "Disputed",
    "Refund Pending",
    "Refunded",
    "Cancelled",
    "Expired",
)

# Allowed lifecycle transitions. ``Retired`` intentionally cannot become
# ``Sold``: a retired credit is not re-sellable except through an explicit
# refund that restores the balance and is recorded in the ledger.
TRANSITIONS = {
    "Active": {"Partially Sold", "Retired", "Disputed", "Cancelled", "Expired"},
    "Partially Sold": {"Active", "Partially Sold", "Retired", "Disputed", "Expired"},
    "Disputed": {"Active", "Partially Sold", "Retired", "Refund Pending", "Refunded"},
    "Refund Pending": {"Refunded", "Disputed"},
    "Retired": {"Disputed", "Refund Pending", "Refunded"},
    "Refunded": {"Active"},
    "Cancelled": set(),
    "Expired": set(),
}


def assert_transition(current: str, next_state: str) -> None:
    current = current or "Active"
    if next_state not in LIFECYCLE_STATES:
        raise ValueError(f"Unknown lifecycle state: {next_state}")
    if next_state == current:
        return
    if next_state not in TRANSITIONS.get(current, set()):
        raise ValueError(f"Invalid lifecycle transition: {current} -> {next_state}")


def certificate_id_for_sale(listing_id: str, sale_index: int) -> str:
    """Unique certificate id per sale.

    The first sale keeps the historical id (so existing links keep working);
    later partial sales append a two-digit sequence. Together with the
    per-listing settlement lock this is collision-free, and the id is also
    recorded inside the SALE ledger payload for independent derivation.
    """
    lid = str(listing_id or "").replace("-", "")[:8].upper() or "UNKNOWN"
    year = datetime.now(timezone.utc).year
    base = f"{CERT_PREFIX}-{year}-CERT-{lid}"
    return base if int(sale_index or 1) <= 1 else f"{base}-{int(sale_index):02d}"


def sale_index_from_chain(chain: Iterable[dict], listing_id: str) -> int:
    count = 0
    for event in chain or []:
        if event.get("type") != "SALE":
            continue
        payload = event.get("payload") or {}
        if str(payload.get("listing_id") or "") == str(listing_id):
            count += 1
    return count


def _event_map(chain: Iterable[dict]) -> dict[str, dict]:
    """Group events by escrow_ref; keep the first SALE/SPLIT/RETIRE/REFUND."""
    grouped: dict[str, dict] = {}
    for event in chain or []:
        etype = event.get("type")
        if etype not in ("SALE", "SPLIT", "RETIRE", "REFUND", "DISPUTE", "DISPUTE_RESOLVED", "CORRECTION"):
            continue
        payload = event.get("payload") or {}
        ref = str(payload.get("escrow_ref") or payload.get("dispute_id") or "")
        if not ref:
            continue
        bucket = grouped.setdefault(ref, {})
        bucket.setdefault(etype, []).append(event)
    return grouped


def derive_certificates(
    listing_rows: Iterable[dict],
    chain_lookup: Callable[[str], list],
) -> list[dict]:
    """Build one certificate record per SALE event (plus legacy fallbacks)."""
    certificates: list[dict] = []
    for row in listing_rows or []:
        listing_id = row.get("id")
        if not listing_id:
            continue
        farm_id = row.get("farm_id") or ""
        chain = chain_lookup(farm_id) if farm_id else []
        grouped = _event_map(chain)
        found_sale = False
        for ref, events in grouped.items():
            sales = events.get("SALE") or []
            if not sales:
                continue
            sale = sales[0]
            payload = sale.get("payload") or {}
            if str(payload.get("listing_id") or "") != str(listing_id):
                continue
            found_sale = True
            split = (events.get("SPLIT") or [{}])[0].get("payload") or {}
            retire = (events.get("RETIRE") or [{}])[0]
            refund = (events.get("REFUND") or [None])[-1]
            dispute = (events.get("DISPUTE") or [None])[-1]
            resolved = (events.get("DISPUTE_RESOLVED") or [None])[-1]
            failed = bool(events.get("SALE_FAILED"))
            refunded = bool(refund)
            cert_id = payload.get("certificate_id") or certificate_id_for_sale(
                listing_id, 1
            )
            status = "FAILED" if failed else ("REFUNDED" if refunded else (
                "RETIRED" if (retire or str(row.get("status")).lower() == "retired")
                else "HELD_IN_ESCROW"
            ))
            dispute_status = "NONE"
            if dispute and not resolved:
                dispute_status = "OPEN"
            elif dispute and resolved:
                dispute_status = str(
                    ((resolved.get("payload") or {}).get("decision") or "RESOLVED")
                ).upper()
            cert = {
                "id": cert_id,
                "listing_id": listing_id,
                "farm_id": farm_id,
                "escrow_ref": ref,
                "sale_seq": payload.get("sale_seq"),
                "farmer_phone": row.get("farmer_phone"),
                "farmer_name": row.get("farmer_name"),
                "issued_to": payload.get("buyer"),
                "buyer": payload.get("buyer"),
                "buyer_c_id": payload.get("buyer_c_id"),
                "crop": row.get("crop"),
                "location": row.get("location"),
                "volume_mt": round(float(payload.get("credits") or 0), 4),
                "value_inr": round(float(payload.get("gross_inr") or 0), 2),
                "unit_price": payload.get("unit_price"),
                "issued_date": str(sale.get("ts") or "")[:10],
                "retired_at": str(retire.get("ts") or "")[:10] if retire else None,
                "status": status,
                "dispute_status": dispute_status,
                "refunded_at": str(refund.get("ts") or "")[:10] if refund else None,
                "refund_ref": (refund.get("payload") or {}).get("refund_ref") if refund else None,
                "requires_reconciliation": failed,
                "settlement_status": "failed" if failed else "settled",
                "split": {
                    "farmer_inr": split.get("farmer_inr"),
                    "fpo_inr": split.get("fpo_inr"),
                    "platform_inr": split.get("platform_inr"),
                    "model": split.get("model"),
                },
                "batch_hash": (retire.get("payload") or {}).get("batch_hash") or (events.get("SPLIT") or [{}])[0].get("hash"),
                "ledger_hash": sale.get("hash"),
                "ledger_verified": None,
                "source": "ledger",
                "on_chain": False,
            }
            applied = []
            for correction in events.get("CORRECTION", []):
                cp = correction.get("payload") or {}
                if str(cp.get("certificate_id") or "") != str(cert_id):
                    continue
                field = cp.get("field")
                if field in ("farmer_name", "location", "crop"):
                    cert[field] = cp.get("new_value")
                    applied.append({
                        "field": field,
                        "old_value": cp.get("old_value"),
                        "new_value": cp.get("new_value"),
                        "at": correction.get("ts"),
                        "hash": correction.get("hash"),
                    })
            cert["corrections_applied"] = applied
            certificates.append(cert)
        if not found_sale and str(row.get("status")).lower() in ("sold", "retired"):
            # Legacy/demo rows with no SALE event still need a verifiable row.
            cert_id = certificate_id_for_sale(listing_id, 1)
            certificates.append({
                "id": cert_id,
                "listing_id": listing_id,
                "farm_id": farm_id,
                "farmer_phone": row.get("farmer_phone"),
                "farmer_name": row.get("farmer_name"),
                "issued_to": None,
                "buyer": None,
                "crop": row.get("crop"),
                "location": row.get("location"),
                "volume_mt": row.get("total_credits"),
                "value_inr": row.get("current_bid"),
                "unit_price": row.get("price_per_credit"),
                "issued_date": str(row.get("updated_at") or row.get("created_at") or "")[:10],
                "retired_at": str(row.get("updated_at") or "")[:10]
                if str(row.get("status")).lower() == "retired" else None,
                "status": "RETIRED" if str(row.get("status")).lower() == "retired" else "HELD_IN_ESCROW",
                "dispute_status": "NONE",
                "refunded_at": None,
                "refund_ref": None,
                "split": {},
                "batch_hash": row.get("tx_hash"),
                "ledger_hash": None,
                "ledger_verified": None,
                "source": "legacy_row",
                "on_chain": False,
            })
    certificates.sort(
        key=lambda c: (c.get("issued_date") or "", c.get("id") or ""), reverse=True
    )
    return certificates


def find_certificate(
    cert_id: str,
    listing_rows: Iterable[dict],
    chain_lookup: Callable[[str], list],
) -> Optional[dict]:
    target = str(cert_id or "").strip().upper()
    for cert in derive_certificates(listing_rows, chain_lookup):
        if str(cert.get("id") or "").upper() == target:
            return cert
    return None


def lifecycle_snapshot(
    listing: dict,
    chain: Iterable[dict],
) -> dict:
    """Issued/sold/remaining/refunded balances plus event timeline."""
    listing_id = listing.get("id")
    remaining = float(listing.get("total_credits") or 0)
    sold = 0.0
    refunded = 0.0
    retired = 0.0
    events = []
    certificates = []
    grouped = _event_map(chain)
    for ref, bucket in grouped.items():
        sales = bucket.get("SALE") or []
        if not sales:
            continue
        payload = sales[0].get("payload") or {}
        if str(payload.get("listing_id") or "") != str(listing_id):
            continue
        if bucket.get("SALE_FAILED"):
            # The balance was restored (or flagged for reconciliation); this
            # sale did not issue a valid certificate.
            continue
        credits = float(payload.get("credits") or 0)
        sold += credits
        if bucket.get("RETIRE"):
            retired += credits
        refund = (bucket.get("REFUND") or [None])[-1]
        if refund:
            refunded += float((refund.get("payload") or {}).get("credits") or credits)
        certificates.append(payload.get("certificate_id"))
        events.append({
            "type": "SALE",
            "at": sales[0].get("ts"),
            "escrow_ref": ref,
            "credits": credits,
            "certificate_id": payload.get("certificate_id"),
        })
        if refund:
            events.append({
                "type": "REFUND",
                "at": refund.get("ts"),
                "escrow_ref": ref,
                "credits": float((refund.get("payload") or {}).get("credits") or credits),
                "certificate_id": payload.get("certificate_id"),
            })
    dispute_status = str(listing.get("dispute_status") or "NONE").upper()
    lifecycle_state = listing.get("lifecycle_state") or (
        "Retired" if str(listing.get("status")).lower() == "retired"
        else ("Partially Sold" if sold - refunded > 0 and remaining > 0 else "Active")
    )
    unique_candidates = [c for c in certificates if c]
    duplicate_ids = len(unique_candidates) != len(set(unique_candidates))
    return {
        "listing_id": listing_id,
        "status": listing.get("status"),
        "lifecycle_state": lifecycle_state,
        "dispute_status": dispute_status,
        "credits_issued": round(remaining + sold - refunded, 4),
        "credits_sold": round(sold - refunded, 4),
        "credits_refunded": round(refunded, 4),
        "credits_remaining": round(remaining, 4),
        "certificates": sorted(set(unique_candidates)),
        "certificate_count": len(set(unique_candidates)),
        "duplicate_certificate_ids": duplicate_ids,
        "events": sorted(events, key=lambda e: e.get("at") or ""),
        "invariants": {
            "remaining_non_negative": remaining >= -1e-9,
            "sold_non_negative": (sold - refunded) >= -1e-9,
            "unique_certificate_ids": not duplicate_ids,
            "retired_equals_sold_less_refunds": abs((sold - refunded) - retired) <= 1e-6
            or lifecycle_state != "Retired",
        },
    }


def refund_reference(cert_id: str, escrow_ref: Optional[str] = None) -> str:
    seed = f"{cert_id}:{escrow_ref or ''}:{datetime.now(timezone.utc).isoformat()}"
    return "REF-" + hashlib.sha256(seed.encode()).hexdigest()[:12].upper()


def certificate_digest(cert: dict) -> str:
    return hashlib.sha256(
        json.dumps(cert, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
