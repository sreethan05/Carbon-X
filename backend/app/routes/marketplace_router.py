"""Marketplace routes: listings, bids, escrow purchases, auto-match, conditional splits."""
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from typing import Literal, Optional
import json
import time
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

router = APIRouter(prefix="/marketplace", tags=["marketplace"])


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


def _resolve_fpo_link(farm: Optional[dict], farmer_phone: str) -> str:
    if farm and farm.get("fpo_id"):
        fpos = db.list_fpos() if db.is_ready() else []
        match = next((f for f in fpos if f.get("id") == farm.get("fpo_id")), None)
        return (match or {}).get("name") or "Linked FPO"
    if farm and farm.get("fpo"):
        return farm["fpo"]
    return market_store.fpo_for_phone(farmer_phone)


def _purchase_flow(listing: dict, credits: float, buyer_name: str, apply_update) -> dict:
    available = float(listing.get("total_credits") or 0)
    unit_price = float(listing.get("price_per_credit") or 0)
    gross = round(credits * unit_price, 2)
    farm_id = listing.get("farm_id") or ""
    fpo_name = _resolve_fpo_link(None, listing.get("farmer_phone") or "")
    if not fpo_name and farm_id and db.is_ready():
        farm = db.get_farm(farm_id) or {}
        fpo_name = _resolve_fpo_link(farm, listing.get("farmer_phone") or "")

    split = split_engine.compute_split(gross, fpo_involved=bool(fpo_name), fpo_name=fpo_name)
    escrow_ref = "ESC-" + uuid.uuid4().hex[:12].upper()
    batch_hash = None
    partial = credits < available - 1e-6

    updates = {"tx_hash": escrow_ref, "current_bid": gross, "bids_count": int(listing.get("bids_count") or 0) + 1}
    if partial:
        updates["total_credits"] = round(available - credits, 4)
    else:
        updates["status"] = "Retired"
    apply_update(updates)

    cert_id = _cert_id_for_listing(listing.get("id"))
    sale_event = ledger.append_event(farm_id, "SALE", {
        "listing_id": listing.get("id"),
        "buyer": buyer_name,
        "credits": credits,
        "unit_price": unit_price,
        "gross_inr": gross,
        "escrow_ref": escrow_ref,
        "certificate_id": cert_id,
    })
    split_event = ledger.append_event(farm_id, "SPLIT", {
        "escrow_ref": escrow_ref,
        "model": split["model"],
        "farmer_inr": split["farmer_amount_inr"],
        "fpo_inr": split["fpo_amount_inr"],
        "platform_inr": split["platform_amount_inr"],
    })
    batch_hash = split_event["hash"]
    ledger.append_event(farm_id, "RETIRE", {
        "certificate_id": cert_id,
        "credits_retired": credits,
        "escrow_ref": escrow_ref,
        "batch_hash": batch_hash,
        "buyer": buyer_name,
    })

    return {
        "success": True,
        "message": "Purchase complete — escrowed, split paid, credits retired",
        "certificate_id": cert_id,
        "listing_id": listing.get("id"),
        "farm_id": farm_id,
        "buyer_name": buyer_name,
        "escrow_ref": escrow_ref,
        "batch_hash": batch_hash,
        "ledger_tail": sale_event["hash"],
        "retired": not partial,
        "credits_purchased": credits,
        "credits_remaining": round(available - credits, 4),
        "gross_amount": gross,
        "unit_price": unit_price,
        "split": split,
        "farmer_name": listing.get("farmer_name"),
        "farmer_phone": listing.get("farmer_phone"),
        "crop": listing.get("crop"),
        "location": listing.get("location"),
        "source": listing.get("_source", "live_db"),
    }


# ─── Models ───

class CreateListingModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    carbon_credits: Optional[float] = None
    biodiversity_credits: Optional[float] = None
    credits: Optional[float] = None
    price_per_credit: float = 520
    farm_id: Optional[str] = None
    crop: Optional[str] = ""
    token_id: Optional[str] = None
    tx_hash: Optional[str] = None


class BidModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bid_amount: float
    bidder_name: Optional[str] = "Corporate Buyer"


class MarketplaceBuyModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    listing_id: str
    credits: float
    unit_price: Optional[float] = None
    buyer_name: Optional[str] = "Corporate Buyer"


class AutoMatchModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_volume: float
    priority: Optional[str] = "lowest_price"
    filters: Optional[dict] = None


# ─── Endpoints ───

@router.get("/listings")
def marketplace_listings(
    status: Optional[str] = Query("Active"),
    crop: Optional[str] = None,
    location: Optional[str] = None,
    farmer_phone: Optional[str] = None,
    farm_id: Optional[str] = None,
    listing_model: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    min_credits: Optional[float] = None,
    max_credits: Optional[float] = None,
    search: Optional[str] = None,
    sort: str = Query("created_at"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    cursor: Optional[str] = None,
):
    try:
        query_kwargs = {
            "status": status, "crop": crop, "location": location,
            "farmer_phone": farmer_phone, "farm_id": farm_id,
            "listing_model": listing_model, "min_price": min_price,
            "max_price": max_price, "min_credits": min_credits,
            "max_credits": max_credits, "search": search,
            "sort": sort, "order": order, "limit": limit, "offset": offset,
        }
        if cursor:
            try:
                import base64 as _b64
                query_kwargs["offset"] = int(_b64.urlsafe_b64decode(cursor.encode()).decode())
            except Exception:
                return {"success": False, "message": "Invalid cursor", "code": "BAD_CURSOR"}
        applied = {k: v for k, v in query_kwargs.items() if v is not None}

        result = None
        source = "live_db"
        if db.is_ready():
            try:
                result = db.get_listings_filtered(**query_kwargs)
            except Exception as e:
                print(f"[marketplace/listings] LIVE DB query failed ({e}) — serving FALLBACK sample data")
                result = None
        else:
            print("[marketplace/listings] LIVE DB not configured — serving FALLBACK sample data")
        if result is None:
            source = "fallback"
            from app import sample_data
            rows = market_store.all_rows()
            result = sample_data.filter_listings(rows, **query_kwargs)

        # Build next_cursor
        next_cursor = None
        if len(result["listings"]) == limit:
            next_offset = offset + limit
            import base64 as _b64
            next_cursor = _b64.urlsafe_b64encode(str(next_offset).encode()).decode()

        print(
            f"[marketplace/listings] source={'LIVE DB' if source == 'live_db' else 'FALLBACK sample data'} "
            f"| matched={result['total']} | returned={len(result['listings'])} | filters={applied or 'default'}"
        )
        return {
            "success": True, "source": source, "total": result["total"],
            "count": len(result["listings"]), "filters": applied,
            "listings": result["listings"], "next_cursor": next_cursor,
        }
    except Exception as e:
        return {"success": False, "message": str(e), "source": "error", "total": 0, "count": 0, "listings": []}


@router.post("/listings")
def create_listing(data: CreateListingModel, current_user: dict = Depends(get_current_user)):
    try:
        _require_database()
        phone = current_user.get("phone")
        user = _get_user(phone)
        if not user:
            return {"success": False, "message": "User not found"}
        if data.farm_id:
            from app.services.trust_engine import farm_may_list
            farm = db.get_farm(data.farm_id)
            if farm and farm.get("owner_phone") != phone:
                return {"success": False, "message": "Farm does not belong to this user"}
            latest = db.get_kyc_status(phone)
            badge = ((latest or {}).get("extracted_fields") or {}).get("badge") or (farm or {}).get("badge")
            ok, reason = farm_may_list(farm, badge)
            if not ok:
                return {"success": False, "message": reason}
        c_credits = data.carbon_credits
        b_credits = data.biodiversity_credits
        if c_credits is None and b_credits is None and data.credits is not None:
            c_credits = round(float(data.credits) * 0.8, 2)
            b_credits = round(float(data.credits) * 0.2, 2)
        else:
            c_credits = float(c_credits or 0)
            b_credits = float(b_credits or 0)
        total = round(c_credits + b_credits, 2)
        listing = {
            "farmer_phone": phone,
            "farmer_name": user.get("name", "Farmer"),
            "location": f"{user.get('village', '')}, {user.get('district', '')}".strip(", "),
            "crop": data.crop or "Mixed Crop",
            "size_label": "",
            "carbon_credits": c_credits,
            "biodiversity_credits": b_credits,
            "total_credits": total,
            "price_per_credit": data.price_per_credit,
            "listing_model": "Fixed Price",
            "status": "Active",
            "farm_id": data.farm_id,
            "token_id": data.token_id,
            "tx_hash": data.tx_hash,
            "image_url": "https://images.unsplash.com/photo-1500937386664-56d1dfef3854?auto=format&fit=crop&q=80&w=400",
        }
        saved = db.insert_listing(listing)
        if not saved or not saved.get("id"):
            return {"success": False, "message": "Failed to save listing"}
        if data.farm_id and data.token_id:
            db.update_farm(data.farm_id, {"token_id": data.token_id})
        return {"success": True, "listing": saved}
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.post("/listings/{listing_id}/bid")
def place_bid(listing_id: str, data: BidModel, current_user: dict = Depends(get_current_user)):
    sb = db._client()
    if not sb:
        return {"success": False, "message": "Database unavailable"}
    try:
        rows = (sb.table("marketplace_listings").select("*").eq("id", listing_id).execute().data) or []
        if not rows:
            return {"success": False, "message": "Listing not found"}
        listing = rows[0]
        if str(listing.get("status") or "Active").lower() != "active":
            return {"success": False, "message": f"Bidding closed (listing status: {listing.get('status')})"}
        current = float(listing.get("current_bid") or 0)
        base = float(listing.get("price_per_credit") or 0)
        amount = float(data.bid_amount or 0)
        if amount <= 0:
            return {"success": False, "message": "Bid amount must be greater than zero"}
        floor = current if current > 0 else base
        if amount <= floor:
            return {"success": False, "message": f"Bid must exceed the current standing bid of ₹{floor:,.0f}"}
        sb.table("marketplace_listings").update({
            "current_bid": amount,
            "bids_count": int(listing.get("bids_count") or 0) + 1,
        }).eq("id", listing_id).execute()
        return {
            "success": True, "message": "Bid placed successfully", "listing_id": listing_id,
            "bid_amount": amount, "bidder_name": data.bidder_name or current_user.get("name"),
            "previous_bid": current, "bids_count": int(listing.get("bids_count") or 0) + 1,
        }
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.post("/buy")
def buy_marketplace_credits(data: MarketplaceBuyModel, current_user: Optional[dict] = Depends(get_current_user_optional)):
    buyer = data.buyer_name or (current_user or {}).get("name") or "Corporate Buyer"

    if not db.is_ready():
        listing = market_store.get(data.listing_id)
        if not listing:
            return {"success": False, "message": "Listing not found"}
        if str(listing.get("status") or "Active").lower() not in ("active", ""):
            return {"success": False, "message": f"Listing is no longer available (status: {listing.get('status')})"}
        available = float(listing.get("total_credits") or 0)
        if available <= 0:
            return {"success": False, "message": "This listing has no purchasable credits left"}
        credits = round(min(float(data.credits or available), available), 4)
        if credits <= 0:
            return {"success": False, "message": "Credit quantity must be greater than zero"}
        listing["_source"] = "demo_store"
        return _purchase_flow(listing, credits, buyer, lambda fields: market_store.update(data.listing_id, fields))

    try:
        sb = db._client()
        rows = (sb.table("marketplace_listings").select("*").eq("id", data.listing_id).execute().data) or []
        if not rows:
            return {"success": False, "message": "Listing not found"}
        listing = rows[0]
        if str(listing.get("status") or "Active").lower() not in ("active", ""):
            return {"success": False, "message": f"Listing is no longer available (status: {listing.get('status')})"}
        available = float(listing.get("total_credits") or 0)
        if available <= 0:
            return {"success": False, "message": "This listing has no purchasable credits left"}
        credits = round(min(float(data.credits or available), available), 4)
        if credits <= 0:
            return {"success": False, "message": "Credit quantity must be greater than zero"}
        # Never write ledger events against a phantom farm
        farm_id = listing.get("farm_id")
        if farm_id and not db.get_farm(farm_id):
            return {"success": False, "message": "Listing references an unknown farm — purchase rejected"}
        return _purchase_flow(listing, credits, buyer, lambda fields: sb.table("marketplace_listings").update(fields).eq("id", data.listing_id).execute())
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.post("/auto-match")
def auto_match_bulk(data: AutoMatchModel):
    rows_source = None
    if not db.is_ready():
        rows_source = [r for r in market_store.all_rows() if r.get("status") == "Active"]
    listings = rows_source
    if listings is None:
        sb = db._client()
        try:
            listings = (sb.table("marketplace_listings").select("*").eq("status", "Active").execute().data) or []
        except Exception as e:
            return {"success": False, "message": str(e), "matched_farms": []}
    listings = [l for l in listings if float(l.get("total_credits") or 0) > 0]
    farm_ids = list({l.get("farm_id") for l in listings if l.get("farm_id")})
    farms_by_id = {}
    if farm_ids and db.is_ready():
        sb = db._client()
        farms_by_id = {f.get("id"): f for f in (sb.table("farms").select("id,name,badge,ndvi").in_("id", farm_ids).execute().data or [])}

    if data.priority == "highest_ndvi":
        listings.sort(key=lambda l: float((farms_by_id.get(l.get("farm_id")) or {}).get("ndvi") or 0), reverse=True)
    else:
        listings.sort(key=lambda l: float(l.get("price_per_credit") or 0))

    volume = float(data.target_volume or 0)
    matched = []
    for l in listings:
        if volume <= 0:
            break
        take = min(volume, float(l.get("total_credits") or 0))
        farm = farms_by_id.get(l.get("farm_id")) or {}
        badge = farm.get("badge") or "DOCUMENT"
        line_gross = round(take * float(l.get("price_per_credit") or 0), 2)
        fpo_name = _resolve_fpo_link(farm or None, l.get("farmer_phone") or "")
        line_split = split_engine.compute_split(line_gross, fpo_involved=bool(fpo_name), fpo_name=fpo_name)
        matched.append({
            "listing_id": l.get("id"), "farm": farm.get("name") or l.get("location") or "Telangana Parcel",
            "farmer": l.get("farmer_name") or "Marketplace Farmer", "survey": l.get("location"),
            "crop": l.get("crop"), "credits": round(take, 2), "rate": float(l.get("price_per_credit") or 0),
            "badge": badge, "badge_color": "emerald" if badge == "REGISTRY" else ("forest" if badge == "REGISTRY_DOC" else "amber"),
            "farmer_share_inr": line_split["farmer_amount_inr"], "fpo_name": fpo_name or None,
        })
        volume -= take

    gross = round(sum(m["credits"] * m["rate"] for m in matched), 2)
    overall_split = split_engine.compute_split(
        gross, fpo_involved=any(m.get("fpo_name") for m in matched)
    )
    return {
        "success": True, "target_volume": float(data.target_volume or 0),
        "total_matched": round(sum(m["credits"] for m in matched), 2), "gross_value": gross,
        "farmer_total_inr": overall_split["farmer_amount_inr"], "fpo_total_inr": overall_split["fpo_amount_inr"],
        "platform_total_inr": overall_split["platform_amount_inr"], "split_model": overall_split["model"],
        "matched_farms": matched,
    }