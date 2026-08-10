# Issue 71: Searcher3 PUCT gate missing `!g_pvnetValueOnly`

- **Status:** closed (2026-08-10)
- **Tier:** Low
- **Date:** 2026-08-10
- **Source:** Investigator audit 2026-08-10, `src/sim/search/BattleScumSearcher3.cpp:2125-2126, 2162-2163`

## Symptom

S3 `selectBestEdgePUCT`/`selectBestValidEdgePUCT`: `usePuct` checks
`g_usePVNet && g_combatPVNet.loaded()` but omits `&& !g_pvnetValueOnly`.
S2 has it; S3's own `computeEdgePriors` has it.

With `STS_PVNET_VALUE_ONLY=1` and no GBM: priors stay 0 → explore term ≡ 0
→ all edges tie → always picks edge 0 → degenerate search.

## Evidence

- `BattleScumSearcher3.cpp:2125-2126`: missing `!g_pvnetValueOnly`.
- `BattleScumSearcher3.cpp:2162-2163`: same.
- `BattleScumSearcher2.cpp:550-551, 589-591`: correct in S2.
- `BattleScumSearcher3.cpp:2788-2790`: correct in S3's own prior code.

## Candidate fix directions

Add `&& !g_pvnetValueOnly` to both `usePuct` assignments.

## Relevant code

- `src/sim/search/BattleScumSearcher3.cpp:2125-2126, 2162-2163`
