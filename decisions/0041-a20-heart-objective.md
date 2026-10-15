# ADR-0041: Default whole runs target A20 Ironclad Heart kills

Date: 2026-10-16
Status: accepted

## Context

The user requested that future research target A20 Ironclad Heart kills and
that key collection be enabled in a separate PR before rollout distillation.
Previously `one_combat` defaulted to A0 with key collection disabled. The
simulator intentionally calls an Act-3 clear without keys a victory, so merely
turning on collection would still allow missing-key runs to count as wins.

## Decision

- `one_combat` defaults to key collection, with `STS_COLLECT_KEYS=0` retained
  for historical experiments. Whole-run `run`, `bestbench`, `reprobench` and
  `runtrace` default to ascension 20; explicit positional ascensions override it.
- Required key choices precede learned policies. Sapphire precedes its paired
  relic; Ruby is collected at a legal Act-3+ campfire. On the last act's map,
  while Emerald is missing, take the first legal edge that still reaches the
  visible burning elite. Earlier acts retain ordinary pathing.
- The run driver and OOC MCTS terminal values require Act 4 for a full Heart
  victory when collection is enabled. An explicit `STS_STOP_AFTER_ACT` keeps
  its separate benchmark objective; the real A20 Act-3 stop waits for both bosses.
- Simulator victory semantics remain unchanged. Historical keys-off Act-3
  comparisons must explicitly freeze their keys, horizon and ascension.

## Consequences

This is an objective change authorized by the user, not a measured playing
strength improvement. Existing policy, CTM and leaf artifacts are not thereby
qualified for Heart decisions. Their recorded training/support domains still
apply, and historical Act-3 win rates must not be presented as Heart win rates.
The final-act route rule is a deterministic feasibility rule, not an optimized
choice among eligible routes.

## Evidence

`apps/one_combat.cpp`, `apps/one_combat/run_driver.cpp`,
`apps/one_combat/ooc_mcts_adapter.cpp`, `sim/search/RunGoal.{h,cpp}` and
`tests/run_goal_test.cpp`; maintained settings and historical-result boundaries
are in `evaluation/current-baselines.md` and `architecture/out-of-combat.md`.
