# Pilot Protocol (Draft v1.0)

**Status: NOT STARTED.** No farmers, FPOs or field samples have been enrolled
under this protocol. The demo dataset and test fixtures are not a pilot.
Last updated: 2026-10-22.

## 1. Purpose

Run a small, consent-based field pilot that tests whether the proxy estimates,
field procedures, lifecycle rules and farmer experience work in real conditions
— and publish the result even if it is negative.

The pilot is not a certification. Field validation remains
`proxy_unvalidated` until the thresholds in `docs/VALIDATION_PROTOCOL.md` are
met.

## 2. Goals and non-goals

**Goals**

1. Enrol 20–50 parcels across at least two crops and 2–3 FPOs in Telangana.
2. Collect 30+ verified annual-rate samples with frozen estimates and lab
   references.
3. Measure consent comprehension, grievance handling and data-request response.
4. Exercise listing, partial sale, retirement, refund and dispute flows with a
   controlled test buyer.
5. Publish a pilot report with errors, exclusions, costs and failures.

**Non-goals**

- Verra/Gold Standard certification or registry listing.
- Claiming measured sequestration or credit-grade MRV.
- Real-money bank/UPI settlement (payout rails remain simulated until cleared).
- Proving additionality, permanence or leakage across a full project boundary.

## 3. Participants and roles

| Role | Responsibility |
|---|---|
| Pilot lead | Protocol, timeline, external review coordination |
| Field coordinator | Farmer recruitment, consent, scheduling |
| Independent sampler | Soil sampling; must not also approve the result |
| Lab | Accredited/qualified SOC analysis with traceable reference |
| Data steward | Consent records, export/erasure requests, incident log |
| FPO officer | Member verification, local grievance first contact |
| Independent reviewer | Reviews design, consent and results; no financial interest |
| Test buyer | Exercises purchase/retirement/refund with clearly marked test funds |

## 4. Participant selection and consent

- Recruit through FPOs with an existing member relationship; no pressure to join.
- Explain in Telugu (or the farmer's preferred language), with a written/audio
  summary, that credits are proxy estimates and validation is not complete.
- Separate consent for: platform service, MRV evidence, payouts, public passport,
  research, marketing. A farmer can join without public visibility or marketing.
- Explain withdrawal, grievance contact and the 7-day acknowledgement target.
- Record consent version, language, method and timestamp.
- Do not sample a parcel without an explicit MRV-evidence consent and a
  `consent_ref`.
- Do not publish a photo of a person without a separate release.

## 5. Field procedure

1. **Eligibility:** parcel boundary, ownership/tenancy evidence, crop and
   baseline period checked; duplicate parcels excluded.
2. **Enrolment:** farmer maps the parcel; Stage 1 crop/NDVI check runs. A
   mismatch is saved PENDING for FPO review, not auto-rejected.
3. **Freeze:** the model estimate, CI90, formula version and inputs are frozen
   before sampling.
4. **Sampling:** independent sampler follows the approved design (number of
   cores, depth, compositing, bulk density, GPS, lab method). Exact procedure
   must be attached as an annex before field work.
5. **Lab:** result uploaded with lab reference; a second reviewer verifies it.
6. **Comparison:** `GET /ops/ground-truth/eval` compares frozen estimate to the
   measured rate. Stock samples only test plausibility.
7. **Follow-up:** 5-day NDVI monitoring continues; a drop ≥0.15 flags the farm
   and writes a `MONITOR` ledger event.

## 6. Transaction exercise

Use the demo/test environment first:

1. List a parcel and confirm the proxy label is visible.
2. Buy part of the listing; confirm a unique certificate and partial-sale state.
3. Retire the certificate; confirm public PDF/JSON redaction.
4. Refund the sale; confirm credits are restored and the certificate is void.
5. Open a dispute; confirm sales are frozen; resolve with release/reject/refund.
6. Reconcile wallet totals against the ledger; confirm failed settlements are
   excluded and listed as issues.

Do not move real money until R5 (financial controls) and payment-provider
approval are complete.

## 7. Success measures

| Measure | Target | Evidence |
|---|---|---|
| Parcels enrolled | ≥20 | Enrolment log |
| Verified annual-rate samples | ≥30 | Ground-truth report |
| Validation status | `field_validated_limited` **or** published failure | `/validation/status` |
| Consent comprehension | ≥80% correct on 5 key questions | Short exit survey |
| Data export requests completed | 100% within 30 days | Request log |
| Erasure requests completed or blocked with reason | 100% within 30 days | Request log |
| Grievances acknowledged | 100% within 7 days | Grievance log |
| Settlement reconciliation | 0 unresolved duplicates; all failures listed | `/wallet/reconciliation` |
| Independent review | Signed R1/R2/R4 before public claims | Review register |

A missed target is reported, not hidden. The pilot can fail and still produce a
useful result.

## 8. Issue and adverse-event reporting

Log every issue with: date, parcel/farm id, actor role, what happened, affected
money/credits, data exposed (if any), immediate mitigation, root cause, owner
and resolution date.

Immediate escalation:

- any suspected personal-data disclosure;
- any double-sale, negative balance or duplicate certificate;
- a payment settled without a ledger record;
- a farmer withdrawing consent after sampling;
- a lab result that cannot be traced;
- a conflict of interest involving a reviewer.

Do not delete evidence or ledger events during an investigation. Use refunds,
corrections and `SALE_FAILED`/incident records so history remains auditable.

## 9. Independent review

Before the first field sample:

- R1 MRV/soil scientist approves the sampling design and thresholds;
- R2 agronomist approves crop windows/factors;
- R4 ethics/consent reviewer approves the consent pack and grievance process.

After data collection:

- R1 reviews the validation report and any factor-calibration proposal;
- the pilot report is published with reviewer names, scope and dissenting views.

See `docs/INDEPENDENT_REVIEW.md`. None of these reviews is currently obtained.

## 10. Readiness checklist

- [ ] Named pilot lead and field coordinator.
- [ ] Signed FPO agreements and farmer consent forms.
- [ ] Independent sampler and qualified lab contracted.
- [ ] R1/R2/R4 reviews completed and published.
- [ ] `supabase/10_trust_controls.sql` applied to the pilot database.
- [ ] Redis-backed locks and durable ledger storage configured.
- [ ] Incident/grievance log and data-request SLA owner assigned.
- [ ] Test-buyer account and controlled funds approved.
- [ ] Baseline/estimate freeze verified on a dry run.
- [ ] Public-access matrix reviewed for the pilot's district/crop combinations.
