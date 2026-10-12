# #401 feature-importance and grouped-ablation audit of the `v_win` / `v_rich` tree contract (§438)

Ledger entry: [ledger-06 §438](../../ledger-06.md). Analysis only: no tracked model, default or
feature contract changed.

## Provenance

- Repo at `491bc21b` (scripts in `scripts/` were run from a scratch directory; paths inside them point
  there). Python 3.13, xgboost 3.4.1, numpy 2.5.3, pandas 3.0.5, 4-CPU cloud container.
- Models (sha256): B0 `models/v_win_trees.txt` `fc52c14c…`; X2-B `models/candidates/v_win_x2b_trees.txt`
  `a251b33d…`; A20 win `models/candidates/v_win_a20_419.txt` `706c019a…`; A20 floor
  `models/candidates/v_rich_a20_419.txt` `bfd69fd3…`. Trees are evaluated with `scripts/fasttrees.py`, a
  vectorized copy of `tools/analysis/vwin_tree_utils.predict_rows` (max abs difference ≤ 1.2e-15 on
  2,000 rows for all three win models).
- **A0 data:** the four #334 collector returns on the share (`/mnt/project-files/vwin334-cloud-returns/`,
  154 source seeds), MAP rows joined to `runout.csv` `finalWon` (`trajectoryValid=1`). TEST seeds under
  the #334 split rule (`source_split`) were dropped at load and never read: 122 seeds remain (96 TRAIN,
  26 VALIDATION), 115,108 rows (many correlated branch rows per seed). B0 predates #334, so all 122 seeds
  are held out for it; X2-B was trained on #334 TRAIN, so it is scored on the 26 VALIDATION seeds only.
- **A20 data:** `strategicgen` v1 runs at ASC 20 from `/mnt/project-files/a20-value-retrain/runs-2c89ed97/`
  (frozen `2c89ed97`, the §419/§432 corpus). Every second chunk in sorted order (4,915 of 9,830 chunks),
  up to 8 random decision rows per run (`random_state=401`): 629,138 rows, 78,643 runs, win rate 4.7%,
  mean final floor 29.3. Split by `sha256("issue401-a20-v1:{seed}")`: TRAIN 62% / ES 8% (early stopping) /
  VAL 15% / TEST 15%. TEST rows were never used in any fit or metric. Packed matrix sha256 `4383fbba…`
  (not uploaded; `build_a20.py` + `pack_a20.py` rebuild it). No new gameplay seeds were run.
- A20 permutation of the §419 A20 trees uses only rows from that training's own validation seeds
  (`v4_a20_retrain_20261009/gold2/a20_trees/val_seeds.json.gz`) that are not in this audit's TEST split:
  34,424 rows, 4,303 runs. (The first pass included 6,216 TEST-split rows; it was rerun without them after
  review. Group deltas moved by at most 1.1 MSE / 0.006 NLL; the earlier numbers are not used.)

## Method

Semantic groups (`scripts/groups.py`) over the 448 B0 inputs: progress (act, floor), hp, gold, potion
slots, keys, deck cards (`d*` + deckSize), upgrades (`u*`), relics (`r*`, value 1 + relic counter),
potions (`pot*`), bottled ids, path history (`pv*`), boss, future encounters (nextEliteId, nextFight0–2;
hidden per §371), queue counters (remElites, remFights, monOffset, eliteOffset; public per §371), RNG
pity counters (potionChance, cardRarityFactor), and the 12 forward-map columns (`fm*`, curMapX/Y), which
are in the data and in X2-B but not in B0.

- **Stage 1, permutation:** shuffle a whole group's columns jointly across rows (2 repeats), report the
  held-out loss increase with a 95% seed-cluster bootstrap CI. Permutation measures what a *trained*
  model uses, not what is necessary.
- **Stage 2, retrain ablations (A20):** refit XGBoost per arm (eta 0.1, depth 6, subsample 0.8,
  colsample 0.5, min_child_weight 20, hist, early stop 50 on ES), score VAL; delta = arm − FULL per row,
  95% seed-cluster bootstrap (1,000). Targets: final floor (MSE, the `v_rich` target) and won (log loss,
  the `v_win` target). `FULL#2`–`FULL#4` are FULL refit with three other seeds: the retraining null.
  The bootstrap CIs cover VAL sampling only, not refit randomness; read every delta against the refit
  spread (four FULL fits span 0.09 floor MSE and 0.0009 win NLL; a reviewer's independent rerun suggests
  refit noise up to about ±0.15 MSE).
- **A0 cross-check:** same arms subset on #334 TRAIN → VALIDATION, depth 4, eta 0.05, 3 training
  seeds averaged.

## Results

### Stage 1 permutation (Δ held-out loss; groups ordered by B0)

| group | B0 on A0 (122 seeds), ΔNLL | X2-B on A0 VAL (26 seeds), ΔNLL | A20 win (§419), ΔNLL | A20 floor (§419), ΔMSE |
|---|---|---|---|---|
| relics | +0.083 [0.049, 0.114] | +0.047 [0.010, 0.089] | +0.055 [0.049, 0.063] | +70.6 [66.9, 74.1] |
| progress | +0.054 [0.048, 0.059] | +0.002 | +0.003 | +17.4 |
| deck cards | +0.050 [0.025, 0.075] | +0.019 | +0.016 | +45.7 |
| hp | +0.037 [0.024, 0.053] | +0.035 | +0.007 | +13.8 |
| path history | +0.023 | +0.009 (n.s.) | +0.001 | +6.0 |
| future encounters (hidden) | **+0.0155 [0.013, 0.018]** | +0.0004 (n.s.) | −0.0003 (n.s.) | **+4.3 [3.9, 4.8]** |
| boss | +0.003 (n.s.) | +0.004 | −0.000 (n.s.) | +1.5 |
| potion slots | +0.003 | +0.003 (n.s.) | +0.000 | +1.3 |
| queue counters | +0.001 (n.s.) | +0.002 | +0.001 | +2.1 |
| RNG counters | +0.001 | +0.0004 (n.s.) | +0.000 | +0.2 |
| potions | +0.000 | +0.013 | +0.001 | +2.3 |
| upgrades | −0.001 (n.s.) | +0.016 | +0.004 | +10.8 |
| bottled / keys / gold | ≈ 0 | ≈ 0 | ≈ 0 | ≤ 0.12 |
| forward map | not an input | +0.0005 (n.s.) | not an input | not an input |

Baselines: B0 on A0 NLL 0.611, AUC 0.726, mean prediction 0.577 vs win rate 0.762 (B0 underpredicts
#334 wins); X2-B NLL 0.397, AUC 0.795; A20 win NLL 0.141, AUC 0.851; A20 floor MSE 96.9. Dead inputs:
B0 has 16 of 448 inputs never split and 5 constant on the A0 rows. Per-relic permutation (top: Dead
Branch, Snecko Eye, Shuriken, Brimstone in both B0 and the A20 tree) shows the relic group's weight is
spread over many relics, not one proxy column (`results/relic_perm_*.json`).

### Stage 2 retrain ablations on A20 (VAL 93,911 rows, 11,739 runs)

| arm | floor ΔMSE (FULL 101.23) | win ΔNLL (FULL 0.1447) |
|---|---|---|
| − relics | +6.64 [+5.89, +7.32] | +0.0118 [+0.0095, +0.0142] |
| − deck cards | +5.50 [+4.87, +6.12] | +0.0054 [+0.0037, +0.0069] |
| − hp | +3.22 [+2.76, +3.67] | +0.0018 [+0.0006, +0.0029] |
| − potions | +0.93 [+0.60, +1.27] | +0.0000 |
| − progress | +0.45 [+0.19, +0.70] | +0.0000 |
| − upgrades | +0.43 [+0.13, +0.71] | +0.0000 |
| − boss | +0.23 (n.s.) | −0.0001 |
| − future encounters (hidden) | +0.01 (n.s.) | −0.0000 |
| − queue counters | +0.06 (n.s.) | −0.0002 |
| − RNG counters | −0.09 (n.s.) | −0.0002 |
| PUBLIC (− all three above, 10 columns; also drops the queue counters, which §371 classes as public) | +0.18 [−0.08, +0.45] | −0.0005 [−0.0014, +0.0003] |
| PUBLIC′ (− hidden future, − RNG; queue counters kept, 6 columns) | +0.14 [−0.15, +0.42] | −0.0005 [−0.0014, +0.0004] |
| − bottled / − potion slots / − gold / − keys | within ±0.12 (n.s.) | within ±0.0004 (n.s.) |
| − path history | −0.27 [−0.53, −0.04] | +0.0009 [−0.0000, +0.0017] |
| cyclic relic counters → presence | −0.19 [−0.38, +0.01] | −0.0005 [−0.0013, +0.0002] |
| **+ forward map** | **−2.15 [−2.51, −1.80]** | −0.0008 [−0.0016, −0.0000] |
| PUBLIC + forward map | −2.24 [−2.63, −1.85] | −0.0005 (n.s.) |
| FULL#2 / #3 / #4 (refit null) | −0.04 / +0.05 / +0.03 | +0.0004 / −0.0000 / −0.0005 |

"Cyclic relic counters" are Happy Flower, Incense Burner, Ink Bottle, Nunchaku, Pen Nib, Sundial and Tiny
Chest, whose `r*` value carries an in-combat cycle counter.

### A0 cross-check on #334 (TRAIN 96 seeds → VALIDATION 26 seeds)

FULL VAL NLL 0.4695 (a constant 0.81 predictor scores about 0.487). PUBLIC −0.0014 [−0.0061, +0.0034];
+forward map +0.0006 [−0.0022, +0.0035]; PUBLIC + forward map +0.0056 [+0.0004, +0.0107]; −upgrades
+0.0041 (n.s.); −relics −0.033 [−0.073, +0.004]. The training-seed spread is up to 0.013 NLL, above every
difference except −relics, so this corpus cannot resolve any group (consistent with §371's 0.007–0.010
seed noise); −relics pointing *better* suggests the 147 relic columns overfit 96 seeds.

## Interpretation (Inference)

- Relics, deck cards and HP carry most unique signal for both targets and every model family audited;
  potions, progress and upgrades add a little for floor only.
- The hidden future-encounter fields are used by B0 at A0 and by the A20 floor tree (not by the A20 win
  tree). A refit without them, or without all ten hidden/queue/RNG columns, shows no loss we can detect at
  A20: at most about 0.45 floor MSE (upper CI) on top of refit noise. The signal looks recoverable from
  public inputs, which supports a public-only contract (#397) on this corpus.
- The forward map is the only missing group tested, and it helps: −2.15 floor MSE at A20, far outside the
  refit spread, borderline on win (4.7% positives). This resolves §418's A0 `INCONCLUSIVE` only for A20 floor; at A0
  it remains unresolved on the available #334 fragment.
- Bottled ids, keys, gold, potion slots and boss id have no unique value at A20. They are cheap integer
  counters, so removal buys no runtime; no deletion recommended.

All results are offline prediction-error changes on the generator's own runs (`strategicgen` v1, A20;
#334 fragment, A0). None is a measured win-rate change.

## Not done

No MLP, #379 screen leaf, #399 policy, #400 stopping or CTM audit; no live or gameplay test; no TEST split
opened; feature-build runtime not measured (all inputs are counters from one `GameContext` pass plus
one map-reachability sweep for the forward map); full #334 corpus (on Philipp's machine) not used.
