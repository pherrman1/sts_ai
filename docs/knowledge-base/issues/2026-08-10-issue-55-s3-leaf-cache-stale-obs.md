# Issue 55: Searcher3 depth-cap leaf cache serves wrong-world values

- **Status:** closed (2026-08-10)
- **Tier:** High
- **Date:** 2026-08-10
- **Source:** Investigator audit 2026-08-10, `src/sim/search/BattleScumSearcher3.cpp:2081-2083, 2634-2650`

## Symptom

At the depth-cap direct-eval site, `ensureObservation` sets `node.obsHash` on
first visit and never refreshes it. When the same node is re-visited under a
different determinization world at the depth cap, the cached `obsHash` is the
first world's hash, but `state` is the current world. The leaf cache hits and
returns the first world's value for the current world's state.

## Evidence

- `BattleScumSearcher3.cpp:268-282`: `ensureObservation` sets `obsHash` once.
- `BattleScumSearcher3.cpp:2081-2083`: depth-cap uses `cur->obsHash`.
- `BattleScumSearcher3.cpp:2634-2650`: `evaluateLeaf` → `leafCache.find(obsHash)`.
- Other direct-eval sites (no-legal-action, invalid-edge) pass freshly-visited
  node → correct. Only the depth-cap site is wrong.
- PVNet configs only (`g_usePVNet=true`).

## Why it matters

Wrong values pollute search in PVNet-loaded Searcher3 configs, skewing action
selection at depth-cap nodes.

## Candidate fix directions

Recompute `obsHash` at the depth-cap site before calling `evaluateLeaf`, or
invalidate the cache key when the node is re-visited under a different world.

## Relevant code

- `src/sim/search/BattleScumSearcher3.cpp:268-282`, `2081-2083`, `2634-2650`
