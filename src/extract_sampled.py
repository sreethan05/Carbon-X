"""Bounded, stratified, checkpointed full-contract feature extraction.

Samples GBIF richness cells evenly across species-count strata (so the model
sees the full richness spectrum), extracts the full 33-feature serving
contract (``src/extract_features.py``) and checkpoints progress every 25
cells. Resume-safe: coordinates already present in the checkpoint are
skipped, so the runner can be restarted after a crash or a timebox stop.

Usage:
    python extract_sampled.py [max_cells=600]

Env:
    EXTRACT_TIME_BUDGET_MIN  wall-clock budget, default 85 (0 disables) —
                             the run stops after the current 25-cell chunk
                             and still writes checkpoint + final CSV
    EXTRACT_WORKERS          concurrent cells, default 3 (EE handles a few
                             parallel reduceRegion calls; failures are
                             retried once, then counted)
    CARBONX_SOILGRIDS_REST   0 disables the ISRIC REST probe/fallback

Outputs (src/data/):
    features_v3_checkpoint.csv        resume checkpoint
    satellite_features_v3.csv         final feature table (33 contract
                                      features + lat/lon/targets + REST SOC
                                      target column)
    features_v3_extraction_log.json   run summary, per-feature non-null counts
"""
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import pandas as pd

from extract_features import (
    DATA_DIR,
    EXTRACTION_VERSION,
    FEATURE_ORDER,
    SOILGRIDS_TARGET_COL,
    get_features,
    init_ee,
    soilgrids_rest_available,
)

MAX_CELLS = int(sys.argv[1]) if len(sys.argv) > 1 else 600
STRATA = 8  # species-count quantiles
PER_STRATUM = max(1, MAX_CELLS // STRATA)
TIME_BUDGET_MIN = float(os.getenv("EXTRACT_TIME_BUDGET_MIN", "85"))
WORKERS = max(1, int(os.getenv("EXTRACT_WORKERS", "3")))
CHECKPOINT_EVERY = 25

CKPT_PATH = DATA_DIR / "features_v3_checkpoint.csv"
OUT_PATH = DATA_DIR / "satellite_features_v3.csv"
LOG_PATH = DATA_DIR / "features_v3_extraction_log.json"

EXTRA_COLS = ["latitude", "longitude", "species_count", "observation_count",
              SOILGRIDS_TARGET_COL]


def extract_one(row):
    """Extract one cell with one retry. Returns (features, None) or (None, err)."""
    last_error = None
    for attempt in range(2):
        try:
            feats = get_features(row["latitude"], row["longitude"])
            if feats and not all(v is None for v in feats.values()):
                feats.update({
                    "latitude": row["latitude"],
                    "longitude": row["longitude"],
                    "species_count": row["species_count"],
                    "observation_count": row.get("observation_count", 0),
                })
                return feats, None
            last_error = "all features null"
        except Exception as e:  # noqa: BLE001 — retried once, then reported
            last_error = f"{type(e).__name__}: {str(e)[:160]}"
        if attempt == 0:
            time.sleep(3)
    return None, last_error


def main():
    start = time.time()
    started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    richness = pd.read_csv(DATA_DIR / "species_richness_weighted.csv")
    richness = richness[richness["species_count"] > 2].reset_index(drop=True)
    print(f"Available richness cells: {len(richness)}")

    richness["stratum"] = pd.qcut(richness["species_count"].rank(method="first"),
                                  STRATA, labels=False)
    sample = (richness.groupby("stratum", group_keys=False)
              .apply(lambda g: g.sample(n=min(PER_STRATUM, len(g)), random_state=42)))
    print(f"Sampled {len(sample)} cells across {STRATA} richness strata "
          f"(max_cells={MAX_CELLS})")

    try:
        prev = pd.read_csv(CKPT_PATH)
    except Exception:
        prev = pd.DataFrame()
    done = set(zip(prev["latitude"], prev["longitude"])) if len(prev) else set()
    todo = [row for _, row in sample.iterrows()
            if (row["latitude"], row["longitude"]) not in done]
    print(f"Checkpoint: {len(prev)} rows already extracted; {len(todo)} cells to do")

    init_ee()
    rest_ok = soilgrids_rest_available()

    new_rows = []
    attempted = failed = 0
    stop_reason = "completed"
    budget_seconds = TIME_BUDGET_MIN * 60

    for offset in range(0, len(todo), CHECKPOINT_EVERY):
        if budget_seconds and (time.time() - start) > budget_seconds:
            stop_reason = "time_budget"
            break
        chunk = todo[offset:offset + CHECKPOINT_EVERY]
        with ThreadPoolExecutor(max_workers=min(WORKERS, len(chunk))) as ex:
            futures = {ex.submit(extract_one, row): row for row in chunk}
            for future in as_completed(futures):
                row = futures[future]
                attempted += 1
                feats, error = future.result()
                if feats is not None:
                    new_rows.append(feats)
                else:
                    failed += 1
                    print(f"  failed ({row['latitude']},{row['longitude']}): {error}")

        dfs_to_concat = [df for df in [prev, pd.DataFrame(new_rows)] if not df.empty]
        combined = pd.concat(dfs_to_concat, ignore_index=True) if dfs_to_concat else pd.DataFrame()
        if not combined.empty:
            combined = combined.drop_duplicates(subset=["latitude", "longitude"]).reset_index(drop=True)
            tmp_ckpt = CKPT_PATH.with_suffix(".csv.tmp")
            combined.to_csv(tmp_ckpt, index=False)
            tmp_ckpt.replace(CKPT_PATH)
        elapsed = (time.time() - start) / 60
        print(f"  {min(offset + len(chunk), len(todo))}/{len(todo)} processed | "
              f"ok={len(new_rows)} failed={failed} | {elapsed:.1f} min")

    dfs_to_concat = [df for df in [prev, pd.DataFrame(new_rows)] if not df.empty]
    out = pd.concat(dfs_to_concat, ignore_index=True) if dfs_to_concat else pd.DataFrame()
    if len(out):
        out = (out.drop_duplicates(subset=["latitude", "longitude"])
               .sort_values(["latitude", "longitude"])
               .reset_index(drop=True))
    tmp_out = OUT_PATH.with_suffix(".csv.tmp")
    out.to_csv(tmp_out, index=False)
    tmp_out.replace(OUT_PATH)

    feature_cols = FEATURE_ORDER + [SOILGRIDS_TARGET_COL]
    log = {
        "extraction_version": EXTRACTION_VERSION,
        "started_at": started_at,
        "elapsed_minutes": round((time.time() - start) / 60, 2),
        "stop_reason": stop_reason,
        "time_budget_minutes": TIME_BUDGET_MIN,
        "workers": WORKERS,
        "max_cells_requested": MAX_CELLS,
        "sample_size": int(len(sample)),
        "resumed_rows": int(len(prev)),
        "attempted_this_run": attempted,
        "succeeded_this_run": len(new_rows),
        "failed_this_run": failed,
        "total_rows": int(len(out)),
        "soilgrids_rest_available": bool(rest_ok),
        "per_feature_non_null": {c: int(out[c].notna().sum())
                                 for c in feature_cols if c in out.columns},
    }
    with open(LOG_PATH, "w", encoding="utf-8") as fh:
        json.dump(log, fh, indent=2)
    print(f"DONE ({stop_reason}): {len(out)} cells written to {OUT_PATH.name}; "
          f"this run attempted={attempted} ok={len(new_rows)} failed={failed} "
          f"in {log['elapsed_minutes']} min")
    print(f"Run log: {LOG_PATH.name}")


if __name__ == "__main__":
    main()
