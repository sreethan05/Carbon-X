"""Public field-validation status for carbon estimates.

These endpoints exist so a farmer, buyer, auditor or journalist can check the
*evidence state* of the numbers CarbonX shows, without trusting a marketing
page.  The default public view is aggregate only (no farm ids or lab refs);
staff get the row-level comparisons.
"""
from typing import Optional

from fastapi import APIRouter, Depends

from app.security import get_current_user_optional
from app.services import validation
from app.routes.ops_router import _validation_report

router = APIRouter(prefix="/validation", tags=["validation"])

_STAFF_ROLES = {"admin", "verifier", "fpo"}


def _is_staff(user: Optional[dict]) -> bool:
    return str((user or {}).get("role") or "").lower() in _STAFF_ROLES


@router.get("/status")
def validation_status(current_user: Optional[dict] = Depends(get_current_user_optional)):
    """Current validation verdict, thresholds and honest claim limits.

    ``status`` is one of ``proxy_unvalidated``, ``proxy_insufficient_data``,
    ``field_validated_limited`` or ``field_validation_failed``.  Until it is
    ``field_validated_limited`` every credit figure must stay labelled as a
    proxy estimate in the API, UI, PDFs and CSV exports.
    """
    report = _validation_report()
    body = report if _is_staff(current_user) else validation.public_view(report)
    return {
        "success": True,
        "status": report["status"],
        "public_label": report["public_label"],
        "proxy_estimate": report["proxy_estimate"],
        "generated_at": report["generated_at"],
        "thresholds": report["thresholds"],
        "counts": {
            "samples_total": report["samples_total"],
            "verified_rate_samples": report["verified_rate_samples"],
            "pending_verification_samples": report["pending_verification_samples"],
            "rejected_samples": report["rejected_samples"],
            "stock_reference_samples": report["stock_reference_samples"],
        },
        "metrics": report["metrics"],
        "per_crop": body.get("per_crop", {}),
        "stock_plausibility": report.get("stock_plausibility"),
        "supported_claims": report["supported_claims"],
        "unsupported_claims": report["unsupported_claims"],
        "report": body,
    }


@router.get("/claims")
def validation_claims():
    """The claim limits in one place, for the UI and docs to quote verbatim."""
    return {
        "success": True,
        "proxy_label": validation.PUBLIC_LABEL,
        "validated_label": validation.PUBLIC_LABEL_VALIDATED,
        "failed_label": validation.PUBLIC_LABEL_FAILED,
        "minimum_samples": validation.MIN_VALIDATION_SAMPLES,
        "thresholds": {
            "max_mape_pct": validation.MAX_VALIDATION_MAPE,
            "max_abs_bias_pct": validation.MAX_VALIDATION_BIAS,
            "min_ci90_coverage_pct": validation.MIN_CI90_COVERAGE,
        },
        "supported_claims": validation.SUPPORTED_CLAIMS,
        "unsupported_claims": validation.UNSUPPORTED_CLAIMS,
        "method_version": "field-validation-v1",
    }
