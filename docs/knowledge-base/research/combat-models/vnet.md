# VNet combat value

Last verified: 2026-08-11.

## Purpose / research question

Can a learned combat value model (predicting end-of-fight HP) improve Searcher3's
leaf evaluation? What training data, target, and hyperparameters produce the
best online transfer?

## Current conclusion

**A hyperparameter-tuned XGBoost GBM trained on honest combat data predicting
end-HP is the deployed combat value leaf.** It provides +12.5pp win over
rollout-only at α=0.3. The deployed model is `build/v_combat_7k_tuned.txt`
(1,000 trees, sha256 `ea35b78c…`, §148, 2026-08-09), which superseded the
earlier 804-tree honest model (§126).

The learning target is raw end-of-fight HP. Direct utility-R as a target
(won ? 50+endHp : 0) has better offline calibration but is significantly
worse online — the third documented case of offline≠online transfer.

## Evidence map

| When | Evidence | Result |
| --- | --- | --- |
| 2026-07-30 | [Phase 4b PVNet alpha sweep](../../../../docs/experiments/ledger-03.md) | Early experiment with PVNet as value leaf |
| 2026-08-04 | [§97 Combat value under gate stack](../../../../docs/experiments/ledger-03.md) | Old-era 1,500-tree vnet rejected (−3.1pp at α0.3) |
| 2026-08-07 | [§126 Honest-data V_combat promoted](../../../../docs/experiments/ledger-05.md) | Three gates +12.5/+12.1/+12.5pp → promoted to default ON in fair-S3 |
| 2026-08-07 | [Decision: VNet promotion](../../../decision-log/2026-08-07-vnet-promotion.md) | Promotion rationale + cpu-trade call |
| 2026-08-07 | [§129 Gate-stack-distribution retrain](../../../../docs/experiments/ledger-05.md) | NULL for replacement; α optimum shifts 0.3→0.5 but no win improvement |
| 2026-08-09 | [§148 Hyperparameter tuning](../../../../docs/experiments/ledger-06.md) | Optuna TPE search; +10.9pp at matched 804 trees → deployed as 7k model |
| 2026-08-09 | [§154 Training-vs-deployment distribution shift](../../../../docs/experiments/ledger-06.md) | Mismatch is WEAK — do NOT build a relabeling pipeline |
| 2026-08-08 | [§137 Covariate-shift mixture retrain](../../../../docs/experiments/ledger-06.md) | Mixture does NOT improve search-leaf ranking; branch closed |
| 2026-08-09 | [§150 Per-encounter specialization](../../../../docs/experiments/ledger-06.md) | Gate negative, line closed |
| 2026-08-07 | [§131 Target-vs-data ablation](../../../../docs/experiments/ledger-05.md) | Fresh data is the big lever (2.7×), utility target adds 31% on identical data |
| 2026-08-07 | [§133-§134 Utility-R GBM online gate](../../../../docs/experiments/ledger-05.md) | Falsified at every α despite better offline EV |

## Hyperparameter configuration

The deployed model uses the §148 tuned parameters:
- max_depth 8, eta 0.03, subsample 0.54, colsample_bytree 0.81
- min_child_weight 82, reg_alpha 1.8, gamma 4.4
- 2,000 rounds, 40 early stop
- 1,000 trees in the deployed model

## Rejected / falsified approaches

- **Old-era (pre-§113) combat data** — vnet rejected under gate stack (§97)
- **Gate-stack-distribution retrain** — no improvement over honest-only data (§129)
- **Covariate-shift mixture (combatgen + leafdiag)** — hurts search-leaf ranking (§137)
- **Per-encounter specialization** — gate negative (§150), line closed
- **Direct utility-R target** — significantly worse online (§133/§134)
- **Distillation from deeper search** — not worthwhile (§151)

## Relationships

- [leaf-evaluation.md](../combat-search/leaf-evaluation.md) — VNet is the primary leaf evaluator
- [pvnet-and-alternatives.md](pvnet-and-alternatives.md) — PVNet value head as alternative leaf
- [searcher3.md](../combat-search/searcher3.md) — VNet loads by default in the fair-S3 path

## Current implementation

Default ON in the fair-S3 path since 2026-08-07. `STS_VNET=<path>` overrides;
`STS_VNET=<missing-path>` disables. `STS_VNET_ALPHA` defaults to 0.3.
S2 fair / non-fair paths are env-only (no default vnet load).

See [`docs/knowledge-base/architecture/combat-search.md`](../../architecture/combat-search.md)
and [`docs/knowledge-base/architecture/training-and-inference.md`](../../architecture/training-and-inference.md).

## Open questions

- The exact §126 `v_combat_honest.txt` (804-tree) artifact provenance is deferred.
- The §148 `v_combat_7k_tuned.txt` artifact is verified at sha256 `ea35b78c…`.
- Is value-scale normalization a viable bridge between end-HP VNet and utility-R targets?
