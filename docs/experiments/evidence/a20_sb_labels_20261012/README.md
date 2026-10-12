# §445 evidence: A20 short-branch label corpus and learned pickers

- `BRIEF-sb-labels.md`: the worker brief, verbatim (sha256 `6c441a8c…`). There were 25 workers, W=0..24.
- `data-sha256.txt`: sha256 of each `/mnt/project-files/v4-a20-retrain/sblabels-wW.tar.gz`. Each tar holds `out/s-<seed>.csv` (finished seeds), `stmp-*` partials (excluded), logs and provenance JSON.

## Rebuild
1. Concatenate every `out/s-*.csv` from the 25 tars (252,015 rows). Set `labelFloor := labelFloorAlt` (A20 trees) and drop `labelFloorAlt` and `labelWonAlt`. This gives `sbl_a20.csv`.
2. `split_sbl.json`: 80/20 split by seed (numpy rng 20261012), in the `train_strategic_tok.py` split format.
3. V4 retrains: run `train_strategic_tok.py sbl_a20.csv <name>` with `STRAT_LABEL_SCALE=floor STRAT_SPLIT_LOAD=split_sbl.json STRAT_INIT_CKPT=<deployed V4 checkpoint> STRAT_INIT_REUSE_NORM=1 STRAT_EPOCHS=30 STRAT_PATIENCE=30 STRAT_SELECT_METRIC=q_top1`.
   - `SBL30`: `STRAT_Q_ONLY=1`.
   - `SBLC`: `STRAT_Q_ONLY=1 STRAT_Q_TARGET=fallback_centered`.
   - `SBLCF`: `STRAT_Q_ONLY=0 STRAT_Q_TARGET=fallback_centered`.
   - `run_sblc.sh` runs the two centered models. Training logs are included, with the seed lists removed.
4. Gold2 scoring of the V4 models: the §432 recipe (`../v4_a20_retrain_20261009/gold2/README.md`, `tsq.py` patch) applied to each `*_best_qtop1.pt`.
5. GBM pickers: `gbm_rank.py` (log in `gbm_rank.log`) and the learning curve `gbm_lc.py` (`gbm_lc.log`).
6. `score_gold2c.py` builds the combined table `gold2_score_sbl.txt` on the 397 common decisions.

## Forward-map A20 trees (`a20_trees_fm/`)
- `build_fm.py` and `train_fm.py` are `build2.py`/`train.py` from the §432 packet with feature list `feats_fm.txt`: the 448 `v_rich` features, minus `nextEliteId` and `nextFight0-2`, plus `fmDElite..fmCTreasure`, `curMapX` and `curMapY` (456 in total).
- Same 157k runs, same 10-states-per-run sample and same validation seeds as the `v_*_a20_full` trees.
- Metrics are in `train.log`. Tree files: `/mnt/project-files/v4-a20-retrain/inputs/v_rich_a20_fm.txt` (sha256 `d5889c8efe2a7e50…`) and `v_win_a20_fm.txt` (`b489a67b1df3c114…`).
