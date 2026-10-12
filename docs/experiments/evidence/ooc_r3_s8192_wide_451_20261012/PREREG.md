# Pre-registration: rollout3 combo at 8192 simulations and with broader chance widening (ledger §451)

Written and committed before any cohort seed ran. Philipp's request, 2026-10-12 19:58Z in the project thread for this
run: "Can we do rollout3 with the parameters that won 224/256 games but with 8192 sims? And another one which has even
more chance nodes but with 4096 nodes? Do 128 seeds. On 8 workers." The coordinator added a same-commit control arm
(below) because §433-era runs do not reproduce byte-for-byte after #480 (§446).

## Question

§433 `combo` (rollout3 at 4096 simulations with broad chance widening, `WIDEN_K=4`, `WIDEN_ALPHA=0.75`) won 224/256
vs MCTS off 199/256. On fresh seeds and the same binary, does (a) doubling the simulation budget to 8192, or (b)
widening chance nodes further at 4096 simulations, win more runs than `combo`? No hypothesis about the sign; §427
(2048 → 4096, +3.1 pp) and §429 (wbroad, +1.6 pp) were both NOT_SHOWN.

## Arms ([arm_env.sh](arm_env.sh))

| arm | setting |
|---|---|
| `combo` | §433 `combo` unchanged (4096 simulations, `WIDEN_K=4`, `WIDEN_ALPHA=0.75`, `LEAF_COMBATS=3`, native leaf, V4 prior and leaf policy, flat exact-10k Silver, current production CTM `pathb_r2_lizard` with the near-full brew fallback per §435): the control |
| `s8192` | `combo` with `STS_OOC_MCTS_SIMS=8192` |
| `wide` | `combo` with `STS_OOC_MCTS_WIDEN_K=8` (`WIDEN_ALPHA` stays 0.75) |

All arms pin `STS_OOC_PUBLIC_FUTURES=8` (the default since #496/ADR-0028). `arm_env.sh` sources §433's `arm_env.sh`,
checks the combo lines exist exactly once and that §433 sets neither `STS_OOC_PUBLIC_FUTURES`, `STS_WIN_NET`,
`STS_OOC_MCTS_LEAF_WIN_MODEL` nor `STS_OOC_MCTS_MERGE_OUTCOMES`. Each variant differs from `combo` in exactly one
line. Each unit writes its `STS_*` environment to `ARM-SEED.env`.

**What `wide` changes** (`src/sim/search/OocMctsPlanner.cpp`, `chanceWideningLimit` and the chance branch of
`evaluate`): a chance node visited n times may hold up to ceil(K·n^α) sampled outcomes; below the cap a visit samples
a new successor, at the cap it revisits a uniformly chosen existing one. `wbroad` (K=4, α=0.75) stops adding outcomes
once n > 256. `wide` doubles the cap at every n; since 8·n^0.75 ≥ n for all n ≤ 4096, every visit to a chance node in
a 4096-simulation search samples a fresh outcome, so no outcome is revisited: the most chance branching this knob
can give at this budget. Deterministic transitions are unaffected (they always reuse their single successor).
**Inference:** below chance nodes the tree then gets one visit per sampled outcome, so `wide` trades depth of the
tree after chance for breadth of outcome sampling.

## Provenance

- Code commit `19cfc1ae` ([CODE_COMMIT](CODE_COMMIT), main after #505). Each worker builds `one_combat` and refuses to
  run unless its sha256 equals [binary.sha256](binary.sha256). The run commit may differ from it only in docs and tools.
- **Seeds 83000000 .. 83000000+NPAIRS−1** (NPAIRS = 128, [NPAIRS](NPAIRS)), fresh, all three arms on every seed.
  Worker W (1..8) runs seeds 83000000+16(W−1) .. +15 in all arms (48 one-seed units, 4 at a time). Smoke seeds
  83009000–83009009 (planning container, [SMOKE.md](SMOKE.md)).
- Per-unit timeout 12 h. Silver stalls are caught per seed by `bestbench` (`[bestbench-seed-failure]`); such seeds
  drop out of the pairs. No seed is rerun or replaced.
- Units write to the worker's local disk (`$HOME/x451-wNN/out/`). When all 48 are done the worker uploads
  `/mnt/project-files/rollout3-8192-wide-451/wNN.tar` and then `wNN.DONE.txt` (with the tar's sha256).

## Analysis ([tools/analyze_ooc_451.py](../../../../tools/analyze_ooc_451.py))

Pairs: cohort seeds with a result row in all three arms. **Two primary comparisons**, each paired by seed against
`combo`: Δwin = win(variant) − win(combo), paired seed bootstrap 95% CI (10,000 resamples, seed 451, the same
resample indices for both comparisons). Per comparison:

- **BETTER** if the CI lower bound > 0;
- **WORSE** if the CI upper bound < 0;
- otherwise **NOT_SHOWN**.

No multiplicity correction; the two comparisons are read separately. `s8192` vs `wide` is not tested.

**Secondary (descriptive):** exact McNemar p, Δfloor (CI), Δ end HP, boss deaths, mean floor, seconds per run, MCTS
CPU, owned and fallback share, support aborts and simulations per run.

**Reading.** `combo` won 87.5% in §433. 128 pairs resolve about ±7 pp, so only a large difference will be shown.
NOT_SHOWN does not mean equal.

## Validity

- All units rc=0 apart from listed stall failures; any other nonzero rc, crash or missing seed makes the result
  INVALID until explained.
- Every unit's `.env` holds `STS_OOC_PUBLIC_FUTURES=8` and its arm's `STS_OOC_MCTS_SIMS` / `STS_OOC_MCTS_WIDEN_K`;
  every log prints `[ooc-mcts-config]` with `"leafValue":"native"`, `"leafCombats":3`, `"prior":"policy"`,
  `"leafPolicy":"v4"`, `"wideningAlpha":0.75` and the arm's `"simulations"` (4096 / 8192 / 4096) and `"wideningK"`
  (4 / 4 / 8).

## Decision

No default change from this run (OOC MCTS stays off by default, ADR-0027). A result feeds the choice of the rollout3
configuration for later runs; that choice is Philipp's.
