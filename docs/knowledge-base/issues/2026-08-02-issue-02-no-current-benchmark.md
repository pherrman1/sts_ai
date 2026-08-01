# Issue 02: No fresh benchmark on the current checkout

- **Status:** closed
- **Tier:** Critical
- **Last verified:** 2026-08-02
- **Source:** [`evaluation/current-baselines.md`](../evaluation/current-baselines.md), "Known limitations"

## Symptom

The primary recorded project-fair reference (39/128 wins, 2026-07-23,
`EXPERIMENTS.md` §66i) cannot be exactly reproduced from tracked artifacts: the
raw cited directory is absent and not every flag/model hash is pinned. No
current-checkout measurement claims the default stack equals or exceeds that
reference.

## Evidence

- `current-baselines.md` baseline table: the primary fair row is marked
  **Unverified** for exact searcher and flags; the raw directory is absent.
- `current-baselines.md` "Open questions": which exact artifact hashes and flags
  produced the 39/128 result; what the current default stack's paired result is
  on the recorded seed block.

## Why it matters

Every downstream comparison (Searcher3/PVNet experiments, self-play gates)
anchors on a headline that may not describe the current executable. Baseline
claims are the project's truth reference; an unverified anchor silently
invalidates relative conclusions.

## Candidate fix direction

Run the recorded seed block with the current default stack under the recorded
flags and record the result as a new, correctly labelled measurement; treat any
39/128 comparison as provisional until then.

## Relevant code

- `apps/one_combat.cpp::bestBench`, `runFullRunOOC`
- `EXPERIMENTS.md` §26, §66i

## Resolution (2026-08-02)

Resolved: the current default fair stack was measured on the recorded block (128 seeds, 1000 sims, A0, `STS_FAIR=1`, 12 threads) as **27/128 (21.1%)**, floor 37.5, HP 8.6; see `EXPERIMENTS.md` §68 and the updated `current-baselines.md` row. Not a paired comparison with §66i.

## Closed by

*Fixed in the 2026-08-02 working tree (uncommitted); re-run the referenced focused checks before committing.*
