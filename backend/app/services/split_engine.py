"""Conditional payment-split engine.

CarbonX payout model (from the platform spec):

- Farmer 70% floor — never diluted, paid via UPI/bank.
- FPO 5% only when its involvement is proven (onboarding/verification work).
- Platform takes the remainder: 25% when an FPO was involved (4-way split),
  30% when not (3-way split).

All arithmetic runs in paise (integer) so no rupee is lost or invented to
rounding; the residue from flooring goes to the platform share.
"""

FARMER_SHARE = 0.70
FPO_SHARE = 0.05


def _inr(paise: int) -> float:
    return round(paise / 100.0, 2)


def compute_split(gross_inr: float, fpo_involved: bool, fpo_name: str = "") -> dict:
    """Split a gross sale amount into the conditional payout lines."""
    gross_p = int(round(float(gross_inr or 0) * 100))
    farmer_p = int(gross_p * FARMER_SHARE)
    fpo_p = int(gross_p * FPO_SHARE) if fpo_involved else 0
    platform_p = gross_p - farmer_p - fpo_p

    lines = [
        {
            "recipient": "Farmer",
            "share_pct": round(farmer_p / gross_p * 100, 2) if gross_p else 0.0,
            "amount_inr": _inr(farmer_p),
            "route": "UPI / bank payout",
            "note": "70% floor — guaranteed",
        }
    ]
    if fpo_involved:
        lines.append(
            {
                "recipient": "FPO",
                "share_pct": round(fpo_p / gross_p * 100, 2) if gross_p else 0.0,
                "amount_inr": _inr(fpo_p),
                "route": "FPO account",
                "note": f"Earned — verification work proven{f' ({fpo_name})' if fpo_name else ''}",
            }
        )
    lines.append(
        {
            "recipient": "Platform",
            "share_pct": round(platform_p / gross_p * 100, 2) if gross_p else 0.0,
            "amount_inr": _inr(platform_p),
            "route": "Platform retention",
            "note": "Operations + monitoring",
        }
    )

    return {
        "model": "4-way" if fpo_involved else "3-way",
        "fpo_involved": bool(fpo_involved),
        "fpo_name": fpo_name or None,
        "gross_inr": _inr(gross_p),
        "farmer_amount_inr": _inr(farmer_p),
        "fpo_amount_inr": _inr(fpo_p),
        "platform_amount_inr": _inr(platform_p),
        "lines": lines,
    }
