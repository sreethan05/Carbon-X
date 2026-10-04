FEATURE_COLS = ["NDVI","NDWI","SAVI","NDVI_STD","B4","B8","B11","B8_VAR",
                "ELEVATION","NDVI_RANGE","SEASONAL_CONTRAST"]
ARTIFACTS    = "artifacts"
DATA         = "data"
# GEE project the machine's Earth Engine auth has access to (matches backend/.env).
GEE_PROJECT  = "carbonx-507617"
GRID_SIZE    = 0.02
NDVI_MIN     = 0.02
NDVI_MAX     = 0.95
NDVI_STD_MIN = 0.0