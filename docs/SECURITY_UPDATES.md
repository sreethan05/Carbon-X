# Security Update Process (v1.0)

**Status:** process defined; rehearsed on first real advisory. Last updated:
2026-10-22.

## How updates normally arrive

1. **Dependabot** (`.github/dependabot.yml`) opens PRs for known vulnerabilities
   and version updates — weekly for npm and pip.
2. **Weekly report job** (`.github/workflows/security-audit.yml`, Mondays 02:40
   UTC) runs `npm audit --omit=dev` and `pip-audit` over the *dependency set*
   and uploads JSON reports as artifacts. These jobs are **report-only**:
   findings do not block merge on their own; the response SLAs below do apply
   to fixing them.

## Triage SLAs

| Severity (per GHSA/CVE) | Response | Fix shipped by | Owner |
|---|---|---|---|
| Critical (RCE / auth bypass in a runtime dep) | Same day triage | ≤ 72 h patch version bump + CI green | DevOps lead |
| High | ≤ 2 business days | ≤ 7 days | DevOps lead |
| Medium | ≤ 1 week | ≤ 30 days (brottled batch) | Engineering lead |
| Low / advisory-noise | Best effort | Batched monthly | Engineering |

A "patch version" fast-path applies when the fix is a semver-patch jump
(`1.2.3 → 1.2.4`): merge Dependabot's PR after CI green, then run
`python scripts/staging_smoke.py --base <staging>` before promoting the deploy.

## If a critical advisory has no patch yet

1. Apply the documented mitigation from the advisory (config, env var, temporary
   version pin) in the same PR that pins the version.
2. If none exists, disable the affected surface (feature flag) in
   `backend/.env`/Vercel envs and note it in `docs/DR_RUNBOOK.md` incident log.
3. Track in `docs/INDEPENDENT_REVIEW.md` §2 only if it affects a trust claim.

## What we do not do

- No `npm update`-style mass bumps outside Dependabot's PRs without a CI/staging
  gate — runtime deps here are security-sensitive (auth, payments, ML).
- No audit failing-the-build by default: audit noise changes weekly; the merge
  blocks on CI (`ci.yml`) tests, and audits are reviewed through the SLA table.
- No dependency is added "just for an audit" without owner review.
