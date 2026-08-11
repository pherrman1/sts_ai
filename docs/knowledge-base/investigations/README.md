# Investigations

Last verified: 2026-08-11 against the current working tree.

This directory is for reproducible, unresolved technical investigations. An
investigation is evidence collection, not a decision or a speculative design.

## Current investigations

- [Stale implementation audit (2026-08-11)](2026-08-11-stale-implementation-audit.md) —
  ranked cleanup candidates from a reachability + scientific-status map of
  `apps/`, `src/`, `include/`, `bindings/`. Identifies 22+ dead one_combat
  modes, ~15 diagnostic-only flags, and 2 load-only flags as HIGH-confidence
  deletion candidates. Recommends 6 sequential cleanup batches. **Investigation
  only — no deletions performed.**

The resolved Searcher3 reuse investigation was distilled into
[`decisions/s3-obs-stable-reuse-promotion.md`](../decisions/s3-obs-stable-reuse-promotion.md).
Its intermediate reports are retained under `docs/archive/research/s3-reuse/`.
The historical PVNet headline investigation remains in this directory as a
closed reproducibility record, not an active task.

## Required record format

Each investigation should include status, `Last verified`, symptom, scope,
exact reproduction, expected/observed results, evidence, hypotheses labelled
**Inference**, eliminated hypotheses, current blocker or next check, and a
`Relevant code` section. Close it with the fixing commit/test or mark it
obsolete if the reproduction disappears.

## Relevant code

- `src/sim/search/BattleScumSearcher3.cpp` — current search/RNG candidates.
- `src/sim/search/ScumSearchAgent2.cpp` — Searcher3 construction and fair execution.
- `apps/one_combat.cpp` — reproducibility and CSV producer paths.
- `paired_analysis.py` — current CSV consumer.
- `CMakeLists.txt` and `.gitmodules` — bootstrap discrepancy.
