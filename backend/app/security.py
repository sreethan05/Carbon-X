import os
import re
import secrets
import hashlib
from app import redis_store
from app import supabase_db
import bcrypt
import logging
from jose import jwt, JWTError
from datetime import datetime, timedelta, timezone
from fastapi import Depends, Header, HTTPException
from typing import Optional

logger = logging.getLogger("carbonx.security")

_DEV_EPHEMERAL_SECRET = secrets.token_urlsafe(48)
ALGORITHM = "HS256"
_BCRYPT_MAX_BYTES = 72
JWT_ACCESS_TOKEN_EXPIRE_HOURS = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_HOURS", "24"))


def token_signature(token: str) -> str:
    """Return a fixed-length SHA-256 identifier for a token string."""
    return hashlib.sha256(token.strip().encode("utf-8")).hexdigest()


def revoke_token(token: str, ttl_seconds: int = 86400) -> None:
    """Add a token to the revocation blocklist for cross-worker invalidation."""
    redis_store.revoke_token(token_signature(token), ttl_seconds=ttl_seconds)


def is_token_revoked(token: str) -> bool:
    """Check if a token has been revoked."""
    return redis_store.is_token_revoked(token_signature(token))


def _get_secret_key() -> str:
    """Retrieve a configured JWT key; production must never use a fallback."""
    secret = os.getenv("JWT_SECRET_KEY", "").strip()
    if secret:
        return secret
    if os.getenv("CARBONX_ENVIRONMENT", "development").strip().lower() in {"production", "prod"}:
        raise RuntimeError("JWT_SECRET_KEY must be set in production")
    # Development-only: an ephemeral process key is safer than a known shared
    # default and intentionally invalidates sessions after a restart.
    return _DEV_EPHEMERAL_SECRET


# Backwards compatibility for modules importing SECRET_KEY directly
SECRET_KEY = _get_secret_key()


def hash_password(password: str) -> str:
    if not password:
        raise ValueError("Password cannot be empty")
    pw_bytes = str(password).encode("utf-8")[:_BCRYPT_MAX_BYTES]
    return bcrypt.hashpw(pw_bytes, bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(plain_password, hashed_password) -> bool:
    if not plain_password or not hashed_password:
        return False
    try:
        pw_bytes = plain_password.encode("utf-8") if isinstance(plain_password, str) else bytes(plain_password)
        hash_bytes = hashed_password.encode("utf-8") if isinstance(hashed_password, str) else bytes(hashed_password)
        return bcrypt.checkpw(pw_bytes[:_BCRYPT_MAX_BYTES], hash_bytes)
    except Exception:
        return False


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    to_encode.setdefault("iat", int(now.timestamp()))
    to_encode["exp"] = now + (expires_delta or timedelta(hours=JWT_ACCESS_TOKEN_EXPIRE_HOURS))
    return jwt.encode(to_encode, _get_secret_key(), algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    if not token or not isinstance(token, str):
        return None
    if is_token_revoked(token):
        return None
    try:
        return jwt.decode(token, _get_secret_key(), algorithms=[ALGORITHM])
    except (JWTError, Exception):
        return None


def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    if not authorization or not authorization.strip():
        raise HTTPException(status_code=401, detail="Not authenticated")
    parts = authorization.split(None, 1)
    if len(parts) < 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = parts[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Invalid token")
    if is_token_revoked(token):
        raise HTTPException(status_code=401, detail="Token has been revoked")
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")

    # When live DB is active, enforce real-time status and role changes
    if supabase_db.is_ready():
        phone = payload.get("phone")
        c_id = payload.get("c_id")
        if phone:
            profile = supabase_db.get_profile(phone)
            if profile is not None:
                if profile.get("is_active") is False or profile.get("status") == "disabled":
                    raise HTTPException(status_code=403, detail="Account has been deactivated")
                db_role = profile.get("role")
                if db_role and db_role != payload.get("role"):
                    payload["role"] = db_role
        elif c_id is not None:
            corp = supabase_db.get_corporate_by_id(c_id)
            if corp is not None:
                if corp.get("is_active") is False or corp.get("status") == "disabled":
                    raise HTTPException(status_code=403, detail="Corporate account has been deactivated")

    return payload


def get_current_user_optional(authorization: Optional[str] = Header(None)) -> Optional[dict]:
    """Resolve the JWT bearer if present; otherwise return None instead of 401."""
    if not authorization or not authorization.strip():
        return None
    parts = authorization.split(None, 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        token = parts[1].strip()
        if token:
            return decode_token(token)
    return None


def require_role(*allowed_roles: str):
    allowed_set = {r.lower() for r in allowed_roles}

    def _check(current_user: dict = Depends(get_current_user)):
        raw_role = str(current_user.get("role", "farmer"))
        if raw_role.lower() not in allowed_set and raw_role not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail=f"Access denied. Required role: {', '.join(allowed_roles)}",
            )
        return current_user

    return _check

