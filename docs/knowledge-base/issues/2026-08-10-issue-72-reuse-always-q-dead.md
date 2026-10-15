# Issue 72: `STS_REUSE_ALWAYS_Q` is dead code

- **Status:** closed (2026-08-10)
- **Fix:** `reuseSearchCount` is now maintained: `advanceRoot` resets it to 0
  when the tree is promoted (reused), and `search()`/`searchToTotal()`
  increment it when `>= 0` (searches executed since the last promotion). The
  STS_REUSE_ALWAYS_Q exploit condition `reuseSearchCount >= 0` is therefore
  true on carried trees and the feature is live (verified with
  `STS_REUSE_DIAG`). `parentChildViolations` remains diagnostic-only (no
  invariant check site exists yet).
  Regression test: `./build/test issue_fixes` (ctest `issue_fixes`).
- **Tier:** Low
- **Date:** 2026-08-10
- **Source:** Investigator audit 2026-08-10, `include/sim/search/BattleScumSearcher3.h:145`

## Symptom

`reuseSearchCount` is never written (header:145). Read at :2131/:2166/:3046
but `reuseSearchCount >= 0` is always false → `STS_REUSE_ALWAYS_Q` is inert.
`parentChildViolations` also never incremented.

## Evidence

- `BattleScumSearcher3.h:145`: `reuseSearchCount` never incremented.
- `BattleScumSearcher3.cpp:1441`: reset only.
- `BattleScumSearcher3.cpp:3038`: print only.

## Candidate fix directions

Implement the counter increment or remove the dead code and env-var parsing.

## Relevant code

- `include/sim/search/BattleScumSearcher3.h:145`
- `src/sim/search/BattleScumSearcher3.cpp:2131, 2166, 3046`
