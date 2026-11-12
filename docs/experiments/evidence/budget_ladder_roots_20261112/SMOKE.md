# Budget ladder per root: smoke (2026-11-12, cloud container, binary 854b4c43 = code a352f45d)

Seeds 111959990 and 111959991 (D2's smoke block; smoke data only, not used in any analysis). Environment
[record_env.sh](record_env.sh) apart from the ladder list where stated.

## Main line bit-identical with the ladder on or off

- Seed 111959990, `STS_AZGEN_BUDGET_LADDER` unset vs `1000,2000,4000,8000,16000` (and, with the first build,
  `1000,2000,4000,8000`): 819 rows each (791 roots, 28 fights). With `ladder`, `mainCpu` and the fight rows'
  `teacherId` (it names the ladder, `-lad5`) removed, all 819 rows are identical: every root's edges, visits, Q,
  max-backed Q, prior, Gumbel pick, chosen action and wire, and every fight's outcome, HP and score.
- The tree-reuse line of the log is identical (reroots 649, inherited 3,951,108, cap resets 38).

## Matching of the ladder picks

- First build: 305 of 2,868 picks (10.6 %) did not match a root edge by action bits, since the played root is a
  rerooted tree whose hand can name an equivalent card copy differently.
- Fixed in a352f45d: both the pick and the played root's edges are translated to the live state
  (`SilverSearcher::translateAction`) before matching. Now 86 of 3,585 picks (2.4 %) stay unmatched; their roots are
  dropped and counted (`ladder_unmatched`, 28 of 717 roots on this seed).

## Cost

| seed | wall s | played search CPU s | ladder CPU s (1k / 2k / 4k / 8k / 16k) |
|---|---|---|---|
| 111959990 (ladder 1k-16k) | 1,456 | 523 | 29 / 59 / 116 / 230 / 465 |
| 111959991 (ladder 1k-8k) | 3,935 | 2,287 | 1,579 for 1k-8k; 16k adds about 1,580 (2 × 8k) |

Without the ladder seed 111959990 took 545 s. The ladder adds about 1.8× the played search's CPU, so a run costs
about 2.5-2.8× a G16 run: about 0.4-1.5 lane-hours per run, about 150-220 lane-hours for 256 runs.

## Pipeline

pack_states.py → tensorize.py (ladder_edge.npy, ladder_cpu.npy, main_cpu.npy, meta `ladderBudgets`) →
budget_ladder.py `--no-net --smoke-folds` (folds by root, smoke only) runs end to end on seed 111959990. Uniform
losses (Q units) 0: 2.87, 1k: 1.21, 2k: 1.01, 4k: 0.84, 8k: 0.86, 16k: 0.74 at 0 / 0.04 / 0.08 / 0.17 / 0.33 / 0.67
CPU s per root. Tensorize output on D2 rows without a ladder is byte-identical to before (all .npy and meta.json).
