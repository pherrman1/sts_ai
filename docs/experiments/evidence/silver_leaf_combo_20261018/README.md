# Silver victory-leaf combination A/B (whole A20 runs, student_sel, OOC MCTS off)

Pre-registration: [PREREG.md](PREREG.md). Analysis: `tools/analyze_silver_leaf_combo.py analyze <this dir> <tars...>`.

- Arms: `base`, `W`, `WT`, `K27`, `K135`, `WTK27`, `WTK135` ([run_unit.sh](run_unit.sh)); per-type potion weights
  [WEIGHTS_TYPE](WEIGHTS_TYPE) from [derive_weights.py](derive_weights.py) on the PR #665 probe tars.
- Cohort: A20 seeds 111198434–111198945 (512), all seven arms ([units.txt](units.txt), arm-major).
- Smoke: 111198946 (all seven arms, 2026-10-18 17:49Z, uncommitted pre-freeze build: rc=0, 39–46 s per run, each
  arm logs its research-leaf line, student_sel loaded, arms diverge in max HP and death fight; all die on floor 33).
  111198947–111198949 for later smokes; 111198950–111198965 for the pre-launch reviewer (coordinator block 111198434–111198965).
- Frozen code: `c52d9ccf81f3f64d7a1ec1439d7788df0e3c8ce1` (main `b807c5b4` + this change: g7f_E rollout root table default, Curl Up lethal fix and
  every merged default up to #665), `one_combat` sha256 `b9d43a55…2593`. Smoke 111198947 on that binary (arms
  `base`, `WTK135`): rc=0, 114 / 112 s, both reach floor 56 (base dies to the Heart, WTK135 wins), the g7f_E
  root table and the arm's research-leaf line in the logs.
