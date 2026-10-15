# Deviations from PREREG.md

**D1 (2026-10-09, before any cohort seed ran):** the smoke on seed 65009000 failed only its integrity step, because
`analyze.py` globbed `*.csv` and read each unit's `ARM-LO.mcts.csv` trace as a second result file ("duplicate row").
All 8 smoke runs had rc 0, one CSV row and the right cpuct, root-selection and candidate banners. Fix: `load()` reads
only files named exactly `ARM-LO.csv`, and the selftest now includes a decoy `.mcts.csv`. No other change. analyze.py
sha256 5a9498a9… -> a3f6ccd5fd9f6d31767df6b1863979ac7e2d7730f2e31db377f83b8485c46240. The re-run check on the same smoke outputs passed; the original failure note is kept as
`smoke/SMOKE_FAIL.analyzer-glob-bug`, and worker 1's first FROZEN.txt (recorded the old analyze.py hash) as
`smoke/w01-FROZEN.setup-by-new-ctm-thread.txt`.

**D2 (2026-10-09 ~18:07Z, before any result was read):** worker 02 accidentally started a second foreground `run 2`
beside its detached one and killed both at ~18:06:50Z, leaving four rc=143 `.done` files. The operator renamed them
`*.done.killed-by-operator` and explained this in `w02/OPERATOR-NOTE.txt`. The four units reran whole from one clean
launch at 18:08:10Z with the same seeds, arm and binary, outcome-blind. `analyze.py` reads only `*.done`, so the renamed
files are not counted.
