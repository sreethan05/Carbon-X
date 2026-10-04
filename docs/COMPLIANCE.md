# Legal, Regulatory & Compliance Posture

**Not legal advice.** This documents the platform's current design posture
and its roadmap to formal compliance. A compliance review is Phase 1 of the
roadmap (docs/ROADMAP.md).

## India's Carbon Credit Trading Scheme (CCTS)

- CCTS (2023) binds ~490 obligated entities across nine energy-intensive
  sectors; offset mechanisms are opening alongside.
- **Current demand anchoring is voluntary** (corporate net-zero/ESG buyers):
  under current rules offset credits do not satisfy obligated entities'
  compliance targets, and CarbonX does not claim otherwise.
- **Alignment path**: as BEE's offset mechanism matures (agriculture
  methodologies — improved rice cultivation, livestock manure methane — are
  already approved; agroforestry/biochar in the draft pipeline), CarbonX's
  evidence chain (hash-anchored, plot-level, monitored) is designed to feed
  registry-grade verification without re-architecture. Avoiding NDC
  double-counting: corresponding-adjustment decisions sit with the registry
  and Government of India; the platform's retirement model (single
  retirement, certificate, batch hash) is structured to support it.

## Benefit sharing

Aligned to the Government of India's Virtual/Voluntary Carbon Market
agriculture framework (Jan 2024) principles and Verra's benefit-sharing
requirements: the **70% farmer floor is code-enforced**, the FPO's 5%
requires proven verification work, and the split is visible to the farmer
on one screen. The certificate is aggregated — no farmer-identifying data
reaches buyers.

## Data protection (DPDP Act 2023)

- Identity: phone-OTP (JWT sessions). **Only the last 4 digits of Aadhaar
  are stored** (`profiles.aadhaar_last4`) — a stated design principle, not
  an accident. Full Aadhaar is used transiently for checksum validation and
  never persisted (see `backend/app/services/kyc_service.py`).
- Field photos/documents: stored per-farmer; buyer-facing surfaces expose
  only aggregates and hashes.
- Consent: enrollment records consent at registration; consent revocation =
  account deletion path (production item: self-serve deletion flow).
- Land registry documents of any type are accepted (no Aadhaar dependency)
  precisely to minimise PII collected.

## Credit quality & registry roadmap

1. **Phase 0** (pilot): ground-truth calibration (Soil Health Card labs /
   field sampling on 20–50 plots) via the built-in
   `ground_truth_samples` table and error reporting.
2. **Phase 1**: independent validation of the methodology
   (docs/MRV_METHODOLOGY.md) by an ICAR/KVK partner.
3. **Phase 2**: Verra/Gold Standard listing under VM0042-aligned scope;
   Polygon settlement for public verification.
4. Ongoing: the hash ledger and retirement model already match registry
   expectations for traceability and permanence risk management (5-day
   monitoring → at-risk flagging).
