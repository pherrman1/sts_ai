# Smoke (2026-10-25, Philipp's go 09:49Z covers it)

Binary `e57de384…` (v3 preset, code `eb94f4e`), this container, three lanes at once, `run_unit.sh` as frozen except
`SOURCE_ONLY=1` for the rerun.

| unit | source | act-1 root (offered, production pick) | forks | rc |
|---|---|---|---|---|
| 111379980 | died act 2, floor 22 | Coffee Dripper / Philosopher's Stone / Slaver's Collar, took 0 (`heart1_screen`) | 1:1 floor 33, 1:2 act 3 floor 39, 1:3 (skip) floor 31 | all 0 |
| 111379981 | died act 2, floor 29 | Slaver's Collar / Velvet Choker / Coffee Dripper, took 2 | 1:0 floor 33, 1:1 floor 33, 1:3 floor 31 | all 0 |

- All six forks pass `forks.py check` (traces equal the source's for the 65 / 70 rows before the root; the root row is
  `forced_boss_relic` with the forced choice).
- Rerun determinism: `SOURCE_ONLY=1` replay of 111379980 gives a byte-identical trace and an identical outcome file
  (except `producerSha`, which is the same here too).
- Banner checks (learned stop, CTM, student_sel, `screens_a20_default=map_full_budget`, Act 4 strong, M0 leaf) pass.
- `analyze.py --stage A` reads the smoke units (2 roots, 8 games, no problems).
- Wall 135–400 s per game; both sources died in act 2, so neither an act-2 root nor Act 4 was exercised (the act-2
  path is the same code with ACT=2; Act-4 CPU is unmeasured here, the cost estimate stays an estimate).
- Seeds used: 111379980, 111379981 (111379982–989 free for the review).
