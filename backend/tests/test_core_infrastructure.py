"""Tests for core infrastructure components:
- config.py (_env_bool, _env_int, _env_str, defaults)
- logging_setup.py (JsonFormatter, request_id correlation, exception handling)
- redis_store.py (OTP, rate limiting, locks, shared/cache operations, disconnect handling)
- main.py (security headers, trace headers, uniform error envelope, CORS)
"""
import json
import logging
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import config as app_config
from app import logging_setup
from app import redis_store
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


class ConfigTests(unittest.TestCase):
    def test_env_bool_default_true_when_unset(self):
        k = "_TEST_CARBONX_BOOL_UNSET_VAR_XYZ"
        os.environ.pop(k, None)
        self.assertTrue(app_config._env_bool(k, default=True))
        self.assertFalse(app_config._env_bool(k, default=False))

    def test_env_bool_empty_string_yields_default(self):
        k = "_TEST_CARBONX_BOOL_EMPTY"
        os.environ[k] = "   "
        self.assertTrue(app_config._env_bool(k, default=True))
        self.assertFalse(app_config._env_bool(k, default=False))
        os.environ.pop(k, None)

    def test_env_bool_falsy_values(self):
        k = "_TEST_CARBONX_BOOL_FALSE"
        for val in ("0", "false", "False", "no", "NO", "off", "OFF"):
            os.environ[k] = val
            self.assertFalse(app_config._env_bool(k, default=True))
        os.environ.pop(k, None)

    def test_env_bool_truthy_values(self):
        k = "_TEST_CARBONX_BOOL_TRUE"
        for val in ("1", "true", "True", "yes", "YES", "on", "ON"):
            os.environ[k] = val
            self.assertTrue(app_config._env_bool(k, default=False))
        os.environ.pop(k, None)


class LoggingSetupTests(unittest.TestCase):
    def test_json_formatter_valid_json_and_request_id(self):
        formatter = logging_setup.JsonFormatter()
        logging_setup.request_id_var.set("test-request-id-123")
        record = logging.LogRecord(
            name="carbonx.test",
            level=logging.INFO,
            pathname=__file__,
            lineno=10,
            msg="test message",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        data = json.loads(output)
        self.assertEqual(data["logger"], "carbonx.test")
        self.assertEqual(data["level"], "INFO")
        self.assertEqual(data["msg"], "test message")
        self.assertEqual(data["request_id"], "test-request-id-123")
        self.assertIn("ts", data)

    def test_json_formatter_handles_formatting_errors_gracefully(self):
        formatter = logging_setup.JsonFormatter()
        record = logging.LogRecord(
            name="carbonx.test",
            level=logging.ERROR,
            pathname=__file__,
            lineno=20,
            msg="Hello %s %s",  # missing arguments
            args=("only_one",),
            exc_info=None,
        )
        output = formatter.format(record)
        data = json.loads(output)
        self.assertIn("Hello", data["msg"])


class RedisStoreTests(unittest.TestCase):
    def setUp(self):
        redis_store.clear_otp("9999999999")

    def tearDown(self):
        redis_store.clear_otp("9999999999")

    def test_otp_lifecycle_in_memory(self):
        phone = "9999999999"
        redis_store.store_otp(phone, "123456")
        # Wrong attempt
        self.assertFalse(redis_store.verify_otp(phone, "000000"))
        # Correct attempt
        self.assertTrue(redis_store.verify_otp(phone, "123456"))
        # Re-verification fails (single use)
        self.assertFalse(redis_store.verify_otp(phone, "123456"))

    def test_otp_max_attempts_exceeded(self):
        phone = "9999999999"
        redis_store.store_otp(phone, "888888")
        for _ in range(5):
            self.assertFalse(redis_store.verify_otp(phone, "000000"))
        # 6th attempt with correct OTP still fails because limit exceeded
        self.assertFalse(redis_store.verify_otp(phone, "888888"))

    def test_distributed_lock_acquire_and_release(self):
        lock_name = "test_feature_lock"
        self.assertTrue(redis_store.acquire_lock(lock_name, ttl_seconds=60))
        self.assertTrue(redis_store.release_lock(lock_name))

    def test_otp_send_rate_limiting(self):
        phone = "9999999998"
        # Reset memory for this phone
        redis_store._send_memory.pop(phone, None)
        self.assertFalse(redis_store.otp_send_rate_limited(phone, max_sends=3, window_seconds=60))
        self.assertFalse(redis_store.otp_send_rate_limited(phone, max_sends=3, window_seconds=60))
        self.assertFalse(redis_store.otp_send_rate_limited(phone, max_sends=3, window_seconds=60))
        # 4th send within window must be rate limited
        self.assertTrue(redis_store.otp_send_rate_limited(phone, max_sends=3, window_seconds=60))

    def test_shared_and_cache_operations(self):
        key = "unit_test_key"
        self.assertTrue(redis_store.shared_set(key, "val123", ttl_seconds=60) or not redis_store.redis_available())
        redis_store.cache_set("cache_key_xyz", "cached_val", ttl_seconds=60)
        self.assertEqual(redis_store.cache_get("cache_key_xyz"), "cached_val")


class MainAppMiddlewareTests(unittest.TestCase):
    def test_security_headers_present(self):
        r = client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(r.headers.get("X-Frame-Options"), "DENY")
        self.assertEqual(r.headers.get("Referrer-Policy"), "strict-origin-when-cross-origin")
        self.assertIn("default-src", r.headers.get("Content-Security-Policy", ""))
        self.assertTrue(len(r.headers.get("X-Request-ID", "")) > 0)
        self.assertEqual(r.headers.get("X-API-Version"), "1.0.0")

    def test_request_id_header_sanitization(self):
        # Valid custom request ID echoed
        r = client.get("/", headers={"X-Request-ID": "custom-trace-id-123"})
        self.assertEqual(r.headers.get("X-Request-ID"), "custom-trace-id-123")

        # Invalid CRLF injection sanitized to generated uuid
        r = client.get("/", headers={"X-Request-ID": "bad\r\ninjected: header"})
        self.assertNotEqual(r.headers.get("X-Request-ID"), "bad\r\ninjected: header")
        self.assertTrue(len(r.headers.get("X-Request-ID", "")) > 0)

    def test_validation_error_envelope_carries_code(self):
        # Send bad JSON that fails Pydantic validation
        r = client.post("/marketplace/buy", json={"bad_field": 123})
        self.assertEqual(r.status_code, 422)
        body = r.json()
        self.assertFalse(body["success"])
        self.assertEqual(body.get("code"), "VALIDATION_ERROR")
        self.assertTrue("message" in body)


if __name__ == "__main__":
    unittest.main()
