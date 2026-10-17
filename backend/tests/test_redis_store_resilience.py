"""Tests for Redis store resilience and in-memory fallbacks when Redis is unavailable.

Covers:
1. Shared keys: shared_get, shared_set, shared_delete with TTL & cleanup
2. Locks: acquire_lock, release_lock mutual exclusion, TTL expiry, and release semantics
3. Rate limiting: otp_send_rate_limited in-memory sliding window, boundary conditions
4. OTP lifecycle: store_otp, verify_otp (attempts lockout, single use), clear_otp
5. Cache & pub/sub fallbacks: cache_get/set, publish_ledger_event
6. Disconnect handling: mid-call Redis errors gracefully falling back to memory
"""

import os
import sys
import time
import unittest
from unittest.mock import MagicMock, patch

import redis

# Ensure backend root is in sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import redis_store


class RedisUnavailableBaseTestCase(unittest.TestCase):
    """Base test case ensuring Redis is forced unavailable."""

    def setUp(self):
        redis_store.reset_redis_client()
        redis_store.reset_all_memory_stores()
        # Force _redis_client to return None to test pure in-memory paths
        self._client_patch = patch.object(redis_store, "_redis_client", return_value=None)
        self._client_patch.start()

    def tearDown(self):
        self._client_patch.stop()
        redis_store.reset_redis_client()
        redis_store.reset_all_memory_stores()


class SharedMemoryStoreResilienceTests(RedisUnavailableBaseTestCase):
    """Resilience tests for shared_get, shared_set, and shared_delete."""

    def test_shared_set_and_get(self):
        self.assertTrue(redis_store.shared_set("user:session:1", "active", ttl_seconds=60))
        self.assertEqual(redis_store.shared_get("user:session:1"), "active")

    def test_shared_get_nonexistent(self):
        self.assertIsNone(redis_store.shared_get("nonexistent_key_xyz"))

    def test_shared_ttl_expiration(self):
        # Set with 1-second TTL
        redis_store.shared_set("temp_token", "secret123", ttl_seconds=1)
        self.assertEqual(redis_store.shared_get("temp_token"), "secret123")
        # Artificially expire in memory
        with redis_store._state_lock:
            redis_store._shared_memory["temp_token"] = (time.time() - 1.0, "secret123")
        self.assertIsNone(redis_store.shared_get("temp_token"))
        # Key should have been evicted
        self.assertNotIn("temp_token", redis_store._shared_memory)

    def test_shared_set_overwrite(self):
        redis_store.shared_set("config:flag", "false", ttl_seconds=60)
        self.assertEqual(redis_store.shared_get("config:flag"), "false")
        redis_store.shared_set("config:flag", "true", ttl_seconds=120)
        self.assertEqual(redis_store.shared_get("config:flag"), "true")

    def test_shared_delete_existing(self):
        redis_store.shared_set("key_to_del", "val", ttl_seconds=60)
        self.assertTrue(redis_store.shared_delete("key_to_del"))
        self.assertIsNone(redis_store.shared_get("key_to_del"))

    def test_shared_delete_nonexistent(self):
        self.assertFalse(redis_store.shared_delete("does_not_exist"))

    def test_shared_delete_expired(self):
        redis_store.shared_set("expired_del", "val", ttl_seconds=1)
        with redis_store._state_lock:
            redis_store._shared_memory["expired_del"] = (time.time() - 0.5, "val")
        self.assertFalse(redis_store.shared_delete("expired_del"))

    def test_shared_set_clamps_non_positive_ttl(self):
        self.assertTrue(redis_store.shared_set("zero_ttl", "val", ttl_seconds=0))
        self.assertEqual(redis_store.shared_get("zero_ttl"), "val")
        self.assertTrue(redis_store.shared_set("neg_ttl", "val", ttl_seconds=-10))
        self.assertEqual(redis_store.shared_get("neg_ttl"), "val")

    def test_shared_memory_max_eviction(self):
        with patch.object(redis_store, "_SHARED_MEMORY_MAX", 5):
            now = time.time()
            for i in range(10):
                redis_store.shared_set(f"k_{i}", f"v_{i}", ttl_seconds=100)
            self.assertLessEqual(len(redis_store._shared_memory), 5)
            # The most recent key should still be accessible
            self.assertEqual(redis_store.shared_get("k_9"), "v_9")


class LockResilienceTests(RedisUnavailableBaseTestCase):
    """Resilience tests for acquire_lock and release_lock in-memory fallback."""

    def test_acquire_and_release_lock_success(self):
        lock_name = "ledger_sync_lock"
        self.assertTrue(redis_store.acquire_lock(lock_name, ttl_seconds=60))
        self.assertTrue(redis_store.release_lock(lock_name))

    def test_acquire_lock_mutual_exclusion(self):
        lock_name = "payment_settle_order_123"
        # First acquisition succeeds
        self.assertTrue(redis_store.acquire_lock(lock_name, ttl_seconds=60))
        # Second acquisition while held must fail
        self.assertFalse(redis_store.acquire_lock(lock_name, ttl_seconds=60))
        # Releasing allows acquisition again
        self.assertTrue(redis_store.release_lock(lock_name))
        self.assertTrue(redis_store.acquire_lock(lock_name, ttl_seconds=60))

    def test_release_unheld_lock(self):
        self.assertFalse(redis_store.release_lock("unheld_lock_abc"))

    def test_double_release_fails_second_time(self):
        lock_name = "double_release_test"
        self.assertTrue(redis_store.acquire_lock(lock_name, ttl_seconds=60))
        self.assertTrue(redis_store.release_lock(lock_name))
        self.assertFalse(redis_store.release_lock(lock_name))

    def test_lock_ttl_expiration(self):
        lock_name = "auto_expire_lock"
        redis_store.acquire_lock(lock_name, ttl_seconds=1)
        self.assertFalse(redis_store.acquire_lock(lock_name, ttl_seconds=1))
        # Simulate expiration
        with redis_store._state_lock:
            redis_store._memory_locks[lock_name] = time.time() - 0.5
        # Can now be acquired again
        self.assertTrue(redis_store.acquire_lock(lock_name, ttl_seconds=60))

    def test_release_expired_lock_returns_false(self):
        lock_name = "expired_release"
        redis_store.acquire_lock(lock_name, ttl_seconds=1)
        with redis_store._state_lock:
            redis_store._memory_locks[lock_name] = time.time() - 0.5
        # Attempting to release an expired lock returns False
        self.assertFalse(redis_store.release_lock(lock_name))

    def test_distinct_locks_independent(self):
        self.assertTrue(redis_store.acquire_lock("lock_a", ttl_seconds=60))
        self.assertTrue(redis_store.acquire_lock("lock_b", ttl_seconds=60))
        self.assertFalse(redis_store.acquire_lock("lock_a", ttl_seconds=60))
        self.assertTrue(redis_store.release_lock("lock_a"))
        self.assertTrue(redis_store.acquire_lock("lock_a", ttl_seconds=60))
        self.assertTrue(redis_store.release_lock("lock_b"))


class OtpSendRateLimitingResilienceTests(RedisUnavailableBaseTestCase):
    """Resilience tests for otp_send_rate_limited in-memory sliding window."""

    def test_rate_limiting_sliding_window(self):
        phone = "9876543210"
        max_sends = 3
        window = 60

        # First 3 sends are allowed
        self.assertFalse(redis_store.otp_send_rate_limited(phone, max_sends=max_sends, window_seconds=window))
        self.assertFalse(redis_store.otp_send_rate_limited(phone, max_sends=max_sends, window_seconds=window))
        self.assertFalse(redis_store.otp_send_rate_limited(phone, max_sends=max_sends, window_seconds=window))

        # 4th send within the window is blocked
        self.assertTrue(redis_store.otp_send_rate_limited(phone, max_sends=max_sends, window_seconds=window))
        # 5th send is also blocked
        self.assertTrue(redis_store.otp_send_rate_limited(phone, max_sends=max_sends, window_seconds=window))

    def test_sliding_window_recovery_after_expiry(self):
        phone = "9876543211"
        max_sends = 2
        window = 10

        self.assertFalse(redis_store.otp_send_rate_limited(phone, max_sends=max_sends, window_seconds=window))
        self.assertFalse(redis_store.otp_send_rate_limited(phone, max_sends=max_sends, window_seconds=window))
        self.assertTrue(redis_store.otp_send_rate_limited(phone, max_sends=max_sends, window_seconds=window))

        # Advance timestamps so all entries are outside window
        with redis_store._state_lock:
            redis_store._send_memory[phone] = [time.time() - 15.0, time.time() - 12.0]

        # Allowed again
        self.assertFalse(redis_store.otp_send_rate_limited(phone, max_sends=max_sends, window_seconds=window))

    def test_independent_phone_limits(self):
        phone1 = "9000000001"
        phone2 = "9000000002"

        for _ in range(3):
            self.assertFalse(redis_store.otp_send_rate_limited(phone1, max_sends=3, window_seconds=60))
        self.assertTrue(redis_store.otp_send_rate_limited(phone1, max_sends=3, window_seconds=60))

        # phone2 should still have quota
        self.assertFalse(redis_store.otp_send_rate_limited(phone2, max_sends=3, window_seconds=60))

    def test_zero_max_sends_always_limited(self):
        phone = "9111111111"
        self.assertTrue(redis_store.otp_send_rate_limited(phone, max_sends=0, window_seconds=60))


class OtpLifecycleResilienceTests(RedisUnavailableBaseTestCase):
    """Resilience tests for store_otp, verify_otp, clear_otp in-memory fallback."""

    def test_otp_verification_success_is_single_use(self):
        phone = "9999900001"
        redis_store.store_otp(phone, "654321")
        self.assertTrue(redis_store.verify_otp(phone, "654321"))
        # Must not be reusable
        self.assertFalse(redis_store.verify_otp(phone, "654321"))

    def test_otp_incorrect_code_increments_attempts_until_lockout(self):
        phone = "9999900002"
        redis_store.store_otp(phone, "112233")
        # 4 wrong attempts
        for _ in range(4):
            self.assertFalse(redis_store.verify_otp(phone, "000000"))
        # 5th wrong attempt triggers lockout
        self.assertFalse(redis_store.verify_otp(phone, "000000"))
        # 6th attempt with CORRECT OTP fails because OTP was invalidated
        self.assertFalse(redis_store.verify_otp(phone, "112233"))

    def test_otp_expired_fails(self):
        phone = "9999900003"
        redis_store.store_otp(phone, "998877")
        with redis_store._state_lock:
            val, exp, attempts = redis_store._memory_store[phone]
            redis_store._memory_store[phone] = (val, time.time() - 10.0, attempts)
        self.assertFalse(redis_store.verify_otp(phone, "998877"))

    def test_clear_otp(self):
        phone = "9999900004"
        redis_store.store_otp(phone, "445566")
        redis_store.clear_otp(phone)
        self.assertFalse(redis_store.verify_otp(phone, "445566"))


class CacheAndPubSubResilienceTests(RedisUnavailableBaseTestCase):
    """Resilience tests for cache_get/cache_set and publish_ledger_event."""

    def test_cache_get_and_set(self):
        redis_store.cache_set("scan_hash_1", '{"carbon": 12.5}', ttl_seconds=60)
        self.assertEqual(redis_store.cache_get("scan_hash_1"), '{"carbon": 12.5}')

    def test_cache_expiration(self):
        redis_store.cache_set("scan_hash_exp", '{"carbon": 1.0}', ttl_seconds=1)
        with redis_store._state_lock:
            redis_store._memory_cache["scan_hash_exp"] = (time.time() - 1.0, '{"carbon": 1.0}')
        self.assertIsNone(redis_store.cache_get("scan_hash_exp"))

    def test_publish_ledger_event_fails_gracefully(self):
        # Pub/Sub has no memory broadcast without Redis; returns False safely
        res = redis_store.publish_ledger_event("farm_123", {"event": "ISSUE"})
        self.assertFalse(res)


class DisconnectAndFailoverTests(unittest.TestCase):
    """Tests simulating mid-flight Redis connection drops and exception handling."""

    def setUp(self):
        redis_store.reset_redis_client()
        redis_store.reset_all_memory_stores()

    def tearDown(self):
        redis_store.reset_redis_client()
        redis_store.reset_all_memory_stores()

    def test_redis_available_and_health_check_down(self):
        with patch.object(redis_store, "_redis_client", return_value=None):
            self.assertFalse(redis_store.redis_available())
            self.assertFalse(redis_store.health_check())

    def test_handle_disconnect_resets_client_on_network_errors(self):
        redis_store._client = MagicMock()
        redis_store._client_checked_at = 0.0

        for exc in (
            redis.ConnectionError("Connection refused"),
            redis.TimeoutError("Socket timed out"),
            ConnectionResetError("Peer reset connection"),
            BrokenPipeError("Broken pipe"),
            OSError("Network unreachable"),
        ):
            redis_store._client = MagicMock()
            redis_store._handle_disconnect(exc)
            self.assertIsNone(redis_store._client, f"Failed for {type(exc)}")
            self.assertGreater(redis_store._client_checked_at, 0.0)

    def test_shared_set_falls_back_when_redis_pipe_raises(self):
        mock_client = MagicMock()
        mock_client.set.side_effect = redis.ConnectionError("Redis server crashed")

        with patch.object(redis_store, "_redis_client", return_value=mock_client):
            # Must not throw; should fall back to memory and return True
            success = redis_store.shared_set("resilient_key", "survives_crash", ttl_seconds=60)
            self.assertTrue(success)

        # Now verify it's available via in-memory fallback
        with patch.object(redis_store, "_redis_client", return_value=None):
            self.assertEqual(redis_store.shared_get("resilient_key"), "survives_crash")

    def test_acquire_lock_falls_back_when_redis_raises(self):
        mock_client = MagicMock()
        mock_client.set.side_effect = redis.TimeoutError("Redis timed out")

        with patch.object(redis_store, "_redis_client", return_value=mock_client):
            # Should fall back to in-memory lock
            self.assertTrue(redis_store.acquire_lock("failover_lock", ttl_seconds=60))

        with patch.object(redis_store, "_redis_client", return_value=None):
            # Second acquire in memory must fail (mutual exclusion preserved)
            self.assertFalse(redis_store.acquire_lock("failover_lock", ttl_seconds=60))
            # Release succeeds
            self.assertTrue(redis_store.release_lock("failover_lock"))

    def test_otp_rate_limiter_falls_back_when_redis_zset_raises(self):
        mock_client = MagicMock()
        mock_pipe = MagicMock()
        mock_pipe.execute.side_effect = redis.ConnectionError("Connection lost during pipeline")
        mock_client.pipeline.return_value = mock_pipe

        phone = "9988001122"
        with patch.object(redis_store, "_redis_client", return_value=mock_client):
            # First send falls through to memory and succeeds
            self.assertFalse(redis_store.otp_send_rate_limited(phone, max_sends=2, window_seconds=60))
            # Second send succeeds
            self.assertFalse(redis_store.otp_send_rate_limited(phone, max_sends=2, window_seconds=60))
            # Third send is rate limited in memory
            self.assertTrue(redis_store.otp_send_rate_limited(phone, max_sends=2, window_seconds=60))


if __name__ == "__main__":
    unittest.main()
