"""CarbonX Automated Data & Ledger Backup Utility.

Exports remote Supabase tables, local ledger hash chains, and evidence files
into a timestamped compressed archive.

Usage:
    python scripts/backup_data.py [--output-dir backups] [--verify]

Prerequisites:
    Configured backend/.env or SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.
"""
import argparse
import datetime
import gzip
import json
import os
import shutil
import sys
import tarfile
import tempfile

# Add backend directory to sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.join(BASE_DIR, "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(BACKEND_DIR, ".env"))

from app import supabase_db as db
from app.services import evidence_service


TABLES_TO_BACKUP = [
    "profiles",
    "fpos",
    "corporates",
    "farms",
    "marketplace_listings",
    "ledger_events",
    "farm_evidence",
    "kyc_verifications",
    "ground_truth_samples",
]


def backup(output_dir: str = "backups") -> str:
    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
    os.makedirs(output_dir, exist_ok=True)
    archive_name = f"carbonx_backup_{timestamp}.tar.gz"
    archive_path = os.path.join(output_dir, archive_name)

    temp_stage = tempfile.mkdtemp(prefix="carbonx_bkp_")
    try:
        manifest = {
            "timestamp": timestamp,
            "version": "1.0",
            "tables": {},
            "files": [],
        }

        # 1. Export Supabase DB Tables
        sb = db._client()
        if sb:
            print("[backup] Connected to Supabase DB. Dumping tables...")
            for table in TABLES_TO_BACKUP:
                try:
                    res = sb.table(table).select("*").execute()
                    rows = res.data or []
                    table_file = os.path.join(temp_stage, f"{table}.json")
                    with open(table_file, "w", encoding="utf-8") as f:
                        json.dump(rows, f, indent=2, default=str)
                    manifest["tables"][table] = len(rows)
                    print(f"  [OK] {table}: {len(rows)} records")
                except Exception as e:
                    print(f"  [FAIL] {table} failed: {e}")
                    manifest["tables"][table] = f"error: {e}"
        else:
            print("[backup] Supabase DB not configured. Skipping remote table export.")

        # 2. Backup Local Ledger JSON
        ledger_path = os.getenv("CARBONX_LEDGER_PATH", os.path.join(BACKEND_DIR, "data", "ledger.json"))
        if os.path.exists(ledger_path):
            dst = os.path.join(temp_stage, "ledger.json")
            shutil.copy2(ledger_path, dst)
            manifest["files"].append("ledger.json")
            print(f"  [OK] Copied local hash ledger: {ledger_path}")

        # 3. Backup Local Evidence Store
        ev_dir = evidence_service.evidence_dir()
        if os.path.exists(ev_dir):
            ev_stage = os.path.join(temp_stage, "evidence")
            shutil.copytree(ev_dir, ev_stage, dirs_exist_ok=True)
            manifest["files"].append("evidence")
            print(f"  [OK] Copied evidence directory: {ev_dir}")

        # 4. Write Backup Manifest
        with open(os.path.join(temp_stage, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        # 5. Create compressed tar.gz archive
        with tarfile.open(archive_path, "w:gz") as tar:
            tar.add(temp_stage, arcname="")

        size_kb = os.path.getsize(archive_path) / 1024.0
        print(f"\n[backup] Successfully generated {archive_path} ({size_kb:.2f} KB)")
        return archive_path
    finally:
        shutil.rmtree(temp_stage, ignore_errors=True)


def verify_backup(archive_path: str) -> bool:
    print(f"\n[verify] Inspecting backup archive: {archive_path}")
    if not os.path.isfile(archive_path):
        print(f"  [FAIL] File not found: {archive_path}")
        return False
    try:
        with tarfile.open(archive_path, "r:gz") as tar:
            names = tar.getnames()
            if "manifest.json" not in names:
                print("  [FAIL] manifest.json missing from archive")
                return False
            manifest_file = tar.extractfile("manifest.json")
            manifest = json.loads(manifest_file.read().decode("utf-8"))
            print(f"  [OK] Archive valid. Backup timestamp: {manifest.get('timestamp')}")
            print(f"  [OK] Tables included: {list(manifest.get('tables', {}).keys())}")
            print(f"  [OK] Files included: {manifest.get('files', [])}")
            return True
    except Exception as e:
        print(f"  [FAIL] Backup verification failed: {e}")
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CarbonX Backup Utility")
    parser.add_argument("--output-dir", default="backups", help="Directory to store backup archives")
    parser.add_argument("--verify", type=str, default=None, help="Path to archive file to verify")
    args = parser.parse_args()

    if args.verify:
        ok = verify_backup(args.verify)
        sys.exit(0 if ok else 1)
    else:
        path = backup(args.output_dir)
        ok = verify_backup(path)
        sys.exit(0 if ok else 1)
