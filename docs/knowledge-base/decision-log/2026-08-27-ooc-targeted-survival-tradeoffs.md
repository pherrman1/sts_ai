# Targeted marginal OOC survival tradeoffs

Date: 2026-08-27

## Prespecified question

On merged PR #71 baseline `a2acb1019a42aafefe7afdcdcbb4cc8d19167008`,
do the safer actions in the 15 already discovered marginal
safety-vs-strength contexts produce more terminal run wins than their paired
higher-conditional-survivor-value alternatives under fresh full-run futures?

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
- Report safe/strength/tie decisions, paired replicate outcomes, mean and
  median two-choice terminal-win regret, and a deterministic 10,000-sample
  hierarchical paired bootstrap: resample unique source seeds as outer
  clusters, then resample matched future outcomes within each selected
  decision.

## Decision rule

Call the result `SUPPORT_SAFETY` only if the safe action wins more decision
contexts, has lower mean regret, and the clustered 95% interval for mean
safe-minus-strength terminal-win rate excludes zero. Treat a small, tied, or
noisy advantage as `INCONCLUSIVE`. Call it `REJECT_SAFETY` only for a clear
adverse result under the symmetric criteria. With only 15 selected contexts,
this is exploratory evidence and cannot authorize production behavior or model
training.

## Non-goals

No uniform corpus expansion, new screen support, production OOC change,
NN/GBM training, auxiliary-head implementation, combat-leaf E3c repeat, or
broad gameplay benchmark.
