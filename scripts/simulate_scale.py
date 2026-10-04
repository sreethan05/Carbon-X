"""Scale simulation — demonstrates pipeline throughput and unit cost.

Simulates N farm verification + sale/split cycles through the REAL credit
engine, split engine and ledger (local sandbox chain), and reports latency
percentiles plus the platform's unit-economics constants.

This is a simulation of backend compute cost only (satellite extraction cost
is modelled separately — each Sentinel-2 feature extraction costs processing
units on the free Copernicus/EE tier). Not a load test of live Supabase.

Usage: python scripts/simulate_scale.py [n_farms=100000]
"""
import math
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.services import credit_engine, split_engine  # noqa: E402
from app.services import ledger as ledger_module  # noqa: E402

CROPS = ["Rice", "Maize", "Cotton", "Millets", "Sugarcane", "Turmeric", "Chilli"]

# Unit economics (documented in docs/ECONOMICS.md — assumptions shown there).
FIELD_AGENT_COST_PER_FARM_INR = 0          # farmer self-serves via phone
SATELLITE_COST_PER_SCAN_INR = 0.40         # free-tier PU amortised + egress estimate
PLATFORM_FIXED_MONTHLY_INR = 0             # free tiers (Supabase/EE/Vercel)
AVG_CREDITS_PER_FARM = 40
AVG_PRICE_PER_CREDIT_INR = 450
FARMER_SHARE = 0.70


def main(n_farms: int = 100_000):
    ledger_module._sb = lambda: None  # simulation uses the file sandbox
    ledger_module._CHAINS = {}
    ledger_module._PATH = ":memory:"  # never touches disk or DB

    latencies_verify, latencies_sale = [], []
    t0 = time.perf_counter()
    for i in range(min(n_farms, 5000)):  # sample 5k for timing, extrapolate
        area = 0.4 + (i % 30) * 0.1
        crop = CROPS[i % len(CROPS)]
        ndvi = 0.3 + (i % 50) / 100
        t1 = time.perf_counter()
        est = credit_engine.quick_scan_estimate(area, crop, ndvi)
        split = split_engine.compute_split(est["credits_tco2e"] * AVG_PRICE_PER_CREDIT_INR,
                                           fpo_involved=(i % 3 == 0))
        ledger_module.append_event(f"sim-{i % 1000}", "SALE", {"credits": est["credits_tco2e"]})
        latencies_verify.append((time.perf_counter() - t1) * 1000)

    def pct(values, p):
        return round(statistics.quantiles(values, n=100)[p - 1], 2)

    elapsed = time.perf_counter() - t0
    per_farm_ms = statistics.mean(latencies_verify)

    # Extrapolated annual cost for n_farms
    gross = n_farms * AVG_CREDITS_PER_FARM * AVG_PRICE_PER_CREDIT_INR
    platform_revenue = gross * 0.25
    satellite_cost = n_farms * SATELLITE_COST_PER_SCAN_INR * 73  # 73 cycles / yr (5-day)

    print(f"Simulated {min(n_farms, 5000):,} verification+sale cycles "
          f"(extrapolating to {n_farms:,} farms)")
    print(f"  per-farm pipeline latency: mean={per_farm_ms:.2f} ms | "
          f"p50={pct(latencies_verify, 50)} ms | p95={pct(latencies_verify, 95)} ms | "
          f"max={max(latencies_verify):.2f} ms")
    print(f"  throughput (single worker): ~{1000 / per_farm_ms:,.0f} farms/sec compute-bound")
    print()
    print("Unit economics @ {:,} farms/yr:".format(n_farms))
    print(f"  gross credit value        : INR {gross:,.0f}")
    print(f"  platform revenue (25%)    : INR {platform_revenue:,.0f}")
    print(f"  farmer payouts (70% floor): INR {gross * FARMER_SHARE:,.0f}")
    print(f"  satellite monitoring cost : INR {satellite_cost:,.0f} "
          f"({SATELLITE_COST_PER_SCAN_INR} x 73 cycles/farm)")
    print(f"  verification cost/farm    : INR {SATELLITE_COST_PER_SCAN_INR * 73:.0f} "
          f"(vs INR 2,000+ single soil test)")
    print(f"  break-even farms          : "
          f"{math.ceil(satellite_cost / max(platform_revenue / max(n_farms, 1), 0.01)):,} "
          f"(satellite cost covered by per-farm platform share)")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 100_000)
