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

    def test_invalid_cursor_rejected(self):
        r = client.get("/marketplace/listings", params={"cursor": "not-a-cursor"})
        self.assertFalse(r.json()["success"])
        self.assertEqual(r.json().get("code"), "BAD_CURSOR")


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
        # ~1-degree square over the Bay of Bengal ≈ 10,000+ km² — far past the
        # scan limit; must be rejected without any Earth Engine call.
        big = {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [
            [[85.0, 15.0], [86.0, 15.0], [86.0, 16.0], [85.0, 16.0], [85.0, 15.0]]]}}
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
