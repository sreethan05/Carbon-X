"""Tests for telemetry, logging, and privacy safeguards:
- Zero PII leaks: phone numbers, passwords, and Aadhaar numbers masked in JSON log records
- Request-ID propagation across log records and HTTP request lifecycle
- Prometheus /metrics endpoint (request count counter, latency histograms)
"""
import io
import json
import logging
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient

from app.logging_setup import JsonFormatter, mask_pii, request_id_var
from app.main import app

client = TestClient(app)


class LoggingPrivacyTests(unittest.TestCase):
    def setUp(self):
        self.formatter = JsonFormatter()
        request_id_var.set("")

    def tearDown(self):
        request_id_var.set("")

    def _format_message(self, msg, args=(), exc_info=None, extra=None):
        record = logging.LogRecord(
            name="carbonx.privacy_test",
            level=logging.INFO,
            pathname=__file__,
            lineno=30,
            msg=msg,
            args=args,
            exc_info=exc_info,
        )
        if extra:
            for k, v in extra.items():
                setattr(record, k, v)
        output = self.formatter.format(record)
        return json.loads(output)

    def test_phone_number_masked_plain_10_digits(self):
        raw_phone = "9876543210"
        data = self._format_message(f"User OTP sent to {raw_phone} successfully")
        self.assertNotIn(raw_phone, data["msg"])
        self.assertIn("******3210", data["msg"])

    def test_phone_number_masked_with_country_code(self):
        cases = [
            ("+919876543210", "+91******3210"),
            ("+91 9876543210", "+91 ******3210"),
            ("+91-9876543210", "+91-******3210"),
            ("09876543210", "0******3210"),
        ]
        for raw, expected_masked in cases:
            data = self._format_message(f"Contact farmer at {raw}")
            self.assertNotIn(raw, data["msg"])
            self.assertIn(expected_masked, data["msg"])

    def test_labeled_phone_numbers_in_json_and_params(self):
        msg = '{"phone": "9876543210", "farmer_phone": "+919123456789", "owner_phone": "9000000001"}'
        data = self._format_message(msg)
        self.assertNotIn("9876543210", data["msg"])
        self.assertNotIn("9123456789", data["msg"])
        self.assertNotIn("9000000001", data["msg"])
        self.assertIn("******3210", data["msg"])
        self.assertIn("******6789", data["msg"])
        self.assertIn("******0001", data["msg"])

    def test_passwords_masked_in_all_variations(self):
        raw_passwords = [
            ("password: secretPassword123", "password: ********"),
            ('{"password": "secretPassword123"}', '{"password": "********"}'),
            ("password=SuperSecret!", "password=********"),
            ("with password MyPassword999", "with password ********"),
            ("passwd: TopSecretPass", "passwd: ********"),
            ("pwd=MyShortPass", "pwd=********"),
            ('secret: "classified_api_token"', 'secret: "********"'),
            ("access_token: eyJhbGciOiJIUzI1NiJ9", "access_token: ********"),
            ("api_key=AIzaSyA123456789", "api_key=********"),
        ]
        for raw_text, expected_substring in raw_passwords:
            data = self._format_message(f"Login debug info: {raw_text}")
            self.assertNotIn("secretPassword123", data["msg"])
            self.assertNotIn("SuperSecret!", data["msg"])
            self.assertNotIn("MyPassword999", data["msg"])
            self.assertNotIn("TopSecretPass", data["msg"])
            self.assertNotIn("classified_api_token", data["msg"])
            self.assertNotIn("eyJhbGciOiJIUzI1NiJ9", data["msg"])
            self.assertNotIn("AIzaSyA123456789", data["msg"])
            self.assertIn(expected_substring, data["msg"])

    def test_aadhaar_numbers_masked_various_formats(self):
        cases = [
            ("1234 5678 9012", "XXXX-XXXX-9012"),
            ("1234-5678-9012", "XXXX-XXXX-9012"),
            ("123456789012", "XXXX-XXXX-9012"),
            ("9876 5432 1098", "XXXX-XXXX-1098"),
        ]
        for raw_aadhaar, expected_masked in cases:
            data = self._format_message(f"Verified Aadhaar: {raw_aadhaar}")
            self.assertNotIn(raw_aadhaar, data["msg"])
            self.assertNotIn("1234 5678", data["msg"])
            self.assertNotIn("1234-5678", data["msg"])
            self.assertNotIn("9876 5432", data["msg"])
            self.assertIn(expected_masked, data["msg"])

    def test_exception_traceback_masks_pii(self):
        try:
            raw_phone = "9876543210"
            raw_pass = "MySecretExceptionPassword"
            raw_aadhaar = "1234-5678-9012"
            raise ValueError(f"Auth failure for phone={raw_phone}, password={raw_pass}, aadhaar={raw_aadhaar}")
        except ValueError:
            exc_info = sys.exc_info()

        data = self._format_message("Exception occurred during KYC processing", exc_info=exc_info)
        self.assertIn("exc", data)
        self.assertNotIn("9876543210", data["exc"])
        self.assertNotIn("MySecretExceptionPassword", data["exc"])
        self.assertNotIn("1234-5678-9012", data["exc"])
        self.assertIn("******3210", data["exc"])
        self.assertIn("********", data["exc"])
        self.assertIn("XXXX-XXXX-9012", data["exc"])

    def test_extra_attributes_mask_pii(self):
        extra = {
            "farmer_phone": "9876543210",
            "farmer_aadhaar": "1234 5678 9012",
            "temp_password": "superSecretPassword123",
            "farm_id": "f-12345",
        }
        data = self._format_message("Farmer record processed", extra=extra)
        self.assertNotIn("9876543210", data["farmer_phone"])
        self.assertNotIn("1234 5678 9012", data["farmer_aadhaar"])
        self.assertNotIn("superSecretPassword123", data["temp_password"])
        self.assertIn("******3210", data["farmer_phone"])
        self.assertIn("XXXX-XXXX-9012", data["farmer_aadhaar"])
        self.assertIn("********", data["temp_password"])
        self.assertEqual(data["farm_id"], "f-12345")

    def test_non_pii_entities_preserved(self):
        safe_msg = (
            "UUID e1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d; "
            "timestamp 1729179000; port 8000; area 2.45 ha; "
            "credits 15.2; year 2026; last4 9012"
        )
        data = self._format_message(safe_msg)
        self.assertIn("e1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d", data["msg"])
        self.assertIn("1729179000", data["msg"])
        self.assertIn("8000", data["msg"])
        self.assertIn("2.45", data["msg"])
        self.assertIn("15.2", data["msg"])
        self.assertIn("2026", data["msg"])
        self.assertIn("9012", data["msg"])


class RequestIDPropagationTests(unittest.TestCase):
    def setUp(self):
        self.formatter = JsonFormatter()
        request_id_var.set("")

    def tearDown(self):
        request_id_var.set("")

    def test_request_id_from_context_var(self):
        request_id_var.set("trace-ctx-999")
        record = logging.LogRecord(
            name="carbonx.test",
            level=logging.INFO,
            pathname=__file__,
            lineno=50,
            msg="test message",
            args=(),
            exc_info=None,
        )
        output = self.formatter.format(record)
        data = json.loads(output)
        self.assertEqual(data.get("request_id"), "trace-ctx-999")

    def test_request_id_from_record_attribute(self):
        record = logging.LogRecord(
            name="carbonx.test",
            level=logging.INFO,
            pathname=__file__,
            lineno=50,
            msg="test message",
            args=(),
            exc_info=None,
        )
        record.request_id = "trace-attr-777"
        output = self.formatter.format(record)
        data = json.loads(output)
        self.assertEqual(data.get("request_id"), "trace-attr-777")

    def test_request_id_propagates_through_http_request(self):
        test_rid = "custom-trace-req-888"
        response = client.get("/", headers={"X-Request-ID": test_rid})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("X-Request-ID"), test_rid)

    def test_auto_generated_request_id_on_http_request(self):
        response = client.get("/")
        self.assertEqual(response.status_code, 200)
        rid = response.headers.get("X-Request-ID")
        self.assertIsNotNone(rid)
        self.assertTrue(len(rid) >= 8)


class PrometheusTelemetryTests(unittest.TestCase):
    def test_metrics_endpoint_healthy(self):
        response = client.get("/metrics")
        self.assertEqual(response.status_code, 200)
        self.assertIn("# HELP", response.text)
        self.assertIn("# TYPE", response.text)

    def test_metrics_include_request_count_counter(self):
        # Trigger requests
        client.get("/")
        client.get("/health")

        response = client.get("/metrics")
        self.assertEqual(response.status_code, 200)
        text = response.text

        # http_requests_total should be declared as counter
        self.assertIn("# TYPE http_requests_total counter", text)
        self.assertIn("http_requests_total{", text)

    def test_metrics_include_latency_histograms(self):
        # Trigger requests
        client.get("/")
        client.get("/health")

        response = client.get("/metrics")
        self.assertEqual(response.status_code, 200)
        text = response.text

        # http_request_duration_seconds or high-resolution variant must be present as histogram
        has_latency_histogram = (
            "# TYPE http_request_duration_seconds histogram" in text
            or "# TYPE http_request_duration_highr_seconds histogram" in text
        )
        self.assertTrue(has_latency_histogram, "Expected HTTP request latency histogram in /metrics")

        # Verify bucket, count, and sum metrics exist
        self.assertTrue(
            "http_request_duration_seconds_bucket{" in text
            or "http_request_duration_highr_seconds_bucket{" in text,
            "Expected latency histogram bucket metric",
        )
        self.assertTrue(
            "http_request_duration_seconds_count" in text
            or "http_request_duration_highr_seconds_count" in text,
            "Expected latency histogram count metric",
        )
        self.assertTrue(
            "http_request_duration_seconds_sum" in text
            or "http_request_duration_highr_seconds_sum" in text,
            "Expected latency histogram sum metric",
        )


if __name__ == "__main__":
    unittest.main()
