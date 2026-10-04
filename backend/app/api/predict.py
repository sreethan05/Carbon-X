from fastapi import APIRouter
from app.services.ml_service import predict_score
from app.services.gee_service import get_satellite_features

router = APIRouter()

@router.post("/predict")
def predict(
    longitude: float,
    latitude: float
):

    features = get_satellite_features(
        longitude,
        latitude
    )

    score = predict_score(features)

    human_score = round(float(score) * 100, 2)

    status = "Healthy"

    if human_score < 40:
        status = "Low Biodiversity"

    elif human_score < 70:
        status = "Moderate"

    estimated_credits = round(human_score / 40, 2)

    return {
        "location": {
            "longitude": longitude,
            "latitude": latitude
        },
        "satellite_features": features,
        "biodiversity_score": human_score,
        "status": status,
        "estimated_credits": estimated_credits
    }