# CarbonX — Development Rules (RULES.md)

> How AI agents and humans must code here. The always-on rulebook is the root
> [AGENTS.md](../AGENTS.md) (the open `agents.md` standard — read first, kept
> current); this file states the durable conventions in full. Security
> requirements additionally live in [SECURITY.md](../SECURITY.md) and
> [docs/SECURITY_UPDATES.md](SECURITY_UPDATES.md).

## Honesty (highest-priority rule)

- Never fabricate data. Satellite/ML values must come from real sources; when
  Earth Engine, DB, or a model is unavailable → return an explicit
  unavailable/error with a labelled fallback (`source=`, `ml_source=`), never
  invented numbers.
- Model serving refuses failed quality gates (`features_source='extracted'`
  required) and falls back to the labelled NDVI heuristic.
- Estimates always carry `formula_version` (+ `-r2` suffix) and `ci90`.
- Simulated money paths must say so; production refuses simulated settlement
  without the explicit opt-in var.

## Security

- Authorization is verified **server-side** on every privileged call; roles:
  farmer / fpo / corporate / admin-verifier. The client is never trusted.
- Farmers never touch `marketplace/buy` or corporate routes; wash-trading
  (self-purchase) is prohibited; cross-FPO actions are forbidden.
- Secrets live only in env files (gitignored). Real `JWT_SECRET_KEY` ≥ 32
  random chars in production; OTP dev-echo (`CARBONX_ALLOW_DEV_OTP`) never set
  in production.
- Money = **integer paise** arithmetic only — never floats; split lines must
  sum exactly to the gross; farmer 70% floor is never diluted by rounding.
- Strict input validation: Pydantic models with `extra=forbid`, GeoJSON
  polygons fully validated (closure, ≤10,000 ha, India bounds), uploads ≤ size
  limits, opaque cursors.
- Every failure uses the uniform error envelope with a machine code and
  `X-Request-ID`; log/exception text is PII-masked by the JSON formatter.

## Architecture

- `backend/app/main.py` is a thin composition root; features live in
  `app/routes/*` + `app/services/*`. Routers stay thin; business logic in
  services; typed DB row shapes in `app/supabase_db.py` TypedDicts.
- Frontend API calls go through `src/services/api.js` against `/py-api/*` only
  (nothing imports a browser Supabase client; nothing client-side reads the DB).
- Reuse existing helpers/components before writing new ones; no duplicated
  split/ledger/estimate logic — the canonical engines
  (`split_engine`, `ledger`, `credit_engine.quick_scan_estimate`,
  `access_policy`) are the only implementations.

## Frontend / design

- Follow `docs/DESIGN.md` tokens (colors/fonts/components) — do not add
  one-off colors or shadows; responsive with loading/empty/error states.
- Public surfaces use `access_policy` redaction (placeholders, district-level
  location, held/refunded/disputed certs excluded).
- Service worker: app shell only; API calls stay network-only (never cache
  money paths).

## Testing

- Tests are **hermetic**: force demo mode post-import; do not depend on
  `backend/.env`, live Supabase, or the network. GEE/DB
  live tests must skip cleanly when credentials are absent.
- Add/extend tests with every behaviour change; run the relevant suite (and
  lint) before committing anything.
- Tags that involve money get both unit math tests and a concurrency test.

## Git & docs

- Small, conventional commits (`feat:`, `fix:`, `chore:`, `docs:`,
  `test:`) — one logical change each; never commit secrets or generated data.
- Documentation travels with behaviour: update `AGENTS.md` and the matching
  `docs/*.md` in the same PR (PRD/DESIGN/TEST_PLAN/RULES/DECISIONS, etc.), so
  docs never describe an app that no longer exists.
- Update [docs/BACKLOG.md](BACKLOG.md) rather than leaving TODO comments when
  deferring work; deferred items need a reason and source.
