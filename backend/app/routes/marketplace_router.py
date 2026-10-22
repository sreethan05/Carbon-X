"""Marketplace routes: listings, bids, escrow purchases, auto-match, conditional splits."""
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from typing import Literal, Optional
import json
import time
import uuid

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
from app.services import access_policy, credit_engine, credit_lifecycle, ledger, market_store, split_engine
from app.services import validation

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


def _dispute_open(listing: dict) -> bool:
    return str((listing or {}).get("dispute_status") or "NONE").upper() in ("OPEN", "DISPUTED")


def _sanitize_listing_for_caller(listing: dict, caller: Optional[dict]) -> dict:
    item = dict(listing)
    caller_phone = (caller or {}).get("phone")
    caller_role = (caller or {}).get("role")
    is_owner = bool(caller_phone and caller_phone == item.get("farmer_phone"))
    is_authorized = caller_role in ("admin", "fpo", "verifier")
    if not (is_owner or is_authorized):
        # Public marketplace: no phone, no farmer identity, district only.
        item["farmer_phone"] = None
        item["farmer_name"] = "Verified farmer (name withheld)"
        item["location"] = access_policy.public_location(item.get("location"))
        item["location_precision"] = "district"
    else:
        item["location_precision"] = "village"
    item.setdefault("dispute_status", "NONE")
    return item


def _resolve_fpo_link(farm: Optional[dict], farmer_phone: str) -> str:
    if farm and farm.get("fpo_id"):
        fpos = db.list_fpos() if db.is_ready() else []
        match = next((f for f in fpos if f.get("id") == farm.get("fpo_id")), None)
        return (match or {}).get("name") or "Linked FPO"
    if farm and farm.get("fpo"):
        return farm["fpo"]
    # Only demo listings (no real farm row) fall back to the sample FPO map;
    # a live farm with no recorded FPO link means the split has no FPO leg.
    return market_store.fpo_for_phone(farmer_phone) if farm is None else ""


def _prior_sale_gross(farm_id: str, listing_id: str) -> float:
    """Sum of SALE proceeds already booked in the hash ledger for this listing."""
    if not farm_id or not listing_id:
        return 0.0
    total = 0.0
    for event in ledger.get_chain(farm_id):
        if event.get("type") != "SALE":
            continue
        payload = event.get("payload") or {}
        if payload.get("listing_id") == listing_id:
            total += float(payload.get("gross_inr") or 0)
    return round(total, 2)


def settle_listing_purchase(
    listing: dict,
    credits: float,
    buyer_name: str,
    apply_update,
    farm: Optional[dict] = None,
    payment_ref: Optional[str] = None,
    rollback_update=None,
) -> dict:
    """Settle a (partial) credit purchase: CAS → SALE → SPLIT → RETIRE.

    Shared money path for /marketplace/buy (built-in simulated escrow,
    ``payment_ref=None``) and /payments/checkout (the provider's reference,
    e.g. a verified Razorpay payment id). ``apply_update(fields)`` must perform
    the compare-and-swap on the listing row and return truthy only if the row
    still held the state that was read — a concurrent buyer loses cleanly.

    ``rollback_update(fields)`` compensates the balance CAS if a ledger append
    fails, so a failed chain write does not silently consume credits.  The
    listing lock is still held, making the restore race-free.

    ``payment_ref``, when provided, is recorded on the SALE ledger event and
    echoed in the response so the chain links back to the payment provider.
    """
    available = float(listing.get("total_credits") or 0)
    unit_price = float(listing.get("price_per_credit") or 0)
    gross = round(credits * unit_price, 2)
    farm_id = listing.get("farm_id") or ""
    listing_id = str(listing.get("id") or "")
    if not listing_id:
        return {"success": False, "message": "Listing id is required"}
    if farm is None and farm_id and db.is_ready():
        farm = db.get_farm(farm_id)
    fpo_name = _resolve_fpo_link(farm, listing.get("farmer_phone") or "")

    split = split_engine.compute_split(gross, fpo_involved=bool(fpo_name), fpo_name=fpo_name)
    escrow_ref = "ESC-" + uuid.uuid4().hex[:12].upper()
    partial = credits < available - 1e-6

    # Serialize the whole settle (balance CAS + ledger appends + certificate
    # sequence allocation) per listing.  Redis makes this cross-worker; the
    # memory fallback covers single-process/demo mode.  The CAS below is still
    # the final authority if the lock expired or a worker missed it.
    lock_name = f"listing:settle:{listing_id}"
    if not redis_store.acquire_lock(lock_name, ttl_seconds=60):
        return {
            "success": False,
            "code": "CONFLICT",
            "message": "Another purchase is settling this listing — retry in a moment",
        }
    try:
        ledger_entity_id = farm_id or listing_id
        chain = ledger.get_chain(ledger_entity_id)
        sale_seq = credit_lifecycle.sale_index_from_chain(chain, listing_id) + 1
        net_sold = 0.0
        for event in chain:
            payload = event.get("payload") or {}
            if event.get("type") == "SALE" and str(payload.get("listing_id")) == listing_id:
                net_sold += float(payload.get("credits") or 0)
            elif event.get("type") == "REFUND" and str(payload.get("listing_id")) == listing_id:
                net_sold -= float(payload.get("credits") or 0)
        net_sold = max(0.0, net_sold)
        prior = {
            "total_credits": available,
            "status": listing.get("status") or "Active",
            "tx_hash": listing.get("tx_hash"),
            "current_bid": listing.get("current_bid"),
            "bids_count": listing.get("bids_count"),
            "credits_sold": listing.get("credits_sold"),
            "lifecycle_state": listing.get("lifecycle_state"),
        }
        prior = {k: v for k, v in prior.items() if v is not None}
        prior.setdefault("status", "Active")
        prior.setdefault("total_credits", available)

        updates = {
            "tx_hash": escrow_ref,
            "current_bid": round(_prior_sale_gross(farm_id, listing_id) + gross, 2),
            "bids_count": int(listing.get("bids_count") or 0) + 1,
            "credits_sold": round(net_sold + credits, 4),
            "lifecycle_state": "Retired" if not partial else "Partially Sold",
        }
        if partial:
            updates["total_credits"] = round(available - credits, 4)
        else:
            updates["status"] = "Retired"
            updates["total_credits"] = 0.0

        # Compare-and-swap: proceed (and write ledger events) only if the row
        # was still in the state we read. A concurrent buyer wins the race.
        # ``credits_sold``/``lifecycle_state`` are new columns; retry without
        # them on a pre-migration database rather than blocking every sale.
        optional = {"credits_sold", "lifecycle_state"}
        try:
            cas_ok = apply_update(updates)
        except Exception:
            if not (set(updates) & optional):
                raise
            fallback = {k: v for k, v in updates.items() if k not in optional}
            cas_ok = apply_update(fallback)
        if not cas_ok:
            return {
                "success": False,
                "code": "CONFLICT",
                "message": "Listing changed during checkout (concurrent purchase) — refresh and try again",
            }

        cert_id = credit_lifecycle.certificate_id_for_sale(listing_id, sale_seq)
        sale_payload = {
            "listing_id": listing_id,
            "buyer": buyer_name,
            "credits": credits,
            "unit_price": unit_price,
            "gross_inr": gross,
            "escrow_ref": escrow_ref,
            "certificate_id": cert_id,
            "sale_seq": sale_seq,
        }
        if payment_ref:
            sale_payload["payment_ref"] = payment_ref
        try:
            sale_event = ledger.append_event(ledger_entity_id, "SALE", sale_payload)
            split_event = ledger.append_event(ledger_entity_id, "SPLIT", {
                "escrow_ref": escrow_ref,
                "listing_id": listing_id,
                "certificate_id": cert_id,
                "gross_inr": gross,
                "model": split["model"],
                "farmer_inr": split["farmer_amount_inr"],
                "fpo_inr": split["fpo_amount_inr"],
                "platform_inr": split["platform_amount_inr"],
            })
            batch_hash = split_event["hash"]
            ledger.append_event(ledger_entity_id, "RETIRE", {
                "certificate_id": cert_id,
                "listing_id": listing_id,
                "credits_retired": credits,
                "escrow_ref": escrow_ref,
                "batch_hash": batch_hash,
            })
        except Exception as exc:
            # The balance CAS committed but the chain did not.  First try to
            # put the balance back (we still hold the per-listing lock), then
            # record a SALE_FAILED reconciliation event.  Never pretend the
            # purchase succeeded and never leave credits silently consumed.
            balance_restored = False
            if rollback_update is not None:
                try:
                    balance_restored = bool(rollback_update(prior))
                except Exception as rollback_exc:
                    print(f"[marketplace] balance rollback failed for {listing_id}: {rollback_exc}")
            try:
                ledger.append_event(ledger_entity_id, "SALE_FAILED", {
                    "listing_id": listing_id,
                    "certificate_id": cert_id,
                    "escrow_ref": escrow_ref,
                    "credits": credits,
                    "gross_inr": gross,
                    "error": str(exc)[:500],
                    "balance_restored": balance_restored,
                    "requires_reconciliation": not balance_restored,
                })
            except Exception:
                pass
            return {
                "success": False,
                "code": "LEDGER_WRITE_FAILED_BALANCE_RESTORED" if balance_restored else "LEDGER_WRITE_FAILED",
                "message": (
                    "The ledger write failed; the listing balance was restored. "
                    "No certificate was issued. Retry the purchase."
                    if balance_restored else
                    "Payment/balance changed but the ledger write failed. "
                    "Do not retry blindly; contact ops with the escrow reference."
                ),
                "escrow_ref": escrow_ref,
                "certificate_id": cert_id,
                "balance_restored": balance_restored,
                "requires_reconciliation": not balance_restored,
            }

        result = {
            "success": True,
            "message": "Purchase complete — escrowed, split paid, credits retired",
            "certificate_id": cert_id,
            "sale_seq": sale_seq,
            "listing_id": listing_id,
            "farm_id": farm_id,
            "buyer_name": buyer_name,
            "escrow_ref": escrow_ref,
            "batch_hash": batch_hash,
            "ledger_tail": sale_event["hash"],
            "retired": not partial,
            "lifecycle_state": "Retired" if not partial else "Partially Sold",
            "credits_purchased": credits,
            "credits_remaining": round(max(0.0, available - credits), 4),
            "gross_amount": gross,
            "unit_price": unit_price,
            "split": split,
            "payout_status": "recorded_simulated_rails",
            "farmer_name": listing.get("farmer_name"),
            "farmer_phone": listing.get("farmer_phone"),
            "crop": listing.get("crop"),
            "location": listing.get("location"),
            "source": listing.get("_source", "live_db"),
        }
        if payment_ref:
            result["payment_ref"] = payment_ref
        return result
    finally:
        redis_store.release_lock(lock_name)


def _purchase_flow(
    listing: dict,
    credits: float,
    buyer_name: str,
    apply_update,
    farm: Optional[dict] = None,
    rollback_update=None,
) -> dict:
    """Legacy name for the marketplace buy path — no payment provider involved."""
    return settle_listing_purchase(
        listing, credits, buyer_name, apply_update,
        farm=farm, rollback_update=rollback_update,
    )


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
    current_user: Optional[dict] = Depends(get_current_user_optional),
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
                decoded_offset = int(_b64.urlsafe_b64decode(cursor.encode()).decode())
                if decoded_offset < 0:
                    return {"success": False, "message": "Invalid cursor", "code": "BAD_CURSOR"}
                query_kwargs["offset"] = decoded_offset
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

        # Build next_cursor (offset may have come from the cursor itself)
        next_cursor = None
        if len(result["listings"]) == limit and (
            result.get("total") is None or (int(query_kwargs["offset"]) + limit < result["total"])
        ):
            next_offset = int(query_kwargs["offset"]) + limit
            import base64 as _b64
            next_cursor = _b64.urlsafe_b64encode(str(next_offset).encode()).decode()


        print(
            f"[marketplace/listings] source={'LIVE DB' if source == 'live_db' else 'FALLBACK sample data'} "
            f"| matched={result['total']} | returned={len(result['listings'])} | filters={applied or 'default'}"
        )
        sanitized = [_sanitize_listing_for_caller(l, current_user) for l in result["listings"]]
        validation_status = validation.current_status()
        for item in sanitized:
            item["credits_basis"] = "proxy_estimate"
            item["validation"] = validation_status
        return {
            "success": True, "source": source, "total": result["total"],
            "count": len(sanitized), "filters": applied,
            "credits_basis": "proxy_estimate",
            "validation": validation_status,
            "listings": sanitized, "next_cursor": next_cursor,
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
            if not farm:
                return {"success": False, "message": "Farm not found"}
            if farm.get("owner_phone") != phone:
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
        if total <= 0 or c_credits < 0 or b_credits < 0:
            return {"success": False, "message": "Total credits must be greater than zero"}
        if float(data.price_per_credit or 0) <= 0:
            return {"success": False, "message": "Price per credit must be greater than zero"}

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
def place_bid(listing_id: str, data: BidModel, current_user: Optional[dict] = Depends(get_current_user_optional)):
    if db.is_ready() and not current_user:
        raise HTTPException(status_code=401, detail="Sign in to place a bid")
    bidder_name = data.bidder_name or (current_user or {}).get("name") or "Corporate Buyer"
    amount = float(data.bid_amount or 0)
    if amount <= 0:
        return {"success": False, "message": "Bid amount must be greater than zero"}

    if not db.is_ready():
        listing = market_store.get(listing_id)
        if not listing:
            return {"success": False, "message": "Listing not found"}
        if str(listing.get("status") or "Active").lower() != "active":
            return {"success": False, "message": f"Bidding closed (listing status: {listing.get('status')})"}
        if _dispute_open(listing):
            return {"success": False, "code": "DISPUTED", "message": "Bidding is frozen while this certificate is under dispute"}
        current = float(listing.get("current_bid") or 0)
        base = float(listing.get("price_per_credit") or 0)
        floor = current if current > 0 else base
        if amount <= floor:
            return {"success": False, "message": f"Bid must exceed the current standing bid of ₹{floor:,.0f}"}

        ok, msg, updated_row = market_store.place_bid_cas(listing_id, amount, current)
        if not ok:
            return {"success": False, "message": msg, "code": "CONFLICT"}
        return {
            "success": True, "message": "Bid placed successfully", "listing_id": listing_id,
            "bid_amount": amount, "bidder_name": bidder_name,
            "previous_bid": current, "bids_count": int((updated_row or {}).get("bids_count") or 1),
        }

    try:
        sb = db._client()
        rows = (sb.table("marketplace_listings").select("*").eq("id", listing_id).execute().data) or []
        if not rows:
            return {"success": False, "message": "Listing not found"}
        listing = rows[0]
        if str(listing.get("status") or "Active").lower() != "active":
            return {"success": False, "message": f"Bidding closed (listing status: {listing.get('status')})"}
        if _dispute_open(listing):
            return {"success": False, "code": "DISPUTED", "message": "Bidding is frozen while this certificate is under dispute"}
        current = float(listing.get("current_bid") or 0)
        base = float(listing.get("price_per_credit") or 0)
        floor = current if current > 0 else base
        if amount <= floor:
            return {"success": False, "message": f"Bid must exceed the current standing bid of ₹{floor:,.0f}"}

        new_bids_count = int(listing.get("bids_count") or 0) + 1
        q = sb.table("marketplace_listings").update({
            "current_bid": amount,
            "bids_count": new_bids_count,
        }).eq("id", listing_id)
        if listing.get("current_bid") is not None and current > 0:
            q = q.eq("current_bid", listing.get("current_bid"))
        else:
            q = q.is_("current_bid", "null")
        res = q.select("id").execute()
        if not (res.data or []):
            return {
                "success": False,
                "code": "CONFLICT",
                "message": "A higher or concurrent bid was placed — refresh and try again",
            }
        return {
            "success": True, "message": "Bid placed successfully", "listing_id": listing_id,
            "bid_amount": amount, "bidder_name": bidder_name,
            "previous_bid": current, "bids_count": new_bids_count,
        }
    except Exception as e:
        return {"success": False, "message": str(e)}



@router.post("/buy")
def buy_marketplace_credits(data: MarketplaceBuyModel, current_user: Optional[dict] = Depends(get_current_user_optional)):
    """Escrow purchase: split → hash-ledger events → instant retirement.

    Demo mode (DB off) stays open for local testing; with the live database a
    signed-in farmer/buyer token is required — anonymous visitors must never
    be able to move money or retire credits in production.
    """
    if db.is_ready() and not current_user:
        raise HTTPException(
            status_code=401,
            detail="Sign in with a corporate buyer account to purchase credits",
        )
    if current_user and str((current_user or {}).get("role", "")).lower() in ("farmer",):
        raise HTTPException(
            status_code=403,
            detail="Farmer accounts cannot purchase credits. Corporate buyer account required.",
        )
    if db.is_ready() and str((current_user or {}).get("role", "")).lower() != "buyer":
        raise HTTPException(
            status_code=403,
            detail="Farmer accounts cannot purchase credits. Corporate buyer account required.",
        )
    if db.is_ready() and not app_config.ALLOW_SIMULATED_SETTLEMENT:
        raise HTTPException(
            status_code=503,
            detail="Direct settlement is disabled until a live payment provider is configured.",
        )
    buyer = data.buyer_name or (current_user or {}).get("name") or "Corporate Buyer"

    # Input validation: credit quantity must be positive
    if data.credits is not None and float(data.credits) <= 0:
        return {"success": False, "message": "Credit quantity must be greater than zero"}

    if not db.is_ready():
        listing = market_store.get(data.listing_id)
        if not listing:
            return {"success": False, "message": "Listing not found"}
        if str(listing.get("status") or "Active").lower() not in ("active", ""):
            return {"success": False, "message": f"Listing is no longer available (status: {listing.get('status')})"}
        if _dispute_open(listing):
            return {"success": False, "code": "DISPUTED", "message": "This listing is frozen while a certificate dispute is open"}
        if current_user and current_user.get("phone") and listing.get("farmer_phone") == current_user.get("phone"):
            raise HTTPException(status_code=403, detail="Self-purchase / wash trading is prohibited.")
        available = float(listing.get("total_credits") or 0)
        if available <= 0:
            return {"success": False, "message": "This listing has no purchasable credits left"}
        credits = round(min(float(data.credits or available), available), 4)
        if credits <= 0:
            return {"success": False, "message": "Credit quantity must be greater than zero"}
        listing["_source"] = "demo_store"
        return _purchase_flow(
            listing, credits, buyer,
            lambda fields: market_store.update_cas(data.listing_id, fields, expected_credits=available),
            rollback_update=lambda fields: market_store.update(data.listing_id, fields) is not None,
        )

    try:
        sb = db._client()
        rows = (sb.table("marketplace_listings").select("*").eq("id", data.listing_id).execute().data) or []
        if not rows:
            return {"success": False, "message": "Listing not found"}
        listing = rows[0]
        if str(listing.get("status") or "Active").lower() not in ("active", ""):
            return {"success": False, "message": f"Listing is no longer available (status: {listing.get('status')})"}
        if _dispute_open(listing):
            return {"success": False, "code": "DISPUTED", "message": "This listing is frozen while a certificate dispute is open"}
        if current_user and current_user.get("phone") and listing.get("farmer_phone") == current_user.get("phone"):
            raise HTTPException(status_code=403, detail="Self-purchase / wash trading is prohibited.")
        available = float(listing.get("total_credits") or 0)
        if available <= 0:
            return {"success": False, "message": "This listing has no purchasable credits left"}
        credits = round(min(float(data.credits or available), available), 4)
        if credits <= 0:
            return {"success": False, "message": "Credit quantity must be greater than zero"}
        # Never write ledger events against a phantom farm
        farm_id = listing.get("farm_id")
        farm = db.get_farm(farm_id) if farm_id else None
        if farm_id and not farm:
            return {"success": False, "message": "Listing references an unknown farm — purchase rejected"}

        def _cas_update(fields: dict) -> bool:
            """UPDATE ... WHERE id AND (status | credit balance) matched."""
            q = sb.table("marketplace_listings").update(fields).eq("id", data.listing_id)
            q = q.eq("status", listing.get("status") or "Active").eq("total_credits", available)
            return bool(q.select("id").execute().data)

        def _rollback_update(fields: dict) -> bool:
            # Unconditional restore is safe: the per-listing settlement lock is
            # still held and the loser of any CAS never wrote the ledger.
            try:
                res = sb.table("marketplace_listings").update(fields).eq("id", data.listing_id).execute()
                return bool(res.data)
            except Exception:
                core = {k: v for k, v in fields.items() if k not in ("credits_sold", "lifecycle_state")}
                res = sb.table("marketplace_listings").update(core).eq("id", data.listing_id).execute()
                return bool(res.data)

        return _purchase_flow(
            listing, credits, buyer, _cas_update, farm=farm,
            rollback_update=_rollback_update,
        )

    except Exception as e:
        return {"success": False, "message": str(e)}


@router.post("/auto-match")
def auto_match_bulk(data: AutoMatchModel):
    target_vol = float(data.target_volume or 0)
    if target_vol <= 0:
        return {
            "success": False,
            "message": "Target volume must be greater than zero",
            "target_volume": 0.0,
            "total_matched": 0.0,
            "gross_value": 0.0,
            "farmer_total_inr": 0.0,
            "fpo_total_inr": 0.0,
            "platform_total_inr": 0.0,
            "split_model": "3-way",
            "matched_farms": [],
        }

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
    listings = [
        l for l in listings
        if float(l.get("total_credits") or 0) > 0 and not _dispute_open(l)
    ]

    # Apply criteria filters if provided
    if data.filters and isinstance(data.filters, dict):
        f_crop = (data.filters.get("crop") or "").lower().strip()
        f_loc = (data.filters.get("location") or "").lower().strip()
        f_min_p = data.filters.get("min_price")
        f_max_p = data.filters.get("max_price")
        if f_crop:
            listings = [l for l in listings if f_crop in str(l.get("crop") or "").lower()]
        if f_loc:
            listings = [l for l in listings if f_loc in str(l.get("location") or "").lower()]
        if f_min_p is not None:
            try:
                listings = [l for l in listings if float(l.get("price_per_credit") or 0) >= float(f_min_p)]
            except (ValueError, TypeError):
                pass
        if f_max_p is not None:
            try:
                listings = [l for l in listings if float(l.get("price_per_credit") or 0) <= float(f_max_p)]
            except (ValueError, TypeError):
                pass

    farm_ids = list({l.get("farm_id") for l in listings if l.get("farm_id")})
    farms_by_id = {}
    if farm_ids and db.is_ready():
        sb = db._client()
        farms_by_id = {f.get("id"): f for f in (sb.table("farms").select("id,name,badge,ndvi,geojson").in_("id", farm_ids).execute().data or [])}
    elif not db.is_ready():
        # Demo fallback: populate farms_by_id from sample_data.FARMS
        from app import sample_data
        for sf in sample_data.FARMS:
            fid = sample_data._fallback_farm_id(sf["key"])
            farms_by_id[fid] = {
                "id": fid,
                "name": sf.get("name"),
                "badge": "REGISTRY" if sf.get("score", 0) > 500 else "REGISTRY_DOC",
                "ndvi": float(sf.get("ndvi") or 0.7),
            }

    # Reference coordinates for spatial sorting (Telangana agricultural centroid default: 17.85, 79.15)
    ref_lat = 17.85
    ref_lon = 79.15
    if data.filters and isinstance(data.filters, dict):
        try:
            if "latitude" in data.filters:
                ref_lat = float(data.filters["latitude"])
            if "longitude" in data.filters:
                ref_lon = float(data.filters["longitude"])
        except (ValueError, TypeError):
            pass

    def _listing_distance(l: dict) -> float:
        fid = l.get("farm_id")
        f = farms_by_id.get(fid) or {}
        coords = None
        geojson = f.get("geojson")
        if geojson and isinstance(geojson, dict):
            try:
                from app.services.polygon_service import ring_from_geojson
                ring = ring_from_geojson(geojson)
                if len(ring) >= 3:
                    coords = (
                        sum(float(p[1]) for p in ring[:-1]) / (len(ring) - 1),
                        sum(float(p[0]) for p in ring[:-1]) / (len(ring) - 1),
                    )
            except Exception:
                coords = None
        if not coords:
            loc = str(l.get("location") or "").lower()
            if "bonakal" in loc or "khammam" in loc:
                coords = (17.18, 80.20)
            elif "yellareddy" in loc or "nizamabad" in loc:
                coords = (18.23, 78.02)
            elif "jagtial" in loc or "karimnagar" in loc:
                coords = (18.79, 78.91)
            elif "devarakonda" in loc or "nalgonda" in loc:
                coords = (16.70, 78.92)
            elif "moinabad" in loc or "rangareddy" in loc:
                coords = (17.33, 78.27)
            else:
                coords = (17.85, 79.15)
        return ((coords[0] - ref_lat) ** 2 + (coords[1] - ref_lon) ** 2) ** 0.5

    # Prioritization: price, ndvi, nearest
    if data.priority == "highest_ndvi":
        listings.sort(key=lambda l: float((farms_by_id.get(l.get("farm_id")) or {}).get("ndvi") or 0), reverse=True)
    elif data.priority == "nearest":
        listings.sort(key=_listing_distance)
    else:
        listings.sort(key=lambda l: float(l.get("price_per_credit") or 0))

    volume = target_vol
    matched = []
    farmer_share_accum = 0.0
    fpo_share_accum = 0.0
    platform_share_accum = 0.0

    for l in listings:
        if volume <= 0:
            break
        take = min(volume, float(l.get("total_credits") or 0))
        farm = farms_by_id.get(l.get("farm_id")) or {}
        badge = farm.get("badge") or "DOCUMENT"
        line_gross = round(take * float(l.get("price_per_credit") or 0), 2)
        fpo_name = _resolve_fpo_link(farm or None, l.get("farmer_phone") or "")
        line_split = split_engine.compute_split(line_gross, fpo_involved=bool(fpo_name), fpo_name=fpo_name)
        farmer_share_accum += line_split["farmer_amount_inr"]
        fpo_share_accum += line_split["fpo_amount_inr"]
        platform_share_accum += line_split["platform_amount_inr"]

        matched.append({
            "listing_id": l.get("id"),
            "farm": farm.get("name") or l.get("location") or "Telangana Parcel",
            "farmer": l.get("farmer_name") or "Marketplace Farmer",
            "survey": l.get("location"),
            "crop": l.get("crop"),
            "credits": round(take, 2),
            "rate": float(l.get("price_per_credit") or 0),
            "badge": badge,
            "badge_color": "emerald" if badge == "REGISTRY" else ("forest" if badge == "REGISTRY_DOC" else "amber"),
            "farmer_share_inr": line_split["farmer_amount_inr"],
            "fpo_name": fpo_name or None,
        })
        volume -= take

    gross = round(sum(m["credits"] * m["rate"] for m in matched), 2)
    has_fpo = any(m.get("fpo_name") for m in matched)
    split_model = "4-way" if has_fpo else "3-way"

    return {
        "success": True,
        "target_volume": target_vol,
        "total_matched": round(sum(m["credits"] for m in matched), 2),
        "gross_value": gross,
        "farmer_total_inr": round(farmer_share_accum, 2),
        "fpo_total_inr": round(fpo_share_accum, 2),
        "platform_total_inr": round(platform_share_accum, 2),
        "split_model": split_model,
        "matched_farms": matched,
    }
