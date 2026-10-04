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

# Set by the HTTP middleware per request; included in every carbonx.* record.
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")


class JsonFormatter(logging.Formatter):
    def format(self, record):
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        rid = request_id_var.get("")
        if rid:
            payload["request_id"] = rid
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def setup_logging():
    if os.getenv("CARBONX_JSON_LOGS", "1").strip().lower() in ("0", "false", "no"):
        return
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger("carbonx")
    root.handlers = [handler]
    root.setLevel(logging.INFO)
    root.propagate = False
