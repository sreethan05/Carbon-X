"""Payout reconciliation from the hash ledger.

The ledger's SPLIT event is the final record of how a sale was divided. The
wallet/UI must display *that* record, not recompute and hope the split model
has not changed. This module turns SALE/SPLIT/REFUND events into per-sale
statements and checks the invariants:

- gross = sum(farmer, fpo, platform) within one paise;
- farmer amount is at least the 70% floor;
- every SALE has a SPLIT;
- every refund reverses at most the original sale and carries split reversals;
- certificate ids are unique per sale.
"""
from __future__ import annotations

from typing import Iterable, Optional

FARMER_FLOOR = 0.70
ONE_PAISE = 0.01


def _f(value, default=0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def group_events(chain: Iterable[dict], listing_id: Optional[str] = None) -> dict[str, dict]:
    """Group ledger events by escrow reference (the settlement key)."""
    grouped: dict[str, dict] = {}
    for event in chain or []:
        etype = event.get("type")
        if etype not in ("SALE", "SPLIT", "RETIRE", "REFUND", "SALE_FAILED",
                         "DISPUTE", "DISPUTE_RESOLVED"):
            continue
        payload = event.get("payload") or {}
        ref = str(payload.get("escrow_ref") or payload.get("dispute_id") or "")
        if not ref:
            continue
        if listing_id is not None and str(payload.get("listing_id") or "") != str(listing_id):
            # RETIRE events created by the legacy/manual path may omit listing_id.
            if etype in ("SALE", "SPLIT", "REFUND", "SALE_FAILED") or payload.get("listing_id"):
                continue
        bucket = grouped.setdefault(ref, {})
        bucket.setdefault(etype, []).append(event)
    return grouped


def settlement_statements(
    chain: Iterable[dict],
    listing_id: Optional[str] = None,
) -> list[dict]:
    statements = []
    for ref, bucket in group_events(chain, listing_id).items():
        sales = bucket.get("SALE") or []
        if not sales:
            continue
        sale = sales[0]
        sp = sale.get("payload") or {}
        split_event = (bucket.get("SPLIT") or [{}])[0]
        sp_split = split_event.get("payload") or {}
        retire = (bucket.get("RETIRE") or [{}])[0]
        refund_event = (bucket.get("REFUND") or [None])[-1]
        refund_payload = (refund_event or {}).get("payload") or {}
        failed = bool(bucket.get("SALE_FAILED"))
        gross = round(_f(sp.get("gross_inr")), 2)
        farmer = round(_f(sp_split.get("farmer_inr")), 2)
        fpo = round(_f(sp_split.get("fpo_inr")), 2)
        platform = round(_f(sp_split.get("platform_inr")), 2)
        split_sum = round(farmer + fpo + platform, 2)
        floor = round(gross * FARMER_FLOOR, 2)
        refunded = bool(refund_event)
        refund_credits = _f(refund_payload.get("credits")) if refunded else 0.0
        statement = {
            "escrow_ref": ref,
            "listing_id": sp.get("listing_id"),
            "certificate_id": sp.get("certificate_id"),
            "sale_seq": sp.get("sale_seq"),
            "buyer": sp.get("buyer"),
            "credits_sold": round(_f(sp.get("credits")), 4),
            "unit_price": _f(sp.get("unit_price")),
            "gross_inr": gross,
            "farmer_inr": farmer,
            "fpo_inr": fpo,
            "platform_inr": platform,
            "split_model": sp_split.get("model"),
            "split_sum_inr": split_sum,
            "farmer_share_pct": round(farmer / gross * 100, 2) if gross else 0.0,
            "farmer_floor_inr": floor,
            "farmer_floor_met": bool(gross > 0 and farmer + ONE_PAISE >= floor),
            "has_split": bool(split_event),
            "retired": bool(retire) or refunded,
            "refunded": refunded,
            "refund_credits": round(refund_credits, 4) if refunded else 0.0,
            "refund_ref": refund_payload.get("refund_ref") if refunded else None,
            "refund_farmer_inr": round(_f(refund_payload.get("farmer_inr")), 2) if refunded else 0.0,
            "refund_fpo_inr": round(_f(refund_payload.get("fpo_inr")), 2) if refunded else 0.0,
            "refund_platform_inr": round(_f(refund_payload.get("platform_inr")), 2) if refunded else 0.0,
            "net_gross_inr": round(gross - _f(refund_payload.get("gross_inr")), 2) if refunded else gross,
            "failed": failed,
            "payout_status": (
                "failed_reconciliation" if failed else
                ("refunded" if refunded else "recorded_simulated_rails")
            ),
            "ledger_hash": sale.get("hash"),
            "sale_at": sale.get("ts"),
            "refunded_at": refund_event.get("ts") if refunded else None,
        }
        statement["issues"] = _statement_issues(statement)
        statements.append(statement)
    statements.sort(key=lambda s: s.get("sale_at") or "")
    return statements


def _statement_issues(s: dict) -> list[str]:
    issues = []
    if s["gross_inr"] <= 0:
        issues.append("gross_not_positive")
    if not s["has_split"]:
        issues.append("missing_split")
    if s["has_split"] and abs(s["split_sum_inr"] - s["gross_inr"]) > ONE_PAISE:
        issues.append("split_does_not_equal_gross")
    if s["gross_inr"] > 0 and not s["farmer_floor_met"]:
        issues.append("farmer_below_70pct_floor")
    if s["refunded"] and s["refund_credits"] > s["credits_sold"] + 1e-9:
        issues.append("refund_exceeds_sale_credits")
    if s["refunded"]:
        reversal = s["refund_farmer_inr"] + s["refund_fpo_inr"] + s["refund_platform_inr"]
        if reversal > s["gross_inr"] + ONE_PAISE:
            issues.append("refund_split_exceeds_gross")
    if s.get("failed"):
        issues.append("sale_failed_reconciliation")
    return issues


def reconcile(statements: Iterable[dict]) -> dict:
    statements = list(statements or [])
    issues = []
    cert_ids = []
    for s in statements:
        cert_ids.append(s.get("certificate_id"))
        for issue in s.get("issues") or []:
            issues.append({
                "escrow_ref": s.get("escrow_ref"),
                "certificate_id": s.get("certificate_id"),
                "issue": issue,
            })
    seen = set()
    duplicates = []
    for cert in cert_ids:
        if not cert:
            continue
        if cert in seen:
            duplicates.append(cert)
        seen.add(cert)
    for cert in sorted(set(duplicates)):
        issues.append({"certificate_id": cert, "issue": "duplicate_certificate_id"})
    counted = [s for s in statements if not s.get("failed")]
    return {
        "status": "reconciled" if not issues else "issues_found",
        "settlements": len(statements),
        "counted_settlements": len(counted),
        "failed_settlements": len(statements) - len(counted),
        "gross_inr": round(sum(s["gross_inr"] for s in counted), 2),
        "net_gross_inr": round(sum(s["net_gross_inr"] for s in counted), 2),
        "farmer_inr": round(sum(s["farmer_inr"] - s["refund_farmer_inr"] for s in counted), 2),
        "fpo_inr": round(sum(s["fpo_inr"] - s["refund_fpo_inr"] for s in counted), 2),
        "platform_inr": round(sum(s["platform_inr"] - s["refund_platform_inr"] for s in counted), 2),
        "refunded_inr": round(sum(
            s["refund_farmer_inr"] + s["refund_fpo_inr"] + s["refund_platform_inr"]
            for s in counted
        ), 2),
        "issues": issues,
        "payout_status": "recorded_simulated_rails",
        "note": (
            "Amounts are the ledger's final SPLIT/REFUND records. The payment "
            "rails are simulated in this pilot; bank/UPI settlement is not claimed."
        ),
    }
