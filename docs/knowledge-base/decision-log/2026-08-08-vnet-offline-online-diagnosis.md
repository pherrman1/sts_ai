# 2026-08-08 — VNet offline-vs-online performance diagnosis

Date: 2026-08-08
Session/task: Multi-agent investigation into why combat VNets perform well offline but fail online, plus Experiment A stratification measurement.

## Decision

Three read-only investigators + one architect synthesized repository evidence across training/inference parity, distribution shift, and search dynamics. The architect proposed three discriminating experiments. All three were executed on existing §135a data.

**Experiment A (stratified leaf ranking):** The endHp model's ranking advantage does NOT concentrate in near-death states (as hypothesized). Gap narrowest in low-HP (+0.0039 vs +0.0082 overall), widest in high-HP (+0.0177) and deep-tree (+0.0180).

**Experiment B (blend-α sweep):** At the deployed α=0.3, the models are statistically INDISTINGUISHABLE at per-leaf ranking (endHp 0.7499 vs utilityR 0.7486, CIs overlap). Both models improve with any blend > 0. The ±12pp online gap cannot come from blended leaf ranking quality.

**Experiment C (top-action agreement):** Models agree on the best leaf 80.9% of the time. When they disagree (19.1%), the split is 25.1% vs 24.4% — a coin flip. Overall endHp advantage: +23 decisions (+0.13pp) out of 17,098. Top-action selection cannot explain the online gap.

## Rationale

The architect's original hypothesis was that the ranking gap concentrates in near-death deep-tree states, which would explain amplification from ≤2.3pp top-1 gap to ±12pp win-rate swings. **The measured data refutes this** — the largest gap is in `hp_high` and `deep` strata, and at `low_deep` the gap is zero.

**Inference:** The endHp model's smoother predictions (lag-1 AC 0.549 vs 0.502) help in high-information states where ranking is hardest and the search tree is deepest. In near-death states, both models converge toward terminal values and the advantage disappears. The ±12pp amplification through PUCT visit-redistribution dynamics remains unexplained by mean ranking metrics alone.

## Alternatives considered

- Hypothesis A (concentrated in near-death states): **refuted** — gap is narrowest there.
- Hypothesis B (uniform advantage): **partially supported** — gap is positive in nearly all strata, but varies 5× (0.0006 to 0.0180).
- Hypothesis C (tail-concentration in close decisions): not yet tested; closeAcc/largeGapAcc stratification needed.

## Evidence

- `build/leafdiag_gate_64.csv` (288k rows), `build/leafref_gate_64_4k.csv` (287k refs)
- `build/leaf_ranking_reconfirm.json` — Experiment A results
- `tools/leaf_ranking.py` — existing ranking tool; Experiment A used a standalone script due to tool performance
- `EXPERIMENTS.md` §134, §135a, §137
- `docs/knowledge-base/architecture/combat-search.md`
- `src/sim/search/BattleScumSearcher3.cpp` (blend formula, terminal bonus)

## Status and follow-up

- Experiment A: **completed** (166s, 16,676 groups, 15 strata). Gap is narrowest in low-HP (+0.0039), widest in high-HP (+0.0177) and deep (+0.0180). Refutes cliff-edge concentration hypothesis.
- Experiment B (blend sweep): **completed** (341s, 8 α × 2 models). Key result: at deployed α=0.3 the models are statistically INDISTINGUISHABLE (endHp 0.7499 vs utilityR 0.7486, CIs overlap). The ±12pp online gap cannot be explained by per-leaf blended ranking quality. Must be from unblended sites, PUCT scale dynamics, or visit-redistribution amplification.
- Experiment C (top-action agreement): **completed** (0.4s compute, 17,098 decisions). Models agree 80.9% of the time. On disagreements: 25.1% vs 24.4% correct — a coin flip. Overall endHp advantage: +23 decisions (+0.13pp). Top-action selection cannot explain the ±12pp online gap.
- All three experiments recorded in EXPERIMENTS.md §139, §140, §141.
- New tools: `tools/leaf_blend_sweep.py`, `tools/leaf_top_action.py`
- The full architect JSON plan is preserved in the Pi session history, not as a separate file
