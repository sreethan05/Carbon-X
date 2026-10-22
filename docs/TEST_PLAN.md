# CarbonX — Test Plan (TEST_PLAN.md)

> HOW WE VERIFY IT. What "working" means, what runs automatically, what a human
> checks before a pilot, and the gaps we admit. Update in the same PR that
> changes behaviour.

## Automated gates (must be green before push)

| Gate | Command | Where it enforces |
|---|---|---|
| Backend tests | `cd backend && python -m unittest discover tests` | CI `backend` job; pre-commit locally |
| Frontend lint | `npm run lint` (0 errors, 0 warnings) | CI `frontend` job |
| Production build | `npm run build` | CI `frontend` job |
| Docker images | `docker compose build` (5 images) | Docker CI workflow |
| Dependency audit (report-only) | npm audit + pip-audit | `security-audit.yml` weekly |

Harness note: local PowerShell exits 1 on stderr noise — judge the
`Ran X tests … OK` line, not the exit code.

## Backend suite map (what each file proves)

| Suite | Verifies |
|---|---|
| `test_integration.py` | Error envelopes + request-id on every failure; listings served with honest `source`; the money path (buy → split → retire → wallet from ledger) |

| `test_payments.py` | Provider selection, Razorpay order/webhook HMAC, amount-mismatch → refund logs, idempotent settlement, no secret leaks |
| `test_concurrency_stress.py` | 20-thread races: no oversell, single-winner full buys, duplicate webhooks settle once |
| `test_settlement_failure.py` | Ledger failure → balance restored + `SALE_FAILED` event |
| `test_ledger_crypto_tamper.py` | Any single-character change in payloads/seq/hashes/timestamps breaks verification; truncation detected |

| `test_security_pentest.py` | Cross-role IDOR, wash-trading ban, CRLF/SQL/XSS header fuzzing, forged/expired/none-alg JWTs, production-config refusal |

| `test_trust_program.py` | Validation labels, privacy consent/export/erasure, certificate lifecycle, redaction across public surfaces, corp settings, support tickets |

| `test_user_journeys.py` | End-to-end farmer, corporate, FPO-officer happy/Forbidden paths |
| `test_evidence_api.py` / `test_evidence_service.py` | Photo/geotag upload, EXIF GPS, polygon-boundary ray-casting, ID sanitization |
| `test_geospatial_deep.py` | Polygon degeneracy, winding order, India-bounds rejection, area guards, hostile EXIF |
| `test_gee.py` / `test_gee_services.py` | GEE offline honesty (never fabricates), init state, polygon validation |
| `test_marketplace_deep.py` | Filters, auto-match, CAS bidding, thread safety, cursor pagination |
| `test_soil_carbon_calibration.py` | IPCC-range soil factors, `-r2` formula version, ci90 math |
| `test_telemetry_and_privacy.py` | PII masking in logs, `/metrics`, request-id propagation |
| `test_trust_monitor_ws.py` | 5-day monitor cycle, monitor secret auth, passport fallback, WS dedup ring |

| `test_trust_layer.py` | Split engine (70% floor, paise), ledger chain, Stage-1 windows, credit engine |
| `test_voice*` | Multilingual intents, role guards, redaction, rate limits |
| `test_core_infrastructure.py` / `test_redis_store_resilience.py` | Env parsing, JSON logs, Redis failover/locks/OTP lifecycle |

Mode: hermetic — tests force demo mode post-import and clear external envs;
`CARBONX_TEST_LIVE_DB=1` opts into the DB-coupled suite (skipped otherwise;
CI also skips 2 live-Earth-Engine tests without GEE creds).

## Staging / preview deployment checks

1. Deploy per [docs/DEPLOYMENT.md](DEPLOYMENT.md).
2. Run `python scripts/staging_smoke.py --base <staging-url> [--token <JWT>]`
   (health, listings source flag, validation/claims, trust pages).
3. Watch `/health` reports DB readiness and the monitor secret is rejected when
   not configured.

## Production QA checklist (human, after every deploy)

- [ ] Live URL: signup (OTP) → login → dashboard loads with real data
- [ ] Wallet totals reconcile with ledger-derived statements
- [ ] One real (simulated or Razorpay) purchase end-to-end; certificate PDF opens
- [ ] Error handling: invalid OTP, oversell attempt, unknown listing → clean envelopes
- [ ] Mobile (Android Chrome) + desktop; refresh and direct URLs on deep routes
- [ ] Logged-out access to protected routes blocked with proper codes
- [ ] `/metrics` reachable, JSON logs carry `request_id`
- [ ] Logs contain no PII (grep a sample for phone numbers)
- [ ] Empty/offline states labelled (no silent fallbacks)

## Load & resilience

- `load-tests/k6_carbonx.js` (SLOs in [docs/OPS_TARGETS.md](OPS_TARGETS.md)).
- Disaster recovery drill: [docs/DR_RUNBOOK.md](DR_RUNBOOK.md).

## Known gaps (honest)

- Ground-truth validation eval returns an honest empty state until real field
  SOC samples exist (external dependency, not a test gap).
- axe accessibility: gated in CI on `/`, `/marketplace`, `/trust`,
  `/corporate/login` at `critical`; on 2026-10-22 all four were audited at
  **every severity and fixed to zero findings** (contrast tokens, missing
  `<main>` landmarks). Remaining pages get the same treatment opportunistically.
- The gated Playwright suite covers the public surfaces + demo corporate login.
  The full farmer signup → scan → list → buy money journey is exercised by the
  510-test backend suite and API integration tests; browser-canvas flows (Leaflet
  farm mapping, satellite preview) remain manual-QA items on the checklist below.
