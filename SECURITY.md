# Security Policy — CarbonX

## Reporting a vulnerability

**Please use GitHub Private Vulnerability Reporting** (click **Security and
quality → Report a vulnerability** on this repository). Do not open a public
issue for anything you believe is exploitable.

If private reporting is unavailable, contact the maintainers via a maintainer
email listed on a recent commit rather than publishing the issue.

Our policy:

- Acknowledge vulnerability reports within **72 hours**.
- Investigate and respond with a plan within **7 days**.
- Fix critical issues rapidly; publish fixes with a changelog and credit the
  reporter.

Please include: a summary, affected component/endpoint, proof of concept, and
impact. Reports are handled under coordinated disclosure.

## Supported versions

| Version | Branch | Supported |
|---|---|---|
| current development | `main` | ✅ security fixes only on latest |
| older commits/tags | — | ❌ upgrade instead |

## What is in scope

- The FastAPI backend (`backend/app/**`) — auth/OTP, payments, marketplace,
  evidence, voice, monitoring endpoints.
- The React frontend (`src/**`) — XSS/CSRF/clickjacking posture, PWA service
  worker behaviour.
- Dockerfiles / docker-compose, CI workflows, dependency supply chain.

## Out of scope

- The legacy `backend/src/` standalone AMR minting service and `blockchain/`
  Solidity code **unless/until** they are wired into the live path — both are
  documented as production-roadmap items and are not in the verification or
  payout path today (their API returns explicit 503-style errors when
  unconfigured).
- Reports about the demo/sample-data modes being *not confidential* — demo
  mode is explicitly labelled and gated; it is not a vulnerability per se, but
  a misreported *unlabelled* fallback would be.

## Current security posture (summary)

- RLS deny-all posture: anon/authenticated are granted nothing in Supabase;
  all DB access goes through the backend using `service_role` (bypasses RLS),
  so nothing client-side reads the database directly.
- Phone-OTP auth with Redis-backed storage (10-min TTL, 5 attempts),
  rate limiting: 3 sends / 10 min per phone via Redis ZSET (memory fallback
  single-worker), accepted in-process.
- Production startup refuses unsafe configuration (weak JWT secret, unmanaged
  Redis, localhost CORS tokens, dev OTP on, without an explicit payments
  mode — see `backend/app/config.py::validate_production_configuration`).
- Security headers (CSP, X-Frame-Options, nosniff, optional HSTS via
  `CARBONX_FORCE_HTTPS=1`) on every response.
- Payment webhooks are HMAC-signature verified; amount mismatches and
  conflicts are never settled silently but follow conflict-refund explicit
  logging.
- Continuous checks: 515+ backend tests including a dedicated pentest suite
  (`backend/tests/test_security_pentest.py`), HTTPX/CRLF/XSS header fuzzing,
  forged-token tests; weekly report-only dependency audit
  (`security-audit.yml`); triage SLAs in
  [docs/SECURITY_UPDATES.md](docs/SECURITY_UPDATES.md).

## Known external dependencies

- `supabase/10_trust_controls.sql` must be applied by a human with SQL access
  before a live pilot (see docs/DEPLOYMENT.md).
- Third-party services (Textplate SMS, Razorpay, Sarvam AI, Google Earth
  Engine, Azure Document Intelligence) require their credentials to stay
  secret and their usage to respect their own security terms.
