"""WebSocket fanout for live ledger updates, with optional Redis bridging.

Single worker: ledger.append_event → in-process broadcast (bridged from the
sync writer thread onto the event loop by `ledger.set_main_loop`).

Multi-worker (uvicorn --workers N / multiple containers): the emitting worker
also publishes the event on Redis pub/sub; every worker runs a per-farm
subscriber task and forwards received events to its local WebSocket clients.
Events are deduplicated by (seq, hash) so the in-process copy and the Redis
echo never arrive twice.
"""
import asyncio
import json
import logging
from collections import deque

from fastapi import APIRouter, WebSocket

from app import redis_store
from app.services import ledger

logger = logging.getLogger("carbonx.ws")

router = APIRouter()

_subscribers: dict[str, set[WebSocket]] = {}
_listeners: dict[str, asyncio.Task] = {}
_delivered_ring: dict[str, deque] = {}
_delivered_set: dict[str, set] = {}

_DEDUPE_WINDOW = 64


def _mark_delivered(farm_id: str, event: dict) -> bool:
    """True when this exact event has not been delivered in this process yet."""
    seq, digest = event.get("seq"), event.get("hash")
    key = f"{seq}:{digest}" if digest else json.dumps(event, sort_keys=True, default=str)
    seen = _delivered_set.setdefault(farm_id, set())
    if key in seen:
        return False
    ring = _delivered_ring.setdefault(farm_id, deque())
    if len(ring) >= _DEDUPE_WINDOW:
        seen.discard(ring.popleft())
    ring.append(key)
    seen.add(key)
    return True


async def _deliver(farm_id: str, event: dict) -> None:
    if not _mark_delivered(farm_id, event):
        return
    subscribers = _subscribers.get(farm_id)
    if not subscribers:
        return
    msg = json.dumps(event, default=str)
    dead = set()
    for ws in list(subscribers):
        try:
            await ws.send_text(msg)
        except Exception:
            dead.add(ws)
    if dead:
        for ws in dead:
            subscribers.discard(ws)
        if not subscribers:
            _subscribers.pop(farm_id, None)
            _stop_listener_if_idle(farm_id)


async def broadcast(farm_id: str, event: dict) -> None:
    """In-process fanout; `ledger._publish` schedules this on the app loop."""
    await _deliver(farm_id, event)


async def _redis_listener(farm_id: str) -> None:
    """Forward Redis-published ledger events to this worker's subscribers."""
    import redis.asyncio as aioredis

    channel = redis_store.LEDGER_CHANNEL_PREFIX + farm_id
    while _subscribers.get(farm_id):
        if not await asyncio.to_thread(redis_store.redis_available):
            await asyncio.sleep(15)  # Redis not configured/down — re-check later
            continue
        client = None
        pubsub = None
        try:
            client = aioredis.from_url(
                redis_store.redis_url(), decode_responses=True, socket_timeout=5.0,
            )
            pubsub = client.pubsub()
            await pubsub.subscribe(channel)
            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                if not _subscribers.get(farm_id):
                    break
                try:
                    event = json.loads(message.get("data") or "{}")
                except ValueError:
                    continue
                await _deliver(farm_id, event)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("ledger redis listener for %s failed: %s", farm_id, e)
        finally:
            try:
                if pubsub is not None:
                    await pubsub.unsubscribe(channel)
                    await pubsub.aclose()
            except Exception:
                pass
            try:
                if client is not None:
                    await client.aclose()
            except Exception:
                pass
        await asyncio.sleep(5)  # backoff before resubscribing; loop exits when idle


def _ensure_listener(farm_id: str) -> None:
    task = _listeners.get(farm_id)
    if task is None or task.done():
        _listeners[farm_id] = asyncio.create_task(_redis_listener(farm_id))


def _stop_listener_if_idle(farm_id: str) -> None:
    if _subscribers.get(farm_id):
        return
    _subscribers.pop(farm_id, None)
    task = _listeners.pop(farm_id, None)
    if task is not None and not task.done():
        task.cancel()
    _delivered_ring.pop(farm_id, None)
    _delivered_set.pop(farm_id, None)


@router.websocket("/ws/ledger/{farm_id}")
async def websocket_ledger(ws: WebSocket, farm_id: str):
    await ws.accept()
    _subscribers.setdefault(farm_id, set()).add(ws)
    _ensure_listener(farm_id)
    try:
        verification = ledger.verify_chain(farm_id)
        chain = ledger.get_chain(farm_id)
        if chain:
            events_list = [{k: v for k, v in e.items() if not k.startswith("_")} for e in chain]
            await ws.send_text(json.dumps({
                "type": "snapshot",
                "farm_id": farm_id,
                "events": len(chain),
                "verified": verification.get("valid", False),
                "tail_hash": verification.get("tail_hash"),
                "types": [e["type"] for e in chain],
                "history": events_list,
            }, default=str))
        while True:
            await ws.receive_text()
    except Exception:
        pass
    finally:
        subs = _subscribers.get(farm_id)
        if subs is not None:
            subs.discard(ws)
            if not subs:
                _subscribers.pop(farm_id, None)
        _stop_listener_if_idle(farm_id)
