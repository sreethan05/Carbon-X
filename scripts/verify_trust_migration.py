"""Read-only verification that 10_trust_controls.sql was applied.

Re-runnable ops check (via PostgREST OpenAPI, service_role bypasses RLS):
- the 4 new tables exist
- the key new columns exist on altered tables
Prints ASCII-only PASS/FAIL lines. No writes are performed.
"""
import json
import pathlib
import sys
import urllib.request
import urllib.error

BACKEND_ENV = pathlib.Path("backend/.env")

env = {}
for line in BACKEND_ENV.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, v = line.split("=", 1)
    env[k.strip()] = v.strip().strip('"').strip("'")

url = env.get("SUPABASE_URL", "").rstrip("/")
key = env.get("SUPABASE_SERVICE_ROLE_KEY", "")
if not url or not key:
    print("FAIL: SUPABASE credentials not found in backend/.env")
    sys.exit(1)

req = urllib.request.Request(
    f"{url}/rest/v1/",
    headers={"apikey": key, "Authorization": f"Bearer {key}"},
)
try:
    with urllib.request.urlopen(req, timeout=30) as r:
        spec = json.load(r)
except urllib.error.HTTPError as e:
    print(f"FAIL: OpenAPI fetch HTTP {e.code}")
    sys.exit(1)

defs = spec.get("definitions") or spec.get("components", {}).get("schemas", {})
props = {name: d.get("properties", {}) for name, d in defs.items()}

fails = 0


def check(table, col):
    global fails
    ok = table in props and (col is None or col in props[table])
    if ok:
        print(f"PASS {table}" + (f".{col}" if col else " (table)"))
    else:
        fails += 1
        print(f"FAIL {table}" + (f".{col} missing" if col else " (table missing)"))


for t in ("consent_records", "privacy_requests", "corporate_settings", "support_tickets"):
    check(t, None)

for t, c in (
    ("ground_truth_samples", "measurement_type"),
    ("ground_truth_samples", "estimate_snapshot"),
    ("marketplace_listings", "lifecycle_state"),
    ("marketplace_listings", "dispute_status"),
    ("profiles", "is_active"),
    ("profiles", "consent_version"),
    ("farm_evidence", "deleted_at"),
    ("kyc_verifications", "document_deleted_at"),
):
    check(t, c)

print("---")
print("MIGRATION VERIFIED" if fails == 0 else f"{fails} CHECKS FAILED")
sys.exit(0 if fails == 0 else 1)
