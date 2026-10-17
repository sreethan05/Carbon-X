from pathlib import Path

# Full 33-feature serving contract matching extract_features.py, train.py, and ml_service.py
FEATURE_COLS = [
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

V2_FEATURE_COLS = ["NDVI", "NDWI", "SAVI", "NDVI_STD", "B4", "B8", "B11", "B8_VAR",
                   "ELEVATION", "NDVI_RANGE", "SEASONAL_CONTRAST"]

ARTIFACTS    = str(Path(__file__).resolve().parent.parent / "backend" / "ml" / "models")
DATA         = str(Path(__file__).resolve().parent / "data")
# GEE project the machine's Earth Engine auth has access to (matches backend/.env).
GEE_PROJECT  = "carbonx-507617"
GRID_SIZE    = 0.02
NDVI_MIN     = 0.02
NDVI_MAX     = 0.95
NDVI_STD_MIN = 0.0