"""Land registry lookup against the Supabase ``land_registry`` mock table."""
from typing import Optional

from app import supabase_db as db
from app.services.polygon_service import as_geojson_feature


def lookup_survey(survey_number: str) -> dict:
    """Return a normalized registry record or a not-found payload.

    Table columns: survey_number, owner_name, village, mandal, area_ha,
    geom, registry_geometry_available, tier.
    """
    survey = (survey_number or "").strip()
    if not survey:
        return {"found": False, "survey_number": survey, "message": "Survey number is required"}
    try:
        row = db.get_land_registry(survey)
    except PermissionError as exc:
        return {
            "found": False,
            "survey_number": survey,
            "error": "permission_denied",
            "message": str(exc),
        }
    except Exception as exc:
        return {"found": False, "survey_number": survey, "error": "lookup_failed", "message": str(exc)}

    if not row:
        return {"found": False, "survey_number": survey}

    geom = row.get("geom")
    geojson = as_geojson_feature(geom)
    has_geom = bool(row.get("registry_geometry_available")) or geojson is not None
    return {
        "found": True,
        "survey_number": row.get("survey_number") or survey,
        "owner_name": row.get("owner_name"),
        "village": row.get("village"),
        "mandal": row.get("mandal"),
        "area_ha": row.get("area_ha"),
        "registry_geometry_available": has_geom,
        "geojson": geojson,
        "tier_hint": row.get("tier"),
    }
