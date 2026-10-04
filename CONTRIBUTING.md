# Contributing

## Ground rules
1. **Every claim in UI/docs must match the code.** If you add a feature,
   name it precisely; if something is simulated, label it in the UI.
2. **Money math changes need tests.** Split logic, credit calculations and
   ledger behavior are covered in `backend/tests/` — extend the suite in
   the same PR.
3. **The farmer's 70% floor is an invariant.** PRs must not dilute it.

## Setup
See README Quickstart. Copy `.env.example` → `.env` and `backend/.env`
(never commit real credentials).

## Workflow
- Branch from `main`, keep PRs focused.
- `npm run lint && npm run build` and `cd backend && python -m unittest
  discover tests` must pass (CI enforces this).
- Update `AGENTS.md` when setup/schema/endpoints change — it is the
  project's context file for humans and AI assistants.

## Commit style
Conventional-ish prefixes: `feat:`, `fix:`, `docs:`, `chore:`, with a body
explaining the why.
