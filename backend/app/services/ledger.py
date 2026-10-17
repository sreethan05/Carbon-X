"""Tamper-evident SHA-256 event ledger (hash chain), blockchain-free.

Every consequential event about a farm's credits (ISSUE, LIST, SALE, SPLIT,
RETIRE, MONITOR) is appended as a record whose hash covers its content plus
the previous record's hash — an internal chain anyone can recompute:

    hash = sha256(seq | entity_id | type | canonical_json(payload) | prev_hash)

Storage: Supabase `ledger_events` table when the database is configured
(payload_json holds the exact canonical text the hash covers, so verification
is byte-exact); otherwise a local JSON file (backend/data/ledger.json,
gitignored; CARBONX_LEDGER_PATH overrides). Existing local chains migrate to
Supabase automatically on first use after the DB comes online.
"""
import hashlib
import json
import logging
import os

logger = logging.getLogger("carbonx.ledger")
from datetime import datetime, timezone
from threading import RLock

_LOCK = RLock()
_MIGRATED = False
# In-process pub/sub for live ledger push (#WS); ws_router bridges the same
# events across workers via Redis pub/sub when REDIS_URL is configured.
_ENTITY_LISTENERS: dict = {}
_main_loop = None


def set_main_loop(loop) -> None:
    """Capture the app's event loop (called from main's startup) so sync
    ledger writes can bridge broadcasts onto it from worker threads."""
    global _main_loop
    _main_loop = loop


def subscribe(entity_id: str, callback) -> None:
    """Register callback(event_dict) fired after every append for entity."""
    with _LOCK:
        _ENTITY_LISTENERS.setdefault(entity_id, set()).add(callback)


def unsubscribe(entity_id: str, callback) -> None:
    with _LOCK:
        listeners = _ENTITY_LISTENERS.get(entity_id)
        if listeners is not None:
            listeners.discard(callback)
            if not listeners:
                _ENTITY_LISTENERS.pop(entity_id, None)


def _publish(entity_id: str, event: dict) -> None:
    for cb in list(_ENTITY_LISTENERS.get(entity_id, [])):
        try:
            cb(event)
        except Exception as e:  # a dead websocket must never break the ledger
            logger.warning("ledger listener failed: %s", e)
    # Broadcast to WebSocket subscribers (ws_router registers a loop at
    # startup). append_event runs in sync/worker-thread contexts, so the
    # coroutine must be bridged with run_coroutine_threadsafe — a bare
    # asyncio.create_task here would raise (no loop in this thread) and the
    # broadcast would silently never happen.
    try:
        import asyncio
        if _main_loop is not None and _main_loop.is_running():
            from app.routes.ws_router import broadcast
            asyncio.run_coroutine_threadsafe(broadcast(entity_id, event), _main_loop)
    except Exception:
        pass  # main not loaded yet (e.g., during tests) or app shutting down
    # Cross-worker fanout: other workers subscribe to this channel and
    # forward the event to their own WebSocket clients (no-op without Redis
    # — the in-process broadcast above already served this worker).
    try:
        from app import redis_store
        redis_store.publish_ledger_event(entity_id, event)
    except Exception:
        pass

_CHAINS: dict = {}
_DEFAULT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
    "ledger.json",
)
_PATH = os.getenv("CARBONX_LEDGER_PATH", _DEFAULT_PATH)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical(payload) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def _event_hash(seq: int, entity_id: str, event_type: str, payload_json: str, prev_hash: str) -> str:
    material = f"{seq}|{entity_id}|{event_type}|{payload_json}|{prev_hash}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _load_file():
    if os.path.exists(_PATH):
        try:
            with open(_PATH, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                _CHAINS.update(data)
        except (OSError, ValueError):
            pass


def _persist_file():
    try:
        os.makedirs(os.path.dirname(_PATH), exist_ok=True)
        tmp_path = f"{_PATH}.tmp.{os.getpid()}"
        with open(tmp_path, "w", encoding="utf-8") as fh:
            json.dump(_CHAINS, fh, indent=1, default=str)
        os.replace(tmp_path, _PATH)
    except OSError:
        pass  # in-memory only if the disk refuses


_load_file()


def _sb():
    from app import supabase_db as db

    return db._client() if db.is_ready() else None


def _migrate_local_to_db(sb):
    """Push local-file chains into Supabase, preserving seq/hashes.

    Retries on the next call until it succeeds (a failed attempt must not
    latch the flag, or pre-grant chains never migrate).
    """
    global _MIGRATED
    with _LOCK:
        if _MIGRATED or not _CHAINS:
            _MIGRATED = True
            return
        chains_snapshot = {k: list(v) for k, v in _CHAINS.items()}
    try:
        rows = []
        for entity_id, chain in chains_snapshot.items():
            existing = (
                sb.table("ledger_events").select("seq").eq("entity_id", entity_id).execute().data
            ) or []
            have = {r["seq"] for r in existing}
            for e in chain:
                if e["seq"] in have:
                    continue
                rows.append({
                    "entity_id": entity_id,
                    "seq": e["seq"],
                    "event_type": e["type"],
                    "payload": e["payload"],
                    "payload_json": _canonical(e["payload"]),
                    "ts": e["ts"],
                    "prev_hash": e["prev_hash"],
                    "hash": e["hash"],
                })
        if rows:
            # on_conflict + ignore_duplicates makes concurrent instances safe:
            # a losing race simply no-ops instead of erroring.
            sb.table("ledger_events").upsert(
                rows, on_conflict="entity_id,seq", ignore_duplicates=True
            ).execute()
        with _LOCK:
            _MIGRATED = True
    except Exception as e:
        # NOTE: deliberately do NOT latch _MIGRATED on failure — retry next call.
        logger.warning("local→db migration deferred: %s", e)


def append_event(entity_id: str, event_type: str, payload: dict, ts: str = "") -> dict:
    """Append an event to the entity's chain and return the stored record.

    When Supabase is reachable, seq/prev_hash are read from the DB chain so
    local file state can never fork the numbering.
    """
    with _LOCK:
        payload_json = _canonical(payload)
        sb = _sb()
        if sb:
            _migrate_local_to_db(sb)
            try:
                rows = (
                    sb.table("ledger_events")
                    .select("seq,hash")
                    .eq("entity_id", entity_id)
                    .order("seq", desc=False)
                    .execute()
                    .data
                ) or []
                seq = len(rows)
                prev = rows[-1]["hash"] if rows else "0" * 64
                event = {
                    "seq": seq,
                    "entity_id": entity_id,
                    "type": event_type,
                    "payload": payload,
                    "ts": ts or _now(),
                    "prev_hash": prev,
                }
                event["hash"] = _event_hash(seq, entity_id, event_type, payload_json, prev)
                sb.table("ledger_events").insert({
                    "entity_id": entity_id,
                    "seq": seq,
                    "event_type": event_type,
                    "payload": payload,
                    "payload_json": payload_json,
                    "ts": event["ts"],
                    "prev_hash": prev,
                    "hash": event["hash"],
                }).execute()
                _CHAINS.setdefault(entity_id, []).append(event)  # keep file mirror in sync
                _persist_file()
                _publish(entity_id, event)
                return event
            except Exception as e:
                logger.error("DB append failed (%s) — writing to local file", e)

        chain = _CHAINS.setdefault(entity_id, [])
        prev = chain[-1]["hash"] if chain else "0" * 64
        seq = len(chain)
        event = {
            "seq": seq,
            "entity_id": entity_id,
            "type": event_type,
            "payload": payload,
            "ts": ts or _now(),
            "prev_hash": prev,
        }
        event["hash"] = _event_hash(seq, entity_id, event_type, payload_json, prev)
        chain.append(event)
        _persist_file()
        _publish(entity_id, event)
        return event


def get_chain(entity_id: str) -> list:
    """Events for an entity, oldest first (Supabase preferred, file fallback)."""
    sb = _sb()
    if sb:
        _migrate_local_to_db(sb)
        try:
            rows = (
                sb.table("ledger_events")
                .select("seq,entity_id,event_type,payload,ts,prev_hash,hash,payload_json")
                .eq("entity_id", entity_id)
                .order("seq", desc=False)
                .execute()
                .data
            )
            if rows is not None:
                return [{
                    "seq": r["seq"],
                    "entity_id": r["entity_id"],
                    "type": r["event_type"],
                    "payload": r["payload"],
                    "ts": r["ts"],
                    "prev_hash": r["prev_hash"],
                    "hash": r["hash"],
                    "_payload_json": r.get("payload_json") or _canonical(r["payload"]),
                } for r in rows]
        except Exception as e:
            logger.warning("DB read failed (%s) — falling back to local file", e)
    with _LOCK:
        return [dict(e, _payload_json=_canonical(e["payload"])) for e in _CHAINS.get(entity_id, [])]


def _verify_chain_events(chain: list) -> dict:
    """Recompute every hash across an event list; return {valid, length, tail_hash, broken_at}."""
    prev = "0" * 64
    prev_dt = None
    for idx, event in enumerate(chain):
        seq = event.get("seq")
        entity_id = event.get("entity_id", "")
        event_type = event.get("type", "")
        payload = event.get("payload", {})
        payload_canon = _canonical(payload)

        # Enforce that if _payload_json is present (e.g. from Supabase / get_chain),
        # it strictly matches the canonical serialization of payload.
        stored_payload_json = event.get("_payload_json")
        if stored_payload_json is not None and stored_payload_json != payload_canon:
            return {
                "valid": False,
                "length": len(chain),
                "tail_hash": chain[-1]["hash"] if chain else None,
                "broken_at": seq if seq is not None else idx,
            }

        # Timestamp validation: must be present, valid ISO format, and monotonic
        ts_str = event.get("ts")
        if not ts_str or not isinstance(ts_str, str):
            return {
                "valid": False,
                "length": len(chain),
                "tail_hash": chain[-1]["hash"] if chain else None,
                "broken_at": seq if seq is not None else idx,
            }
        try:
            curr_dt = datetime.fromisoformat(ts_str)
            if curr_dt.tzinfo is None:
                curr_dt = curr_dt.replace(tzinfo=timezone.utc)
            if prev_dt is not None and curr_dt < prev_dt:
                return {
                    "valid": False,
                    "length": len(chain),
                    "tail_hash": chain[-1]["hash"] if chain else None,
                    "broken_at": seq if seq is not None else idx,
                }
            prev_dt = curr_dt
        except Exception:
            return {
                "valid": False,
                "length": len(chain),
                "tail_hash": chain[-1]["hash"] if chain else None,
                "broken_at": seq if seq is not None else idx,
            }

        prev_hash = event.get("prev_hash", "")
        event_hash = event.get("hash", "")

        expected = _event_hash(seq, entity_id, event_type, payload_canon, prev)
        if seq != idx or prev_hash != prev or event_hash != expected:
            return {
                "valid": False,
                "length": len(chain),
                "tail_hash": chain[-1]["hash"] if chain else None,
                "broken_at": seq if seq is not None else idx,
            }
        prev = event_hash
    return {
        "valid": True,
        "length": len(chain),
        "tail_hash": chain[-1]["hash"] if chain else None,
        "broken_at": None,
    }


def verify_chain(entity_id: str) -> dict:
    """Recompute every hash; return {valid, length, tail_hash, broken_at}."""
    chain = get_chain(entity_id)
    return _verify_chain_events(chain)


def ensure_genesis(entity_id: str, snapshot: dict, ts: str = "") -> dict:
    """Create the deterministic ISSUE event if the entity has no chain yet.

    The payload snapshot (farm satellite + verification state) makes the
    genesis hash stable across restarts for unchanged farms.
    """
    with _LOCK:
        existing = get_chain(entity_id)
        if existing:
            return existing[0]
        return append_event(
            entity_id,
            "ISSUE",
            {
                "note": "Credit issuance anchored to farm evidence snapshot",
                "snapshot": snapshot,
            },
            ts=ts,
        )


def summary(entity_id: str) -> dict:
    """Compact chain view for embedding in passport/wallet responses."""
    chain = get_chain(entity_id)
    verification = _verify_chain_events(chain)
    return {
        "events": len(chain),
        "tail_hash": verification["tail_hash"],
        "verified": verification["valid"],
        "first_ts": chain[0]["ts"] if chain else None,
        "last_ts": chain[-1]["ts"] if chain else None,
        "types": [e["type"] for e in chain],
    }
