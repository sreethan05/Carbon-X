"""Centralized platform constants (#15 in the audit).

Single import point for tunables that were previously scattered across
main.py and services. Values here are defaults — environment variables
still win where the call site reads them.
"""

# OTP abuse brake
OTP_SEND_WINDOW_SECONDS = 600          # 10 minutes
OTP_SEND_MAX_PER_WINDOW = 3
OTP_TTL_SECONDS = 10 * 60
OTP_MAX_ATTEMPTS = 5

# Monitoring (5-day Sentinel-2 revisit cycle)
MONITOR_INTERVAL_SECONDS = 5 * 24 * 60 * 60
NDVI_DROP_ALERT = 0.15

# Carbon math provenance — bump when credit_engine's equations change;
# every ledger ISSUE snapshot and scan_estimate records this version.
FORMULA_VERSION = "vm0042-aligned-2026-10-04"

# /analyze guards
ANALYZE_CACHE_TTL_SECONDS = 600
ANALYZE_MAX_AREA_HECTARES = 10_000     # EE quota guard for mis-drawn regions
EE_BACKOFF_ATTEMPTS = 3
EE_BACKOFF_BASE_DELAY = 1.5

# Marketplace
PDF_CACHE_MAX_ENTRIES = 128
