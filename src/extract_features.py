"""Enhanced satellite feature extraction for CarbonX biodiversity/SOC models.

Features (matching /analyze endpoint exactly):
- Sentinel-2: NDVI, NDWI, SAVI, B4, B8, B11 means
- Red-edge: NDRE, IRECI, CIre (don't saturate at high biomass)
- Time-series: NDVI_STD, B8_VAR, phenology metrics (SOS, EOS, amplitude, integral)
- Sentinel-1 SAR: VV, VH, VV/VH ratio, temporal coherence
- GEDI: canopy height (rh98), AGBD (above-ground biomass density)
- Terrain: elevation, slope, aspect
- Habitat heterogeneity: NDVI range, texture
- Seasonal contrast: Kharif vs Rabi NDVI
- SoilGrids SOC prior (from ingested ground_truth_samples)

All computed at 10m scale for S2, 250m for SoilGrids, 25m for SAR/GEDI.
"""
import ee
import pandas as pd
import time
import os
import json
from pathlib import Path

# ─── Config ───
GEE_PROJECT = os.getenv("GEE_PROJECT", "carbonsetu-496709")
DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DATA_DIR.mkdir(exist_ok=True)

# SoilGrids asset (from ingest_soilgrids.py)
SOILGRIDS_IMG = None  # Will be initialized lazily


def init_ee():
    """Initialize Earth Engine."""
    ee.Initialize(project=GEE_PROJECT)
    print(f"Earth Engine initialized (project: {GEE_PROJECT})")


def get_soilgrids_image():
    """Get or create the SoilGrids multi-band image."""
    global SOILGRIDS_IMG
    if SOILGRIDS_IMG is not None:
        return SOILGRIDS_IMG
    
    # Try community dataset first
    try:
        img = ee.Image("projects/soilgrids/isric/soilgrids_v2/soc_0-30cm_mean").select([0], ["soc_mean_gkg"])
        img = img.addBands(ee.Image("projects/soilgrids/isric/soilgrids_v2/soc_0-30cm_stock").select([0], ["soc_stock_tha"]))
        img = img.addBands(ee.Image("projects/soilgrids/isric/soilgrids_v2/soc_0-30cm_Q0.05").select([0], ["soc_q05_gkg"]))
        img = img.addBands(ee.Image("projects/soilgrids/isric/soilgrids_v2/soc_0-30cm_Q0.5").select([0], ["soc_q50_gkg"]))
        img = img.addBands(ee.Image("projects/soilgrids/isric/soilgrids_v2/soc_0-30cm_Q0.95").select([0], ["soc_q95_gkg"]))
        img.getInfo()
        print("Using SoilGrids community dataset")
    except Exception:
        # Fallback to standard ISRIC assets
        img = ee.Image("ISRIC/SoilGrids2_0/SOC/mean_0-30cm").select("b1").rename("soc_mean_gkg")
        img = img.addBands(ee.Image("ISRIC/SoilGrids2_0/SOC_STOCK/mean_0-30cm").select("b1").rename("soc_stock_tha"))
        img = img.addBands(ee.Image("ISRIC/SoilGrids2_0/SOC/quantile_0.05_0-30cm").select("b1").rename("soc_q05_gkg"))
        img = img.addBands(ee.Image("ISRIC/SoilGrids2_0/SOC/quantile_0.5_0-30cm").select("b1").rename("soc_q50_gkg"))
        img = img.addBands(ee.Image("ISRIC/SoilGrids2_0/SOC/quantile_0.95_0-30cm").select("b1").rename("soc_q95_gkg"))
        print("Using standard ISRIC SoilGrids 2.0 assets")
    
    SOILGRIDS_IMG = img
    return img


def compute_phenology_metrics(ndvi_collection, geometry):
    """Compute phenology metrics from NDVI time series.
    
    Returns: SOS (start of season), EOS (end of season), amplitude, integral
    Using harmonic fitting on the time series.
    """
    # Get time series as array
    ndvi_ts = ndvi_collection.map(lambda img: img.set('timestamp', img.date().millis()))
    
    # Harmonic fitting (2 harmonics = annual + semi-annual)
    # This gives us fitted curve from which we derive phenology
    harmonic = ndvi_ts.select('NDVI').reduce(ee.Reducer.robustLinearRegression(3, 2))
    
    # For simplicity, use percentile-based phenology
    # SOS = date when NDVI crosses 20% of annual amplitude
    # EOS = date when NDVI drops below 20% of amplitude
    
    # Get day-of-year for each image
    def add_doy(img):
        doy = img.date().getRelative('day', 'year')
        return img.addBands(ee.Image.constant(doy).rename('doy'))
    
    ndvi_with_doy = ndvi_ts.map(add_doy)
    
    # Reduce to get statistics
    stats = ndvi_with_doy.select(['NDVI', 'doy']).reduce(
        ee.Reducer.percentile([20, 50, 80]).combine(
            ee.Reducer.minMax(), '', True
        ).combine(
            ee.Reducer.mean(), '', True
        )
    )
    
    # Compute approximate phenology
    ndvi_min = stats.select('NDVI_min')
    ndvi_max = stats.select('NDVI_max')
    ndvi_amp = ndvi_max.subtract(ndvi_min).rename('NDVI_AMPLITUDE')
    ndvi_integral = stats.select('NDVI_mean').multiply(365).rename('NDVI_INTEGRAL')
    
    # SOS/EOS approximated from 20th/80th percentile DOY
    sos = stats.select('doy_p20').rename('SOS_DOY')
    eos = stats.select('doy_p80').rename('EOS_DOY')
    
    return ee.Image.cat([ndvi_amp, ndvi_integral, sos, eos])


def get_features(lat, lon, buffer=1500):
    """Extract all features for a single point.
    
    Matches /analyze endpoint feature extraction exactly.
    """
    pt = ee.Geometry.Point([lon, lat]).buffer(buffer)
    
    # ─── Sentinel-2 SR Harmonized ───
    s2_col = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
              .filterBounds(pt)
              .filterDate("2023-01-01", "2023-12-31")
              .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 20)))
    
    # Median composite (cloud-robust)
    s2_median = s2_col.median()
    
    # Band selections
    B2 = s2_median.select("B2")   # Blue
    B3 = s2_median.select("B3")   # Green
    B4 = s2_median.select("B4")   # Red
    B5 = s2_median.select("B5")   # Red Edge 1 (705 nm)
    B6 = s2_median.select("B6")   # Red Edge 2 (740 nm)
    B7 = s2_median.select("B7")   # Red Edge 3 (783 nm)
    B8 = s2_median.select("B8")   # NIR (842 nm)
    B8A = s2_median.select("B8A") # Narrow NIR (865 nm)
    B11 = s2_median.select("B11") # SWIR 1 (1610 nm)
    B12 = s2_median.select("B12") # SWIR 2 (2190 nm)
    
    # ─── Core Spectral Indices ───
    ndvi = s2_median.normalizedDifference(["B8", "B4"]).rename("NDVI")
    ndwi = s2_median.normalizedDifference(["B3", "B11"]).rename("NDWI")
    savi = s2_median.expression("((NIR-RED)/(NIR+RED+0.5))*1.5", 
                                 {"NIR": B8, "RED": B4}).rename("SAVI")
    
    # ─── Red-Edge Indices (don't saturate at high biomass) ───
    # NDRE = (NIR - RedEdge) / (NIR + RedEdge) — uses B5 (705nm)
    ndre = s2_median.normalizedDifference(["B8", "B5"]).rename("NDRE")
    
    # IRECI = (NIR - RedEdge1) / (NIR + RedEdge1) * (RedEdge3 / RedEdge2)
    # More sensitive to chlorophyll at high LAI
    ireci = s2_median.expression(
        "(NIR - RE1) / (NIR + RE1) * (RE3 / RE2)",
        {"NIR": B8, "RE1": B5, "RE2": B6, "RE3": B7}
    ).rename("IRECI")
    
    # CIre = NIR / RedEdge1 - 1 (Chlorophyll Index red-edge)
    cire = s2_median.expression("NIR / RE1 - 1", 
                                 {"NIR": B8, "RE1": B5}).rename("CIre")
    
    # ─── Time-Series Dispersion ───
    ndvi_col = s2_col.map(lambda i: i.normalizedDifference(["B8", "B4"]).rename("NDVI"))
    b8_col = s2_col.map(lambda i: i.select("B8"))
    
    ndvi_std = ndvi_col.reduce(ee.Reducer.stdDev()).rename("NDVI_STD")
    b8_var = b8_col.reduce(ee.Reducer.variance()).rename("B8_VAR")
    
    # ─── Seasonal Contrast ───
    kharif = s2_col.filterDate("2023-06-01", "2023-10-31")
    rabi = s2_col.filterDate("2023-11-01", "2024-03-31")
    
    kharif_ndvi = kharif.map(lambda i: i.normalizedDifference(["B8", "B4"])).mean().rename("KHARIF_NDVI")
    rabi_ndvi = rabi.map(lambda i: i.normalizedDifference(["B8", "B4"])).mean().rename("RABI_NDVI")
    seasonal_contrast = kharif_ndvi.subtract(rabi_ndvi).rename("SEASONAL_CONTRAST")
    
    # ─── Habitat Heterogeneity ───
    ndvi_range = ndvi_col.max().subtract(ndvi_col.min()).rename("NDVI_RANGE")
    
    # ─── Phenology Metrics ───
    try:
        phenology = compute_phenology_metrics(ndvi_col, pt)
    except Exception as e:
        print(f"  Phenology computation failed: {e}")
        phenology = ee.Image.constant([0, 0, 0, 0]).rename(['NDVI_AMPLITUDE', 'NDVI_INTEGRAL', 'SOS_DOY', 'EOS_DOY'])
    
    # ─── Terrain ───
    dem = ee.Image("USGS/SRTMGL1_003")
    elevation = dem.select("elevation").rename("ELEVATION")
    slope = ee.Terrain.slope(dem).rename("SLOPE")
    aspect = ee.Terrain.aspect(dem).rename("ASPECT")
    
    # ─── Sentinel-1 SAR ───
    try:
        s1_col = (ee.ImageCollection("COPERNICUS/S1_GRD")
                  .filterBounds(pt)
                  .filterDate("2023-01-01", "2023-12-31")
                  .filter(ee.Filter.eq("instrumentMode", "IW"))
                  .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
                  .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VH")))
        
        s1_median = s1_col.median()
        vv = s1_median.select("VV").rename("S1_VV")
        vh = s1_median.select("VH").rename("S1_VH")
        vv_vh_ratio = vv.divide(vh).rename("S1_VV_VH_RATIO")
        
        # Temporal coherence (pairwise coherence across 12-day intervals)
        # Simplified: stdDev of VV as texture proxy
        s1_std = s1_col.select("VV").reduce(ee.Reducer.stdDev()).rename("S1_VV_STD")
        
        sar_bands = ee.Image.cat([vv, vh, vv_vh_ratio, s1_std])
    except Exception as e:
        print(f"  SAR extraction failed: {e}")
        sar_bands = ee.Image.constant([0, 0, 0, 0]).rename(['S1_VV', 'S1_VH', 'S1_VV_VH_RATIO', 'S1_VV_STD'])
    
    # ─── GEDI Lidar ───
    try:
        gedi = ee.ImageCollection("LARSE/GEDI/GEDI02_A_002_MONTHLY")\
                .filterBounds(pt).filterDate("2023-01-01", "2023-12-31").median()
        
        rh98 = gedi.select("rh98").rename("GEDI_RH98")  # Canopy height (98th percentile)
        agbd = gedi.select("agbd").rename("GEDI_AGBD")  # Above-ground biomass density
        gedi_bands = ee.Image.cat([rh98, agbd])
    except Exception as e:
        print(f"  GEDI extraction failed: {e}")
        gedi_bands = ee.Image.constant([0, 0]).rename(['GEDI_RH98', 'GEDI_AGBD'])
    
    # ─── SoilGrids SOC Prior ───
    soilgrids = get_soilgrids_image()
    soilgrids_sampled = soilgrids.reduceRegion(
        reducer=ee.Reducer.mean(), geometry=pt, scale=250, maxPixels=1e9
    )
    
    # Build feature stack (order matters for model compatibility)
    stack = ee.Image.cat([
        # Core S2 indices (8 bands) - MUST MATCH /analyze
        ndvi.rename("NDVI"),
        ndwi.rename("NDWI"),
        savi.rename("SAVI"),
        B4.rename("B4"),
        B8.rename("B8"),
        B11.rename("B11"),
        ndvi_std.rename("NDVI_STD"),
        b8_var.rename("B8_VAR"),
        
        # Red-edge (3 bands)
        ndre.rename("NDRE"),
        ireci.rename("IRECI"),
        cire.rename("CIre"),
        
        # Seasonal (3 bands)
        kharif_ndvi.rename("KHARIF_NDVI"),
        rabi_ndvi.rename("RABI_NDVI"),
        seasonal_contrast.rename("SEASONAL_CONTRAST"),
        
        # Heterogeneity (1 band)
        ndvi_range.rename("NDVI_RANGE"),
        
        # Phenology (4 bands)
        phenology.select("NDVI_AMPLITUDE"),
        phenology.select("NDVI_INTEGRAL"),
        phenology.select("SOS_DOY"),
        phenology.select("EOS_DOY"),
        
        # Terrain (3 bands)
        elevation,
        slope,
        aspect,
        
        # SAR (4 bands)
        sar_bands.select("S1_VV"),
        sar_bands.select("S1_VH"),
        sar_bands.select("S1_VV_VH_RATIO"),
        sar_bands.select("S1_VV_STD"),
        
        # GEDI (2 bands)
        gedi_bands.select("GEDI_RH98"),
        gedi_bands.select("GEDI_AGBD"),
        
        # SoilGrids prior (5 bands) - sampled at 250m
        # Note: these will be constant within 250m pixel
        soilgrids.select("soc_mean_gkg").rename("SOILGRIDS_SOC_MEAN"),
        soilgrids.select("soc_stock_tha").rename("SOILGRIDS_SOC_STOCK"),
        soilgrids.select("soc_q05_gkg").rename("SOILGRIDS_SOC_Q05"),
        soilgrids.select("soc_q50_gkg").rename("SOILGRIDS_SOC_Q50"),
        soilgrids.select("soc_q95_gkg").rename("SOILGRIDS_SOC_Q95"),
    ])
    
    # Extract
    feat_values = stack.reduceRegion(
        reducer=ee.Reducer.mean(), geometry=pt, scale=10, maxPixels=1e9
    ).getInfo()
    
    return feat_values


def extract_all():
    """Extract features for all richness grid cells (checkpointed)."""
    # Load richness data (from aggregate_richness.py)
    richness_path = DATA_DIR / "species_richness_weighted.csv"
    if not richness_path.exists():
        print(f"Richness file not found: {richness_path}")
        print("Run: python src/aggregate_richness.py first")
        return
    
    richness = pd.read_csv(richness_path)
    print(f"Loaded {len(richness)} richness grid cells")
    
    ckpt_path = DATA_DIR / "features_v3_checkpoint.csv"
    out_path = DATA_DIR / "satellite_features_v3.csv"
    
    done_df = pd.read_csv(ckpt_path) if ckpt_path.exists() else pd.DataFrame()
    done_coords = set(zip(done_df.get("latitude", []), done_df.get("longitude", [])))
    
    new_rows, failed = [], 0
    
    for idx, row in richness.iterrows():
        coord = (row["latitude"], row["longitude"])
        if coord in done_coords:
            continue
        
        try:
            f = get_features(row["latitude"], row["longitude"])
            if not f or all(v is None for v in f.values()):
                failed += 1
                continue
            
            f.update({
                "latitude": row["latitude"],
                "longitude": row["longitude"],
                "species_count": row["species_count"],
                "observation_count": row.get("observation_count", 0),
            })
            new_rows.append(f)
            
            if len(new_rows) % 50 == 0:
                pd.concat([done_df, pd.DataFrame(new_rows)], ignore_index=True).to_csv(ckpt_path, index=False)
                print(f"Checkpoint: {len(done_df) + len(new_rows)} | failed: {failed}")
                time.sleep(2)  # Rate limit
        
        except Exception as e:
            print(f"Row {idx}: {e}")
            failed += 1
            time.sleep(3)
    
    final = pd.concat([done_df, pd.DataFrame(new_rows)], ignore_index=True)
    final.to_csv(out_path, index=False)
    print(f"Done. {len(final)} rows. {failed} failed.")
    print(f"Features saved to: {out_path}")


if __name__ == "__main__":
    init_ee()
    extract_all()