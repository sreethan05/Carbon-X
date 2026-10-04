import os
import bcrypt
from jose import jwt, JWTError
from datetime import datetime, timedelta, timezone
from fastapi import Depends, Header, HTTPException
from typing import Optional

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "carbonx_dev_secret_change_in_production")
ALGORITHM = "HS256"

_BCRYPT_MAX_BYTES = 72


def hash_password(password: str) -> str:
    return bcrypt.hashpw(str(password).encode("utf-8")[:_BCRYPT_MAX_BYTES], bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(plain_password, hashed_password) -> bool:
    try:
        return bcrypt.checkpw(
            str(plain_password).encode("utf-8")[:_BCRYPT_MAX_BYTES],
            str(hashed_password).encode("utf-8"),
        )
    except (ValueError, TypeError):
        return False

def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    to_encode["exp"] = datetime.now(timezone.utc) + (expires_delta or timedelta(hours=72))
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def decode_token(token: str):
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None


def get_current_user(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = authorization.split(" ")[1]
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    return payload


def get_current_user_optional(authorization: Optional[str] = Header(None)):
    """Resolve the JWT bearer if present; otherwise return None instead of 401."""
    if authorization and authorization.startswith("Bearer "):
        payload = decode_token(authorization.split(" ")[1])
        if payload:
            return payload
    return None


def require_role(*allowed_roles):
    def _check(current_user: dict = Depends(get_current_user)):
        role = current_user.get("role", "farmer")
        if role not in allowed_roles:
            raise HTTPException(status_code=403, detail=f"Access denied. Required role: {', '.join(allowed_roles)}")
        return current_user
    return _check
