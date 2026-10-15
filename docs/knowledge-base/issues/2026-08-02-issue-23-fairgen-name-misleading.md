# Issue 23: `fairgen` does not enable the fair path itself

- **Status:** closed
- **Tier:** Medium
- **Last verified:** 2026-08-02
- **Source:** [`architecture/training-and-inference.md`](../architecture/training-and-inference.md), "Known limitations"

## Symptom

The `fairgen` mode installs the Searcher3 hook but does not set `g_fairPlay` or
`g_useSearcher3`; callers need `STS_FAIR=1 STS_SEARCHER3=1` for the intended
project-fair Searcher3 producer. Without Searcher3, its policy output has no
callback rows. The mode name is misleading and its archived invocation records
only `STS_SEARCHER3=1`.

## Evidence

- `apps/one_combat.cpp::runFairGenSeed`, `fairGen` branch: hook installation
  without flag setting.
- `training-and-inference.md`: "`fairgen` installs the Searcher3 hook but does
  not set `g_fairPlay` or `g_useSearcher3`."

## Why it matters

Datasets produced under an accidentally wrong regime are silently mislabelled
fair; the PVNet training-data provenance issue (Issue 16) is a direct
consequence.

## Candidate fix direction

Make `fairgen` require or set both flags (or abort with an explicit message),
and record the exact flags in generated data provenance.

## Relevant code

- `apps/one_combat.cpp::fairGen`, `runFairGenSeed`
- `src/sim/search/ScumSearchAgent2.cpp` hooks

## Resolution (2026-08-02)

Fixed: `fairgen` forces `search::g_fairPlay` and `search::g_useSearcher3` in its dispatch branch with a printed message. Verified: 1-seed run emits 983 policy rows without `STS_FAIR=1 STS_SEARCHER3=1`.

## Closed by

*Fixed in the 2026-08-02 working tree (uncommitted); re-run the referenced focused checks before committing.*
