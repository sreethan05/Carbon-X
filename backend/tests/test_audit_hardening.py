"""Tests for the audit-hardening behaviors (cursors, error codes, guards,
quality-gate integrity). Run from backend/: python -m unittest tests.test_audit_hardening -v
"""
import base64
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

for _k in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY",
           "VITE_SUPABASE_URL", "VITE_SUPABASE_ANON_KEY"):
    os.environ.pop(_k, None)
os.environ["SUPABASE_URL"] = ""
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = ""

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app import supabase_db as _db  # noqa: E402

# post-import reset (load_dotenv(override=True) re-reads backend/.env)
for _k in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"):
    os.environ.pop(_k, None)
os.environ["SUPABASE_URL"] = ""
_db._supabase = None
_db._ready = False

client = TestClient(app)

GOOD_POLYGON = {
    "type": "Feature",
    "geometry": {"type": "Polygon", "coordinates": [
        [[79.15, 17.25], [79.16, 17.25], [79.16, 17.26], [79.15, 17.26], [79.15, 17.25]]]},
}


class CursorPaginationTests(unittest.TestCase):
    def test_first_page_carries_next_cursor(self):
        body = client.get("/marketplace/listings", params={"limit": 2}).json()
        self.assertTrue(body["success"])
        if body["total"] > 2:
            self.assertIn("next_cursor", body)
        self.assertLessEqual(len(body["listings"]), 2)

    def test_cursor_walks_pages(self):
        first = client.get("/marketplace/listings", params={"limit": 2}).json()
        if "next_cursor" not in first:
            self.skipTest("single page of data")
        second = client.get("/marketplace/listings",
                            params={"limit": 2, "cursor": first["next_cursor"]}).json()
        self.assertTrue(second["success"])
        first_ids = {l["id"] for l in first["listings"]}
        second_ids = {l["id"] for l in second["listings"]}
        self.assertFalse(first_ids & second_ids, "cursor must not overlap pages")

    def test_cursor_walks_three_pages(self):
        """Regression: page 3 must advance past page 2 (old bug reused the
        original offset when building next_cursor from a cursor request)."""
        seen = set()
        cursor = None
        pages = 0
        while pages < 3:
            params = {"limit": 2}
            if cursor:
                params["cursor"] = cursor
            body = client.get("/marketplace/listings", params=params).json()
            self.assertTrue(body["success"])
            ids = {l["id"] for l in body["listings"]}
            if not ids:
                break
            self.assertFalse(seen & ids, f"page {pages + 1} overlapped a previous page")
            seen |= ids
            pages += 1
            cursor = body.get("next_cursor")
            if not cursor:
                break
        self.assertGreaterEqual(pages, 2)
        if pages >= 3:
            self.assertGreaterEqual(len(seen), 5)

    def test_invalid_cursor_rejected(self):
        r = client.get("/marketplace/listings", params={"cursor": "not-a-cursor"})
        self.assertFalse(r.json()["success"])
        self.assertEqual(r.json().get("code"), "BAD_CURSOR")


class LedgerIntegrityTests(unittest.TestCase):
    def test_unknown_farm_ledger_has_no_phantom_genesis(self):
        """Demo mode must not mint an ISSUE event for an arbitrary id."""
        body = client.get("/ledger/phantom-farm-id-that-does-not-exist").json()
        self.assertTrue(body["success"])
        self.assertEqual(body["events"], [], "phantom id must not anchor a chain")
        self.assertTrue(body["verification"]["valid"])

    def test_market_store_cas_blocks_double_spend(self):
        from app.services import market_store
        row = next(r for r in market_store.all_rows() if str(r.get("status")) == "Active")
        credits = float(row["total_credits"])
        # stale balance (concurrent buyer already took the row) → reject
        self.assertFalse(market_store.update_cas(
            row["id"], {"total_credits": credits - 1}, expected_credits=credits + 5))
        # current balance → accept
        self.assertTrue(market_store.update_cas(
            row["id"], {"total_credits": credits - 1}, expected_credits=credits))
        # balance moved → an old-balance CAS must now fail (no double spend)
        self.assertFalse(market_store.update_cas(
            row["id"], {"status": "Retired"}, expected_credits=credits))
        # restore state for later tests
        market_store.update(row["id"], {"total_credits": credits})


class ErrorEnvelopeCodesTests(unittest.TestCase):
    def test_unauthorized_carries_code(self):
        r = client.get("/wallet")  # requires auth
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.json().get("code"), "UNAUTHORIZED")

    def test_not_found_carries_code(self):
        r = client.get("/definitely-missing")
        self.assertEqual(r.json().get("code"), "NOT_FOUND")


class AnalyzeGuardTests(unittest.TestCase):
    def test_oversized_polygon_rejected_before_ee(self):
        # 61-degree span polygon — exceeds the 60-degree scan limit;
        # must be rejected before any Earth Engine call.
        big = {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [
            [[0.0, 0.0], [61.0, 0.0], [61.0, 61.0], [0.0, 61.0], [0.0, 0.0]]]}}
        r = client.post("/analyze", json={"geojson": big, "crop_type": "Rice"})
        self.assertFalse(r.json()["success"])
        self.assertIn("scan limit", r.json()["message"])

    def test_extra_fields_forbidden_on_buy(self):
        r = client.post("/marketplace/buy", json={
            "listing_id": "x", "credtis": 5})  # typo on purpose
        self.assertEqual(r.status_code, 422)

    def test_predict_includes_ml_source(self):
        r = client.get("/predict", params={"longitude": 79.0, "latitude": 17.0})
        self.assertEqual(r.status_code, 200)
        self.assertIn("ml_source", r.json())


if __name__ == "__main__":
    unittest.main()
