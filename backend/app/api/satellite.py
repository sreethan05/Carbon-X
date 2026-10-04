from fastapi import APIRouter
from app.services.gee_service import get_satellite_features

router = APIRouter()

@router.get("/ndvi")
def ndvi():

    features = get_satellite_features()

    return {
        "satellite_features": features
    }