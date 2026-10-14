# §443 Stage 4: Lizard support and the fresh-seed re-gate of the A20 CTM (2026-10-13 to 2026-10-14)

Ledger: §443 (continued) at the end of `docs/experiments/ledger-06.md`.

- `PREREG-REGATE.md`: Stage 4 pre-registration (approved 2026-10-13 15:00Z; sha256 c7a27aaf…). Its Step 1 could not
  run as written; `PREREG-LIZARD.md` (Step 1b, with the step-4 amendment and Philipp's 2026-10-14 09:38Z override
  of the failed keep check) replaces it.
- Lizard candidate artifacts and the full build log: `claude/ctm-a20-data` `c507cebb`,
  `ctm-a20-stage4/candidate-lizard/` (data only, never merged).
- Gate tools: `claude/ctm-a20-data` `6faa5695`, `ctm-a20-stage4/regate-tools/` (frozen `gate3a.py` 25f7dc00 and the
  Stage 3a run script, copied from Philipp's machine).
- `run_regate.sh` + `FROZEN.txt`: the re-gate as run in the cloud (binary built at 40db7d62, sha256 e59727ca, identical
  to Stage 3a's), frozen before any scoring. Rows: every row of the fresh Stage 4 corpus (`claude/ctm-a20-data`
  `ctm-a20-stage4/`, units with rc=0 plus the w02 per-seed rerun; seed 78600595 excluded), no TEST filter.
- `main_fresh.json`: gate result (NOT_QUALIFIED); `lizard_fairy_fresh.json`, `lizard_brew_fresh.json`: diagnostics.
  Score CSV hashes: `/mnt/project-files/ctm-a20/regate/fresh/results/scores.sha256`.
