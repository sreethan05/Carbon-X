"""Payment provider abstraction — simulated by default, Razorpay-ready.

No real money moves unless ``CARBONX_PAYMENTS_PROVIDER=razorpay`` AND both
``RAZORPAY_KEY_ID`` / ``RAZORPAY_KEY_SECRET`` are configured (see
``is_live()``). The simulated provider creates clearly-labelled fake orders
and settles immediately; the Razorpay provider creates real orders and
settlement happens only after a signature-verified webhook
(``app/routes/payments_router.py``).

Secrets are read from ``app.config`` at call time (so tests can override them)
and are never logged or returned in any dict. Order creation is the only
outbound network call in the payments layer (8s timeout, HTTP Basic auth).
"""
import hashlib
import hmac
import logging
import uuid

import httpx

from app import config as app_config

logger = logging.getLogger("carbonx.payments")

PROVIDER_SIMULATED = "simulated"
PROVIDER_RAZORPAY = "razorpay"
VALID_PROVIDERS = (PROVIDER_SIMULATED, PROVIDER_RAZORPAY)

RAZORPAY_API_BASE = "https://api.razorpay.com/v1"
RAZORPAY_TIMEOUT_SECONDS = 8.0


def provider_name() -> str:
    """Configured provider, normalized. Unknown values degrade to simulated."""
    name = (app_config.PAYMENTS_PROVIDER or "").strip().lower() or PROVIDER_SIMULATED
    if name not in VALID_PROVIDERS:
        logger.warning("Unknown CARBONX_PAYMENTS_PROVIDER=%r — using 'simulated'", name)
        return PROVIDER_SIMULATED
    return name


def is_live() -> bool:
    """True only when Razorpay is selected *and* both API keys are configured."""
    return (
        provider_name() == PROVIDER_RAZORPAY
        and bool((app_config.RAZORPAY_KEY_ID or "").strip())
        and bool((app_config.RAZORPAY_KEY_SECRET or "").strip())
    )


def create_order(*, listing_id: str, credits: float, amount_inr: float, receipt: str) -> dict:
    """Create a payment order for a credits purchase.

    Simulated (default): no network call, returns a labelled fake order.
    Razorpay: POST /orders with HTTP Basic auth; on provider/network failure
    returns ``{"success": False, "message": ...}`` which the caller turns into
    the uniform error envelope. Key ids/secrets never appear in the result or
    the logs.
    """
    if not is_live():
        return {
            "provider": PROVIDER_SIMULATED,
            "order_id": "SIM-" + uuid.uuid4().hex[:12],
            "status": "created",
            "simulated": True,
        }

    amount_paise = int(round(float(amount_inr or 0) * 100))  # rupees -> paise (integer)
    if amount_paise < 100:
        logger.error("Razorpay order creation rejected: amount must be at least ₹1.00 (100 paise), got %s", amount_paise)
        return {"success": False, "message": "Order amount must be at least ₹1.00"}

    payload = {
        "amount": amount_paise,
        "currency": "INR",
        "receipt": str(receipt)[:40],  # Razorpay receipt max length
        # Razorpay note values must be strings.
        "notes": {"listing_id": str(listing_id), "credits": str(credits)},
    }
    try:
        response = httpx.post(
            f"{RAZORPAY_API_BASE}/orders",
            json=payload,
            auth=(app_config.RAZORPAY_KEY_ID, app_config.RAZORPAY_KEY_SECRET),
            timeout=RAZORPAY_TIMEOUT_SECONDS,
        )
    except Exception as exc:  # timeouts/connection errors — log type only
        logger.error("Razorpay order creation failed: %s", type(exc).__name__)
        return {"success": False, "message": "Payment provider unreachable — order not created"}

    if response.status_code >= 400:
        logger.error("Razorpay order creation rejected: HTTP %s", response.status_code)
        return {"success": False, "message": f"Payment provider rejected the order (HTTP {response.status_code})"}

    try:
        data = response.json()
    except Exception:
        logger.error("Razorpay order creation returned a non-JSON response")
        return {"success": False, "message": "Payment provider returned an invalid response"}
    if not data.get("id"):
        logger.error("Razorpay order creation returned no order id")
        return {"success": False, "message": "Payment provider returned an invalid response"}

    return {
        "provider": PROVIDER_RAZORPAY,
        "order_id": data["id"],
        "status": data.get("status") or "created",
        "simulated": False,
    }


def verify_webhook_signature(raw_body: bytes, signature: str) -> bool:
    """Verify Razorpay's ``X-Razorpay-Signature``: HMAC-SHA256 of the raw body.

    Constant-time compare. False when the webhook secret isn't configured or no
    signature was supplied — a webhook can never be trusted by default.
    """
    secret = (app_config.RAZORPAY_WEBHOOK_SECRET or "").strip()
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.strip())


def verify_checkout_signature(order_id: str, payment_id: str, signature: str) -> bool:
    """Verify the Razorpay checkout-modal signature scheme.

    Razorpay signs ``"{order_id}|{payment_id}"`` with the API key secret
    (HMAC-SHA256, hex). Used when a client confirms checkout directly instead
    of relying on the webhook.
    """
    secret = (app_config.RAZORPAY_KEY_SECRET or "").strip()
    if not secret or not order_id or not payment_id or not signature:
        return False
    message = f"{order_id}|{payment_id}".encode("utf-8")
    expected = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.strip())
