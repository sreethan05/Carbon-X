"""Payments routes: provider config, checkout initiation, Razorpay webhooks.

Default provider is ``simulated``: checkout settles immediately through the
same settlement function as /marketplace/buy and the response is labelled
``simulated`` end-to-end (no money moves). With provider ``razorpay`` and both
API keys configured (``is_live()``), checkout creates a real Razorpay order
and the listing is never touched on initiate — settlement happens only after a
signature-verified ``payment.captured`` webhook.

The webhook never needs a JWT: the HMAC signature over the raw body *is* the
authentication.
"""
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from typing import Optional
import json
import logging
import threading
import time
from datetime import datetime, timezone

from app.security import get_current_user_optional
from app import redis_store
from app import supabase_db as db
from app import config as app_config
from app.routes.marketplace_router import settle_listing_purchase
from app.services import market_store, payments

logger = logging.getLogger("carbonx.payments")

router = APIRouter(prefix="/payments", tags=["payments"])

# Razorpay orders awaiting their webhook.
#
# The in-process dicts below are the fallback (single worker, no Redis, and
# what tests clear between cases). When Redis is configured every record is
# mirrored to it, so the webhook can land on ANY worker and state survives a
# restart for the record's TTL — pending orders 24h, processed outcomes 7d.
# A shared lock serializes concurrent deliveries of the same order across
# workers (no-op without Redis; _PENDING_LOCK covers threads in-process).
_PENDING_LOCK = threading.RLock()
_PENDING: dict[str, dict] = {}   # order_id -> pending purchase {listing_id, credits, buyer_name, amount_inr, created_at}
_SETTLED: dict[str, dict] = {}   # order_id -> outcome record (idempotency: settled | conflict_refund_required)

_PENDING_TTL_SECONDS = 24 * 3600
_SETTLED_TTL_SECONDS = 7 * 24 * 3600


def _pending_key(order_id: str) -> str:
    return f"carbonx:payments:pending:{order_id}"


def _settled_key(order_id: str) -> str:
    return f"carbonx:payments:settled:{order_id}"


def _pending_put(order_id: str, record: dict) -> None:
    with _PENDING_LOCK:
        if len(_PENDING) > 2048:
            excess = len(_PENDING) - 2048
            for k in list(_PENDING.keys())[:excess]:
                _PENDING.pop(k, None)
        _PENDING[order_id] = record
    redis_store.shared_set(_pending_key(order_id), json.dumps(record, default=str), _PENDING_TTL_SECONDS)


def _pending_get(order_id: str) -> Optional[dict]:
    with _PENDING_LOCK:
        local = _PENDING.get(order_id)
    if local is not None:
        return dict(local)
    raw = redis_store.shared_get(_pending_key(order_id))
    if raw:
        try:
            return json.loads(raw)
        except ValueError:
            return None
    return None


def _pending_pop(order_id: str) -> None:
    with _PENDING_LOCK:
        _PENDING.pop(order_id, None)
    redis_store.shared_delete(_pending_key(order_id))


def _settled_put(order_id: str, record: dict) -> None:
    with _PENDING_LOCK:
        if len(_SETTLED) > 4096:
            excess = len(_SETTLED) - 4096
            for k in list(_SETTLED.keys())[:excess]:
                _SETTLED.pop(k, None)
        _SETTLED[order_id] = record
    redis_store.shared_set(_settled_key(order_id), json.dumps(record, default=str), _SETTLED_TTL_SECONDS)


def _settled_get(order_id: str) -> Optional[dict]:
    with _PENDING_LOCK:
        local = _SETTLED.get(order_id)
    if local is not None:
        return dict(local)
    raw = redis_store.shared_get(_settled_key(order_id))
    if raw:
        try:
            return json.loads(raw)
        except ValueError:
            return None
    return None


class CheckoutModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    listing_id: str
    credits: float
    buyer_name: Optional[str] = "Corporate Buyer"


def _resolve_purchase(listing_id: str, credits: float) -> dict:
    """Read + validate a listing exactly like /marketplace/buy does.

    Returns ``{"error": <envelope>}`` when the listing cannot be bought, else
    ``{"listing", "credits", "apply_update", "farm"}`` where ``apply_update``
    is the provider-agnostic compare-and-swap used by
    ``settle_listing_purchase``.
    """
    if not db.is_ready():
        listing = market_store.get(listing_id)
        if not listing:
            return {"error": {"success": False, "message": "Listing not found"}}
        if str(listing.get("status") or "Active").lower() not in ("active", ""):
            return {"error": {"success": False, "message": f"Listing is no longer available (status: {listing.get('status')})"}}
        if str(listing.get("dispute_status") or "NONE").upper() in ("OPEN", "DISPUTED"):
            return {"error": {"success": False, "code": "DISPUTED", "message": "Listing is frozen while a certificate dispute is open"}}
        available = float(listing.get("total_credits") or 0)
        if available <= 0:
            return {"error": {"success": False, "message": "This listing has no purchasable credits left"}}
        resolved = round(min(float(credits or available), available), 4)
        if resolved <= 0:
            return {"error": {"success": False, "message": "Credit quantity must be greater than zero"}}
        listing["_source"] = "demo_store"
        return {
            "listing": listing,
            "credits": resolved,
            "farm": None,
            "apply_update": lambda fields: market_store.update_cas(listing_id, fields, expected_credits=available),
            "rollback_update": lambda fields: market_store.update(listing_id, fields) is not None,
        }

    try:
        sb = db._client()
        rows = (sb.table("marketplace_listings").select("*").eq("id", listing_id).execute().data) or []
    except Exception as e:
        return {"error": {"success": False, "message": str(e)}}
    if not rows:
        return {"error": {"success": False, "message": "Listing not found"}}
    listing = rows[0]
    if str(listing.get("status") or "Active").lower() not in ("active", ""):
        return {"error": {"success": False, "message": f"Listing is no longer available (status: {listing.get('status')})"}}
    if str(listing.get("dispute_status") or "NONE").upper() in ("OPEN", "DISPUTED"):
        return {"error": {"success": False, "code": "DISPUTED", "message": "Listing is frozen while a certificate dispute is open"}}
    available = float(listing.get("total_credits") or 0)
    if available <= 0:
        return {"error": {"success": False, "message": "This listing has no purchasable credits left"}}
    resolved = round(min(float(credits or available), available), 4)
    if resolved <= 0:
        return {"error": {"success": False, "message": "Credit quantity must be greater than zero"}}
    # Never write ledger events against a phantom farm (same guard as /buy).
    farm_id = listing.get("farm_id")
    farm = db.get_farm(farm_id) if farm_id else None
    if farm_id and not farm:
        return {"error": {"success": False, "message": "Listing references an unknown farm — purchase rejected"}}

    def _cas_update(fields: dict) -> bool:
        """UPDATE ... WHERE id AND status AND credit balance matched."""
        q = (
            sb.table("marketplace_listings")
            .update(fields)
            .eq("id", listing_id)
            .eq("status", listing.get("status") or "Active")
            .eq("total_credits", available)
        )
        return bool(q.select("id").execute().data)

    def _rollback_update(fields: dict) -> bool:
        try:
            res = sb.table("marketplace_listings").update(fields).eq("id", listing_id).execute()
            return bool(res.data)
        except Exception:
            core = {k: v for k, v in fields.items() if k not in ("credits_sold", "lifecycle_state")}
            res = sb.table("marketplace_listings").update(core).eq("id", listing_id).execute()
            return bool(res.data)

    return {
        "listing": listing, "credits": resolved, "apply_update": _cas_update,
        "rollback_update": _rollback_update, "farm": farm,
    }


@router.get("/config")
def payments_config():
    """Public payment configuration — never exposes keys or secrets."""
    return {"success": True, "provider": payments.provider_name(), "live": payments.is_live()}


@router.post("/checkout")
def create_checkout(
    data: CheckoutModel,
    current_user: Optional[dict] = Depends(get_current_user_optional),
):
    """Initiate a purchase.

    Simulated: settle immediately (labelled simulated). Razorpay/live: create
    the order and park a pending record — settlement only after a verified
    webhook, never on initiate.
    """
    if db.is_ready() and not current_user:
        raise HTTPException(
            status_code=401,
            detail="Sign in with a farmer or corporate account to purchase credits",
        )
    if db.is_ready() and str((current_user or {}).get("role", "")).lower() != "buyer":
        raise HTTPException(status_code=403, detail="Only corporate buyer accounts can initiate checkout")
    # In live mode the account name and id come from the authenticated token;
    # never trust a client-supplied buyer identity for certificate ownership.
    buyer = (
        (current_user or {}).get("name") or "Corporate Buyer"
        if db.is_ready() else data.buyer_name or "Corporate Buyer"
    )
    # Bind the sale to the corporate account id whenever the token has one —
    # demo and live records alike: certificate ownership is id-keyed.
    buyer_c_id = (current_user or {}).get("c_id")

    resolved = _resolve_purchase(data.listing_id, data.credits)
    if resolved.get("error"):
        return resolved["error"]
    listing = resolved["listing"]
    credits = resolved["credits"]

    if not payments.is_live():
        if db.is_ready() and not app_config.ACCEPT_SIMULATED_PAYMENTS:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Live checkout is not configured. Set Razorpay credentials, or set "
                    "CARBONX_ACCEPT_SIMULATED_PAYMENTS=1 for an explicitly simulated demo."
                ),
            )
        # Simulated provider — or razorpay selected without keys — so no real
        # money can move: settle immediately, labelled simulated everywhere.
        result = settle_listing_purchase(
            listing, credits, buyer, resolved["apply_update"],
            farm=resolved["farm"], payment_ref="SIMULATED", buyer_c_id=buyer_c_id,
            rollback_update=resolved.get("rollback_update"),
        )
        if not result.get("success"):
            return result  # CONFLICT envelope — nothing was settled
        return {"success": True, "provider": "simulated", "simulated": True, "settlement": result}

    # Razorpay live: order only. The listing deliberately stays untouched until
    # the webhook confirms the capture.
    amount_inr = round(credits * float(listing.get("price_per_credit") or 0), 2)
    receipt = f"carbonx-{str(data.listing_id).replace('-', '')[:8]}-{int(time.time())}"
    order = payments.create_order(
        listing_id=data.listing_id, credits=credits, amount_inr=amount_inr, receipt=receipt,
    )
    if order.get("success") is False or not order.get("order_id"):
        return {
            "success": False,
            "code": "PAYMENT_ORDER_FAILED",
            "message": order.get("message") or "Could not create payment order",
        }
    order_id = order["order_id"]
    _pending_put(order_id, {
        "listing_id": data.listing_id,
        "credits": credits,
        "buyer_name": buyer,
        "buyer_c_id": buyer_c_id,
        "amount_inr": amount_inr,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return {
        "success": True,
        "provider": "razorpay",
        "payment_required": True,
        "order": order,
        "checkout": {"key_id": app_config.RAZORPAY_KEY_ID, "order_id": order_id},
    }


@router.post("/webhook")
async def razorpay_webhook(
    request: Request,
    x_razorpay_signature: Optional[str] = Header(None),
):
    """Razorpay webhook receiver (no auth — the HMAC signature is the auth).

    At-least-once delivery contract:
    - bad/missing signature -> 400 INVALID_SIGNATURE (nothing is processed);
    - unknown event/order/payment -> logged, 200 ``ignored`` (Razorpay retries
      otherwise);
    - already processed order -> 200 ``duplicate`` (idempotency — a retry can
      never settle twice);
    - captured amount not matching the order -> 200
      ``conflict_refund_required`` (wrong money is never turned into credits);
    - capture against a listing that moved after the order -> 200
      ``conflict_refund_required``, recorded so retries stay duplicates. Money
      was captured but no credits exist to retire: this needs a manual refund,
      and is logged at error level.
    """
    raw_body = await request.body()
    if not payments.verify_webhook_signature(raw_body, x_razorpay_signature or ""):
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "Invalid webhook signature", "code": "INVALID_SIGNATURE"},
        )

    try:
        payload = json.loads(raw_body.decode("utf-8") or "{}")
    except Exception:
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "Invalid webhook payload", "code": "BAD_PAYLOAD"},
        )

    event = payload.get("event")
    if event != "payment.captured":
        logger.info("Payment webhook ignored (event=%s)", event)
        return {"success": True, "ignored": True}

    entity = ((payload.get("payload") or {}).get("payment") or {}).get("entity") or {}
    order_id = entity.get("order_id")
    payment_id = entity.get("id")
    if not order_id or not payment_id:
        logger.warning("Payment webhook ignored (missing order_id/payment_id)")
        return {"success": True, "ignored": True}

    if _settled_get(order_id):
        # Already processed (settled or conflict) — never settle twice.
        return {"success": True, "duplicate": True}

    # Multi-worker serialization: without Redis this is a no-op (a single
    # process is serialized by _PENDING_LOCK below); with Redis only one
    # worker settles a given order even if retries arrive concurrently.
    if not redis_store.acquire_lock(f"payments:webhook:{order_id}", 300):
        return {"success": True, "duplicate": True}

    try:
        with _PENDING_LOCK:
            if _settled_get(order_id):  # check again under in-process lock
                return {"success": True, "duplicate": True}

            pending = _pending_get(order_id)
            if not pending:
                # At-least-once delivery: an unknown order is not an error for Razorpay.
                logger.warning("Payment webhook for unknown order=%s (payment=%s) ignored", order_id, payment_id)
                return {"success": True, "ignored": True}

            expected_paise = int(round(float(pending["amount_inr"]) * 100))
            captured_paise = entity.get("amount")
            try:
                captured_val = int(captured_paise) if captured_paise is not None else None
            except (ValueError, TypeError):
                captured_val = None

            if captured_val is None or abs(captured_val - expected_paise) > 1:
                # The captured amount is missing or does not match the order amount:
                # never turn wrong money into credits — log loudly and request a refund.
                return _record_conflict(
                    order_id, payment_id,
                    f"Captured amount {captured_paise} paise does not match the order amount {expected_paise} paise",
                    pending=pending,
                )

            # Re-resolve the listing as of now: another buyer may have taken it after
            # the order was created (or the farm may have vanished on the live DB).
            resolved = _resolve_purchase(pending["listing_id"], pending["credits"])
            if resolved.get("error"):
                return _record_conflict(
                    order_id, payment_id,
                    resolved["error"].get("message") or "Listing is no longer available",
                    pending=pending,
                )

            result = settle_listing_purchase(
                resolved["listing"], resolved["credits"], pending["buyer_name"],
                resolved["apply_update"], farm=resolved["farm"],
                payment_ref=f"RZP-{payment_id}",
                rollback_update=resolved.get("rollback_update"),
                buyer_c_id=pending.get("buyer_c_id"),
            )
            if not result.get("success"):
                # Money was captured but the listing CAS lost a race — never retry into
                # a double settlement; flag it for manual refund.
                return _record_conflict(
                    order_id, payment_id,
                    result.get("message") or "Listing changed during settlement",
                    pending=pending,
                )

            _settled_put(order_id, {
                "outcome": "settled",
                "payment_id": payment_id,
                "certificate_id": result.get("certificate_id"),
                "settled_at": datetime.now(timezone.utc).isoformat(),
            })
            _pending_pop(order_id)
            return {"success": True, "settled": True, "order_id": order_id, "payment_id": payment_id, "settlement": result}
    finally:
        redis_store.release_lock(f"payments:webhook:{order_id}")


def _record_conflict(order_id: str, payment_id: str, message: str, pending: Optional[dict] = None) -> dict:
    """Money captured but the listing can no longer be settled: log loudly,
    mark the order processed (so Razorpay retries are duplicates, not a second
    settlement attempt) and request a manual refund."""
    record = {
        "outcome": "conflict_refund_required",
        "payment_id": payment_id,
        "reason": message,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    if pending:
        record["listing_id"] = pending.get("listing_id")
        record["credits"] = pending.get("credits")
        record["buyer_name"] = pending.get("buyer_name")
        record["amount_inr"] = pending.get("amount_inr")
    _settled_put(order_id, record)
    _pending_pop(order_id)
    logger.error(
        "PAYMENT CONFLICT — captured payment %s for order %s could not be settled (%s); refund required",
        payment_id, order_id, message,
    )
    return {"success": True, "outcome": "conflict_refund_required", "message": message}
