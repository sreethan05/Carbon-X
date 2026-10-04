"""Redis-backed short-lived OTP storage with in-memory fallback."""

import hmac
import os
import time
import redis

OTP_TTL_SECONDS = 10 * 60
OTP_MAX_ATTEMPTS = 5
OTP_KEY_PREFIX = "carbonx:otp:"
OTP_ATTEMPT_PREFIX = "carbonx:otp_attempts:"

_client: redis.Redis | None = None
_memory_store: dict[str, tuple[str, float, int]] = {}


def _redis_client() -> redis.Redis | None:
    global _client
    if _client is not None:
        return _client
    try:
        redis_url = os.getenv("REDIS_URL", "redis://localhost:4000").strip()
        client = redis.Redis.from_url(redis_url, decode_responses=True, socket_timeout=1.0)
        client.ping()
        _client = client
        return _client
    except Exception:
        return None


def _key(phone: str) -> str:
    return f"{OTP_KEY_PREFIX}{phone}"


def _attempt_key(phone: str) -> str:
    return f"{OTP_ATTEMPT_PREFIX}{phone}"


def store_otp(phone: str, otp: str) -> None:
    client = _redis_client()
    if client:
        try:
            client.set(_key(phone), otp, ex=OTP_TTL_SECONDS)
            client.delete(_attempt_key(phone))
            return
        except Exception:
            pass
    # In-memory fallback if Redis is down or not running
    _memory_store[phone] = (otp, time.time() + OTP_TTL_SECONDS, 0)


def verify_otp(phone: str, otp: str) -> bool:
    client = _redis_client()
    if client:
        try:
            key = _key(phone)
            stored_otp = client.get(key)
            if not stored_otp:
                return False
            if not hmac.compare_digest(str(stored_otp), str(otp)):
                attempts = int(client.incr(_attempt_key(phone)))
                client.expire(_attempt_key(phone), OTP_TTL_SECONDS)
                if attempts >= OTP_MAX_ATTEMPTS:
                    client.delete(key, _attempt_key(phone))
                return False
            client.delete(key)
            client.delete(_attempt_key(phone))
            return True
        except Exception:
            pass
    # In-memory fallback
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
            client.delete(_key(phone))
            client.delete(_attempt_key(phone))
        except Exception:
            pass
    _memory_store.pop(phone, None)


def health_check() -> bool:
    client = _redis_client()
    if client:
        try:
            return bool(client.ping())
        except Exception:
            return False
    return False

