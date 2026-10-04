"""Single source of truth for verification tier, badge, status, and eligibility.

The frontend must never assign badges. This module decides:

- path FPO (no survey number) -> status PENDING, badge None until FPO confirms
- survey + registry geom + owner/area match -> tier 1A, badge REGISTRY
- survey + registry owner/area, geom missing -> tier 1B, badge REGISTRY_DOC
- survey not in registry -> tier 2, badge DOCUMENT
- fraud/three-source failure -> status FLAGGED, route to FPO
"""
from typing import Optional

from app.services.kyc_service import _match_name
from app.services.polygon_service import area_delta_pct

MARKETPLACE_BADGES = ("REGISTRY", "REGISTRY_DOC", "DOCUMENT", "FPO")
AREA_TOLERANCE_PCT = 20.0


def names_match(left: str, right: str) -> bool:
    if not left or not right:
        return False
    _score, ok = _match_name(left, right)
    return ok


def decide_tier(
    *,
    fpo_path: bool,
    survey_number: str = "",
    registry: Optional[dict] = None,
    owner_name: str = "",
    ocr_owner: str = "",
    claimed_area_ha: Optional[float] = None,
) -> dict:
    """Return {tier, badge, path} before fraud is applied."""
    if fpo_path or not (survey_number or "").strip():
        return {"tier": None, "badge": None, "path": "fpo"}

    found = bool(registry and registry.get("found"))
    if not found:
        return {"tier": "2", "badge": "DOCUMENT", "path": "registry"}

    has_geom = bool(registry.get("registry_geometry_available") or registry.get("geojson"))
    registry_owner = registry.get("owner_name") or ""
    owner_ok = names_match(owner_name, registry_owner) or names_match(ocr_owner, registry_owner) or names_match(owner_name, ocr_owner)
    area_ok = True
    if claimed_area_ha and registry.get("area_ha"):
        delta = area_delta_pct(float(registry["area_ha"]), float(claimed_area_ha))
        area_ok = delta is None or delta <= AREA_TOLERANCE_PCT

    if has_geom and owner_ok and area_ok:
        return {"tier": "1A", "badge": "REGISTRY", "path": "registry"}
    return {"tier": "1B", "badge": "REGISTRY_DOC", "path": "registry"}


def apply_fraud(decision: dict, fraud: dict) -> dict:
    """Merge fraud outcome. FPO path stays PENDING until confirm."""
    if decision.get("path") == "fpo":
        return {
            "tier": None,
            "badge": None,
            "risk": "LOW",
            "status": "PENDING",
            "failed_checks": [],
            "marketplace_eligible": False,
            "credits_blocked": True,
        }
    status = fraud.get("status") or "VERIFIED"
    risk = fraud.get("risk") or "LOW"
    failed = fraud.get("failed_checks") or []
    flagged = status == "FLAGGED"
    badge = None if flagged else decision.get("badge")
    return {
        "tier": decision.get("tier"),
        "badge": badge,
        "risk": risk,
        "status": status,
        "failed_checks": failed,
        "marketplace_eligible": (not flagged) and badge in MARKETPLACE_BADGES,
        "credits_blocked": flagged,
    }


def fpo_confirmed_result() -> dict:
    return {
        "tier": None,
        "badge": "FPO",
        "risk": "LOW",
        "status": "VERIFIED",
        "failed_checks": [],
        "marketplace_eligible": True,
        "credits_blocked": False,
    }


def farm_may_list(farm: Optional[dict], badge: Optional[str] = None) -> tuple[bool, str]:
    if not farm:
        return True, ""
    status = str(farm.get("status") or "").upper()
    if status in ("PENDING", "FLAGGED"):
        return False, f"Farm status {status} cannot be listed"
    farm_badge = badge or farm.get("badge")
    if farm_badge and farm_badge not in MARKETPLACE_BADGES:
        return False, f"Badge {farm_badge} is not marketplace-eligible"
    return True, ""
