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

## Result

The frozen implementation at
`7baf98a7b464a7cfbc91f9ee163a691e4cd3dc2b` evaluated all 15 selected
contexts with 16 fresh matched futures per action: 480/480 valid full-run
branches. The full-run adjudicator used 1,000 combat simulations and terminal
run win as its primary utility. Safe and strength siblings shared both the
hidden-encounter seed and continuation/search seed within each future.

The safe action won 4 contexts, the strength action won 5, and 6 tied. Rule
results were:

| Rule | Correct among 9 non-ties | Mean chosen win | Mean regret | Median regret |
| --- | ---: | ---: | ---: | ---: |
| survival only | 4 (44.4%) | 0.5917 | 0.0917 | 0 |
| strength only | 5 (55.6%) | 0.6250 | 0.0583 | 0 |
| combined product | 6 (66.7%) | 0.6458 | 0.0375 | 0 |
| dense K=3 | 5 (55.6%) | 0.6042 | 0.0792 | 0 |

Combined product had the best point estimates, but its paired source-seed
cluster bootstrap interval versus survival only was `[-0.00735, 0.14338]` and
versus strength only was `[-0.06250, 0.11029]`. Both primary intervals include
zero, so the prespecified verdict is **INCONCLUSIVE**. This is promising but
noisy evidence on a discovery-selected set, not authorization to change OOC
behavior, train auxiliary heads, or claim that a factorized model learns
better.

## Run provenance

- Command, through the designated GCP launcher and repository seed guard:
  `./build/ooc_targeted_7baf98a/one_combat oocmargtradeoffeval 15 /home/philippherrmann/sts_sweep/build/ooc_targeted_e1_targets_7baf98a.csv /home/philippherrmann/sts_sweep/build/ooc_targeted_e1_adjudication_7baf98a.csv 1000 16 0`
- Frozen Release executable SHA-256:
  `D628CB493B3EC21FC68D2E803C532AE0F8F6FE447C3DA4DCA47C964215545299`.
- Target manifest: `build/ooc_targeted_e1/targets_rules_reviewed.csv`, SHA-256
  `6CCA74E13D8ED653083671E42530A3F36C55954616A2AE86D020534B9B6954D5`.
- Raw adjudication: `build/ooc_targeted_e1/adjudication_7baf98a.csv`, SHA-256
  `1F8CABA2A8DFC5DFC9A460F57CDBAA15A79594D13EFBB9A9DD0250305D991642`.
- Raw GCP log: `build/ooc_targeted_e1/gcp_ooc_targeted_e1_7baf98a.log`,
  SHA-256
  `232552386519D648D1B9BF86F79003CB8AC605EF329CA47326395627B7627888`.
- Analyzed decisions: `build/ooc_targeted_e1/final/decisions.csv`, SHA-256
  `0E727A46ED075C5BF36D543DFAD732243959495B0B223D909A2265997186832`.
- Summary: `build/ooc_targeted_e1/final/summary.json`, SHA-256
  `5DC020CECD2A2B7BBDF1E65E74A5534CCC5767C8FD624E65BE12A86FBD146818`.
- Exact model SHA-256 values: combat VNet
  `E26FFFDBE21392CC08DB841859D46C13188ACD16B180323868B04DCA55E15EA2`,
  win trees
  `724A75CCC4BC2394306181DB229AA2295433450F9596F1BC1479083DDA337E35`,
  rich trees
  `C866B62512BB7CF8ABDEBC6175415508CB667FE2D628198AC107FD35591A9447`,
  and policy trees
  `43C9DBDDBEBE52B4DCE961B9376FCB76C1AC72A735CAF161B646BE0FA34F1A55`.

An independent post-run audit reproduced target selection, exact sibling RNG
pairing, rule reconstruction, aggregate metrics, deterministic bootstrap
intervals, and verdict from the raw artifacts. Production gameplay behavior
remains unchanged.
