"""Structured logging for CarbonX services.

Call `setup_logging()` once at startup (main.py does when not disabled):
carbonx.* loggers emit single-line JSON — parseable by any log aggregator.
Request correlation: the HTTP middleware stamps X-Request-ID; pass it into
log calls where available (uvicorn access logs carry it per request).
"""
import contextvars
import json
import logging
import os
import re
from typing import Any

# Set by the HTTP middleware per request; included in every carbonx.* record.
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")

# ─── PII Masking Patterns ───
_PASSWORD_KEY_PATTERN = re.compile(
    r'(?i)(?P<prefix>[\'"]?(?:password|passwd|pwd|secret|api_key|access_token|auth_token|refresh_token|password_hash)[\'"]?\s*(?:[:=]|is|\s)\s*[\'"]?)(?P<val>[^\s\'",}{\]]+)(?P<suffix>[\'"]?)'
)

_LABELED_PHONE_PATTERN = re.compile(
    r'(?i)(?P<prefix>[\'"]?(?:phone|mobile|cell|tel|phone_number|owner_phone|farmer_phone|officer_phone)[\'"]?\s*(?:[:=]|is|\s)\s*[\'"]?)(?P<val>\+?\d[\d\s\-()]{6,14}\d)(?P<suffix>[\'"]?)'
)

_STANDALONE_PHONE_PATTERN = re.compile(
    r'(?<![a-zA-Z0-9+])(?:\+91[\-\s]?|0)?[6-9](?:\d{9}|\d{4}[\-\s]\d{5}|\d{2}[\-\s]\d{3}[\-\s]\d{4})(?![a-zA-Z0-9])'
)

_AADHAAR_PATTERN = re.compile(
    r'(?<![a-zA-Z0-9+])(?:\d{4}[\s\-]\d{4}[\s\-]\d{4}|\d{12})(?![a-zA-Z0-9])'
)


_SENSITIVE_KEY_PATTERN = re.compile(
    r'(?i)(?:password|passwd|pwd|secret|api_key|access_token|auth_token|refresh_token|password_hash)'
)
_PHONE_KEY_PATTERN = re.compile(
    r'(?i)(?:phone|mobile|cell|tel|phone_number|owner_phone|farmer_phone|officer_phone)'
)
_AADHAAR_KEY_PATTERN = re.compile(
    r'(?i)(?:aadhaar)'
)


def _mask_password_match(m: re.Match) -> str:
    prefix = m.group("prefix")
    suffix = m.group("suffix")
    return f"{prefix}********{suffix}"


def _mask_labeled_phone_match(m: re.Match) -> str:
    prefix = m.group("prefix")
    val = m.group("val")
    suffix = m.group("suffix")
    digits = re.sub(r"\D", "", val)
    last4 = digits[-4:] if len(digits) >= 4 else digits
    if "+91" in val:
        formatted = f"+91******{last4}"
    elif val.strip().startswith("0") and len(digits) == 11:
        formatted = f"0******{last4}"
    else:
        formatted = f"******{last4}"
    return f"{prefix}{formatted}{suffix}"


def _mask_standalone_phone_match(m: re.Match) -> str:
    raw = m.group(0)
    digits = re.sub(r"\D", "", raw)
    last4 = digits[-4:]
    if raw.startswith("+91-"):
        return f"+91-******{last4}"
    elif raw.startswith("+91 "):
        return f"+91 ******{last4}"
    elif raw.startswith("+91"):
        return f"+91******{last4}"
    elif raw.startswith("0") and len(digits) == 11:
        return f"0******{last4}"
    return f"******{last4}"


def _mask_aadhaar_match(m: re.Match) -> str:
    raw = m.group(0)
    digits = re.sub(r"\D", "", raw)
    last4 = digits[-4:]
    return f"XXXX-XXXX-{last4}"


def mask_pii(val: Any, key: Any = None) -> Any:
    """Mask sensitive PII (passwords, phone numbers, Aadhaar numbers)."""
    if key is not None:
        key_str = str(key)
        if _SENSITIVE_KEY_PATTERN.search(key_str):
            return "********"
        if _PHONE_KEY_PATTERN.search(key_str) and isinstance(val, (str, int)):
            sval = str(val)
            digits = re.sub(r"\D", "", sval)
            last4 = digits[-4:] if len(digits) >= 4 else digits
            if "+91" in sval:
                return f"+91******{last4}"
            elif sval.strip().startswith("0") and len(digits) == 11:
                return f"0******{last4}"
            return f"******{last4}"
        if _AADHAAR_KEY_PATTERN.search(key_str) and isinstance(val, (str, int)):
            digits = re.sub(r"\D", "", str(val))
            if len(digits) == 12:
                return f"XXXX-XXXX-{digits[-4:]}"

    if isinstance(val, str):
        # 1. Passwords / Secrets
        val = _PASSWORD_KEY_PATTERN.sub(_mask_password_match, val)
        # 2. Labeled phone numbers
        val = _LABELED_PHONE_PATTERN.sub(_mask_labeled_phone_match, val)
        # 3. Standalone phone numbers
        val = _STANDALONE_PHONE_PATTERN.sub(_mask_standalone_phone_match, val)
        # 4. Aadhaar numbers (12-digit)
        val = _AADHAAR_PATTERN.sub(_mask_aadhaar_match, val)
        return val
    elif isinstance(val, dict):
        return {k: mask_pii(v, key=k) for k, v in val.items()}
    elif isinstance(val, list):
        return [mask_pii(x) for x in val]
    return val


class JsonFormatter(logging.Formatter):
    def format(self, record):
        try:
            msg = record.getMessage()
        except Exception:
            msg = str(record.msg)

        msg = mask_pii(msg)

        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": msg,
        }
        rid = getattr(record, "request_id", None) or request_id_var.get("")
        if rid:
            payload["request_id"] = str(rid)
        if record.exc_info:
            payload["exc"] = mask_pii(self.formatException(record.exc_info))
        if getattr(record, "stack_info", None):
            payload["stack"] = mask_pii(self.formatStack(record.stack_info))

        # Include custom extra attributes from record if present, with PII masked
        standard_attrs = {
            "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
            "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
            "created", "msecs", "relativeCreated", "thread", "threadName",
            "processName", "process", "message", "request_id"
        }
        for k, v in record.__dict__.items():
            if k not in standard_attrs and not k.startswith("_"):
                payload[k] = mask_pii(v, key=k)

        return json.dumps(payload, default=str)


def setup_logging():
    if os.getenv("CARBONX_JSON_LOGS", "1").strip().lower() in ("0", "false", "no"):
        return
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger("carbonx")
    root.handlers = [handler]
    log_level = os.getenv("CARBONX_LOG_LEVEL", "INFO").strip().upper()
    root.setLevel(getattr(logging, log_level, logging.INFO))
    root.propagate = False

