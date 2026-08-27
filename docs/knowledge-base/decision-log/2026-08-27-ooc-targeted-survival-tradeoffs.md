# Targeted marginal OOC survival tradeoffs

Date: 2026-08-27

## Prespecified question

On merged PR #71 baseline `a2acb1019a42aafefe7afdcdcbb4cc8d19167008`,
does the combined discovery score `p_survive * v_alive` identify the better
full-run action in the 15 already discovered marginal safety-vs-strength
contexts more accurately than survival-only or survivor-value-only rules under
fresh full-run futures? The existing dense K=3 score is a secondary baseline.

This is a new targeted exploratory experiment. It does not reinterpret or
modify the frozen PR #71 artifacts and it does not test a learned auxiliary
head.

## Target selection

Read only `regime=marg` rows from the frozen `raw.csv` and `raw_block2.csv`.
Within each decision, require an action pair whose `p_survive` and `v_alive`
orders oppose. Select the pair with the largest survival-probability gap, then
the largest survivor-value gap, with deterministic action-index tie breaking.
The higher-survival action is `safe`; the higher-`v_alive` action is
`strength`. Validate identical `(continuationSeed, hiddenSeed)` sets across all
sibling actions before selection. This discovery selection is subject to
winner's-curse; fresh adjudication seeds are used for evaluation.

Four decision rules are frozen before adjudication:

1. `survivalOnly`: select `safe`;
2. `strengthOnly`: select `strength`;
3. `combinedProduct`: select the larger `p_survive * v_alive`;
4. `denseK3`: select the larger mean producer utility `10*labelWon + labelHp`.

Exact score ties use the producer's original lower-action-index tie break.

## Adjudication

- 15 targeted decision contexts; no uniform new OOC collection.
- 16 fresh matched replicates per action and 1,000 simulations in the existing
  unbootstrapped full-run adjudicator.
- For each replicate, resample the remaining current-act normal and elite
  encounters once before either action. The safe and strength branches share
  both the encounter `hiddenSeed` and continuation/search seed.
- Restore the frozen producer combat VNet
  `models/v_combat_7k_tuned.txt`; retain the native floor/win and policy models.
- Primary utility: terminal run win. Final HP is diagnostic only.
- For each rule report safe/strength choices, accuracy on adjudication-non-tied
  contexts, mean adjudicated terminal win, and mean/median two-choice regret.
  Report paired replicate outcomes and deterministic 10,000-sample hierarchical
  paired bootstrap intervals for combined-product minus each baseline's chosen
  terminal-win rate: resample unique source seeds as outer clusters, then
  resample matched future outcomes within each selected decision.

## Decision rule

Call the result `SUPPORT_COMBINED` only if combined product has strictly higher
non-tied accuracy, lower mean regret, and a clustered paired 95% interval above
zero for chosen terminal-win rate versus both survival-only and strength-only.
Call `REJECT_COMBINED` only under the symmetric adverse criteria. Otherwise the
result is `INCONCLUSIVE`. Dense K=3 is reported as a secondary comparison but
is not part of the primary two-baseline promotion rule. With only 15 selected
contexts, this is exploratory evidence and cannot authorize production
behavior or model training.

## Non-goals

No uniform corpus expansion, new screen support, production OOC change,
NN/GBM training, auxiliary-head implementation, combat-leaf E3c repeat, or
broad gameplay benchmark.
