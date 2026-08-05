# Issue 34: Searcher3 computeEdgePriors heap overflow for entityDim != 128

- **Status:** closed
- **Tier:** Critical
- **Last verified:** 2026-08-05
- **Source:** code review 2026-08-05; `BattleScumSearcher3.cpp`

## Symptom

`BattleScumSearcher3.cpp::computeEdgePriors` resized its `thread_local`
`global` buffer to a hard-coded 128 floats before `g_combatPVNet.encode(...)`,
which writes `entityDim` floats. The loader accepts `entityDim` up to 256
(`CombatPVNet.cpp:102`), so any d256 artifact silently heap-overflows the
buffer (corruption or ASAN abort). The Searcher2 block written later does it
correctly (`BattleScumSearcher2.cpp:436,439` resize to `entityDim`).

## Evidence

- `BattleScumSearcher3.cpp:579-580` (`global.resize(128)`).
- `CombatPVNet.cpp:101-108` (`entityDim` up to 256).

## Why it matters

Memory-unsafe on any future non-128 PVNet artifact (the §100 wave referenced a
d256 model family). Latent: no recorded experiment used a d256 combat artifact
(payoff gate used `v_combat_pvnet.txt`, d128), so no recorded number is
affected.

## Candidate fix direction

Resize to `g_combatPVNet.entityDim` (as Searcher2 does).

## Relevant code

- `src/sim/search/BattleScumSearcher3.cpp::computeEdgePriors`

## Resolution (2026-08-05)

Fixed in the 2026-08-05 code-review working tree; verified with the ASAN build
on the S3+PVNet path. Rerun ledger: verify-only row (no experiment used d256).
