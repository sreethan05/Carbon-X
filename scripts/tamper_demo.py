"""Live greenwashing defense: show the ledger catching a tamper attempt.

Creates a small credit chain in a sandbox (file-backed, never touches
production data), then plays the fraudster: silently inflates the retired
credit volume, recomputes the chain, and shows the exact event where the
tamper is caught.

Run: python scripts/tamper_demo.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.services import ledger as ledger_module  # noqa: E402


def main():
    sandbox = Path(__file__).resolve().parents[1] / "backend" / "data" / "tamper_demo.json"
    os.environ["CARBONX_LEDGER_PATH"] = str(sandbox)
    ledger_module._PATH = str(sandbox)
    ledger_module._CHAINS = {}
    ledger_module._sb = lambda: None  # demo is deliberately file-only
    if sandbox.exists():
        sandbox.unlink()

    print("=" * 64)
    print("CARBONX TAMPER DEMONSTRATION")
    print("=" * 64)

    print("\n1. A credit's honest lifecycle is recorded:")
    ledger_module.ensure_genesis("demo-farm", {"farm": "Venkat's plot", "ndvi": 0.78})
    ledger_module.append_event("demo-farm", "SALE", {"buyer": "ESG Corp", "credits": 40})
    ledger_module.append_event("demo-farm", "SPLIT", {"farmer_inr": 12600, "platform_inr": 4500})
    ledger_module.append_event("demo-farm", "RETIRE", {"certificate": "CX-2026-CERT-DEMO", "credits": 40})
    check = ledger_module.verify_chain("demo-farm")
    print(f"   chain: {check['length']} events | verified = {check['valid']}")

    print("\n2. A fraudster edits the ledger after the fact:")
    print("   (changes RETIRE credits 40 -> 400, hoping nobody recomputes)")
    chain = ledger_module.get_chain("demo-farm")
    retire_event = next(e for e in chain if e["type"] == "RETIRE")
    retire_event["payload"]["credits"] = 400
    # write the tampered chain as if it were the stored state
    ledger_module._CHAINS["demo-farm"] = chain

    print("\n3. Anyone can recompute the chain:")
    check = ledger_module.verify_chain("demo-farm")
    print(f"   verified = {check['valid']}")
    print(f"   broken at event seq = {check['broken_at']} "
          f"(the exact RETIRE record that was altered)")
    print(f"   tail hash still on file: {str(check['tail_hash'])[:16]}…")

    print("\n4. Verdict:")
    if not check["valid"]:
        print("   TAMPER CAUGHT. The hash of every event covers the previous")
        print("   event's hash — you cannot edit history without breaking the")
        print("   chain at a pinpointable location. Buyers and farmers can run")
        print("   this recomputation themselves (GET /ledger/{farm_id}).")
    sandbox.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
