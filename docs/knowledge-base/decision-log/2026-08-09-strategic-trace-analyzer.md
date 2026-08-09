# 2026-08-09 — Strategic trace analyzer tool

Date: 2026-08-09
Session/task: Add the Wave-0D consumer for the `STS_OOC_STRATEGIC_TRACE` CSV.

## Decision

Add `tools/analyze_strategic_trace.py`, a strict consumer for the exact CSV
written by `apps/one_combat.cpp`'s `runFullRunOOC` flush (header
`seed,decIdx,act,floor,screen,nActions,actionBits,qValues,bestIdx,
bestSecondMargin,threshold,heurIdx,takeIdx,rule,owned,collectKeys,
stopAfterAct,won,finalFloor,finalHp`). It reports overall and per-screen
decision counts, owned (gate-fired) vs bypassed rates, margin-rule vs
regret-rule breakdown, best-second margin and best-Q summaries, and
decision-level owned-vs-bypassed outcome/final-floor/final-HP comparisons,
with `--json` output and a `--self-test` synthetic-data check. Schema drift
and malformed rows fail loudly (matching `paired_analysis.py` conventions);
the `-1.0` no-second margin sentinel is excluded from margin stats and
counted separately.

## Rationale

**Inference:** the trace's outcome columns are run-constant and repeated per
decision row, so the owned-vs-bypassed outcome comparison is decision-level;
the tool labels it as such rather than pretending it is run-level.

## Alternatives considered

- Registering the tool as a ctest entry — rejected: `CMakeLists.txt` uses
  CRLF line endings, and editing it would create mixed line endings that make
  `git diff --check` dirty; existing `tools/*_selftest.py` scripts are also
  standalone (not in ctest).

## Evidence

- `tools/analyze_strategic_trace.py::load/analyze/selftest`; self-test passes
  on 12 synthetic rows across 3 seeds with hand-computed statistics.
- `python3 -m py_compile tools/analyze_strategic_trace.py` passes.
- Real-producer smoke: `STS_OOC_STRATEGIC_TRACE=/tmp/strat_trace_real.csv
  STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_final.native
  ./build/one_combat bestbench 2 1 0 0` → 4 REWARDS decisions parsed and
  summarized (1 owned at margin 6.49, 3 bypassed), matching the CSV rows.

## Status and follow-up

- Implemented. No C++ or benchmark behavior changed.
