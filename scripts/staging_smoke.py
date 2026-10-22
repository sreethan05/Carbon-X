#!/usr/bin/env python3
"""Staging smoke checks for a deployed CarbonX backend.

Verifies the live-service behaviours that unit tests cannot observe:
health wiring, public redaction, validation labels, privacy policy, PDF/CSV
surface and Prometheus metrics. Run it against a staging deployment before
promoting to production.

Usage:
    python scripts/staging_smoke.py --base https://staging-api.example.com
    CARBONX_STAGE_BASE=... python scripts/staging_smoke.py

Optional authed checks (personalised surfaces):
    --token <JWT>   or CARBONX_STAGE_TOKEN

Exit code: 0 = all critical checks passed; 1 = at least one critical failure
(warnings do not affect the exit code but are listed).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any, Optional

TIMEOUT = 20
CRITICAL_PREFIX = "CRITICAL "

FAILURES: list[str] = []
WARNINGS: list[str] = []


def _get(base: str, path: str, token: Optional[str] = None, accept: str = "application/json") -> tuple[int, Any]:
    req = urllib.request.Request(
        f"{base.rstrip('/')}{path}",
        headers={
            "Accept": accept,
            "User-Agent": "carbonx-staging-smoke/1.0",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read().decode("utf-8", "replace")
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, raw
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8", "replace"))
        except Exception:
            return e.code, None
    except Exception as e:  # network / timeout
        return 0, None or {"success": False, "message": str(e)}


def fail(name: str, detail: str) -> None:
    FAILURES.append(f"{CRITICAL_PREFIX}{name}: {detail}")


def warn(name: str, detail: str) -> None:
    WARNINGS.append(f"Warning {name}: {detail}")


def ok(name: str, detail: str) -> None:
    print(f" [OK] {name}: {detail}")


def check_critical(name: str, condition: bool, ok_detail: str, bad_detail: str) -> None:
    if condition:
        ok(name, ok_detail)
    else:
        fail(name, bad_detail)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--base", default=os.getenv("CARBONX_STAGE_BASE", "http://localhost:8000"))
    parser.add_argument("--token", default=os.getenv("CARBONX_STAGE_TOKEN", ""))
    parser.add_argument("--skip-authed", action="store_true", help="skip token-authed checks")
    args = parser.parse_args()
    base = args.base.strip()
    token = (args.token or "").strip() or None

    print(f"CarbonX staging smoke -> {base}")

    # 1) Health wiring
    status, health = _get(base, "/health")
    health_ok = status == 200 and isinstance(health, dict) and health.get("success") in (True, None)
    check_critical("health", health_ok,
                   f"{status} {json.dumps({k: health.get(k) for k in ('database',)} if isinstance(health, dict) else {})}",
                   f"got status={status}")
    if isinstance(health, dict):
        db_state = health.get("database") or {}
        if isinstance(db_state, dict) and db_state.get("ready") is not True:
            warn("database.ready", "staging DB is not wired (demo/fallback mode)")
        if health.get("dev_otp"):
            fail("dev_otp", "dev OTP is exposed even in staging — misconfiguration")

    # 2) Validation labels are public and labelled proxy-unvalidated-ish
    status, val = _get(base, "/validation/status")
    valid_statuses = {
        "proxy_unvalidated", "proxy_insufficient_data",
        "field_validated_limited", "field_validation_failed",
    }
    check_critical(
        "validation/status",
        status == 200 and isinstance(val, dict) and val.get("status") in valid_statuses,
        f"{status}, status={val.get('status') if isinstance(val, dict) else None}",
        f"got status={status}",
    )

    # 3) Claims limits are published (labels + prohibited-claims allowlist)
    status, claims = _get(base, "/validation/claims")
    claims_ok = (
        status == 200
        and isinstance(claims, dict)
        and bool(claims.get("proxy_label"))
        and "unsupported_claims" in claims
    )
    check_critical(
        "validation/claims",
        claims_ok,
        f"{status}, proxy label + {len(claims.get('unsupported_claims') or [])} prohibited claim(s) published"
        if isinstance(claims, dict) else f"got status={status}",
        f"got status={status}",
    )

    # 4) Privacy policy is discoverable
    status, policy = _get(base, "/privacy/policy")
    check_critical(
        "privacy/policy",
        status == 200 and isinstance(policy, dict) and policy.get("policy_version"),
        f"{status}, version={policy.get('policy_version') if isinstance(policy, dict) else None}",
        f"got status={status}",
    )

    # 5) Public marketplace: no identity leak
    status, listings = _get(base, "/marketplace/listings?limit=20")
    leaked = None
    redacted = True
    if isinstance(listings, dict) and isinstance(listings.get("listings"), list):
        for row in listings["listings"]:
            if row.get("farmer_phone"):
                leaked = "farmer_phone"
                break
    check_critical(
        "marketplace_identity",
        status == 200 and leaked is None,
        f"{status}, {len(listings.get('listings') or [])} rows, no farmer identity in public rows"
        if isinstance(listings, dict) else f"got status={status}",
        f"got status={status}; leak={leaked}",
    )
    if isinstance(listings, dict) and listings.get("source") == "fallback":
        warn("marketplace.source", "serving fallback sample data — staging DB not wired")

    # 6) Public certificate CSV surface
    status, csv_text = _get(base, "/certificates/export.csv?limit=5", accept="text/csv")
    csv_ok = status == 200 and isinstance(csv_text, str) and csv_text.strip().startswith("id")
    check_critical("certificates_csv", csv_ok, f"{status} CSV header ok", f"got status={status}")

    # 7) Prometheus metrics reachable
    status, text = _get(base, "/metrics", accept="text/*")
    metrics_ok = status == 200 and isinstance(text, str) and ("carbonx" in text or "http_request" in text or "#" in text)
    check_critical("metrics", metrics_ok, f"{status} metrics endpoint", f"got status={status}")

    # 8) WebSocket route presence cannot be proven without an upgrade-capable
    # client (plain GET returns 404 for websocket routes); note only.
    status_ws = None
    try:
        req = urllib.request.Request(base.rstrip("/") + "/ws/ledger/stage-smoke")
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            status_ws = resp.status
    except urllib.error.HTTPError as e:
        status_ws = e.code
    except Exception:
        status_ws = None
    if status_ws in (400, 426):
        ok("ws_route", f"upgrade-aware response ({status_ws}) — websocket route present")
    elif status_ws == 404:
        print(" [note] ws_route: verify /ws/ledger/{farm_id} with a real WS client "
              "(plain HTTP GET cannot open a websocket; in-process pub-sub needs the app shell)")

    # 9) Authed checks
    if token and not args.skip_authed:
        for path in ("/privacy/consent", "/support/tickets", "/corporate/settings"):
            status, body = _get(base, path, token=token)
            if status in (200, 404):  # 404 tolerated for buyer-only settings
                ok(f"authed {path}", status)
            else:
                warn(f"authed {path}", f"status={status}")

    print("\n-- Staging smoke summary --")
    for w in WARNINGS:
        print(w)
    if FAILURES:
        for f in FAILURES:
            print(f)
        print(f"\nFailed: {len(FAILURES)} critical check(s).")
        return 1
    print("\nAll critical checks passed "
          + (f"(+{len(WARNINGS)} warning(s))" if WARNINGS else "")
          + ".")
    return 0


if __name__ == "__main__":
    sys.exit(main())
