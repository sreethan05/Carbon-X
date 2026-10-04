# Roadmap & Sustainability

## Dated milestones (owner: project maintainer)

| Phase | When | Milestone | Exit criteria |
|---|---|---|---|
| Phase 0 | Month 0–3 | **Calibration pilot** — one Telangana district, one FPO, 200–500 farmers | 20–50 ground-truth SOC samples entered via `ground_truth_samples`; estimate-vs-measured error published |
| Phase 1 | Month 3–9 | **First real purchase** — payment-gateway escrow (Razorpay route/hold replaces simulated escrow; split logic unchanged) | one cooperative purchase settled; farmer paid via UPI with auditable split |
| Phase 2 | Month 9–18 | **Registry-grade verification** — ICAR/KVK validation of the methodology; Polygon (Amoy) settlement live; Verra/Gold Standard scoping | third-party validation letter; testnet mints verifiable |
| Phase 3 | Month 18+ | **Scale via FPO federations** — state-level; water & biodiversity credits on the same rails | 10k+ farmers; second instrument live |

## Post-hackathon sustainability

- **Maintenance**: single maintainer + FPO partner; the stack is one mobile
  client, one BaaS, one free satellite API, thin dashboards — deliberately
  operable by one person (see docs/ARCHITECTURE.md).
- **Funding path**: Phase 0 costs ≈ ₹0 infra + field time; grant-fit
  (climate/MRV accelerators, state agri innovation funds) before any
  commercial raise; revenue engine from Phase 1 (docs/ECONOMICS.md).
- **Go-to-market, first 1,000 farmers**: 5 FPO partnerships × 200 members;
  FPO desks already exist in-product (onboarding workbench, verification
  queue); the FPO's own field staff run assisted onboarding.

## Governance of the verification standard

Who audits the auditor? The design answer is layered:
1. **The ledger is public-verify**: anyone can recompute any credit's chain
   (`GET /ledger/{farm_id}`, `scripts/tamper_demo.py`) — the platform cannot
   quietly rewrite a credit's history.
2. **The math is open**: the five-step calculation is documented equation-by-
   equation (docs/MRV_METHODOLOGY.md) and exposed in every API response.
3. **Phase 2 brings external audit**: an ICAR/KVK partner validates the
   methodology, and registry listing (Verra/GS) subjects it to third-party
   validation & verification bodies — the standard answer to "who audits
   the auditor", adopted deliberately rather than invented.
