# 2026-08-08: Context telemetry v2 summarizer

## Context

Improve the Pi context-read telemetry summarizer to distinguish necessary
exploration from redundant rereading, large reads from small reads, and
hotspots from navigation problems. Telemetry-only — no production code or
agent behavior changes.

## Decision

Rewrote `tools/summarize_agent_context.py` with 11 analytical sections:
1. Operation breakdown (read/search/list/git/inspect/other)
2. Top files by read calls
3. Top files by requested lines (mean/median/max)
4. Unique vs repeated line coverage (interval merging, duplication ratios)
5. Hot-region analysis (200-line buckets, configurable)
6. Per-session duplication
7. Cross-agent duplication (reported unavailable for historical data)
8. Repeated search analysis (same-session + cross-session)
9. CODE_MAP usage tracking + CODE_MAP-first rate
10. Human-readable default report
11. Machine-readable JSON output (`--json PATH`)

Rewrote `tools/test_agent_telemetry.py` with 46 tests covering all 15
required test cases from the handoff.

Created `docs/knowledge-base/operations/context-telemetry.md` as the
telemetry tooling documentation page.

Updated CODE_MAP.md to link to the new page.

## Rationale

The old summarizer had fundamental limitations: it counted read calls
without measuring content volume, didn't distinguish unique line coverage
from repeated reads, didn't identify hot regions in large files, and mixed
read operations with search operations. The new summarizer fixes these by
using interval merging for line-coverage analysis, bucket-based hot-region
identification, and strict operation classification.

**Inference**: Interval merging for unique-line coverage is the correct
approach; it's O(n log n) in the number of read operations and doesn't
allocate per-line arrays.

Agent/parent_session metadata is absent from all historical telemetry
(0 of 1226 records), so cross-agent duplication is reported as unavailable
rather than invented.

## Alternatives considered

- **Add agent/parent_session to the TS telemetry extension**: Blocked by
  `.pi/extensions/` safety protection. Would also not help historical data.
  The Python-only approach is simpler and adequate — new sessions will
  naturally include these fields when the extension is updated separately.

- **Line-by-line array expansion for coverage**: Rejected in favor of
  interval merging (O(n log n) vs O(max_line_number)).

## Evidence

- Summarizer: `tools/summarize_agent_context.py`
- Tests: `tools/test_agent_telemetry.py` (46 tests pass)
- Documentation: `docs/knowledge-base/operations/context-telemetry.md`
- CODE_MAP update: `docs/knowledge-base/CODE_MAP.md`

## Results for current 44-session corpus (1226 records)

| Metric | Value |
|--------|-------|
| Total records | 1,226 |
| Read operations | 545 |
| Search operations | 626 |
| List operations | 35 |
| Git inspection | 20 |
| Top file by reads | `apps/one_combat.cpp` (119 reads, 9,107 lines requested, 56.0% dup) |
| Top file by duplication | `train_strategic_tok.py` (73.6% dup, 2,800/740 lines) |
| Top one_combat.cpp hot region | Lines 1401-1600 (18 reads touching) |
| Top EXPERIMENTS.md hot region | Lines 6201-6400 (11 reads touching) |
| CODE_MAP read rate | 18/44 sessions (40.9%) |
| CODE_MAP-first rate | 16/44 sessions (36.4%) |
| Unknown-range reads | 157 (excluded from coverage analysis) |
| Cross-agent available | No (0 records with agent metadata) |

## Status

Done. Summarizer is functional and tested. Cross-agent dedup depends on
future telemetry collecting agent metadata.

## Follow-up

- Update `.pi/extensions/sts-telemetry/index.ts` to emit `agent`, `session`,
  and `parent_session` when the safety extension allows it.
- Re-run summarizer after collecting new telemetry with agent metadata to
  populate the cross-agent duplication section.
- Consider extracting frequently re-read hot regions (e.g.,
  `one_combat.cpp` lines 1401-1600) into focused include files.
