# Privacy Notice & Data Protection Impact Assessment (Draft)

**Status:** operational draft. **Qualified privacy-counsel review: NOT OBTAINED.**
**Policy version:** 2026-10-22.
**Last updated:** 2026-10-22.

> This is not a legal opinion and must not be published as one. The notice is
> written to match what the code actually does so a qualified reviewer can
> correct it. The public page at `/trust` labels it a draft.

## 1. Controller and contact

- Controller: CarbonX
- Privacy contact: `privacy@carbonx.example` (replace with a monitored address
  before a live pilot)
- Grievance acknowledgement target: 7 days (operational target, not a legal
  representation)

## 2. Purpose-specific consent

Consent is recorded per purpose, versioned, append-only and language-tagged.
Withdrawal creates a new record; it does not erase the earlier decision.

| Purpose | Required? | What it covers |
|---|---|---|
| `platform_service` | Yes | OTP login, farm records, passport, support |
| `mrv_evidence` | No | Practice photos, geotags and field evidence |
| `payouts` | No | Payout processing and transaction records |
| `public_passport` | No | Public passport/certificate visibility |
| `research` | No | De-identified methodology research |
| `marketing` | No | Marketing messages |

`platform_service` cannot be withdrawn while the account is active; the account
must be deleted instead. No optional purpose is bundled into login.

Implementation: `backend/app/services/privacy.py`,
`backend/app/routes/privacy_router.py`, `supabase/10_trust_controls.sql`.
UI: `/trust`.

## 3. Data map

| Data | Where it lives | Public by default? | Notes |
|---|---|---|---|
| Phone | `profiles.phone`; OTP in Redis | No | Login key and account-lock anchor |
| Name, village, district, state | `profiles` | No (district may appear in aggregate) | Public passport withholds name/village/phone |
| Aadhaar | `profiles.aadhaar_last4` only | No | Full number and image are never stored |
| UPI VPA | `profiles.upi` | No | Used for simulated payout statements |
| Farm boundary | `farms.geojson` | No | Passport exposes crop/district/area, not coordinates |
| Satellite metrics/credits | `farms` | Aggregate only | Always labelled proxy until validation passes |
| Practice photos | evidence store / `farm_evidence` | Opt-in only | EXIF/GPS stripped on public download |
| Geotags | evidence store / `farm_evidence` | No | Owner, FPO of record and staff only |
| KYC document | Hash + outcome only | No | Raw upload is not retained by CarbonX |
| Ledger events | `backend/data/ledger.json` + DB mirror | Redacted | Public view removes identity, rupees and payment refs |
| Buyer name | listing/ledger/certificate | No | Buyer-of-record certificate access only |
| Consent/privacy requests | `consent_records`, `privacy_requests` | No | Retained as proof of compliance |

## 4. Aadhaar and document handling

Current code:

- Stores only the last four digits in `profiles.aadhaar_last4`.
- Never stores the full Aadhaar number or the uploaded image.
- KYC records store SHA-256 and perceptual hashes, verification outcome,
  checks, masked extracted fields and reasons.
- API/UI masking is applied before returning KYC data.
- Evidence/KYC deletion markers exist for erasure requests.

Open questions for a privacy specialist:

1. Is retaining even the last four digits necessary and lawful for this purpose?
2. Is the legal basis consent, contract, or a specified legitimate use?
3. What processor agreements and cross-border terms apply to Supabase, SMS,
   Earth Engine, Sarvam and payment providers?
4. Are document hashes personal data, and for how long may they be retained?
5. Does the pilot need a local-language notice, separate consent for photos of
   people, and a child/guardian rule?
6. What is the breach notification runbook and retention schedule?

## 5. Public-access decisions

The public web never receives:

- farmer name, phone, village, exact coordinates or boundary geometry;
- evidence photo bytes unless the farmer opted in (and then EXIF GPS is stripped);
- rupee gross/split values or buyer identity;
- held/refunded/failed certificates;
- payment provider references.

It may receive: passport id, crop, district, area, aggregate proxy credits,
validation status, redacted ledger event type/sequence/time/hash and retired
certificate ids. See `docs/PUBLIC_ACCESS.md`.

## 6. Access, correction and erasure

- **Export:** `GET /privacy/export` returns one JSON archive of the caller's
  profile, farms, listings, evidence metadata, consent history, requests and
  ledger records. Third-party buyer data is redacted.
- **Correction:** `POST /privacy/corrections` creates a reviewed request; it
  does not silently overwrite a record. Financial corrections require refund +
  reissue.
- **Erasure:** `POST /privacy/delete` requires `confirm=DELETE`. It is blocked
  while listings are active or disputes are open. When allowed, the profile is
  scrubbed to an inactive tombstone; phone remains only as an account-lock/FK
  anchor. Farm boundaries, name, UPI, Aadhaar suffix and evidence are erased.
- **Sessions:** the current token is revoked and other tokens fail the inactive
  profile check.

Residual risk: the immutable hash ledger may contain historical free-text farm
or crop names. It is never silently rewritten; this is disclosed and must be
addressed in the reviewer-approved retention policy.

## 7. Retention schedule (draft)

The machine-readable schedule is returned by `GET /privacy/policy`. Summary:

- account profile: active life, then anonymised on verified deletion;
- farm/MRV records: active credits plus 8 years after last sale for audit and
  disputes;
- KYC hashes/outcome: 8 years after last transaction;
- practice photos/geotags: while enrolled, deleted on erasure unless a sale or
  dispute requires retention;
- consent/privacy requests: 8 years after closure;
- OTP codes: 10 minutes, Redis only;
- ledger: audit integrity, with new payloads excluding phone and buyer details.

## 8. Risk register

| Risk | Likelihood | Impact | Current control | Residual / owner |
|---|---|---|---|---|
| Re-identification from village + crop + area | Medium | High | Public hides village/name; district-level only | Review k-anonymity threshold |
| Exact farm location leak | Medium | High | Coordinates/geotags owner-only | Add automated response tests on every route |
| Aadhaar over-retention | Low | High | Last-4 only; raw image not stored | Privacy counsel decision |
| Photo EXIF leak | Medium | High | Public photo bytes re-encoded without EXIF | Independent verification of every media path |
| Immutable ledger retains names | Medium | Medium | New payloads exclude identities; disclosure | Retention/erasure policy review |
| Consent fatigue / bundled consent | Medium | Medium | Purpose-specific, optional purposes separate | Field-test comprehension |
| Erasure breaks ledger/FK integrity | Low | Medium | Tombstone + blockers; financial history retained | Document legal basis |
| Processor breach | Low | High | Minimal data, service-role keys server-side | DPAs and incident runbook |

## 9. Reviewer checklist

- [ ] Confirm lawful basis for each purpose and each data category.
- [ ] Approve or reject Aadhaar last-4 retention.
- [ ] Approve retention periods and deletion mechanics.
- [ ] Review processor list, DPAs, storage regions and cross-border transfers.
- [ ] Review public-access matrix and re-identification risk.
- [ ] Review consent copy in English/Telugu/Hindi for comprehension.
- [ ] Review breach notification and data-subject request SLAs.
- [ ] Sign the DPIA and record the version/date in `docs/INDEPENDENT_REVIEW.md`.
