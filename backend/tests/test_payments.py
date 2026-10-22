"""Payments layer tests — provider abstraction, checkout, webhook settlement.

Hermetic: no live DB, no network. Runs in demo mode against the in-memory
market store; Razorpay paths are exercised with monkeypatched config/httpx and
locally computed HMAC signatures.

Run from backend/: python -m unittest tests.test_payments -v
"""
import hashlib
import hmac
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

for _k in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY",
           "VITE_SUPABASE_URL", "VITE_SUPABASE_ANON_KEY"):
    os.environ.pop(_k, None)
os.environ["SUPABASE_URL"] = ""
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = ""

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app import supabase_db as _db  # noqa: E402
from app import config as app_config  # noqa: E402
from app.services import market_store, payments  # noqa: E402
from app.services import ledger as ledger_service  # noqa: E402
from app.routes import payments_router as payments_routes  # noqa: E402

# post-import reset (main.py load_dotenv(override=True) re-reads backend/.env)
for _k in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY",
           "VITE_SUPABASE_URL", "VITE_SUPABASE_ANON_KEY"):
    os.environ.pop(_k, None)
os.environ["SUPABASE_URL"] = ""
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = ""
_db._supabase = None
_db._ready = False

# Payment config must never leak from a developer's backend/.env into tests.
app_config.PAYMENTS_PROVIDER = "simulated"
app_config.RAZORPAY_KEY_ID = ""
app_config.RAZORPAY_KEY_SECRET = ""
app_config.RAZORPAY_WEBHOOK_SECRET = ""

# Hermetic hash ledger: never touch the developer's backend/data/ledger.json
# (same pattern as test_integration.py).
import tempfile  # noqa: E402
from app.services import ledger as _ledger  # noqa: E402
_ledger._PATH = os.path.join(tempfile.mkdtemp(prefix="carbonx_test_payments_ledger_"), "ledger.json")
_ledger._CHAINS = {}
_ledger._MIGRATED = True

# The orchestrator registers the payments router in main.py; include it here
# defensively so this suite stays self-contained if that registration has not
# landed in the current working tree yet.
if not any(getattr(route, "path", "") == "/payments/config" for route in app.routes):
    app.include_router(payments_routes.router)

client = TestClient(app)


# ─── Helpers ───

def _active_listing() -> dict:
    rows = client.get("/marketplace/listings", params={"status": "Active"}).json()["listings"]
    assert rows, "demo store has no active listing"
    return rows[0]


def _webhook_body(order_id: str, payment_id: str, amount_paise: int = 10000,
                  event: str = "payment.captured") -> bytes:
    return json.dumps({
        "event": event,
        "payload": {"payment": {"entity": {
            "id": payment_id, "order_id": order_id,
            "amount": amount_paise, "currency": "INR",
        }}},
    }).encode("utf-8")


def _sign(body: bytes, secret: str = "whsec_test") -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


class ProviderSelectionTests(unittest.TestCase):
    def test_default_provider_is_simulated(self):
        with mock.patch.object(app_config, "PAYMENTS_PROVIDER", ""):
            self.assertEqual(payments.provider_name(), "simulated")
            self.assertFalse(payments.is_live())
        with mock.patch.object(app_config, "PAYMENTS_PROVIDER", "simulated"):
            self.assertEqual(payments.provider_name(), "simulated")
            self.assertFalse(payments.is_live())

    def test_provider_is_case_insensitive(self):
        with mock.patch.object(app_config, "PAYMENTS_PROVIDER", "RAZORPAY"):
            self.assertEqual(payments.provider_name(), "razorpay")

    def test_unknown_provider_falls_back_to_simulated(self):
        with mock.patch.object(app_config, "PAYMENTS_PROVIDER", "stripe"):
            with self.assertLogs("carbonx.payments", level="WARNING"):
                self.assertEqual(payments.provider_name(), "simulated")

    def test_razorpay_is_live_only_with_both_keys(self):
        with mock.patch.object(app_config, "PAYMENTS_PROVIDER", "razorpay"), \
             mock.patch.object(app_config, "RAZORPAY_KEY_ID", "rzp_test_key"), \
             mock.patch.object(app_config, "RAZORPAY_KEY_SECRET", ""):
            self.assertEqual(payments.provider_name(), "razorpay")
            self.assertFalse(payments.is_live(), "half-configured razorpay must never be live")
        with mock.patch.object(app_config, "PAYMENTS_PROVIDER", "razorpay"), \
             mock.patch.object(app_config, "RAZORPAY_KEY_ID", ""), \
             mock.patch.object(app_config, "RAZORPAY_KEY_SECRET", "secret"):
            self.assertFalse(payments.is_live())
        with mock.patch.object(app_config, "PAYMENTS_PROVIDER", "razorpay"), \
             mock.patch.object(app_config, "RAZORPAY_KEY_ID", "rzp_test_key"), \
             mock.patch.object(app_config, "RAZORPAY_KEY_SECRET", "secret"):
            self.assertTrue(payments.is_live())


class CreateOrderTests(unittest.TestCase):
    def test_simulated_order_shape(self):
        with mock.patch.object(app_config, "PAYMENTS_PROVIDER", "simulated"):
            order = payments.create_order(
                listing_id="listing-1", credits=2.5, amount_inr=1234.56, receipt="rcpt-1")
        self.assertEqual(order["provider"], "simulated")
        self.assertTrue(order["order_id"].startswith("SIM-"))
        self.assertEqual(len(order["order_id"]), len("SIM-") + 12)
        self.assertEqual(order["status"], "created")
        self.assertTrue(order["simulated"])

    def test_razorpay_order_payload_and_no_secret_leak(self):
        captured: dict = {}

        class FakeResponse:
            status_code = 200

            def json(self):
                return {"id": "order_TEST123", "status": "created", "amount": 12345}

        def fake_post(url, **kwargs):
            captured["url"] = url
            captured.update(kwargs)
            return FakeResponse()

        with mock.patch.object(app_config, "PAYMENTS_PROVIDER", "razorpay"), \
             mock.patch.object(app_config, "RAZORPAY_KEY_ID", "rzp_test_key"), \
             mock.patch.object(app_config, "RAZORPAY_KEY_SECRET", "secret_do_not_leak"), \
             mock.patch.object(payments.httpx, "post", fake_post):
            order = payments.create_order(
                listing_id="listing-abc", credits=4.5, amount_inr=123.45, receipt="carbonx-1")

        self.assertEqual(captured["url"], "https://api.razorpay.com/v1/orders")
        self.assertEqual(captured["json"]["amount"], 12345, "amount must be paise (integer)")
        self.assertEqual(captured["json"]["currency"], "INR")
        self.assertEqual(captured["json"]["receipt"], "carbonx-1")
        self.assertEqual(captured["json"]["notes"]["listing_id"], "listing-abc")
        self.assertEqual(captured["json"]["notes"]["credits"], "4.5")
        self.assertEqual(captured["auth"], ("rzp_test_key", "secret_do_not_leak"))
        self.assertEqual(captured["timeout"], 8.0)
        self.assertEqual(order["provider"], "razorpay")
        self.assertEqual(order["order_id"], "order_TEST123")
        self.assertFalse(order["simulated"])
        dumped = json.dumps(order)
        self.assertNotIn("secret_do_not_leak", dumped)
        self.assertNotIn("rzp_test_key", dumped)

    def test_razorpay_http_error_returns_error_dict(self):
        class FakeResponse:
            status_code = 400

            def json(self):
                return {"error": {"description": "Authentication failed"}}

        with mock.patch.object(app_config, "PAYMENTS_PROVIDER", "razorpay"), \
             mock.patch.object(app_config, "RAZORPAY_KEY_ID", "rzp_test_key"), \
             mock.patch.object(app_config, "RAZORPAY_KEY_SECRET", "secret"), \
             mock.patch.object(payments.httpx, "post", lambda *a, **k: FakeResponse()):
            order = payments.create_order(
                listing_id="listing-1", credits=1, amount_inr=100, receipt="r")
        self.assertIs(order.get("success"), False)
        self.assertIn("message", order)

    def test_razorpay_network_error_returns_error_dict(self):
        def boom(*args, **kwargs):
            raise RuntimeError("connection reset")

        with mock.patch.object(app_config, "PAYMENTS_PROVIDER", "razorpay"), \
             mock.patch.object(app_config, "RAZORPAY_KEY_ID", "rzp_test_key"), \
             mock.patch.object(app_config, "RAZORPAY_KEY_SECRET", "secret"), \
             mock.patch.object(payments.httpx, "post", boom):
            order = payments.create_order(
                listing_id="listing-1", credits=1, amount_inr=100, receipt="r")
        self.assertIs(order.get("success"), False)
        self.assertIn("message", order)


class SignatureTests(unittest.TestCase):
    def test_webhook_signature_roundtrip(self):
        body = b'{"event":"payment.captured"}'
        sig = _sign(body)
        with mock.patch.object(app_config, "RAZORPAY_WEBHOOK_SECRET", "whsec_test"):
            self.assertTrue(payments.verify_webhook_signature(body, sig))
            tampered = body + b" "
            self.assertFalse(payments.verify_webhook_signature(tampered, sig))
            self.assertFalse(payments.verify_webhook_signature(body, "deadbeef"))
            self.assertFalse(payments.verify_webhook_signature(body, ""))

    def test_webhook_signature_false_without_secret(self):
        body = b"{}"
        sig = _sign(body)
        with mock.patch.object(app_config, "RAZORPAY_WEBHOOK_SECRET", ""):
            self.assertFalse(payments.verify_webhook_signature(body, sig))

    def test_checkout_signature_scheme(self):
        with mock.patch.object(app_config, "RAZORPAY_KEY_SECRET", "key_secret"):
            sig = hmac.new(b"key_secret", b"order_1|pay_1", hashlib.sha256).hexdigest()
            self.assertTrue(payments.verify_checkout_signature("order_1", "pay_1", sig))
            self.assertFalse(payments.verify_checkout_signature("order_1", "pay_2", sig))
            self.assertFalse(payments.verify_checkout_signature("order_1", "pay_1", ""))
        with mock.patch.object(app_config, "RAZORPAY_KEY_SECRET", ""):
            self.assertFalse(payments.verify_checkout_signature("order_1", "pay_1", "anything"))


class ConfigEndpointTests(unittest.TestCase):
    def test_config_simulated(self):
        with mock.patch.object(app_config, "PAYMENTS_PROVIDER", "simulated"):
            body = client.get("/payments/config").json()
        self.assertEqual(body, {"success": True, "provider": "simulated", "live": False})

    def test_config_razorpay_never_exposes_secrets(self):
        with mock.patch.object(app_config, "PAYMENTS_PROVIDER", "razorpay"), \
             mock.patch.object(app_config, "RAZORPAY_KEY_ID", "rzp_test_key"), \
             mock.patch.object(app_config, "RAZORPAY_KEY_SECRET", "super_secret"), \
             mock.patch.object(app_config, "RAZORPAY_WEBHOOK_SECRET", "whsec_test"):
            r = client.get("/payments/config")
        self.assertEqual(r.json(), {"success": True, "provider": "razorpay", "live": True})
        self.assertNotIn("rzp_test_key", r.text)
        self.assertNotIn("super_secret", r.text)
        self.assertNotIn("whsec_test", r.text)


class SimulatedCheckoutTests(unittest.TestCase):
    def setUp(self):
        market_store.reset()
        payments_routes._PENDING.clear()
        payments_routes._SETTLED.clear()

    def test_checkout_simulated_settles_immediately(self):
        listing = _active_listing()
        with mock.patch.object(app_config, "PAYMENTS_PROVIDER", "simulated"):
            body = client.post("/payments/checkout", json={
                "listing_id": listing["id"], "credits": 1,
                "buyer_name": "Sim Checkout Corp"}).json()
        self.assertTrue(body["success"], body)
        self.assertEqual(body["provider"], "simulated")
        self.assertTrue(body["simulated"])
        settlement = body["settlement"]
        self.assertTrue(settlement["success"], settlement)
        self.assertEqual(settlement["payment_ref"], "SIMULATED")
        self.assertEqual(settlement["credits_purchased"], 1)
        self.assertFalse(settlement["retired"])
        # partial purchase: listing stays Active with fewer credits, tx_hash set
        row = market_store.get(listing["id"])
        self.assertEqual(str(row["status"]), "Active")
        self.assertAlmostEqual(float(row["total_credits"]),
                               float(listing["total_credits"]) - 1, places=4)
        self.assertTrue(row["tx_hash"])

    def test_checkout_unknown_listing_rejected(self):
        with mock.patch.object(app_config, "PAYMENTS_PROVIDER", "simulated"):
            body = client.post("/payments/checkout", json={
                "listing_id": "no-such-listing", "credits": 1}).json()
        self.assertFalse(body["success"])
        self.assertEqual(body["message"], "Listing not found")

    def test_checkout_retired_listing_rejected(self):
        listing = _active_listing()
        with mock.patch.object(app_config, "PAYMENTS_PROVIDER", "simulated"):
            first = client.post("/payments/checkout", json={
                "listing_id": listing["id"], "credits": listing["total_credits"]}).json()
            self.assertTrue(first["success"], first)
            self.assertTrue(first["settlement"]["retired"], first)
            second = client.post("/payments/checkout", json={
                "listing_id": listing["id"], "credits": 1}).json()
        self.assertFalse(second["success"])
        self.assertIn("no longer available", second["message"])
        self.assertEqual(str(market_store.get(listing["id"])["status"]), "Retired")

    def test_marketplace_buy_response_shape_unchanged(self):
        """/marketplace/buy must not gain a payment_ref key (provider-less path)."""
        listing = _active_listing()
        body = client.post("/marketplace/buy", json={
            "listing_id": listing["id"], "credits": 1,
            "buyer_name": "Legacy Buy Corp"}).json()
        self.assertTrue(body["success"], body)
        self.assertNotIn("payment_ref", body)
        self.assertNotIn("provider", body)


class RazorpayWebhookFlowTests(unittest.TestCase):
    """End-to-end: initiate (razorpay) -> verified webhook -> settlement."""

    def setUp(self):
        market_store.reset()
        payments_routes._PENDING.clear()
        payments_routes._SETTLED.clear()

    def _razorpay_env(self):
        return mock.patch.multiple(
            app_config,
            PAYMENTS_PROVIDER="razorpay",
            RAZORPAY_KEY_ID="rzp_test_key",
            RAZORPAY_KEY_SECRET="key_secret",
            RAZORPAY_WEBHOOK_SECRET="whsec_test",
        )

    def test_webhook_settlement_end_to_end_and_idempotent(self):
        listing = _active_listing()
        credits = float(listing["total_credits"])
        amount_paise = int(round(credits * float(listing["price_per_credit"]) * 100))
        fake_order = {"provider": "razorpay", "order_id": "order_e2e_1",
                      "status": "created", "simulated": False}

        with self._razorpay_env(), \
             mock.patch.object(payments, "create_order", return_value=fake_order) as create:
            checkout = client.post("/payments/checkout", json={
                "listing_id": listing["id"], "credits": credits,
                "buyer_name": "Razorpay Test Corp"}).json()
        self.assertTrue(checkout["success"], checkout)
        self.assertEqual(checkout["provider"], "razorpay")
        self.assertTrue(checkout["payment_required"])
        self.assertEqual(checkout["checkout"]["key_id"], "rzp_test_key")
        self.assertEqual(checkout["checkout"]["order_id"], "order_e2e_1")
        self.assertFalse(checkout.get("simulated"))
        self.assertTrue(create.called)
        # initiate must NOT settle
        self.assertEqual(str(market_store.get(listing["id"])["status"]), "Active")

        raw = _webhook_body("order_e2e_1", "pay_e2e_1", amount_paise)
        headers = {"X-Razorpay-Signature": _sign(raw), "Content-Type": "application/json"}
        with self._razorpay_env():
            r = client.post("/payments/webhook", content=raw, headers=headers)
        result = r.json()
        self.assertTrue(result["success"], result)
        self.assertTrue(result["settled"])
        settlement = result["settlement"]
        self.assertTrue(settlement["success"], settlement)
        self.assertEqual(settlement["payment_ref"], "RZP-pay_e2e_1")
        self.assertTrue(settlement["retired"])

        row = market_store.get(listing["id"])
        self.assertEqual(row["status"], "Retired")
        self.assertTrue(row["tx_hash"])

        # the SALE ledger event carries the provider payment ref (internal
        # audit view; the public /ledger endpoint redacts payment refs)
        internal_events = ledger_service.get_chain(settlement["farm_id"])
        tagged = [e for e in internal_events
                  if e.get("type") == "SALE"
                  and (e.get("payload") or {}).get("payment_ref") == "RZP-pay_e2e_1"]
        self.assertEqual(len(tagged), 1)
        self.assertEqual(tagged[0]["payload"]["listing_id"], listing["id"])

        # duplicate webhook: idempotent, chain does not grow, no second settle
        with self._razorpay_env():
            dup = client.post("/payments/webhook", content=raw, headers=headers).json()
        self.assertTrue(dup["success"])
        self.assertTrue(dup["duplicate"])
        chain2 = ledger_service.get_chain(settlement["farm_id"])
        self.assertEqual(len(chain2), len(internal_events))
        self.assertEqual(str(market_store.get(listing["id"])["status"]), "Retired")

    def test_webhook_invalid_signature_rejected_400(self):
        raw = _webhook_body("order_1", "pay_1")
        with self._razorpay_env():
            r = client.post("/payments/webhook", content=raw,
                            headers={"X-Razorpay-Signature": "deadbeef"})
        self.assertEqual(r.status_code, 400)
        body = r.json()
        self.assertFalse(body["success"])
        self.assertEqual(body["code"], "INVALID_SIGNATURE")

    def test_webhook_missing_signature_rejected_400(self):
        raw = _webhook_body("order_1", "pay_1")
        with self._razorpay_env():
            r = client.post("/payments/webhook", content=raw)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["code"], "INVALID_SIGNATURE")

    def test_webhook_unknown_event_ignored(self):
        raw = _webhook_body("order_1", "pay_1", event="payment.failed")
        with self._razorpay_env():
            r = client.post("/payments/webhook", content=raw,
                            headers={"X-Razorpay-Signature": _sign(raw)})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"success": True, "ignored": True})

    def test_webhook_unknown_order_ignored(self):
        raw = _webhook_body("order_that_never_existed", "pay_1")
        with self._razorpay_env():
            r = client.post("/payments/webhook", content=raw,
                            headers={"X-Razorpay-Signature": _sign(raw)})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"success": True, "ignored": True})

    def test_webhook_conflict_after_concurrent_buy_flags_refund(self):
        listing = _active_listing()
        credits = float(listing["total_credits"])
        fake_order = {"provider": "razorpay", "order_id": "order_conflict_1",
                      "status": "created", "simulated": False}
        with self._razorpay_env(), \
             mock.patch.object(payments, "create_order", return_value=fake_order):
            checkout = client.post("/payments/checkout", json={
                "listing_id": listing["id"], "credits": credits}).json()
        self.assertTrue(checkout["success"], checkout)

        # a faster buyer settles the listing before the webhook arrives
        direct = client.post("/marketplace/buy", json={
            "listing_id": listing["id"], "credits": credits,
            "buyer_name": "Faster Corp"}).json()
        self.assertTrue(direct["success"], direct)

        amount_paise = int(round(credits * float(listing["price_per_credit"]) * 100))
        raw = _webhook_body("order_conflict_1", "pay_conflict_1", amount_paise=amount_paise)
        headers = {"X-Razorpay-Signature": _sign(raw), "Content-Type": "application/json"}
        with self._razorpay_env():
            r = client.post("/payments/webhook", content=raw, headers=headers)
        body = r.json()
        self.assertEqual(r.status_code, 200)
        self.assertTrue(body["success"])
        self.assertEqual(body.get("outcome"), "conflict_refund_required")
        self.assertIn("no longer available", body.get("message", ""))

        # retry is recorded as already processed — never a second settlement
        with self._razorpay_env():
            retry = client.post("/payments/webhook", content=raw, headers=headers).json()
        self.assertEqual(retry, {"success": True, "duplicate": True})

        chain = client.get(f"/ledger/{direct['farm_id']}").json()
        tagged = [e for e in chain["events"]
                  if (e.get("payload") or {}).get("payment_ref") == "RZP-pay_conflict_1"]
        self.assertEqual(tagged, [], "a conflicted capture must never write ledger events")

    def test_webhook_amount_mismatch_flags_refund(self):
        listing = _active_listing()
        credits = float(listing["total_credits"])
        fake_order = {"provider": "razorpay", "order_id": "order_mismatch_1",
                      "status": "created", "simulated": False}
        with self._razorpay_env(), \
             mock.patch.object(payments, "create_order", return_value=fake_order):
            checkout = client.post("/payments/checkout", json={
                "listing_id": listing["id"], "credits": credits}).json()
        self.assertTrue(checkout["success"], checkout)

        # Webhook with wrong amount (e.g. ₹100 instead of full listing amount)
        raw = _webhook_body("order_mismatch_1", "pay_mismatch_1", amount_paise=10000)
        headers = {"X-Razorpay-Signature": _sign(raw), "Content-Type": "application/json"}
        with self._razorpay_env():
            r = client.post("/payments/webhook", content=raw, headers=headers)
        body = r.json()
        self.assertEqual(r.status_code, 200)
        self.assertTrue(body["success"])
        self.assertEqual(body.get("outcome"), "conflict_refund_required")
        self.assertIn("does not match the order amount", body.get("message", ""))

    def test_webhook_missing_amount_flags_refund(self):
        listing = _active_listing()
        credits = 1.0
        fake_order = {"provider": "razorpay", "order_id": "order_no_amount_1",
                      "status": "created", "simulated": False}
        with self._razorpay_env(), \
             mock.patch.object(payments, "create_order", return_value=fake_order):
            checkout = client.post("/payments/checkout", json={
                "listing_id": listing["id"], "credits": credits}).json()
        self.assertTrue(checkout["success"], checkout)

        # Webhook payload with missing amount
        body_dict = {
            "event": "payment.captured",
            "payload": {"payment": {"entity": {
                "id": "pay_no_amount_1", "order_id": "order_no_amount_1",
            }}},
        }
        raw = json.dumps(body_dict).encode("utf-8")
        headers = {"X-Razorpay-Signature": _sign(raw), "Content-Type": "application/json"}
        with self._razorpay_env():
            r = client.post("/payments/webhook", content=raw, headers=headers)
        body = r.json()
        self.assertEqual(r.status_code, 200)
        self.assertTrue(body["success"])
        self.assertEqual(body.get("outcome"), "conflict_refund_required")

    def test_order_min_amount_validation(self):
        with self._razorpay_env():
            order = payments.create_order(
                listing_id="listing-1", credits=1, amount_inr=0.5, receipt="r",
            )
        self.assertFalse(order.get("success"))
        self.assertIn("at least ₹1.00", order.get("message", ""))


if __name__ == "__main__":
    unittest.main()
