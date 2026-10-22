# Public Access Policy (v1.0)

**Status:** implemented; independent review of the re-identification risk is
pending. Last updated: 2026-10-22.

CarbonX is transparent about evidence and ledger integrity without publishing
farmers' identities, exact fields, private photos or commercial terms. One
sanitizer policy applies consistently to JSON, PDF, CSV, WebSocket and UI.

## 1. Tiers

| Tier | Who | How established |
|---|---|---|
| Public | Anyone | No token |
| Owner | Farmer/FPO of that farm | Token phone matches `owner_phone`, or FPO id matches the farm's FPO |
| Buyer of record | Corporate buyer | Token `role=buyer` **and** buyer name matches the certificate's buyer field |
| Staff | Admin/verifier | Token role |
| FPO officer | FPO role | Profile `fpo_id` must match the farm's `fpo_id`; missing scope is denied |

A farmer token does not unlock another farmer's passport, evidence, wallet or
certificate. A generic buyer token does not unlock every certificate.

## 2. Record-by-record matrix

### Carbon passport — `GET /passport/{farm_id}`

| Field | Public | Owner/FPO/staff |
|---|---|---|
| Passport id, crop, district/state, area, satellite metrics | Yes | Yes |
| Proxy credits, CI90, validation status, trust flags | Yes | Yes |
| Farm name | Withheld (`Registered farm parcel`) | Yes |
| Owner name/phone, village | No | Yes |
| Exact boundary/coordinates | No | Yes |
| Expected income and rupee values | No | Yes |
| Ledger summary | Counts/verification only | Full event payloads |

### Hash ledger — `GET /ledger/{farm_id}` and WebSocket

Public events expose: type, sequence, timestamp, hash, previous hash, credit
quantity and public-safe references. Public redaction removes:

- farmer/buyer names and phones;
- gross rupees, split amounts and payment provider references;
- free-text reasons/notes that may contain personal data.

Public sockets receive the same redacted events as the HTTP endpoint. Owner and
staff sockets receive full events over a separately authorised connection.

### Certificates — JSON, CSV, PDF

- Public: only `RETIRED` certificates. Id, crop, volume, retirement date, batch
  hash, validation label, but no buyer/farmer name, phone, rupee value, split,
  exact location or escrow payment reference.
- Owner (farmer of record) and buyer of record: their own certificate,
  including held/refunded/disputed state.
- Staff: any certificate for audit.
- Held, refunded, disputed and failed certificates return 404 publicly.
- PDF watermark states `REFUNDED`, `DISPUTED`, `FAILED SETTLEMENT` where
  applicable. PDF cache keys include the access tier so a public PDF can never
  be served to an owner response with private fields (or vice versa).

### Marketplace — `GET /marketplace/listings`

Public: listing id, crop, district-level location, available credits, price,
status, proxy-validation label, image.

Withheld: farmer name, phone, village, exact coordinates, any buyer information.
Public listings show `Verified farmer (name withheld)` where a name would
normally appear. Owner/staff responses may include their own contact data.

### Evidence — `GET /farms/{id}/evidence`

Public:

- counts of photos/geotags;
- verification booleans (`practice_photo`, `geotag_inside_boundary`);
- opt-in photos only, re-encoded to strip EXIF/GPS.

Owner/FPO/staff: exact coordinates, uploader identity, private photos and
metadata. Geotags are never public. Public photo bytes are served through a
sanitiser, not the original file.

### Wallet and payouts

Wallet, payout statements and reconciliation are authenticated endpoints. No
public route exposes farmer shares, FPO shares, platform shares, UPI ids or
buyer payment references. `current_bid` on legacy rows is never trusted as a
settlement amount.

## 3. Consent interaction

Public passport visibility is an optional consent purpose, but the redaction
rules above apply even when that purpose is granted. Consent cannot turn off
the identity/coordinate/rupee protections. Evidence photos are public only when
the uploader explicitly opts in **and** the sanitizer strips GPS.

## 4. Enforcement points

- `backend/app/services/access_policy.py` — tiers, ledger filtering, location
  redaction;
- `backend/app/routes/trust_router.py` — passport, certificates, CSV, wallet;
- `backend/app/routes/marketplace_router.py` — listing sanitizer;
- `backend/app/routes/evidence_router.py` — evidence/photo sanitizer;
- `backend/app/routes/ws_router.py` — per-socket ledger redaction;
- `backend/app/services/certificate_pdf.py` — PDF watermark/fields;
- UI `/trust` page publishes this matrix.

## 5. Tests and open risks

`backend/tests/test_trust_program.py` covers public/owner passport and ledger
redaction, certificate CSV/PDF redaction, evidence coordinates and listing
identity withholding. R3/R4 reviews must still assess re-identification from
district + crop + area and approve the final public matrix.

Open risks:

- small-district/crop/area combinations can be identifying;
- the immutable ledger may contain historical names in old payloads;
- future endpoints must use the shared sanitizer, not a new ad-hoc response;
- CSV/PDF exports need regression tests whenever a field is added.
