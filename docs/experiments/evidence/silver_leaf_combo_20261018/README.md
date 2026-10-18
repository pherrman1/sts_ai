# Silver victory-leaf combination A/B (whole A20 runs, student_sel, OOC MCTS off)

Pre-registration: [PREREG.md](PREREG.md). Analysis: extract each worker tar into its own directory, then
`tools/analyze_silver_leaf_combo.py analyze <this dir> <extracted dirs...>` (it reads unit files, not tars).

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

## Result (ledger-06 §TBD)

3,584/3,584 units rc=0, 16/16 tars verified ([verify.txt](verify.txt), [tars.sha256](tars.sha256)), 512 pairs.
Five of six arms are WORSE than base (18.8% wins, 38.88 mean floor) on floors; per-type `WT` is NOT_SHOWN; see [result.json](result.json) and the ledger table.
Largest losses: `K27` −5.23 floors / −8.4 pp wins, `WTK27` −6.32 / −9.0. Seeds 111198948–111198949 unused; 111198950–111198965 reviewer block.
