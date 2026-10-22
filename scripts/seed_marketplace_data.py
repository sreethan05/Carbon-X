"""Seed realistic sample data into the CarbonX marketplace (remote Supabase DB).

Seeds the canonical demo data from backend/app/sample_data.py:
demo farmer profiles, farms, and varied marketplace_listings
(Active / Sold / Expired) so the dashboard has meaningful data.

Execution strategy (printed to the terminal):
  1. PRIMARY  — LIVE DB via Supabase REST (supabase-py) using the key in
     backend/.env (SUPABASE_SERVICE_ROLE_KEY preferred).
  2. FALLBACK — Supabase Management API SQL endpoint (runs as postgres) using
     the Supabase CLI's stored access token.

Safe to re-run: inserts are guarded (upsert on phone / NOT EXISTS / existence checks).

Usage:
    python scripts/seed_marketplace_data.py
"""
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
load_dotenv(ROOT / "backend" / ".env")

from app.sample_data import (  # noqa: E402
    FARMERS,
    FARMS,
    LISTINGS,
    TEST_FARMER_PHONE,
    TEST_FARM_ID,
    farm_geojson,
    materialize_listings,
)

FPO_ID = "a1b2c3d4-e5f6-4a5b-8c9d-0e1f2a3b4c5d"
FPO_REG_NO = "FPO-TG-001"
FPO_NAME = "Khammam Farmer Producer Org"

CORP_ID = "b6fecf68-1d5c-4bb9-bb52-609d055c097b"
CORP_NAME = "Telangana Sustainable Agro Pvt Ltd"
# bcrypt hash for "Corporate@2026"
CORP_PASSWORD_HASH = "$2b$12$KkQ1bK0j8j/T8G1oG8vVtep67p/rF3hUqQj9/q.xN3qF3wT4kM0ye"

# Own CarbonX project (sreethan05). Override with SUPABASE_PROJECT_REF env var.
PROJECT_REF = os.getenv("SUPABASE_PROJECT_REF", "ihyqhisxgdwxudnxksts")


# ── PRIMARY: live DB via Supabase REST ──

def build_rest_client():
    from supabase import create_client

    url = os.getenv("SUPABASE_URL", "").strip()
    key = (
        os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        or os.getenv("SUPABASE_KEY", "").strip()
        or os.getenv("SUPABASE_ANON_KEY", "").strip()
    )
    if not url or not key:
        raise RuntimeError("SUPABASE_URL / key not found in backend/.env")
    return create_client(url, key)


def _profile_rows():
    rows = []
    # 1. Platform Admin
    rows.append({
        "phone": "9000000000",
        "name": "Platform Administrator",
        "role": "admin",
        "state": "Telangana",
        "district": "Hyderabad",
        "village": "Platform HQ",
        "upi": "admin@carbonx",
    })
    # 2. Farmers and FPO officer
    for phone, f in FARMERS.items():
        is_officer = (phone == "9000000001")
        is_member = (phone in ("9000000002", "9000000003", "9000000004"))
        rows.append({
            "phone": phone,
            "name": "Srinivas Rao (FPO Officer)" if is_officer else f["name"],
            "role": "fpo" if is_officer else "farmer",
            "fpo_id": FPO_ID if (is_officer or is_member) else None,
            "state": f["state"],
            "district": f["district"],
            "village": f["village"],
            "upi": f.get("upi", ""),
        })
    return rows


def _farm_row(f):
    return {
        "name": f["name"],
        "owner_phone": f["phone"],
        "status": "Verified",
        "crop_type": f["crop"],
        "area_hectares": f["area"],
        "ndvi": f["ndvi"],
        "evi": f["evi"],
        "soil_moisture": f["soil"],
        "tree_cover": f["trees"],
        "vegetation_health": "Good",
        "satellite_source": "Sentinel-2 (GEE)",
        "ai_confidence": 0.88,
        "carbon_tonnes": f["carbon"],
        "biodiversity_score": f["score"],
        "biodiversity_credits": round(f["score"] / 40.0, 2),
        "total_credits": round(f["carbon"] + f["score"] / 40.0, 2),
        "irrigation": f["irrigation"],
        "geojson": farm_geojson(),
    }


def seed_via_rest() -> int:
    """Seed through the live DB. Returns number of newly inserted listings."""
    sb = build_rest_client()

    # 0. Ensure FPO and Corporate Buyer
    sb.table("fpos").upsert([{
        "id": FPO_ID,
        "name": FPO_NAME,
        "registration_no": FPO_REG_NO,
    }], on_conflict="registration_no").execute()
    print(f"  [LIVE DB] FPO ensured ({FPO_REG_NO}: {FPO_NAME})")

    sb.table("corporates").upsert([{
        "c_id": CORP_ID,
        "name": CORP_NAME,
        "password_hash": CORP_PASSWORD_HASH,
    }], on_conflict="c_id").execute()
    print(f"  [LIVE DB] Corporate Buyer ensured ({CORP_NAME})")

    profiles = _profile_rows()
    sb.table("profiles").upsert(profiles, on_conflict="phone").execute()
    print(f"  [LIVE DB] {len(profiles)} profiles ensured (Admin, FPO, and Farmers; upsert on phone)")

    farm_ids = {}
    for f in FARMS:
        res = (
            sb.table("farms")
            .select("id")
            .eq("owner_phone", f["phone"])
            .eq("name", f["name"])
            .limit(1)
            .execute()
        )
        if res.data:
            farm_ids[f["key"]] = res.data[0]["id"]
            continue
        res = sb.table("farms").insert(_farm_row(f)).execute()
        farm_ids[f["key"]] = res.data[0]["id"]
        print(f"  [LIVE DB] farm created: {f['name']} -> {res.data[0]['id']}")

    rows = materialize_listings(as_of=datetime.now(timezone.utc), farm_ids=farm_ids)

    phones = list(FARMERS.keys()) + [TEST_FARMER_PHONE]
    res = (
        sb.table("marketplace_listings")
        .select("farmer_phone,crop,status,price_per_credit")
        .in_("farmer_phone", phones)
        .execute()
    )
    existing = {
        (r["farmer_phone"], r["crop"], r["status"], float(r["price_per_credit"]))
        for r in res.data or []
    }
    missing = [
        r for r in rows
        if (r["farmer_phone"], r["crop"], r["status"], float(r["price_per_credit"])) not in existing
    ]
    if missing:
        sb.table("marketplace_listings").insert(missing).execute()
    print(f"  [LIVE DB] listings ensured: {len(missing)} newly inserted, "
          f"{len(rows) - len(missing)} already existed")
    return len(missing)


# ── FALLBACK: Management API SQL (runs as postgres) ──

def read_cli_access_token():
    token = os.getenv("SUPABASE_ACCESS_TOKEN", "").strip()
    if token:
        return token
    token_file = Path.home() / ".supabase" / "access-token"
    if token_file.exists():
        return token_file.read_text().strip()
    return _read_windows_credential("Supabase CLI:supabase")


def _read_windows_credential(target):
    try:
        import ctypes
        from ctypes import wintypes

        class CREDENTIAL(ctypes.Structure):
            _fields_ = [("Flags", wintypes.DWORD), ("Type", wintypes.DWORD),
                        ("TargetName", wintypes.LPWSTR), ("Comment", wintypes.LPWSTR),
                        ("LastWritten", wintypes.FILETIME), ("CredentialBlobSize", wintypes.DWORD),
                        ("CredentialBlob", ctypes.POINTER(ctypes.c_byte)), ("Persist", wintypes.DWORD),
                        ("AttributeCount", wintypes.DWORD), ("Attributes", ctypes.c_void_p),
                        ("TargetAlias", wintypes.LPWSTR), ("UserName", wintypes.LPWSTR)]

        ptr = ctypes.POINTER(CREDENTIAL)()
        if not ctypes.windll.advapi32.CredReadW(target, 1, 0, ctypes.byref(ptr)):
            return None
        cred = ptr.contents
        return ctypes.string_at(cred.CredentialBlob, cred.CredentialBlobSize).decode("utf-8", errors="ignore").rstrip("\x00")
    except Exception:
        return None


def run_sql(query: str):
    import httpx

    token = read_cli_access_token()
    if not token:
        sys.exit("No Supabase access token available (CLI not logged in?).")
    r = httpx.post(
        f"https://api.supabase.com/v1/projects/{PROJECT_REF}/database/query",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": query},
        timeout=60,
    )
    if r.status_code >= 400:
        sys.exit(f"Management API error {r.status_code}: {r.text[:300]}")
    return r.json()


def sql(value):
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, (dict, list)):
        import json

        value = json.dumps(value)
    return "'" + str(value).replace("'", "''") + "'"


def seed_via_sql() -> int:
    """Seed through the Management API. Returns number of newly inserted listings."""
    # 0. Ensure FPO and Corporate Buyer
    run_sql(
        f"insert into fpos (id, name, registration_no)\n"
        f"values ({sql(FPO_ID)}, {sql(FPO_NAME)}, {sql(FPO_REG_NO)})\n"
        f"on conflict (registration_no) do update set name = excluded.name"
    )
    print(f"  [FALLBACK] FPO ensured ({FPO_REG_NO}: {FPO_NAME})")

    run_sql(
        f"insert into corporates (c_id, name, password_hash)\n"
        f"values ({sql(CORP_ID)}, {sql(CORP_NAME)}, {sql(CORP_PASSWORD_HASH)})\n"
        f"on conflict (c_id) do update set password_hash = excluded.password_hash, name = excluded.name"
    )
    print(f"  [FALLBACK] Corporate Buyer ensured ({CORP_NAME})")

    profiles = _profile_rows()
    values = ",\n  ".join(
        "(" + ", ".join(sql(v) for v in (p["phone"], p["name"], p["role"], p["state"], p["district"], p["village"], p.get("upi", ""), p.get("fpo_id"))) + ")"
        for p in profiles
    )
    rows = run_sql(
        "insert into profiles (phone, name, role, state, district, village, upi, fpo_id)\nvalues\n  "
        + values
        + "\non conflict (phone) do update set name = excluded.name, role = excluded.role, fpo_id = excluded.fpo_id\nreturning phone"
    )
    print(f"  [FALLBACK] {len(profiles)} profiles ensured ({len(rows)} affected)")

    farm_ids = {}
    for f in FARMS:
        row = _farm_row(f)
        cols = ", ".join(row.keys())
        vals = ", ".join(sql(v) for v in row.values())
        res = run_sql(
            f"insert into farms ({cols})\nselect {vals}\nwhere not exists "
            f"(select 1 from farms where owner_phone = {sql(f['phone'])} and name = {sql(f['name'])})\nreturning id"
        )
        if res:
            farm_ids[f["key"]] = res[0]["id"]
            print(f"  [FALLBACK] farm created: {f['name']} -> {res[0]['id']}")
        else:
            res = run_sql(
                f"select id from farms where owner_phone = {sql(f['phone'])} and name = {sql(f['name'])} limit 1"
            )
            farm_ids[f["key"]] = res[0]["id"]

    listing_rows = materialize_listings(farm_ids=farm_ids)
    inserted = 0
    for row in listing_rows:
        cols = ", ".join(row.keys())
        vals = ", ".join(sql(v) for v in row.values())
        res = run_sql(
            f"insert into marketplace_listings ({cols})\nselect {vals}\nwhere not exists "
            f"(select 1 from marketplace_listings where farmer_phone = {sql(row['farmer_phone'])} "
            f"and crop = {sql(row['crop'])} and status = {sql(row['status'])} "
            f"and price_per_credit = {sql(row['price_per_credit'])})\nreturning id"
        )
        inserted += len(res)
    print(f"  [FALLBACK] listings ensured: {inserted} newly inserted, "
          f"{len(listing_rows) - inserted} already existed")
    return inserted


def main():
    print("Seeding CarbonX marketplace sample data")
    print("[SOURCE] Trying LIVE DB via Supabase REST (service role key)...")
    try:
        seed_via_rest()
        print("[SOURCE] SUCCESS — data lives in the LIVE DB (Supabase REST).")
        return
    except Exception as e:
        print(f"[SOURCE] LIVE DB path failed: {str(e)[:160]}")
    print("[SOURCE] Falling back to Management API SQL (runs as postgres)...")
    seed_via_sql()
    print("[SOURCE] SUCCESS — seeded via FALLBACK (Management API SQL).")


if __name__ == "__main__":
    main()
