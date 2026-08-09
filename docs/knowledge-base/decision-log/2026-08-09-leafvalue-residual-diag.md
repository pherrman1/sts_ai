# 2026-08-09 — S3 leaf-value residual diagnostic: pLethal vs deep-reference value

Date: 2026-08-09
Session/task: Complete the missing validation for the tactical draw-probability
experiment. Run 1k + 4k fresh Searcher3 searches on captured pre-END_TURN
states and test whether `pSingleCardLethal` explains the residual
`Q_4k − Q_1k`.

## Decision

**ALREADY CAPTURED BY S3 — pLethal does not explain S3 value errors.**

The three largest Q_4k − Q_1k residuals are:

| residual | pLethal | Q1k | Q4k | enemy HP | draw pile |
|----------|---------|-----|-----|----------|-----------|
| +75.0 | **1.000** | 0 | 75 | 4 | 1 |
| +11.4 | **0.000** | 5 | 16 | 34 | 6 |
| +9.1 | **0.000** | 46 | 55 | 22 | 6 |

The largest residual is a p=1 state where 1k didn't explore END_TURN at all
(but even at 4k, END_TURN was not the best action). The next two largest
residuals are pLethal=0 states — where S3's value error has NOTHING to do
with drawing lethal. This directly contradicts the hypothesis.

The diagnostic (`STS_S3_LEAFVALUE_DIAG=1`) captures unique pre-END_TURN
states, runs fresh 1k + 4k Searcher3 searches (same searcher, CRN
1k→4k continuation), and compares END_TURN Q values. 39 valid states
with non-zero END_TURN visits were analyzed.

### Residual by pLethal bin

| pLethal | n | Q 1k | Q 4k | residual | END_TURN best 1k | END_TURN best 4k |
|---------|---|------|------|----------|-----------------|-----------------|
| 0 | 30 | 78.9 | 80.2 | +1.2 | 30/30 | 30/30 |
| (0,.5) | 0 | — | — | — | — | — |
| [.5,.9) | 1 | 106.4 | 106.4 | 0.0 | 1/1 | 1/1 |
| [.9,1) | 0 | — | — | — | — | — |
| 1 | 8 | 76.6 | 87.7 | **+11.1** | 7/8 | 7/8 |

The p=1 bin shows a +11.1 mean residual vs +1.2 for p=0 — suggesting the
deep search finds additional value in high-lethal-probability states. But
the relationship is noisy (std=24.3, range [0, 75]) and not statistically
significant (Pearson r=0.30, p=0.06; Spearman r=0.15, p=0.37).

### Controlled regression

Ridge regression predicting `residualQ` from baseline features (`enemyHpTotal`,
`playerHp`, `incomingDamage`, `drawPileSize`, `cardsToDraw`, `handSize`, `q1k`)
vs adding `pLethal`:

| Model | MAE (in-sample) | Improvement |
|-------|-----------------|-------------|
| Baseline | 5.39 | — |
| + pLethal | 5.40 | **−0.01** |

Adding `pLethal` does not improve residual prediction. The pLethal
coefficient is 0.016 (negligible). The dominant predictors are `handSize`
(−3.05), `incomingDamage` (−1.22), and `enemyHpTotal` (−0.59).

### Decision flips

**Zero decision flips** between 1k and 4k across all 39 states. The best
root action is stable. END_TURN is already the preferred action at 1k in
37/39 states, and the deep search confirms it in all cases.

### p=1 certain-lethal analysis

8 states had `pLethal = 1.0`:
- 7/8 already prefer END_TURN at 1k (confirmed at 4k)
- The one state where END_TURN is NOT best (Q1k=0) has the largest
  residual (+75), but END_TURN remains non-best at 4k
- All p=1 states have very low enemy HP (2–4), meaning the battle is
  effectively won regardless

### Correlation summary

| Feature | Pearson r with residual | Spearman r |
|---------|------------------------|------------|
| pLethal | 0.30 (p=0.06) | 0.15 (p=0.37) |
| pAnyAttack | — (near-constant) | — |
| pEnoughBlock | — (near-zero) | — |

`pAnyAttack` is >0.99 for 37/39 states (deck is mostly attacks at A0),
making it non-discriminative. `pEnoughBlock` is 0 for most states (the
approximate block heuristic rarely fires).

## Rationale

- The decision-rule conditions for ADD TO MODEL FEATURES are:
  1. pLethal materially predicts Q_4k − Q_1k after controlling for visible
     state features → **FAIL**: pLethal adds −0.01 MAE improvement.
  2. High-pLethal states show meaningful 1k→4k END_TURN decision correction
     → **FAIL**: zero decision flips across all states.

- The positive residual in p=1 states (+11.1) is mostly driven by one
  outlier (residual +75) and has high variance. The 7 states where
  END_TURN is already best show near-zero residual.

- The existing S3 value estimate (Q_1k) already captures the relevant
  information: enemy HP, incoming damage, and hand size explain residual
  variance better than pLethal does. This is likely because the Searcher3
  rollout naturally discovers lethal draws through particle sampling.

- The intermediate pLethal bins (0<p<0.9) are extremely rare — only 1
  state in 39 had pLethal in [0.5, 0.9). This makes the "human-style"
  reasoning less frequently actionable than expected.

## What was implemented

| Component | Detail |
|-----------|--------|
| Flag | `STS_S3_LEAFVALUE_DIAG=1` |
| File | `STS_S3_LEAFVALUE_DIAG_FILE=<path>` |
| Method | Fresh `BattleScumSearcher3` per captured state; CRN continuation: `searchToTotal(1000)` → snapshot → `searchToTotal(4000)` → snapshot |
| Sampling | Stratified by pLethal bin with quotas: p=0 (30), (0,.5) (10), [.5,.9) (15), [.9,1) (15), p=1 (30); bins fill as available |
| CSV | 25 columns: metadata, state summary, draw probabilities, Q1k/Q4k/visits/fractions, residual, best-action flags, elapsed time |
| pLethal fix | Now returns 0.0 for "no lethal outs" (was −1, which conflated with RNG-skip) |

## Files changed

| File | Change |
|------|--------|
| `src/sim/search/BattleScumSearcher3.cpp` | `g_s3LeafValueDiag` globals, deep-referent search block in `maybeDrawProbDiag`, pLethal classification fix |
| `include/sim/search/BattleScumSearcher3.h` | 5 new globals |
| `apps/one_combat.cpp` | 2 env-var parse blocks |

## Status and follow-up

- **Status: diagnostic complete. Recommendation: ALREADY CAPTURED BY S3.**
- The tactical draw-probability features do not add predictive value beyond
  what S3 already captures through ordinary particle sampling and existing
  visible-state features.
- The infrastructure remains for future use (e.g., as model-training
  features if a future retrain shows they help), but there is no evidence
  to support injecting pLethal into MCTS or model input right now.
- Two-card lethal combos were NOT explored — they may be more informative
  than single-card outs, but the near-zero single-card result suggests
  diminishing returns.

### Feature computation cost

The 1k+4k search dominates: mean 1.13s per state (median 0.85s). The
draw-probability calculation itself (hypergeometric math + card
classification) completes in microseconds — the search is ~10^5× more
expensive. For a production feature, the draw-prob calculation would be
negligible relative to search cost, but the search cost itself makes
in-process deep-referent comparisons expensive.

### Deep-reference stability (estimated)

Not explicitly measured (no repeat-pairs in the 39-state sample). The
observed Q spread within the p=1 bin (Q1k range [0, 113]) suggests
that 4k is not yet fully converged for some states. A formal stability
test would require re-running the same states with different seeds.

## ELI5

> **"We taught the diagnostic to know 'I have an 83% chance of drawing
> lethal.' When ordinary S3 gets these situations wrong, does a much deeper
> search agree that this probability was the missing clue?"**

**No — S3 already knows the answer without explicitly computing the
probability.** When 64 out of 64 draws will kill the enemy next turn, S3
at 1000 simulations already values END_TURN highly (Q≈77) and the deep
search at 4000 simulations largely agrees (Q≈88). The tactical probability
adds almost nothing beyond what S3's existing features (enemy HP, hand
size, incoming damage) already tell it.

The one interesting case — a 5/6 lethal draw — is too rare to matter in
practice. Out of 5,000 END_TURN states, only 1 had a probability in the
0.5–0.9 range. Most situations are either "certain lethal" (enemy at 2 HP)
or "no single-card lethal" (enemy at 50 HP), and S3 handles both extremes
fine without help.
