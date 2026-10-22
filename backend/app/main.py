"""CarbonX API composition root.

Route implementations live in app/routes/*; this module wires the app
together: env loading, CORS, security/trace headers, structured logging,
metrics, the uniform error envelope, startup tasks, health endpoints and
router registration. Keep this file thin — behavior belongs in the routers.
"""
from pathlib import Path

from dotenv import load_dotenv

APP_DIR = Path(__file__).resolve().parent
BACKEND_DIR = APP_DIR.parent
ROOT_DIR = BACKEND_DIR.parent

load_dotenv(ROOT_DIR / ".env", override=True)
load_dotenv(BACKEND_DIR / ".env", override=True)

import asyncio
from contextlib import asynccontextmanager
import logging
import re

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import config as app_config
from app import gee_runtime
from app import redis_store
from app import supabase_db as db
from app.logging_setup import request_id_var, setup_logging

setup_logging()
logger = logging.getLogger("carbonx.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown: validate production config, ledger loop bridge + the 5-day monitor scheduler."""
    app_config.validate_production_configuration()
    from app.services import ledger as _ledger
    _ledger.set_main_loop(asyncio.get_running_loop())
    monitor_task = None
    if db.is_ready() and app_config.AUTO_MONITOR:
        from app.routes.monitor_router import monitoring_loop
        monitor_task = asyncio.create_task(monitoring_loop())
        print("[monitor] 5-day scheduler armed (first cycle in 90s)")
    try:
        yield
    finally:
        if monitor_task is not None:
            monitor_task.cancel()
            try:
                await monitor_task
            except asyncio.CancelledError:
                pass
        _ledger.set_main_loop(None)


app = FastAPI(
    title="CarbonX API",
    version="1.0.0",
    lifespan=lifespan,
    description="Satellite-verified carbon + biodiversity credits for Indian smallholder farmers. "
                "Trust pipeline: register -> verify (Stage 1) -> calculate (Stage 2) -> anchor -> "
                "monitor -> sell/split/retire. See docs/MRV_METHODOLOGY.md for the equations.",
    openapi_tags=[
        {"name": "auth", "description": "Phone-OTP registration/login, JWT sessions"},
        {"name": "farms", "description": "Boundary registration, satellite analysis, Trust Engine"},
        {"name": "marketplace", "description": "Listings, matching, escrow purchases, conditional splits"},
        {"name": "trust", "description": "Hash ledger, certificates, monitoring, ground-truth calibration"},
        {"name": "ops", "description": "Operational snapshots and calibration tooling (no PII)"},
        {"name": "fpo", "description": "FPO desk: pending/flagged farms, farmer roster, credit pooling"},
        {"name": "corporate", "description": "Corporate buyer authentication"},
        {"name": "evidence", "description": "Practice-photo + geotag capture feeding passport evidence quality"},
        {"name": "payments", "description": "Checkout + provider webhooks (simulated default, Razorpay-ready)"},
    ],
)

cors_origins = [origin.strip() for origin in app_config.CORS_ORIGINS.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-API-Version"],
)


# ── Security headers + request-ID + version header ──
_VALID_REQUEST_ID = re.compile(r"^[a-zA-Z0-9_\-]{1,64}$")

@app.middleware("http")
async def security_and_trace_headers(request, call_next):
    import uuid as _uuid
    incoming_rid = request.headers.get("X-Request-ID", "").strip()
    if incoming_rid and _VALID_REQUEST_ID.match(incoming_rid):
        request_id = incoming_rid
    else:
        request_id = _uuid.uuid4().hex[:16]
    request_id_var.set(request_id)
    try:
        response = await call_next(request)
    except Exception as exc:
        logger.error(
            "Unhandled exception in request pipeline %s %s: %s",
            request.method, request.url.path, exc, exc_info=True,
        )
        response = JSONResponse(
            status_code=500,
            content={"success": False, "message": "Internal server error", "code": "INTERNAL_ERROR"},
        )
    response.headers["X-Request-ID"] = request_id
    response.headers["X-API-Version"] = "1.0.0"
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; img-src 'self' data: https:; script-src 'self'; style-src 'self' 'unsafe-inline'",
    )
    if app_config.FORCE_HTTPS:
        response.headers.setdefault("Strict-Transport-Security", "max-age=63072000; includeSubDomains")
    return response


# ── Prometheus metrics ──
try:
    from prometheus_fastapi_instrumentator import Instrumentator
    Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)
except Exception as _e:  # pragma: no cover
    print(f"metrics disabled: {_e}")


# ── Uniform error envelope: every failure returns {success:false,message,code} ──
@app.exception_handler(RequestValidationError)
async def validation_exception_envelope(request, exc):
    msgs = []
    for err in exc.errors():
        loc = ".".join(str(x) for x in err.get("loc", []) if x != "body")
        msgs.append(f"{loc}: {err.get('msg', 'invalid')}" if loc else str(err.get("msg", "invalid")))
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "message": "; ".join(msgs) or "Validation failed",
            "code": "VALIDATION_ERROR",
        },
    )

_HTTP_ERROR_CODES = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    422: "UNPROCESSABLE_ENTITY",
    429: "RATE_LIMITED",
    500: "INTERNAL_ERROR",
    502: "BAD_GATEWAY",
    503: "SERVICE_UNAVAILABLE",
}

@app.exception_handler(StarletteHTTPException)
async def http_exception_envelope(request, exc):
    detail = exc.detail if isinstance(exc.detail, str) else "Request failed"
    if isinstance(detail, list):
        detail = "; ".join(d.get("msg", str(d)) for d in detail if isinstance(d, dict))
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "message": detail,
            "code": _HTTP_ERROR_CODES.get(exc.status_code, f"HTTP_{exc.status_code}"),
        },
    )

@app.exception_handler(Exception)
async def unhandled_exception_envelope(request, exc):
    logger.error("Unhandled exception on %s %s: %s", request.method, request.url.path, exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"success": False, "message": "Internal server error", "code": "INTERNAL_ERROR"},
    )


# ── Health check helpers ──
def _sms_ready() -> bool:
    try:
        from app.phone_service import sms_configured
        return sms_configured()
    except Exception:
        return False


def _twilio_ready() -> bool:
    return _sms_ready()


# ── Health endpoints ──
@app.get("/")
def root():
    return {
        "message": "CarbonX API running",
        "version": "1.0.0",
        "supabase": db.is_ready(),
        "sms": _sms_ready(),
        "twilio": _twilio_ready(),
        "earth_engine": gee_runtime.earth_engine_ready,
        "redis": redis_store.redis_available(),
    }


@app.get("/health")
def health():
    database = db.health_check()
    return {
        "success": database["ready"],
        "database": database,
        "sms": {"ready": _sms_ready(), "provider": "Textplate"},
        "twilio": {"ready": _twilio_ready(), "provider": "Textplate"},
        "earth_engine": {"ready": gee_runtime.earth_engine_ready},
        "redis": {"ready": redis_store.redis_available()},
    }


# ── Routers ──
from app.routes.analyze_router import router as analyze_router
from app.routes.monitor_router import router as monitor_router
from app.routes.ws_router import router as ws_router
from app.routes.auth_router import router as auth_router
from app.routes.evidence_router import router as evidence_router
from app.routes.farms_router import router as farms_router
from app.routes.marketplace_router import router as marketplace_router
from app.routes.payments_router import router as payments_router
from app.routes.trust_router import router as trust_router
from app.routes.ops_router import router as ops_router
from app.routes.validation_router import router as validation_router
from app.routes.privacy_router import router as privacy_router, ops_router as ops_privacy_router
from app.routes.fpo_router import router as fpo_router
from app.routes.corporate_router import router as corporate_router
from app.routes.support_router import router as support_router

from app.voice_agent.voice_routes import router as voice_router

app.include_router(analyze_router)
app.include_router(monitor_router)
app.include_router(ws_router)
app.include_router(auth_router)
app.include_router(auth_router, prefix="/auth")
app.include_router(evidence_router)
app.include_router(farms_router)
app.include_router(marketplace_router)
app.include_router(payments_router)
app.include_router(trust_router)
app.include_router(ops_router)
app.include_router(validation_router)
app.include_router(privacy_router)
app.include_router(ops_privacy_router)
app.include_router(fpo_router)
app.include_router(corporate_router)
app.include_router(support_router)
app.include_router(voice_router)
