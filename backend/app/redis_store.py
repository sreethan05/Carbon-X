"""Redis-backed short-lived state (OTP, rate limits, caches, locks, pub/sub)
with in-memory fallbacks so the app runs fully without Redis."""

import hmac
import json
import os
import threading
import time
import redis

from app import config as app_config

OTP_TTL_SECONDS = getattr(app_config, "OTP_TTL_SECONDS", 10 * 60)
OTP_MAX_ATTEMPTS = getattr(app_config, "OTP_MAX_ATTEMPTS", 5)
OTP_SEND_MAX_PER_WINDOW = getattr(app_config, "OTP_SEND_MAX_PER_WINDOW", 3)
OTP_SEND_WINDOW_SECONDS = getattr(app_config, "OTP_SEND_WINDOW_SECONDS", 600)
OTP_KEY_PREFIX = "carbonx:otp:"
OTP_ATTEMPT_PREFIX = "carbonx:otp_attempts:"

_state_lock = threading.RLock()
_client: redis.Redis | None = None
_CLIENT_RETRY_INTERVAL = 15.0  # seconds between probes while Redis is down
_client_checked_at = 0.0
_memory_store: dict[str, tuple[str, float, int]] = {}
_memory_locks: dict[str, float] = {}
_shared_memory: dict[str, tuple[float, str]] = {}
_revoked_memory: dict[str, float] = {}
_SHARED_MEMORY_MAX = 10000


def redis_url() -> str:
    return os.getenv("REDIS_URL", getattr(app_config, "REDIS_URL", "redis://localhost:4000")).strip()


def _handle_disconnect(e: Exception) -> None:
    global _client, _client_checked_at
    if isinstance(e, (redis.RedisError, ConnectionResetError, BrokenPipeError, TimeoutError, OSError)):
        _client = None
        _client_checked_at = time.time()


def reset_redis_client() -> None:
    """Reset the cached Redis client and probe timer (useful for testing)."""
    global _client, _client_checked_at
    _client = None
    _client_checked_at = 0.0


def reset_all_memory_stores() -> None:
    """Clear all in-memory fallback stores (useful for test isolation)."""
    with _state_lock:
        _memory_store.clear()
        _send_memory.clear()
        _memory_locks.clear()
        _memory_cache.clear()
        _shared_memory.clear()
        _revoked_memory.clear()



def _redis_client() -> redis.Redis | None:
    """One shared client. A failed probe is remembered briefly so a missing
    Redis costs one connection attempt per interval, not one per call."""
    global _client, _client_checked_at
    if _client is not None:
        return _client
    now = time.time()
    if now - _client_checked_at < _CLIENT_RETRY_INTERVAL:
        return None
    _client_checked_at = now
    try:
        client = redis.Redis.from_url(redis_url(), decode_responses=True, socket_timeout=1.0)
        client.ping()
        _client = client
        return _client
    except Exception:
        return None


def redis_available() -> bool:
    return _redis_client() is not None


def _key(phone: str) -> str:
    return f"{OTP_KEY_PREFIX}{phone}"


def _attempt_key(phone: str) -> str:
    return f"{OTP_ATTEMPT_PREFIX}{phone}"


def store_otp(phone: str, otp: str) -> None:
    client = _redis_client()
    if client:
        try:
            pipe = client.pipeline()
            pipe.set(_key(phone), otp, ex=OTP_TTL_SECONDS)
            pipe.delete(_attempt_key(phone))
            pipe.execute()
            return
        except Exception as e:
            _handle_disconnect(e)
    # In-memory fallback if Redis is down or not running
    with _state_lock:
        now = time.time()
        _memory_store[phone] = (otp, now + OTP_TTL_SECONDS, 0)
        if len(_memory_store) > 10000:
            for k in [k for k, (_, exp, _) in _memory_store.items() if now > exp]:
                _memory_store.pop(k, None)
            while len(_memory_store) > 10000:
                _memory_store.pop(next(iter(_memory_store)))


def verify_otp(phone: str, otp: str) -> bool:
    client = _redis_client()
    if client:
        try:
            key = _key(phone)
            stored_otp = client.get(key)
            if not stored_otp:
                return False
            if not hmac.compare_digest(str(stored_otp), str(otp)):
                pipe = client.pipeline()
                pipe.incr(_attempt_key(phone))
                pipe.expire(_attempt_key(phone), OTP_TTL_SECONDS)
                res = pipe.execute()
                attempts = int(res[0])
                if attempts >= OTP_MAX_ATTEMPTS:
                    client.delete(key, _attempt_key(phone))
                return False
            client.delete(key, _attempt_key(phone))
            with _state_lock:
                _memory_store.pop(phone, None)
            return True
        except Exception as e:
            _handle_disconnect(e)
    # In-memory fallback
    with _state_lock:
        stored = _memory_store.get(phone)
        if not stored:
            return False
        val, exp, attempts = stored
        if time.time() > exp:
            _memory_store.pop(phone, None)
            return False
        if not hmac.compare_digest(str(val), str(otp)):
            attempts += 1
            if attempts >= OTP_MAX_ATTEMPTS:
                _memory_store.pop(phone, None)
            else:
                _memory_store[phone] = (val, exp, attempts)
            return False
        _memory_store.pop(phone, None)
        return True


def clear_otp(phone: str) -> None:
    client = _redis_client()
    if client:
        try:
            client.delete(_key(phone), _attempt_key(phone))
        except Exception as e:
            _handle_disconnect(e)
    with _state_lock:
        _memory_store.pop(phone, None)


def health_check() -> bool:
    client = _redis_client()
    if client:
        try:
            return bool(client.ping())
        except Exception as e:
            _handle_disconnect(e)
            return False
    return False


# ── Distributed OTP-send rate limiting (#2) ──
_SEND_KEY_PREFIX = "carbonx:otp_sends:"
_send_memory: dict[str, list[float]] = {}


def otp_send_rate_limited(
    phone: str,
    max_sends: int = OTP_SEND_MAX_PER_WINDOW,
    window_seconds: int = OTP_SEND_WINDOW_SECONDS,
) -> bool:
    """Sliding-window limiter backed by a Redis sorted set when available
    (works across workers/instances); falls back to per-process memory."""
    now = time.time()
    max_sends = max(0, int(max_sends))
    window_seconds = max(1, int(window_seconds))
    if max_sends == 0:
        return True
    client = _redis_client()
    key = f"{_SEND_KEY_PREFIX}{phone}"
    if client is not None:
        try:
            pipe = client.pipeline()
            pipe.zremrangebyscore(key, 0, now - window_seconds)
            pipe.zcard(key)
            _, count = pipe.execute()
            if count >= max_sends:
                return True
            member = f"{now}:{time.time_ns()}"
            pipe = client.pipeline()
            pipe.zadd(key, {member: now})
            pipe.expire(key, window_seconds)
            pipe.execute()
            return False
        except Exception as e:
            _handle_disconnect(e)
            pass  # fall through to memory limiter
    with _state_lock:
        if len(_send_memory) > 10000:
            expired = [p for p, timestamps in _send_memory.items() if not timestamps or (now - timestamps[-1] >= window_seconds)]
            for p in expired:
                _send_memory.pop(p, None)
        hits = [t for t in _send_memory.get(phone, []) if now - t < window_seconds]
        if len(hits) >= max_sends:
            _send_memory[phone] = hits
            return True
        hits.append(now)
        _send_memory[phone] = hits
        return False


# ── Token Revocation & Blocklist ──────────────────────────────────────────
_REVOCATION_PREFIX = "carbonx:revoked_token:"


def revoke_token(token_signature: str, ttl_seconds: int = 86400) -> None:
    """Revoke a token identifier (e.g. SHA-256 of token) for the remainder of its lifetime."""
    if not token_signature:
        return
    client = _redis_client()
    key = f"{_REVOCATION_PREFIX}{token_signature}"
    if client is not None:
        try:
            client.set(key, "1", ex=max(1, int(ttl_seconds)))
            return
        except Exception as e:
            _handle_disconnect(e)
    with _state_lock:
        now = time.time()
        _revoked_memory[token_signature] = now + max(1, int(ttl_seconds))
        if len(_revoked_memory) > 5000:
            expired = [k for k, exp in _revoked_memory.items() if now >= exp]
            for k in expired:
                _revoked_memory.pop(k, None)


def is_token_revoked(token_signature: str) -> bool:
    """Check if a token identifier has been revoked."""
    if not token_signature:
        return False
    client = _redis_client()
    key = f"{_REVOCATION_PREFIX}{token_signature}"
    if client is not None:
        try:
            return bool(client.exists(key))
        except Exception as e:
            _handle_disconnect(e)
    with _state_lock:
        exp = _revoked_memory.get(token_signature)
        if exp is None:
            return False
        if time.time() >= exp:
            _revoked_memory.pop(token_signature, None)
            return False
        return True


# ── Cross-worker coordination ─────────────────────────────────────────────
# These make multi-worker deployments (uvicorn --workers N) safe: one
# monitor cycle per interval, ledger events fan out to every worker, and
# caches are shared. Each helper degrades to a correct single-process
# fallback when Redis is not configured.

def acquire_lock(name: str, ttl_seconds: int = 3600) -> bool:
    """Best-effort distributed lock via SET NX EX with in-memory fallback.

    When Redis is available, uses atomic SET NX EX.
    When Redis is unavailable, maintains an in-memory lock table with TTL expiry
    so mutual exclusion is preserved within the process.
    """
    ttl = max(1, int(ttl_seconds))
    client = _redis_client()
    if client is not None:
        try:
            return bool(client.set(f"carbonx:lock:{name}", "1", nx=True, ex=ttl))
        except Exception as e:
            _handle_disconnect(e)
            # fall through to memory fallback
    with _state_lock:
        now = time.time()
        exp = _memory_locks.get(name)
        if exp is not None and exp > now:
            return False
        _memory_locks[name] = now + ttl
        if len(_memory_locks) > 1000:
            for k in [k for k, e in _memory_locks.items() if e <= now]:
                _memory_locks.pop(k, None)
            while len(_memory_locks) > 1000:
                _memory_locks.pop(next(iter(_memory_locks)))
        return True


def release_lock(name: str) -> bool:
    """Release a distributed lock previously acquired via acquire_lock.

    Returns True if the lock key was deleted or released from memory fallback,
    False if the release failed or the lock was not held.
    """
    client = _redis_client()
    if client is not None:
        try:
            res = bool(client.delete(f"carbonx:lock:{name}"))
            with _state_lock:
                _memory_locks.pop(name, None)
            return res
        except Exception as e:
            _handle_disconnect(e)
            # fall through to memory fallback
    with _state_lock:
        now = time.time()
        exp = _memory_locks.pop(name, None)
        if exp is not None and exp > now:
            return True
        return False


LEDGER_CHANNEL_PREFIX = "carbonx:ledger:"


def publish_ledger_event(entity_id: str, event: dict) -> bool:
    """Fan a ledger event out to other workers over Redis pub/sub.

    Returns False when Redis is unavailable — the emitting worker still
    delivers to its own WebSocket subscribers in-process."""
    client = _redis_client()
    if client is None:
        return False
    try:
        client.publish(LEDGER_CHANNEL_PREFIX + entity_id, json.dumps(event, default=str))
        return True
    except Exception as e:
        _handle_disconnect(e)
        return False


_CACHE_PREFIX = "carbonx:cache:"
_memory_cache: dict[str, tuple[float, str]] = {}
_MEMORY_CACHE_MAX = 1024


def cache_get(key: str) -> str | None:
    """Fetch a cached string (JSON) — Redis first, then this worker's memory."""
    client = _redis_client()
    if client is not None:
        try:
            value = client.get(_CACHE_PREFIX + key)
            if value is not None:
                return value
        except Exception as e:
            _handle_disconnect(e)
    with _state_lock:
        hit = _memory_cache.get(key)
        if not hit:
            return None
        expires_at, value = hit
        if time.time() >= expires_at:
            _memory_cache.pop(key, None)
            return None
        return value


def cache_set(key: str, value: str, ttl_seconds: int) -> None:
    """Store a string (JSON) with a TTL; memory fallback without Redis."""
    ttl = max(1, int(ttl_seconds))
    client = _redis_client()
    if client is not None:
        try:
            client.set(_CACHE_PREFIX + key, value, ex=ttl)
            return
        except Exception as e:
            _handle_disconnect(e)
    with _state_lock:
        now = time.time()
        _memory_cache[key] = (now + ttl, value)
        if len(_memory_cache) > _MEMORY_CACHE_MAX:
            for k in [k for k, (exp, _) in _memory_cache.items() if exp <= now]:
                _memory_cache.pop(k, None)
            while len(_memory_cache) > _MEMORY_CACHE_MAX:
                _memory_cache.pop(next(iter(_memory_cache)))


# ── Shared keys with in-memory fallback ──────────────────────────────────
# Distributed across workers when Redis is configured; degrades to
# in-process TTL dictionary when running without Redis.

def shared_get(key: str) -> str | None:
    """Fetch a shared string key — Redis first, then memory fallback."""
    client = _redis_client()
    if client is not None:
        try:
            value = client.get(key)
            if value is not None:
                return value
        except Exception as e:
            _handle_disconnect(e)
    with _state_lock:
        hit = _shared_memory.get(key)
        if not hit:
            return None
        expires_at, value = hit
        if time.time() >= expires_at:
            _shared_memory.pop(key, None)
            return None
        return value


def shared_set(key: str, value: str, ttl_seconds: int) -> bool:
    """Store a shared string key with TTL — Redis first, then memory fallback."""
    ttl = max(1, int(ttl_seconds))
    client = _redis_client()
    if client is not None:
        try:
            client.set(key, str(value), ex=ttl)
            return True
        except Exception as e:
            _handle_disconnect(e)
    with _state_lock:
        now = time.time()
        _shared_memory[key] = (now + ttl, str(value))
        if len(_shared_memory) > _SHARED_MEMORY_MAX:
            for k in [k for k, (exp, _) in _shared_memory.items() if exp <= now]:
                _shared_memory.pop(k, None)
            while len(_shared_memory) > _SHARED_MEMORY_MAX:
                _shared_memory.pop(next(iter(_shared_memory)))
        return True


def shared_delete(key: str) -> bool:
    """Delete a shared key — Redis first, then memory fallback."""
    client = _redis_client()
    if client is not None:
        try:
            res = bool(client.delete(key))
            with _state_lock:
                _shared_memory.pop(key, None)
            return res
        except Exception as e:
            _handle_disconnect(e)
    with _state_lock:
        hit = _shared_memory.pop(key, None)
        if hit is not None:
            expires_at, _ = hit
            return time.time() < expires_at
        return False
