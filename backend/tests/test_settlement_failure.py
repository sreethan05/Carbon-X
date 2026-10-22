"""Settlement recovery: ledger-write failure must not eat credits (P3.3).

When the balance CAS commits but the hash-chain append fails, the settlement
must (a) restore the listing balance under the same lock and (b) record an
auditable SALE_FAILED event for reconciliation — never deliver a certificate.
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
from app.services import ledger as _ledger, market_store, privacy  # noqa: E402
import importlib  # noqa: E402

marketplace_router = importlib.import_module("app.routes.marketplace_router")  # noqa: E402

for _k in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY",
           "VITE_SUPABASE_URL", "VITE_SUPABASE_ANON_KEY"):
    os.environ.pop(_k, None)
os.environ["SUPABASE_URL"] = ""
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = ""
_db._supabase = None
_db._ready = False

_ledger._PATH = os.path.join(tempfile.mkdtemp(prefix="carbonx_settle_fail_"), "ledger.json")
_ledger._CHAINS = {}
_ledger._MIGRATED = True

client = TestClient(app)


def _listing(credits: float = 10.0) -> dict:
    now = "2026-10-22T00:00:00+00:00"
    return market_store.insert({
        "id": f"list-{uuid.uuid4()}",
        "farm_id": f"farm-{uuid.uuid4()}",
        "farmer_phone": "9331111111",
        "farmer_name": "Recovery Farmer",
        "crop": "Rice",
        "location": "Bonakal, Khammam, Telangana",
        "size_label": f"{credits:g} ha",
        "listing_model": "Fixed Price",
        "price_per_credit": 150.0,
        "total_credits": credits,
        "carbon_credits": credits,
        "biodiversity_credits": 0,
        "status": "Active",
        "created_at": now,
        "updated_at": now,
    })


class SettlementFailureRecoveryTests(unittest.TestCase):
    def setUp(self):
        market_store.reset()
        _ledger._CHAINS = {}
        privacy.reset_memory()

    def test_ledger_write_failure_restores_balance_and_records_sale_failed(self):
        row = _listing(credits=10.0)

        def exploding_append(entity_id, event_type, payload):
            if event_type == "SALE":
                raise OSError("simulated ledger disk/driver outage")
            return _real_append(entity_id, event_type, payload)

        with mock.patch.object(
            marketplace_router, "ledger",
            **{"append_event.side_effect": exploding_append},
        ) as _patched:
            # append_event remains a real function for SALE_FAILED writes.
            _real_append = _ledger.append_event
            _patched.append_event.side_effect = exploding_append

            res = client.post("/marketplace/buy", json={
                "listing_id": row["id"], "credits": 4, "buyer_name": "Recovery Buyer",
            })
            body = res.json()

        # API contract: no certificate delivered; explicit reconciliation path.
        self.assertFalse(body.get("success"), body)
        self.assertEqual(body.get("code"), "LEDGER_WRITE_FAILED_BALANCE_RESTORED")
        self.assertTrue(body.get("balance_restored"))
        self.assertFalse(body.get("requires_reconciliation"))
        self.assertIn("escrow_ref", body)

        # Balance is back to the pre-sale amount.
        fresh = market_store.get(row["id"]) or {}
        self.assertEqual(float(fresh.get("total_credits") or 0), 10.0)
        self.assertEqual(str(fresh.get("status") or "").lower(), "active")

        # Chain has no settled sale/retire for this listing; the failure is
        # auditable as SALE_FAILED.
        farm_id = row["farm_id"]
        types = [e.get("type") for e in _ledger.get_chain(farm_id)]
        self.assertNotIn("SALE", types)
        self.assertNotIn("RETIRE", types)
        self.assertIn("SALE_FAILED", types)

        # The buyer can retry: a clean settle now succeeds against the
        # restored balance.
        retry = client.post("/marketplace/buy", json={
            "listing_id": row["id"], "credits": 4, "buyer_name": "Recovery Buyer",
        }).json()
        self.assertTrue(retry.get("success"), retry)
        self.assertEqual(
            float((market_store.get(row["id"]) or {}).get("total_credits") or 0), 6.0,
        )


if __name__ == "__main__":
    unittest.main()
