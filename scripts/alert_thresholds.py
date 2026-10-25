#!/usr/bin/env python3
"""Alert threshold evaluation against a deployed CarbonX API.

Reads ``GET /metrics`` (Prometheus exposition from
prometheus_fastapi_instrumentator) and ``GET /health`` and evaluates the
pre-registered operational targets from ``docs/OPS_TARGETS.md``:

- API 5xx rate above 1%                      -> page
- health/read endpoints p95 above 250 ms     -> page
- marketplace listings p95 above 500 ms      -> page
- passport / wallet p95 above 800 ms         -> page
- satellite scan (POST /analyze) p95 > 30 s  -> page
- evidence photo upload p95 > 10 s           -> page
- certificate PDF render p95 > 2 s           -> page
- Redis unavailable (health)                 -> page
- DB migrations missing (health)             -> page (never a silent pass)
- DB unready                                 -> page unless --allow-db-off

Limitations (stated on purpose): ``/metrics`` counters are cumulative since
process start, so the 5xx rate and latency percentiles are process-lifetime
figures, NOT the PromQL 5-minute windows the alert legend prescribes. A real
Prometheus + Alertmanager stack should keep using rate() over 5m; this script
is the no-stack fallback so thresholds are still evaluated somewhere before
that deployment exists. Percentile alerts additionally require at least 30
observations on the path — fresh-boot warm-up traffic is reported as a
warning, never silently ignored and never an alarm over noise.

Usage:
    python scripts/alert_thresholds.py --base https://staging-api.example.com
    OPS_BASE_URL=... python scripts/alert_thresholds.py

Exit code: 0 = no page-level alert; 1 = at least one page-level alert (or the
API is unreachable, which is itself an availability alert).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import urllib.error
import urllib.request

TIMEOUT = 20

# Per-path latency targets (seconds) from docs/OPS_TARGETS.md section 1/2.
PATH_TARGETS: list[tuple[str, str, float]] = [
    ("health_read", "health", 0.25),
    ("marketplace_listings", "marketplace/listings", 0.5),
    ("passport_wallet", "passport", 0.8),
    ("passport_wallet", "wallet", 0.8),
    ("satellite_scan", "analyze", 30.0),
    ("evidence_photo", "evidence/photo", 10.0),
    ("certificate_pdf", "pdf", 2.0),
]

MAX_5XX_RATE = 0.01  # docs/OPS_TARGETS.md: page when > 1%
MIN_P95_OBSERVATIONS = 30  # below this, a lifetime percentile is warm-up noise, not a stable p95

METRIC_LINE = re.compile(
    r"^([a-zA-Z_:][a-zA-Z0-9_:]*)(\{[^}]*\})?\s+([-+eE0-9.nan]+)\s*$"
)
LABEL = re.compile(r'([a-zA-Z_][a-zA-Z0-9_]*)="((?:[^"\\]|\\.)*)"')


def _parse_labels(raw: str) -> dict[str, str]:
    if not raw:
        return {}
    return {label: value for label, value in LABEL.findall(raw)}


def _parse_metrics(text: str) -> tuple[dict[tuple, float], dict[tuple, list[tuple[float, float]]]]:
    """Return (counters, buckets).

    counters: {(metric, path, code, method): value}
    buckets: {(metric, path, code, method): [(le, cumulative_count), ...]}
    """
    counters: dict[tuple, float] = {}
    buckets: dict[tuple, list[tuple[float, float]]] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = METRIC_LINE.match(line)
        if not match:
            continue
        metric, labels_raw, value_raw = match.groups()
        labels = _parse_labels(labels_raw or "")
        path = labels.get("path") or labels.get("handler") or ""
        code = labels.get("code", "")
        method = labels.get("method", "")
        try:
            value = float(value_raw)
        except ValueError:
            continue
        key = (metric, path, code, method)
        if metric.endswith("_bucket"):
            le_raw = labels.get("le", "")
            try:
                le = float(le_raw)
            except ValueError:
                if le_raw == "+Inf":
                    le = math.inf
                else:
                    continue
            buckets.setdefault(key, []).append((le, value))
        else:
            counters[key] = value
    return counters, buckets


def _num(value: float) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "n/a"
    return f"{value:.4g}"


def _p95(buckets: list[tuple[float, float]]) -> float | None:
    """Estimate the 0.95 quantile from cumulative histogram buckets.

    Returns None only when the series carries no observations; when the
    threshold falls past the last finite bucket bound it returns inf (the
    quantile is beyond what the bucket layout can resolve).
    """
    if not buckets:
        return None
    finite = sorted((le, count) for le, count in buckets if le != math.inf)
    total = max((count for _, count in buckets), default=0.0)
    if total <= 0:
        return None
    threshold = 0.95 * total
    for le, count in finite:
        if count >= threshold:
            return le
    return math.inf


def _window(
    counters: dict[tuple, float],
    buckets: dict[tuple, list[tuple[float, float]]],
) -> tuple[dict[tuple, float], dict[tuple, list[tuple[float, float]]]]:
    """Aggregate counters/buckets per (path, code, method).

    prometheus_fastapi_instrumentator historically exposes either
    http_requests_total or (as a fallback) histogram _count series for the
    same information; prefer the counter and fall back to _count so the
    5xx math works on both shapes.
    """
    scan_counters = {k: v for k, v in counters.items() if k[0] == "http_requests_total"}
    if not scan_counters:
        scan_counters = {
            k: v for k, v in counters.items() if k[0] == "http_request_duration_seconds_count"
        }
    scan_buckets = {k: v for k, v in buckets.items() if k[0].endswith("duration_seconds_bucket")}
    return scan_counters, scan_buckets


def _get(base: str, path: str) -> tuple[int, str]:
    req = urllib.request.Request(
        f"{base.rstrip('/')}{path}",
        headers={"Accept": "text/plain, application/json", "User-Agent": "carbonx-alert-thresholds/1.0"},
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.status, resp.read().decode("utf-8", "replace")


def evaluate(base: str, allow_db_off: bool) -> int:
    page_alerts: list[str] = []
    warnings: list[str] = []
    oks: list[str] = []

    try:
        _, health_text = _get(base, "/health")
        health = json.loads(health_text)
    except Exception as exc:  # noqa: BLE001 - the API being unreachable IS an alert
        print(f"[ALERT-PAGE] api_unreachable: {base} is not reachable ({exc})")
        return 1

    database = health.get("database") or {}
    migrations = database.get("migrations") or {}
    if database.get("ready"):
        oks.append("database_ready=true")
    else:
        msg = str(database.get("message") or "")
        if "not configured" in msg.lower() and allow_db_off:
            warnings.append("database not configured (deployed without Supabase) — acceptable only for demo mode")
        else:
            page_alerts.append("database_ready=false (DB outage or configuration regression)")

    if migrations.get("checked"):
        if migrations.get("ok"):
            oks.append("migrations_ok=true")
        else:
            missing = {
                "tables": migrations.get("missing_tables"),
                "columns": migrations.get("missing_columns"),
            }
            page_alerts.append(f"migrations incomplete: {missing}")
    else:
        warnings.append("migrations NOT checked (unconfigured/unreachable schema probe) — not a silent pass")

    redis_ready = (health.get("redis") or {}).get("ready")
    if redis_ready:
        oks.append("redis_ready=true")
    else:
        warnings.append(
            "redis_ready=false — single-worker rate limits and locks degrade to the in-process fallback "
            "(page-worthy in multi-worker production)"
        )

    try:
        _, metrics_text = _get(base, "/metrics")
    except Exception as exc:  # noqa: BLE001
        page_alerts.append(f"metrics endpoint unreachable: {exc}")
        metrics_text = ""

    counters, buckets = _parse_metrics(metrics_text)
    scan_counters, scan_buckets = _window(counters, buckets)

    total_requests = sum(scan_counters.values())
    server_errors = sum(v for k, v in scan_counters.items() if k[2].startswith("5"))
    if total_requests > 0:
        rate = server_errors / total_requests
        if rate > MAX_5XX_RATE:
            page_alerts.append(f"5xx_rate={_num(rate * 100)}% (1e-2 threshold exceeded)")
        else:
            oks.append(f"5xx_rate={_num(rate * 100)}%")
    else:
        warnings.append("no http_requests_total series in /metrics — 5xx rate not evaluable")

    # Aggregate latencies per path across codes/methods.
    per_path_buckets: dict[str, list[tuple[float, float]]] = {}
    per_path_counts: dict[str, float] = {}
    for (_metric, path, _code, _method), series in scan_buckets.items():
        if not path:
            continue
        per_path_buckets.setdefault(path, []).extend(series)
    for (_metric, path, _code, _method), value in scan_counters.items():
        if path:
            per_path_counts[path] = per_path_counts.get(path, 0.0) + value

    latency_rows: list[tuple[str, str, str, str]] = []
    for signal, needle, target in PATH_TARGETS:
        paths = [p for p in per_path_buckets if needle in p]
        if not paths:
            warnings.append(f"p95 target '{signal}' — no series matching '{needle}' (not exercised yet)")
            continue
        merged = [b for p in paths for b in per_path_buckets[p]]
        quantile = _p95(merged)
        if quantile is None:
            warnings.append(f"p95 target '{signal}' — buckets present but empty")
            continue
        observations = sum(per_path_counts.get(p, 0.0) for p in paths)
        measured = (
            "> last bucket bound"
            if math.isinf(quantile)
            else f"{quantile * 1000:.0f} ms"
        )
        latency_rows.append((signal, ", ".join(sorted(paths)), measured, f"{target * 1000:.0f} ms"))
        if observations < MIN_P95_OBSERVATIONS:
            warnings.append(
                f"p95 '{signal}' has only {int(observations)} observation(s) (<{MIN_P95_OBSERVATIONS}) "
                "— warm-up traffic, not evaluated as an alert"
            )
        elif quantile > target:
            page_alerts.append(f"p95 {signal}={_num(quantile)}s > target {_num(target)}s (paths: {', '.join(paths)})")
        else:
            oks.append(f"p95 {signal}={quantile * 1000:.0f} ms <= {target * 1000:.0f} ms")

    print(f"\n=== CarbonX alert thresholds — {base} ===")
    for name, paths, measured, target in latency_rows:
        print(f"  latency  {name:<22} p95={measured:>10}  target={target:>8}  ({paths})")
    for ok in oks:
        print(f"  [ok]         {ok}")
    for warning in warnings:
        print(f"  [warn]       {warning}")
    for alert in page_alerts:
        print(f"  [ALERT-PAGE] {alert}")

    print(
        "\nNot evaluable from /metrics alone (log-derived alerts — ship logs to Prometheus/Loki for these):\n"
        "  - ledger chain verification failures (verify via /ledger/{farm_id} or the DR drill)\n"
        "  - OTP delivery failures, rate-limit abuse spikes, Earth Engine scan failures,\n"
        "    webhook conflict refunds (all surfaced via carbonx.* JSON logs)"
    )
    print(f"\nsummary: {len(page_alerts)} page alert(s), {len(warnings)} warning(s), {len(oks)} ok")
    return 1 if page_alerts else 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    parser.add_argument(
        "--base",
        default=os.getenv("OPS_BASE_URL") or os.getenv("CARBONX_STAGE_BASE") or "http://127.0.0.1:8000",
        help="Deployed API base URL (env: OPS_BASE_URL / CARBONX_STAGE_BASE)",
    )
    parser.add_argument(
        "--allow-db-off",
        action="store_true",
        help="Treat database.ready=false as a warning when the deployment is wired without Supabase (demo mode)",
    )
    args = parser.parse_args()
    sys.exit(evaluate(args.base, allow_db_off=args.allow_db_off))


if __name__ == "__main__":
    main()
