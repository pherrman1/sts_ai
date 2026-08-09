# 2026-08-09 — S3 draw-probability diagnostic: exact tactical draw probabilities

Date: 2026-08-09
Session/task: Add cheap exact draw-probability calculations to Searcher3 and
measure whether tactical features like P(draw lethal) correlate with search
value estimates.

## Decision

**ALREADY CAPTURED BY S3 — superseded by leafvalue residual diagnostic.**

The subsequent deep-referent comparison (`STS_S3_LEAFVALUE_DIAG=1`, 39 states,
1k→4k CRN) found that `pSingleCardLethal` does not improve residual prediction
over existing S3 features. Zero decision flips between 1k and 4k. S3's ordinary
search already captures the relevant tactical information.

See: `docs/knowledge-base/decision-log/2026-08-09-leafvalue-residual-diag.md`

The diagnostic (`STS_S3_DRAW_PROB_DIAG=1`) computes exact hypergeometric
probabilities at END_TURN boundaries: `P(draw ≥1 lethal)`, `P(draw any attack)`,
`P(draw enough block)`, expected counts. The combinatorial helper is validated
with unit tests. The features are cheap to compute (no particles, no rollouts,
no neural inference).

### Prevalence

| Metric | Value |
|--------|-------|
| Unique END_TURN states | 5,000 (capped) |
| States with pLethal > 0 | 21.1% |
| pLethal = 1.0 (certain lethal) | 17.7% |
| pLethal ∈ [0.75, 1.0) | 2.8% |
| pLethal ∈ [0.50, 0.75) | 0.7% |
| pAnyAttack > 0 | 84.4% |
| Skip reasons (empty) | 0% (classification works for all seen states) |

### Human-style examples

```
seed=3 floor=1 enc=4: dp=1, outs=1, p=1.000, enemyHp=7, incDmg=3
  → "One card left, it's lethal, I have a 100% chance."

seed=3 floor=1 enc=4: dp=6, outs=1, p=0.833, enemyHp=13, incDmg=11
  → "6 cards left, 1 lethal out, draw 5 → 83.3% chance."

seed=1 floor=1 enc=1: dp=5, outs=2, p=1.000, enemyHp=2, incDmg=9
  → "5 cards left, 2 lethal, draw 5 → 100% (can't miss both)."

seed=7 floor=1 enc=1: dp=5, outs=4, p=1.000, enemyHp=5, incDmg=9
  → "5 cards left, 4 lethal, draw 5 → 100%."
```

### Limitations and incomplete sections

- **Task Section 14 (S3 Q correlation) incomplete**: the hook fires only at
  the leaf-expansion boundary where the END_TURN edge has no accumulated
  statistics (Q=0, visits=0). Internal-node END_TURN hooks were not added.
  Without edge statistics, the "does S3 already understand lethal draw
  probability?" question cannot be answered from this data.
- **Task Section 15 (deep-value comparison) not run**: requires sampling
  100-300 states, running deep evaluations for each, and measuring whether
  pLethal explains residual S3 error. Not done.
- **Block estimation is crude**: `enoughBlockOuts` uses an approximate block
  value (5 + upgraded), not the engine's actual card block calculation.
- **pLethal=-1 is ambiguous**: both "no lethal outs found" and "RNG skip"
  produce the same sentinel value. A clearer skip-reason column would help.

## What was implemented

| Component | Detail |
|-----------|--------|
| Probability helpers | `hypergeometricAtLeastOne(N, K, D)` — exact 1 − C(N−K,D)/C(N,D); `expectedCount(N, K, D)` — D·K/N |
| Draw-count determination | Simulates END_TURN on a copy to get `cardsToDraw`; handles Runic Pyramid retain |
| Card classification | `classifyDrawPile()` — classifies each draw-pile card as attack/playable/block/enoughBlock/singleCardLethal |
| Lethal check | Simulates post-monster-turn state, tests each card against each targetable monster |
| RNG safety | Skips Ink Bottle random-draw states; multi-hit attacks treated as deterministic (damage per hit is fixed in this engine) |
| Cross-thread dedup | Global `unordered_set<uint64_t>` under mutex — no thread-duplicate rows |
| CSV | 27 columns: metadata, state summary, draw-pile classification, probabilities, END_TURN edge stats, skip reason |
| Unit tests | `draw_prob_helper`: 8 combinatorial test cases; `draw_prob_engine`: constructed combat state with known lethal out |
| Performance | ~33 CPU-sec/run vs ~23 without (43% overhead), mainly from simulating END_TURN per state + lethal re-simulation per card |

## Files changed

| File | Change |
|------|--------|
| `src/sim/search/BattleScumSearcher3.cpp` | `hypergeometricAtLeastOne()`, `expectedCount()`, `classifyDrawPile()`, `maybeDrawProbDiag()`, hook in `step()` leaf-expansion path, cross-thread dedup state |
| `include/sim/search/BattleScumSearcher3.h` | `g_s3DrawProbDiag`, `g_s3DrawProbDiagFile` |
| `apps/one_combat.cpp` | 2 env-var parse blocks |
| `apps/test.cpp` | `testDrawProbHelper()`, `testDrawProbEngine()` |

## Status and follow-up

- **Status: diagnostic complete. Recommendation: USE FOR MODEL TRAINING ONLY.**
- The features are cheap and well-defined. They capture human-style "I have
  an X% chance to draw lethal" reasoning.
- Before injecting into MCTS: run the deep-value comparison (Section 15)
  on 100-300 states stratified by lethal-probability bin, to determine
  whether S3's current estimate systematically undervalues high-lethal-prob
  END_TURN states.
- If residual analysis shows pLethal explains S3 error, add as a combat
  model input feature (VNet or policy feature) or as an END_TURN prior
  adjustment.
- Two-card lethal combos are NOT implemented — leave for future work if
  single-card outs prove useful.

## ELI5

> **"Can the AI cheaply know things like 'I have a five-in-six chance of
> drawing lethal next turn,' and is it currently making worse estimates
> because it doesn't explicitly know that?"**

**Yes, it CAN know this cheaply.** The diagnostic calculates exact draw
probabilities using basic combinatorics (no simulations, no neural nets) in
microseconds. About 1 in 5 END_TURN states has at least one lethal card in
the draw pile, and 18% of states have a 100% chance of drawing lethal.

**But we haven't yet measured whether S3 misses this.** The hook fires at
the leaf-expansion boundary where the END_TURN edge has no accumulated search
statistics yet, so we can't compare the probability against S3's value
estimate. The next step is to sample states with high vs low lethal
probability and compare S3's current estimate against a deeper evaluation,
to see if S3 is systematically wrong.
