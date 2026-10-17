"""Automatic 5-day NDVI monitoring: scheduled loop + /monitor/run trigger.

The heavy lifting lives in `perform_monitoring_cycle()` (pure, no FastAPI
dependencies) so the scheduler and the HTTP trigger share one implementation.
The previous code called the dependency-decorated endpoint directly from the
scheduler, which passed FastAPI `Depends` objects as arguments — a latent bug
that only stayed silent while MONITOR_SECRET was unset.

Multi-worker safety: the scheduler acquires a Redis lock (SET NX EX) so N
workers do not run the same cycle concurrently and double-write MONITOR
events. Without Redis every worker runs it — a single-process deployment has
exactly one scheduler, which is the correct semantics there.
"""
import asyncio
from datetime import datetime, timezone
from typing import Optional

import hmac
from fastapi import APIRouter, Depends, Header, HTTPException

from app import config as app_config
from app import redis_store
from app import supabase_db as db
from app.security import get_current_user_optional
from app.services import ledger

router = APIRouter()

NDVI_DROP_ALERT = app_config.NDVI_DROP_ALERT

# The lock must outlive one cycle (seconds) and expire long before the next
# one (days), so an hour is a safe upper bound.
_MONITOR_LOCK_NAME = "monitor_cycle"
_MONITOR_LOCK_TTL_SECONDS = 3600


def perform_monitoring_cycle() -> dict:
    """Run one monitoring pass over every live farm; returns the report."""
    if not db.is_ready():
        return {"success": False, "message": "Monitoring needs the database (demo mode has no live farms)"}
    try:
        sb = db._client()
        farms = (sb.table("farms").select("id,name,ndvi,status,last_monitor_ndvi,last_monitored_at").execute().data) or []
        checked = 0
        at_risk = []
        healthy = 0
        now_iso = datetime.now(timezone.utc).isoformat()
        for farm in farms:
            if str(farm.get("status") or "").lower() in ("pending",):
                continue
            checked += 1
            current = farm.get("ndvi")
            if current is None:
                continue
            current = float(current)
            last = farm.get("last_monitor_ndvi")
            drop = round(float(last) - current, 3) if last is not None else 0.0
            if last is not None and drop >= NDVI_DROP_ALERT:
                sb.table("farms").update({
                    "last_monitor_ndvi": current,
                    "last_monitored_at": now_iso,
                    "status": "Flagged",
                }).eq("id", farm["id"]).execute()
                ledger.append_event(farm["id"], "MONITOR", {
                    "risk": "ndvi_drop", "drop": drop,
                    "previous_ndvi": float(last), "current_ndvi": current,
                    "note": "Credits at-risk — routed to FPO review (drought/disease/abandonment possible)",
                })
                at_risk.append({
                    "farm_id": farm["id"], "name": farm.get("name"),
                    "drop": drop, "previous_ndvi": float(last), "current_ndvi": current,
                })
            else:
                sb.table("farms").update({
                    "last_monitor_ndvi": current,
                    "last_monitored_at": now_iso,
                }).eq("id", farm["id"]).execute()
                healthy += 1
        return {
            "success": True, "checked": checked, "healthy": healthy,
            "at_risk_count": len(at_risk), "at_risk": at_risk,
            "alert_threshold": NDVI_DROP_ALERT, "ran_at": now_iso,
        }
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.post("/monitor/run")
def run_monitoring_cycle(
    current_user: Optional[dict] = Depends(get_current_user_optional),
    x_monitor_secret: Optional[str] = Header(None),
):
    required_secret = app_config.MONITOR_SECRET
    if required_secret:
        valid_secret = bool(x_monitor_secret and hmac.compare_digest(
            str(x_monitor_secret), str(required_secret)
        ))
        if not valid_secret:
            if not (current_user and current_user.get("role") in ("fpo", "admin", "verifier")):
                raise HTTPException(
                    status_code=403,
                    detail="Monitoring requires the monitor secret or an FPO/admin session",
                )
    return perform_monitoring_cycle()


async def monitoring_loop():
    """Scheduler used by app startup when CARBONX_AUTO_MONITOR=1 (default)."""
    await asyncio.sleep(90)  # let the app finish booting first
    while True:
        try:
            if app_config.AUTO_MONITOR and redis_store.acquire_lock(
                    _MONITOR_LOCK_NAME, _MONITOR_LOCK_TTL_SECONDS):
                result = perform_monitoring_cycle()
                if result.get("success"):
                    print(f"[monitor] scheduled cycle: checked={result.get('checked')} "
                          f"at_risk={result.get('at_risk_count')}")
                else:
                    print(f"[monitor] scheduled cycle skipped: {result.get('message')}")
        except Exception as e:
            print(f"[monitor] scheduled cycle failed: {e}")
        await asyncio.sleep(app_config.MONITOR_INTERVAL_SECONDS)
