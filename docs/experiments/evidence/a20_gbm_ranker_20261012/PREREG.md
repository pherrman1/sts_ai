# §447: A20 GBM ranker in live play (pre-registration)

Question (Philipp, 2026-10-12 10:54Z, "Live test"): does the §445 A20 GBM ranker,
which beat the heuristic on the Gold2 regret benchmark (1.73 vs 2.26 floors) and was
not shown better than V4 (1.73 vs 1.98), win more floors than the current A20 stack
when it plays every out-of-combat decision?

- Code: the commit that adds `STS_OOC_GBM_RANKER` (default off), release `one_combat`.
  The run uses the pushed commit named in RESULT.md; the binary sha256 is recorded there.
- Model: `models/candidates/ooc_gbm_ranker_a20_sbl.txt` (sha256 372431c1…), exported by
  `export_win_model.export_booster(b, out, 1157)` from the §445 centered-regression
  booster `gbm_squarederror.json` (sha256 f4bdf068…, copy on the share at
  `/mnt/project-files/v4-a20-retrain/gbm/`). 1,015 features, 1,157 trees.
- Stack for both arms: `silver_learned_stop/live_env.sh` (V4 gates REST/EVENT/SHOP/
  TREASURE/BOSS_RELIC, margin 1.0, keys off), `STS_SILVER_LEARNED_STOP=1`,
  `STS_STOP_AFTER_ACT=3`, `bestbench 10000 128 20 79000000`. This is the §419 stack.
- Arms: C = stack as is. T = stack + `STS_OOC_GBM_RANKER=<model>`. The ranker takes every
  real OOC decision with at least two candidates after the chest rule, the reward-relic
  rule and Match and Keep; it overrides the V4 gates and the heuristic chain.
- Seeds 79000000..79000127, paired. Seeds 79009000..79009008 were smoke only.
- Primary: mean paired floor difference T − C, 95% paired bootstrap CI (10,000 reps,
  RNG 20261012). Secondary: wins, Act 3 reached, deaths per act.
- Decision: `GBM_BETTER` if the CI lower bound > 0; `GBM_WORSE` if the CI upper bound
  < 0; else `NOT_SHOWN`. No default change in any case; a default change is Philipp's
  call and would need a larger confirmation run.

Checks already run (smoke folder):
- Parity: on 628 live decisions (3,031 candidates) of 8 smoke seeds, the C++ scores match
  xgboost on the dumped features within 4.2e-6 and the argmax agrees on every decision
  (`parity.py`). Features come from the same `richRow` text strategicgen2 writes, so
  live/training feature parity holds by construction.
- Smoke 79009001..008 (not evidence): T 0/8 wins, mean floor 35.4; C 2/8, 38.4.
