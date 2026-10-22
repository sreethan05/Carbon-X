"""API tests for the evidence router (photo upload, geotag, GET listing).

Hermetic: a mini FastAPI app includes only the evidence router, auth is
overridden via ``dependency_overrides``, files go to a tempdir, and the
live-DB paths run against an in-test fake Supabase client (never the network).

Run from backend/: python -m unittest tests.test_evidence_api -v
"""
import io
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

for _k in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY",
           "VITE_SUPABASE_URL", "VITE_SUPABASE_ANON_KEY"):
    os.environ.pop(_k, None)
os.environ["SUPABASE_URL"] = ""
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = ""

_EVIDENCE_TMP = tempfile.mkdtemp(prefix="carbonx_evidence_api_")
os.environ["CARBONX_EVIDENCE_DIR"] = _EVIDENCE_TMP


def setUpModule():
    # Re-assert the override at run time: discovery imports every test module
    # before running any, so another module may have replaced the env var.
    os.environ["CARBONX_EVIDENCE_DIR"] = _EVIDENCE_TMP

from fastapi import FastAPI  # noqa: E402
from fastapi.exceptions import RequestValidationError  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from starlette.exceptions import HTTPException as StarletteHTTPException  # noqa: E402
from PIL import Image  # noqa: E402

from app.routes import evidence_router  # noqa: E402
from app.routes.evidence_router import router as evidence_api_router  # noqa: E402
from app.security import get_current_user, get_current_user_optional  # noqa: E402
from app.services import evidence_service as evidence  # noqa: E402
from app import supabase_db as _db  # noqa: E402

# post-import reset (main.py load_dotenv(override=True) may have restored env).
for _k in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY",
           "VITE_SUPABASE_URL", "VITE_SUPABASE_ANON_KEY"):
    os.environ.pop(_k, None)
os.environ["SUPABASE_URL"] = ""
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = ""
_db._supabase = None
_db._ready = False


def tearDownModule():
    shutil.rmtree(_EVIDENCE_TMP, ignore_errors=True)


# ─── Envelope handlers matching app.main ───

async def _validation_envelope(request, exc):
    messages = []
    for error in exc.errors():
        loc = ".".join(str(part) for part in error.get("loc", []) if part != "body")
        messages.append(f"{loc}: {error.get('msg', 'invalid')}" if loc else str(error.get("msg", "invalid")))
    return JSONResponse(status_code=422, content={"success": False, "message": "; ".join(messages)})


_HTTP_CODES = {401: "UNAUTHORIZED", 403: "FORBIDDEN", 404: "NOT_FOUND", 409: "CONFLICT", 429: "RATE_LIMITED"}


async def _http_envelope(request, exc):
    detail = exc.detail if isinstance(exc.detail, str) else "Request failed"
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "message": detail, "code": _HTTP_CODES.get(exc.status_code, f"HTTP_{exc.status_code}")},
    )


# ─── Fake Supabase (in-test only) ───

class _FakeResult:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count


class _FakeQuery:
    def __init__(self, store, table_name):
        self.store = store
        self.table_name = table_name
        self._insert = None
        self._filters = []
        self._order = None
        self._descending = False
        self._limit = None

    def insert(self, row):
        self._insert = row
        return self

    def select(self, *columns, **kwargs):
        return self

    def eq(self, column, value):
        self._filters.append((column, value))
        return self

    def order(self, column, desc=False):
        self._order = column
        self._descending = bool(desc)
        return self

    def limit(self, value):
        self._limit = int(value)
        return self

    def execute(self):
        rows = self.store.setdefault(self.table_name, [])
        if self._insert is not None:
            row = dict(self._insert)
            row.setdefault("id", f"ev-{len(rows) + 1}")
            row.setdefault("created_at", datetime.now(timezone.utc).isoformat())
            rows.append(row)
            return _FakeResult([dict(row)])
        selected = [dict(row) for row in rows]
        for column, value in self._filters:
            selected = [row for row in selected if row.get(column) == value]
        if self._order:
            selected.sort(key=lambda row: str(row.get(self._order) or ""), reverse=self._descending)
        if self._limit is not None:
            selected = selected[: self._limit]
        return _FakeResult(selected)


class FakeSupabase:
    def __init__(self):
        self.tables = {}

    def table(self, name):
        return _FakeQuery(self.tables, name)


# ─── Fixtures ───

SQUARE = {
    "type": "Feature",
    "geometry": {"type": "Polygon", "coordinates": [
        [[79.15, 17.25], [79.16, 17.25], [79.16, 17.26], [79.15, 17.26], [79.15, 17.25]]]},
}


def _dms(value):
    value = abs(value)
    degrees = int(value)
    minutes_float = (value - degrees) * 60
    minutes = int(minutes_float)
    seconds = round((minutes_float - minutes) * 60, 4)
    return (degrees, minutes, seconds)


def make_jpeg(with_gps=False, latitude=17.255, longitude=79.155):
    image = Image.new("RGB", (16, 16), "green")
    buffer = io.BytesIO()
    if with_gps:
        exif = Image.Exif()
        exif[34853] = {
            1: "N", 2: _dms(latitude),
            3: "E", 4: _dms(longitude),
        }
        image.save(buffer, format="JPEG", exif=exif)
    else:
        image.save(buffer, format="JPEG")
    return buffer.getvalue()


def post_photo(client, farm_id, data=None, content_type="image/jpeg", payload=None):
    files = {"file": ("photo.jpg", payload if payload is not None else make_jpeg(), content_type)}
    return client.post(f"/farms/{farm_id}/evidence/photo", files=files, data=data or {})


class EvidenceApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app = FastAPI()
        app.include_router(evidence_api_router)
        app.add_exception_handler(RequestValidationError, _validation_envelope)
        app.add_exception_handler(StarletteHTTPException, _http_envelope)
        cls.app = app
        cls.client = TestClient(app)

    def setUp(self):
        evidence.reset_memory()
        self.app.dependency_overrides[get_current_user] = lambda: {"phone": "9000000001", "role": "farmer"}
        self.app.dependency_overrides[get_current_user_optional] = lambda: {"phone": "9000000001", "role": "farmer"}
        self.addCleanup(self.app.dependency_overrides.pop, get_current_user, None)
        self.addCleanup(self.app.dependency_overrides.pop, get_current_user_optional, None)

    # ── Photo upload ──

    def test_photo_happy_path_demo_mode_without_coords(self):
        r = post_photo(self.client, "farm-photo-1")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body["success"])
        self.assertTrue(body["demo_mode"])
        self.assertEqual(body["farm_id"], "farm-photo-1")
        photo = body["photo"]
        self.assertTrue(photo["accepted"])
        self.assertIsNone(photo["geotag"])
        self.assertIn("No GPS coordinates", photo["reason"])
        self.assertEqual(len(photo["sha256"]), 64)
        self.assertEqual(photo["mime"], "image/jpeg")
        self.assertGreater(photo["size_bytes"], 0)
        self.assertIsNone(photo["captured_at"])
        self.assertEqual(body["components"], {"practice_photo": True, "geotag_inside_boundary": False})

    def test_photo_file_written_to_disk(self):
        body = post_photo(self.client, "farm-photo-disk").json()
        folder = os.path.join(evidence.evidence_dir(), "farm-photo-disk")
        files = os.listdir(folder)
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0], f"{body['photo']['sha256'][:16]}.jpg")

    def test_photo_captured_at_echoed(self):
        r = post_photo(self.client, "farm-photo-time", data={"captured_at": "2026-10-17T08:30:00Z"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["photo"]["captured_at"].startswith("2026-10-17T08:30:00"))

    def test_photo_invalid_captured_at_rejected(self):
        r = post_photo(self.client, "farm-photo-badtime", data={"captured_at": "yesterday-ish"})
        self.assertEqual(r.status_code, 400)
        self.assertFalse(r.json()["success"])

    def test_photo_oversize_rejected(self):
        payload = b"\x00" * (evidence.MAX_PHOTO_BYTES + 1)
        r = post_photo(self.client, "farm-photo-big", payload=payload)
        self.assertEqual(r.status_code, 413)
        body = r.json()
        self.assertFalse(body["success"])
        self.assertIn("8 MB", body["message"])

    def test_photo_wrong_mime_rejected(self):
        r = post_photo(self.client, "farm-photo-txt", payload=b"hello", content_type="text/plain")
        self.assertEqual(r.status_code, 415)
        body = r.json()
        self.assertFalse(body["success"])
        self.assertIn("JPEG", body["message"])

    def test_photo_invalid_image_rejected(self):
        r = post_photo(self.client, "farm-photo-junk", payload=b"not an image")
        self.assertEqual(r.status_code, 400)
        self.assertFalse(r.json()["success"])

    def test_photo_unsafe_farm_id_rejected(self):
        r = post_photo(self.client, "bad!farm")
        self.assertEqual(r.status_code, 400)
        self.assertFalse(r.json()["success"])

    def test_geotag_unsafe_farm_id_rejected(self):
        r = self.client.post("/farms/bad!farm/evidence/geotag",
                             json={"latitude": 17.25, "longitude": 79.155})
        self.assertEqual(r.status_code, 400)
        self.assertFalse(r.json()["success"])

    def test_get_evidence_unsafe_farm_id_rejected(self):
        r = self.client.get("/farms/bad!farm/evidence")
        self.assertEqual(r.status_code, 400)
        self.assertFalse(r.json()["success"])

    def test_photo_requires_auth(self):
        self.app.dependency_overrides.pop(get_current_user, None)
        r = post_photo(self.client, "farm-photo-auth")
        self.assertEqual(r.status_code, 401)
        body = r.json()
        self.assertFalse(body["success"])
        self.assertEqual(body.get("code"), "UNAUTHORIZED")

    def test_photo_one_sided_coords_rejected(self):
        r = post_photo(self.client, "farm-photo-half", data={"latitude": "17.25"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("together", r.json()["message"])

    def test_photo_request_coords_stored_as_geotag(self):
        r = post_photo(self.client, "farm-photo-req", data={"latitude": "17.25", "longitude": "79.155"})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        geotag = body["photo"]["geotag"]
        self.assertEqual(geotag["source"], "request")
        self.assertAlmostEqual(geotag["latitude"], 17.25)
        self.assertAlmostEqual(geotag["longitude"], 79.155)
        self.assertFalse(geotag["inside_boundary"])
        self.assertIn("No farm boundary", geotag["reason"])
        self.assertEqual(body["components"]["geotag_inside_boundary"], False)

        listing = self.client.get("/farms/farm-photo-req/evidence").json()
        self.assertEqual(len(listing["geotags"]), 1)
        self.assertEqual(listing["geotags"][0]["inside_boundary"], False)
        self.assertNotIn("created_by", listing["geotags"][0])

    def test_photo_exif_gps_used_as_source(self):
        payload = make_jpeg(with_gps=True, latitude=17.25, longitude=79.155)
        r = post_photo(self.client, "farm-photo-exif", payload=payload)
        self.assertEqual(r.status_code, 200)
        geotag = r.json()["photo"]["geotag"]
        self.assertEqual(geotag["source"], "exif")
        self.assertAlmostEqual(geotag["latitude"], 17.25, places=4)
        self.assertAlmostEqual(geotag["longitude"], 79.155, places=4)

    def test_photo_exif_wins_over_form_coords(self):
        payload = make_jpeg(with_gps=True, latitude=17.25, longitude=79.155)
        r = post_photo(self.client, "farm-photo-both", payload=payload,
                       data={"latitude": "18.0", "longitude": "80.0"})
        self.assertEqual(r.status_code, 200)
        geotag = r.json()["photo"]["geotag"]
        self.assertEqual(geotag["source"], "exif")
        self.assertAlmostEqual(geotag["latitude"], 17.25, places=4)

    # ── Boundary verification with a real (fake-farm) polygon ──

    def test_photo_inside_fake_boundary_marks_component_true(self):
        farm = {"owner_phone": "9000000001", "geojson": SQUARE}
        with patch.object(evidence_router, "_load_farm", return_value=farm):
            r = post_photo(self.client, "farm-inside", data={"latitude": "17.255", "longitude": "79.155"})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body["photo"]["geotag"]["inside_boundary"])
        self.assertTrue(body["components"]["geotag_inside_boundary"])
        listing = self.client.get("/farms/farm-inside/evidence").json()
        self.assertTrue(listing["components"]["geotag_inside_boundary"])
        self.assertTrue(listing["geotags"][0]["inside_boundary"])

    def test_photo_outside_fake_boundary_stays_false(self):
        farm = {"owner_phone": "9000000001", "geojson": SQUARE}
        with patch.object(evidence_router, "_load_farm", return_value=farm):
            r = post_photo(self.client, "farm-outside", data={"latitude": "18.0", "longitude": "80.0"})
        body = r.json()
        self.assertFalse(body["photo"]["geotag"]["inside_boundary"])
        self.assertIn("outside", body["photo"]["geotag"]["reason"])
        self.assertFalse(body["components"]["geotag_inside_boundary"])

    # ── Geotag endpoint ──

    def test_geotag_extra_fields_rejected(self):
        r = self.client.post("/farms/farm-gt-extra/evidence/geotag",
                             json={"latitude": 17.25, "longitude": 79.155, "accuracy_metres": 5})
        self.assertEqual(r.status_code, 422)
        body = r.json()
        self.assertFalse(body["success"])
        self.assertTrue(body["message"])

    def test_geotag_out_of_range_rejected(self):
        r = self.client.post("/farms/farm-gt-range/evidence/geotag",
                             json={"latitude": 95.0, "longitude": 79.155})
        self.assertEqual(r.status_code, 422)
        self.assertFalse(r.json()["success"])

    def test_geotag_demo_mode_stores_without_boundary(self):
        r = self.client.post("/farms/farm-gt-demo/evidence/geotag",
                             json={"latitude": 17.25, "longitude": 79.155, "accuracy_m": 8.0})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body["success"])
        self.assertTrue(body["demo_mode"])
        self.assertFalse(body["geotag"]["inside_boundary"])
        self.assertIn("No farm boundary", body["geotag"]["reason"])
        self.assertEqual(body["components"], {"practice_photo": False, "geotag_inside_boundary": False})
        listing = self.client.get("/farms/farm-gt-demo/evidence").json()
        self.assertEqual(len(listing["geotags"]), 1)
        self.assertEqual(listing["photos"], [])

    def test_geotag_inside_fake_boundary_marks_component_true(self):
        farm = {"owner_phone": "9000000001", "geojson": SQUARE}
        with patch.object(evidence_router, "_load_farm", return_value=farm):
            r = self.client.post("/farms/farm-gt-in/evidence/geotag",
                                 json={"latitude": 17.255, "longitude": 79.155})
        body = r.json()
        self.assertTrue(body["geotag"]["inside_boundary"])
        self.assertTrue(body["components"]["geotag_inside_boundary"])
        self.assertIn("inside", body["geotag"]["reason"].lower())

    # ── GET listing ──

    def test_get_evidence_empty_shape(self):
        r = self.client.get("/farms/farm-empty/evidence")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body["success"])
        self.assertTrue(body["demo_mode"])
        self.assertEqual(body["components"], {"practice_photo": False, "geotag_inside_boundary": False})
        self.assertEqual(body["photos"], [])
        self.assertEqual(body["geotags"], [])
        self.assertEqual(body["photo_count"], 0)
        self.assertIsNone(body["last_photo_at"])

    def test_get_evidence_newest_first(self):
        for _ in range(2):
            post_photo(self.client, "farm-order")
        photos = self.client.get("/farms/farm-order/evidence").json()["photos"]
        self.assertEqual(len(photos), 2)
        times = [photo["created_at"] for photo in photos]
        self.assertEqual(times, sorted(times, reverse=True))

    # ── DB-ready authorization paths (fake client, no network) ──

    def test_db_ready_unknown_farm_returns_404_envelope(self):
        with patch.object(_db, "is_ready", return_value=True), \
                patch.object(evidence_router, "_load_farm", return_value=None):
            r = self.client.post("/farms/farm-missing/evidence/geotag",
                                 json={"latitude": 17.25, "longitude": 79.155})
        self.assertEqual(r.status_code, 404)
        body = r.json()
        self.assertFalse(body["success"])
        self.assertIn("not found", body["message"].lower())

    def test_db_ready_owner_mismatch_returns_403_envelope(self):
        foreign_farm = {"owner_phone": "9111111111", "geojson": SQUARE}
        with patch.object(_db, "is_ready", return_value=True), \
                patch.object(evidence_router, "_load_farm", return_value=foreign_farm):
            r = self.client.post("/farms/farm-foreign/evidence/geotag",
                                 json={"latitude": 17.255, "longitude": 79.155})
        self.assertEqual(r.status_code, 403)
        body = r.json()
        self.assertFalse(body["success"])
        self.assertEqual(body.get("code"), "FORBIDDEN")

    def test_db_ready_fpo_role_allowed_and_persists(self):
        fake = FakeSupabase()
        foreign_farm = {"owner_phone": "9111111111", "geojson": SQUARE}
        self.app.dependency_overrides[get_current_user] = lambda: {"phone": "9000000001", "role": "fpo"}
        with patch.object(_db, "is_ready", return_value=True), \
                patch.object(_db, "_client", return_value=fake), \
                patch.object(evidence_router, "_load_farm", return_value=foreign_farm):
            r = self.client.post("/farms/farm-fpo/evidence/geotag",
                                 json={"latitude": 17.255, "longitude": 79.155})
            self.assertEqual(r.status_code, 200, r.text)
            body = r.json()
            self.assertFalse(body["demo_mode"])
            self.assertTrue(body["geotag"]["inside_boundary"])
            self.assertTrue(body["components"]["geotag_inside_boundary"])
            self.assertEqual(len(fake.tables["farm_evidence"]), 1)
            row = fake.tables["farm_evidence"][0]
            self.assertEqual(row["kind"], "geotag")
            self.assertEqual(row["created_by"], "9000000001")
            self.assertTrue(row["inside_boundary"])

            listing = self.client.get("/farms/farm-fpo/evidence").json()
        self.assertFalse(listing["demo_mode"])
        self.assertEqual(len(listing["geotags"]), 1)
        self.assertTrue(listing["components"]["geotag_inside_boundary"])

    def test_db_ready_photo_persists_and_get_reads_stored_row(self):
        fake = FakeSupabase()
        own_farm = {"owner_phone": "9000000001", "geojson": SQUARE}
        with patch.object(_db, "is_ready", return_value=True), \
                patch.object(_db, "_client", return_value=fake), \
                patch.object(evidence_router, "_load_farm", return_value=own_farm):
            r = post_photo(self.client, "farm-db-photo",
                           data={"latitude": "17.255", "longitude": "79.155"})
            self.assertEqual(r.status_code, 200, r.text)
            body = r.json()
            self.assertFalse(body["demo_mode"])
            self.assertEqual(len(fake.tables["farm_evidence"]), 1)
            stored = fake.tables["farm_evidence"][0]
            self.assertEqual(stored["sha256"], body["photo"]["sha256"])
            self.assertEqual(stored["kind"], "photo")
            self.assertTrue(stored["inside_boundary"])

            listing = self.client.get("/farms/farm-db-photo/evidence").json()
        self.assertFalse(listing["demo_mode"])
        self.assertEqual(listing["components"], {"practice_photo": True, "geotag_inside_boundary": True})
        self.assertEqual(len(listing["photos"]), 1)
        self.assertEqual(listing["photos"][0]["sha256"], body["photo"]["sha256"])
        self.assertIsNotNone(listing["last_photo_at"])

    def test_get_evidence_photo_serves_bytes(self):
        r = post_photo(self.client, "farm-serve")
        self.assertEqual(r.status_code, 200)
        digest = r.json()["photo"]["sha256"]

        fetch_res = self.client.get(f"/farms/farm-serve/evidence/photo/{digest}")
        self.assertEqual(fetch_res.status_code, 200)
        self.assertEqual(fetch_res.headers.get("content-type"), "image/jpeg")
        self.assertGreater(len(fetch_res.content), 0)

    def test_get_evidence_photo_unauthorized_when_private(self):
        r = post_photo(self.client, "farm-priv")
        self.assertEqual(r.status_code, 200)
        digest = r.json()["photo"]["sha256"]

        # Caller is unauthenticated or a different user with no consent
        self.app.dependency_overrides[get_current_user_optional] = lambda: None
        try:
            fetch_res = self.client.get(f"/farms/farm-priv/evidence/photo/{digest}")
            self.assertEqual(fetch_res.status_code, 403)
        finally:
            self.app.dependency_overrides[get_current_user_optional] = lambda: {"phone": "9000000001", "role": "farmer"}

    def test_get_evidence_photo_allowed_with_public_consent(self):
        r = post_photo(self.client, "farm-pub", data={"public_consent": "true"})
        self.assertEqual(r.status_code, 200)
        digest = r.json()["photo"]["sha256"]

        # Caller is unauthenticated, but photo has public consent
        self.app.dependency_overrides[get_current_user_optional] = lambda: None
        try:
            fetch_res = self.client.get(f"/farms/farm-pub/evidence/photo/{digest}")
            self.assertEqual(fetch_res.status_code, 200)
            self.assertEqual(fetch_res.headers.get("content-type"), "image/jpeg")
        finally:
            self.app.dependency_overrides[get_current_user_optional] = lambda: {"phone": "9000000001", "role": "farmer"}

    def test_get_evidence_photo_not_found(self):
        r = self.client.get("/farms/farm-serve/evidence/photo/0123456789abcdef0123456789abcdef")
        self.assertEqual(r.status_code, 404)

    def test_get_evidence_photo_invalid_sha(self):
        r = self.client.get("/farms/farm-serve/evidence/photo/not-a-valid-sha!")
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main()

