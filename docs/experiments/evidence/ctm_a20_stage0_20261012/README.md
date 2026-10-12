# §443 Stage 0 and G0: production CTM at A20, generator policy for an A20 corpus (2026-10-12)

Raw data (shared project folder, not in Git): `/mnt/project-files/ctm-a20/`
- `stage0-78100000-999.tgz` (sha256 `4378e54e…`): generator output, both `ctmscorerows` score files, `report.json`.
- `g0-smoke-78009004-043.tgz` (sha256 `c83b1ad2…`): G0 smoke output, both teachers, the flag-off check.
- `PLAN.md` (draft plan and decision rules, written before Stage 0 ran), `STAGE0-RESULT.md`.

## Stage 0
Main `fcd253f1`, Release `one_combat` sha256 `c3c5e950…`. Teacher: `make_teacher.py fcd253f1… BINARY . teacher.json`.
Four units of 250 seeds, each run as
```
env -i PATH="$PATH" HOME="$HOME" OMP_NUM_THREADS=1 <teacher environment> \
  bash tools/seed_guard.sh BINARY combattransitiongen 250 10000 20 OUT.jsonl LO teacher.json
```
with LO = 78100000, 78100250, 78100500, 78100750. Scoring, from the repo root: `one_combat ctmscorerows ROWS OUT.csv`
once on the rows as generated and once with `predictorInput.globals.ascension` set to 0, then
`analyze.py ASC20.csv ASC0.csv report.json`.

## G0 smoke
Commit `c67ba2db`, Release `one_combat` sha256 `5cd43eca…`. Teacher: `make_teacher.py c67ba2db… BINARY . teacher.json
--deployed-ooc`. Four units of 10 seeds (LO = 78009004, 78009014, 78009024, 78009034) with the command above and
`combattransitiongen 10 10000 20`.

Flag-off check: the same binary with the plain teacher (no `--deployed-ooc`), `combattransitiongen 3 10000 20` from
78100000. All 31 rows equal the Stage 0 rows for seeds 78100000–78100002 except `teacherId` (which names the commit).

## Results
See ledger §443.
