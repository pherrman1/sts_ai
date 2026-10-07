# Counterfactual OOC label pilot (2026-10-07)

Requested by Philipp in the card-pricing thread: before generating a corpus of
counterfactual OOC labels for a new leaf/value GBM, measure cost and label noise
on a small pilot. Descriptive only; no default or gameplay change.

## Question

If every option of a sampled out-of-combat decision is played K times with
shared hidden futures to the next boss, are the label differences between
options larger than their noise, at what K, and at what cost?

## Design (frozen before the run)

- Mode `one_combat ooccfpilotgen` (this change). Source trajectory and option
  set are `vwinrefreshgen`'s: production V4 chain, outcome-blind reservoir with
  one sample per decision type, option cap chosen plus five.
- In scope: `CARD_REWARD`, `REST`, `SHOP`, `BOSS_RELIC`. Per seed one sampled
  in-scope decision, chosen by `sha256("ooc-cf-pilot-v1-select:{seed}")`.
- Every option is forced, then the hidden future is redrawn with
  `sampleNoncombatFuture` (the OOC MCTS leaf redraw) from a seed that depends
  on (seed, decision, k) only, so all options share future k.
- Continuation: V4 chain plus production Silver with learned stopping
  (ADR-0026), A0, fair RNG, keys off. Horizon: the first boss fight after the
  branch ends, or death before it.
- Label per run: `bossWon` and `hp` after the boss (0 on death).
- Seeds 54000000..54000031 (32 seeds, four parts of eight on four cores),
  K = 8. Analysis uses the first 4 futures for the K=4 comparison.

## Analysis (analyze.py)

- Primary score per run: `hp` after the boss (0 if dead). Also boss win rate.
- Per state, every option pair: mean paired difference over k and its standard
  error; a pair is resolved when |mean| > 2 SE. Report the resolved share at
  K=4 and K=8, and paired versus unpaired SE (the gain from shared futures).
- X2-B (`models/candidates/v_win_x2b_trees.txt`) on the after-option features:
  pairwise agreement on resolved pairs. V4's chosen option: rank by label.
- Cost: CPU seconds per label run, per state, by decision type.

## Reading

No pass/fail gate. The pilot sizes the next step: the smallest K whose resolved
share is close to K=8, and the CPU cost per state for a corpus estimate.
