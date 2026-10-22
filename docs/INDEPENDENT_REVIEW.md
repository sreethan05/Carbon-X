# Independent Review Register

**Status: reviews not yet obtained.** This register exists so CarbonX does not
mistake an internal checklist for an external qualification.

Last updated: 2026-10-22.

## 1. Why this register exists

The product makes scientific, legal and financial claims. Internal tests can
show that code matches its own specification; they cannot show that the
specification is defensible. Each review below must be performed by a named
person or firm with relevant qualifications, and the signed scope must be
published or linked before the corresponding claim is shown publicly.

## 2. Required reviews

| ID | Review | Minimum qualification | Scope | Status |
|---|---|---|---|---|
| R1 | MRV / soil-carbon methodology | Soil scientist or MRV lead with agricultural SOC field experience; no commercial interest in CarbonX | Equations, baselines, additionality, uncertainty, sampling design, validation thresholds, monitoring | **NOT OBTAINED** |
| R2 | Agronomy / crop factors | Agronomist familiar with Telangana crops and conservation practices | Crop NDVI windows, crop factors, Stage 1 crop mismatch rules, practice claims | **NOT OBTAINED** |
| R3 | Privacy / DPDP | Indian privacy counsel or qualified DPO | Notice, consent, Aadhaar last-4 handling, document retention, export/erasure, processor terms, DPIA | **NOT OBTAINED** |
| R4 | Pilot ethics / consent | Independent reviewer or institutional ethics contact | Farmer recruitment, consent language, withdrawal, grievance, data minimisation, photo consent | **NOT OBTAINED** |
| R5 | Financial controls | Chartered accountant or payments/audit specialist | Split eligibility, rounding, escrow, refunds, reconciliation, payout statements | **NOT OBTAINED** |
| R6 | Registry / certification pathway | Registry-approved VVB or methodology expert | Whether the methodology can be listed/verified and what evidence is missing | **NOT OBTAINED** |
| R7 | Language / consent comprehension (native speaker) | Native Telugu and Hindi reviewer with readability experience | Telugu/Hindi UI copy and consent text, especially financial and agronomy wording (`src/context/LanguageContext.jsx`, `/trust`, `/support`) | **NOT OBTAINED** |

Statuses may change only to `IN REVIEW`, `COMPLETED` or `REJECTED`, with a
reviewer name, date, signed scope and link to the deliverable. A verbal opinion
is not completion.

## 3. Review package to send

- `docs/MRV_METHODOLOGY.md`
- `docs/VALIDATION_PROTOCOL.md`
- `docs/MODEL_CARD.md`
- `docs/PILOT_PROTOCOL.md`
- `docs/PRIVACY_DPIA.md`
- `docs/CREDIT_LIFECYCLE.md`
- `docs/PUBLIC_ACCESS.md`
- `docs/CLAIMS_ERRATA.md`
- The exact source revision under review (commit hash) and test results.

## 4. Review outcomes and claim changes

A completed review may require changing formulas, thresholds, copy or data
practices. CarbonX must record the decision in this register and in the
methodology changelog, bump the formula/policy version, and re-run validation.
Review is not a marketing badge; a negative finding is published as a negative
finding.

## 5. Sign-off template

```
Review ID:
Reviewer / firm:
Qualification and relevant experience:
Conflict-of-interest declaration:
Scope reviewed (document versions / commit):
Findings:
Required changes:
Limitations:
Decision: approved / approved with changes / rejected
Signature and date:
Public link to report:
```

## 6. Claims that remain blocked

Until the relevant review is completed:

- no claim of registry-approved or Verra/Gold Standard methodology;
- no claim of measured or lab-grade sequestration;
- no claim of credit-grade permanence or leakage accounting;
- no claim that Aadhaar/document handling is legally compliant;
- no claim of audited financial controls or real bank/UPI settlement;
- no claim that a pilot has been independently validated.
