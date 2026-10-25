#!/usr/bin/env python3
"""Scripted CarbonX disaster-recovery restore drill.

Executes the verifiable steps of ``docs/DR_RUNBOOK.md`` against a deployed
API (and, when the local machine holds backend credentials, the backup
utility), then prints a drill report and the manual PITR follow-ups:

1. Health gate      — GET /health: database.ready, migrations (checked/ok or
                      an explicit "NOT checked" label), redis, Earth Engine.
2. Ledger integrity — GET /ledger/{farm_id} -> ``verified: true`` (farm id
                      given with --farm-id or auto-discovered from the
                      public marketplace listings).
3. Local mirror     — the SHA-256 hash-ledger mirror file parses and is
                      counted (backend/data/ledger.json or
                      CARBONX_LEDGER_PATH); absence is a labelled warning.
4. Backup + verify  — run scripts/backup_data.py backup() and verify the
                      produced archive (skipped with --skip-backup, e.g. on
                      machines without backend credentials).

RTO/RPO figures and the quarterly schedule stay in docs/DR_RUNBOOK.md —
update the measured wall-clock there after real drills.

Usage:
    python scripts/dr_restore_drill.py --base https://staging-api.example.com
    OPS_BASE_URL=... python scripts/dr_restore_drill.py --farm-id <uuid>

Exit code: 0 = drill passed; 1 = at least one critical failure.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

TIMEOUT = 20
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.join(BASE_DIR, "backend")

FAILURES: list[str] = []
WARNINGS: list[str] = []
EVENTS: list[tuple[str, str]] = []


def _http_get(base: str, path: str) -> tuple[int, object]:
    req = urllib.request.Request(
        f"{base.rstrip('/')}{path}",
        headers={"Accept": "application/json", "User-Agent": "carbonx-dr-drill/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read().decode("utf-8", "replace"))
        except Exception:
            return exc.code, {}
    except Exception as exc:  # noqa: BLE001 - connection errors are drill failures
        raise RuntimeError(f"cannot reach {base}{path}: {exc}") from exc


def drill_health(base: str) -> dict:
    status, health = _http_get(base, "/health")
    if status != 200:
        FAILURES.append(f"health endpoint returned HTTP {status}")
        return {}

    database = health.get("database") or {}
    migrations = database.get("migrations") or {}

    if database.get("ready"):
        EVENTS.append(("health", "database.ready=true"))
    else:
        message = str(database.get("message") or "")
        if "not configured" in message.lower():
            WARNINGS.append(
                "database Supabase client NOT configured on this deployment — drill ran in demo/no-DB mode "
                "(restore of the real DB was not exercised)"
            )
        else:
            FAILURES.append("database.ready=false on a configured deployment — primary store outage")

    if migrations.get("checked"):
        if migrations.get("ok"):
            EVENTS.append(("health", "migrations_ok=true"))
        else:
            FAILURES.append(
                f"missing migrations: tables={migrations.get('missing_tables')} "
                f"columns={migrations.get('missing_columns')}"
            )
    else:
        WARNINGS.append("migrations NOT checked (schema probe unconfigured/unreachable) — reported, never silent")

    EVENTS.append(("health", f"redis.ready={bool((health.get('redis') or {}).get('ready'))}"))
    EVENTS.append(("health", f"earth_engine.ready={bool((health.get('earth_engine') or {}).get('ready'))}"))
    return {
        "database": database,
        "redis": health.get("redis"),
        "earth_engine": health.get("earth_engine"),
        "sms": health.get("sms"),
    }


def drill_ledger(base: str, farm_id: str | None) -> None:
    ledger_farm_id = farm_id
    if not ledger_farm_id:
        try:
            status, listings = _http_get(base, "/marketplace/listings?limit=5")
            if status == 200:
                rows = listings.get("listings") or []
                for row in rows:
                    candidate = row.get("farm_id")
                    if candidate:
                        ledger_farm_id = str(candidate)
                        break
                if ledger_farm_id:
                    EVENTS.append(
                        ("ledger", f"farm id auto-discovered from marketplace listings: {ledger_farm_id}")
                    )
        except Exception as exc:  # noqa: BLE001
            WARNINGS.append(f"could not auto-discover a farm id from listings: {exc}")

    if not ledger_farm_id:
        WARNINGS.append(
            "no farm id supplied or discovered — ledger chain verification skipped "
            "(pass --farm-id next run; DB-off demo deployments always attempt this step)"
        )
        return

    try:
        status, ledger = _http_get(base, f"/ledger/{ledger_farm_id}")
    except RuntimeError as exc:
        WARNINGS.append(f"ledger verification skipped — {exc}")
        return
    payload = ledger.get("ledger") if isinstance(ledger.get("ledger"), dict) else ledger
    verification = (ledger.get("verification") or (payload or {}).get("verification") or {}) if isinstance(ledger, dict) else {}
    verified = (ledger or {}).get("verified")
    if verified is None:
        verified = verification.get("valid")
    event_count = verification.get("length")
    if event_count is None and isinstance(payload, dict):
        event_count = len(payload.get("events") or [])
    if status == 200 and verified:
        if event_count == 0:
            WARNINGS.append(
                f"GET /ledger/{ledger_farm_id} -> chain verifies but holds 0 events on this deployment "
                "(no issuance yet — chain integrity click-tested only)"
            )
        else:
            EVENTS.append(
                (
                    "ledger",
                    f"GET /ledger/{ledger_farm_id} verified=true, events={event_count} (tamper-evident chain intact)",
                )
            )
    elif status == 200:
        FAILURES.append(
            f"GET /ledger/{ledger_farm_id} -> HTTP 200 but verified != true (chain broken or verification failed)"
        )
    elif "not found" in str((ledger.get("message") or ledger.get("detail") or "")).lower():
        WARNINGS.append(f"ledger has no events for farm '{ledger_farm_id}' yet — chain verification not exercised")
    else:
        FAILURES.append(f"GET /ledger/{ledger_farm_id} -> HTTP {status} (unexpected)")


def drill_local_mirror() -> None:
    path = os.environ.get("CARBONX_LEDGER_PATH") or os.path.join(BACKEND_DIR, "data", "ledger.json")
    if not os.path.exists(path):
        WARNINGS.append(
            f"local ledger mirror absent at {path} — acceptable when Supabase is the sole ledger store, "
            "but then the DB is the only copy (RPO depends entirely on Supabase PITR)"
        )
        return
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        chains = len(data) if isinstance(data, (dict, list)) else 0
        EVENTS.append(("mirror", f"local ledger mirror parses: {path} ({chains} chains) — backup copy exists"))
    except (OSError, ValueError) as exc:
        FAILURES.append(f"local ledger mirror present but unreadable: {path} ({exc})")


def drill_backup(output_dir: str, skip: bool) -> None:
    if skip:
        WARNINGS.append("backup step skipped (--skip-backup)")
        return
    try:
        if BACKEND_DIR not in sys.path:
            sys.path.insert(0, BACKEND_DIR)
        import backup_data  # noqa: PLC0415 - imported lazily so --skip-backup is dependency-free
    except Exception as exc:  # noqa: BLE001
        WARNINGS.append(
            f"backup utility not importable on this machine ({exc}) — run scripts/backup_data.py manually with backend credentials"
        )
        return
    try:
        archive = backup_data.backup(output_dir=output_dir)
    except Exception as exc:  # noqa: BLE001
        FAILURES.append(f"backup() failed: {exc}")
        return
    if not archive or not os.path.exists(archive):
        FAILURES.append(f"backup() returned no archive at {archive}")
        return
    if backup_data.verify_backup(archive):
        EVENTS.append(("backup", f"archive written and verified: {archive}"))
    else:
        FAILURES.append(f"backup archive failed verification: {archive}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    parser.add_argument(
        "--base",
        default=os.getenv("OPS_BASE_URL") or os.getenv("CARBONX_STAGE_BASE") or "http://127.0.0.1:8000",
        help="Deployed API base URL (env: OPS_BASE_URL / CARBONX_STAGE_BASE)",
    )
    parser.add_argument("--farm-id", default=None, help="Farm id for ledger chain verification (auto-discovered otherwise)")
    parser.add_argument("--output-dir", default=os.path.join(BASE_DIR, "backups"), help="Backup archive directory")
    parser.add_argument("--skip-backup", action="store_true", help="Skip the backup/verify step (e.g. CI without backend credentials)")
    args = parser.parse_args()

    print(f"\n=== CarbonX DR restore drill — {args.base} ===")
    try:
        health_state = drill_health(args.base)
    except RuntimeError as exc:
        print(f"[FAIL] health gate: {exc}")
        sys.exit(1)
    if not health_state:
        print("[FAIL] health gate unusable — aborting remaining steps")
        sys.exit(1)

    drill_ledger(args.base, args.farm_id)
    drill_local_mirror()
    drill_backup(args.output_dir, args.skip_backup)

    for scope, event in EVENTS:
        print(f"  [{scope:<7}] {event}")
    for warning in WARNINGS:
        print(f"  [warn ] {warning}")
    for failure in FAILURES:
        print(f"  [FAIL ] {failure}")

    print(
        "\nManual follow-ups (docs/DR_RUNBOOK.md):\n"
        "  - Supabase PITR restore into a SCRATCH project, then re-run this drill with --base <scratch-url>\n"
        "  - Record the measured wall-clock as your RTO in docs/DR_RUNBOOK.md (target: 1 hour)\n"
        "  - Reverse drill: delete the local mirror file, confirm Supabase remains source of truth\n"
        "  - Schedule: quarterly (next drill date is tracked in the runbook)"
    )
    print(f"\nsummary: {len(FAILURES)} critical failure(s), {len(WARNINGS)} warning(s), {len(EVENTS)} verified step(s)")
    sys.exit(1 if FAILURES else 0)


if __name__ == "__main__":
    main()
