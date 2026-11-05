# Silver price-table leaf: model a746 (leaf plan stage 0, thread B)

Tooling, not an experiment: no ledger §, no campaign, no new seeds. Design and use:
[silver-price-table-leaf.md](../../../knowledge-base/research/combat-search/silver-price-table-leaf.md).
Stage C (the first experiment with this flag): [PREREG-stageC.md](PREREG-stageC.md), draft, not run.

## Model provenance
- Recipe: §746's model A at 100% of the data (`fit_all.py` → §732's `fit_value.py`, `Feat` + `gbm` imported
  unchanged), with no outer fold: the deployed model trains on every labelled fight. Script: [fit_export.py](fit_export.py).
- Labels: `../heart_entry_perturb2_20261101/results/labels_all.csv` (§731 + §745, 4,252 bases × 16 fights = 68,032
  rows, 1,437 source seeds), sha256 `93937a22d0fc56fb…`.
- States: §731's `variants.tar` (share `heart-entry-perturb/`, sha256 `ac30cf81c5554922…`, lines 0-999) followed by
  round 2's (share `heart-entry-perturb2/`, `bac886ef2754e0c4…`, lines 1000-4252); per-file sha256 of the 16
  concatenated `v<k>.jsonl` in the vocabulary file.
- Fit (2026-11-05, author container, xgboost 3.0.5, scikit-learn 1.9.1, numpy 2.5.3, ≈ 37 min wall on 4 cores): CV
  picked depth 2, min child weight 5, 3,077 rounds (CV BCE 0.4305); base score 0.6368; 337 of 440 features split on;
  in-sample BCE 0.347. The per-fold picks of §746's fit_all were depth 2-3, mcw 20, 1,550-3,090 rounds.
- Files:
  - `models/candidates/silver_price_a746.trees` (CompactTreeNet, logistic; sha256 `350667379969aae2…`);
  - `models/candidates/silver_price_a746.vocab.json` (440 feature names in column order, monotone constraints,
    hyperparameters, label / state / trees sha256; sha256 `65879355b0506a49…`);
  - `tests/data/silver_price_a746.parity.jsonl` (288 stored states with Python's sparse feature row and margin);
  - XGBoost model `model_a.ubj` on the share (`leaf-plan/price-table/`, sha256 `e3c31b1e81f0a3f4…`), not in the repo.
- Reproduce: `python3 fit_export.py LABELS_ALL.csv VARIANTS_ALL_DIR OUT_DIR` (the variants dir = the two tars'
  `v<k>.jsonl` concatenated, §731 first).

## Checks (author container, Release build)
- `silver_price_table` (ctest): feature rows identical to Python on 288 states, max |margin − XGBoost| 1.0e-5
  (float32 vs double accumulation); GameContext → state equal on 32 states; 288/288 tables with a non-decreasing HP
  curve and potion prices ≥ 0.62 HP; leaf without a table = Silver's default; with a table monotone in HP and potions;
  build 0.58 ms per table (17 model rows on average).
- `silver_price_table_off_identity` (ctest): 4 S&S → Heart act4replay fights (flat 500 sims, seeds 111459990-993):
  rows equal main 4851f703's (`tests/data/silver_price_table_identity/expected.csv`, written by a 4851f703 build)
  with the option unset and `=0`; `a746` loads, logs and plays.

## Tables on §724's 592 S&S entry states (descriptive)
`silver_price_table_test --report` on `ss_states.tar` (share `incense-term-gate/`); output
`leaf-plan/price-table/ss_tables.jsonl` on the share. 513 of 592 states start S&S at full HP.

| quantity | 5% | 25% | median | 75% | 95% |
|---|---|---|---|---|---|
| U(start HP), HP units (the default leaf gives the HP itself, ≈ 70-110) | 45 | 78 | 146 | 273 | 402 |
| potion price, HP units (default 11; 882 potions) | 1.8 | 8.8 | 12.8 | 21.6 | 54.1 |
| max-HP price, HP per point (default 2) | −1.39 | −0.77 | −0.43 | −0.14 | +0.55 |
| (winBonus + U + potions) / model's own win value V(start) / s | 0.29 | 0.85 | 1.27 | 1.81 | 2.41 |

- Fairy in a Bottle (129 states): 36 / 44 / 55 HP (quartiles); the default leaf's death save is 0.3 × max HP ≈ 25.
- The scale floor (a quarter of the chord slope) binds in 18% of states, mostly at full HP, where the model's top
  HP segment is flat.
- Max HP is priced negative in most states: at fixed HP more max HP lowers the HP fraction, which the model weighs
  more than max HP itself. A Feed kill (+3 max HP, +3 HP) is worth U(h + 3) − U(h) + 3 × that price.
- The win-value ratio shows what keeping `winBonus` = 53 means: the table prices dying against a start-like win
  between 0.3× and 2.4× of what the model itself says (median 1.27×). Stage C co-reports S&S deaths for this reason.
- Incense Burner counter prices (all 592 states; centred per state, mean HP per counter 0..5):
  −2.7, −2.7, −3.1, +6.3, +8.5, −6.2, against §723's kill pp × 1.33 centred: −2.3, +2.5, −11.0, +7.6, +13.5, −10.4.
  Correlation of the means 0.90; per-state correlation median 0.89, positive in 592/592. The refit model prices the
  Incense phase at about 0.6× §723's size and misses counter 1. §732's "model A missed the Incense phase" was on
  §731's labels only; the refit adds §745's 320 Incense counter changes. These states and §723's are from the same
  source campaigns as the labels, so this is not an out-of-sample check.

## Anchored win bonus on the same 592 states (descriptive)
`silver_price_table_test --report` now builds the anchored table (`anchorRaw`, `anchorWinBonus`; the other fields are
unchanged); output `leaf-plan/price-table/ss_tables_anchor.jsonl` on the share. Raw anchor V(root)/s − (U(start) +
potion prices): 5/25/50/75/95% = −36.9 / −14.5 / 10.8 / 113.8 / 1,063.5. Clamped to [53, 212]: 398 states at the
floor (anchored table = plain table), 81 inside, 113 at the cap; mean bonus 92.5. Stage C's TA arm therefore differs
from T in about a third of the Incense states; the share for the other states is reported at freeze.

## Smoke (stage C configuration, not a result)
`act4replay` with `STS_ACT4REPLAY_CHAIN=heart`, learned budget, §724's Silver settings, the 4 identity states, battle
seeds 111459990-993 (used smoke block), OMP 4, arms off and `STS_SILVER_PRICE_TABLE_LEAF=a746`: both rc 0, 136 s
wall each; S&S CPU 18.2 s vs 17.3 s (4 fights), Heart kills 3/4 vs 4/4. Four states say nothing about the effect.
Rows and logs on the share (`leaf-plan/price-table/{off,on}.{csv,log}`).
