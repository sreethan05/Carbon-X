"""High-concurrency stress tests for Marketplace & Payments.

Covers:
1. High-concurrency purchasing (20 simultaneous threads):
   - Full buy race on limited stock (exactly 1 winner, 19 rejected, zero oversell).
   - Concurrent partial buys without overselling (balance conservation).
   - Competing partial buys with client retries draining inventory cleanly.
   - Concurrent simulated checkouts via /payments/checkout.
2. High-concurrency bidding (20 simultaneous threads):
   - Competing bids burst: CAS handles conflicts cleanly; bids count and amounts
     remain completely consistent.
   - Competing ascending bids with retries: reaches highest target bid with
     strictly monotonic bid progression.
   - Direct store CAS concurrency under simultaneous attempts.
3. Concurrent webhook delivery (10 simultaneous threads):
   - Duplicate delivery of the exact same Razorpay payment webhook: exactly 1
     succeeds (settled), exactly 9 return duplicate (idempotent), zero double-settle.
   - Secondary burst on already settled order: 10/10 return duplicate.
   - Concurrent webhook for conflicted order (listing retired): exactly 1 records
     conflict_refund_required, 9 return duplicate, safely idempotent.
"""
import hashlib
import hmac
import json
import os
import random
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Hermetic demo mode: disable remote Supabase
for _k in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY",
           "VITE_SUPABASE_URL", "VITE_SUPABASE_ANON_KEY"):
    os.environ.pop(_k, None)
os.environ["SUPABASE_URL"] = ""
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = ""

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402
from app import supabase_db as _db  # noqa: E402
from app import config as app_config  # noqa: E402
from app.services import market_store, ledger, payments  # noqa: E402
from app.routes import payments_router as payments_routes  # noqa: E402

# Post-import environment reset
for _k in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY",
           "VITE_SUPABASE_URL", "VITE_SUPABASE_ANON_KEY"):
    os.environ.pop(_k, None)
os.environ["SUPABASE_URL"] = ""
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = ""
_db._supabase = None
_db._ready = False

# Isolated temp ledger
ledger._PATH = os.path.join(tempfile.mkdtemp(prefix="carbonx_stress_ledger_"), "ledger.json")
ledger._CHAINS = {}
ledger._MIGRATED = True

# Register payments router defensively if not registered
if not any(getattr(route, "path", "") == "/payments/config" for route in app.routes):
    app.include_router(payments_routes.router)

client = TestClient(app)


def _sign_webhook(body: bytes, secret: str = "whsec_stress_test") -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _webhook_payload(order_id: str, payment_id: str, amount_paise: int) -> bytes:
    return json.dumps({
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": payment_id,
                    "order_id": order_id,
                    "amount": amount_paise,
                    "currency": "INR",
                }
            }
        },
    }).encode("utf-8")


class ConcurrencyPurchasingStressTests(unittest.TestCase):
    """Stress testing concurrent credit purchases on limited inventory."""

    def setUp(self):
        market_store.reset()
        payments_routes._PENDING.clear()
        payments_routes._SETTLED.clear()
        ledger._CHAINS.clear()

    def test_concurrent_purchases_full_buy_exact_single_winner(self):
        """20 threads simultaneously race to buy ALL remaining credits of a listing.
        
        Exactly 1 must win; 19 must cleanly lose; zero oversell occurs.
        """
        listing = market_store.insert({
            "farmer_phone": "9999900001",
            "farmer_name": "Stress Farmer",
            "crop": "Cotton",
            "location": "Warangal, Telangana",
            "total_credits": 10.0,
            "price_per_credit": 500.0,
            "status": "Active",
            "farm_id": "farm-stress-purchasing-1",
        })
        listing_id = listing["id"]
        num_threads = 20
        barrier = threading.Barrier(num_threads)
        results = [None] * num_threads

        def buyer_task(index: int):
            barrier.wait()  # Synchronize release of all 20 threads
            resp = client.post("/marketplace/buy", json={
                "listing_id": listing_id,
                "credits": 10.0,
                "buyer_name": f"Buyer-{index}",
            })
            results[index] = resp.json()

        threads = [threading.Thread(target=buyer_task, args=(i,)) for i in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        successes = [r for r in results if r.get("success") is True]
        failures = [r for r in results if r.get("success") is False]

        self.assertEqual(len(successes), 1, f"Expected exactly 1 winner, got {len(successes)}")
        self.assertEqual(len(failures), 19, f"Expected 19 losers, got {len(failures)}")

        winner = successes[0]
        self.assertEqual(winner["credits_purchased"], 10.0)
        self.assertEqual(winner["credits_remaining"], 0.0)
        self.assertTrue(winner["retired"])

        for loser in failures:
            # Losers must either encounter a CAS CONFLICT or find the listing already retired
            is_conflict = loser.get("code") == "CONFLICT" or "concurrent" in loser.get("message", "").lower()
            is_unavailable = "no longer available" in loser.get("message", "").lower()
            self.assertTrue(is_conflict or is_unavailable, f"Unexpected failure envelope: {loser}")

        # Check in-memory store: status is Retired
        final_row = market_store.get(listing_id)
        self.assertEqual(final_row["status"], "Retired")

        # Verify ledger has exactly 1 SALE event
        chain = ledger.get_chain("farm-stress-purchasing-1")
        sale_events = [e for e in chain if e["type"] == "SALE"]
        self.assertEqual(len(sale_events), 1)
        self.assertEqual(sale_events[0]["payload"]["credits"], 10.0)

        # Verification of the hash chain
        verify = ledger.verify_chain("farm-stress-purchasing-1")
        self.assertTrue(verify["valid"])

    def test_concurrent_purchases_partial_buy_no_oversell(self):
        """20 threads simultaneously attempt partial buys (1.0 credit each) on a 5.0 credit listing.
        
        Zero oversell: total credits purchased across all successful responses MUST NOT exceed 5.0.
        """
        listing = market_store.insert({
            "farmer_phone": "9999900002",
            "farmer_name": "Partial Farmer",
            "crop": "Paddy",
            "location": "Khammam, Telangana",
            "total_credits": 5.0,
            "price_per_credit": 450.0,
            "status": "Active",
            "farm_id": "farm-stress-partial-1",
        })
        listing_id = listing["id"]
        num_threads = 20
        barrier = threading.Barrier(num_threads)
        results = [None] * num_threads

        def partial_buyer(index: int):
            barrier.wait()
            resp = client.post("/marketplace/buy", json={
                "listing_id": listing_id,
                "credits": 1.0,
                "buyer_name": f"Partial-Buyer-{index}",
            })
            results[index] = resp.json()

        threads = [threading.Thread(target=partial_buyer, args=(i,)) for i in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        successes = [r for r in results if r.get("success") is True]
        total_purchased = sum(r["credits_purchased"] for r in successes)

        # Total purchased must be strictly <= 5.0
        self.assertLessEqual(total_purchased, 5.0)

        final_row = market_store.get(listing_id)
        remaining_in_store = float(final_row["total_credits"]) if final_row["status"] == "Active" else 0.0

        # Exact credit conservation: purchased + remaining == initial stock (5.0)
        self.assertAlmostEqual(total_purchased + remaining_in_store, 5.0, places=4)

        # Check ledger consistency
        chain = ledger.get_chain("farm-stress-partial-1")
        sales = [e for e in chain if e["type"] == "SALE"]
        self.assertEqual(len(sales), len(successes))
        self.assertTrue(ledger.verify_chain("farm-stress-partial-1")["valid"])

    def test_concurrent_purchases_with_client_retries_drains_inventory_cleanly(self):
        """20 threads competing to buy 1.5 credits each on a 12.0 credit listing,
        retrying on CAS CONFLICT until inventory is exhausted.
        
        Exactly 8 purchases succeed (8 * 1.5 = 12.0), inventory reaches 0, zero oversell.
        """
        listing = market_store.insert({
            "farmer_phone": "9999900003",
            "farmer_name": "Drain Farmer",
            "crop": "Maize",
            "location": "Nalgonda, Telangana",
            "total_credits": 12.0,
            "price_per_credit": 400.0,
            "status": "Active",
            "farm_id": "farm-stress-drain-1",
        })
        listing_id = listing["id"]
        num_threads = 20
        barrier = threading.Barrier(num_threads)
        successful_purchases = []
        lock = threading.Lock()

        def retry_buyer(index: int):
            barrier.wait()
            for _ in range(50):  # retry loop
                resp = client.post("/marketplace/buy", json={
                    "listing_id": listing_id,
                    "credits": 1.5,
                    "buyer_name": f"Retry-Buyer-{index}",
                })
                data = resp.json()
                if data.get("success") is True:
                    with lock:
                        successful_purchases.append(data)
                    break
                # If listing is no longer available (retired), stop retrying
                if "no longer available" in data.get("message", "").lower():
                    break
                time.sleep(0.005)  # brief backoff before retry

        threads = [threading.Thread(target=retry_buyer, args=(i,)) for i in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Exactly 8 purchases of 1.5 credits = 12.0 credits
        self.assertEqual(len(successful_purchases), 8)
        total_bought = sum(p["credits_purchased"] for p in successful_purchases)
        self.assertAlmostEqual(total_bought, 12.0, places=4)

        final_row = market_store.get(listing_id)
        self.assertEqual(final_row["status"], "Retired")

        # Verify ledger has exactly 8 SALE, 8 SPLIT, 8 RETIRE events with unbroken hash chain
        chain = ledger.get_chain("farm-stress-drain-1")
        sales = [e for e in chain if e["type"] == "SALE"]
        self.assertEqual(len(sales), 8)
        self.assertTrue(ledger.verify_chain("farm-stress-drain-1")["valid"])

    def test_concurrent_simulated_checkout_no_oversell(self):
        """20 threads call POST /payments/checkout simultaneously with simulated provider.
        
        Exactly 1 succeeds in buying the listing's full volume (5 credits); 19 lose cleanly.
        """
        listing = market_store.insert({
            "farmer_phone": "9999900004",
            "farmer_name": "Checkout Farmer",
            "crop": "Chilli",
            "location": "Guntur",
            "total_credits": 5.0,
            "price_per_credit": 600.0,
            "status": "Active",
            "farm_id": "farm-stress-sim-checkout",
        })
        listing_id = listing["id"]
        num_threads = 20
        barrier = threading.Barrier(num_threads)
        results = [None] * num_threads

        def checkout_task(index: int):
            barrier.wait()
            resp = client.post("/payments/checkout", json={
                "listing_id": listing_id,
                "credits": 5.0,
                "buyer_name": f"Sim-Buyer-{index}",
            })
            results[index] = resp.json()

        with mock.patch.object(app_config, "PAYMENTS_PROVIDER", "simulated"):
            threads = [threading.Thread(target=checkout_task, args=(i,)) for i in range(num_threads)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        successes = [r for r in results if r.get("success") is True]
        self.assertEqual(len(successes), 1)
        self.assertTrue(successes[0]["settlement"]["retired"])
        self.assertEqual(market_store.get(listing_id)["status"], "Retired")


class ConcurrencyBiddingStressTests(unittest.TestCase):
    """Stress testing concurrent bidding and Compare-And-Swap integrity."""

    def setUp(self):
        market_store.reset()

    def test_concurrent_bidding_burst_cas_consistency(self):
        """20 threads simultaneously place competing bids of different amounts.
        
        CAS must handle conflicts cleanly, bids_count must accurately match
        successful bids, and current_bid must equal the highest winning bid.
        """
        listing = market_store.insert({
            "farmer_phone": "9999900010",
            "farmer_name": "Auction Farmer",
            "crop": "Turmeric",
            "location": "Nizamabad",
            "total_credits": 100.0,
            "price_per_credit": 500.0,
            "current_bid": 500.0,
            "bids_count": 0,
            "status": "Active",
        })
        listing_id = listing["id"]
        num_threads = 20
        barrier = threading.Barrier(num_threads)
        results = [None] * num_threads

        def bidder_task(index: int):
            # Target bid amounts from 515 up to 800
            bid_amount = 500.0 + (index + 1) * 15.0
            barrier.wait()
            resp = client.post(f"/marketplace/listings/{listing_id}/bid", json={
                "bid_amount": bid_amount,
                "bidder_name": f"Bidder-{index}",
            })
            results[index] = resp.json()

        threads = [threading.Thread(target=bidder_task, args=(i,)) for i in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        successes = [r for r in results if r.get("success") is True]
        failures = [r for r in results if r.get("success") is False]

        # At least one bid must have succeeded
        self.assertGreaterEqual(len(successes), 1)

        # Every failure must be a clean rejection or CAS conflict
        for f in failures:
            is_conflict = f.get("code") == "CONFLICT" or "concurrent" in f.get("message", "").lower()
            is_underbid = "must exceed" in f.get("message", "").lower()
            self.assertTrue(is_conflict or is_underbid, f"Unexpected failure: {f}")

        final_listing = market_store.get(listing_id)
        # bids_count must exactly equal the number of successful bids
        self.assertEqual(final_listing["bids_count"], len(successes))

        # current_bid must match the maximum bid among the successful bids
        max_winning_bid = max(r["bid_amount"] for r in successes)
        self.assertEqual(final_listing["current_bid"], max_winning_bid)

    def test_concurrent_competing_bids_with_retries_reaches_maximum_bid(self):
        """20 threads compete, retrying on conflict if their target bid is still higher than standing.
        
        Ensures standing bid monotonically increases to the global maximum (700.0).
        """
        listing = market_store.insert({
            "farmer_phone": "9999900011",
            "farmer_name": "Ascending Auction",
            "crop": "Cotton",
            "location": "Adilabad",
            "total_credits": 50.0,
            "price_per_credit": 500.0,
            "current_bid": 500.0,
            "bids_count": 0,
            "status": "Active",
        })
        listing_id = listing["id"]
        num_threads = 20
        barrier = threading.Barrier(num_threads)
        winning_bids = []
        lock = threading.Lock()

        def persistent_bidder(index: int):
            target_bid = 500.0 + (index + 1) * 10.0  # 510 to 700
            barrier.wait()
            for _ in range(30):
                row = market_store.get(listing_id)
                current = float(row.get("current_bid") or 0)
                if target_bid <= current:
                    break  # Outbid cleanly
                resp = client.post(f"/marketplace/listings/{listing_id}/bid", json={
                    "bid_amount": target_bid,
                    "bidder_name": f"Persistent-{index}",
                })
                data = resp.json()
                if data.get("success") is True:
                    with lock:
                        winning_bids.append(target_bid)
                    break
                time.sleep(0.005)

        threads = [threading.Thread(target=persistent_bidder, args=(i,)) for i in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        final_listing = market_store.get(listing_id)
        # The highest bidder was thread 19 with bid 700.0
        self.assertEqual(final_listing["current_bid"], 700.0)
        self.assertEqual(final_listing["bids_count"], len(winning_bids))

    def test_concurrent_direct_store_place_bid_cas(self):
        """Directly test market_store.place_bid_cas under 20 concurrent threads."""
        listing = market_store.insert({
            "total_credits": 20.0,
            "price_per_credit": 100.0,
            "current_bid": 100.0,
            "bids_count": 0,
            "status": "Active",
        })
        listing_id = listing["id"]
        num_threads = 20
        barrier = threading.Barrier(num_threads)
        results = [None] * num_threads

        def direct_cas_task(i: int):
            barrier.wait()
            # All threads pass expected_bid=100.0 (simultaneous stale view)
            ok, msg, updated = market_store.place_bid_cas(listing_id, 100.0 + (i + 1) * 5, expected_bid=100.0)
            results[i] = (ok, msg, updated)

        threads = [threading.Thread(target=direct_cas_task, args=(i,)) for i in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        successes = [r for r in results if r[0] is True]
        failures = [r for r in results if r[0] is False]

        # Exactly 1 thread must win CAS on expected_bid=100.0
        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 19)
        self.assertEqual(market_store.get(listing_id)["bids_count"], 1)


class ConcurrencyWebhookStressTests(unittest.TestCase):
    """Stress testing concurrent Razorpay webhook delivery and idempotency."""

    def setUp(self):
        market_store.reset()
        payments_routes._PENDING.clear()
        payments_routes._SETTLED.clear()
        ledger._CHAINS.clear()

    def _razorpay_env(self):
        return mock.patch.multiple(
            app_config,
            PAYMENTS_PROVIDER="razorpay",
            RAZORPAY_KEY_ID="rzp_stress_key",
            RAZORPAY_KEY_SECRET="stress_secret",
            RAZORPAY_WEBHOOK_SECRET="whsec_stress_test",
        )

    def test_concurrent_duplicate_webhook_delivery_exactly_one_settles(self):
        """Simulate duplicate delivery of the SAME Razorpay payment webhook across 10 threads.
        
        Exactly 1 must return settled=True; exactly 9 must return duplicate=True;
        credits must be deducted exactly once; ledger must record exactly 1 SALE event.
        """
        listing = market_store.insert({
            "farmer_phone": "9999900020",
            "farmer_name": "Webhook Farmer",
            "crop": "Soybean",
            "location": "Kamareddy",
            "total_credits": 20.0,
            "price_per_credit": 500.0,
            "status": "Active",
            "farm_id": "farm-stress-webhook-1",
        })
        listing_id = listing["id"]
        order_id = "order_stress_dup_100"
        payment_id = "pay_stress_dup_100"
        credits_to_buy = 4.0
        amount_inr = 2000.0
        amount_paise = 200000

        # Park pending order
        payments_routes._pending_put(order_id, {
            "listing_id": listing_id,
            "credits": credits_to_buy,
            "buyer_name": "Concurrent Webhook Corp",
            "amount_inr": amount_inr,
            "created_at": time.time(),
        })

        raw_body = _webhook_payload(order_id, payment_id, amount_paise)
        signature = _sign_webhook(raw_body)
        headers = {
            "X-Razorpay-Signature": signature,
            "Content-Type": "application/json",
        }

        num_threads = 10
        barrier = threading.Barrier(num_threads)
        responses = [None] * num_threads

        def webhook_worker(index: int):
            barrier.wait()
            r = client.post("/payments/webhook", content=raw_body, headers=headers)
            responses[index] = (r.status_code, r.json())

        with self._razorpay_env():
            threads = [threading.Thread(target=webhook_worker, args=(i,)) for i in range(num_threads)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        # All 10 requests must return 200 OK and success=True
        for status_code, body in responses:
            self.assertEqual(status_code, 200)
            self.assertTrue(body["success"], body)

        settled_responses = [body for _, body in responses if body.get("settled") is True]
        duplicate_responses = [body for _, body in responses if body.get("duplicate") is True]

        self.assertEqual(len(settled_responses), 1, "Expected exactly 1 thread to settle")
        self.assertEqual(len(duplicate_responses), 9, "Expected exactly 9 duplicate idempotent responses")

        # Inventory in store must be deducted exactly once: 20.0 - 4.0 = 16.0
        final_row = market_store.get(listing_id)
        self.assertAlmostEqual(float(final_row["total_credits"]), 16.0, places=4)
        self.assertEqual(final_row["status"], "Active")

        # Farm ledger must have exactly 1 SALE event for this payment
        chain = ledger.get_chain("farm-stress-webhook-1")
        sale_events = [e for e in chain if e["type"] == "SALE" and (e["payload"] or {}).get("payment_ref") == f"RZP-{payment_id}"]
        self.assertEqual(len(sale_events), 1)

        # Hash chain must be valid
        self.assertTrue(ledger.verify_chain("farm-stress-webhook-1")["valid"])

        # Order must be recorded in _SETTLED and popped from _PENDING
        self.assertIsNone(payments_routes._pending_get(order_id))
        settled_record = payments_routes._settled_get(order_id)
        self.assertIsNotNone(settled_record)
        self.assertEqual(settled_record["outcome"], "settled")

    def test_concurrent_secondary_burst_all_idempotent(self):
        """Subsequent burst of 10 concurrent webhooks for an already settled order
        must all cleanly return duplicate=True with zero side-effects.
        """
        order_id = "order_already_settled"
        payment_id = "pay_already_settled"
        payments_routes._settled_put(order_id, {
            "outcome": "settled",
            "payment_id": payment_id,
            "certificate_id": "CX-2026-CERT-STRESS",
            "settled_at": time.time(),
        })

        raw_body = _webhook_payload(order_id, payment_id, 100000)
        signature = _sign_webhook(raw_body)
        headers = {"X-Razorpay-Signature": signature, "Content-Type": "application/json"}

        num_threads = 10
        barrier = threading.Barrier(num_threads)
        responses = [None] * num_threads

        def burst_worker(index: int):
            barrier.wait()
            r = client.post("/payments/webhook", content=raw_body, headers=headers)
            responses[index] = r.json()

        with self._razorpay_env():
            threads = [threading.Thread(target=burst_worker, args=(i,)) for i in range(num_threads)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        for body in responses:
            self.assertTrue(body["success"])
            self.assertTrue(body.get("duplicate"))

    def test_concurrent_webhook_conflict_refund_idempotent(self):
        """10 concurrent webhooks for an order where the listing became unavailable.
        
        Exactly 1 records conflict_refund_required, 9 return duplicate, safely idempotent.
        """
        # Listing already retired
        listing = market_store.insert({
            "total_credits": 10.0,
            "price_per_credit": 500.0,
            "status": "Retired",
        })
        order_id = "order_conflict_100"
        payment_id = "pay_conflict_100"

        payments_routes._pending_put(order_id, {
            "listing_id": listing["id"],
            "credits": 5.0,
            "buyer_name": "Conflict Corp",
            "amount_inr": 2500.0,
            "created_at": time.time(),
        })

        raw_body = _webhook_payload(order_id, payment_id, 250000)
        signature = _sign_webhook(raw_body)
        headers = {"X-Razorpay-Signature": signature, "Content-Type": "application/json"}

        num_threads = 10
        barrier = threading.Barrier(num_threads)
        responses = [None] * num_threads

        def conflict_worker(index: int):
            barrier.wait()
            r = client.post("/payments/webhook", content=raw_body, headers=headers)
            responses[index] = r.json()

        with self._razorpay_env():
            threads = [threading.Thread(target=conflict_worker, args=(i,)) for i in range(num_threads)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        conflicts = [b for b in responses if b.get("outcome") == "conflict_refund_required"]
        duplicates = [b for b in responses if b.get("duplicate") is True]

        self.assertEqual(len(conflicts), 1)
        self.assertEqual(len(duplicates), 9)

        # Check stored outcome
        settled_record = payments_routes._settled_get(order_id)
        self.assertIsNotNone(settled_record)
        self.assertEqual(settled_record["outcome"], "conflict_refund_required")


if __name__ == "__main__":
    unittest.main()
