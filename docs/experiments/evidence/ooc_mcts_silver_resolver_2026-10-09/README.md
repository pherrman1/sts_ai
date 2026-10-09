# §410 evidence: OOC MCTS with a Silver combat resolver (pilot)

- [PREREG.md](PREREG.md): question, arms, matched-CPU calibration, cohort, analysis, validity.
- [arm_env.sh](arm_env.sh), [run_unit.sh](run_unit.sh), [worker.sh](worker.sh): the run harness.
  `CODE_COMMIT` is the build commit; [binary.sha256](binary.sha256) its Release `one_combat`.
- Calibration trace rows (seed 64009000): [prod](calibration-prod.mcts.csv),
  [silv2048](calibration-silv2048.mcts.csv).
- Analysis: `python3 tools/analyze_silver_resolver_pilot.py report.json /mnt/project-files/ooc-mcts-silver-resolver/w0{1,2,3,4}`.

Raw data (not in git): `/mnt/project-files/ooc-mcts-silver-resolver/w01..w04/`.
