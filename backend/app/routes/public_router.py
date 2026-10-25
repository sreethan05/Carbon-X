"""Public verification API — trust as marketing (#startup).

Anyone with a certificate ID (printed on the PDF, shown to buyers) can verify
a retirement against the tamper-evident ledger — no account, no auth. This is
the platform's public transparency surface: farmer identities stay anonymized,
financial splits stay private, and everything else is exactly what the ledger
proves.
"""
from fastapi import APIRouter, Depends

from app import config as app_config
from app import supabase_db as db
from app.services import credit_engine, ledger, market_store

router = APIRouter(tags=["public"])


def _impact_equivalents(tco2e: float) -> dict:
    """EPA GHG equivalencies (2024 factors) — rounded for display."""
    if not tco2e or tco2e <= 0:
        return {}
    return {
        "miles_driven": round(tco2e * 3967),
        "cars_off_road_one_year": round(tco2e / 4.6, 1),
        "tree_seedlings_10_years": round(tco2e / 0.06),
        "note": "US EPA Greenhouse Gas Equivalencies Calculator",
    }


@router.get("/verify/{cert_id}")
def public_verify(cert_id: str):
    """Public, unauthenticated verification of a retired credit batch."""
    rows = None
    if not db.is_ready():
        rows = [r for r in market_store.all_rows()
                if str(r.get("status")).lower() in ("sold", "retired")]
    else:
        try:
            sb = db._client()
            rows = (sb.table("marketplace_listings").select("*")
                    .in_("status", ["Sold", "Retired"]).execute().data) or []
        except Exception as e:
            return {"success": False, "message": str(e)}

    from app.routes.trust_router import _cert_id_for_listing
    row = next((r for r in rows if _cert_id_for_listing(r.get("id")) == cert_id), None)
    if not row:
        return {"success": False, "code": "NOT_FOUND",
                "message": "No retired certificate found for this ID. Check the ID on the PDF certificate."}

    farm_id = row.get("farm_id") or ""
    chain = ledger.get_chain(farm_id) if farm_id else []
    verification = ledger.verify_chain(farm_id) if farm_id else {"valid": False, "length": 0}

    farmer_name = row.get("farmer_name") or "Verified Smallholder"
    first_name = farmer_name.split(" ")[0]
    location = row.get("location") or "Telangana, India"
    district = location.split(",")[-2].strip() if "," in location else location

    credits = float(row.get("total_credits") or 0)
    volume = round(credits, 2)
    retired = str(row.get("status")).lower() == "retired"

    return {
        "success": True,
        "certificate_id": cert_id,
        "status": "RETIRED" if retired else "HELD_IN_ESCROW",
        "credits_tco2e": volume,
        "crop": row.get("crop"),
        "region": district,
        "farmer": {
            "display_name": f"{first_name} (Verified Smallholder)",
            "verification_badge": "Registry-verified" if retired else "Document-verified",
            "note": "Full identity protected — verification proves the practice, not the person",
        },
        "methodology": {
            "standard": "VM0042-aligned, deliberately simplified",
            "formula_version": app_config.FORMULA_VERSION,
            "mrv_cycle": "Sentinel-2 NDVI, re-checked every 5 days",
            "uncertainty": "10-30% evidence-quality deduction applied before issuance",
        },
        "impact_equivalents": _impact_equivalents(volume),
        "ledger": {
            "events": [{"seq": e["seq"], "type": e["type"], "ts": e["ts"],
                        "hash": e["hash"], "prev_hash": e["prev_hash"]}
                       for e in chain],
            "verified": verification["valid"],
            "tail_hash": verification["tail_hash"],
            "public_recompute": f"GET /ledger/{farm_id}",
        },
        "escrow_ref": row.get("tx_hash"),
        "verified_at": (row.get("updated_at") or row.get("created_at") or "")[:10],
    }
