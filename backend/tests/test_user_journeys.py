"""Three end-to-end product journeys at the API level.

P2 journeys mapped to executable checks (demo/degraded mode, no live DB):

1. Farmer: verified parcel â†’ listing â†’ partial sale â†’ wallet pays â†’
   certificate lifecycle â†’ grievance ticket tracked to resolution.
2. Corporate buyer: login â†’ browse (redacted) â†’ full purchase â†’ buyer-only
   certificate view + account settings â†’ public surfaces stay redacted.
3. FPO officer: cannot attach evidence outside the FPO scope; can verify a
   member farm geotag inside the boundary.

These run against the public API only (TestClient) â€” they are the "journeys"
the UI wires over, and they document what the degraded/demo deployment can
honestly demonstrate. OTP/SMS and Earth Engine scan steps require live
credentials and are covered by their dedicated suites.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
import uuid
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app import supabase_db as _db  # noqa: E402
from app import security  # noqa: E402
from app.services import evidence_service  # noqa: E402
from app.services import ledger as _ledger  # noqa: E402
from app.services import market_store, privacy  # noqa: E402
import importlib  # noqa: E402

evidence_router = importlib.import_module("app.routes.evidence_router")  # noqa: E402
support_svc = importlib.import_module("app.services.support_tickets")  # noqa: E402
corp_svc = importlib.import_module("app.services.corporate_settings")  # noqa: E402

# Hermetic mode POST-import (see docs/AGENTS note in README/conventions).
for _k in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY",
           "VITE_SUPABASE_URL", "VITE_SUPABASE_ANON_KEY"):
    os.environ.pop(_k, None)
os.environ["SUPABASE_URL"] = ""
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = ""
_db._supabase = None
_db._ready = False

_ledger._PATH = os.path.join(tempfile.mkdtemp(prefix="carbonx_journeys_"), "ledger.json")
_ledger._CHAINS = {}
_ledger._MIGRATED = True

client = TestClient(app)

FARMER = "9551111111"
BUYER_NAME = "Journey Buyer Pvt Ltd"


def _token(payload: dict) -> dict:
    return {"Authorization": "Bearer " + security.create_access_token(payload)}


def _farmer_token() -> dict:
    return _token({"phone": FARMER, "role": "farmer", "name": "Journey Farmer"})


def _buyer_token(name: str = BUYER_NAME) -> dict:
    return _token({"c_id": 11, "role": "buyer", "name": name})


def _officer_token() -> dict:
    return _token({"phone": "9000000001", "role": "fpo", "name": "FPO Officer"})


def _listing(*, phone: str = FARMER, name: str = "Journey Farmer", credits: float = 10.0) -> dict:
    now = "2026-10-22T00:00:00+00:00"
    return market_store.insert({
        "id": f"list-{uuid.uuid4()}",
        "farm_id": f"farm-{uuid.uuid4()}",
        "farmer_phone": phone,
        "farmer_name": name,
        "crop": "Rice",
        "location": "Bonakal, Khammam, Telangana",
        "size_label": f"{credits:g} ha",
        "listing_model": "Fixed Price",
        "price_per_credit": 120.0,
        "total_credits": credits,
        "carbon_credits": credits,
        "biodiversity_credits": 0,
        "status": "Active",
        "created_at": now,
        "updated_at": now,
    })


class FarmerJourneyTests(unittest.TestCase):
    """Parcel â†’ partial sale â†’ wallet â†’ certificate â†’ grievance ticket."""

    def setUp(self):
        market_store.reset()
        _ledger._CHAINS = {}
        privacy.reset_memory()
        evidence_service.reset_memory()
        support_svc.reset_memory()

    def test_farmer_journey_end_to_end(self):
        row = _listing()

        # Current math is honestly labelled proxy on every public surface.
        passport = client.get("/passport/demo-journey-farm").json()
        status = (passport.get("validation") or {})
        self.assertEqual(status.get("status"), "proxy_unvalidated")
        self.assertTrue(status.get("proxy_estimate"))

        # Partial sale of 3 of 10 credits.
        sale = client.post("/marketplace/buy", json={
            "listing_id": row["id"], "credits": 3, "buyer_name": BUYER_NAME,
        }).json()
        self.assertTrue(sale.get("success"), sale)
        cert_id = sale.get("certificate_id")
        self.assertTrue(cert_id)
        updated = market_store.get(row["id"]) or {}
        self.assertEqual(float(updated.get("total_credits") or 0), 7.0)

        # Wallet pays from the ledger, not from optimistic UI math.
        wallet = client.get("/wallet", headers=_farmer_token()).json()
        self.assertTrue(wallet.get("success"), wallet)
        txs = wallet.get("transactions") or []
        self.assertTrue(any(str(t.get("certificate_id")) == str(cert_id) for t in txs))
        settled = next(t for t in txs if str(t.get("certificate_id")) == str(cert_id))
        self.assertEqual(settled.get("status"), "SETTLED")
        self.assertGreater(float(settled.get("farmer_share") or 0), 0)
        recon = wallet.get("reconciliation") or {}
        self.assertGreaterEqual(float(recon.get("farmer_total_inr") or 0), 0)

        # Certification lifecycle: unique id, credits recorded, dispute intact.
        life = client.get(f"/certificates/{cert_id}/lifecycle").json()
        self.assertTrue(life.get("success"), life)
        self.assertEqual(float(life["lifecycle"]["credits_sold"]), 3.0)
        self.assertEqual(life["lifecycle"]["dispute_status"], "NONE")

        # Grievance track: farmer questions the estimate; staff answers.
        ticket = client.post("/support/tickets", json={
            "category": "estimate",
            "title": "Volume seems high for 3 credit share",
            "detail": "Neighbour with similar field reported a smaller rate.",
        }, headers=_farmer_token()).json()
        self.assertTrue(ticket.get("success"), ticket)
        tid = ticket["ticket"]["id"]
        opened = client.get("/support/tickets", headers=_farmer_token()).json()
        self.assertEqual(opened["summary"]["open"], 1)

        staff = client.post(
            f"/support/tickets/{tid}/update",
            json={
                "status": "Resolved",
                "resolution": "Field inspection matched the frozen estimate; no change.",
            },
            # Global staff resolves; an FPO officer would need a verifiable
            # FPO membership link for this farmer (demo mode cannot resolve
            # one, and FPO access is scoped — never global staff).
            headers=_token({"phone": "9000000009", "role": "verifier", "name": "Support Staff"}),
        ).json()
        self.assertTrue(staff.get("success"), staff)
        closed = client.get("/support/tickets", headers=_farmer_token()).json()
        self.assertEqual(closed["summary"]["resolved"], 1)
        self.assertIn("no change", closed["tickets"][0]["resolution"])


class CorporateBuyerJourneyTests(unittest.TestCase):
    """Login â†’ browse redacted â†’ full purchase â†’ buyer view â†’ public redaction."""

    def setUp(self):
        market_store.reset()
        _ledger._CHAINS = {}
        privacy.reset_memory()
        corp_svc._memory.clear()
        corp_svc._table_unavailable.clear()

    def test_buyer_journey_end_to_end(self):
        row = _listing()

        # Public marketplace must not disclose the farmer identity.
        listings = client.get("/marketplace/listings").json()
        self.assertTrue(listings.get("success"), listings)
        public_rows = [l for l in listings["listings"] if l.get("id") == row["id"]]
        self.assertTrue(public_rows)
        public_row = public_rows[0]
        self.assertIsNone(public_row.get("farmer_phone"))
        self.assertNotIn("Journey Farmer", str(public_row))

        # Demo buyer login works in degraded mode.
        login = client.post("/corporate/login", json={
            "name": "Telangana Sustainable Agro Pvt Ltd",
            "password": "Corporate@2026",
        }).json()
        self.assertTrue(login.get("success"), login)
        buyer_auth = {"Authorization": f"Bearer {login['token']}"}

        # Full purchase settles and retires.
        sale = client.post("/marketplace/buy", json={
            "listing_id": row["id"], "credits": 10, "buyer_name": "Telangana Sustainable Agro Pvt Ltd",
        }).json()
        self.assertTrue(sale.get("success"), sale)
        cert_id = sale["certificate_id"]
        self.assertEqual(str((market_store.get(row["id"]) or {}).get("status") or "").lower(), "retired")

        # Buyer-of-record sees their own certificate; anonymous stays redacted.
        mine = client.get(f"/certificates/{cert_id}", headers=buyer_auth).json()["certificate"]
        self.assertEqual(mine.get("access", {}).get("buyer"), True)
        self.assertIn("Telangana Sustainable Agro", str(mine.get("issued_to") or ""))
        public = client.get(f"/certificates/{cert_id}").json()["certificate"]
        self.assertTrue(public.get("public_view"))
        self.assertNotIn("Telangana Sustainable Agro", str(public.get("buyer")))
        self.assertIsNone(public.get("value_inr"))

        # Account-level target persists server-side (memory fallback here).
        put = client.put("/corporate/settings", json={"target_offsets_mt": 42},
                         headers=buyer_auth).json()
        self.assertTrue(put.get("success"), put)
        got = client.get("/corporate/settings", headers=buyer_auth).json()
        self.assertEqual(got["settings"]["target_offsets_mt"], 42.0)

        # Export CSV keeps the same access policy as JSON/PDF.
        csv_res = client.get("/certificates/export.csv")
        self.assertIn(cert_id, csv_res.text)
        self.assertNotIn("Journey Farmer", csv_res.text)


class _MiniSupabase:
    """Tiny Supabase stand-in for the FPO evidence-scoping journey."""

    def __init__(self, farms_rows, profiles_rows):
        self._tables = {
            "farms": farms_rows,
            "profiles": profiles_rows,
            "farm_evidence": [],
        }

    def table(self, name: str):
        return _MiniTable(self._tables.get(name, []))


class _MiniTable:
    def __init__(self, rows):
        self._rows = rows

    def select(self, *_a, **_k):
        return self

    def eq(self, *a, **k):
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, *_a, **_k):
        return self

    def insert(self, row):
        self._pending = row
        return self

    def execute(self):
        class R:
            data = self._rows

        return R()


class FpoOfficerJourneyTests(unittest.TestCase):
    """FPO evidence workflow: own-scope allowed, foreign-scope rejected."""

    OWNER_FARM_A = {"id": "farm-fpo-a", "owner_phone": "9552222111", "fpo_id": "fpo-a"}

    def setUp(self):
        market_store.reset()
        _ledger._CHAINS = {}
        privacy.reset_memory()
        evidence_service.reset_memory()

    def test_officer_cannot_verify_outside_fpo_scope(self):
        foreign = {**self.OWNER_FARM_A, "fpo_id": "fpo-other"}
        officer = {"phone": "9000000001", "role": "fpo"}
        from app.routes.evidence_router import get_current_user  # local import

        app.dependency_overrides[get_current_user] = lambda: officer
        try:
            with mock.patch.object(_db, "is_ready", return_value=True), \
                    mock.patch.object(_db, "get_profile",
                                               return_value={"phone": "9000000001", "fpo_id": "fpo-a"}), \
                    mock.patch.object(evidence_router, "_load_farm",
                                               return_value=foreign):
                res = client.post(
                    "/farms/farm-fpo-a/evidence/geotag",
                    json={"latitude": 17.255, "longitude": 79.155},
                    headers=_officer_token(),
                )
                self.assertEqual(res.status_code, 403, res.text)
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    def test_officer_verifies_member_farm_geotag_inside_boundary(self):
        member = {**self.OWNER_FARM_A, "geojson": {"type": "Polygon",
                    "coordinates": [[[79.15, 17.25], [79.16, 17.25],
                                     [79.16, 17.26], [79.15, 17.26], [79.15, 17.25]]]}}
        fake = _MiniSupabase(
            farms_rows=[member],
            profiles_rows=[{"phone": "9000000001", "fpo_id": "fpo-a"}],
        )
        officer = {"phone": "9000000001", "role": "fpo"}
        from app.routes.evidence_router import get_current_user  # local import

        app.dependency_overrides[get_current_user] = lambda: officer
        try:
            with mock.patch.object(_db, "is_ready", return_value=True), \
                    mock.patch.object(_db, "_client", return_value=fake), \
                    mock.patch.object(_db, "get_profile",
                                               return_value={"phone": "9000000001", "fpo_id": "fpo-a"}), \
                    mock.patch.object(evidence_router, "_load_farm",
                                               return_value=member):
                res = client.post(
                    "/farms/farm-fpo-a/evidence/geotag",
                    json={"latitude": 17.255, "longitude": 79.155},
                    headers=_officer_token(),
                )
                self.assertEqual(res.status_code, 200, res.text)
                body = res.json()
                self.assertTrue(body.get("geotag", {}).get("inside_boundary"))
        finally:
            app.dependency_overrides.pop(get_current_user, None)


if __name__ == "__main__":
    unittest.main()
