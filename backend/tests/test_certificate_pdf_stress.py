"""Stress and edge-case tests for Verra-style PDF certificate generation.

Covers:
- Extremely long buyer names, farmer names, locations, and hashes
- Non-ASCII/Unicode strings (Telugu, Hindi, Chinese, Arabic, emojis, accents)
- Rapid concurrent requests hitting and invalidating LRU cache
- Corrupted, missing, and invalid QR code data
- Defensive type handling and algorithmic complexity (O(log N) string fitting)
"""
import io
import os
import sys
import threading
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4, landscape

from app.services import certificate_pdf
from app.services.certificate_pdf import (
    render_certificate_pdf,
    get_cached_certificate_pdf,
    invalidate_certificate_pdf,
    clear_certificate_pdf_cache,
    certificate_cache_stats,
    CertificatePdfCache,
    _fit_string,
    _wrapped,
)


class CertificatePdfStressTests(unittest.TestCase):
    def setUp(self):
        clear_certificate_pdf_cache()

    def tearDown(self):
        clear_certificate_pdf_cache()

    # =========================================================================
    # 1. Extremely Long Strings & Algorithmic DoS Resistance
    # =========================================================================

    def test_fit_string_extreme_length_performance(self):
        """Ensure _fit_string operates in O(log N) and never hangs on 100k+ chars."""
        c = canvas.Canvas(io.BytesIO(), pagesize=landscape(A4))
        huge_str = "A" * 100000

        t0 = time.perf_counter()
        fitted = _fit_string(c, huge_str, "Helvetica-Bold", 24, 400)
        t1 = time.perf_counter()

        self.assertLess(t1 - t0, 0.05, "_fit_string took longer than 50ms on 100k chars")
        self.assertTrue(fitted.endswith("..."))
        self.assertLessEqual(c.stringWidth(fitted, "Helvetica-Bold", 24), 400)

    def test_fit_string_edge_cases(self):
        """Test boundary conditions for _fit_string."""
        c = canvas.Canvas(io.BytesIO(), pagesize=landscape(A4))

        # None or empty
        self.assertEqual(_fit_string(c, None, "Helvetica", 12, 200), "")
        self.assertEqual(_fit_string(c, "", "Helvetica", 12, 200), "")

        # Zero or negative max width
        self.assertEqual(_fit_string(c, "Hello", "Helvetica", 12, 0), "")
        self.assertEqual(_fit_string(c, "Hello", "Helvetica", 12, -50), "")

        # String fits without truncation
        self.assertEqual(_fit_string(c, "Short text", "Helvetica", 12, 500), "Short text")

        # Newlines/tabs sanitized into single spaces
        multiline = "Line 1\nLine 2\r\nLine 3\tEnd"
        fitted_multi = _fit_string(c, multiline, "Helvetica", 12, 500)
        self.assertNotIn("\n", fitted_multi)
        self.assertNotIn("\r", fitted_multi)
        self.assertNotIn("\t", fitted_multi)
        self.assertEqual(fitted_multi, "Line 1 Line 2 Line 3 End")

    def test_extremely_long_individual_fields(self):
        """Test certificate rendering where individual fields exceed 50k characters."""
        fields_to_test = [
            ("buyer", "Buyer " + "X" * 50000),
            ("farmer_name", "Farmer " + "Y" * 50000),
            ("location", "Location " + "Z" * 50000),
            ("crop", "Crop " + "C" * 20000),
            ("id", "CX-" + "I" * 5000),
            ("batch_hash", "H" * 10000),
        ]

        for field_name, long_val in fields_to_test:
            with self.subTest(field=field_name):
                cert = {
                    "id": "CX-STRESS-LONG",
                    "buyer": "Default Buyer",
                    "farmer_name": "Default Farmer",
                    "crop": "Cotton",
                    "volume": 25.5,
                    "location": "Warangal, Telangana",
                    "issued_date": "2026-10-15",
                    "status": "RETIRED",
                    "batch_hash": "a" * 64,
                }
                cert[field_name] = long_val

                t0 = time.perf_counter()
                pdf = render_certificate_pdf(cert, use_cache=False)
                elapsed = time.perf_counter() - t0

                self.assertLess(elapsed, 1.0, f"Rendering with huge {field_name} took {elapsed:.2f}s")
                self.assertIsInstance(pdf, bytes)
                self.assertTrue(pdf.startswith(b"%PDF"))
                self.assertIn(b"%%EOF", pdf)

    def test_all_fields_simultaneously_huge(self):
        """Cert where every single field is massive simultaneously."""
        cert = {
            "id": "CX-" + "9" * 3000,
            "buyer": "Mega Corp " + "B" * 30000,
            "farmer_name": "Ramesh & " + "F" * 30000,
            "crop": "Paddy " + "C" * 10000,
            "volume": 123456789.99,
            "value": 9876543210.0,
            "location": "District " + "L" * 30000,
            "issued_date": "2026-10-15 " + "D" * 500,
            "retired_date": "2026-10-17 " + "R" * 500,
            "status": "RETIRED",
            "batch_hash": "e" * 8000,
        }

        t0 = time.perf_counter()
        pdf = render_certificate_pdf(cert, use_cache=False)
        elapsed = time.perf_counter() - t0

        self.assertLess(elapsed, 1.5, f"All-huge certificate took {elapsed:.2f}s")
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertIn(b"%%EOF", pdf)
        self.assertGreater(len(pdf), 3000)

    # =========================================================================
    # 2. Non-ASCII and Unicode Strings
    # =========================================================================

    def test_non_ascii_and_multilingual_scripts(self):
        """Test rendering Telugu, Hindi, Chinese, Arabic, European accents, and emoji."""
        multilingual_cases = [
            {
                "name": "telugu_regional",
                "buyer": "వరంగల్ ఆగ్రో కార్పొరేషన్ (Warangal Agro Corp)",
                "farmer": "రాములు మరియు లక్ష్మి (Ramulu & Lakshmi)",
                "location": "వరంగల్ రూరల్, తెలంగాణ (Warangal Rural, Telangana)",
                "crop": "వరి (Paddy)",
            },
            {
                "name": "hindi_devanagari",
                "buyer": "भारत सस्टेनेबल एंटरप्राइजेज",
                "farmer": "राम शरण किसान",
                "location": "इंदौर, मध्य प्रदेश",
                "crop": "कपास (Cotton)",
            },
            {
                "name": "chinese_cjk",
                "buyer": "北京绿色碳资产管理有限公司",
                "farmer": "李伟 / 农业合作社",
                "location": "山东省寿光市",
                "crop": "有机小麦 (Organic Wheat)",
            },
            {
                "name": "arabic_rtl",
                "buyer": "شركة الطاقة المتجددة العالمية",
                "farmer": "أحمد بن عبد الله",
                "location": "الرياض، المملكة العربية السعودية",
                "crop": "نخيل (Date Palm)",
            },
            {
                "name": "european_accents_and_symbols",
                "buyer": "Société Générale d'Écologie & Müller-Strauß GmbH €100k",
                "farmer": "François & Zoë Noël — São Paulo Farmers",
                "location": "Zürich / Genève / Malmö / Kraków",
                "crop": "Blé d'hiver & Maïs © ® ™",
            },
            {
                "name": "modern_emojis",
                "buyer": "Green Planet Corp 🌍🌿✨",
                "farmer": "Farmer Ramesh 🌾🚜🧑‍🌾",
                "location": "Telangana Green Zone 🌳🌱",
                "crop": "Paddy Rice 🌾☀️",
            },
            {
                "name": "whitespace_and_control_chars",
                "buyer": "Buyer\nWith\r\nEmbedded\tTabs\x00AndNull",
                "farmer": "Farmer\t\tName\nSecondLine",
                "location": "Plot 123\r\nVillage ABC\x00Sector 4",
                "crop": "Paddy\r\nRice",
            },
            {
                "name": "special_dashes_quotes_and_math",
                "buyer": "“High-Grade” ‘Bio-Carbon’ — Batch #1 – Tier 1 • VIP",
                "farmer": "Alpha & Omega ∑ ∫ √ ≈ ≠ ≤ ≥",
                "location": "17°23'45.6\"N 78°28'12.3\"E",
                "crop": "Regenerative Pulses ± 5%",
            },
        ]

        for case in multilingual_cases:
            with self.subTest(case=case["name"]):
                cert = {
                    "id": f"CX-UNI-{case['name']}",
                    "buyer": case["buyer"],
                    "farmer_name": case["farmer"],
                    "crop": case["crop"],
                    "volume": 50.0,
                    "value": 75000.0,
                    "location": case["location"],
                    "issued_date": "2026-10-15",
                    "status": "RETIRED",
                    "batch_hash": "4a7d1ed414474e4033ac29ccb8653d9b",
                }

                pdf = render_certificate_pdf(cert, use_cache=False)
                self.assertIsInstance(pdf, bytes)
                self.assertTrue(pdf.startswith(b"%PDF"))
                self.assertIn(b"%%EOF", pdf)

    # =========================================================================
    # 3. Corrupted and Invalid QR Code Data
    # =========================================================================

    def test_corrupted_and_invalid_qr_data(self):
        """Certificates with broken, overflowed, or non-string QR inputs must not crash."""
        corrupt_cases = [
            ("none_values", {"id": None, "batch_hash": None}),
            ("empty_values", {"id": "", "batch_hash": ""}),
            ("null_bytes", {"id": "CX\x00BAD\x00ID", "batch_hash": "HASH\x00BYTE"}),
            ("overflow_hash", {"id": "CX-VALID", "batch_hash": "F" * 15000}),
            ("overflow_id", {"id": "CX-" + "9" * 10000, "batch_hash": "abc"}),
            ("malformed_characters", {"id": "CX/?#@!$%^&*()+=[]{}|\\", "batch_hash": "not-a-hex-hash"}),
            ("numeric_types", {"id": 12345678, "batch_hash": 987654321}),
            ("unicode_in_id_and_hash", {"id": "CX-రమేష్-🌾", "batch_hash": "హాష్-🔥"}),
        ]

        for name, params in corrupt_cases:
            with self.subTest(case=name):
                cert = {
                    "id": params["id"],
                    "buyer": "Resilience Buyer",
                    "farmer_name": "Resilience Farmer",
                    "crop": "Paddy",
                    "volume": 10.0,
                    "location": "Warangal",
                    "status": "RETIRED",
                    "batch_hash": params["batch_hash"],
                }

                pdf = render_certificate_pdf(cert, use_cache=False)
                self.assertIsInstance(pdf, bytes)
                self.assertTrue(pdf.startswith(b"%PDF"))
                self.assertIn(b"%%EOF", pdf)

    def test_completely_empty_or_minimal_dict(self):
        """Passing an empty dict or all-None cert dict must render gracefully."""
        for cert in ({}, {"id": None, "buyer": None, "volume": None, "status": None}):
            pdf = render_certificate_pdf(cert, use_cache=False)
            self.assertTrue(pdf.startswith(b"%PDF"))
            self.assertIn(b"%%EOF", pdf)

    # =========================================================================
    # 4. Rapid Concurrent Requests & LRU Cache Stress
    # =========================================================================

    def test_concurrent_cache_hammering(self):
        """16 concurrent threads generating, reading, and invalidating certificates."""
        errors = []
        thread_count = 16
        iterations_per_thread = 50

        # Shared pool of 6 certificates so threads rapidly hit cache while concurrently invalidating
        def worker(thread_idx):
            try:
                for i in range(iterations_per_thread):
                    pool_idx = (thread_idx + i) % 6
                    cert_id = f"CX-CONC-POOL-{pool_idx}"
                    cert = {
                        "id": cert_id,
                        "buyer": f"Buyer Pool {pool_idx}",
                        "farmer_name": f"Farmer Pool {pool_idx}",
                        "crop": "Cotton",
                        "volume": 15.0,
                        "value": 22500.0,
                        "location": "Khammam, Telangana",
                        "issued_date": "2026-10-15",
                        "status": "RETIRED",
                        "batch_hash": f"hash_pool_{pool_idx}",
                    }

                    # Render with cache (concurrent cache hits)
                    pdf = render_certificate_pdf(cert, use_cache=True)
                    if not pdf.startswith(b"%PDF") or b"%%EOF" not in pdf:
                        errors.append(f"Thread {thread_idx} got invalid PDF on iteration {i}")

                    # Check direct cache retrieval
                    cached = get_cached_certificate_pdf(cert_id)
                    if cached is not None and not cached.startswith(b"%PDF"):
                        errors.append(f"Thread {thread_idx} got corrupted cache for {cert_id}")

                    # Concurrent invalidation of a designated dynamic key
                    if i % 15 == 0 and thread_idx == 0:
                        invalidate_certificate_pdf("CX-CONC-POOL-0")

                    # Concurrent stats inspection
                    if i % 10 == 0:
                        stats = certificate_cache_stats()
                        if "size" not in stats or "maxsize" not in stats:
                            errors.append(f"Thread {thread_idx} got invalid stats")
            except Exception as e:
                errors.append(f"Thread {thread_idx} crashed: {type(e).__name__}: {e}")

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(thread_count)]
        t0 = time.perf_counter()
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        total_time = time.perf_counter() - t0

        self.assertEqual(len(errors), 0, f"Encountered concurrency errors: {errors[:5]}")
        self.assertLess(total_time, 5.0, f"Concurrent cache hammering took too long: {total_time:.2f}s")

    def test_cache_state_transition_integrity(self):
        """Transitioning from HELD_IN_ESCROW to RETIRED must NOT return stale ESCROW PDF."""
        cert_escrow = {
            "id": "CX-TRANSITION-001",
            "buyer": "Green Holdings",
            "farmer_name": "Sita Devi",
            "crop": "Paddy",
            "volume": 10.0,
            "location": "Warangal",
            "status": "HELD_IN_ESCROW",
            "batch_hash": "hash_v1_escrow",
        }
        pdf_escrow = render_certificate_pdf(cert_escrow, use_cache=True)
        self.assertTrue(pdf_escrow.startswith(b"%PDF"))

        # Transition to RETIRED
        cert_retired = {
            "id": "CX-TRANSITION-001",
            "buyer": "Green Holdings",
            "farmer_name": "Sita Devi",
            "crop": "Paddy",
            "volume": 10.0,
            "location": "Warangal",
            "status": "RETIRED",
            "batch_hash": "hash_v2_retired",
        }
        pdf_retired = render_certificate_pdf(cert_retired, use_cache=True)
        self.assertTrue(pdf_retired.startswith(b"%PDF"))

        # PDFs must differ because status and watermark changed
        self.assertNotEqual(
            pdf_escrow, pdf_retired,
            "render_certificate_pdf returned stale HELD_IN_ESCROW PDF after status changed to RETIRED"
        )

        # Cache get by cert_id should return the latest (RETIRED) PDF
        cached_latest = get_cached_certificate_pdf("CX-TRANSITION-001")
        self.assertEqual(cached_latest, pdf_retired)

    def test_lru_cache_eviction_under_concurrency(self):
        """Test small-capacity LRU cache eviction under multithreaded insertion."""
        small_cache = CertificatePdfCache(maxsize=10)
        errors = []

        def filler(worker_id):
            try:
                for i in range(50):
                    key = f"key-{worker_id}-{i}"
                    small_cache.set(key, f"val-{worker_id}-{i}".encode())
                    _ = small_cache.get(key)
            except Exception as e:
                errors.append(f"Worker {worker_id} error: {e}")

        threads = [threading.Thread(target=filler, args=(w,)) for w in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0)
        self.assertLessEqual(len(small_cache), 10, "Cache size exceeded maxsize")
        self.assertEqual(small_cache.stats()["size"], len(small_cache))


if __name__ == "__main__":
    unittest.main()
