"""API integration tests — full request cycle through the FastAPI app.

Runs in DEMO MODE (no Supabase env in CI): exercises the marketplace fallback
store, the complete purchase -> split -> ledger -> retirement pipeline, the
earnings calculator, ground-truth eval, ops summary, and error envelopes.

Run from backend/: python -m unittest tests.test_integration -v
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

for _k in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY",
           "VITE_SUPABASE_URL", "VITE_SUPABASE_ANON_KEY"):
    os.environ.pop(_k, None)
os.environ["SUPABASE_URL"] = ""
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = ""
os.environ["CARBONX_ALLOW_DEV_OTP"] = "1"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app

# Force demo mode AFTER import: main.py load_dotenv(override=True) re-reads
# backend/.env at import time, so env-clearing must happen post-import and the
# cached Supabase client must be reset. Tests never touch the live database.
from app import supabase_db as _db
for _k in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY",
           "VITE_SUPABASE_URL", "VITE_SUPABASE_ANON_KEY"):
    os.environ.pop(_k, None)
os.environ["SUPABASE_URL"] = ""
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = ""
_db._supabase = None
_db._ready = False
  # noqa: E402  (no env -> DB off -> demo mode)

client = TestClient(app)

POLYGON = {
    "type": "Feature",
    "geometry": {
        "type": "Polygon",
        "coordinates": [[[79.15, 17.25], [79.16, 17.25], [79.16, 17.26],
                         [79.15, 17.26], [79.15, 17.25]]],
    },
}


class HealthAndListingsTests(unittest.TestCase):
    def test_health_reports_demo_state(self):
        r = client.get("/health")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIn("database", body)
        self.assertIn("earth_engine", body)

    def test_listings_served_with_source_flag(self):
        r = client.get("/marketplace/listings")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body["success"])
        self.assertIn(body["source"], ("live_db", "fallback"))
        self.assertGreater(len(body["listings"]), 0)

    def test_listings_search_filter(self):
        r = client.get("/marketplace/listings", params={"crop": "rice"})
        body = r.json()
        self.assertTrue(all("rice" in (l["crop"] or "").lower() for l in body["listings"]))


class PurchasePipelineTests(unittest.TestCase):
    def test_full_buy_split_retire_cycle(self):
        """The demo-mode money path: buy ALL credits -> retired -> ledger
        events -> certificate -> wallet-visible, on the in-memory store."""
        listings = client.get("/marketplace/listings", params={"status": "Active"}).json()["listings"]
        target = min(listings, key=lambda l: l["total_credits"])
        r = client.post("/marketplace/buy", json={
            "listing_id": target["id"], "credits": target["total_credits"],
            "buyer_name": "Integration Test Corp",
        })
        body = r.json()
        self.assertTrue(body["success"], body)
        self.assertIn(body["split"]["model"], ("3-way", "4-way"))
        self.assertTrue(body["retired"])
        self.assertTrue(body["batch_hash"])
        self.assertAlmostEqual(
            body["split"]["farmer_amount_inr"]
            + body["split"]["fpo_amount_inr"]
            + body["split"]["platform_amount_inr"],
            body["gross_amount"], places=2)

        # certificate visible in the escrow ledger
        certs = client.get("/certificates").json()["certificates"]
        self.assertTrue(any(c["id"] == body["certificate_id"] for c in certs))

        # ledger chain verifies for the farm
        chain = client.get(f"/ledger/{body['farm_id']}").json()
        self.assertTrue(chain["verification"]["valid"])
        self.assertTrue(any(e["type"] == "SALE" for e in chain["events"]))

    def test_buy_more_than_available_fails_cleanly(self):
        listings = client.get("/marketplace/listings", params={"status": "Active"}).json()["listings"]
        if not listings:
            self.skipTest("no active listings left in demo store")
        target = listings[0]
        available = float(target["total_credits"] or 0)
        r = client.post("/marketplace/buy", json={
            "listing_id": target["id"], "credits": 10 ** 9, "buyer_name": "Greedy Corp"})
        body = r.json()
        # Over-buys clamp to availability (documented behaviour) — never
        # issue more credits than the listing holds.
        if body.get("success"):
            self.assertLessEqual(body["credits_purchased"], available)
        else:
            self.assertIn("message", body)

    def test_auto_match_previews_farmer_share(self):
        r = client.post("/marketplace/auto-match", json={"target_volume": 50})
        body = r.json()
        self.assertTrue(body["success"])
        self.assertGreater(len(body["matched_farms"]), 0)
        for m in body["matched_farms"]:
            self.assertGreater(m["farmer_share_inr"], 0)


class TrustEndpointsTests(unittest.TestCase):
    def test_earnings_calculator_steps(self):
        r = client.post("/farms/earnings-calculator", json={
            "area_hectares": 2.0, "crop": "Rice", "ndvi": 0.72})
        body = r.json()
        self.assertTrue(body["success"])
        self.assertEqual(len(body["estimate"]["steps"]), 5)
        self.assertIn("ci90", body["estimate"])

    def test_ground_truth_eval_honest_empty_state(self):
        r = client.get("/ops/ground-truth/eval")
        self.assertEqual(r.status_code, 200)
        # demo mode: DB off -> clear message, never a fake accuracy number
        body = r.json()
        if not body["success"]:
            self.assertIn("message", body)

    def test_passport_demo_farm_includes_trust_and_monitoring(self):
        r = client.get("/passport/demo")
        body = r.json()
        self.assertTrue(body["success"])
        self.assertIn("expected_earnings", body)
        self.assertIn("trust", body)
        self.assertIn("ledger", body)

    def test_invalid_polygon_rejected_precisely(self):
        r = client.post("/analyze", json={
            "geojson": {"type": "Feature", "geometry": {"type": "Point",
                        "coordinates": [79.0, 17.0]}},
            "crop_type": "Rice"})
        body = r.json()
        self.assertFalse(body["success"])
        self.assertIn("Polygon", body["message"])

    def test_unclosed_ring_rejected(self):
        bad = {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [
            [[79.15, 17.25], [79.16, 17.25], [79.16, 17.26], [79.15, 17.26]]]}}
        r = client.post("/analyze", json={"geojson": bad, "crop_type": "Rice"})
        self.assertIn("closed", r.json()["message"])

    def test_demo_login_blocked_when_db_off_is_allowed_but_token_works(self):
        r = client.post("/demo/login", json={})
        body = r.json()
        if body.get("success"):  # demo mode active
            wallet = client.get("/wallet", headers={
                "Authorization": f"Bearer {body['token']}"})
            self.assertEqual(wallet.status_code, 200)
        else:
            self.assertIn("message", body)


class ErrorEnvelopeTests(unittest.TestCase):
    def test_404_unknown_route_uses_envelope(self):
        r = client.get("/definitely-not-a-route")
        self.assertEqual(r.status_code, 404)
        body = r.json()
        self.assertFalse(body["success"])
        self.assertIn("message", body)

    def test_validation_error_uses_envelope(self):
        r = client.post("/marketplace/buy", json={"credits": 5})
        self.assertEqual(r.status_code, 422)
        body = r.json()
        self.assertFalse(body["success"])
        self.assertIn("message", body)

    def test_request_id_header_present(self):
        r = client.get("/health")
        self.assertIn("X-Request-ID", r.headers)
        self.assertEqual(r.headers.get("X-Content-Type-Options"), "nosniff")


if __name__ == "__main__":
    unittest.main()
