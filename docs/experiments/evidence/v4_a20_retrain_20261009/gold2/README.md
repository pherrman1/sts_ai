# §432 evidence: Gold2 scoring and A20 candidate trees

Paths below that start with `/tmp/claude-0/` were container-local during the run; this file records how to rebuild them.

## Inputs (share)
- Old gold: `/mnt/project-files/v4-a20-retrain/gold-2c89ed97/w00..w24/chunk-*.csv.gz` (71 files, 262 seeds).
- Gold2: `/mnt/project-files/v4-a20-retrain/gold2-w{0..24}.tar.gz` (each holds `out/s-<seed>.csv`, 260 seeds).
- SB2: `/mnt/project-files/v4-a20-retrain/sb2-gold-w{0..7}.tar.gz` (`out/s-<seed>.csv`).
- Tarball sha256s are in `data-sha256.txt`.

## Building the scoring tables
1. `gold.csv` is the concatenation of every old-gold `chunk-*.csv.gz` (109,438 rows, no duplicates on `seed,decIdx,action`).
2. `gold2.csv` is the concatenation of every `out/s-*.csv` in the extracted Gold2 tars (108,579 rows), in the same column order.
3. SB2 tars were extracted to `/tmp/claude-0/sb2/wW/`.
4. Neural pickers: `train_strategic_tok.py` with `train_strategic_tok_regret_dump.patch` applied (it adds `q_regret`, `q_top1_ties` and the per-decision list `_qd` = (seed*1e6+decIdx, regret, tie-aware hit) to the metrics JSON). Run at 0 epochs for each checkpoint:
   `STRAT_DEVICE=cpu STRAT_TOK_COMPILE=0 STRAT_LABEL_SCALE=floor STRAT_SPLIT_LOAD=split_gold.json STRAT_INIT_CKPT=<ckpt> STRAT_INIT_REUSE_NORM=1 STRAT_Q_ONLY=1 STRAT_EPOCHS=0 python3 tsq.py gold2.csv g2eval_<name>`.
   The `split_gold.json` split puts seed 69100000 in train and the other 261 seeds in val. Checkpoints:
   - `v4final.pt`, the deployed V4 checkpoint
   - `W30_best_qtop1.pt`, the §419 G2 retrain
   - `R2W30_best_qtop1.pt`, the §419 G3 retrain
5. `score_gold2.py` joins the four sources and writes `gold2_score.txt`. `score_sb2_vs_oldgold.py` writes `sb2_vs_oldgold.txt`.

## A20 candidate trees (`models/candidates/v_{rich,win}_a20_419.txt`)
Files are in `a20_trees/`.
- `feats_rich.txt`: the 448 `feat` lines of `models/v_rich_trees.txt` (`grep "^feat " models/v_rich_trees.txt | awk '{print $2}'`). The win trees use the same list.
- `build2.py`: converts each `/mnt/project-files/a20-value-retrain/runs-2c89ed97/*/chunk-*.csv.gz` (`strategicgen` v1 A20 runs, seeds 71000000+10000*W+k) to parquet. At training time 6,329 chunk files existed; their names are in `parts_used.txt.gz`. More chunks landed later.
- `train.py`: samples 10 states per run (1,012,391 states, 101,241 runs) and makes a run-grouped 90/10 split (rng 20261011; validation seeds in `val_seeds.json.gz`). It reports the A0 trees on validation, then fits XGBoost warm-started from the A0 booster and from scratch. Both are exported with `export_win_model.export_booster`.
- The committed candidates are the scratch fits (sha256 `bfd69fd3…` floor, `706c019a…` win). Metrics are in `train.log` and `v_*_a20_metrics.json`. xgboost 3.4.1.
