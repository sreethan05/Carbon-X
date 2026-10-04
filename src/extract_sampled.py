"""Bounded, stratified Sentinel-2 feature extraction.

Extracting every GBIF grid cell through Earth Engine takes hours; this runner
samples cells evenly across the species-count range (so the model sees the
full richness spectrum), caps the total, and checkpoints progress.

Usage: python extract_sampled.py [max_cells=320]
"""
import sys
import time

import pandas as pd

from config import DATA
from extract_features import get_features

MAX_CELLS = int(sys.argv[1]) if len(sys.argv) > 1 else 320
STRATA = 8  # species-count quantiles
PER_STRATUM = MAX_CELLS // STRATA


def main():
    richness = pd.read_csv(f"{DATA}/species_richness_weighted.csv")
    richness = richness[richness["species_count"] > 2].reset_index(drop=True)
    print(f"Available cells: {len(richness)}")

    richness["stratum"] = pd.qcut(richness["species_count"].rank(method="first"), STRATA, labels=False)
    sample = (richness.groupby("stratum", group_keys=False)
              .apply(lambda g: g.sample(n=min(PER_STRATUM, len(g)), random_state=42)))
    print(f"Sampled {len(sample)} cells across {STRATA} richness strata")

    rows, failed = [], 0
    ckpt_path = f"{DATA}/features_v2_checkpoint.csv"
    done = set()
    try:
        prev = pd.read_csv(ckpt_path)
        done = set(zip(prev["latitude"], prev["longitude"]))
    except Exception:
        prev = pd.DataFrame()

    for i, (_, row) in enumerate(sample.iterrows(), 1):
        coord = (row["latitude"], row["longitude"])
        if coord in done:
            continue
        try:
            f = get_features(row["latitude"], row["longitude"])
            if f and not all(v is None for v in f.values()):
                f.update({"latitude": row["latitude"], "longitude": row["longitude"],
                          "species_count": row["species_count"],
                          "observation_count": row["observation_count"]})
                rows.append(f)
            else:
                failed += 1
        except Exception as e:
            failed += 1
            print(f"  cell {i}: {type(e).__name__}")
        if i % 25 == 0:
            pd.concat([prev, pd.DataFrame(rows)], ignore_index=True).to_csv(ckpt_path, index=False)
            print(f"  {i}/{len(sample)} extracted ({failed} failed)")
            time.sleep(1)

    out = pd.concat([prev, pd.DataFrame(rows)], ignore_index=True).drop_duplicates(
        subset=["latitude", "longitude"])
    out.to_csv(f"{DATA}/satellite_features_v2.csv", index=False)
    print(f"DONE: {len(out)} cells written to satellite_features_v2.csv ({failed} failed this run)")


if __name__ == "__main__":
    main()
