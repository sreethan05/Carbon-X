import unittest

from app.services.credit_lifecycle import derive_certificates


class CertificateDeduplicationTests(unittest.TestCase):
    def test_replayed_sale_event_exposes_one_canonical_certificate(self):
        listing = {
            "id": "listing-1",
            "farm_id": "farm-1",
            "status": "Retired",
            "total_credits": 2,
        }
        sale_payload = {
            "listing_id": "listing-1",
            "certificate_id": "CX-2026-CERT-ABC12345",
            "credits": 2,
        }
        chain = [
            {"type": "SALE", "ts": "2026-01-01T00:00:00Z", "hash": "h1", "payload": {**sale_payload, "escrow_ref": "escrow-1"}},
            {"type": "SALE", "ts": "2026-01-02T00:00:00Z", "hash": "h2", "payload": {**sale_payload, "escrow_ref": "escrow-2"}},
        ]

        certificates = derive_certificates([listing], lambda _farm_id: chain)

        self.assertEqual(1, len(certificates))
        self.assertEqual("CX-2026-CERT-ABC12345", certificates[0]["id"])
        self.assertEqual(1, certificates[0]["duplicate_event_count"])


if __name__ == "__main__":
    unittest.main()
