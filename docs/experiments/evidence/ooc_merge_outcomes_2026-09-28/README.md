# OOC MCTS equivalent-outcome merging: paired gameplay comparison (#384)

Status: the sequential plan below was **stopped by the user after look 1**
(time became available for a fixed cohort). The **current plan is the fixed
128-seed cohort**, frozen before any of its seeds ran (2026-09-28).

## Question and arms

Does pooling equivalent sampled chance outcomes (`STS_OOC_MCTS_MERGE_OUTCOMES=1`)
change whole-run play strength of opt-in OOC MCTS? Only that variable differs.

| Arm | `STS_OOC_MCTS_MERGE_OUTCOMES` |
|---|---|
| control | `0` (current behavior) |
| treatment | `1` |

## Frozen provenance

- Source commit: `6ed6c943397c058610855f3d29d513bdf9f37a97` (clean tree; pinned
  submodules json `2222d386`, pybind11 `63d627c5`).
- Build: `linux-gcc-release` preset, GCC 13.3.0, Linux, 4 cores.
- Frozen executable copy SHA-256:
  `a7450100fee8b937ed9efb4f39824e11c92f9a975f48393af4015ad9a957380a`.
- Models (SHA-256):
  - `models/v_win_trees.txt` `fc52c14cb7239a33b3c1f9d0477ccb6c895fd51a07240fe804744e605067ad70`
  - `models/v_rich_trees.txt` `3a3420469b1d648e0e306d6cb6a7e85f3d3499105e3ff3a56eee6c579194ffe3`
  - `models/policy_trees_c.txt` `24793bd39dd1a35c8865035e458c3aa40616ef021cb26b05f914f72fb5e5a321`
  - `selfplay/models/ooc_strategic_tok_final.native` `e62abd833fc8cb9081a1cec4a1a012832ac3b0e3166da3892841911664f1184c`
  - `selfplay/models/combat_transition_deepsets_lizard_t2.native` (automatic CTM stack) `abb2a9ead6efd6b97ee64192e0459eb08ceff7fd93f2b5f4b87a0bf379e571ab`
  - `selfplay/models/combat_transition_near_full_except_smoke_v2.native` (Brew fallback) `e9a18951710fdfe9e1a81a2703090a41f039067c670a1d8a0393b5e7e8e0ddfd`
- Command and full environment: [`run_arm.sh`](run_arm.sh) (`env -i`, seed guard,
  `bestbench 10000 <n> 0 <lo>`). Ironclad A0, project-fair, keys off, stop after
  Act 3, exact-10k native Silver (adaptive off), OOC MCTS 2,048 simulations,
  default PUCT/widening/early stop, automatic CTM stack with active-Lizard
  correction, `OMP_NUM_THREADS=2` per arm, both arms concurrently.

## Current plan: fixed 128-seed cohort

- Cohort: seeds `38410000..38410127` (fresh; disjoint from the stopped
  sequential cohort and the canary). Each arm is one `run_arm.sh` invocation of
  128 seeds; both arms run concurrently.
- One analysis after all 128 pairs complete: two-sided 95% Student-t interval
  on the paired treatment-minus-control difference of `score = floor + 10*won`
  (`analyze.py <runs> --seed-lo 38410000 --looks 128`).
- Verdict: interval above 0 = treatment better; below 0 = treatment worse;
  otherwise inconclusive. Secondary (not decision-bearing): wins with exact
  McNemar, mean floor, end HP, seconds per run.
- No default change follows from this cohort alone.
- The canary (below) is reused; it ran on the same frozen binary and runner.

## Stopped sequential plan (historical)

- Cohort: seeds `38400000..38400255` (fresh block), used strictly in order.
- Looks at cumulative paired N = 8, 16, 32, 64, 128, 256. Each look adds the
  next block (`+8, +8, +16, +32, +64, +128`) to both arms. Cap: 256 pairs.
- Primary metric per seed: `score = floor + 10*won`; paired difference
  treatment minus control.
- Interval at each look: two-sided Student-t interval at level
  `1 - 0.05/6` (Bonferroni over the six planned looks) — plain 95% intervals
  at repeated looks would inflate false positives.
- Stop at the first look whose interval excludes 0 (better or worse), else
  continue; at N = 256 an interval containing 0 is **inconclusive**.
- Secondary (reported, not decision-bearing): win counts with exact McNemar,
  mean floor, end HP, seconds per run.
- No default change follows from this cohort alone; a positive result would
  need a separate confirmation plan.
- Canary: one fresh seed per arm (`38401000`) before the cohort, validated with
  `tools/agent/check_benchmark_canary.py`; canary rows are not cohort data.

Analysis: [`analyze.py`](analyze.py) (pure Python; enforces seed membership).

## Results

### Canary (seed 38401000, not cohort data)

Both arms passed `tools/agent/check_benchmark_canary.py` (native Silver, 1 seed,
10,000 sims, 2 threads, fair, executable SHA and binary hash as frozen); logs
show `"mergeOutcomes":false` / `true`. Control lost on floor 50; treatment won.

### Stopped sequential cohort, look 1 (N = 8, seeds 38400000..38400007)

Treatment minus control `floor + 10*won`: mean -7.0, sd 10.7, 99.17%
t-interval [-20.8, +6.8] (continue). Wins 6/8 control vs 4/8 treatment
(discordant 0 treatment-only, 2 control-only, McNemar p = 0.50). The run was
stopped during look 2 (control had completed 3 seeds, treatment 2); those
partial rows are preserved but not analyzed.

### Fixed 128-seed cohort (seeds 38410000..38410127) — inconclusive

Both arms completed all 128 seeds (exit 0; no `bestbench-seed-failure`); logs
show `"mergeOutcomes":false` (control) and `true` (treatment). Started
2026-09-28 21:11 UTC; control finished 00:19, treatment 00:41 UTC.

| Metric | Control (off) | Treatment (on) | Treatment - control |
|---|---|---|---|
| **`floor + 10*won`** (primary) | | | mean **-0.25**, sd 12.65, 95% t-interval **[-2.46, +1.96]** |
| Wins | 86/128 (67.2%) | 83/128 (64.8%) | -2.3 pp; discordant 16 treatment-only / 19 control-only, exact McNemar p = 0.74 |
| Mean floor | 47.47 | 47.45 | -0.02 |
| Mean end HP | 24.7 | 24.2 | -0.5 |
| Mean seconds per run | 174.9 | 197.2 | +12.7% |

Verdict under the frozen rule: **inconclusive** (the interval contains 0).

MCTS trace totals (`*.mcts.csv`, descriptive):

| | Control | Treatment |
|---|---|---|
| Nonbattle decisions / MCTS-owned / fallback | 15,042 / 14,655 / 387 | 15,086 / 14,709 / 377 |
| Simulations | 14,761,785 | 14,778,954 |
| Transition samples / distinct particles | 14,246,809 / 14,246,809 | 20,882,469 / 13,332,063 (36.2% pooled) |
| Max searched depth | 4 | 15 |
| Support aborts | 34 | 26 |
| MCTS CPU per simulation | 0.99 ms | 1.18 ms (+19%) |

Interpretation: pooling works mechanically (deeper trees, same simulation
budget, the same fallback rate) but produced no detectable change in play
strength at this sample size. Descriptive paired 95% t-intervals (not
decision-bearing): win rate -2.3 pp [-11.5, +6.8] pp, final floor -0.02
[-1.58, +1.54]. A win-rate effect of a few points in either direction is not
ruled out.
**Inference:** with priors, `v_win` leaves and the playout continuation
unchanged, the extra depth mostly re-orders shop/reward sequences that the
leaf evaluator already scores similarly. **Open question:** whether pooling
matters more once #379 replaces the playout with a screen-aware leaf.

Raw evidence: `cohort128/`, `sequential_stopped/`, `canary/` (logs and action
traces gzipped), checksums in `manifest.sha256`. Reproduce the verdict with
`python3 analyze.py cohort128 --seed-lo 38410000 --looks 128`.
