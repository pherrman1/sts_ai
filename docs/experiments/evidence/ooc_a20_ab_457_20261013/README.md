# §457 OOC MCTS `combo` vs off at ascension 20 (2026-10-13)

Pre-registration: [PREREG.md](PREREG.md) (independent pre-launch review PASS; delta review PASS after the third arm
was added). Result and interpretation: ledger §457 in `docs/experiments/ledger-06.md`.

- Run commit `6679d0cd` (code `52e605fd`, Release `one_combat` `fdc44395…`, see `CODE_COMMIT`, `binary.sha256`).
- Arms (`arm_env.sh`): `off`, `combo` (A20 candidate CTM from `claude/ctm-a20-data` `34d4dfac`, pinned in
  `ctm_artifacts.txt`), `combo_def` (default CTM stack). One `bestbench 10000 1 20 SEED` unit per seed and arm
  (`run_unit.sh`), 8 workers × 16 seeds (`worker.sh`, worker brief
  `/mnt/project-files/ooc-a20-ab/BRIEF-worker.md` sha256 `d7dac9a8…`).
- Seeds 87000000–87000127; smokes 74047000–74047003 (`smoke.tar`: 74047000 off and default-CTM combo, 74047001 all
  arms, 74047002 combo, 74047003 combo with `STS_FORCE_RELIC=LIZARD_TAIL`).
- Raw: `/mnt/project-files/ooc-a20-ab/wWW.tar` (hashes in `data-sha256.txt`).
- Analysis: `python3 tools/analyze_ooc_a20_457.py report.json DIR...` over the extracted `out/` folders gives
  `report.json` (selftest: `python3 tools/analyze_ooc_a20_457.py selftest`).
