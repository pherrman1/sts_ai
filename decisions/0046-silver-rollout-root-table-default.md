# ADR-0046: Silver's greedy rollouts use a per-root card table from the gen-6 E prior by default

Date: 2026-10-17
Status: accepted

## Context

ADR-0040 made Silver's greedy leaf rollout play cards by one fixed table fitted to gen-6 choices. PR #612 added
`STS_SILVER_ROLLOUT_ROOT_TABLE`. With it, at every searched root, a `combat_policy_mlp` model scores each distinct
card in hand, draw and discard pile as a play at the root state, and that search's playouts use those scores as
their card table.

Results with gen-6 E (`ca9bd7f2…`) at A20, fight level:
- §519 (2,500 simulations, 1,426 fights): +2.69 [+0.61, +4.80] fight score at equal simulations (descriptive). The
  pre-registered contrast against greedy at 2,650 simulations was +1.87 [−0.15, +3.94] at 1.007x CPU per fight:
  `NOT_CPU_MATCHED`, `NOT_SHOWN`.
- §521 (10,000 simulations, 1,403 fights): +1.77 [−0.24, +3.87] at equal simulations. Against greedy at 10,700 it
  was +1.79 [−0.40, +3.99] at 1.008x CPU per fight: `NOT_CPU_MATCHED`, `NOT_SHOWN`. Greedy at 10,700 vs 10,000:
  −0.02 [−1.69, +1.73].
- Cost: 5–6% more CPU per simulation, mostly from longer playouts, plus 1–2% more search decisions per fight.

On 2026-10-17 at 22:10Z, Philipp wrote in thread "Distilled Silver playout picker": "i actually want it on, i think
the direction is definitely goo denough even though its technically not proven".

## Decision

- With `STS_SILVER_ROLLOUT_ROOT_TABLE` unset, Silver builds the per-root rollout card table with the bundled
  `models/combat_policy_mlp_g6_E.txt` (sha256 `ca9bd7f2…`, the same file as
  `docs/experiments/evidence/silver_prior_arch_20261014/models/gen6/`). The path is relative to the working
  directory, like the other bundled models. The model loads at the first Silver search, which prints
  `[silver] rollout root table model loaded: <path>`; a model that does not load is fatal there.
- `STS_SILVER_ROLLOUT_ROOT_TABLE=0` restores the fixed ADR-0040 table exactly. A path selects another
  `combat_policy_mlp` model.
- The `ctmsilvergen` armset `roottable` now requires `STS_SILVER_ROLLOUT_ROOT_TABLE=0`, so its `greedy` arms, source
  run and control keep the ADR-0040 table as in §519 and §521.
- Effective Silver leaf specifications record `rollout_root_table` (path and sha256) whenever it is on, so teacher
  files written with `=0` match earlier ones.

## Consequences

- Every Silver search run through the native Silver backend (`runNativeSilverCombat`: benchmarks, whole runs,
  data generation) plays differently and costs about 5–6% more CPU per simulation. The live advisor's
  `NativeSilverAdvisorSession` builds its own `SilverSearcher` and keeps the ADR-0040 table.
- The playing-strength effect is not established. Both pre-registered tests were `NOT_CPU_MATCHED` and `NOT_SHOWN`;
  the equal-simulation contrast was positive in all four budget pairs.
- Comparisons with runs from before this ADR need `STS_SILVER_ROLLOUT_ROOT_TABLE=0`.
- Silver must run from a directory containing `models/combat_policy_mlp_g6_E.txt`, or with
  `STS_SILVER_ROLLOUT_ROOT_TABLE` set.
