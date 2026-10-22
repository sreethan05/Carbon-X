"""Centralized configuration constants for CarbonX backend.

All tunable constants live here so they can be imported without circular
dependencies and overridden via environment variables.
"""
import os


# ─── Environment helpers ───
def _env_bool(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    val = raw.strip().lower()
    if val in ("0", "false", "no", "off"):
        return False
    if val in ("1", "true", "yes", "on"):
        return True
    return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "").strip())
    except Exception:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "").strip())
    except Exception:
        return default


def _env_str(name: str, default: str) -> str:
    return os.getenv(name, "").strip() or default


ENVIRONMENT = _env_str("CARBONX_ENVIRONMENT", "development").lower()
IS_PRODUCTION = ENVIRONMENT in {"production", "prod"}


# ─── Core config ───
# Formula version for auditability — bump when crop factors or methodology change.
# Single source of truth: credit_engine imports this value.
FORMULA_VERSION = _env_str("CARBONX_FORMULA_VERSION", "vm0042-soilgrids-v1-r2-2026-10-04")

# NDVI drop threshold for 5-day monitoring (Sentinel-2 revisit)
NDVI_DROP_ALERT = _env_float("CARBONX_NDVI_DROP_ALERT", 0.15)

# ─── Security / Auth ───
# OTP settings
OTP_TTL_SECONDS = _env_int("CARBONX_OTP_TTL_SECONDS", 10 * 60)          # 10 minutes
OTP_MAX_ATTEMPTS = _env_int("CARBONX_OTP_MAX_ATTEMPTS", 5)
OTP_SEND_MAX_PER_WINDOW = _env_int("CARBONX_OTP_SEND_MAX", 3)           # per phone
OTP_SEND_WINDOW_SECONDS = _env_int("CARBONX_OTP_SEND_WINDOW", 600)      # 10 minutes

# Monitoring secret for external cron
MONITOR_SECRET = _env_str("CARBONX_MONITOR_SECRET", "")

# Force HTTPS (HSTS header)
FORCE_HTTPS = _env_bool("CARBONX_FORCE_HTTPS", False)

# ─── Payments ───
# Provider: "simulated" (default — no real money moves; settlement is immediate
# and labelled simulated) or "razorpay" (real orders once the key id + secret
# are configured). Unknown values degrade to "simulated" with a warning.
PAYMENTS_PROVIDER = _env_str("CARBONX_PAYMENTS_PROVIDER", "simulated")
ALLOW_SIMULATED_SETTLEMENT = _env_bool("CARBONX_ALLOW_SIMULATED_SETTLEMENT", False)
RAZORPAY_KEY_ID = _env_str("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = _env_str("RAZORPAY_KEY_SECRET", "")
RAZORPAY_WEBHOOK_SECRET = _env_str("RAZORPAY_WEBHOOK_SECRET", "")

# ─── Earth Engine / Satellite ───
# Cache TTL for /analyze results (same polygon + crop = identical median composite)
ANALYZE_CACHE_TTL_SECONDS = _env_int("CARBONX_ANALYZE_CACHE_TTL", 600)  # 10 minutes

# Maximum area for a single scan (prevents quota abuse on huge polygons)
ANALYZE_MAX_AREA_HECTARES = _env_int("CARBONX_ANALYZE_MAX_AREA_HA", 10000)

# Auto-enable 5-day in-process monitoring scheduler
AUTO_MONITOR = _env_bool("CARBONX_AUTO_MONITOR", True)

# ─── PDF / Certificate ───
# In-memory cache for generated PDF certificates (immutable after retirement)
PDF_CACHE_MAX_ENTRIES = _env_int("CARBONX_PDF_CACHE_MAX", 512)

# ─── JSON Logging ───
JSON_LOGS = _env_bool("CARBONX_JSON_LOGS", True)

# ─── CORS ───
CORS_ORIGINS = _env_str("CORS_ORIGINS", "http://localhost:5000,http://localhost:5173,http://localhost:3000")  # port 5000 is the frontend origin

# ─── GEE Project ───
GEE_PROJECT = _env_str("GEE_PROJECT", "carbonx-507617")

# ─── Monitoring scheduler interval ───
MONITOR_INTERVAL_SECONDS = 5 * 24 * 60 * 60  # 5 days (Sentinel-2 revisit)

# ─── Redis ───
REDIS_URL = _env_str("REDIS_URL", "redis://localhost:6379/0")

# ─── Blockchain / Amoy (optional) ───
AMOY_RPC_URL = _env_str("AMOY_RPC_URL", "https://rpc-amoy.polygon.technology")
AMOY_CHAIN_ID = _env_int("AMOY_CHAIN_ID", 80002)


# ─── Production Invariant Enforcement ───
def validate_production_configuration() -> None:
    """Enforce strict production invariants; block process startup on insecure settings."""
    if not IS_PRODUCTION:
        return

    # 1. JWT Secret Key
    jwt_secret = os.getenv("JWT_SECRET_KEY", "").strip()
    if not jwt_secret:
        raise RuntimeError("CRITICAL PRODUCTION CONFIG ERROR: JWT_SECRET_KEY must be set in production")
    if len(jwt_secret) < 32:
        raise RuntimeError("CRITICAL PRODUCTION CONFIG ERROR: JWT_SECRET_KEY must be at least 32 characters long")
    if jwt_secret.lower() in ("secret", "change_me", "development", "jwt_secret_key_here"):
        raise RuntimeError("CRITICAL PRODUCTION CONFIG ERROR: JWT_SECRET_KEY is using an insecure placeholder")

    # 2. Dev OTP setting
    if _env_bool("CARBONX_ALLOW_DEV_OTP", False):
        raise RuntimeError("CRITICAL PRODUCTION CONFIG ERROR: CARBONX_ALLOW_DEV_OTP cannot be enabled in production")

    # 3. Simulated settlement with live Razorpay
    if PAYMENTS_PROVIDER == "razorpay" and ALLOW_SIMULATED_SETTLEMENT:
        raise RuntimeError("CRITICAL PRODUCTION CONFIG ERROR: CARBONX_ALLOW_SIMULATED_SETTLEMENT cannot be enabled with live Razorpay")

    # 4. Supabase DB configuration
    sb_url = os.getenv("SUPABASE_URL", "").strip()
    sb_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not sb_url or not sb_key:
        raise RuntimeError("CRITICAL PRODUCTION CONFIG ERROR: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in production")

    # 5. Wildcard CORS
    origins = [o.strip() for o in CORS_ORIGINS.split(",") if o.strip()]
    if "*" in origins:
        raise RuntimeError("CRITICAL PRODUCTION CONFIG ERROR: CORS_ORIGINS cannot contain wildcard '*' in production")

