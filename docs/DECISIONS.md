# Architecture Decisions (DECISIONS.md)

> WHY. One decision per record, MADR-condensed: context → chosen option and
> because → consequences. These consolidate what [AGENTS.md](../AGENTS.md)
> narrates as project state. New ADRs append here (never rewrite history;
> supersede with a fresh ADR and mark status).

## ADR-001 — React 18 + Vite SPA instead of Next.js SSR
> 2026-10-22 update: the SPA is now on **React 19** with react-leaflet v5
> (BACKLOG #41); the SSR decision itself stands.

**Decision:** plain React SPA (`src/`) with FastAPI backend.
**Because:** the heavy lifting is satellite/marketplace API work, not
SEO-bearing content; a SPA + Python API keeps the two halves independent and
simple, and `vercel.json` rewrites proxy the existing `/py-api` contract.
**Good because** one language per half, trivially portable hosting.
**Bad because** slower first paint and manual proxy config (`VITE_PY_API_BASE`).

## ADR-002 — Supabase Postgres accessed only via `service_role` backend

**Decision:** RLS denies anon/authenticated on every table; the FastAPI backend
holds `SUPABASE_SERVICE_ROLE_KEY` and is the sole writer; the frontend has no
DB client.
**Because:** farmer phones/aadhaar/evidence require server-side authorization
anyway (IDOR risk), so a permissive client API would be a liability.
**Good because** single authorization choke-point (role checks live next to
queries), full testability of authz in the pentest suite.
**Bad because** the service key is all-powerful — leaks are catastrophic, so
key hygiene is documented in every env template. Note: RLS with per-role
policies are possible only after the pending migration era ends.

## ADR-003 — SHA-256 hash chain as the live ledger; on-chain settlement deferred

**Decision:** the tamper-evident ledger of record is the per-farm SHA-256 chain
(`ledger.py`, persisted + verified); Polygon/Amoy minting stays a
production-roadmap item (`backend/src/` + `blockchain/` kept, documented, and
503-guarded when unconfigured).
**Because:** credits must be verifiable and auditable now, and a local chain
has no gas/keys/network dependency; the blockchain adds regulatory/handshake
overhead to a first product.
**Good because** tests fully exercise tamper-detection, and `docs/ROADMAP.md`
tracks the raise path.
**Bad because** on-chain immutability/verification is not yet delivered, so
external auditability relies on docs + process until then.

## ADR-004 — Demo-first degradation with honest labels

**Decision:** every externally-dependent path (DB, GEE, ML, payments)
degrades to a labelled in-memory/sample fallback (`source=`, `ml_source=`),
and demo login is only issued when the DB is unconfigured.
**Because** the project must boot and demonstrate end-to-end with zero cloud
credentials while students/judges/volunteers explore it.
**Good because** reproducible development and demos, honest surface (SAMPLE
DATA badges).
**Bad because** the fallback surface must never grow into a shadow product —
`RULES.md` forces labels everywhere.

## ADR-005 — Conditional split with a hard 70% farmer floor (integer paise)

**Decision:** payout split = farmer ≥70%, FPO 5% only when involvement is
proven (`farm.fpo_id` live), platform keeps the remainder, computed in integer
paise with exact-sum verification; wallet reports are ledger-derived.
**Because** pilot trust depends on guaranteed farmer income and provable FPO
contribution — folklore sharing failing all money math is checked by tests.
**Good because** rounding cannot silently dilute anyone (tested).
**Bad because** changing split rules is a governance + code change, not a
config flag.

## ADR-006 — Payments: simulated by default; Razorpay is the only live provider

**Decision** `CARBONX_PAYMENTS_PROVIDER=simulated` for local/demo; production
demands complete Razorpay credentials (or an explicit
`CARBONX_ACCEPT_SIMULATED_PAYMENTS=1`); `CARBONX_ALLOW_SIMULATED_SETTLEMENT`
is forbidden alongside Razorpay; webhooks are HMAC-verified, and amount
mismatch/concurrency conflicts produce refund-not-settlement flows.
**Because** real money in a student/pilot codebase must never be implied.
**Good because** every simulated payment is a visible choice; conflicts can
never silently take money.
**Bad because** onboarding a buyer tenant requires env discipline.

## ADR-007 — Canonical credit formula (5-step, `-r2`) as single source of truth

**Decision:** `credit_engine.quick_scan_estimate` (additionality delta →
biomass proxy → IPCC-consistent soil factor → raw total → uncertainty
deduction) is the only credit estimator; `/analyze` and the earnings
calculator both call it; `FORMULA_VERSION` is stamped into estimates and
ledger events.
**Because** two estimators previously disagreed (the old ad-hoc
`area × tree_cover × 0.12` path), which is fatal for audit.
**Good because** every estimate is reproducible and version-tracked; ci90
spans come from one uncertainty model.
**Bad because** recalibrations (r2) require version discipline and docs.

## ADR-008 — ML honesty gates: refuse bad models, label every output

**Decision:** the biodiversity v2 / SOC serving layer refuses models whose
spatial-CV R² or features-source provenance fails gates, and falls back to the
NDVI heuristic labelled via `ml_source`.
**Because** one early model was circular (label = formula of its own features)
and had to be retired — trust beats demo-competition metrics.
**Good because** the serving layer can never silently inflate quality.
**Bad because** some enrolled model artefacts (pickled on older sklearn) are
refused on newer runtime versions until re-pickled (backlog #37).

## ADR-009 — AGENTS.md as the agent rulebook and docs index

**Decision:** this repo's AI-facing rulebook is the root `AGENTS.md`, following
the open `agents.md` convention (60k+ projects; Linux-Foundation stewarded),
pointing to the `docs/` suite instead of duplicating it.
**Because** one predictable file is what all major agents parse
(Codex/Cursor/Copilot/Gemini/Zed/OpenCode…), and an index beats verbose
duplication for context economy.
**Good because** documentation travels with behaviour (RULES.md mandates).
**Bad because** AGENTS.md grows — needs pruning reviews.

## ADR-010 — Trust program: pre-registered validation + labelled proxy status

**Decision:** carbon estimates are labelled `proxy_unvalidated` until the
pre-registered thresholds (≥30 verified **annual-rate** samples, MAPE ≤30%,
|bias| ≤20%, CI90 coverage ≥50%) are met with field data; statuses and claims
are public via `/validation/*` and `/trust`.
**Because** a carbon project must not claim field validation it does not have
(credibility > marketing).
**Good because** the honest status is machine-checkable and visible to buyers.
**Bad because** early pilots must accept a lower-tier label until field
samples accrue (`docs/VALIDATION_PROTOCOL.md` describes the thresholds —
real field data is the unlock).

## ADR-011 — FPO access is farm-scoped, buying is id-keyed

**Decision:** global staff (admin, verifier) is the only globally-privileged
set. FPO accounts resolve their own `fpo_id` (token or profile lookup) and see
full records only for farms/certificates whose `fpo_id` matches — passports,
ledger JSON/WS, certificates, earnings/KYC, ops summary, ground-truth ingest
and the validation report all check the match; unresolvable or DB-off callers
fail closed to the public view. Buyer-of-record access binds to
`buyer_c_id` recorded on the SALE ledger event (display names are
presentation-only; the name fallback survives only in offline demo sales).
**Because** fearing every FPO as staff let one FPO read farmer PII and
validation rows belonging to another FPO.
**Good because** scope is a single rule in `access_policy` enforced at every
boundary; a name collision can no longer grant certificate access.
**Bad because** surgeons-before-2026 live rows without `buyer_c_id` lose
buyer access on the live DB (acceptably conservative; refund ops remain
admin/verifier).

## ADR-012 — One simulated-payments gate; migrations-reported health

**Decision:** `CARBONX_ACCEPT_SIMULATED_PAYMENTS` is the single gate for
simulated settlement (startup validation, `/payments/checkout`,
`/marketplace/buy`, compose, docs). The legacy
`CARBONX_ALLOW_SIMULATED_SETTLEMENT` is honoured as a deprecated alias that
loses to an explicit canonical value. `/health` reports `database.migrations`
(probed via the PostgREST OpenAPI schema, 60 s cache): `migrations_ok=false`
names missing required tables/columns instead of silently shipping features
whose migrations never ran. Docker Compose publishes only the frontend;
Redis is internal-only with `--requirepass` (and an authenticating
healthcheck); the dev overlay (`docker-compose.dev.yml`) republishes
backend/Redis on loopback for local debugging only.
**Because** two differently-named variables for the same gate could let a
deployment pass startup validation while checkout 503'd, and half-applied
migrations would sail through a table-name-only health check.
**Good because** operators get one documented knob and a health endpoint
that states exactly which migration files are missing.
**Bad because** an operator skipping the checklist can still boot with the
demo Redis password — the doc explicitly forbids that default on servers.
