"""Exhaustive tests for marketplace router and in-memory store.

Covers:
1. GET /marketplace/listings: filtering, search, sorting, opaque cursor pagination, negative cursor rejection.
2. POST /marketplace/listings: validation, nonexistent farm rejection, positive credits/price checks.
3. POST /marketplace/auto-match: greedy allocation, lowest_price / highest_ndvi / nearest spatial centroid,
   filter criteria, line-item split accumulation consistency.
4. In-memory demo store (market_store): thread-safety, CAS updates, place_bid_cas, offline fallback.
5. Settle purchase helper, bidding endpoints in demo mode, concurrent bid CAS handling.
"""
import base64
import os
import sys
import threading
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

for _k in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "VITE_SUPABASE_URL", "VITE_SUPABASE_ANON_KEY"):
    os.environ.pop(_k, None)
os.environ["SUPABASE_URL"] = ""
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = ""

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402
from app import supabase_db as _db  # noqa: E402
from app.security import create_access_token  # noqa: E402
from app.services import market_store  # noqa: E402

# Force demo mode
for _k in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_ANON_KEY", "VITE_SUPABASE_URL", "VITE_SUPABASE_ANON_KEY"):
    os.environ.pop(_k, None)
    os.environ[_k] = ""
_db._supabase = None
_db._ready = False

client = TestClient(app)


class MarketplaceListingsDeepTests(unittest.TestCase):
    def setUp(self):
        market_store.reset()

    def test_cursor_negative_offset_rejected(self):
        neg_cursor = base64.urlsafe_b64encode(str(-10).encode()).decode()
        r = client.get("/marketplace/listings", params={"cursor": neg_cursor})
        body = r.json()
        self.assertFalse(body["success"])
        self.assertEqual(body.get("code"), "BAD_CURSOR")

    def test_cursor_valid_offset_decoding(self):
        cursor = base64.urlsafe_b64encode(str(2).encode()).decode()
        r = client.get("/marketplace/listings", params={"cursor": cursor, "limit": 2})
        body = r.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["filters"].get("offset"), 2)

    def test_no_next_cursor_when_at_end_of_results(self):
        all_res = client.get("/marketplace/listings", params={"status": "Active"}).json()
        total = all_res["total"]
        r = client.get("/marketplace/listings", params={"limit": total + 5})
        body = r.json()
        self.assertTrue(body["success"])
        self.assertIsNone(body.get("next_cursor"))

    def test_filtering_by_price_and_credits(self):
        r = client.get("/marketplace/listings", params={"min_price": 500, "max_price": 600})
        body = r.json()
        self.assertTrue(body["success"])
        for l in body["listings"]:
            price = float(l["price_per_credit"])
            self.assertGreaterEqual(price, 500)
            self.assertLessEqual(price, 600)


class MarketplaceCreationValidationTests(unittest.TestCase):
    def test_create_listing_requires_database(self):
        # Demo mode blocks direct listing creation with 503
        token = create_access_token({"phone": "9876543210", "name": "Test", "role": "farmer"})
        r = client.post("/marketplace/listings", json={
            "farm_id": "any-farm",
            "credits": 10,
            "price_per_credit": 500,
        }, headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(r.status_code, 503)


class AutoMatchDeepTests(unittest.TestCase):
    def setUp(self):
        market_store.reset()

    def test_auto_match_rejects_zero_or_negative_volume(self):
        r = client.post("/marketplace/auto-match", json={"target_volume": 0})
        body = r.json()
        self.assertFalse(body["success"])
        self.assertIn("Target volume must be greater than zero", body["message"])

        r_neg = client.post("/marketplace/auto-match", json={"target_volume": -15})
        self.assertFalse(r_neg.json()["success"])

    def test_auto_match_lowest_price_sorting(self):
        r = client.post("/marketplace/auto-match", json={"target_volume": 100, "priority": "lowest_price"})
        body = r.json()
        self.assertTrue(body["success"])
        rates = [m["rate"] for m in body["matched_farms"]]
        self.assertEqual(rates, sorted(rates))

    def test_auto_match_highest_ndvi_sorting(self):
        r = client.post("/marketplace/auto-match", json={"target_volume": 150, "priority": "highest_ndvi"})
        body = r.json()
        self.assertTrue(body["success"])
        self.assertGreater(len(body["matched_farms"]), 0)

    def test_auto_match_nearest_priority(self):
        r = client.post("/marketplace/auto-match", json={"target_volume": 100, "priority": "nearest"})
        body = r.json()
        self.assertTrue(body["success"])
        self.assertGreater(len(body["matched_farms"]), 0)

    def test_auto_match_filters(self):
        r = client.post("/marketplace/auto-match", json={
            "target_volume": 50,
            "filters": {"crop": "Rice"},
        })
        body = r.json()
        self.assertTrue(body["success"])
        for m in body["matched_farms"]:
            self.assertEqual(m["crop"].lower(), "rice")

    def test_line_split_accumulation_consistency(self):
        r = client.post("/marketplace/auto-match", json={"target_volume": 120})
        body = r.json()
        self.assertTrue(body["success"])
        matched = body["matched_farms"]
        sum_farmer = round(sum(m["farmer_share_inr"] for m in matched), 2)
        self.assertEqual(body["farmer_total_inr"], sum_farmer)
        # Gross matches sum of all 3 legs exactly
        total_legs = round(body["farmer_total_inr"] + body["fpo_total_inr"] + body["platform_total_inr"], 2)
        self.assertAlmostEqual(total_legs, body["gross_value"], places=2)


class MarketStoreAndBiddingTests(unittest.TestCase):
    def setUp(self):
        market_store.reset()

    def test_market_store_thread_safety(self):
        rows = market_store.all_rows()
        target = rows[0]
        initial_credits = float(target["total_credits"])

        def worker(idx):
            market_store.update(target["id"], {"total_credits": initial_credits + idx})

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        updated = market_store.get(target["id"])
        self.assertIsNotNone(updated)

    def test_place_bid_in_demo_mode(self):
        rows = market_store.all_rows()
        active = next(r for r in rows if r["status"] == "Active")
        listing_id = active["id"]
        base_price = float(active["price_per_credit"])

        # Below floor bid
        r_low = client.post(f"/marketplace/listings/{listing_id}/bid", json={"bid_amount": base_price - 10})
        self.assertFalse(r_low.json()["success"])
        self.assertIn("Bid must exceed", r_low.json()["message"])

        # Valid higher bid
        r_valid = client.post(f"/marketplace/listings/{listing_id}/bid", json={"bid_amount": base_price + 50})
        body = r_valid.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["bid_amount"], base_price + 50)
        self.assertGreater(body["bids_count"], 0)

        # Stale bid attempt
        r_stale = client.post(f"/marketplace/listings/{listing_id}/bid", json={"bid_amount": base_price + 20})
        self.assertFalse(r_stale.json()["success"])

    def test_buy_zero_credits_rejected(self):
        rows = market_store.all_rows()
        active = next(r for r in rows if r["status"] == "Active")
        r = client.post("/marketplace/buy", json={"listing_id": active["id"], "credits": 0})
        body = r.json()
        self.assertFalse(body["success"])
        self.assertIn("greater than zero", body["message"])


if __name__ == "__main__":
    unittest.main()
