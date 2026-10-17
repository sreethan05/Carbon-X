"""Cryptographic ledger and hash chain tamper-detection verification suite.

Tests:
1. Byte alteration detection across all record fields (seq, entity_id, type, payload, prev_hash, ts, hash)
2. Single-character modifications in payloads (strings, numbers, booleans, nested structures)
3. Event sequence reordering / swapping attacks
4. Chain truncation attacks (tail truncation, head truncation, middle excision)
5. Canonical JSON nested dictionary key sorting consistency & deterministic hashing
"""
import copy
import hashlib
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone, timedelta

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services import ledger as ledger_module


class LedgerCryptoTamperTests(unittest.TestCase):
    """Hermetic cryptographic ledger tamper and integrity tests."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="carbonx_ledger_crypto_")
        self.ledger_file = os.path.join(self.temp_dir, "test_ledger.json")
        os.environ["CARBONX_LEDGER_PATH"] = self.ledger_file
        ledger_module._PATH = self.ledger_file
        ledger_module._CHAINS = {}
        self._orig_sb = ledger_module._sb
        ledger_module._sb = lambda: None  # hermetic: no remote DB in tests

    def tearDown(self):
        ledger_module._sb = self._orig_sb
        if os.path.exists(self.ledger_file):
            try:
                os.remove(self.ledger_file)
            except OSError:
                pass
        if os.path.exists(self.temp_dir):
            try:
                os.rmdir(self.temp_dir)
            except OSError:
                pass

    def _create_standard_chain(self, farm_id="farm-crypto-01"):
        """Create a standard 4-event credit lifecycle chain: ISSUE -> SALE -> SPLIT -> RETIRE."""
        e0 = ledger_module.append_event(
            farm_id,
            "ISSUE",
            {
                "credits": 100,
                "crop": "Paddy / Rice",
                "evidence": {"satellite": "Sentinel-2", "ndvi": 0.76, "confidence": 0.94},
            },
            ts="2026-10-01T10:00:00+00:00",
        )
        e1 = ledger_module.append_event(
            farm_id,
            "SALE",
            {
                "credits": 100,
                "buyer": "Tata Sustainability Ltd",
                "unit_price_inr": 500.0,
                "gross_inr": 50000.0,
                "escrow_ref": "ESC-TEST-1001",
            },
            ts="2026-10-02T11:00:00+00:00",
        )
        e2 = ledger_module.append_event(
            farm_id,
            "SPLIT",
            {
                "model": "4-way",
                "farmer_inr": 35000.0,
                "fpo_inr": 2500.0,
                "platform_inr": 12500.0,
                "escrow_ref": "ESC-TEST-1001",
            },
            ts="2026-10-02T11:05:00+00:00",
        )
        e3 = ledger_module.append_event(
            farm_id,
            "RETIRE",
            {
                "certificate_id": "CX-2026-CERT-BEEF01",
                "credits_retired": 100,
                "buyer": "Tata Sustainability Ltd",
                "escrow_ref": "ESC-TEST-1001",
            },
            ts="2026-10-02T11:10:00+00:00",
        )
        return farm_id, [e0, e1, e2, e3]

    # =========================================================================
    # 1. Modifying a Single Character in Payload
    # =========================================================================

    def test_single_character_payload_modification_string(self):
        """Altering a single ASCII character in a string payload field breaks the chain."""
        farm_id, events = self._create_standard_chain("farm-tamper-char")
        check_before = ledger_module.verify_chain(farm_id)
        self.assertTrue(check_before["valid"])

        # Mutate "Tata Sustainability Ltd" -> "Tata Sustainability Xtd" (1 char difference)
        ledger_module._CHAINS[farm_id][1]["payload"]["buyer"] = "Tata Sustainability Xtd"
        check_after = ledger_module.verify_chain(farm_id)
        self.assertFalse(check_after["valid"])
        self.assertEqual(check_after["broken_at"], 1)

    def test_single_digit_payload_modification_amount(self):
        """Altering a single numeric digit in a payload field breaks the chain."""
        farm_id, events = self._create_standard_chain("farm-tamper-digit")

        # Mutate farmer_inr: 35000.0 -> 35001.0 (single digit)
        ledger_module._CHAINS[farm_id][2]["payload"]["farmer_inr"] = 35001.0
        check = ledger_module.verify_chain(farm_id)
        self.assertFalse(check["valid"])
        self.assertEqual(check["broken_at"], 2)

    def test_nested_payload_single_character_modification(self):
        """Altering a deep nested dictionary field in payload breaks the chain."""
        farm_id, events = self._create_standard_chain("farm-tamper-nested")

        # Mutate satellite name in nested evidence: "Sentinel-2" -> "Sentinel-3"
        ledger_module._CHAINS[farm_id][0]["payload"]["evidence"]["satellite"] = "Sentinel-3"
        check = ledger_module.verify_chain(farm_id)
        self.assertFalse(check["valid"])
        self.assertEqual(check["broken_at"], 0)

    def test_payload_modification_after_get_chain(self):
        """Mutating payload on a chain returned by get_chain is caught even when _payload_json exists."""
        farm_id, _ = self._create_standard_chain("farm-tamper-post-read")
        chain = ledger_module.get_chain(farm_id)
        self.assertIn("_payload_json", chain[0])

        # Mutate payload in memory
        chain[0]["payload"]["credits"] = 999
        check = ledger_module._verify_chain_events(chain)
        self.assertFalse(check["valid"])
        self.assertEqual(check["broken_at"], 0)

    def test_payload_key_addition_and_deletion(self):
        """Adding or removing any key in the payload dict is caught."""
        farm_id, _ = self._create_standard_chain("farm-tamper-keys")

        # Adding an innocuous-looking key
        ledger_module._CHAINS[farm_id][3]["payload"]["fraudulent_extra_key"] = True
        check_add = ledger_module.verify_chain(farm_id)
        self.assertFalse(check_add["valid"])
        self.assertEqual(check_add["broken_at"], 3)

        # Revert and delete an existing key
        del ledger_module._CHAINS[farm_id][3]["payload"]["fraudulent_extra_key"]
        del ledger_module._CHAINS[farm_id][3]["payload"]["escrow_ref"]
        check_del = ledger_module.verify_chain(farm_id)
        self.assertFalse(check_del["valid"])
        self.assertEqual(check_del["broken_at"], 3)

    # =========================================================================
    # 2. Swapping Two Events in Sequence
    # =========================================================================

    def test_swap_adjacent_events_in_middle(self):
        """Swapping events 1 (SALE) and 2 (SPLIT) breaks continuity immediately."""
        farm_id, events = self._create_standard_chain("farm-swap-1-2")
        check_before = ledger_module.verify_chain(farm_id)
        self.assertTrue(check_before["valid"])

        # Swap event 1 and 2
        chain = ledger_module._CHAINS[farm_id]
        chain[1], chain[2] = chain[2], chain[1]

        check_after = ledger_module.verify_chain(farm_id)
        self.assertFalse(check_after["valid"])
        # Event at index 1 now has seq=2, violating seq == idx constraint, and prev_hash points to event 1
        self.assertEqual(check_after["broken_at"], 2)

    def test_swap_genesis_and_first_event(self):
        """Swapping event 0 (ISSUE) and event 1 (SALE) breaks genesis constraint."""
        farm_id, events = self._create_standard_chain("farm-swap-0-1")
        chain = ledger_module._CHAINS[farm_id]
        chain[0], chain[1] = chain[1], chain[0]

        check = ledger_module.verify_chain(farm_id)
        self.assertFalse(check["valid"])
        # Event at index 0 now has seq=1 (not 0) and prev_hash != '0'*64
        self.assertEqual(check["broken_at"], 1)

    def test_swap_events_with_forged_seq_numbers(self):
        """Even if an attacker swaps events and modifies seq numbers to match indices, hash fails."""
        farm_id, events = self._create_standard_chain("farm-swap-forged-seq")
        chain = ledger_module._CHAINS[farm_id]

        # Swap events 1 and 2, but tamper seq to match new array indices
        ev1 = copy.deepcopy(chain[1])
        ev2 = copy.deepcopy(chain[2])
        ev2["seq"] = 1
        ev1["seq"] = 2
        chain[1] = ev2
        chain[2] = ev1

        check = ledger_module.verify_chain(farm_id)
        self.assertFalse(check["valid"])
        # Hashes no longer match because material = seq | ... | prev_hash
        self.assertEqual(check["broken_at"], 1)

    # =========================================================================
    # 3. Truncating the Chain
    # =========================================================================

    def test_truncate_chain_tail_drops_retirement(self):
        """Truncating the last event (e.g. attempting to cancel retirement) produces tail hash mismatch."""
        farm_id, events = self._create_standard_chain("farm-trunc-tail")
        honest_verification = ledger_module.verify_chain(farm_id)
        honest_tail = honest_verification["tail_hash"]
        self.assertEqual(honest_verification["length"], 4)

        # Attacker truncates the last event (RETIRE)
        ledger_module._CHAINS[farm_id].pop()

        truncated_verification = ledger_module.verify_chain(farm_id)
        # The truncated prefix internally verifies, but length is 3 and tail_hash diverges
        self.assertEqual(truncated_verification["length"], 3)
        self.assertNotEqual(truncated_verification["tail_hash"], honest_tail)
        self.assertEqual(truncated_verification["tail_hash"], events[2]["hash"])

    def test_truncate_chain_head_removes_genesis(self):
        """Truncating event 0 (genesis ISSUE) invalidates the remaining chain immediately."""
        farm_id, _ = self._create_standard_chain("farm-trunc-head")
        # Remove genesis event 0
        ledger_module._CHAINS[farm_id].pop(0)

        check = ledger_module.verify_chain(farm_id)
        self.assertFalse(check["valid"])
        # The new first event has seq=1 and prev_hash pointing to the deleted genesis event
        self.assertEqual(check["broken_at"], 1)

    def test_truncate_chain_middle_event_excision(self):
        """Excising an event from the middle (e.g. removing SPLIT) breaks the hash chain."""
        farm_id, _ = self._create_standard_chain("farm-trunc-middle")
        # Remove event 2 (SPLIT), leaving [0 (ISSUE), 1 (SALE), 3 (RETIRE)]
        del ledger_module._CHAINS[farm_id][2]

        check = ledger_module.verify_chain(farm_id)
        self.assertFalse(check["valid"])
        # Event 3 is at index 2, with seq=3 != idx=2 and prev_hash != chain[1].hash
        self.assertEqual(check["broken_at"], 3)

    # =========================================================================
    # 4. Canonical JSON Nested Dictionary Sorting Consistency
    # =========================================================================

    def test_canonical_json_nested_dictionary_sorting_consistency(self):
        """Canonical JSON serialization is deterministic regardless of Python dict insertion order."""
        # Define dicts with identical content but completely opposite / shuffled insertion order
        dict_a = {
            "z_meta": {"tag": "audit", "alpha": 100},
            "beta": "test",
            "alpha": 42,
            "details": {
                "geo": {"lat": 17.385, "lon": 78.486, "mandal": "Shamshabad"},
                "crops": ["Rice", "Cotton"],
            },
        }

        dict_b = {
            "alpha": 42,
            "details": {
                "details_inner": None,
                "crops": ["Rice", "Cotton"],
                "geo": {"mandal": "Shamshabad", "lon": 78.486, "lat": 17.385},
            },
            "beta": "test",
            "z_meta": {"alpha": 100, "tag": "audit"},
        }
        # Normalize details_inner removal for strict semantic equivalence
        del dict_b["details"]["details_inner"]

        canon_a = ledger_module._canonical(dict_a)
        canon_b = ledger_module._canonical(dict_b)

        # Serialized strings must be identical byte-for-byte
        self.assertEqual(canon_a, canon_b)

        # SHA-256 hashes must be strictly identical
        hash_a = hashlib.sha256(canon_a.encode("utf-8")).hexdigest()
        hash_b = hashlib.sha256(canon_b.encode("utf-8")).hexdigest()
        self.assertEqual(hash_a, hash_b)

    def test_canonical_json_formatting_and_separators(self):
        """Canonical JSON eliminates whitespace around separators (':', ',')."""
        sample = {"b": 2, "a": 1, "nested": {"d": 4, "c": 3}}
        canon = ledger_module._canonical(sample)
        # Strict formatting: no space after ':' or ','
        self.assertNotIn(": ", canon)
        self.assertNotIn(", ", canon)
        self.assertEqual(canon, '{"a":1,"b":2,"nested":{"c":3,"d":4}}')

    def test_canonical_json_unicode_and_special_symbols(self):
        """Canonical serialization handles unicode (e.g. ₹ rupee symbol, regional scripts) reliably."""
        sample_unicode = {
            "currency": "INR",
            "symbol": "₹",
            "village": "నర్సింగి",
            "amount": 12500.50,
        }
        canon1 = ledger_module._canonical(sample_unicode)
        canon2 = ledger_module._canonical(copy.deepcopy(sample_unicode))
        self.assertEqual(canon1, canon2)
        self.assertEqual(
            hashlib.sha256(canon1.encode("utf-8")).hexdigest(),
            hashlib.sha256(canon2.encode("utf-8")).hexdigest(),
        )

    # =========================================================================
    # 5. Field-by-Field Byte Alteration Tamper Detection
    # =========================================================================

    def test_tamper_seq_number(self):
        """Altering the seq field alone is detected immediately."""
        farm_id, _ = self._create_standard_chain("farm-tamper-seq")
        ledger_module._CHAINS[farm_id][2]["seq"] = 42

        check = ledger_module.verify_chain(farm_id)
        self.assertFalse(check["valid"])
        self.assertEqual(check["broken_at"], 42)

    def test_tamper_entity_id(self):
        """Altering the entity_id field is detected immediately."""
        farm_id, _ = self._create_standard_chain("farm-tamper-entity")
        ledger_module._CHAINS[farm_id][1]["entity_id"] = "different-farm-99"

        check = ledger_module.verify_chain(farm_id)
        self.assertFalse(check["valid"])
        self.assertEqual(check["broken_at"], 1)

    def test_tamper_event_type(self):
        """Altering event type (e.g. SALE -> ISSUE) is detected immediately."""
        farm_id, _ = self._create_standard_chain("farm-tamper-type")
        ledger_module._CHAINS[farm_id][1]["type"] = "ISSUE"

        check = ledger_module.verify_chain(farm_id)
        self.assertFalse(check["valid"])
        self.assertEqual(check["broken_at"], 1)

    def test_tamper_prev_hash(self):
        """Altering any character of prev_hash breaks the chain."""
        farm_id, _ = self._create_standard_chain("farm-tamper-prevhash")
        orig_prev = ledger_module._CHAINS[farm_id][2]["prev_hash"]
        # Flip the first hex char
        flipped_char = "a" if orig_prev[0] != "a" else "b"
        ledger_module._CHAINS[farm_id][2]["prev_hash"] = flipped_char + orig_prev[1:]

        check = ledger_module.verify_chain(farm_id)
        self.assertFalse(check["valid"])
        self.assertEqual(check["broken_at"], 2)

    def test_tamper_hash_signature(self):
        """Altering the recorded event hash itself is detected immediately."""
        farm_id, _ = self._create_standard_chain("farm-tamper-hash")
        orig_hash = ledger_module._CHAINS[farm_id][1]["hash"]
        flipped_char = "0" if orig_hash[0] != "0" else "1"
        ledger_module._CHAINS[farm_id][1]["hash"] = flipped_char + orig_hash[1:]

        check = ledger_module.verify_chain(farm_id)
        self.assertFalse(check["valid"])
        self.assertEqual(check["broken_at"], 1)

    def test_tamper_timestamp_non_monotonic_backdating(self):
        """Backdating an event timestamp violates monotonicity and is detected."""
        farm_id, _ = self._create_standard_chain("farm-tamper-backdate")
        # Event 2 was at 2026-10-02T11:05:00. Backdate it to 2026-09-01T00:00:00.
        ledger_module._CHAINS[farm_id][2]["ts"] = "2026-09-01T00:00:00+00:00"

        check = ledger_module.verify_chain(farm_id)
        self.assertFalse(check["valid"])
        self.assertEqual(check["broken_at"], 2)

    def test_tamper_timestamp_corrupted_format(self):
        """Corrupting a timestamp into a malformed string is detected."""
        farm_id, _ = self._create_standard_chain("farm-tamper-bad-ts")
        ledger_module._CHAINS[farm_id][1]["ts"] = "INVALID_TIMESTAMP_STRING"

        check = ledger_module.verify_chain(farm_id)
        self.assertFalse(check["valid"])
        self.assertEqual(check["broken_at"], 1)

    def test_tamper_timestamp_empty(self):
        """Setting timestamp to an empty string is detected."""
        farm_id, _ = self._create_standard_chain("farm-tamper-empty-ts")
        ledger_module._CHAINS[farm_id][0]["ts"] = ""

        check = ledger_module.verify_chain(farm_id)
        self.assertFalse(check["valid"])
        self.assertEqual(check["broken_at"], 0)


if __name__ == "__main__":
    unittest.main()
