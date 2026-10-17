import os
import re
import secrets
import bcrypt
import logging
from jose import jwt, JWTError
from datetime import datetime, timedelta, timezone
from fastapi import Depends, Header, HTTPException
from typing import Optional

logger = logging.getLogger("carbonx.security")

_DEFAULT_SECRET = "carbonx_dev_secret_change_in_production"
ALGORITHM = "HS256"
_BCRYPT_MAX_BYTES = 72


def _get_secret_key() -> str:
    """Retrieve the active JWT secret key, allowing runtime environment overrides."""
    secret = os.getenv("JWT_SECRET_KEY", "").strip()
    return secret or _DEFAULT_SECRET


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
    to_encode["exp"] = now + (expires_delta or timedelta(hours=72))
    return jwt.encode(to_encode, _get_secret_key(), algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    if not token or not isinstance(token, str):
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
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
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

