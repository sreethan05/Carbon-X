# Unit Economics & Business Model

All figures are stated assumptions, not audited results. The live simulation
behind them: `python scripts/simulate_scale.py` (runs the real credit/split
engines over synthetic farms).

## Cost to verify one farm (per year)

| Item | Legacy MRV | CarbonX |
|---|---|---|
| Soil lab tests (₹2,000+, multiple) | ₹4,000–8,000 | ₹0 (proxy + uncertainty deduction) |
| Field agent visits | ₹500–1,500/visit | ₹0 (farmer's phone; FPO assists on exceptions) |
| Satellite monitoring (73 five-day cycles) | — | ~₹29 (free-tier processing amortised + egress) |
| **Total/farm/yr** | **₹5,000–10,000** | **≈ ₹29–100** (audit reserve included) |

That ~50–100× cost collapse is the entire thesis: at legacy cost, a 1-hectare
farm's verification bill exceeds its credit income; at CarbonX cost it is
noise.

## Revenue per farm (assumptions shown)

- Avg verified credits/farm/yr: **40 tCO₂e** (matches demo farms: 33–138).
- Price band **₹400–650/credit**, benchmark ₹340 by badge. For context,
  voluntary-market prices commonly clear at $12–60 (~₹1,000–5,000); the
  platform's band is deliberately conservative for Indian voluntary buyers —
  headroom, not a ceiling. Pricing logic: BEE/CCTS compliance prices set the
  national ceiling; Indian voluntary agri credits clear below that; platform
  takes the conservative end to keep the 70% farmer floor credible.
- Gross/farm/yr at benchmark: 40 × ₹450 ≈ **₹18,000**.
- Farmer keeps **₹12,600 (70% floor)**; FPO ₹900 when involved; platform
  ₹4,500.

## Platform revenue streams (beyond the 25% platform share)

1. **MRV-as-a-service** for existing agri-platforms (the verification engine
   is API-first).
2. **Buyer subscriptions** — portfolio dashboards, retirement certificates,
   audit exports for ESG reporting (Scope 1/2/3 retirement scopes already
   modelled).
3. **Certification fee** per retirement (flat, quoted on certificate).
4. **Data licensing** — aggregate, privacy-preserving ecosystem analytics
   (farmer-identifying data never leaves the platform; DPDP-aligned).
5. **Biodiversity/water credits** on the same verification rails (Phase 3).

## Break-even

From the scale simulation: satellite + infra cost ≈ ₹29/farm/yr against a
platform take of ₹4,500/farm → **break-even at ~649 farms**; everything past
that funds the FPO field network and calibration studies. A single mid-size
FPO (200–500 members) clears break-even in its first season.

## The split, defended against incumbents

| Platform | Documented farmer experience |
|---|---|
| Legacy intermediaries | Up to **70% of credit value diverted** (CarbonX research docs) |
| Boomitra-type aggregators | Farmer share opaque; long contracts; delayed payments reported |
| **CarbonX** | **70% floor, code-enforced (`split_engine`, paise-integer), hash-anchored payout lines the farmer can audit; FPO 5% only when involvement is proven — no work, no cut** |

The floor is not a promise — it is an invariant with tests
(`backend/tests/test_trust_layer.py::SplitEngineTests`).
