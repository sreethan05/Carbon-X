# Quantified Impact Model (assumptions shown)

Every number below is derivable from the platform's own engines. Nothing is
a vague promise.

## The core equation

    Farmers onboarded × avg credits/farm × price × farmer share = farmer income

| Lever | Value | Source |
|---|---|---|
| Avg verified credits/farm/yr | 40 tCO₂e | platform demo farms: 33–138 |
| Price | ₹450/credit | docs/ECONOMICS.md pricing logic |
| Farmer share | 70% floor | `split_engine` (code-enforced) |
| Soil carbon co-benefit | ~2–4 tCO₂e/ha/yr in SOC factors | docs/MRV_METHODOLOGY.md §4 |

**1,000 farmers → ~40,000 tCO₂e/yr → ₹1.8 Cr gross → ₹1.26 Cr to farmers**
→ at ~1 ha average holding, roughly 1,000–4,000 tCO₂e/yr of new soil
carbon, monitored every 5 days.

## Who this includes that incumbents exclude

- **86.1% of farmers are small/marginal** (Agri Census 2015-16) — plots too
  small for legacy MRV economics. CarbonX's marginal cost/farm (~₹29–100/yr)
  makes 0.4 ha viable.
- **The digitally excluded half**: FPO-assisted (Meeseva-style) onboarding
  means no smartphone literacy, no self-registration required — the FPO
  officer enters the data, the farmer confirms.
- **The document-poor**: any land document works through OCR; tenant farmers
  are covered by FPO/community attestation (an honest, stated mechanism —
  not a fictional solved problem).

## Gender & equity

Women perform a majority of agricultural labour but hold a minority of land
titles — legacy carbon programs that require title documents exclude them by
default. CarbonX's document-flexible onboarding + FPO attestation path is
the inclusion mechanism; the pilot KPI set tracks **women's share of
onboarded farmers** explicitly (see below).

## Beyond carbon: climate-resilience co-benefits

The practices being credited (zero-till, direct-seeded rice, cover crops,
agroforestry) simultaneously: reduce irrigation demand (AWD rice cuts
methane up to 48% and water use substantially), stabilise yields against
dry spells (SOC water-holding), and reduce input costs. The platform tracks
biodiversity as a co-benefit score today; water savings are the adjacent
credit instrument on the same rails (Phase 3).

## Pilot KPIs (tracked in-platform)

`/ops/summary` + `ground_truth_samples` give: farmers onboarded (and FPO-
assisted share, women's share), hectares mapped, verified vs flagged plots,
time-to-MRV (target: minutes), credits issued/retired, payout success, 70%
floor holding (auditable from wallet ledger), model uncertainty narrowing as
ground-truth data accumulates.

## Scale path

Telangana (one district, one FPO, 200–500 farmers — Phase 0) → South India
via FPO federations (Phase 2) → national via the FPO mechanism as the
scaling unit (Phase 3). The FPO — not the individual farmer — is the unit
that scales: 10,000 FPOs × 200 farmers = 2M farms reachable through a
channel that already exists and already trusts its members.
