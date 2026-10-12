# Pre-registration: deep OOC MCTS with uniform prior and uniform leaf policy (ledger §441)

Written and committed before any cohort seed ran. Philipp's request, 2026-10-12 08:51Z in the project thread
"CTM profiling/speedup": "can you open on thread which does uniform prior and uniform leaf policy on 128 seeds with
4096 ooc simulations on 8 workers". He named the arm, the seed count, the simulations and the worker count.

## Question

§422/§433 rollout3 uses the V4 network twice: as the tree prior (`STS_OOC_MCTS_PRIOR=policy`) and as the policy that
plays the OOC decisions between the three combats of each leaf rollout (`STS_OOC_MCTS_LEAF_POLICY=v4`). With both
replaced by uniform choices, how does the §433 `combo` search play? Descriptive question; no hypothesis about the sign.

## Arm ([arm_env.sh](arm_env.sh))

| arm | setting |
|---|---|
| `uniform` | §433 `combo` environment (4096 simulations, `WIDEN_K=4`, `WIDEN_ALPHA=0.75`, `LEAF_COMBATS=3`, native leaf, production pathb-r2 CTM, flat exact-10k Silver) with `STS_OOC_MCTS_PRIOR=uniform` and `STS_OOC_MCTS_LEAF_POLICY=uniform` |

`arm_env.sh` sources §433's `arm_env.sh`; it refuses to run unless each replaced line occurs exactly once. It pins
`STS_OOC_PUBLIC_FUTURES=0` (the value §433 ran with, unset = 0), so a later default change of that flag does not reach
this run.

What `uniform` changes in code (`apps/one_combat/ooc_mcts_adapter.cpp`): the tree's root and child priors are flat;
inside a leaf rollout every OOC decision that V4 would take (`v4DecisionSupported`: card rewards, rest, shop, treasure,
boss relic, events except Match and Keep, upgrade select, map) is one uniform draw from `v4CandidateActions`, so the
native shop planner and the V4 gates do not run there. Decisions the V4 policy cannot take still use the native
continuation step. The live V4 fallback for searches the CTM cannot support (mostly active Lizard Tail) is unchanged.

## Controls (paired, not rerun)

The §433 `combo`, `rollout3` and `off` units on seeds 76000000–76000127 (raw `/mnt/project-files/ooc-rollout3-confirm/w01..w04.tar`).
They ran on binary `bab14cd5…` (code `f82eeadd`); this run uses current main `b039e846`, which adds the byte-identical
§436/§437 speedups. **Pairing gate** ([SMOKE.md](SMOKE.md)): the §433 `combo` unit of seed 76000000 rerun with this binary
and this `arm_env.sh` (so with the `PUBLIC_FUTURES=0` pin) must give an identical result row (apart from `sec`) and
byte-identical OOC decision and MCTS action traces. If it does not, the comparison is labelled approximate.

## Provenance

- Code commit `b039e846` ([CODE_COMMIT](CODE_COMMIT), main after #494). Each worker builds `one_combat` and refuses to run
  unless its sha256 equals [binary.sha256](binary.sha256). The run commit may differ from it only in docs and tools.
- **Seeds 76000000–76000127** (128; the §433 cohort's first half, reused on purpose for pairing). Worker W = 1..8 runs
  seeds 76000000+16(W−1) .. +15 as 16 one-seed units, 4 at a time. Smoke seeds 77009000–77009002 (planning container).
- Expected cost (smoke): about 420 s per run, about 15 CPU-hours in all, 30–60 min per 4-CPU worker.
- Per-unit timeout 8 h. Silver stalls are caught per seed by `bestbench` (`[bestbench-seed-failure]`); such seeds drop out
  of the pairs. No seed is rerun or replaced.
- Units write to the worker's local disk (`$HOME/u441-wNN/out/`). When all 16 are done the worker uploads
  `/mnt/project-files/ooc-uniform-441/wNN.tar` and then `wNN.DONE.txt` (with the tar's sha256).

## Analysis ([tools/analyze_ooc_uniform_441.py](../../../../tools/analyze_ooc_uniform_441.py))

Pairs: cohort seeds with a result row in `uniform` and in all three §433 arms. **Primary:** Δwin = win(uniform) −
win(combo), the comparison that differs only in the two flags; paired seed bootstrap 95% CI (10,000 resamples, seed 441).

- **BETTER** if the CI lower bound > 0;
- **WORSE** if the CI upper bound < 0;
- otherwise **NOT_SHOWN**.

**Secondary (descriptive):** uniform − off and uniform − rollout3 with CIs; exact McNemar p, Δfloor (CI), Δ end HP; boss
deaths, mean floor, seconds per run, MCTS CPU, owned and fallback share, support aborts and simulations per run.

**Reading.** 128 pairs resolve about ±7–8 pp. §433's combo won 87.5% over 256 seeds, so only a large loss or gain
from dropping V4 will be shown; a small difference will read NOT_SHOWN.

## Validity

- All 128 units rc=0 apart from listed stall failures; any other nonzero rc, crash or missing seed makes the result
  INVALID until explained.
- Every `uniform` log prints `[ooc-mcts-config]` with `"prior":"uniform"`, `"leafPolicy":"uniform"`,
  `"leafValue":"native"`, `"leafCombats":3`, `"simulations":4096`, `"wideningK":4`, `"wideningAlpha":0.75` and the
  production `combat_model=selfplay/models/combat_transition_deepsets_pathb_r2.native`.

## Decision

No default change from this run. Philipp decides what comes next.
