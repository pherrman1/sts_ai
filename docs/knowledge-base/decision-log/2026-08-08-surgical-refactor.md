# 2026-08-08 — surgical refactor / research-velocity pass

Date: 2026-08-08
Session/task: Audit and refactor hotspots from 68-session agent telemetry

## Decision

Three low-risk changes implemented:

1. Removed dead `evalcombat`/`evalrun` modes from `apps/one_combat.cpp`
   (closed negative experiment, §3; −52 lines).
2. Added a 60-line "Current findings summary" to the top of `EXPERIMENTS.md`
   (accepted / falsified / open questions, with § cross-references).
3. Created `docs/knowledge-base/operations/environment-variables.md` — a
   single-page reference for all `STS_*` env vars consumed by `one_combat`.

## Rationale

Telemetry over 68 sessions showed `EXPERIMENTS.md` (334 reads) and
`apps/one_combat.cpp` (267 reads) as the top hotspots. Agents navigated
them effectively with grep, but the volume suggested two opportunities:

- A findings summary at the top of EXPERIMENTS.md so agents could check
  "is this idea already known bad?" without searching the full 6,700-line
  history.
- An env-flag reference so agents could look up configuration knobs
  without skimming ~900 lines of C++ `getenv`/`printf` chains in `main()`.

The dead-mode removal was the only genuinely dead code found during audit
that was safe to remove without touching other layers.

## Alternatives considered

- **Extract `computeEdgePriors` (S2/S3 near-duplicate)** — deferred.
  Genuine ~70-line duplication but S2 caps the GBM fallback at 64 edges
  (stack arrays), S3 uses dynamic vectors. Would need template/overload
  complexity for marginal savings. Not causing bugs yet.
- **Extract `enumerateActionsForNode` card/potion loops** — rejected.
  S2 uses `Expert::getPlayOrdering` sort; S3 uses unsorted hand iteration.
  This is an intentional experimental difference, not accidental duplication.
- **Split `one_combat.cpp`** — rejected. Too risky (10,883 lines of
  extraction) for marginal benefit; agents navigate it with grep.
- **Searcher base class** — rejected. Would be a large architectural
  change with ABI hazards (Node/Edge layout) and no clear behavioral benefit.
- **Remove legacy modes (`bench`, `cardbench`, etc.)** — rejected.
  These are historical harnesses for experiments documented in
  EXPERIMENTS.md; removal breaks ability to reproduce cited experiments.
- **Move findings summary to a separate `current-findings.md`** — deferred.
  Kept inline in EXPERIMENTS.md for now; if the summary grows or becomes a
  maintenance burden, promote it to
  `docs/knowledge-base/evaluation/current-findings.md` and keep
  EXPERIMENTS.md purely chronological.

## Evidence

- `apps/one_combat.cpp` — mode dispatch, env-flag parsing, removed functions
- `EXPERIMENTS.md` — new summary section (lines 31–88)
- `docs/knowledge-base/operations/environment-variables.md` — new doc
- `docs/knowledge-base/CODE_MAP.md`, `docs/knowledge-base/README.md` —
  updated cross-references
- Build + 9 CTest tests pass; `bestbench` smoke (1 seed, STS_FAIR=1) runs
  correctly

## Status and follow-up

- **Implemented**: all three changes merged.
- **Follow-up — `g_devalueHighHp`**: the extern flag in
  `include/sim/search/BattleScumSearcher2.h` and its definition/usage in
  `src/sim/search/BattleScumSearcher2.cpp` is now unreachable dead code
  (no remaining mode ever sets it to true). Remove it the next time
  Searcher2 is modified for a real change.
- **Follow-up — findings summary**: monitor whether the inline summary
  in EXPERIMENTS.md actually reduces agent reads. If it grows or becomes
  stale, promote to a separate `current-findings.md`.
