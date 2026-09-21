# Investigations

Last verified: 2026-08-11 against the current working tree.

This directory is for reproducible, unresolved technical investigations. An
investigation is evidence collection, not a decision or a speculative design.

## Current investigations

- [Silver retained-search queue-item audit (2026-09-21)](2026-09-21-silver-retained-search-audit.md) — bounded opportunity and native boundary audit for `curCardQueueItem`-only retained-state merging; narrow candidate remains unqualified and no search behavior changed.

- [Stale implementation audit (2026-08-11)](2026-08-11-stale-implementation-audit.md) —
  ranked cleanup candidates from a reachability + scientific-status map of
  `apps/`, `src/`, `include/`, `bindings/`. Identified 14 high-confidence
  dead CLI modes, 2 load-only dead flags, and ~20 superseded-connected items.
  Recommends 6 sequential cleanup batches plus deferred items. **Phase 6
  Batch 1 completed 2026-08-12:** the four server-dependent benchmark modes
  (`restbench`, `shopbench`, `allbench`, `skipbench`) and their wrappers were
  removed; 10 high-confidence dead CLI modes remain for Batch 2. Corrected
  2026-08-11 to fix classification errors (datagen caller, S3_UNION_EXPAND
  behavior, ENDTURN_MARGINALIZE behavior, missing reuse flags).

The resolved Searcher3 reuse investigation was distilled into
[`decisions/s3-obs-stable-reuse-promotion.md`](../decisions/s3-obs-stable-reuse-promotion.md).
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
