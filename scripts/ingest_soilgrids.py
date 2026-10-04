"""Ingest SoilGrids 2.0 SOC data into ground_truth_samples.

SoilGrids 2.0 (ISRIC) — global soil organic carbon content and stock at 250 m
with built-in uncertainty layers (quantile random forest). CC BY 4.0.
Available on Google Earth Engine as community dataset.

Strategy:
- Sample ~10,000 points stratified by SOC quantile across India bbox
- Extract: soc_mean (g/kg), soc_stock (t/ha), soc_uncertainty (Q0.05, Q0.5, Q0.95)
- Upsert to ground_truth_samples with source="soilgrids_v2", farm_id=NULL
- Idempotent: re-runs update existing lat/lon points

Usage:
    python scripts/ingest_soilgrids.py [--n-points 10000] [--bbox india]
"""
import os
import sys
import json
import random
import argparse
from pathlib import Path
from datetime import date

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

from dotenv import load_dotenv
load_dotenv(ROOT / "backend" / ".env")

from seed_marketplace_data import run_sql, PROJECT_REF  # noqa: E402


# ─── India bounding box ───
INDIA_BBOX = [68.0, 6.0, 98.0, 38.0]  # [min_lon, min_lat, max_lon, max_lat]

# ─── SoilGrids 2.0 EE assets ───
# Community dataset paths (verify in EE Code Editor: projects/soilgrids/isric/...)
SOILGRIDS_SOC_CONTENT = "projects/soilgrids/isric/soilgrids_v2/soc_0-30cm_mean"      # g/kg
SOILGRIDS_SOC_STOCK = "projects/soilgrids/isric/soilgrids_v2/soc_0-30cm_stock"        # t/ha
SOILGRIDS_SOC_Q05 = "projects/soilgrids/isric/soilgrids_v2/soc_0-30cm_Q0.05"          # g/kg
SOILGRIDS_SOC_Q50 = "projects/soilgrids/isric/soilgrids_v2/soc_0-30cm_Q0.5"           # g/kg
SOILGRIDS_SOC_Q95 = "projects/soilgrids/isric/soilgrids_v2/soc_0-30cm_Q0.95"          # g/kg

# Fallback if community dataset paths differ — these are the standard ISRIC assets
FALLBACK_ASSETS = {
    "soc_mean": "ISRIC/SoilGrids2_0/SOC/mean_0-30cm",
    "soc_stock": "ISRIC/SoilGrids2_0/SOC_STOCK/mean_0-30cm",
    "soc_q05": "ISRIC/SoilGrids2_0/SOC/quantile_0.05_0-30cm",
    "soc_q50": "ISRIC/SoilGrids2_0/SOC/quantile_0.5_0-30cm",
    "soc_q95": "ISRIC/SoilGrids2_0/SOC/quantile_0.95_0-30cm",
}


def init_ee():
    """Initialize Earth Engine with project from env."""
    try:
        import ee
        ee.Initialize(project=os.getenv("GEE_PROJECT", "carbonsetu-496709"))
        print("Earth Engine initialized")
        return ee
    except Exception as e:
        print(f"EE init failed: {e}")
        raise


def get_soilgrids_image(ee):
    """Build a multi-band SoilGrids image with all needed bands."""
    # Try community dataset first
    try:
        img = ee.Image(SOILGRIDS_SOC_CONTENT).select([0], ["soc_mean_gkg"])
        img = img.addBands(ee.Image(SOILGRIDS_SOC_STOCK).select([0], ["soc_stock_tha"]))
        img = img.addBands(ee.Image(SOILGRIDS_SOC_Q05).select([0], ["soc_q05_gkg"]))
        img = img.addBands(ee.Image(SOILGRIDS_SOC_Q50).select([0], ["soc_q50_gkg"]))
        img = img.addBands(ee.Image(SOILGRIDS_SOC_Q95).select([0], ["soc_q95_gkg"]))
        # Test read
        img.getInfo()
        print("Using SoilGrids community dataset assets")
        return img
    except Exception as e:
        print(f"Community dataset not accessible ({e}), trying standard ISRIC assets...")

    # Fallback to standard ISRIC assets
    img = ee.Image(FALLBACK_ASSETS["soc_mean"]).select("b1").rename("soc_mean_gkg")
    img = img.addBands(ee.Image(FALLBACK_ASSETS["soc_stock"]).select("b1").rename("soc_stock_tha"))
    img = img.addBands(ee.Image(FALLBACK_ASSETS["soc_q05"]).select("b1").rename("soc_q05_gkg"))
    img = img.addBands(ee.Image(FALLBACK_ASSETS["soc_q50"]).select("b1").rename("soc_q50_gkg"))
    img = img.addBands(ee.Image(FALLBACK_ASSETS["soc_q95"]).select("b1").rename("soc_q95_gkg"))
    print("Using standard ISRIC SoilGrids 2.0 assets")
    return img


def generate_stratified_points(ee, soilgrids_img, n_points=10000, bbox=None, seed=20261004):
    """Generate points stratified by SOC quantile across the bbox."""
    bbox = bbox or INDIA_BBOX
    region = ee.Geometry.Rectangle(bbox)

    # Get SOC distribution for stratification
    print("Computing SOC histogram for stratification...")
    hist = soilgrids_img.select("soc_mean_gkg").reduceRegion(
        reducer=ee.Reducer.histogram(50, 0, 100),  # 0-100 g/kg, 50 bins
        geometry=region,
        scale=250,
        maxPixels=1e10,
        bestEffort=True
    ).getInfo()

    # Generate random points, then filter by SOC quantile to get even coverage
    # We'll oversample and bin
    rng = random.Random(seed)
    points = []

    # Generate 3x oversample
    n_gen = n_points * 3
    for _ in range(n_gen):
        lon = rng.uniform(bbox[0], bbox[2])
        lat = rng.uniform(bbox[1], bbox[3])
        points.append((lon, lat))

    print(f"Generated {len(points)} candidate points, sampling SOC values...")
    
    # Batch sample SOC at all points
    fc = ee.FeatureCollection([
        ee.Feature(ee.Geometry.Point([lon, lat]), {"idx": i})
        for i, (lon, lat) in enumerate(points)
    ])
    
    sampled = soilgrids_img.select("soc_mean_gkg").reduceRegions(
        collection=fc,
        reducer=ee.Reducer.mean(),
        scale=250
    )
    
    results = sampled.getInfo()
    features = results.get("features", [])
    
    # Bin by SOC quantile
    soc_values = []
    for f in features:
        props = f.get("properties", {})
        soc = props.get("mean")
        idx = props.get("idx")
        if soc is not None and idx is not None:
            soc_values.append((idx, soc, points[idx][0], points[idx][1]))
    
    if not soc_values:
        print("No valid SOC samples returned")
        return []
    
    # Sort by SOC and pick evenly across quantiles
    soc_values.sort(key=lambda x: x[1])
    n_bins = 10
    per_bin = n_points // n_bins
    selected = []
    
    for i in range(n_bins):
        start = (len(soc_values) * i) // n_bins
        end = (len(soc_values) * (i + 1)) // n_bins
        bin_points = soc_values[start:end]
        if bin_points:
            chosen = rng.sample(bin_points, min(per_bin, len(bin_points)))
            selected.extend(chosen)
    
    # If we need more, fill from remaining
    if len(selected) < n_points:
        remaining = [p for p in soc_values if p not in selected]
        extra = rng.sample(remaining, min(n_points - len(selected), len(remaining)))
        selected.extend(extra)
    
    # Format: (lon, lat, soc_mean)
    final_points = [(lon, lat, soc) for (_, soc, lon, lat) in selected[:n_points]]
    print(f"Selected {len(final_points)} stratified points")
    return final_points


def extract_soc_at_points(ee, soilgrids_img, points):
    """Extract all SOC bands at the given points."""
    if not points:
        return []
    
    print(f"Extracting SOC bands at {len(points)} points...")
    
    # Create feature collection
    fc = ee.FeatureCollection([
        ee.Feature(ee.Geometry.Point([lon, lat]), {"point_id": i})
        for i, (lon, lat, _) in enumerate(points)
    ])
    
    # Sample all bands
    sampled = soilgrids_img.reduceRegions(
        collection=fc,
        reducer=ee.Reducer.mean(),
        scale=250
    )
    
    results = sampled.getInfo()
    features = results.get("features", [])
    
    extracted = []
    for f in features:
        props = f.get("properties", {})
        idx = props.get("point_id")
        if idx is None:
            continue
        lon, lat, _ = points[idx]
        extracted.append({
            "longitude": round(lon, 6),
            "latitude": round(lat, 6),
            "soc_mean_gkg": props.get("soc_mean_gkg"),
            "soc_stock_tha": props.get("soc_stock_tha"),
            "soc_q05_gkg": props.get("soc_q05_gkg"),
            "soc_q50_gkg": props.get("soc_q50_gkg"),
            "soc_q95_gkg": props.get("soc_q95_gkg"),
        })
    
    print(f"Extracted {len(extracted)} valid points")
    return extracted


def sql_val(v):
    """Convert Python value to SQL literal."""
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, (dict, list)):
        return "'" + json.dumps(v).replace("'", "''") + "'"
    return "'" + str(v).replace("'", "''") + "'"


def upsert_to_ground_truth(samples, batch_size=500):
    """Upsert samples to ground_truth_samples via Management API."""
    if not samples:
        print("No samples to upsert")
        return 0
    
    print(f"Upserting {len(samples)} samples in batches of {batch_size}...")
    total_upserted = 0
    
    for i in range(0, len(samples), batch_size):
        batch = samples[i:i + batch_size]
        values = []
        for s in batch:
            # Convert SOC stock t/ha → tCO2e/ha (C to CO2 = 44/12 ≈ 3.67)
            # SoilGrids SOC stock is already in t C/ha for 0-30cm
            # Convert to tCO2e/ha for our credit engine compatibility
            stock_tha = s.get("soc_stock_tha")
            if stock_tha is not None:
                measured_soc_tco2e_ha = round(float(stock_tha) * 3.67, 3)
            else:
                # Fallback: estimate from content (g/kg) assuming bulk density ~1.3
                mean_gkg = s.get("soc_mean_gkg")
                if mean_gkg is not None:
                    measured_soc_tco2e_ha = round(float(mean_gkg) * 1.3 * 0.3 * 3.67, 3)
                else:
                    measured_soc_tco2e_ha = None
            
            values.append(
                f"({sql_val(s['longitude'])}, {sql_val(s['latitude'])}, "
                f"{sql_val(measured_soc_tco2e_ha)}, {sql_val(None)}, "
                f"{sql_val('soilgrids_v2')}, {sql_val(date.today().isoformat())}, "
                f"{sql_val(json.dumps({k: v for k, v in s.items() if k not in ['longitude', 'latitude']}))})"
            )
        
        values_str = ",\n  ".join(values)
        query = f"""
        insert into public.ground_truth_samples
          (longitude, latitude, measured_soc_tco2e_ha, measured_species_count,
           source, measured_at, notes)
        values {values_str}
        on conflict (longitude, latitude) do update set
          measured_soc_tco2e_ha = excluded.measured_soc_tco2e_ha,
          source = excluded.source,
          measured_at = excluded.measured_at,
          notes = excluded.notes;
        """
        try:
            run_sql(query)
            total_upserted += len(batch)
            print(f"  Batch {i//batch_size + 1}: {len(batch)} upserted")
        except Exception as e:
            print(f"  Batch {i//batch_size + 1} failed: {e}")
            # Continue with next batch
    
    return total_upserted


def main():
    parser = argparse.ArgumentParser(description="Ingest SoilGrids 2.0 SOC data")
    parser.add_argument("--n-points", type=int, default=10000,
                        help="Number of points to sample (default: 10000)")
    parser.add_argument("--bbox", nargs=4, type=float, default=INDIA_BBOX,
                        help="Bounding box: min_lon min_lat max_lon max_lat")
    parser.add_argument("--seed", type=int, default=20261004,
                        help="Random seed for reproducibility")
    args = parser.parse_args()
    
    print("=" * 60)
    print("SOILGRIDS 2.0 SOC INGESTION")
    print("=" * 60)
    
    try:
        ee = init_ee()
    except Exception as e:
        print(f"Failed to initialize Earth Engine: {e}")
        sys.exit(1)
    
    # Build SoilGrids image
    soilgrids_img = get_soilgrids_image(ee)
    
    # Generate stratified points
    points = generate_stratified_points(
        ee, soilgrids_img,
        n_points=args.n_points,
        bbox=args.bbox,
        seed=args.seed
    )
    
    if not points:
        print("No points generated — aborting")
        sys.exit(1)
    
    # Extract SOC values at points
    samples = extract_soc_at_points(ee, soilgrids_img, points)
    
    if not samples:
        print("No samples extracted — aborting")
        sys.exit(1)
    
    # Upsert to database
    upserted = upsert_to_ground_truth(samples)
    
    # Verify
    count_rows = run_sql("select count(*) as n from public.ground_truth_samples where source = 'soilgrids_v2';")
    print(f"\nDone. {upserted} samples upserted.")
    print(f"Total soilgrids_v2 samples in DB: {count_rows[0]['n']}")


if __name__ == "__main__":
    main()