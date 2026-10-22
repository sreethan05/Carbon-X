"""End-to-end tests for the trust programme (validation, privacy, lifecycle).

All tests run in demo/offline mode with an isolated in-memory ledger and
marketplace store.  They never touch the real Supabase project or ledger file.
"""
from __future__ import annotations

import csv
import io
import os
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch

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
from app import supabase_db as _db  # noqa: E402
from app import security  # noqa: E402
from app import sample_data  # noqa: E402
from app.services import credit_engine  # noqa: E402
from app.services import evidence_service  # noqa: E402
from app.services import ledger as _ledger  # noqa: E402
from app.services import market_store  # noqa: E402
from app.services import privacy  # noqa: E402
import importlib  # noqa: E402
ops_router = importlib.import_module("app.routes.ops_router")  # noqa: E402
evidence_router = importlib.import_module("app.routes.evidence_router")  # noqa: E402

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
    tempfile.mkdtemp(prefix="carbonx_trust_program_"), "ledger.json"
)
_ledger._CHAINS = {}
_ledger._MIGRATED = True

client = TestClient(app)


def _token(phone: str, role: str = "farmer", name: str = "Test User") -> dict:
    token = security.create_access_token({"phone": phone, "role": role, "name": name})
    return {"Authorization": f"Bearer {token}"}


def _listing(
    *,
    phone: str = "9111111111",
    name: str = "Test Farmer",
    credits: float = 10.0,
    price: float = 100.0,
    status: str = "Active",
    farm_id: str | None = None,
) -> dict:
    now = "2026-10-22T00:00:00+00:00"
    row = {
        "id": f"list-{uuid.uuid4()}",
        "farm_id": farm_id or f"farm-{uuid.uuid4()}",
        "farmer_phone": phone,
        "farmer_name": name,
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
        "status": status,
        "expires_at": None,
        "image_url": None,
        "token_id": None,
        "tx_hash": None,
        "created_at": now,
        "updated_at": now,
    }
    return market_store.insert(row)


def _buy(listing_id: str, credits: float, buyer: str = "Access Buyer") -> dict:
    res = client.post(
        "/marketplace/buy",
        json={"listing_id": listing_id, "credits": credits, "buyer_name": buyer},
    )
    return res.json()


class LifecycleAndPayoutTests(unittest.TestCase):
    def setUp(self):
        market_store.reset()
        _ledger._CHAINS = {}
        privacy.reset_memory()
        evidence_service.reset_memory()
        ops_router.reset_ground_truth_memory()

    def test_partial_sales_have_unique_certificates_and_refund_restores_balance(self):
        row = _listing(phone="9111111111", name="Secret Farmer", credits=10, price=100)
        first = _buy(row["id"], 4)
        second = _buy(row["id"], 3)
        self.assertTrue(first["success"], first)
        self.assertTrue(second["success"], second)
        self.assertNotEqual(first["certificate_id"], second["certificate_id"])
        self.assertEqual(second["sale_seq"], 2)
        self.assertTrue(second["certificate_id"].endswith("-02"))

        listed = market_store.get(row["id"])
        self.assertEqual(float(listed["total_credits"]), 3.0)
        self.assertEqual(listed["status"], "Active")
        self.assertEqual(listed["lifecycle_state"], "Partially Sold")
        self.assertEqual(float(listed["credits_sold"]), 7.0)

        public_certs = client.get("/certificates").json()["certificates"]
        ids = {c["id"] for c in public_certs}
        self.assertIn(first["certificate_id"], ids)
        self.assertIn(second["certificate_id"], ids)
        cert = next(c for c in public_certs if c["id"] == first["certificate_id"])
        self.assertIsNone(cert["farmer_phone"])
        self.assertIsNone(cert["value_inr"])
        self.assertEqual(cert["location"], "Khammam, Telangana")
        self.assertEqual(cert["farmer_name"], "Verified Telangana Smallholder")
        self.assertTrue(cert["public_view"])

        refund = client.post(
            f"/certificates/{first['certificate_id']}/refund",
            json={"reason": "Buyer requested cancellation"},
        ).json()
        self.assertTrue(refund["success"], refund)
        self.assertEqual(refund["credits_restored"], 4.0)
        listed = market_store.get(row["id"])
        self.assertEqual(float(listed["total_credits"]), 7.0)
        self.assertEqual(float(listed["credits_sold"]), 3.0)
        self.assertEqual(listed["lifecycle_state"], "Partially Sold")

        # Public cannot see a refunded (void) certificate; the farmer can.
        self.assertEqual(
            client.get(f"/certificates/{first['certificate_id']}").status_code, 404
        )
        own = client.get(
            f"/certificates/{first['certificate_id']}",
            headers=_token("9111111111"),
        ).json()["certificate"]
        self.assertEqual(own["status"], "REFUNDED")

        again = client.post(
            f"/certificates/{first['certificate_id']}/refund",
            json={"reason": "double click"},
            headers=_token("9111111111"),
        ).json()
        self.assertTrue(again.get("already_refunded"))
        self.assertEqual(float(market_store.get(row["id"])["total_credits"]), 7.0)

        wallet = client.get("/wallet", headers=_token("9111111111")).json()
        self.assertTrue(wallet["success"])
        self.assertEqual(len(wallet["transactions"]), 2)
        statuses = {t["certificate_id"]: t["status"] for t in wallet["transactions"]}
        self.assertEqual(statuses[first["certificate_id"]], "REFUNDED")
        self.assertEqual(statuses[second["certificate_id"]], "SETTLED")
        self.assertEqual(wallet["farmer_share_total"], 210.0)  # 3 credits x 100 x 70%
        self.assertTrue(wallet["reconciliation"]["display_matches_ledger"])

    def test_dispute_freezes_sales_and_refund_resolution(self):
        row = _listing(phone="9444444444", credits=5, price=100)
        sale = _buy(row["id"], 2)
        self.assertTrue(sale["success"], sale)

        opened = client.post(
            f"/certificates/{sale['certificate_id']}/dispute",
            json={"reason": "Boundary claim questioned"},
        ).json()
        self.assertTrue(opened["success"], opened)
        frozen = market_store.get(row["id"])
        self.assertEqual(frozen["dispute_status"], "OPEN")
        self.assertEqual(frozen["lifecycle_state"], "Disputed")

        blocked = _buy(row["id"], 1)
        self.assertFalse(blocked["success"])
        self.assertEqual(blocked["code"], "DISPUTED")

        resolved = client.post(
            f"/certificates/{sale['certificate_id']}/dispute/resolve",
            json={"decision": "refund", "note": "Evidence did not match the parcel"},
        ).json()
        self.assertTrue(resolved["success"], resolved)
        self.assertEqual(resolved["decision"], "refund")
        after = market_store.get(row["id"])
        self.assertEqual(float(after["total_credits"]), 5.0)
        self.assertEqual(after["dispute_status"], "REFUNDED")
        self.assertEqual(after["status"], "Active")
        self.assertEqual(float(after["credits_sold"]), 0.0)

    def test_correction_is_audited_and_does_not_change_money(self):
        row = _listing(phone="9555555555", name="Old Name", credits=2, price=100)
        sale = _buy(row["id"], 2)
        corrected = client.post(
            f"/certificates/{sale['certificate_id']}/correction",
            json={
                "field": "farmer_name",
                "corrected_value": "Corrected Name",
                "reason": "Spelling correction with consent",
            },
        ).json()
        self.assertTrue(corrected["success"], corrected)
        self.assertTrue(corrected["financial_values_unchanged"])
        own = client.get(
            f"/certificates/{sale['certificate_id']}",
            headers=_token("9555555555"),
        ).json()["certificate"]
        self.assertEqual(own["farmer_name"], "Corrected Name")
        self.assertEqual(own["value_inr"], 200.0)
        self.assertEqual(own["corrections_applied"][0]["field"], "farmer_name")

        lifecycle = client.get(
            f"/certificates/{sale['certificate_id']}/lifecycle",
            headers=_token("9555555555"),
        ).json()
        self.assertEqual(
            {e["type"] for e in lifecycle["audit_events"]}, {"CORRECTION"}
        )
        self.assertEqual(lifecycle["payout"]["gross_inr"], 200.0)


class PrivacyTests(unittest.TestCase):
    PHONE = "9222222222"

    def setUp(self):
        market_store.reset()
        _ledger._CHAINS = {}
        privacy.reset_memory()
        evidence_service.reset_memory()
        ops_router.reset_ground_truth_memory()

    def test_consent_export_correction_and_deletion(self):
        auth = _token(self.PHONE)

        policy = client.get("/privacy/policy").json()
        self.assertTrue(policy["success"])
        self.assertIn("platform_service", policy["purposes"])
        self.assertIn("privacy counsel", policy["legal_note"])

        consent = client.post(
            "/privacy/consent",
            json={"purposes": {"mrv_evidence": True, "marketing": False}},
            headers=auth,
        ).json()
        self.assertTrue(consent["success"])
        self.assertTrue(consent["current"]["mrv_evidence"]["granted"])
        self.assertFalse(consent["current"]["marketing"]["granted"])

        withdraw = client.post("/privacy/consent/withdraw/marketing", headers=auth).json()
        self.assertFalse(withdraw["current"]["marketing"]["granted"])
        required = client.post(
            "/privacy/consent/withdraw/platform_service", headers=auth
        )
        self.assertEqual(required.status_code, 409)

        export = client.get("/privacy/export", headers=auth).json()["archive"]
        self.assertEqual(export["data_subject"]["phone"], self.PHONE)
        self.assertEqual(export["schema_version"], "carbonx-privacy-export-v1")
        self.assertEqual(export["kyc"], None)

        created = client.post(
            "/privacy/corrections",
            json={
                "field": "village",
                "current_value": "Old Village",
                "requested_value": "New Village",
                "reason": "Revenue record updated",
            },
            headers=auth,
        ).json()["request"]
        self.assertEqual(created["status"], "in_review")

        listed = client.get("/ops/privacy/requests", headers=_token("9999999999", "verifier")).json()
        self.assertTrue(listed["success"])
        self.assertTrue(any(r["id"] == created["id"] for r in listed["requests"]))
        self.assertTrue(all("****" in (r.get("phone") or "") for r in listed["requests"]))

        resolved = client.post(
            f"/ops/privacy/corrections/{created['id']}/resolve",
            json={"decision": "applied", "note": "Checked revenue record"},
            headers=_token("9999999999", "verifier"),
        ).json()
        self.assertTrue(resolved["applied"])
        mine = client.get("/privacy/requests", headers=auth).json()["requests"]
        self.assertEqual(next(r for r in mine if r["id"] == created["id"])["status"], "completed")

        row = _listing(phone=self.PHONE, credits=5, price=100)
        checks = client.get("/privacy/deletion-check", headers=auth).json()
        self.assertFalse(checks["can_delete"])
        self.assertEqual(checks["blockers"][0]["type"], "active_listing")

        market_store.update(row["id"], {"status": "Sold", "total_credits": 0})
        checks = client.get("/privacy/deletion-check", headers=auth).json()
        self.assertTrue(checks["can_delete"])

        deleted = client.post(
            "/privacy/delete", json={"confirm": "DELETE", "reason": "No longer farming"},
            headers=auth,
        ).json()
        self.assertTrue(deleted["success"], deleted)
        self.assertEqual(deleted["mode"], "memory")
        self.assertTrue(deleted["request"]["status"] == "completed")

        # The current token is invalid immediately after erasure (revoked or
        # rejected as a deleted account — both are correct).
        self.assertIn(client.get("/privacy/consent", headers=auth).status_code, (401, 403))
        self.assertTrue(privacy.deleted_in_session(self.PHONE))


class ValidationTests(unittest.TestCase):
    def setUp(self):
        _ledger._CHAINS = {}
        ops_router.reset_ground_truth_memory()
        market_store.reset()

    def tearDown(self):
        ops_router.reset_ground_truth_memory()

    def test_proxy_is_labelled_until_thirty_verified_samples(self):
        empty = client.get("/validation/status").json()
        self.assertEqual(empty["status"], "proxy_unvalidated")
        self.assertTrue(empty["proxy_estimate"])
        claims = client.get("/validation/claims").json()
        self.assertTrue(claims["supported_claims"])
        self.assertTrue(claims["unsupported_claims"])

        farm = sample_data.FARMS[0]
        farm_id = sample_data._fallback_farm_id(farm["key"])
        auth = _token("9999999999", "verifier")
        first = client.post(
            "/ops/ground-truth",
            json={
                "farm_id": farm_id,
                "measured_soc_tco2e_ha": 1.0,
                "measurement_type": "rate",
                "verification_status": "field_verified",
                "crop": farm["crop"],
                "source": "field_survey",
            },
            headers=auth,
        ).json()["sample"]
        snapshot = first["estimate_snapshot"]
        measured = snapshot["estimated_tco2e_ha"]
        self.assertGreater(measured, 0)

        # Replace the first sample with the exact estimate, then add 29 more.
        ops_router.reset_ground_truth_memory()
        for _ in range(30):
            res = client.post(
                "/ops/ground-truth",
                json={
                    "farm_id": farm_id,
                    "measured_soc_tco2e_ha": measured,
                    "measurement_type": "rate",
                    "verification_status": "field_verified",
                    "crop": farm["crop"],
                    "source": "field_survey",
                },
                headers=auth,
            )
            self.assertTrue(res.json()["success"], res.text)

        report = client.get("/validation/status").json()
        self.assertEqual(report["status"], "field_validated_limited")
        self.assertEqual(report["counts"]["verified_rate_samples"], 30)
        self.assertEqual(report["metrics"]["mape_pct"], 0.0)
        self.assertGreaterEqual(report["metrics"]["ci90_coverage_pct"], 50.0)


class PublicAccessTests(unittest.TestCase):
    OWNER = "9333333333"

    def setUp(self):
        market_store.reset()
        _ledger._CHAINS = {}
        privacy.reset_memory()
        evidence_service.reset_memory()
        ops_router.reset_ground_truth_memory()

    def test_certificate_csv_and_pdf_share_public_redaction(self):
        row = _listing(phone=self.OWNER, name="Secret Farmer", credits=4, price=100)
        sale = _buy(row["id"], 4, buyer="Access Buyer")
        self.assertTrue(sale["success"], sale)

        cert = client.get(f"/certificates/{sale['certificate_id']}").json()["certificate"]
        self.assertIsNone(cert["farmer_phone"])
        self.assertIsNone(cert["value_inr"])
        self.assertEqual(cert["farmer_name"], "Verified Telangana Smallholder")
        self.assertEqual(cert["location"], "Khammam, Telangana")

        csv_res = client.get("/certificates/export.csv")
        self.assertEqual(csv_res.status_code, 200)
        rows = list(csv.DictReader(io.StringIO(csv_res.text)))
        row_csv = next(r for r in rows if r["id"] == sale["certificate_id"])
        self.assertEqual(row_csv["farmer_name"], "Verified Telangana Smallholder")
        self.assertEqual(row_csv["value_inr"], "")
        self.assertNotIn("Secret Farmer", csv_res.text)
        self.assertNotIn(self.OWNER, csv_res.text)

        pdf_res = client.get(f"/certificates/{sale['certificate_id']}/pdf")
        self.assertEqual(pdf_res.status_code, 200)
        self.assertEqual(pdf_res.headers.get("X-CarbonX-Access"), "public")
        self.assertTrue(pdf_res.content.startswith(b"%PDF"))

        buyer = client.get(
            f"/certificates/{sale['certificate_id']}",
            headers=_token("9888888888", "buyer", "Access Buyer"),
        ).json()["certificate"]
        self.assertIsNone(buyer["farmer_phone"])
        self.assertEqual(buyer["split"], {})

        farmer = client.get(
            f"/certificates/{sale['certificate_id']}", headers=_token(self.OWNER)
        ).json()["certificate"]
        self.assertEqual(farmer["farmer_name"], "Secret Farmer")
        self.assertEqual(farmer["value_inr"], 400.0)
        self.assertEqual(farmer["split"]["farmer_inr"], 280.0)

    def test_passport_and_ledger_redact_public_money_and_identity(self):
        row = _listing(phone=self.OWNER, name="Secret Farmer", credits=4, price=100)
        sale = _buy(row["id"], 4, buyer="Access Buyer")
        farm_id = row["farm_id"]

        public = client.get(f"/passport/{farm_id}").json()
        self.assertEqual(public["owner_name"], "Verified smallholder")
        self.assertIsNone(public["phone"])
        self.assertIsNone(public["village"])
        self.assertEqual(public["location_precision"], "district")
        self.assertIsNone(public["expected_earnings"])
        self.assertNotIn("farm_name", public["verification_hash_covers"])
        self.assertEqual(public["ledger"]["access"], "public")
        payloads = [e["payload"] for e in public["ledger"]["history"]]
        self.assertTrue(any(p.get("certificate_id") == sale["certificate_id"] for p in payloads))
        for payload in payloads:
            self.assertNotIn("buyer", payload)
            self.assertNotIn("gross_inr", payload)
            self.assertNotIn("farmer_inr", payload)

        owner = client.get(
            f"/passport/{farm_id}", headers=_token("9000000001")
        ).json()
        self.assertEqual(owner["owner_name"], "Registered Farmer")
        self.assertIsNotNone(owner["expected_earnings"])
        full_payloads = [e["payload"] for e in owner["ledger"]["history"]]
        full_sale = next(p for p in full_payloads if p.get("certificate_id") == sale["certificate_id"])
        self.assertEqual(full_sale["buyer"], "Access Buyer")
        self.assertEqual(full_sale["gross_inr"], 400.0)

        ledger_public = client.get(f"/ledger/{farm_id}").json()
        self.assertEqual(ledger_public["access"], "public_redacted")
        for event in ledger_public["events"]:
            self.assertNotIn("gross_inr", event["payload"])

    def test_evidence_coordinates_are_owner_only(self):
        farm_id = "farm-evidence-public-test"
        farm = {
            "id": farm_id,
            "owner_phone": self.OWNER,
            "fpo_id": None,
            "geojson": {
                "type": "Polygon",
                "coordinates": [[[79.15, 17.25], [79.16, 17.25],
                                 [79.16, 17.26], [79.15, 17.26], [79.15, 17.25]]],
            },
        }
        with patch.object(evidence_router, "_load_farm", return_value=farm):
            added = client.post(
                f"/farms/{farm_id}/evidence/geotag",
                json={"latitude": 17.255, "longitude": 79.155},
                headers=_token(self.OWNER),
            ).json()
            self.assertTrue(added["success"], added)
            self.assertTrue(added["geotag"]["inside_boundary"])

            public = client.get(f"/farms/{farm_id}/evidence").json()
            self.assertEqual(public["access"]["level"], "public")
            self.assertFalse(public["access"]["exact_coordinates"])
            self.assertEqual(public["geotags"], [])

            owner = client.get(
                f"/farms/{farm_id}/evidence", headers=_token(self.OWNER)
            ).json()
            self.assertEqual(owner["access"]["level"], "full")
            self.assertEqual(owner["geotags"][0]["latitude"], 17.255)


class CorporateSettingsTests(unittest.TestCase):
    """Buyer account preferences persist server-side (memory fallback here)."""

    def setUp(self):
        import app.services.corporate_settings as settings_service

        settings_service._memory.clear()
        settings_service._table_unavailable.clear()
        self._svc = settings_service
        self.headers = {
            "Authorization": "Bearer "
            + security.create_access_token({
                "c_id": 7, "role": "buyer", "name": "Pref Buyer Ltd",
            })
        }

    def test_put_and_get_returns_saved_target(self):
        put = client.put(
            "/corporate/settings",
            json={"target_offsets_mt": 250.5},
            headers=self.headers,
        )
        self.assertTrue(put.json().get("success"), put.json())
        self.assertEqual(put.json()["settings"]["target_offsets_mt"], 250.5)

        got = client.get("/corporate/settings", headers=self.headers).json()
        self.assertTrue(got["success"], got)
        self.assertEqual(got["settings"]["target_offsets_mt"], 250.5)
        # Live DB is unconfigured in this suite, so the labelled fallback is used.
        self.assertEqual(got["settings"]["storage"], "memory")

    def test_invalid_target_rejected(self):
        res = client.put(
            "/corporate/settings",
            json={"target_offsets_mt": -5},
            headers=self.headers,
        )
        self.assertEqual(res.status_code, 422)

    def test_requires_buyer_session(self):
        anon = client.get("/corporate/settings")
        self.assertEqual(anon.status_code, 401)


if __name__ == "__main__":
    unittest.main()
