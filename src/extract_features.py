"""Full-contract satellite feature extraction for CarbonX models.

Extracts all 33 features of the serving contract
(``backend/app/services/ml_service.py::FEATURE_ORDER``) where a real source
genuinely provides them. Missing values stay ``None`` — never fabricated,
never backfilled.

Feature sources
---------------
- Sentinel-2 SR Harmonized (2023, cloud-filtered <20%): NDVI, NDWI, SAVI,
  B4, B8, B11, red-edge indices (NDRE, IRECI, CIre), seasonal means
  (KHARIF_NDVI Jun-Oct 2023, RABI_NDVI Nov 2023-Mar 2024),
  SEASONAL_CONTRAST, time-series dispersion (NDVI_STD, B8_VAR),
  heterogeneity (NDVI_RANGE) and percentile phenology
  (NDVI_AMPLITUDE, NDVI_INTEGRAL, SOS_DOY, EOS_DOY).
- SRTM (``USGS/SRTMGL1_003``): ELEVATION, SLOPE, ASPECT.
- Sentinel-1 GRD (2023, IW, VV+VH): S1_VV, S1_VH, S1_VV_VH_RATIO,
  S1_VV_STD (temporal stdDev — a texture/coherence proxy).
- GEDI: canopy height rh98 (``LARSE/GEDI/GEDI02_A_002_MONTHLY``) and
  above-ground biomass density agbd (``LARSE/GEDI/GEDI04_A_002_MONTHLY``).
  GEDI is sparse footprint sampling — cells without shots stay ``None``.
- SoilGrids 2.0 (0-30 cm SOC): EE community/ISRIC assets first; ISRIC REST
  point query as fallback (the assets referenced in
  ``scripts/ingest_soilgrids.py`` 404 as of 2026-10-17 and the REST service
  serves some regions but returns null for others — Indian points returned
  null on that date). When the REST query works its real 0-30 cm stock is
  also recorded as ``soc_stock_rest_tha`` (t C/ha) — the honest SOC training
  target basis. If neither source returns data, every SoilGrids column stays
  ``None``: a SoilGrids dataset may not be substituted by a different
  product (e.g. OpenLandMap) under a SoilGrids band name.

Units: S2 bands are surface reflectance ×10000 (EE native), indices
dimensionless, S1 backscatter dB, GEDI rh98 metres and agbd Mg/ha, terrain
metres/degrees, SoilGrids content g/kg (REST dg/kg ÷ 10) and stock t C/ha
(content × bulk density 1.3 g/cm³ × 30 cm — the same documented
approximation as ``scripts/ingest_soilgrids.py``).
"""
import json
import os
import time
from pathlib import Path

import ee
import pandas as pd

# ─── Config ───
try:  # single source of truth with the serving config
    from config import GEE_PROJECT as _DEFAULT_GEE_PROJECT
except ImportError:  # pragma: no cover - fallback when imported as a module
    _DEFAULT_GEE_PROJECT = "carbonx-507617"
GEE_PROJECT = os.getenv("GEE_PROJECT", _DEFAULT_GEE_PROJECT)
DATA_DIR = Path(__file__).resolve().parent / "data"
DATA_DIR.mkdir(exist_ok=True)

EXTRACTION_VERSION = "v3-full-contract-2026-10-17"

# Serving contract — must stay EXACTLY aligned with
# backend/app/services/ml_service.py::FEATURE_ORDER (train.py asserts this).
FEATURE_ORDER = [
    # Core S2 (8)
    "NDVI", "NDWI", "SAVI", "B4", "B8", "B11", "NDVI_STD", "B8_VAR",
    # Red-edge (3)
    "NDRE", "IRECI", "CIre",
    # Seasonal (3)
    "KHARIF_NDVI", "RABI_NDVI", "SEASONAL_CONTRAST",
    # Heterogeneity (1)
    "NDVI_RANGE",
    # Phenology (4)
    "NDVI_AMPLITUDE", "NDVI_INTEGRAL", "SOS_DOY", "EOS_DOY",
    # Terrain (3)
    "ELEVATION", "SLOPE", "ASPECT",
    # SAR (4)
    "S1_VV", "S1_VH", "S1_VV_VH_RATIO", "S1_VV_STD",
    # GEDI (2)
    "GEDI_RH98", "GEDI_AGBD",
    # SoilGrids prior (5)
    "SOILGRIDS_SOC_MEAN", "SOILGRIDS_SOC_STOCK",
    "SOILGRIDS_SOC_Q05", "SOILGRIDS_SOC_Q50", "SOILGRIDS_SOC_Q95",
]

# Extra (non-contract) column: real ISRIC REST SoilGrids 0-30 cm stock,
# t C/ha — the target basis for the SOC model. Kept separate from the
# SOILGRIDS_SOC_* feature columns so the target source is explicit.
SOILGRIDS_TARGET_COL = "soc_stock_rest_tha"

S2_START, S2_END = "2023-01-01", "2023-12-31"
KHARIF_START, KHARIF_END = "2023-06-01", "2023-10-31"
RABI_START, RABI_END = "2023-11-01", "2024-03-31"
S1_START, S1_END = "2023-01-01", "2023-12-31"
GEDI_START, GEDI_END = "2023-01-01", "2023-12-31"
CLOUD_MAX = 20

# SoilGrids (ISRIC) — REST API v2.0 point query, no key required.
SOILGRIDS_REST_URL = "https://rest.isric.org/soilgrids/v2.0/properties/query"
SOILGRIDS_DEPTHS = ((0, 5), (5, 15), (15, 30))  # cm, standard v2 intervals
SOILGRIDS_BULK_DENSITY = 1.3  # g/cm³ — documented approximation (ingest script)
# dg/kg -> g/kg
SOILGRIDS_DGKG_TO_GKG = 10.0
# stock t C/ha = content g/kg × BD × depth(30cm) / 10
SOILGRIDS_STOCK_FACTOR = SOILGRIDS_BULK_DENSITY * 30.0 / 10.0  # = 3.9
# Probe points used once per run to decide whether the ISRIC REST service is
# actually serving data (it returned HTTP 200 with null values for every
# Indian point on 2026-10-17 while serving e.g. the Netherlands).
SOILGRIDS_PROBE_POINTS = ((78.5, 17.4), (77.3, 8.14), (88.4, 22.6))

_SOILGRIDS_EE_BANDS = {
    "soc_mean_gkg": "SOILGRIDS_SOC_MEAN",
    "soc_stock_tha": "SOILGRIDS_SOC_STOCK",
    "soc_q05_gkg": "SOILGRIDS_SOC_Q05",
    "soc_q50_gkg": "SOILGRIDS_SOC_Q50",
    "soc_q95_gkg": "SOILGRIDS_SOC_Q95",
}

_soilgrids_image = None
_soilgrids_image_checked = False
_soilgrids_rest_ok = None  # None = not probed yet


def init_ee():
    """Initialize Earth Engine."""
    ee.Initialize(project=GEE_PROJECT)
    print(f"Earth Engine initialized (project: {GEE_PROJECT})")
    get_soilgrids_image()


def _mean_reduce(image, geometry, scale, attempts=2, retry_sleep=5):
    """reduceRegion(mean) with one retry — raises after persistent failure."""
    last = None
    for attempt in range(attempts):
        try:
            return image.reduceRegion(
                reducer=ee.Reducer.mean(), geometry=geometry,
                scale=scale, maxPixels=1e9,
            ).getInfo()
        except Exception as e:  # noqa: BLE001 — retried, re-raised below
            last = e
            if attempt + 1 < attempts:
                time.sleep(retry_sleep)
    raise last


# ─── SoilGrids ───

def get_soilgrids_image():
    """EE SoilGrids multi-band image, or None when the assets are unreachable.

    Both the community assets referenced by scripts/ingest_soilgrids.py and
    the standard ISRIC assets returned 404 on 2026-10-17; keep the attempt so
    a future retrain picks them up if ISRIC restores them.
    """
    global _soilgrids_image, _soilgrids_image_checked
    if _soilgrids_image_checked:
        return _soilgrids_image
    _soilgrids_image_checked = True

    try:  # community dataset first (same paths as ingest_soilgrids.py)
        img = ee.Image("projects/soilgrids/isric/soilgrids_v2/soc_0-30cm_mean").select([0], ["soc_mean_gkg"])
        img = img.addBands(ee.Image("projects/soilgrids/isric/soilgrids_v2/soc_0-30cm_stock").select([0], ["soc_stock_tha"]))
        img = img.addBands(ee.Image("projects/soilgrids/isric/soilgrids_v2/soc_0-30cm_Q0.05").select([0], ["soc_q05_gkg"]))
        img = img.addBands(ee.Image("projects/soilgrids/isric/soilgrids_v2/soc_0-30cm_Q0.5").select([0], ["soc_q50_gkg"]))
        img = img.addBands(ee.Image("projects/soilgrids/isric/soilgrids_v2/soc_0-30cm_Q0.95").select([0], ["soc_q95_gkg"]))
        img.getInfo()  # reachability check
        print("SoilGrids: using EE community dataset assets")
        _soilgrids_image = img
        return img
    except Exception:
        pass

    try:  # standard ISRIC assets fallback
        img = ee.Image("ISRIC/SoilGrids2_0/SOC/mean_0-30cm").select("b1").rename("soc_mean_gkg")
        img = img.addBands(ee.Image("ISRIC/SoilGrids2_0/SOC_STOCK/mean_0-30cm").select("b1").rename("soc_stock_tha"))
        img = img.addBands(ee.Image("ISRIC/SoilGrids2_0/SOC/quantile_0.05_0-30cm").select("b1").rename("soc_q05_gkg"))
        img = img.addBands(ee.Image("ISRIC/SoilGrids2_0/SOC/quantile_0.5_0-30cm").select("b1").rename("soc_q50_gkg"))
        img = img.addBands(ee.Image("ISRIC/SoilGrids2_0/SOC/quantile_0.95_0-30cm").select("b1").rename("soc_q95_gkg"))
        img.getInfo()
        print("SoilGrids: using standard ISRIC EE assets")
        _soilgrids_image = img
        return img
    except Exception:
        print("SoilGrids: EE assets unavailable (404) — REST fallback only")
        _soilgrids_image = None
        return None


def fetch_soilgrids_rest(lon, lat, timeout=30, retries=2):
    """ISRIC SoilGrids 2.0 REST point query for 0-30 cm SOC (no API key).

    The endpoint used by scripts/ingest_soilgrids.py
    (``/soilproperty/query`` with ``depth=0-30cm``) now 404s / returns empty
    layers; the current v2 service serves the standard intervals
    (0-5, 5-15, 15-30 cm) which are depth-weighted here to 0-30 cm.
    REST values are dg/kg (d_factor=10) and are divided by 10 to g/kg.
    Stock is derived with the same documented approximation as the ingest
    script: content × bulk density 1.3 g/cm³ × 30 cm / 10 -> t C/ha.

    Returns a dict with real values, or None when the service has no data
    for the point (it currently returns nulls for whole regions, e.g. India
    on 2026-10-17) — never a substitute value.
    """
    import requests

    params = {
        "lon": lon, "lat": lat, "property": "soc",
        "depth": [f"{top}-{bottom}cm" for top, bottom in SOILGRIDS_DEPTHS],
        "value": ["mean", "Q0.05", "Q0.5", "Q0.95"],
    }
    last_error = None
    for attempt in range(retries + 1):
        try:
            r = requests.get(SOILGRIDS_REST_URL, params=params, timeout=timeout)
            r.raise_for_status()
            layers = r.json()["properties"]["layers"]
            soc = next((l for l in layers if l["name"] == "soc"), None)
            if soc is None:
                return None
            by_depth = {(d["range"]["top_depth"], d["range"]["bottom_depth"]): d.get("values", {})
                        for d in soc.get("depths", [])}

            def _weighted(key):
                num, wsum = 0.0, 0.0
                for depth in SOILGRIDS_DEPTHS:
                    value = by_depth.get(depth, {}).get(key)
                    if value is None:
                        return None
                    thickness = depth[1] - depth[0]
                    num += float(value) / SOILGRIDS_DGKG_TO_GKG * thickness
                    wsum += thickness
                return num / wsum

            mean_gkg = _weighted("mean")
            if mean_gkg is None:
                return None
            return {
                "soc_mean_gkg": round(mean_gkg, 3),
                "soc_stock_tha": round(mean_gkg * SOILGRIDS_STOCK_FACTOR, 3),
                "soc_q05_gkg": _weighted("Q0.05"),
                "soc_q50_gkg": _weighted("Q0.5"),
                "soc_q95_gkg": _weighted("Q0.95"),
            }
        except Exception as e:  # noqa: BLE001 — retried, then reported as None
            last_error = e
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
    print(f"  [soilgrids] REST failed for ({lon:.3f},{lat:.3f}): {type(last_error).__name__}")
    return None


def soilgrids_rest_available():
    """Probe the ISRIC REST service once per process.

    Returns True only if at least one probe point returns real values.
    ``CARBONX_SOILGRIDS_REST=0`` skips the probe (and REST usage) entirely.
    """
    global _soilgrids_rest_ok
    if _soilgrids_rest_ok is None:
        if os.getenv("CARBONX_SOILGRIDS_REST", "1") == "0":
            _soilgrids_rest_ok = False
            return False
        for i, (lon, lat) in enumerate(SOILGRIDS_PROBE_POINTS):
            if fetch_soilgrids_rest(lon, lat, retries=0) is not None:
                _soilgrids_rest_ok = True
                break
            if i + 1 < len(SOILGRIDS_PROBE_POINTS):
                time.sleep(0.5)
        else:
            _soilgrids_rest_ok = False
        print(f"SoilGrids REST available for India: {_soilgrids_rest_ok}")
    return _soilgrids_rest_ok


# ─── Per-group feature extraction ───

def compute_phenology_metrics(s2_collection):
    """Percentile-based phenology from a raw Sentinel-2 collection.

    NDVI_AMPLITUDE = max − min; NDVI_INTEGRAL = mean × 365;
    SOS_DOY / EOS_DOY = 20th / 80th percentile acquisition day-of-year —
    real percentiles of the observed series (crude seasonal markers,
    documented as such, not a fitted double-logistic model).

    NDVI and day-of-year are computed together on the raw images because
    images produced by a mapped index operation lose `system:time_start`
    (calling `.date()` on them raises in Earth Engine).
    """
    def add_ndvi_doy(img):
        ndvi = img.normalizedDifference(["B8", "B4"]).rename("NDVI")
        doy = img.date().getRelative("day", "year")
        # toInt() keeps the band type homogeneous across the collection
        # (constant() derives Byte/Short from magnitude and EE requires one type).
        return ndvi.addBands(ee.Image.constant(doy).toInt().rename("doy"))

    stats = s2_collection.map(add_ndvi_doy).select(["NDVI", "doy"]).reduce(
        ee.Reducer.percentile([20, 50, 80])
        .combine(ee.Reducer.minMax(), "", True)
        .combine(ee.Reducer.mean(), "", True)
    )
    ndvi_min = stats.select("NDVI_min")
    ndvi_max = stats.select("NDVI_max")
    return ee.Image.cat([
        ndvi_max.subtract(ndvi_min).rename("NDVI_AMPLITUDE"),
        stats.select("NDVI_mean").multiply(365).rename("NDVI_INTEGRAL"),
        stats.select("doy_p20").rename("SOS_DOY"),
        stats.select("doy_p80").rename("EOS_DOY"),
    ])


def _extract_s2(pt, feats):
    """Sentinel-2 features (core indices, red-edge, seasonal, phenology)."""
    s2_col = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
              .filterBounds(pt)
              .filterDate(S2_START, S2_END)
              .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", CLOUD_MAX)))
    # No early size check: an empty/short collection raises inside the reduce
    # and the group handler leaves S2 features None (logged by get_features).

    s2_median = s2_col.median()
    B4 = s2_median.select("B4")
    B8 = s2_median.select("B8")

    ndvi = s2_median.normalizedDifference(["B8", "B4"]).rename("NDVI")
    ndwi = s2_median.normalizedDifference(["B3", "B11"]).rename("NDWI")
    savi = s2_median.expression("((NIR-RED)/(NIR+RED+0.5))*1.5",
                                {"NIR": B8, "RED": B4}).rename("SAVI")
    ndre = s2_median.normalizedDifference(["B8", "B5"]).rename("NDRE")
    ireci = s2_median.expression(
        "(NIR - RE1) / (NIR + RE1) * (RE3 / RE2)",
        {"NIR": B8, "RE1": s2_median.select("B5"),
         "RE2": s2_median.select("B6"), "RE3": s2_median.select("B7")}
    ).rename("IRECI")
    cire = s2_median.expression("NIR / RE1 - 1",
                                {"NIR": B8, "RE1": s2_median.select("B5")}).rename("CIre")

    ndvi_col = s2_col.map(lambda i: i.normalizedDifference(["B8", "B4"]).rename("NDVI"))
    ndvi_std = ndvi_col.reduce(ee.Reducer.stdDev()).rename("NDVI_STD")
    b8_var = s2_col.map(lambda i: i.select("B8")).reduce(ee.Reducer.variance()).rename("B8_VAR")
    ndvi_range = ndvi_col.max().subtract(ndvi_col.min()).rename("NDVI_RANGE")

    bands = [ndvi, ndwi, savi, B4.rename("B4"), B8.rename("B8"),
             s2_median.select("B11").rename("B11"), ndvi_std, b8_var,
             ndre, ireci, cire]

    # Seasonal: kharif (Jun-Oct 2023) and rabi (Nov 2023 - Mar 2024).
    kharif_col = s2_col.filterDate(KHARIF_START, KHARIF_END)
    if kharif_col.size().getInfo() > 0:
        kharif_ndvi = (kharif_col.map(lambda i: i.normalizedDifference(["B8", "B4"]))
                       .mean().rename("KHARIF_NDVI"))
        bands.append(kharif_ndvi)
    else:
        kharif_ndvi = None

    rabi_col = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
                .filterBounds(pt)
                .filterDate(RABI_START, RABI_END)
                .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", CLOUD_MAX)))
    if rabi_col.size().getInfo() > 0:
        rabi_ndvi = (rabi_col.map(lambda i: i.normalizedDifference(["B8", "B4"]))
                     .mean().rename("RABI_NDVI"))
        bands.append(rabi_ndvi)
    else:
        rabi_ndvi = None

    if kharif_ndvi is not None and rabi_ndvi is not None:
        bands.append(kharif_ndvi.subtract(rabi_ndvi).rename("SEASONAL_CONTRAST"))

    bands.append(ndvi_range)
    pheno_img = compute_phenology_metrics(s2_col)
    bands.extend([pheno_img.select(name) for name in
                  ("NDVI_AMPLITUDE", "NDVI_INTEGRAL", "SOS_DOY", "EOS_DOY")])

    values = _mean_reduce(ee.Image.cat(bands), pt, 10)
    for key, value in (values or {}).items():
        if key in feats and value is not None:
            feats[key] = float(value)


def _extract_terrain(pt, feats):
    """SRTM terrain features."""
    dem = ee.Image("USGS/SRTMGL1_003")
    stack = ee.Image.cat([
        dem.select("elevation").rename("ELEVATION"),
        ee.Terrain.slope(dem).rename("SLOPE"),
        ee.Terrain.aspect(dem).rename("ASPECT"),
    ])
    for key, value in (_mean_reduce(stack, pt, 30) or {}).items():
        if key in feats and value is not None:
            feats[key] = float(value)


def _extract_sar(pt, feats):
    """Sentinel-1 GRD features (2023 IW, VV+VH)."""
    s1_col = (ee.ImageCollection("COPERNICUS/S1_GRD")
              .filterBounds(pt)
              .filterDate(S1_START, S1_END)
              .filter(ee.Filter.eq("instrumentMode", "IW"))
              .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
              .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VH")))
    if s1_col.size().getInfo() == 0:
        print("  [extract] no Sentinel-1 images — SAR features left None")
        return
    s1_median = s1_col.median()
    vv = s1_median.select("VV").rename("S1_VV")
    vh = s1_median.select("VH").rename("S1_VH")
    stack = ee.Image.cat([
        vv, vh,
        vv.divide(vh).rename("S1_VV_VH_RATIO"),
        s1_col.select("VV").reduce(ee.Reducer.stdDev()).rename("S1_VV_STD"),
    ])
    for key, value in (_mean_reduce(stack, pt, 10) or {}).items():
        if key in feats and value is not None:
            feats[key] = float(value)


def _extract_gedi(pt, feats):
    """GEDI canopy height (L2A) and AGBD (L4A) — sparse; None where no shots."""
    l2a_col = (ee.ImageCollection("LARSE/GEDI/GEDI02_A_002_MONTHLY")
               .filterBounds(pt).filterDate(GEDI_START, GEDI_END))
    l4a_col = (ee.ImageCollection("LARSE/GEDI/GEDI04_A_002_MONTHLY")
               .filterBounds(pt).filterDate(GEDI_START, GEDI_END))

    bands = []
    if l2a_col.size().getInfo() > 0:
        bands.append(l2a_col.select("rh98").median().rename("GEDI_RH98"))
    if l4a_col.size().getInfo() > 0:
        bands.append(l4a_col.select("agbd").median().rename("GEDI_AGBD"))
    if not bands:
        return  # no GEDI shots over this cell — both stay None
    try:
        values = _mean_reduce(ee.Image.cat(bands), pt, 25)
        for key, value in (values or {}).items():
            if key in feats and value is not None:
                feats[key] = float(value)
    except Exception as e:  # noqa: BLE001 — GEDI gaps are expected
        print(f"  [extract] GEDI reduce failed: {type(e).__name__}")


def _extract_soilgrids(lon, lat, pt, feats):
    """SoilGrids SOC features (EE assets first, REST fallback) + REST target."""
    sg_values = None
    image = get_soilgrids_image()
    if image is not None:
        try:
            sg_values = _mean_reduce(image, pt, 250)
        except Exception as e:  # noqa: BLE001 — real data or None
            print(f"  [extract] SoilGrids EE reduce failed: {type(e).__name__}")

    if sg_values:
        for band, feature in _SOILGRIDS_EE_BANDS.items():
            value = sg_values.get(band)
            if value is not None:
                feats[feature] = float(value)

    if soilgrids_rest_available():
        rest = fetch_soilgrids_rest(lon, lat)
        if rest:
            if not sg_values:  # EE assets dead → REST is the feature source
                feats["SOILGRIDS_SOC_MEAN"] = rest["soc_mean_gkg"]
                feats["SOILGRIDS_SOC_STOCK"] = rest["soc_stock_tha"]
                feats["SOILGRIDS_SOC_Q05"] = rest["soc_q05_gkg"]
                feats["SOILGRIDS_SOC_Q50"] = rest["soc_q50_gkg"]
                feats["SOILGRIDS_SOC_Q95"] = rest["soc_q95_gkg"]
            # The REST 0-30 cm stock is the explicit SOC target basis —
            # recorded even when the EE features worked (different product).
            feats[SOILGRIDS_TARGET_COL] = rest["soc_stock_tha"]


def get_features(lat, lon, buffer=1500):
    """Extract the full FEATURE_ORDER set for one point.

    Returns a dict with every FEATURE_ORDER key plus SOILGRIDS_TARGET_COL;
    values that genuinely could not be extracted from a real source stay
    None. Feature groups that fail are logged and left None — a group
    failure never fabricates a value.
    """
    pt = ee.Geometry.Point([lon, lat]).buffer(buffer)
    feats = {key: None for key in FEATURE_ORDER}
    feats[SOILGRIDS_TARGET_COL] = None

    for name, fn in (
        ("S2", lambda: _extract_s2(pt, feats)),
        ("terrain", lambda: _extract_terrain(pt, feats)),
        ("SAR", lambda: _extract_sar(pt, feats)),
        ("GEDI", lambda: _extract_gedi(pt, feats)),
        ("SoilGrids", lambda: _extract_soilgrids(lon, lat, pt, feats)),
    ):
        try:
            fn()
        except Exception as e:  # noqa: BLE001 — group stays None
            print(f"  [extract] {name} group failed at ({lat},{lon}): "
                  f"{type(e).__name__}: {str(e)[:160]}")
    return feats


if __name__ == "__main__":
    # Smoke test on the first richness cell (no CSV writes).
    init_ee()
    richness = pd.read_csv(DATA_DIR / "species_richness_weighted.csv")
    row = richness.iloc[0]
    t0 = time.time()
    values = get_features(row["latitude"], row["longitude"])
    print(json.dumps(values, indent=1))
    print(f"elapsed: {time.time() - t0:.1f}s")
