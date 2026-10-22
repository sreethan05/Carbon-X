# Field Validation Protocol (v1.0)

**Status:** implementation complete; field data collection **not started**.
**Last updated:** 2026-10-22.
**Current public status:** `proxy_unvalidated` (0 verified rate samples).

This protocol defines how CarbonX moves from proxy estimates to an honest,
limited validation claim. It is written so an independent reviewer can reject
or amend it before any field work begins.

## 1. What is being validated

CarbonX produces an **annual sequestration rate** in
`tCO2e per hectare per year`. Validation compares that rate with independent
field measurements on the same parcel and crop cycle.

Two measurement types are deliberately separated:

| Measurement | Unit | What it can prove |
|---|---|---|
| Rate sample | tCO2e/ha/yr | Can validate the annual proxy rate |
| SOC stock sample | tCO2e/ha (0–30 cm) | Physical plausibility only; **cannot** validate a rate |

A soil stock is a snapshot. Turning it into a rate requires repeat sampling and
a known time interval. CarbonX therefore never counts stock samples toward the
30-sample rate threshold in `backend/app/services/validation.py`.

## 2. Pre-registered thresholds

These values are fixed before data collection:

- **Minimum verified rate samples:** 30
- **Mean absolute percentage error (MAPE):** ≤ 30%
- **Absolute bias:** ≤ 20%
- **90% interval coverage:** ≥ 50%

The thresholds are public, returned by `GET /validation/status`, and are not
changed after seeing results. A separate per-crop report is published, but it
does not override the pooled verdict. If the pooled data fail any threshold,
the status is `field_validation_failed`; CarbonX does not average its way to a
pass by dropping inconvenient crops.

## 3. Statuses and labels

| Status | Meaning | Public label |
|---|---|---|
| `proxy_unvalidated` | No verified rate samples | Proxy estimate — not field-validated |
| `proxy_insufficient_data` | 1–29 verified rate samples | Proxy estimate — not field-validated |
| `field_validated_limited` | Thresholds met | Field-validated (limited scope) |
| `field_validation_failed` | Enough samples, thresholds failed | Field validation failed |

Until `field_validated_limited`, every API response, passport, certificate, PDF,
CSV and UI surface must call the number a **proxy estimate**. No surface may
describe it as measured, verified sequestration or a guarantee.

## 4. Sampling design

The first pilot uses a stratified design:

1. Select parcels within one agro-climatic zone and one crop per stratum.
2. Include at least five independent farms per major crop before a per-crop
   report is shown.
3. Sample within the same crop season used by the estimate.
4. Record GPS, depth, bulk density, lab method, lab reference and sampling date.
5. Freeze the model estimate **before** the lab result is entered.
6. Require a second reviewer to mark the sample verified.

The exact number of plots, cores per plot and compositing procedure must be
approved by a qualified soil scientist before the first sample is taken.

## 5. Estimate freezing

At sampling time the system stores:

- `estimate_snapshot` — full model output and inputs
- `estimated_tco2e_ha`
- `estimated_ci90_low` / `estimated_ci90_high`
- `formula_version`

The comparison always uses that frozen estimate. A later formula release cannot
retroactively improve the validation result. The validation report also exposes
`method_version` and the formula version of every comparison.

## 6. Uncertainty and coverage

The CI90 interval is a statistical interval for a proxy estimate. It is not a
measurement guarantee. Coverage is the share of measured rates that fall inside
the frozen CI90 interval. A high coverage rate with high bias is still a failed
validation; all four thresholds must pass.

## 7. Ground-truth workflow

1. Farmer or FPO consents to sampling (`consent_ref`).
2. Field sampler records protocol metadata and GPS.
3. Lab result is uploaded with a lab reference.
4. Staff reviewer verifies the record (`verification_status=verified`).
5. `GET /ops/ground-truth/eval` recomputes the report.
6. `POST /ops/ground-truth/calibrate` may suggest per-crop factor changes when
   N ≥ 30. Suggestions are **never auto-applied**; a change requires an
   approved methodology revision and a new formula version.
7. `GET /validation/status` publishes the verdict and claim limits.

## 8. Stop rules

Field work stops and the report is reviewed when:

- a lab reference cannot be authenticated;
- the sample is outside the parcel boundary;
- the crop/season does not match the frozen estimate;
- the same lab result appears under two sample ids;
- a reviewer has a conflict of interest;
- consent is withdrawn.

Excluded samples are shown as `rejected_samples` or `pending_verification_samples`.
They are never silently deleted.

## 9. What this protocol does not establish

It does not establish registry approval, Verra/Gold Standard listing, additionality
beyond the documented baseline, permanence, leakage-free accounting, or
credit-grade measurement. Those require separate review and are listed as
pending in `docs/INDEPENDENT_REVIEW.md`.

## 10. Reference implementation

- `backend/app/services/validation.py` — thresholds, statuses, metrics, claims
- `backend/app/routes/validation_router.py` — public status/claims endpoints
- `backend/app/routes/ops_router.py` — ground-truth ingest/eval/calibrate
- `supabase/10_trust_controls.sql` — sample metadata and estimate snapshots
- `backend/tests/test_trust_program.py` — threshold and labelling tests
