# §486 heart1 OOC policy vs our V4 OOC stack (2026-10-15)

Pre-registration: [PREREG.md](PREREG.md). Result and interpretation: ledger §486 in `docs/experiments/ledger-06.md`
(after the run).

- Code commit `59bb91a` (`CODE_COMMIT`), Release `one_combat` `1e4e17b6…` (`binary.sha256`). Weights: silverbot
  `heart1.pt` `deaba59d…` exported to `heart1.bin` `1e92f2a6…` (`heart1_weights.txt`); workers copy it from
  `/mnt/project-files/heart1-ooc-ab-486/heart1.bin`.
- Arms (`arm_env.sh`): `v4` (§457 `off` environment) and `heart1` (the same plus `STS_OOC_HEART1`). One
  `bestbench 10000 1 ASC SEED` unit per seed, arm and ascension (`run_unit.sh`), `NWORKERS` workers over the
  cohorts in `COHORTS` (`worker.sh`).
- Smokes: 74071950–74071967, `/mnt/project-files/heart1-ooc-ab-486/smoke.tar.gz` (sha256 `f2ac60ef…`).
- Analysis: `python3 tools/analyze_heart1_ab_486.py report.json DIR...` over the extracted `out/` folders
  (selftest: `python3 tools/analyze_heart1_ab_486.py selftest`).
