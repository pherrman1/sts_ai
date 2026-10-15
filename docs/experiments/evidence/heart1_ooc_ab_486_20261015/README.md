# §486 OOC MCTS with heart1 vs V4 as the tree prior (2026-10-15)

Pre-registration: [PREREG.md](PREREG.md). Result and interpretation: ledger §486 in `docs/experiments/ledger-06.md`
(after the run).

- Code commit `d094e012` (`CODE_COMMIT`, main `40532e7` plus `STS_OOC_MCTS_PRIOR=heart1` with its reward mappings and the exact AVX heart1
  forward pass), Release `one_combat` `7fa2a7e9…` (`binary.sha256`). Weights: silverbot `heart1.pt` `deaba59d…`
  exported to `heart1.bin` `1e92f2a6…` (`heart1_weights.txt`); workers copy it from
  `/mnt/project-files/heart1-ooc-ab-486/heart1.bin`.
- Arms (`arm_env.sh`): `v4` (§433 `combo`, V4 tree prior) and `heart1` (the same with the heart1 tree prior); chain
  rollouts in both. One `bestbench 10000 1 ASC SEED` unit per seed, arm and ascension (`run_unit.sh`, 8 h timeout),
  `NWORKERS` workers over the cohorts in `COHORTS` (`worker.sh`).
- Smokes: 74071950–74071967 direct heart1 policy (superseded design, `/mnt/project-files/heart1-ooc-ab-486/smoke.tar.gz`,
  sha256 `f2ac60ef…`); 74071970–74071974 OOC MCTS timing (pre-fix binaries); 74071975 (A20) and 74071976 (A0) heart1-arm act-1 smoke of the final binary for the prior-coverage gate (`smoke-mcts.tar.gz`).
- Analysis: `python3 tools/analyze_heart1_ab_486.py report.json DIR...` over the extracted `out/` folders
  (selftest: `python3 tools/analyze_heart1_ab_486.py selftest`).
