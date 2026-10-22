"""Trust & transparency routes: certificates, wallet, passport, ledger, earnings calculator."""
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from typing import Literal, Optional
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
from app.services import credit_engine, evidence_service, ledger, market_store, split_engine

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


# ─── Endpoints ───

@router.get("/certificates")
def list_certificates():
    rows = None
    if not db.is_ready():
        rows = [r for r in market_store.all_rows() if str(r.get("status")).lower() in ("sold", "retired")]
        rows.sort(key=lambda r: r.get("updated_at") or "", reverse=True)
    else:
        try:
            sb = db._client()
            rows = (sb.table("marketplace_listings").select("*").in_("status", ["Sold", "Retired"]).order("updated_at", desc=True).execute().data) or []
        except Exception as e:
            return {"success": False, "message": str(e), "certificates": []}
    certificates = []
    for r in rows:
        farm_id = r.get("farm_id") or ""
        chain = ledger.summary(farm_id) if farm_id else {}
        sales = _ledger_sales(farm_id, r.get("id"))
        retired = str(r.get("status")).lower() == "retired"
        loc = r.get("location") or "Location not recorded"
        crop_label = f" ({r.get('crop')})" if r.get("crop") else ""
        certificates.append({
            "id": _cert_id_for_listing(r.get("id")),
            "listing_id": r.get("id"),
            "issued_to": sales.get("buyer") or None,
            "farmer_name": r.get("farmer_name"),
            "crop": r.get("crop"),
            "volume_mt": sales["credits"] if sales["found"] else r.get("total_credits"),
            "value_inr": sales["gross_inr"] if sales["found"] else r.get("current_bid"),
            "source_parcels": [f"{loc}{crop_label}"],
            "issued_date": (r.get("updated_at") or r.get("created_at") or "")[:10],
            "retired_at": ((r.get("updated_at") or "")[:10] or None) if retired else None,
            "status": "RETIRED" if retired else "HELD_IN_ESCROW",
            "batch_hash": chain.get("tail_hash"),
            "ledger_verified": chain.get("verified", False),
            "tx_hash": r.get("tx_hash"),
            "on_chain": False,
        })
    return {"success": True, "certificates": certificates}


@router.get("/certificates/{cert_id}")
def get_certificate(cert_id: str):
    rows = None
    if not db.is_ready():
        rows = [r for r in market_store.all_rows() if str(r.get("status")).lower() in ("sold", "retired")]
    else:
        try:
            sb = db._client()
            rows = (sb.table("marketplace_listings").select("*").in_("status", ["Sold", "Retired"]).execute().data) or []
        except Exception as e:
            return {"success": False, "message": str(e)}
    clean_cert_id = str(cert_id).strip().upper()
    row = next((r for r in rows if _cert_id_for_listing(r.get("id")).upper() == clean_cert_id), None)
    if not row:
        raise HTTPException(status_code=404, detail="Certificate not found")
    farm_id = row.get("farm_id") or ""
    chain = ledger.summary(farm_id) if farm_id else {}
    sales = _ledger_sales(farm_id, row.get("id"))
    retired = str(row.get("status")).lower() == "retired"
    loc = row.get("location") or "Location not recorded"
    crop_label = f" ({row.get('crop')})" if row.get("crop") else ""
    return {
        "success": True,
        "certificate": {
            "id": cert_id,
            "listing_id": row.get("id"),
            "issued_to": sales.get("buyer") or None,
            "farmer_name": row.get("farmer_name"),
            "crop": row.get("crop"),
            "volume_mt": sales["credits"] if sales["found"] else row.get("total_credits"),
            "value_inr": sales["gross_inr"] if sales["found"] else row.get("current_bid"),
            "source_parcels": [f"{loc}{crop_label}"],
            "issued_date": (row.get("updated_at") or row.get("created_at") or "")[:10],
            "retired_at": ((row.get("updated_at") or "")[:10] or None) if retired else None,
            "status": "RETIRED" if retired else "HELD_IN_ESCROW",
            "batch_hash": chain.get("tail_hash"),
            "ledger_verified": chain.get("verified", False),
            "tx_hash": row.get("tx_hash"),
            "on_chain": False,
        },
    }


@router.get("/certificates/{cert_id}/pdf")
def download_certificate_pdf(cert_id: str):
    from fastapi.responses import Response
    from app.services.certificate_pdf import render_certificate_pdf, get_cached_certificate_pdf

    cached = get_cached_certificate_pdf(cert_id)
    if cached:
        return Response(
            content=cached,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="CarbonX_Certificate_{cert_id}.pdf"'},
        )

    rows = None
    if not db.is_ready():
        rows = [r for r in market_store.all_rows() if str(r.get("status")).lower() in ("sold", "retired")]
    else:
        try:
            sb = db._client()
            rows = (sb.table("marketplace_listings").select("*").in_("status", ["Sold", "Retired"]).execute().data) or []
        except Exception as e:
            return {"success": False, "message": str(e)}
    clean_cert_id = str(cert_id).strip().upper()
    row = next((r for r in rows if _cert_id_for_listing(r.get("id")).upper() == clean_cert_id), None)
    if not row:
        raise HTTPException(status_code=404, detail="Certificate not found")
    farm_id = row.get("farm_id") or ""
    chain = ledger.summary(farm_id) if farm_id else {}
    sales = _ledger_sales(farm_id, row.get("id"))
    retired = str(row.get("status")).lower() == "retired"
    cert = {
        "id": cert_id, "buyer": sales.get("buyer") or "—",
        "farmer_name": row.get("farmer_name"), "crop": row.get("crop"),
        "volume": sales["credits"] if sales["found"] else row.get("total_credits"),
        "value": sales["gross_inr"] if sales["found"] else row.get("current_bid"),
        "location": row.get("location"),
        "issued_date": (row.get("updated_at") or row.get("created_at") or "")[:10],
        "retired_date": ((row.get("updated_at") or "")[:10] or None) if retired else None,
        "status": "RETIRED" if retired else "HELD_IN_ESCROW",
        "batch_hash": chain.get("tail_hash") or row.get("tx_hash") or "",
    }
    pdf_bytes = render_certificate_pdf(cert)
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="CarbonX_Certificate_{cert_id}.pdf"'},
    )


@router.post("/certificates/{cert_id}/retire")
def retire_certificate(
    cert_id: str,
    scope: Optional[str] = "Scope 1 Neutrality",
    current_user: Optional[dict] = Depends(get_current_user_optional),
):
    """Permanently retire a held certificate.

    Retirement is buyer action in production (live DB requires a signed-in
    account); demo mode stays open so the certificate page works offline.
    """
    if db.is_ready() and not current_user:
        raise HTTPException(
            status_code=401,
            detail="Sign in to retire a certificate",
        )
    if db.is_ready() and str((current_user or {}).get("role", "")).lower() != "buyer":
        raise HTTPException(status_code=403, detail="Only the corporate buyer may retire a certificate")
    rows = None
    if not db.is_ready():
        rows = [r for r in market_store.all_rows() if str(r.get("status")).lower() == "sold"]
    else:
        try:
            sb = db._client()
            rows = (sb.table("marketplace_listings").select("id,status,farm_id").eq("status", "Sold").execute().data) or []
        except Exception as e:
            return {"success": False, "message": str(e)}
    clean_cert_id = str(cert_id).strip().upper()
    target = next((r for r in rows if _cert_id_for_listing(r.get("id")).upper() == clean_cert_id), None)
    if not target:
        all_rows = market_store.all_rows() if not db.is_ready() else (sb.table("marketplace_listings").select("id,status,farm_id").execute().data or [])
        already = next((r for r in all_rows if _cert_id_for_listing(r.get("id")).upper() == clean_cert_id and str(r.get("status")).lower() == "retired"), None)
        if already:
            return {
                "success": True, "message": f"Certificate {cert_id} is already permanently retired",
                "cert_id": cert_id, "status": "RETIRED", "already_retired": True,
            }
        raise HTTPException(status_code=404, detail="Certificate not found")
    retired_ts = datetime.now(timezone.utc).isoformat()
    if not db.is_ready():
        market_store.update(target["id"], {"status": "Retired", "updated_at": retired_ts})
    else:
        sb = db._client()
        sb.table("marketplace_listings").update({"status": "Retired", "updated_at": retired_ts}).eq("id", target["id"]).execute()
    if target.get("farm_id"):
        ledger.append_event(target["farm_id"], "RETIRE", {
            "certificate_id": cert_id, "scope": scope, "manual": True,
        })
    from app.services.certificate_pdf import invalidate_certificate_pdf
    invalidate_certificate_pdf(cert_id)
    return {
        "success": True, "message": f"Certificate {cert_id} permanently retired for {scope}",
        "cert_id": cert_id, "listing_id": target["id"], "status": "RETIRED",
        "scope": scope, "retired_timestamp": retired_ts,
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
    verification_hash = "0x" + uuid.uuid5(uuid.NAMESPACE_URL, f"carbonx:{farm_id}:{farm.get('updated_at')}").hex[:26]

    credits_total = float(farm.get("total_credits") or 0)
    income = credit_engine.income_projection(credits_total, badge)

    verified_status = str(farm.get("status", "")).lower() in ("verified", "ver")
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
    chain["history"] = [{k: v for k, v in e.items() if not k.startswith("_")} for e in ledger.get_chain(farm_id)]
    farm_status = farm.get("status")
    monitoring = {
        "last_monitored_at": farm.get("last_monitored_at"),
        "last_monitor_ndvi": farm.get("last_monitor_ndvi"),
        "at_risk": str(farm_status or "").lower() == "flagged",
        "cycle": "5-day Sentinel-2 revisit",
    }

    return {
        "success": True, "passport_id": f"CX-FARM-{str(farm_id).replace('-', '')[:8].upper()}",
        "demo_mode": demo_mode, "farm_name": farm.get("name"),
        "owner_name": (owner or {}).get("name") or "Registered Farmer",
        "phone": farm.get("owner_phone"),
        "district": (owner or {}).get("district"), "village": (owner or {}).get("village"),
        "crop": farm.get("crop_type"), "irrigation": farm.get("irrigation"),
        "acreage": farm.get("area_hectares"), "badge": badge, "benchmark_price": benchmark,
        "annual_credits": farm.get("total_credits"), "carbon_tonnes": farm.get("carbon_tonnes"),
        "sentinel_ndvi": farm.get("ndvi"), "evi": farm.get("evi"),
        "biodiversity_index": round(float(farm.get("biodiversity_score") or 0) / 10, 1) if farm.get("biodiversity_score") else None,
        "satellite_source": farm.get("satellite_source"), "ai_confidence": farm.get("ai_confidence"),
        "verification_hash": verification_hash, "farm_status": farm_status,
        "kyc_status": (kyc or {}).get("status"),
        "status": "APPROVED MRV RECORD" if verified_status else "PENDING MRV REVIEW",
        "expected_earnings": income,
        "credits_ci90": {"low": farm.get("credits_ci90_low"), "high": farm.get("credits_ci90_high")},
        "formula_version": farm.get("formula_version") or app_config.FORMULA_VERSION,
        "s2_scene": farm.get("s2_scene"),
        "monitoring": monitoring,
        "trust": {
            "evidence_quality": quality["score"],
            "uncertainty_pct": credit_engine.uncertainty_pct(quality["score"]),
            "components": quality["components"],
            "evidence": {
                "practice_photo": evidence["practice_photo"],
                "geotag_inside_boundary": evidence["geotag_inside_boundary"],
                "photo_count": evidence["photo_count"],
                "geotag_count": evidence["geotag_count"],
                "last_photo_at": evidence["last_photo_at"],
                "demo_mode": evidence["demo_mode"],
            },
            "verification_hash": verification_hash,
        },
        "ledger": chain,
    }


@router.get("/wallet")
def get_wallet_ledger(current_user: dict = Depends(get_current_user)):
    phone = current_user.get("phone")
    if not db.is_ready():
        from app import sample_data
        profile = sample_data.FARMERS.get(phone) or {}
        rows = [r for r in market_store.all_rows() if r.get("farmer_phone") == phone]
    else:
        try:
            sb = db._client()
            profile = db.get_profile(phone) or {}
            rows = (sb.table("marketplace_listings").select("*").eq("farmer_phone", phone).execute().data) or []
        except Exception as e:
            return {"success": False, "message": str(e)}

    sold = [r for r in rows if str(r.get("status")).lower() in ("sold", "retired")]
    active = [r for r in rows if str(r.get("status")).lower() == "active"]

    farms_cache: dict = {}

    def _farm(farm_id):
        if not farm_id or not db.is_ready():
            return None
        if farm_id not in farms_cache:
            farms_cache[farm_id] = db.get_farm(farm_id)
        return farms_cache[farm_id]

    # Proceeds come from the hash ledger (the money source of truth); the
    # listing row is only a fallback for rows predating the ledger.
    sales_by_listing = {
        r.get("id"): _ledger_sales(r.get("farm_id") or "", r.get("id")) for r in rows
    }

    def _settled(r):
        return sales_by_listing.get(r.get("id")) if sales_by_listing.get(r.get("id"), {}).get("found") else None

    def _gross(r):
        sales = _settled(r)
        if sales:
            return sales["gross_inr"]
        bid = r.get("current_bid")
        if bid:
            return round(float(bid), 2)
        return round(float(r.get("total_credits") or 0) * float(r.get("price_per_credit") or 0), 2)

    # Partially-bought listings stay Active: their settled proceeds belong in
    # earnings, while only the *remaining* credits are pending escrow.
    settled_rows = sold + [r for r in active if _settled(r)]
    total_earned = round(sum(_gross(r) for r in settled_rows), 2)
    escrow_pending = round(sum(
        float(r.get("total_credits") or 0) * float(r.get("price_per_credit") or 0) for r in active
    ), 2)

    farmer_total = 0.0
    fpo_total = 0.0
    platform_total = 0.0
    transactions = []
    for r in sorted(settled_rows, key=lambda x: x.get("updated_at") or "", reverse=True):
        gross = _gross(r)
        fpo_name = _resolve_fpo_link(_farm(r.get("farm_id")), r.get("farmer_phone") or phone)
        split = split_engine.compute_split(gross, fpo_involved=bool(fpo_name), fpo_name=fpo_name)
        farmer_total += split["farmer_amount_inr"]
        fpo_total += split["fpo_amount_inr"]
        platform_total += split["platform_amount_inr"]
        farm_id = r.get("farm_id") or ""
        chain = ledger.summary(farm_id) if farm_id else {}
        rate = float(r.get("price_per_credit") or 0)
        sales = _settled(r)
        transactions.append({
            "date": (r.get("updated_at") or r.get("created_at") or "")[:10],
            "tx_id": (r.get("tx_hash") or f"TXN-{(r.get('id') or '')[:6].upper()}"),
            "source": f"Marketplace sale ({r.get('crop') or 'Mixed Crop'})",
            "listing_id": r.get("id"), "farm_id": farm_id,
            "credits_sold": sales["credits"] if sales else r.get("total_credits"),
            "rate": rate or None, "gross": gross,
            "farmer_share": split["farmer_amount_inr"], "fpo_share": split["fpo_amount_inr"],
            "platform_share": split["platform_amount_inr"], "split_model": split["model"],
            "ledger_hash": chain.get("tail_hash"),
            "status": "SETTLED" if str(r.get("status")).lower() in ("sold", "retired") else "PARTIAL",
        })

    return {
        "success": True, "total_earned": total_earned, "escrow_pending": escrow_pending,
        "withdrawable_upi": round(farmer_total, 2),
        "farmer_share_total": round(farmer_total, 2), "fpo_share_total": round(fpo_total, 2),
        "platform_share_total": round(platform_total, 2), "upi_id": profile.get("upi"),
        "demo_mode": not db.is_ready(), "transactions": transactions,
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
    return {"success": True, "estimate": estimate, "income": income, "evidence_quality": quality}


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
    public_events = [{k: v for k, v in e.items() if not k.startswith("_")} for e in chain]
    return {
        "success": True, "farm_id": farm_id,
        "verification": verification, "events": public_events,
    }
