# OOC MCTS equivalent-outcome merging: paired gameplay comparison (#384)

Status: **plan frozen before any cohort seed ran** (2026-09-28). Results are
appended below as looks complete.

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

## Seeds, looks and decision rule

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

(pending)
