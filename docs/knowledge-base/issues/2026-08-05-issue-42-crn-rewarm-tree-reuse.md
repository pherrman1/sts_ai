# Issue 42: CRN warm start destructively re-warms the tree-reuse path

- **Status:** closed
- **Tier:** High
- **Last verified:** 2026-08-05
- **Source:** code review 2026-08-05; `BattleScumSearcher3.cpp`

## Symptom

With `STS_S3_CRN=1`, `warmStartRootCRN` was called at the top of every
`search()`/`searchToTotal()`. In the non-fair tree-reuse path
(`ScumSearchAgent2.cpp:167-177`: `advanceRoot` then `searchToTotal`) the root
carries accumulated backpropagated statistics, and the warm start
**overwrites** `child.evaluationSum` with CRN averages (mixed Q prior),
destroying the carried-over tree every decision. Additionally the `crnParticles`
are prepared from the initial root's draw pile; after `advanceRoot` the pile
changed, so `applyParticle` silently falls back to an RNG shuffle (CRN property
broken, searcher RNG consumed). `search()` also lacks the terminal guard that
`searchToTotal()` has.

## Evidence

- `BattleScumSearcher3.cpp:149-157` (evaluationSum overwrite), `:117-124`
  (particles from initial pile), `:160-168` (unconditional calls).

## Why it matters

Latent (the ablation only exercises fair mode, fresh searcher per decision),
but reachable with `STS_S3_CRN=1` without `STS_FAIR`, and the 
`speedtest` mode calls `search()` 4x on one searcher (re-warming each time).

## Candidate fix direction

Fire the warm start at most once per searcher and never after `advanceRoot`.

## Relevant code

- `src/sim/search/BattleScumSearcher3.cpp` (`warmStartRootCRN`, `search`,
  `searchToTotal`, `advanceRoot`)
- `include/sim/search/BattleScumSearcher3.h` (members)

## Resolution (2026-08-05)

Fixed in the 2026-08-05 code-review working tree: new `rootCarried` /
`crnWarmStarted` members gate the warm start (once per fresh searcher, skipped
after `advanceRoot`). §106's CRN verdict (fair-mode, −14.1pp) is unaffected.
