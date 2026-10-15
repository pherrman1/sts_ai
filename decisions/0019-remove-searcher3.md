# ADR-0019: Remove Searcher3

Date: 2026-09-24
Status: accepted

Supersedes: the Searcher3 opt-in path of
[ADR-0003](0003-searcher2-default-searcher3-opt-in.md) and the
`STS_SEARCHER3=1` exception in
[ADR-0018](0018-silver-default-combat-backend.md).

## Context

ADR-0018 made Silver the default combat backend for whole-run play. The live
advisor uses only Silver, and current research producers require
`STS_SEARCHER3=0`. `BattleScumSearcher3` (particle ISMCTS) was still reachable
only through `STS_SEARCHER3=1` and several Searcher3-only modes. It accounted
for about 12,000 lines across the searcher, its particle belief, rejuvenation
probes, diagnostics, tests, run scripts and analyzers. The project decided to
consolidate on Silver.

## Decision

Delete `BattleScumSearcher3` and everything that exists only to run or measure
it:

- the particle belief (`HiddenBattleState`, `Belief`) and S3 rejuvenation
  probes;
- the `STS_S3_*` and `STS_REUSE_*` controls and the fair-Searcher3 automatic
  defaults (`STS_LIVE_VALID`, `STS_VNET`);
- the `fairgen`, `speedtest`, `particle_leaf_probe`,
  `particle_posterior_probe`, `fightrep`, `oocv4h1rollout` and
  `oocv4h1rolloutall` modes;
- Searcher3-only unit tests, run scripts and analyzers.

A non-zero `STS_SEARCHER3` makes `one_combat` exit with an error instead of
silently running another searcher. `STS_SEARCHER3=0` stays accepted, so
existing frozen environment contracts remain valid. Benchmark metadata keeps
its `searcher3` and `s3*` keys with fixed false/zero values for schema
compatibility.

`BattleScumSearcher2` stays because self-play (`selfplay/loop.sh`) still uses
it.

## Rationale

Nothing on the default, live or current research paths used Searcher3.
Keeping it meant maintaining a second native searcher with its own
hidden-state model, flags and tests while the project moves combat search to
Silver.

## Alternatives considered

- Keep Searcher3 as an unmaintained opt-in. Rejected: it would keep the flag
  surface and test burden and would silently rot.
- Remove Searcher2 at the same time. Rejected for now: self-play still uses
  it.

## Consequences

- Searcher3 results in the ledger and baselines are historical. Reproducing
  them requires a binary built before this ADR.
- `STS_DIST_VNET` still loads, but no searcher consumes it.
- Existing `fairgen` CSVs remain usable by the offline PVNet training and
  evaluation scripts, but new ones cannot be generated.

## Affected files

- `src/sim/search/BattleScumSearcher3.cpp`, `include/sim/search/BattleScumSearcher3.h` (deleted)
- `src/sim/search/S3RejuvenationProbe.cpp`, `include/sim/search/S3RejuvenationProbe.h` (deleted)
- `apps/one_combat/particle_diagnostics.{h,cpp}`, `apps/one_combat/fight_replay.{h,cpp}`, `apps/test_belief.{h,cpp}` (deleted)
- `src/sim/search/ScumSearchAgent2.cpp`, `src/sim/search/CombatObservation.cpp`, `apps/one_combat.cpp`, `apps/test.cpp`, `CMakeLists.txt`, `tools/seed_guard.sh`

## Evidence

- Local parity check. The pre-change and post-change release binaries produced
  identical `bestbench` rows (4 seeds, 200 sims) for fair Searcher2,
  known-RNG Searcher2 and Silver. They also produced byte-identical `fightgen`
  value and policy CSVs (2 seeds), which is the mode self-play uses.
