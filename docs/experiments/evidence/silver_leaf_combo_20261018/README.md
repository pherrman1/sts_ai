# Silver victory-leaf combination A/B (whole A20 runs, student_sel, OOC MCTS off)

Pre-registration: [PREREG.md](PREREG.md). Analysis: `tools/analyze_silver_leaf_combo.py analyze <this dir> <tars...>`.

- Arms: `base`, `W`, `WT`, `K27`, `K135`, `WTK27`, `WTK135` ([run_unit.sh](run_unit.sh)); per-type potion weights
  [WEIGHTS_TYPE](WEIGHTS_TYPE) from [derive_weights.py](derive_weights.py) on the PR #665 probe tars.
- Cohort: A20 seeds 111198434–111198945 (512), all seven arms ([units.txt](units.txt), arm-major).
- Smoke: 111198946 (all seven arms, 2026-10-18 17:49Z, uncommitted pre-freeze build: rc=0, 39–46 s per run, each
  arm logs its research-leaf line, student_sel loaded, arms diverge in max HP and death fight; all die on floor 33).
  111198947–111198949 for later smokes; 111198950–111198965 for the pre-launch reviewer (coordinator block 111198434–111198965).
