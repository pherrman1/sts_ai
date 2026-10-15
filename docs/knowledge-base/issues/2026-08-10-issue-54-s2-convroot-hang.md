# Issue 54: Searcher2 `searchToTotalRootStable` infinite loop on zero-growth config

- **Status:** closed (2026-08-10: zero-growth guard in `searchToTotalRootStable` forces the full budget; parse-time warning in `apps/one_combat.cpp`; regression `scum_convroot_stale_outcome`)
- **Tier:** High
- **Date:** 2026-08-10
- **Source:** Investigator audit 2026-08-10, `src/sim/search/BattleScumSearcher2.cpp:245-291`

## Symptom

When `STS_CONV_ROOT_START=0` or `STS_CONV_ROOT_GROW <= 1.0`,
`searchToTotalRootStable` computes `budget` that never grows, the inner loop
runs 0 steps, and the outer `while (root.simulationCount < targetSimulations)`
spins forever.

## Evidence

- `BattleScumSearcher2.cpp:245-291`: `chunkEnd == budget` when grow ≤ 1 or
  start == 0 → inner loop runs 0 steps → outer loop never exits.
- `one_combat.cpp:10106-10107`: both env vars parsed with no validation.
- Defaults (start=250, grow=2.0) are safe.

## Why it matters

A misconfiguration hangs the process rather than failing with an error.

## Candidate fix directions

Add a guard: `if (budget >= targetSimulations) budget = targetSimulations;` or
validate `g_convRootGrow > 1.0 && g_convRootStart > 0` at parse time.

## Relevant code

- `src/sim/search/BattleScumSearcher2.cpp:245-291`
- `apps/one_combat.cpp:10106-10107`
