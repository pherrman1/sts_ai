# Smoke (2026-11-12, cloud, 4 lanes on 4 cores; committed with the result per review K, R1)

Units `111970000 1`, `111970000 2`, `111970000 3` and `111970001 1` ran in parallel. They used binary ca8d9d0b from
the bin cache, net-0420 8c0bd16c and repo main 6b5102f (same build inputs as code 3c85fb26).

| unit | wall s | end floor | arm fights | arm CPU s | rc |
|---|---|---|---|---|---|
| 111970000 a1 | 277 | 17 | 11 | 243 | 0* |
| 111970000 a2 | 564 | 34 | 9 | 485 | 0* |
| 111970000 a3 | 958 | 52 | 11 | 802 | 0* |
| 111970001 a1 | 150 | 17 | 9 | 132 | 0* |

\* The smoke ran an earlier `run_unit.sh` whose banner check expected `(all acts, hallway sims 4000)`. The binary
prints `(all acts, sims 16000, hallway sims 4000)`, so these units ended with rc 87. Every other check passed. The run
commit 72e997a4 checks the printed banner, and nothing else in the script changed.

- **Main line.** Every unit printed the H4 banner, `whole-run Gumbel roots=151-844`, the net-0420 load line and the
  learned-stop line.
- **Determinism.** The main lines of seed 111970000's three units are identical on the shared floors (floor,
  encounter, HP, max HP and deck of every fight): a1 is a prefix of a2, and a2 is a prefix of a3.
- **Analysis.** `analyze.py` ran on the 4 smoke units with rc set to 0: 40 fights, 0 dropped. `--selftest` passes.
- **Cost.** About 1,800 lane-s per seed, so about 128 lane-hours (100-160) for 256 seeds. The run took 88.6.
- **Share.** 41,833 of 50,000 files before the run; this campaign adds about 3,000.
