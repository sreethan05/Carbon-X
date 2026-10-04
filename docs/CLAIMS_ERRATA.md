# Claims Errata — pitch video vs current code

The recorded pitch video predates the honesty overhaul. If a judge
cross-checks it against this repo (they will — every judge Googles), this
sheet is the reconciliation. **Lead the live round with the demo script and
open with the errata itself** — the correction is the credibility moment.

## Claim-by-claim reconciliation

| Video says | The repo truth (today) | Say this on stage |
|---|---|---|
| "PyTorch LSTM predicts carbon" | No LSTM anywhere. Carbon math is a deterministic VM0042-style 5-step engine (`credit_engine`); biodiversity was a GradientBoosting model, now gated behind a quality threshold | "We shipped an LSTM claim in an early pitch. When we audited ourselves we found worse: our first biodiversity model was *circular* — it predicted a formula of its own inputs. We retired it, built a quality gate that refuses to serve below-threshold models, and documented the whole thing in the model card." |
| "R² 0.989" | That number was the circular model's. Real retrain on real GBIF data: test R² ≈ 0.00 — documented in `docs/MODEL_CARD.md` with the serving gate | "R² 0.989 was our model predicting its own inputs. The honest number is near zero, and that's *good* science — the uncertainty now shows up as a 10–30% deduction plus a 90% CI on every credit instead of a fake number." |
| "ERC-1155 blockchain" | No blockchain in the running system. Tamper-evident SHA-256 hash chain in Postgres (`ledger_events`); Polygon is Phase-2 roadmap (`blockchain/` scaffold + deploy docs exist) | "We said ERC-1155. We don't use a token chain — we use a hash chain you can recompute yourself. Watch: (run `python scripts/tamper_demo.py`) — edit a record, the chain breaks at the exact event. Zero gas, and the upgrade path to Polygon is architecture-identical." |
| "90% to farmers" | **70% floor, code-enforced** (paise-integer split with unit tests); FPO 5% only when involved; platform 25–30% | "We over-claimed 90%. The enforced number is a 70% floor — and that's stronger, because it's an invariant with tests, visible to the farmer on one screen with every payout line." |
| Implied live registry / UPI | Land registry = 30 seeded parcels (Dharani/Bhu-Naksha path documented); UPI rails simulated, escrow labelled | "Registry integration and payment-gateway escrow are signed-paper work, not code work — the MoU template and the Razorpay route/hold plan are in the docs." |

## Ground rules for the live round

1. Demo from the repo, never the video. `docs/DEMO_SCRIPT.md` runs entirely
   on the live system.
2. Volunteering an errata ("our first model was circular — here's how we
   caught it") pre-empts the single hardest judge question and converts it
   into the team's strongest signal.
3. If asked about any number: name its source — code, simulation
   (`scripts/simulate_scale.py`), or assumption. Every number in the current
   docs traces to one of those three.
