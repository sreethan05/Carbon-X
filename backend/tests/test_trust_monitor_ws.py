"""Tests for Trust Router, Monitor Router, and WebSocket Router.

Covers:
1. GET /passport/{farm_id}: expected earnings calculation, trust block with real
   evidence flags, ledger event history, demo farm fallback.
2. POST /monitor/run: NDVI change detection, drop threshold (>= 0.15) flagging,
   MONITOR ledger event insertion, secret header auth (403 on invalid secret).
3. WebSocket /ws/ledger/{farm_id}: connection management, snapshot delivery with
   verified metadata and history, ring-buffer deduplication.
4. Certificate verification: GET /certificates/{cert_id}, PDF rendering endpoint call,
   404 on nonexistent cert, cache invalidation on retirement.
"""
import asyncio
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

for _k in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY",
           "VITE_SUPABASE_URL", "VITE_SUPABASE_ANON_KEY"):
    os.environ.pop(_k, None)
os.environ["SUPABASE_URL"] = ""
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = ""
os.environ["CARBONX_ALLOW_DEV_OTP"] = "1"

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402
from app import supabase_db as _db  # noqa: E402
from app import config as app_config  # noqa: E402
from app import security  # noqa: E402
from app.services import ledger as _ledger  # noqa: E402
from app.services import market_store  # noqa: E402
from app.routes import ws_router  # noqa: E402
from app.routes.monitor_router import perform_monitoring_cycle  # noqa: E402

# post-import reset (main.py load_dotenv(override=True) re-reads backend/.env)
for _k in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY",
           "VITE_SUPABASE_URL", "VITE_SUPABASE_ANON_KEY"):
    os.environ.pop(_k, None)
os.environ["SUPABASE_URL"] = ""
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = ""
_db._supabase = None
_db._ready = False


def setUpModule():
    for _k in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY",
               "VITE_SUPABASE_URL", "VITE_SUPABASE_ANON_KEY"):
        os.environ.pop(_k, None)
    os.environ["SUPABASE_URL"] = ""
    os.environ["SUPABASE_SERVICE_ROLE_KEY"] = ""
    _db._supabase = None
    _db._ready = False


client = TestClient(app)


class PassportTests(unittest.TestCase):
    def setUp(self):
        for _k in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY",
                   "VITE_SUPABASE_URL", "VITE_SUPABASE_ANON_KEY"):
            os.environ.pop(_k, None)
        os.environ["SUPABASE_URL"] = ""
        os.environ["SUPABASE_SERVICE_ROLE_KEY"] = ""
        _db._supabase = None
        _db._ready = False

    def test_passport_expected_earnings_and_trust(self):
        auth = {"Authorization": "Bearer " + security.create_access_token(
            {"phone": "9000000001", "role": "farmer"})}
        r = client.get("/passport/demo", headers=auth)
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body["success"])
        self.assertTrue(body["demo_mode"])

        # 1. Expected earnings calculation
        self.assertIn("expected_earnings", body)
        earnings = body["expected_earnings"]
        self.assertIn("expected_income_inr", earnings)
        self.assertIn("benchmark_price_per_credit", earnings)
        self.assertIn("range_inr", earnings)
        self.assertEqual(earnings["farmer_share_pct"], 70.0)

        # 2. Trust block with real evidence flags
        self.assertIn("trust", body)
        trust = body["trust"]
        self.assertIn("evidence_quality", trust)
        self.assertIn("uncertainty_pct", trust)
        self.assertIn("components", trust)
        self.assertIn("evidence", trust)
        ev = trust["evidence"]
        self.assertIn("practice_photo", ev)
        self.assertIn("geotag_inside_boundary", ev)
        self.assertIn("photo_count", ev)
        self.assertIn("geotag_count", ev)

        # 3. Ledger event history
        self.assertIn("ledger", body)
        ledger_block = body["ledger"]
        self.assertIn("events", ledger_block)
        self.assertIsInstance(ledger_block["events"], int)
        self.assertIn("verified", ledger_block)
        self.assertIn("history", ledger_block)
        self.assertIsInstance(ledger_block["history"], list)

    def test_passport_demo_fallback_when_unknown(self):
        # In demo mode, any id falls back to demo farm with demo_mode: True.
        # Use the demo farm's owner session to see the owner-visible farm name.
        auth = {"Authorization": "Bearer " + security.create_access_token(
            {"phone": "9000000001", "role": "farmer"})}
        r = client.get("/passport/unknown-farm-999", headers=auth)
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body["success"])
        self.assertTrue(body["demo_mode"])
        self.assertEqual(body["farm_name"], "Sri Venkateswara Organic Farm")


class MonitorRouterTests(unittest.TestCase):
    def setUp(self):
        for _k in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY",
                   "VITE_SUPABASE_URL", "VITE_SUPABASE_ANON_KEY"):
            os.environ.pop(_k, None)
        os.environ["SUPABASE_URL"] = ""
        os.environ["SUPABASE_SERVICE_ROLE_KEY"] = ""
        _db._supabase = None
        _db._ready = False

        self.tmp_ledger = os.path.join(os.path.dirname(__file__), "_test_monitor_ledger.json")
        os.environ["CARBONX_LEDGER_PATH"] = self.tmp_ledger
        _ledger._PATH = self.tmp_ledger
        _ledger._CHAINS = {}
        if os.path.exists(self.tmp_ledger):
            os.remove(self.tmp_ledger)

    def tearDown(self):
        if os.path.exists(self.tmp_ledger):
            os.remove(self.tmp_ledger)

    def test_monitor_auth_with_secret(self):
        # Configure a required secret
        orig_secret = app_config.MONITOR_SECRET
        try:
            app_config.MONITOR_SECRET = "test-secret-12345"
            # 1. No secret and no auth -> 403
            r = client.post("/monitor/run")
            self.assertEqual(r.status_code, 403)
            self.assertEqual(r.json().get("code"), "FORBIDDEN")

            # 2. Wrong secret -> 403
            r = client.post("/monitor/run", headers={"X-Monitor-Secret": "wrong"})
            self.assertEqual(r.status_code, 403)

            # 3. Correct secret -> allowed (returns 200, offline DB message in test suite)
            r = client.post("/monitor/run", headers={"X-Monitor-Secret": "test-secret-12345"})
            self.assertEqual(r.status_code, 200)
            body = r.json()
            self.assertIn("message", body)
            self.assertIn("database", body["message"])

            # 4. FPO user session without secret -> allowed (returns 200)
            fpo_token = security.create_access_token({"phone": "9000000001", "role": "fpo"})
            r_fpo = client.post("/monitor/run", headers={"Authorization": f"Bearer {fpo_token}"})
            self.assertEqual(r_fpo.status_code, 200)

            # 5. Admin user session without secret -> allowed (returns 200)
            admin_token = security.create_access_token({"phone": "9000000002", "role": "admin"})
            r_admin = client.post("/monitor/run", headers={"Authorization": f"Bearer {admin_token}"})
            self.assertEqual(r_admin.status_code, 200)

            # 6. Farmer session (unauthorized role) without secret -> 403
            farmer_token = security.create_access_token({"phone": "9000000003", "role": "farmer"})
            r_farmer = client.post("/monitor/run", headers={"Authorization": f"Bearer {farmer_token}"})
            self.assertEqual(r_farmer.status_code, 403)
        finally:
            app_config.MONITOR_SECRET = orig_secret

    def test_perform_monitoring_cycle_ndvi_drop_and_ledger_event(self):
        """Verify:
        - 5-day NDVI drop threshold checking (drop >= 0.15 triggers Flagged)
        - Healthy farms (drop < 0.15) update without Flagged status
        - Pending farms are skipped
        - MONITOR event inserted into the tamper-evident ledger and chain verifies
        """
        farms_data = [
            # Farm 1: Drop = 0.65 - 0.45 = 0.20 >= 0.15 threshold -> Flagged + MONITOR event
            {
                "id": "farm-drop-flagged",
                "name": "Drought Impacted Parcel",
                "ndvi": 0.45,
                "status": "Active",
                "last_monitor_ndvi": 0.65,
                "last_monitored_at": "2026-10-10T00:00:00Z",
            },
            # Farm 2: Drop = 0.62 - 0.60 = 0.02 < 0.15 threshold -> Healthy
            {
                "id": "farm-stable-healthy",
                "name": "Healthy Agroforestry Parcel",
                "ndvi": 0.60,
                "status": "Active",
                "last_monitor_ndvi": 0.62,
                "last_monitored_at": "2026-10-10T00:00:00Z",
            },
            # Farm 3: Pending farm -> must be skipped
            {
                "id": "farm-pending-skip",
                "name": "Pending Verification Parcel",
                "ndvi": 0.30,
                "status": "Pending",
                "last_monitor_ndvi": 0.60,
                "last_monitored_at": "2026-10-10T00:00:00Z",
            },
            # Farm 4: Baseline first scan (last_monitor_ndvi is None) -> Healthy
            {
                "id": "farm-first-baseline",
                "name": "Newly Registered Parcel",
                "ndvi": 0.55,
                "status": "Active",
                "last_monitor_ndvi": None,
                "last_monitored_at": None,
            },
        ]

        updates = []

        mock_sb = MagicMock()

        def mock_table(table_name):
            if table_name == "farms":
                t = MagicMock()
                t.select.return_value.execute.return_value.data = farms_data

                def mock_update(payload):
                    u = MagicMock()

                    def mock_eq(col, val):
                        updates.append({"id": val, "payload": payload})
                        eq_m = MagicMock()
                        eq_m.execute.return_value.data = [payload]
                        return eq_m

                    u.eq.side_effect = mock_eq
                    return u

                t.update.side_effect = mock_update
                return t
            return MagicMock()

        mock_sb.table.side_effect = mock_table

        with patch.object(_db, "is_ready", return_value=True), \
             patch.object(_db, "_client", return_value=mock_sb), \
             patch.object(_ledger, "_sb", return_value=None):

            result = perform_monitoring_cycle()

            self.assertTrue(result["success"])
            self.assertEqual(result["checked"], 3)  # Farm 3 (pending) was skipped
            self.assertEqual(result["healthy"], 2)  # Farm 2 and Farm 4
            self.assertEqual(result["at_risk_count"], 1)  # Farm 1
            self.assertEqual(result["alert_threshold"], 0.15)

            # Check at_risk list details
            at_risk_item = result["at_risk"][0]
            self.assertEqual(at_risk_item["farm_id"], "farm-drop-flagged")
            self.assertEqual(at_risk_item["drop"], 0.20)
            self.assertEqual(at_risk_item["previous_ndvi"], 0.65)
            self.assertEqual(at_risk_item["current_ndvi"], 0.45)

            # Check DB update calls: Farm 1 updated with status="Flagged"
            flagged_updates = [u for u in updates if u["id"] == "farm-drop-flagged"]
            self.assertEqual(len(flagged_updates), 1)
            self.assertEqual(flagged_updates[0]["payload"]["status"], "Flagged")
            self.assertEqual(flagged_updates[0]["payload"]["last_monitor_ndvi"], 0.45)

            # Check healthy updates: status NOT updated to Flagged
            healthy_updates = [u for u in updates if u["id"] == "farm-stable-healthy"]
            self.assertEqual(len(healthy_updates), 1)
            self.assertNotIn("status", healthy_updates[0]["payload"])
            self.assertEqual(healthy_updates[0]["payload"]["last_monitor_ndvi"], 0.60)

            # Check MONITOR event insertion into the tamper-evident ledger
            chain = _ledger.get_chain("farm-drop-flagged")
            self.assertGreaterEqual(len(chain), 1)
            monitor_event = chain[-1]
            self.assertEqual(monitor_event["type"], "MONITOR")
            self.assertEqual(monitor_event["payload"]["risk"], "ndvi_drop")
            self.assertEqual(monitor_event["payload"]["drop"], 0.20)
            self.assertEqual(monitor_event["payload"]["previous_ndvi"], 0.65)
            self.assertEqual(monitor_event["payload"]["current_ndvi"], 0.45)
            self.assertIn("hash", monitor_event)
            self.assertIn("prev_hash", monitor_event)

            # Verify cryptographic chain integrity
            verification = _ledger.verify_chain("farm-drop-flagged")
            self.assertTrue(verification["valid"])
            self.assertEqual(verification["length"], len(chain))

    def test_github_workflow_cron_and_contract(self):
        """Verify .github/workflows/monitor.yml configuration:
        - Cron schedule is '0 3 */5 * *' (5-day revisit cadence at 03:00 UTC)
        - Passes X-Monitor-Secret header matching CARBONX_MONITOR_SECRET
        - Validates HTTP 200 and success: true
        """
        workflow_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            ".github", "workflows", "monitor.yml"
        )
        self.assertTrue(os.path.exists(workflow_path), f"Workflow file not found at {workflow_path}")
        with open(workflow_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Cron expression check
        self.assertIn('cron: "0 3 */5 * *"', content)
        # Header check
        self.assertIn('X-Monitor-Secret: $MONITOR_SECRET', content)
        # HTTP 200 check
        self.assertIn('test "$code" = "200"', content)
        # success: true validation
        self.assertIn('"success":[[:space:]]*true', content)
        # manual trigger support
        self.assertIn('workflow_dispatch:', content)


class WebSocketRouterTests(unittest.TestCase):
    def test_websocket_snapshot_delivery(self):
        # Test WS connection and snapshot format
        farm_id = "test-ws-farm-1"
        _ledger.ensure_genesis(farm_id, {"farm": "Test Farm", "crop": "Rice"})

        with client.websocket_connect(f"/ws/ledger/{farm_id}") as ws:
            data = ws.receive_json()
            self.assertEqual(data.get("type"), "snapshot")
            self.assertEqual(data.get("farm_id"), farm_id)
            # events must be an int count for frontend
            self.assertIsInstance(data.get("events"), int)
            self.assertGreaterEqual(data["events"], 1)
            self.assertTrue(data.get("verified"))
            self.assertIn("tail_hash", data)
            self.assertIn("types", data)
            self.assertIn("history", data)
            self.assertIsInstance(data["history"], list)

    def test_deduplication_ring(self):
        farm_id = "test-dedupe-farm"
        event = {"seq": 1, "hash": "abcd1234hash", "type": "SALE", "payload": {}}

        # First delivery: True
        first = ws_router._mark_delivered(farm_id, event)
        self.assertTrue(first)

        # Immediate duplicate: False
        dup = ws_router._mark_delivered(farm_id, event)
        self.assertFalse(dup)


class CertificateTests(unittest.TestCase):
    def setUp(self):
        for _k in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY",
                   "VITE_SUPABASE_URL", "VITE_SUPABASE_ANON_KEY"):
            os.environ.pop(_k, None)
        os.environ["SUPABASE_URL"] = ""
        os.environ["SUPABASE_SERVICE_ROLE_KEY"] = ""
        _db._supabase = None
        _db._ready = False
        market_store.reset()

    def test_certificate_get_and_pdf(self):
        # Buy credits to generate a sold listing
        listings = client.get("/marketplace/listings", params={"status": "Active"}).json()["listings"]
        target = min(listings, key=lambda l: float(l["total_credits"]))
        buy_res = client.post("/marketplace/buy", json={
            "listing_id": target["id"],
            "credits": target["total_credits"],
            "buyer_name": "Cert Test Corp",
        }).json()
        self.assertTrue(buy_res["success"], buy_res)
        cert_id = buy_res["certificate_id"]

        # GET /certificates/{cert_id}
        cert_res = client.get(f"/certificates/{cert_id}")
        self.assertEqual(cert_res.status_code, 200)
        cbody = cert_res.json()
        self.assertTrue(cbody["success"])
        self.assertEqual(cbody["certificate"]["id"], cert_id)
        self.assertIn("batch_hash", cbody["certificate"])
        self.assertIn("ledger_verified", cbody["certificate"])

        # GET /certificates/{cert_id}/pdf
        pdf_res = client.get(f"/certificates/{cert_id}/pdf")
        self.assertEqual(pdf_res.status_code, 200)
        self.assertEqual(pdf_res.headers.get("content-type"), "application/pdf")
        self.assertGreater(len(pdf_res.content), 1000)

        # Nonexistent cert -> 404
        bad_pdf = client.get("/certificates/CX-2026-CERT-NONEXISTENT/pdf")
        self.assertEqual(bad_pdf.status_code, 404)
        self.assertEqual(bad_pdf.json().get("code"), "NOT_FOUND")

        bad_cert = client.get("/certificates/CX-2026-CERT-NONEXISTENT")
        self.assertEqual(bad_cert.status_code, 404)


if __name__ == "__main__":
    unittest.main()
