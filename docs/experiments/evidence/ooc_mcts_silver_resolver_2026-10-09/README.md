# §411 evidence: OOC MCTS with a Silver combat resolver (pilot)

- [PREREG.md](PREREG.md): question, arms, matched-CPU calibration, cohort, analysis, validity.
- [arm_env.sh](arm_env.sh), [run_unit.sh](run_unit.sh), [worker.sh](worker.sh): the run harness.
  `CODE_COMMIT` is the build commit; [binary.sha256](binary.sha256) its Release `one_combat`.
- Calibration trace rows (seed 64009000): [prod](calibration-prod.mcts.csv),
  [silv2048](calibration-silv2048.mcts.csv).
- [report.json](report.json): the analysis on all 16 workers; [smoke-summary.txt](smoke-summary.txt): the
  pre-launch smoke (seed 64009001); [data-sha256.txt](data-sha256.txt): hashes of the result CSVs.
- Analysis: `python3 tools/analyze_silver_resolver_pilot.py report.json $(for w in $(seq -w 1 16); do echo /mnt/project-files/ooc-mcts-silver-resolver/w$w; done)`.

Raw data (not in git): `/mnt/project-files/ooc-mcts-silver-resolver/w01..w16/`.
