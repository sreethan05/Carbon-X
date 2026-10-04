from fastapi import APIRouter
from pydantic import BaseModel
from typing import List

router = APIRouter()

class Point(BaseModel):
    lat: float
    lng: float

class PolygonRequest(BaseModel):
    polygon: List[Point]

@router.post("/analyze")
def analyze_area(data: PolygonRequest):

    polygon_points = data.polygon

    # TEMPORARY ESTIMATION
    estimated_hectares = len(polygon_points) * 2.5

    carbon_rate = 8.5

    total_credits = estimated_hectares * carbon_rate

    market_price = total_credits * 12

    return {

        "estimated_hectares": round(
            estimated_hectares,
            2
        ),

        "carbon_density_score": 82,

        "estimated_credits": round(
            total_credits,
            2
        ),

        "market_value_usd": round(
            market_price,
            2
        ),

        "environmental_impact": "Moderate vegetation density with strong carbon sequestration potential."

    }