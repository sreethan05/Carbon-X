"""Sequential fraud checks for land verification.

Order: Aadhaar checksum, OCR readability, EXIF, village geocode,
duplicate document, name-pattern match, polygon overlap.

Any hard failure -> risk HIGH, status FLAGGED, route to FPO.
Area mismatch is a warning (three-source validation), not a hard fail.
"""
from typing import Optional

from app.services.kyc_service import validate_aadhaar, _match_name
from app.services.polygon_service import polygons_overlap, polygon_area_hectares, area_delta_pct

AREA_TOLERANCE_PCT = 20.0
NDVI_FARMLAND_MIN = 0.15


def run_fraud_checks(
    *,
    aadhaar: str = "",
    checks: dict,
    owner_name: str = "",
    ocr_text: str = "",
    village: str = "",
    geojson: Optional[dict] = None,
    other_farm_geojsons: Optional[list] = None,
    claimed_area_ha: Optional[float] = None,
    skip_ocr: bool = False,
    skip_ndvi: bool = False,
) -> dict:
    failed = []
    warnings = []

    digits = str(aadhaar or "").replace(" ", "").replace("-", "")
    if digits and not digits.upper().startswith("X") and len(digits) >= 12:
        if not validate_aadhaar(aadhaar):
            failed.append("aadhaar_checksum")

    if not skip_ocr:
        if not checks.get("image_readable"):
            failed.append("ocr_readability")
        elif not checks.get("ocr_available") and not (ocr_text or "").strip():
            failed.append("ocr_readability")
        if not checks.get("exif_present"):
            failed.append("exif_validation")

    if village and not checks.get("geocoded_location"):
        failed.append("village_geocode")

    if checks.get("duplicate_detected"):
        failed.append("duplicate_document")

    if not skip_ocr and owner_name:
        _score, matched = _match_name(owner_name, ocr_text or checks.get("ocr_text_preview") or "")
        if not matched and not checks.get("name_match"):
            failed.append("name_pattern")

    if geojson and other_farm_geojsons:
        for other in other_farm_geojsons:
            if other and polygons_overlap(geojson, other):
                failed.append("polygon_overlap")
                break

    measured = polygon_area_hectares(geojson) if geojson else None
    delta = area_delta_pct(claimed_area_ha, measured)
    if delta is not None and delta > AREA_TOLERANCE_PCT:
        warnings.append("area_mismatch")

    ndvi = (checks.get("satellite_ndvi") or {}).get("ndvi")
    if not skip_ndvi and ndvi is not None and float(ndvi) < NDVI_FARMLAND_MIN:
        warnings.append("ndvi_barren")

    hard = [c for c in failed]
    if hard:
        risk, status = "HIGH", "FLAGGED"
    elif warnings:
        risk, status = "MEDIUM", "FLAGGED"
        failed.extend(warnings)
    else:
        risk, status = "LOW", "VERIFIED"

    return {
        "risk": risk,
        "status": status,
        "failed_checks": failed,
        "warnings": warnings,
        "measured_area_ha": measured,
        "area_delta_pct": delta,
    }
