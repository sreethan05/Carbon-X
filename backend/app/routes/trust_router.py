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
from app.services import credit_engine, ledger, market_store, split_engine

router = APIRouter(tags=["trust"])


def _resolve_fpo_link(farm: Optional[dict], farmer_phone: str) -> str:
    if farm and farm.get("fpo_id"):
        fpos = db.list_fpos() if db.is_ready() else []
        match = next((f for f in fpos if f.get("id") == farm.get("fpo_id")), None)
        return (match or {}).get("name") or "Linked FPO"
    if farm and farm.get("fpo"):
        return farm["fpo"]
    return market_store.fpo_for_phone(farmer_phone)


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
    has_photo: Optional[bool] = True
    geotag_ok: Optional[bool] = True
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
        retired = str(r.get("status")).lower() == "retired"
        certificates.append({
            "id": _cert_id_for_listing(r.get("id")),
            "listing_id": r.get("id"),
            "issued_to": "Corporate Buyer",
            "farmer_name": r.get("farmer_name"),
            "crop": r.get("crop"),
            "volume_mt": r.get("total_credits"),
            "value_inr": r.get("current_bid"),
            "source_parcels": [f"{r.get('location') or 'Telangana'} ({r.get('crop') or 'Mixed Crop'})"],
            "issued_date": (r.get("updated_at") or r.get("created_at") or "")[:10],
            "status": "RETIRED" if retired else "HELD_IN_ESCROW",
            "batch_hash": chain.get("tail_hash"),
            "ledger_verified": chain.get("verified", False),
            "tx_hash": r.get("tx_hash"),
            "on_chain": False,
        })
    return {"success": True, "certificates": certificates}


@router.get("/certificates/{cert_id}/pdf")
def download_certificate_pdf(cert_id: str):
    from fastapi.responses import Response
    from app.services.certificate_pdf import render_certificate_pdf

    global _pdf_cache
    if "_pdf_cache" not in globals():
        _pdf_cache = {}
    if len(_pdf_cache) > app_config.PDF_CACHE_MAX_ENTRIES:
        _pdf_cache.clear()
    cached = _pdf_cache.get(cert_id)
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
    row = next((r for r in rows if _cert_id_for_listing(r.get("id")) == cert_id), None)
    if not row:
        return {"success": False, "message": "Certificate not found"}
    farm_id = row.get("farm_id") or ""
    chain = ledger.summary(farm_id) if farm_id else {}
    cert = {
        "id": cert_id, "buyer": "Corporate Buyer",
        "farmer_name": row.get("farmer_name"), "crop": row.get("crop"),
        "volume": row.get("total_credits"), "value": row.get("current_bid"),
        "location": row.get("location"),
        "issued_date": (row.get("updated_at") or row.get("created_at") or "")[:10],
        "retired_date": (row.get("updated_at") or row.get("created_at") or "")[:10],
        "batch_hash": chain.get("tail_hash") or row.get("tx_hash") or "",
    }
    pdf_bytes = render_certificate_pdf(cert)
    _pdf_cache[cert_id] = pdf_bytes
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="CarbonX_Certificate_{cert_id}.pdf"'},
    )


@router.post("/certificates/{cert_id}/retire")
def retire_certificate(cert_id: str, scope: Optional[str] = "Scope 1 Neutrality"):
    rows = None
    if not db.is_ready():
        rows = [r for r in market_store.all_rows() if str(r.get("status")).lower() == "sold"]
    else:
        try:
            sb = db._client()
            rows = (sb.table("marketplace_listings").select("id,status,farm_id").eq("status", "Sold").execute().data) or []
        except Exception as e:
            return {"success": False, "message": str(e)}
    target = next((r for r in rows if _cert_id_for_listing(r.get("id")) == cert_id), None)
    if not target:
        return {
            "success": True, "message": f"Certificate {cert_id} is already permanently retired",
            "cert_id": cert_id, "status": "RETIRED", "already_retired": True,
        }
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
    return {
        "success": True, "message": f"Certificate {cert_id} permanently retired for {scope}",
        "cert_id": cert_id, "listing_id": target["id"], "status": "RETIRED",
        "scope": scope, "retired_timestamp": retired_ts,
    }


@router.get("/passport/{farm_id}")
def get_carbon_passport(farm_id: str):
    farm = db.get_farm(farm_id) if db.is_ready() else None
    demo_mode = False
    if not farm:
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
    quality = credit_engine.evidence_quality(
        has_photo=True, geotag_ok=True,
        fpo_or_registry=badge in ("REGISTRY", "REGISTRY_DOC", "FPO"),
        ndvi_current=farm.get("ndvi") is not None, baseline_known=verified_status,
    )
    ledger.ensure_genesis(farm_id, {
        "farm": farm.get("name"), "crop": farm.get("crop_type"),
        "area_hectares": farm.get("area_hectares"), "ndvi": farm.get("ndvi"),
        "carbon_tonnes": farm.get("carbon_tonnes"), "badge": badge, "status": farm.get("status"),
    }, ts=(farm.get("updated_at") or "") or None)
    chain = ledger.summary(farm_id)
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

    def _gross(r):
        bid = r.get("current_bid")
        if bid:
            return round(float(bid), 2)
        return round(float(r.get("total_credits") or 0) * float(r.get("price_per_credit") or 0), 2)

    total_earned = round(sum(_gross(r) for r in sold), 2)
    escrow_pending = round(sum(_gross(r) for r in active), 2)

    farmer_total = 0.0
    fpo_total = 0.0
    platform_total = 0.0
    transactions = []
    for r in sorted(sold, key=lambda x: x.get("updated_at") or "", reverse=True):
        gross = _gross(r)
        fpo_name = _resolve_fpo_link(None, r.get("farmer_phone") or phone)
        split = split_engine.compute_split(gross, fpo_involved=bool(fpo_name), fpo_name=fpo_name)
        farmer_total += split["farmer_amount_inr"]
        fpo_total += split["fpo_amount_inr"]
        platform_total += split["platform_amount_inr"]
        farm_id = r.get("farm_id") or ""
        chain = ledger.summary(farm_id) if farm_id else {}
        transactions.append({
            "date": (r.get("updated_at") or r.get("created_at") or "")[:10],
            "tx_id": (r.get("tx_hash") or f"TXN-{(r.get('id') or '')[:6].upper()}"),
            "source": f"Marketplace sale ({r.get('crop') or 'Mixed Crop'})",
            "listing_id": r.get("id"), "farm_id": farm_id, "credits_sold": r.get("total_credits"),
            "rate": r.get("price_per_credit"), "gross": gross,
            "farmer_share": split["farmer_amount_inr"], "fpo_share": split["fpo_amount_inr"],
            "platform_share": split["platform_amount_inr"], "split_model": split["model"],
            "ledger_hash": chain.get("tail_hash"), "status": "SETTLED",
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
def get_farm_ledger(farm_id: str):
    chain = ledger.get_chain(farm_id)
    if not chain:
        farm = db.get_farm(farm_id) if db.is_ready() else None
        snapshot = {
            "farm": (farm or {}).get("name") or "Sri Venkateswara Organic Farm (demo)",
            "crop": (farm or {}).get("crop_type") or "Rice",
            "ndvi": (farm or {}).get("ndvi") or 0.78,
            "note": "Genesis anchored from farm evidence snapshot",
        }
        ledger.ensure_genesis(farm_id, snapshot)
        chain = ledger.get_chain(farm_id)
    verification = ledger.verify_chain(farm_id)
    public_events = [{k: v for k, v in e.items() if not k.startswith("_")} for e in chain]
    return {
        "success": True, "farm_id": farm_id,
        "verification": verification, "events": public_events,
    }