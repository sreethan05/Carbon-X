# Engineering Backlog — deferred items with rationale

Items from the production audit deliberately deferred, with the reasoning
and the trigger for doing them. "Deferred" ≠ rejected.

| # | Item | Why deferred now | Do it when |
|---|---|---|---|
| 16 | `/v1` API versioning | Every route is unversioned on one `app`; restructuring risks breaking the frontend for zero current consumer benefit. Mitigated: `X-API-Version` header shipped; error envelope stable. | First external/third-party API consumer, or a breaking change |
| 18 | React Query / SWR across pages | Touches every page; regression risk > benefit at current scale. Passport already polls live; listings get SWR via the service worker. | >10k MAU or any page visibly fighting stale-cache bugs |
| 19 | Zod + React Hook Form | 8+ forms to retrofit; existing inline validation + server-side Pydantic covers correctness. | When a third form-validation bug ships |
| 20 | Full i18n of all strings | `LanguageContext` + translations exist (Te/HI) but page coverage is partial; completing it is a content-translation task more than code. Needs native-speaker review for Telugu/Hindi agronomy terms. | Pilot onboarding (Phase 0) with a Telugu reviewer |
| 21b | SW for ALL API GETs | Deliberately trust-hostile: wallet/ledger/purchases must never serve stale cache. Only the public listings feed is SWR-cached (shipped). | Never for money paths; broader if product adds read-heavy public data |
| 27 | Monsoon gap-filling routine | Sentinel-2 median compositing over a 2-year cloud-filtered window already covers most gaps; a dedicated Harmonic/cubic spline fill is research-flavoured. | If pilot plots show >30% null scan rate in Jun–Sep |
| 28 | Verra/Gold Standard listing | Months + third-party audit + fees; depends on Phase 0/1 ground-truth work. | docs/ROADMAP.md Phase 2 |
| 29 | React Native mobile app | The web PWA covers the demo; a native app is a rebuild. The spec's on-device story (TFLite, offline Room queue) needs native — but after pilot validation. | Post-pilot funding |
| 35 | Corporate portfolio dashboard expansion | Certificates + retirement tracking already exist; portfolio analytics (Scope-1/2/3 grouping over time) is additive scope. | First paying buyer |

## Done from the audit (pointers)

- #1/#22/#23 → `supabase/07_production_schema.sql` (+ applied live)
- #2 → `redis_store.otp_send_rate_limited` (Redis ZSET, memory fallback)
- #3 → `.github/workflows/monitor.yml` + `CARBONX_MONITOR_SECRET` on `/monitor/run`
- #4 → `blockchain/.env.example` + deploy steps in `docs/DEPLOYMENT.md`
  (actual contract deploy needs your testnet wallet + faucet MATIC)
- #5/#15/#17/#24/#25 → security headers, error envelopes, OpenAPI tags +
  description, JSON logging + X-Request-ID, `/metrics` (Prometheus)
- #6 → RLS deny-by-default + documented policy shape (schema file §5)
- #7 → `backend/tests/test_integration.py` (15 hermetic API tests)
- #8 → idempotent upsert (`on_conflict … ignore_duplicates`) + retry-until-success migration
- #9 → in-memory PDF cache (bounded, keyed by cert id — certs immutable)
- #10 → pg_trgm GIN indexes on farmer_name/crop/location
- #11 → EE exponential backoff + 10-min analyze cache + polygon size guard
- #12 → `POST /fpo/login` (registration_no → OTP to linked officer)
- #13 → dead files removed
- #14 → strict GeoJSON polygon validation
- #21 → listings/fpos stale-while-revalidate in the service worker
- #26 → elevation + habitat-heterogeneity + seasonal features added; retrain gated on quality
- #30/#31/#32/#33/#34 → SMS language hook, Dependabot, k6 script, DR runbook, passport CSV export

## Deferred with sources (2026-10-22 - CI-warning research)

- #36 Migrate `starlette.testclient` to `httpx2` - Starlette >=1.2 deprecates
  plain `httpx` in the test client and auto-uses `httpx2` (pydantic's next-gen
  client) when installed; with only `httpx` installed the suite emits
  `StarletteDeprecationWarning` (test-only, harmless - we pass either way).
  Widely deferred by the ecosystem (e.g. PrefectHQ/fastmcp PR #4393: belongs to
  a later ecosystem-wide move) because the WS test-transport behaviour changed
  in some httpx2 versions (2.5.0; clean again at 2.7.0) - our WS ledger tests
  must be re-verified under httpx2 before switching. Do: add `httpx2` to the
  CI test-client slice and re-run the WebSocket tests; NOT a runtime dependency.
- #37 Pin/refresh sklearn pickles - models in `backend/ml/models/` were pickled
  with scikit-learn 1.6.1; CI serves them under 1.9.1 and logs
  `InconsistentVersionWarning`. scikit-learn maintainers: pickles are only
  guaranteed same-version (Lemaetre, scikit-learn ML list 2023-06: you should
  be in an environment that has the same version as the pickle to be safe).
  No correctness risk today - the serving layer's quality/features gates refuse
  these models anyway and fall back to labelled heuristics - but the honest
  fix is to pin `scikit-learn==1.6.*` in requirements OR re-pickle with the
  serving version, not ship cross-version loads in production.
- #38 docker/* actions Node20->Node24 - `docker/setup-buildx-action@v3` /
  `docker/build-push-action@v5` still declare node20 (forced onto Node 24 by
  the runner since 2026-06-16; Node 20 removed 2026-09-23 - runner warning
  only). build-push-action v6 bundles a provenance/attestations default
  change, so the bump needs individual verification of image metadata before
  landing.
- #39 Frontend unit tests + Playwright E2E — **DONE 2026-10-22.** Vitest
  (`tests/unit/`, 21 logic tests: API envelope normalization, credit math,
  marketplace query building, analytics mappers) + Playwright
  (`e2e/app.spec.js`, 6 tests: landing, trust center, honest data-source
  labeling, demo corporate login journey, 2 axe-core critical-scan gates)
  against the real FastAPI backend booted in forced demo mode
  (`CARBONX_SKIP_DOTENV=1` wedge in `backend/app/main.py`). CI: `frontend`
  job runs Vitest; new `e2e` job runs the whole browser suite on
  ubuntu (Node 22). TEST_PLAN gap note removed; residual gaps (non-critical
  axe rules, Leaflet canvas flows) listed in TEST_PLAN Known gaps.
