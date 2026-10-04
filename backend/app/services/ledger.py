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
        with open(_PATH, "w", encoding="utf-8") as fh:
            json.dump(_CHAINS, fh, indent=1, default=str)
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
    if _MIGRATED or not _CHAINS:
        _MIGRATED = True
        return
    try:
        rows = []
        for entity_id, chain in _CHAINS.items():
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
        _CHAINS[entity_id] = chain + [event]
        _persist_file()
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


def verify_chain(entity_id: str) -> dict:
    """Recompute every hash; return {valid, length, tail_hash, broken_at}."""
    chain = get_chain(entity_id)
    prev = "0" * 64
    for event in chain:
        expected = _event_hash(
            event["seq"], event["entity_id"], event["type"], event["_payload_json"], prev
        )
        if event["prev_hash"] != prev or event["hash"] != expected:
            return {
                "valid": False,
                "length": len(chain),
                "tail_hash": chain[-1]["hash"] if chain else None,
                "broken_at": event["seq"],
            }
        prev = event["hash"]
    return {
        "valid": True,
        "length": len(chain),
        "tail_hash": chain[-1]["hash"] if chain else None,
        "broken_at": None,
    }


def ensure_genesis(entity_id: str, snapshot: dict, ts: str = "") -> dict:
    """Create the deterministic ISSUE event if the entity has no chain yet.

    The payload snapshot (farm satellite + verification state) makes the
    genesis hash stable across restarts for unchanged farms.
    """
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
    verification = verify_chain(entity_id)
    chain = get_chain(entity_id)
    return {
        "events": len(chain),
        "tail_hash": verification["tail_hash"],
        "verified": verification["valid"],
        "first_ts": chain[0]["ts"] if chain else None,
        "last_ts": chain[-1]["ts"] if chain else None,
        "types": [e["type"] for e in chain],
    }
