# 2026-08-09 — Key collection gated behind STS_COLLECT_KEYS flag

Date: 2026-08-09
Session/task: Gate Act-4 key collection behind `STS_COLLECT_KEYS=1`, default off.

## Decision

All deliberate Act-4 key collection is gated behind `STS_COLLECT_KEYS=1`
(default `0` = off). Without the flag, no emerald/sapphire keys are taken on
REWARDS screens and no ruby key (RECALL) is taken at rest rooms, so runs end
at the Act 3 boss and `THE_HEART` is unreachable.

The flag is parsed in `apps/one_combat.cpp::main` and sets the global
`g_collectKeys` (defined in `src/sim/search/ScumSearchAgent2.cpp`). All 20
REWARDS chains in `one_combat.cpp`, plus `restWinPolicy`,
`checkpointedActFightUtility`, `ScumSearchAgent2::stepRewardsPolicy` /
`stepOutOfCombatPolicy`, `SimpleAgent::stepRewardsScreen` / `stepRestScreen`,
and the `BEST stack` banner are gated.

## Rationale

Heart kills add variance and a survivability filter past Act 3 that is
undesirable for comparative benchmarking. Default-off makes Act 3 the
terminal condition, keeping paired evaluations cleaner. The flag preserves the
capability for research runs that need Act 4.

The global lives in `ScumSearchAgent2.cpp` (part of `sts_lightspeed_SOURCES`)
so both the `one_combat` and `unit-test` executables link it without extra
CMake wiring.

## Alternatives considered

- Keeping key collection always-on as implemented 2026-08-09 — rejected:
  harms benchmark cleanliness and comparability for Act-3 terminated runs.
- Per-key flags (emerald/sapphire/ruby separately) — rejected: overkill;
  the user's intent is a single toggle for the heart-kill path.
- Gating only sapphire/ruby and leaving emerald always-collected — considered
  but rejected for consistency; the user said emerald from burning elite is
  "accidental" and acceptable, but a single flag is simpler.

## Evidence

- `apps/one_combat.cpp` — 20 REWARDS chains, `restWinPolicy`,
  `checkpointedActFightUtility`, `BEST stack` banner, `STS_COLLECT_KEYS`
  env parse in `main`.
- `src/sim/search/ScumSearchAgent2.cpp` — `g_collectKeys` definition,
  `stepOutOfCombatPolicy` REST_ROOM, `stepRewardsPolicy`.
- `src/sim/search/SimpleAgent.cpp` — `stepRestScreen`, `stepRewardsScreen`.
- `apps/test.cpp` — `testKeyCollection` sets `g_collectKeys = true`.
- `docs/knowledge-base/architecture/out-of-combat.md` — updated data flow
  and verification note.
- `docs/knowledge-base/operations/environment-variables.md` — `STS_COLLECT_KEYS`
  entry added.

## Status and follow-up

- Implemented. All 15 ctest entries pass. Default `bestbench` runs terminate
  at Act 3; `STS_COLLECT_KEYS=1` restores the full key-collection path.
