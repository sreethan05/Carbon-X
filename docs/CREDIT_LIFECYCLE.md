# Credit Lifecycle, Disputes and Refunds (v1.0)

**Status:** implemented; migration `supabase/10_trust_controls.sql` must be
applied before production use. Last updated: 2026-10-22.

The SHA-256 ledger is the money/audit source of truth. Listing rows are the
mutable balance; ledger events are append-only and must agree with that balance.

## 1. States

| State | Meaning |
|---|---|
| `Active` | Credits listed and available |
| `Partially Sold` | Some credits sold/retired; remaining credits still available unless frozen |
| `Disputed` | New bids/sales frozen; existing sale recorded |
| `Retired` | Purchased credits permanently retired; no re-sale |
| `Refunded` | A sale was fully reversed; credits restored to the listing |
| `SALE_FAILED` | Ledger append failed after a balance attempt; excluded from reconciled totals |
| `Sold` | Legacy label only; new full purchases use `Retired` |

Each sale has a unique certificate id derived from listing id + `sale_seq`.
Partial sales therefore produce distinct certificates and cannot share a
certificate id.

## 2. Issuance and listing

1. A farm must pass the listing gate (`farm_may_list`) and belong to the seller.
2. Total credits = carbon + biodiversity credits; both must be non-negative and
   total must be > 0.
3. Price per credit must be > 0.
4. Validation status is attached to the listing response; until field validation
   passes, credits are labelled a proxy estimate.

## 3. Purchase transaction

1. Acquire a per-listing settlement lock (Redis, in-process fallback).
2. Re-read the listing under the lock.
3. Reject if sold out, frozen by a dispute, or the farm no longer exists.
4. Compare-and-swap the remaining balance (`total_credits`).
5. Append `SALE` → `SPLIT` → `RETIRE` ledger events.
6. If the ledger append fails, restore the balance under the same lock and
   append `SALE_FAILED` for reconciliation. Never present the sale as settled.
7. Return the certificate, split lines, escrow reference and batch hash.

The client browser cannot create a certificate or a split. A provider payment
callback is not settlement; the verified webhook settles the sale.

## 4. Partial sale

- Remaining credits decrease; listing becomes `Partially Sold`.
- Each sale stores `sale_seq`, `credits_sold` and its own certificate id.
- A partial sale does not retire the whole listing.
- A full purchase retires the purchased volume atomically.

## 5. Refund

A refund reverses **one full sale**, never an arbitrary amount.

1. Derive the original `SALE`/`SPLIT` from the ledger; legacy rows without a
   ledger sale cannot be refunded safely.
2. Acquire the same settlement/dispute lock.
3. Verify the certificate is not already refunded.
4. Restore the exact credits sold to the listing.
5. Append `REFUND` with the reversed split and refund reference.
6. Mark the certificate `REFUNDED`; its id is never reused.
7. Idempotent repeat requests return `already_refunded` without changing the
   balance again.

If a refund would exceed the original balance or the ledger record is missing,
the request is rejected for manual reconciliation.

## 6. Disputes

Eligible callers: the farmer of record, the buyer of record, or admin/verifier
staff. In production, anonymous disputes are rejected.

1. `POST /certificates/{id}/dispute` appends `DISPUTE` and sets the listing
   `dispute_status=OPEN` / `lifecycle_state=Disputed`.
2. New sales are blocked while the dispute is open.
3. Staff resolve with one of:
   - `release` — keep the sale and release the freeze;
   - `reject` — reject the dispute, keep the sale, release the freeze;
   - `refund` — reverse the full sale and restore credits.
4. Resolution appends `DISPUTE_RESOLVED`. A refunded resolution also appends
   `REFUND` with the reversed split.

## 7. Correction

Non-financial metadata (for example a buyer display name or certificate note)
is corrected with a `CORRECTION` event that records old/new values and the
actor. Financial values are **never** edited in place: the original sale is
refunded and a corrected certificate is reissued. This keeps the certificate,
ledger and payout statement consistent.

## 8. Retirement

`POST /certificates/{id}/retire` retires held credits for a stated scope and
appends a `RETIRE` event. Retired certificates are public only after retirement
and expose no identity, rupee value or split. Refunded, disputed or failed
certificates are not public.

## 9. Reconciliation

`GET /wallet/reconciliation` checks, from ledger records:

- split lines sum to gross (integer paise);
- farmer share meets the 70% floor when applicable;
- no duplicate certificate ids;
- failed sales are excluded from counted totals;
- legacy rows without SALE events are labelled estimates, not reconciled.

`GET /ops/certificates/reconciliation` performs the same check across all
certificates for staff.

## 10. Failure and concurrency rules

- A per-listing Redis lock serialises settlement/dispute/refund operations.
- Balance updates use compare-and-swap, not read-then-write.
- On ledger failure after CAS, restore under the lock; if restoration also
  fails, record `SALE_FAILED` and surface it in reconciliation.
- A refund never deletes history; it appends an opposite event.
- Certificate ids are immutable and unique per sale.
- Redis unavailability falls back to an in-process lock; this is safe for a
  single process only, not a multi-worker production deployment.

## 11. Operational checklist before production

- [ ] Apply `supabase/10_trust_controls.sql`.
- [ ] Run a multi-process lock test against the real Redis deployment.
- [ ] Confirm ledger path is durable and backed up.
- [ ] Confirm every settlement path writes SALE/SPLIT/RETIRE or SALE_FAILED.
- [ ] Confirm provider webhook signature verification and replay protection.
- [ ] Confirm refunds require staff authorization in the live DB.
- [ ] Have R5 financial-controls review completed (`docs/INDEPENDENT_REVIEW.md`).
