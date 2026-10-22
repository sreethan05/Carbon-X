# Operational Targets, Dashboards & Alerts (v1.0)

**Status:** targets defined; dashboards/alerting still need a staging
deployment to be wired in a monitoring stack. Last updated: 2026-10-22.

These are the numbers the pilot operates to. The live Prometheus endpoint is
`GET /metrics`; structured logs use `carbonx.*` loggers.

## 1. Performance targets (staging measured, production gate)

| Metric | Target | How measured | Where it surfaces |
|---|---|---|---|
| Health/read endpoints p95 | < 250 ms | Prometheus histogram `carbonx_http_request_duration_seconds` (path label) | Dashboard panel + alert |
| Marketplace listing p95 | < 500 ms | same, path `/marketplace/listings` | Dashboard panel + alert |
| Passport/wallet p95 | < 800 ms | same (wallet derives ledger chains) | Dashboard panel + alert |
| Fallback-mode read p95 | < 300 ms | same (sample-data store is in-memory) | Dashboard panel |
| Satellite scan (`POST /analyze`) | < 30 s p95; < 90 s hard timeout | request duration + EE-side errors in `carbonx.satellite` logs | Scan failure alert |
| Evidence photo upload | ≤ 8 MB file, < 10 s p95 | upload duration + 413/422 rate | Upload failure alert |
| PDF certificate render | < 2 s p95 | duration of `/certificates/{id}/pdf` | PDF failure alert |
| Availability (staging) | 99.5% | synthetic smoke (`scripts/staging_smoke.py`) every 5 min | Status page + alert |
| Availability (production) | 99.9% | same + host provider status | Page/alert |
| RTO / RPO | 1 h / PITR + daily ledger export | restore drill in `docs/DR_RUNBOOK.md` (quarterly) | Drill log |

Alert legend for duration-based rules: page when threshold satisfied for
5 minutes; ticket when satisfied for 20 minutes. Exact PromQL wiring is a
staging task (see §4) — the targets are fixed first so wiring has something to
compare against, and they are intentionally not tuned after the fact.

## 2. Things that must alert (with their source of truth)

| Signal | Source | Suggested threshold | Owner |
|---|---|---|---|
| API 5xx rate > 1% (5 min) | `carbonx_http_requests_total{code=~"5.."}` | page | DevOps lead |
| Ledger verification failure | `GET /ledger/{id}` reports `verified: false`; logs `carbonx.ledger` | page immediately (integrity) | DevOps + engineering lead |
| Payment webhook conflict | `PAYMENT CONFLICT` in `carbonx.payments` logs | page < 1 h (refund SLA is the runbook's 1 h) | Payments/finance desk |
| Failed settlement duplicates | `GET /wallet/reconciliation` shows `issues_found` / `failed_settlements > 0` | ticket same day | Finance desk |
| OTP delivery failure spike | `SMS` failure logs in `carbonx.secure_sms` (or configured provider errors) | > 10 failures in 10 min | DevOps lead |
| OTP rate-limit abuse | `redis_store.otp_send_rate_limited` counters | > 100 hits/10 min | DevOps lead |
| Monitoring cycle missed | `GET /passport/{id}` `monitoring.last_revisit_at` > 5 days + monitor run HTTP failures (`X-Monitor-Secret` cron) | ticket | MRV/satellite lead |
| Earth Engine scan failures | `carbonx.satellite` error logs; `/analyze` 5xx with `EARTH_ENGINE` codes | > 5/hour | ML/remote sensing lead |
| Redis unavailability | `/health` `redis.ready=false`; lock acquisition errors | page (locks+limits are shared state) | DevOps lead |
| Websocket fanout dead | passport client falls back to 15 s polling; `carbonx.ws` error logs | warn only (degradation is graceful) | Engineering |
| Storage: evidence files vs bucket quota | Supabase storage metrics + upload 5xx | > 80% budget | DevOps lead |
| DB connection watchdog | `/health` `database.ready` flips; PostgREST 500s | page if > 2 min | DevOps lead |

## 3. Dashboards

Minimum Grafana panels on `/metrics`:

1. **Service health** — request rate, 5xx %, p50/p95/p99 by path.
2. **Money paths** — `/marketplace/buy`, `/payments/checkout`, `/payments/webhook`
   outcome counts (settled vs conflict_refund vs failed), plus wallet
   reconciliation status (exported from the JSON API via a small exporter task).
3. **Trust signals** — ledger verification checks run/day and failures
   (must be 0), monitor runs/day (expected ≈ number of active farms per 5-day
   cycle), validation status snapshot.
4. **Identity/OTP** — send-otp attempts, success rate, rate-limit triggers.
5. **Ops saturation** — PDF cache hit ratio, analyze cache TTLs, upload 413/422.

Panels 2–5 read from the same Prometheus endpoint; exporter wiring for the JSON
APIs (4) is queued with the staging deployment (P3.2).

## 4. Staging wiring checklist

- [ ] `/metrics` scraped every 15 s by the staging monitoring stack.
- [ ] `scripts/staging_smoke.py` scheduled every 5 min against staging; failures page.
- [ ] Log shipping for `carbonx.*` JSON logs into the searchable index.
- [ ] Webhook conflict log alert = page (source: §2).
- [ ] Reconciliation status export job (§3 item 2) deployed.
- [ ] One synthetic OTP send + one scan + one webhook replay drill per week,
      logged the same way as the DR drills.
