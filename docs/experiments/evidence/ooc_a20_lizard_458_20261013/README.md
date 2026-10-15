# §458 §457 `combo` rerun with the Lizard-capable A20 CTM (2026-10-13)

Pre-registration: [PREREG.md](PREREG.md) (independent pre-launch review PASS, reviewer smoke seed 74055000). Result and
interpretation: ledger §458 in `docs/experiments/ledger-06.md`.

- Run commit `800fe39f` (code `52e605fd`, Release `one_combat` `fdc44395…`, the §457 binary; see `CODE_COMMIT`,
  `binary.sha256`). 16 workers × 8 seeds (`worker.sh`, brief `/mnt/project-files/ooc-a20-lizard/BRIEF-worker.md`
  sha256 `d261cb30…`).
- One arm, `combo_liz` (`arm_env.sh`): §457 `combo` with the §443 Step 1b Lizard candidate pinned in
  `ctm_artifacts.txt` (`claude/ctm-a20-data` `c507cebb`) and `STS_OOC_MCTS_ACTIVE_LIZARD=1`. The `off`, `combo` and
  `combo_def` rows are §457's (`/mnt/project-files/ooc-a20-ab/wWW.tar`).
- Seeds 87000000–87000127; smokes 74047010–74047011 (planning thread, `/root/a458-smoke`, not archived).
- Raw: `/mnt/project-files/ooc-a20-lizard/wWW.tar` (hashes in `data-sha256.txt`).
- Analysis: `python3 tools/analyze_ooc_a20_458.py report.json <§457 out dirs> <§458 out dirs>` gives `report.json`
  (selftest: `python3 tools/analyze_ooc_a20_458.py selftest`).
- Lizard step pre-registration and artifacts: `/mnt/project-files/ctm-a20/lizard/PREREG-LIZARD.md` (sha256
  `d2ea9904…`), `claude/ctm-a20-data:ctm-a20-stage4/candidate-lizard/` (commands log, fit receipt, SHA256SUMS).
