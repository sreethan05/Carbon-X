"""Access-scope, identity-binding and payments-gate tests (audit 2026-10-22).

Covers the deployment-audit fixes:

1. FPO accounts are NOT global staff — they are scoped to their own fpo_id
   and fail closed when the profile link or the database is unavailable.
2. One simulated-payment gate: CARBONX_ACCEPT_SIMULATED_PAYMENTS, with the
   legacy CARBONX_ALLOW_SIMULATED_SETTLEMENT honoured only as a deprecated
   alias that an explicit canonical value always beats.
3. Buyer-of-record access binds to the corporate account id recorded on the
   SALE ledger event; display names never mediate access on live records.
4. /health degrades honestly when the database is unconfigured (the
   migration probe reports "not checked" instead of pretending all is well).

Everything runs on the isolated demo stack (no Supabase, isolated ledger
and marketplace memory) — it never touches the real project.
"""
from __future__ import annotations

import importlib
import os
import sys
import tempfile
import unittest
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

for _k in (
    "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY",
    "VITE_SUPABASE_URL", "VITE_SUPABASE_ANON_KEY",
):
    os.environ.pop(_k, None)
os.environ["SUPABASE_URL"] = ""
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = ""
os.environ["CARBONX_ALLOW_DEV_OTP"] = "1"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app import config as app_config  # noqa: E402
from app import security  # noqa: E402
from app import supabase_db as _db  # noqa: E402
from app import sample_data  # noqa: E402
from app.services import access_policy  # noqa: E402
from app.services import credit_lifecycle  # noqa: E402
from app.services import ledger as _ledger  # noqa: E402
from app.services import market_store  # noqa: E402
trust_router = importlib.import_module("app.routes.trust_router")  # noqa: E402

# Post-import reset: app.main load_dotenv(override=True) re-reads backend/.env.
for _k in (
    "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY",
    "VITE_SUPABASE_URL", "VITE_SUPABASE_ANON_KEY",
):
    os.environ.pop(_k, None)
os.environ["SUPABASE_URL"] = ""
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = ""
_db._supabase = None
_db._ready = False

_ledger._PATH = os.path.join(
    tempfile.mkdtemp(prefix="carbonx_access_scope_"), "ledger.json"
)
_ledger._CHAINS = {}
_ledger._MIGRATED = True

client = TestClient(app)


def _token(payload: dict) -> dict:
    token = security.create_access_token(payload)
    return {"Authorization": f"Bearer {token}"}


def _listing(*, credits: float = 10.0, price: float = 100.0) -> dict:
    now = "2026-10-22T00:00:00+00:00"
    row = {
        "id": f"list-{uuid.uuid4()}",
        "farm_id": f"farm-{uuid.uuid4()}",
        "farmer_phone": "9111111111",
        "farmer_name": "Secret Farmer",
        "crop": "Rice",
        "location": "Bonakal, Khammam, Telangana",
        "size_label": f"{credits:g} ha",
        "listing_model": "Fixed Price",
        "price_per_credit": price,
        "current_bid": 0,
        "bids_count": 0,
        "total_credits": credits,
        "carbon_credits": credits,
        "biodiversity_credits": 0,
        "status": "Active",
        "expires_at": None,
        "image_url": None,
        "token_id": None,
        "tx_hash": None,
        "created_at": now,
        "updated_at": now,
    }
    return market_store.insert(row)


class AccessPolicyScopeTests(unittest.TestCase):
    """The shared access policy: FPO is scoped, admin/verifier are global."""

    def test_is_staff_excludes_fpo(self):
        self.assertTrue(access_policy.is_staff({"role": "admin"}))
        self.assertTrue(access_policy.is_staff({"role": "verifier"}))
        for role in ("fpo", "farmer", "buyer", None, "FPO"):
            self.assertFalse(access_policy.is_staff({"role": role}),
                             f"role {role!r} must not be global staff")

    def test_owner_sees_own_farm_but_not_others(self):
        farm = {"owner_phone": "9111111111", "fpo_id": "fpo-a"}
        self.assertTrue(access_policy.can_access_farm(
            {"phone": "9111111111", "role": "farmer"}, farm))
        self.assertFalse(access_policy.can_access_farm(
            {"phone": "9222222222", "role": "farmer"}, farm))

    def test_fpo_fails_closed_without_database(self):
        # Demo DB is off: an FPO token resolves no fpo_id, so it must NOT be
        # granted full access to any farm — least privilege by default.
        farm = {"owner_phone": "9111111111", "fpo_id": "fpo-a"}
        self.assertFalse(access_policy.is_fpo_for_farm(
            {"phone": "9000000001", "role": "fpo"}, farm))
        self.assertFalse(access_policy.caller_fpo_id(
            {"phone": "9000000001", "role": "fpo"}))
        self.assertFalse(access_policy.can_access_farm(
            {"phone": "9000000001", "role": "fpo"}, farm))

    def test_fpo_scope_matches_exactly(self):
        self.assertTrue(access_policy.fpo_scope_matches("fpo-a", {"fpo_id": "fpo-a"}))
        self.assertFalse(access_policy.fpo_scope_matches("fpo-b", {"fpo_id": "fpo-a"}))
        self.assertFalse(access_policy.fpo_scope_matches(None, {"fpo_id": "fpo-a"}))
        self.assertFalse(access_policy.fpo_scope_matches("fpo-a", {"fpo_id": None}))
        self.assertFalse(access_policy.fpo_scope_matches("fpo-a", {}))

    def test_embedded_token_fpo_id_is_honoured(self):
        self.assertEqual(
            access_policy.caller_fpo_id({"role": "fpo", "fpo_id": "fpo-9"}),
            "fpo-9",
        )
        farmer = access_policy.can_access_farm(
            {"role": "fpo", "fpo_id": "fpo-a", "phone": "9000000001"},
            {"fpo_id": "fpo-a"})
        self.assertTrue(farmer)


class ScopedEndpointTests(unittest.TestCase):
    """FPO tokens keep the public view on the demo stack (fail closed)."""

    def setUp(self):
        market_store.reset()
        _ledger._CHAINS = {}

    def test_support_desk_failclosed_for_fpo_offline(self):
        # Support scoping needs live membership data: offline (demo) mode can
        # never verify it, so an FPO officer can neither queue-read another
        # caller's tickets nor act on them. Fail closed, no global staff.
        ticket = client.post("/support/tickets", json={
            "category": "estimate", "title": "Estimate looks too high for me",
            "detail": "My neighbour with a similar plot sold for half the rate.",
        }, headers=_token({"phone": "9111111111", "role": "farmer", "name": "Secret Farmer"}))
        self.assertEqual(ticket.status_code, 200)
        tid = ticket.json()["ticket"]["id"]

        auth = _token({"phone": "9777770001", "role": "fpo", "name": "FPO Officer"})
        queue = client.get("/support/staff/queue", headers=auth).json()
        fpo_visible = [t for t in queue.get("tickets", []) if t.get("id") == tid]
        self.assertEqual(fpo_visible, [])

        acted = client.post(f"/support/tickets/{tid}/update", json={
            "status": "In Review", "staff_notes": "Checking with the FPO desk.",
        }, headers=auth)
        self.assertEqual(acted.status_code, 403)
        self.assertIn("outside your FPO scope", acted.json().get("message", ""))

    def test_fpo_passport_stays_public(self):
        farm_id = sample_data._fallback_farm_id(sample_data.FARMS[0]["key"])
        # 9777770001 is NOT any sample farmer's phone: the only way an FPO
        # token is anything but public here is the scoped-FPO branch.
        auth = _token({"phone": "9777770001", "role": "fpo", "name": "FPO Officer"})
        r = client.get(f"/passport/{farm_id}", headers=auth)
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body["access"]["public_view"])
        self.assertFalse(body["access"]["staff"])
        self.assertEqual(body["owner_name"], "Verified smallholder")
        self.assertIsNone(body["village"])
        # farmer_phone must not leak into the identity block
        self.assertIsNone(body["phone"])
        self.assertEqual(body["farm_name"], "Verified smallholder farm")

    def test_fpo_ledger_history_is_redacted(self):
        farm_id = sample_data._fallback_farm_id(sample_data.FARMS[0]["key"])
        r = client.get(f"/ledger/{farm_id}", headers=_token(
            {"phone": "9777770001", "role": "fpo", "name": "FPO Officer"}))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["access"], "public_redacted")

    def test_fpo_validation_report_has_no_foreign_rows(self):
        auth = _token({"phone": "9000000001", "role": "fpo"})
        status = client.get("/validation/status", headers=auth).json()
        # DB is off -> no scoping evidence -> fail closed to the public view
        # (row-level comparisons stripped; only the aggregate count remains).
        self.assertNotIn("comparisons", status["report"])
        self.assertIn("comparison_count", status["report"])
        ev = client.get("/ops/ground-truth/eval", headers=auth).json()
        self.assertEqual(ev["comparisons"], [])

    def test_fpo_sees_bought_certificates_only_publicly(self):
        row = _listing()
        res = client.post("/marketplace/buy", json={
            "listing_id": row["id"], "credits": 3, "buyer_name": "Demo Corp"})
        self.assertTrue(res.json()["success"], res.json())
        cert_id = res.json()["certificate_id"]
        # Every purchase retires its slice, so the certificate itself is a
        # public record — but an FPO token on the demo stack (no fpo_id) must
        # see the redacted public view, never the private fields.
        auth = _token({"phone": "9777770001", "role": "fpo", "name": "FPO Officer"})
        r = client.get(f"/certificates/{cert_id}", headers=auth)
        self.assertEqual(r.status_code, 200)
        body = r.json()["certificate"]
        self.assertTrue(body["public_view"])
        self.assertFalse(body["access"]["staff"])
        self.assertIsNone(body["value_inr"])
        self.assertEqual(body["farmer_name"], "Verified Telangana Smallholder")
        self.assertIsNone(body["farmer_phone"])

    def test_admin_still_global_on_certificates(self):
        row = _listing()
        res = client.post("/marketplace/buy", json={
            "listing_id": row["id"], "credits": 4, "buyer_name": "Demo Corp"})
        self.assertTrue(res.json()["success"], res.json())
        cert_id = res.json()["certificate_id"]
        admin = _token({"phone": "9999999999", "role": "admin"})
        r = client.get(f"/certificates/{cert_id}", headers=admin)
        self.assertEqual(r.status_code, 200)
        body = r.json()["certificate"]
        self.assertFalse(body["public_view"])
        self.assertTrue(body["access"]["staff"])


class BuyerIdentityBindingTests(unittest.TestCase):
    """Certificate access binds to buyer_c_id, never to a display name."""

    def setUp(self):
        market_store.reset()
        _ledger._CHAINS = {}

    def _buy(self, row_id: str, credits: float) -> dict:
        res = client.post("/marketplace/buy", json={
            "listing_id": row_id, "credits": credits,
        }, headers=_token({"c_id": 1, "name": "Buyer One", "role": "buyer"}))
        self.assertTrue(res.json()["success"], res.json())
        return res.json()

    def test_sale_records_buyer_c_id_and_bind_access(self):
        row = _listing()
        result = self._buy(row["id"], 5)
        cert_id = result["certificate_id"]
        self.assertIsNotNone(cert_id)

        # The buyer of record (same c_id, ANY name) moves money freely:
        buy2 = client.post("/marketplace/buy", json={
            "listing_id": row["id"], "credits": 1, "buyer_name": "A Fake Name"},
            headers=_token({"c_id": 1, "name": "Whatever", "role": "buyer"}))
        self.assertTrue(buy2.json()["success"], buy2.json())

        # Admin sees the buyer_c_id recorded on the SALE event:
        admin = _token({"phone": "9999999999", "role": "admin"})
        chain = client.get(f"/ledger/{row['farm_id']}", headers=admin).json()
        sale = next(e for e in chain["events"] if e["type"] == "SALE")
        self.assertEqual(sale["payload"].get("buyer_c_id"), 1)

        # ... while the public ledger strip drops the buyer id entirely:
        public_chain = client.get(f"/ledger/{row['farm_id']}").json()
        self.assertEqual(public_chain["access"], "public_redacted")
        pub_sale = next(e for e in public_chain["events"] if e["type"] == "SALE")
        self.assertNotIn("buyer_c_id", pub_sale["payload"])

    def test_same_name_different_c_id_cannot_see_private_record(self):
        row = _listing()
        result = self._buy(row["id"], 3)
        cert_id = result["certificate_id"]
        # Identical display name, different corporate account: the public
        # certificate stays visible, the private record does not.
        stranger = _token({"c_id": 99, "name": "Buyer One", "role": "buyer"})
        r = client.get(f"/certificates/{cert_id}", headers=stranger)
        self.assertEqual(r.status_code, 200)
        body = r.json()["certificate"]
        self.assertTrue(body["public_view"])
        self.assertFalse(body["access"]["buyer"])
        self.assertIsNone(body["value_inr"])
        self.assertEqual(body["farmer_name"], "Verified Telangana Smallholder")

    def test_held_legacy_certificate_hidden_from_stranger_buyer(self):
        # A legacy "Sold" row with no ledger SALE event derives a
        # HELD_IN_ESCROW certificate, which stays private for everyone but
        # its owner/buyer-of-record/staff.
        now = "2026-10-22T00:00:00+00:00"
        listing_id = f"list-{uuid.uuid4()}"
        market_store.insert({
            "id": listing_id,
            "farm_id": f"farm-{uuid.uuid4()}",
            "farmer_phone": "9111111111",
            "farmer_name": "Secret Farmer",
            "crop": "Rice",
            "location": "Bonakal, Khammam, Telangana",
            "size_label": "4 ha",
            "listing_model": "Fixed Price",
            "price_per_credit": 100.0,
            "current_bid": 400.0,
            "bids_count": 1,
            "total_credits": 4,
            "carbon_credits": 4,
            "biodiversity_credits": 0,
            "status": "Sold",
            "expires_at": None,
            "image_url": None,
            "token_id": None,
            "tx_hash": "0xlegacy",
            "created_at": now,
            "updated_at": now,
        })
        # Anonymous list shows retired certificates only — never the held row.
        certs = client.get("/certificates").json()["certificates"]
        for c in certs:
            self.assertNotEqual(str(c.get("status")).upper(), "HELD_IN_ESCROW")
        # The held certificate id is deterministic; fetch it directly. It must
        # not resolve for a stranger buyer (404 — no existence leak either).
        cert_id = credit_lifecycle.certificate_id_for_sale(listing_id, 1)
        stranger = _token({"c_id": 99, "name": "No One", "role": "buyer"})
        r = client.get(f"/certificates/{cert_id}", headers=stranger)
        self.assertEqual(r.status_code, 404)
        r2 = client.get(f"/certificates/{cert_id}/pdf", headers=stranger)
        self.assertEqual(r2.status_code, 404)
        # ... and its own "farmer" (owner phone) legitimately sees it.
        owner = _token({"phone": "9111111111", "role": "farmer", "name": "Secret Farmer"})
        r3 = client.get(f"/certificates/{cert_id}", headers=owner)
        self.assertEqual(r3.status_code, 200)
        self.assertFalse(r3.json()["certificate"]["public_view"])

    def test_real_buyer_accesses_certificate_by_id(self):
        row = _listing()
        result = self._buy(row["id"], 6)
        buyer = _token({"c_id": 1, "name": "Buyer One", "role": "buyer"})
        r = client.get(
            f"/certificates/{result['certificate_id']}", headers=buyer)
        self.assertEqual(r.status_code, 200)
        body = r.json()["certificate"]
        self.assertFalse(body["public_view"])
        self.assertTrue(body["access"]["buyer"])
        self.assertEqual(body["buyer_c_id"], 1)

    def test_caller_is_buyer_variant_paths(self):
        # Demo stack is offline for this suite — verify the offline fallback
        # (name matching is allowed only while buyer ids are absent).
        self.assertIsNone(_db._supabase)
        cert = {"buyer": "Legacy Corp", "buyer_c_id": None}
        self.assertTrue(trust_router._caller_is_buyer(
            cert, {"role": "buyer", "name": "Legacy Corp"}))
        self.assertFalse(trust_router._caller_is_buyer(
            cert, {"role": "buyer", "name": "Someone Else"}))
        # live records: display names are presentation only once ids exist
        live = {"buyer": "Different Corp", "buyer_c_id": 7}
        self.assertTrue(trust_router._caller_is_buyer(
            live, {"role": "buyer", "c_id": 7, "name": "Whatever Name"}))
        self.assertFalse(trust_router._caller_is_buyer(
            live, {"role": "buyer", "c_id": 8, "name": "Different Corp"}))
        # non-buyer roles never inherit buyer access
        self.assertFalse(trust_router._caller_is_buyer(
            live, {"role": "farmer", "c_id": 7}))


class SimulatedPaymentsGateTests(unittest.TestCase):
    """One gate for simulated settlement, with a losing deprecated alias."""

    def tearDown(self):
        os.environ.pop("CARBONX_ACCEPT_SIMULATED_PAYMENTS", None)
        os.environ.pop("CARBONX_ALLOW_SIMULATED_SETTLEMENT", None)
        importlib.reload(app_config)

    def _reload(self):
        importlib.reload(app_config)
        return app_config.ACCEPT_SIMULATED_PAYMENTS, app_config.ALLOW_SIMULATED_SETTLEMENT

    def test_legacy_alias_enables_when_canonical_unset(self):
        os.environ["CARBONX_ALLOW_SIMULATED_SETTLEMENT"] = "1"
        accept, alias = self._reload()
        self.assertTrue(accept)
        self.assertEqual(alias, accept)  # deprecated attr tracks the canonical one

    def test_explicit_canonical_zero_beats_legacy_one(self):
        os.environ["CARBONX_ACCEPT_SIMULATED_PAYMENTS"] = "0"
        os.environ["CARBONX_ALLOW_SIMULATED_SETTLEMENT"] = "1"
        accept, alias = self._reload()
        self.assertFalse(accept)
        self.assertFalse(alias)

    def test_canonical_one_enables(self):
        os.environ["CARBONX_ACCEPT_SIMULATED_PAYMENTS"] = "1"
        accept, alias = self._reload()
        self.assertTrue(accept)
        self.assertTrue(alias)


class MigrationReadinessTests(unittest.TestCase):
    def test_migration_status_degrades_offline(self):
        _db._supabase = None
        _db._ready = False
        status = _db.migration_status()
        self.assertFalse(status["checked"])
        self.assertIsNone(status["ok"])
        self.assertEqual(status["missing_tables"], [])

    def test_required_schema_covers_trust_tables(self):
        for table in (
            "consent_records", "privacy_requests", "corporate_settings",
            "support_tickets", "ground_truth_samples", "ledger_events",
            "farm_evidence",
        ):
            self.assertIn(table, _db._REQUIRED_SCHEMA)


if __name__ == "__main__":
    unittest.main()
