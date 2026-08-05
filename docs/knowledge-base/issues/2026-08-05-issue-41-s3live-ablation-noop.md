# Issue 41: g_s3Live=0 ablation arm measured nothing

- **Status:** closed
- **Tier:** High
- **Last verified:** 2026-08-05
- **Source:** code review 2026-08-05; `ScumSearchAgent2.cpp`

## Symptom

`STS_S3_LIVE=0` (arm A5, "S3 minus live-valid root-edge filter") originally
picked the most-visited edge and then fell back to the next-most-visited
**valid** edge. Since both branches only ever returned a legal action and the
default branch already picks the most-visited valid edge, the ablation changed
nothing but tie-breaking — an A5 null result could not be read as "the
live-valid filter doesn't matter".

## Evidence

- `ScumSearchAgent2.cpp::s3PickRootAction` (pre-fix: validity filter in both branches).
- `run_s3_ablate.sh` A5 description.

## Why it matters

The §106 ablation (recorded by the concurrent 2026-08-05 session) reports
prune/live toggles as inert; for live the claim only holds once the arm
actually removes the filter (or measures Searcher2's "invalid most-visited
edge ends the battle" behavior).

## Candidate fix direction

Make the ablation branch return the most-visited edge with no validity
fallback; an invalid most-visited edge ends the battle exactly like the
Searcher2 loop (`ScumSearchAgent2.cpp:141-144`).

## Relevant code

- `src/sim/search/ScumSearchAgent2.cpp::s3PickRootAction`

## Resolution (2026-08-05)

Fixed in the 2026-08-05 code-review working tree (no-fallback semantics).
The 5 non-polluted §106 arms stand; s2_ref/s3_ctl were re-run clean after the
bestbench-append trap (issue 46) was found; see rerun-ledger.
