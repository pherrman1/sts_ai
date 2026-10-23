# The CTM-calibration default plays the reviewed flag; `=0` plays main (2026-10-23)

**Question.** [ADR-0058](../../../../decisions/0058-ctm-calibration-default.md) makes the §670 per-fight CTM
calibration the default of the built-in A20 stack. The guard
([`../ctm_calibration_20261023/PREREG.md`](../ctm_calibration_20261023/PREREG.md)) compares `STS_CTM_CALIBRATION=0`
(arm A) with the default (arm C). Does arm C play exactly what the reviewed flag `STS_CTM_CALIBRATION=<table>` played
on main, and does arm A play exactly what main played with the flag unset?

**Design.**
- Binaries (x86-64-v3 release `one_combat`):
  - `main`: built from the code of main `a103a9b7` (#838 merged; built at `ffc1228c`, whose code is the same), sha256
    `94437a98…`;
  - `new`: built from this change before the merge of main `05fac5ab` (`b10c5dba`), sha256 `b855ee27…`. Main's
    changes since `a103a9b7` do not reach `one_combat`; the merged head's incremental build keeps the same binary.
- Seeds: two smoke seeds on which the arms played differently in the §670 smoke: 111394991 (first different decision
  1) and 111394992 (decision 54).
- Games, each one `heartoutcomegen` game under `tools/seed_guard.sh` as in the guard:
  - `old`: main's `../ctm_calibration_20261023/run_unit.sh` on the `main` binary: A with the flag unset (raw CTM), C
    with the explicit table;
  - `new`: this change's `run_unit.sh` on the `new` binary: A with `=0`, C with the flag unset (the default);
  - `exp`: [`run_exp.sh`](run_exp.sh) on the `new` binary with `new` C's environment and the explicit table.
- [`compare.py`](compare.py) requires a complete, integrity-passed outcome footer in every game and compares every
  record after the header and every CTM row. The header holds file paths and the git sha, so it differs.
- Scores: [`../ctm_calibration_20261023/offline/score.sh`](../ctm_calibration_20261023/offline/score.sh) with the
  `new` binary on the §670 row sets (103,583 real fights: the four stage-3 arms and the 256 held-out stage 1–2
  games), unset and `=0`, against the §670 hashes in
  [`../ctm_calibration_20261023/offline/scores.sha256`](../ctm_calibration_20261023/offline/scores.sha256).

**Result.** **PASS** ([`compare.txt`](compare.txt)).
- All 10 games ended with rc 0 and a complete, integrity-passed footer. The calibration banner
  (`table=…ctm_calibration_pathb_a20_v1.json sha256=359619f7… groups=34`) is in every C and `exp` game and in no A
  game.
- Arm C with the default plays exactly as arm C on main with the explicit table, and as the explicit table on the
  `new` binary: every record and every CTM row, on both seeds.
- Arm A with `=0` plays exactly as arm A on main with the flag unset, on both seeds.
- A and C differ on both seeds. The games, the same on both binaries:

  | seed | arm | records | CTM rows | end |
  |---|---|---|---|---|
  | 111394991 | A | 397 | 33 | Heart killed (Act 4, floor 56) |
  | 111394991 | C | 191 | 17 | died in Act 2, floor 24 |
  | 111394992 | A | 217 | 19 | died in Act 2, floor 29 |
  | 111394992 | C | 217 | 19 | died in Act 2, floor 29 |
- Scores: on all five row sets the `new` binary gives the §670 `cal/` scores unset and the `off/` scores with `=0`,
  byte for byte.
- The first run of A-111394991 was cut after 47 records on both binaries. The two seeds ran in parallel into one
  directory, and when one seed's `run_unit.sh` ended, it gzipped every `*.jsonl` there, including the running game's
  file. Seed 111394991 was rerun alone, both arms, in its own directory; its C games equal the first run's. The guard
  cannot hit this, because its worker gives every unit its own directory (`tools/cloud/worker.sh`). `compare.py` now
  requires a complete footer.
- Outputs (the 10 games, `compare.txt`, score hashes):
  `/mnt/project-files/ctm-calibration/ctm_calibration_default_eqcheck_20261023.tar.gz` (sha256 `a9f6ac6c…`).

**Conclusion.** Only the switch changed. The guard's arm C plays exactly what the reviewed §670 flag played,
and arm A exactly what main played, and the real-fight scores agree on all 103,583 fights.

## Commands
From the repository root (`D` = this directory):
```
E=<scratch dir>; D=docs/experiments/evidence/ctm_calibration_default_20261023
BIN=build/linux-gcc-release-x86-64-v3/one_combat
git show a103a9b7:docs/experiments/evidence/ctm_calibration_20261023/run_unit.sh > $E/run_unit_main.sh
# one directory per seed: run_unit.sh gzips every *.jsonl in its directory when its unit ends
bash $E/run_unit_main.sh $PWD $E/run_main $E/old-SEED SEED        # run_main: main's one_combat + student_sel.bin
bash docs/experiments/evidence/ctm_calibration_20261023/run_unit.sh $PWD $E/run_new $E/new-SEED SEED
bash $D/run_exp.sh $PWD $E/run_new $E/new-SEED/C-SEED.env $E/exp/C-SEED SEED \
  STS_CTM_CALIBRATION=models/candidates/ctm_calibration_pathb_a20_v1.json
# copy old-*/* to $E/old/ and new-*/* to $E/new/
python3 -I $D/compare.py $E/old $E/new $E/exp 111394991 111394992 > $D/compare.txt
S=docs/experiments/evidence/ctm_calibration_20261023/offline/score.sh   # ROWS: the §670 row sets (extract.sh)
bash $S $BIN ROWS $E/scores/unset off     # sha256 = cal/ in scores.sha256
bash $S $BIN ROWS $E/scores/zero0 off0    # sha256 = off/
```
