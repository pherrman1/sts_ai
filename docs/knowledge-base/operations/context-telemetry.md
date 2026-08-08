# Context-Usage Telemetry Tooling

Last verified: 2026-08-08 against the current working tree.

## Purpose

Diagnostic measurement of how Pi agent sessions consume repository context:
what they read, how much they reread, what they search for repeatedly, and
whether routing documents like CODE_MAP are actually used.

This is **telemetry-only**. It does not modify agent behaviour, refactor
production code, or change prompts.

## Architecture

```
┌────────────────────────────┐     ┌─────────────────────────────┐
│ .pi/extensions/            │     │ tools/summarize_agent_      │
│ sts-telemetry/index.ts     │────▶│ context.py                  │
│ (JSONL writer)             │     │ (aggregator + reporter)     │
└────────────────────────────┘     └─────────────────────────────┘
         │                                      │
         │ .ai/<session>/                        │
         │ context-reads.jsonl                   │
         ▼                                      ▼
┌────────────────────────────┐     ┌─────────────────────────────┐
│ Per-session JSONL          │     │ Human-readable report +     │
│                            │     │ machine-readable JSON       │
└────────────────────────────┘     └─────────────────────────────┘
```

### Writer: `.pi/extensions/sts-telemetry/index.ts`

A Pi extension hook that records metadata about `read`, `grep`, `find`, `ls`,
`sts_git`, and `sts_inspect` tool calls. Writes per-session JSONL to
`.ai/<sessionId>/context-reads.jsonl`.

**Never records**: reasoning, API keys, file contents, full prompts,
environment variables, auth headers, or arbitrary shell output.

**Recorded fields** (current schema):

| Field | Type | Description |
|-------|------|-------------|
| `ts` | ISO-8601 string | Timestamp |
| `tool` | string | Tool name (`read`, `grep`, `find`, `ls`, `sts_git`, `sts_inspect`) |
| `ok` | bool | Optimistic `true` (updated on `tool_execution_end` when available) |
| `model` | string | Model ID |
| `turn` | int | Turn counter within the session |
| `path` | string | Repository-relative path |
| `offset` | int | Read start line (1-based) |
| `limit` | int | Requested line count |
| `pattern` | string | Search pattern / sts_git subcommand |

**Planned additions** (not yet emitted, needed for cross-agent dedup):

| Field | Type | Description |
|-------|------|-------------|
| `session` | string | Session ID |
| `agent` | string | Agent role (architect, implementer, investigator, reviewer) |
| `parent_session` | string | Parent session ID for subagent telemetry |

Historical sessions (before 2026-08-09) lack these fields. The summarizer
handles this gracefully and reports the limitation.

### Summarizer: `tools/summarize_agent_context.py`

Aggregates one or more JSONL files into a comprehensive report.

Usage:
```bash
# Human-readable report
python3 tools/summarize_agent_context.py .ai/*/context-reads.jsonl

# With JSON output
python3 tools/summarize_agent_context.py .ai/*/context-reads.jsonl --json build/summary.json

# Hot-region analysis for specific files
python3 tools/summarize_agent_context.py .ai/*/context-reads.jsonl \
    --hot-file apps/one_combat.cpp --hot-file EXPERIMENTS.md

# Custom bucket size
python3 tools/summarize_agent_context.py .ai/*/context-reads.jsonl --bucket-lines 100
```

The report covers:

1. **Operation breakdown** — read, search, list, git-inspection, artifact-inspection, other
2. **Top files by read calls**
3. **Top files by requested lines** — with mean/median/max
4. **Unique vs repeated line coverage** — interval merging, duplication ratios
5. **Hot-region analysis** — configurable 200-line buckets, top N regions
6. **Per-session duplication**
7. **Cross-agent duplication** — architect vs investigator overlap (unavailable for historical data)
8. **Repeated searches** — same-session + cross-session
9. **CODE_MAP usage** — read rate and CODE_MAP-first rate
10. **Highest-cost sessions** — by requested lines
11. **Data-quality warnings** — unknown ranges, missing metadata

## Definitions

### Requested lines
Sum of `limit` values across all `read` operations for a file. Computed from
tool-call arguments, so available even when returned-byte metadata is absent.

### Unique lines
Merged interval length after combining all `[offset, offset+limit)` ranges for
a file. Two reads that overlap are merged before counting. Reads without
offset/limit are excluded.

### Repeated lines
`requested_lines - unique_lines`. The number of lines that were read more
than once across different `read` calls.

### Duplication ratio
`repeated_lines / requested_lines`. A ratio of 0% means every read covered
new content; 100% means every line was read multiple times. Higher ratios
suggest candidate files for extraction, caching, or restructuring.

### Hot-region bucket
A fixed-size window (default 200 lines) covering one or more read intervals.
A read spanning multiple buckets contributes to each bucket proportionally.
Bucket reads-touching counts the number of read calls that intersected the
bucket.

### CODE_MAP-first rate
The fraction of sessions that read `docs/knowledge-base/CODE_MAP.md` before
their first read of a production source file (`apps/`, `src/`, `train_*`,
`EXPERIMENTS.md`). Sessions with no production reads at all count as
CODE_MAP-first if they read CODE_MAP at any point.

### Cross-agent duplication
Reads of the same line ranges by different agents (e.g., architect vs
investigator) within the same parent session. Currently unavailable because
historical telemetry (pre-2026-08-09) lacks `agent` and `parent_session`
metadata.

## Limitations

- **157 reads in the current corpus lack offset/limit** and are excluded from
  unique-line and duplication analysis. These are mostly from older sessions
  before the telemetry extension captured range metadata.
- **Agent role metadata is absent** from all historical sessions. Cross-agent
  duplication analysis is unavailable.
- **Subagent parent relationships are not recorded** in historical telemetry.
- **Duration and returned-byte data** are not recorded (to avoid expensive
  instrumentation).
- **File extension classification** groups `EXPERIMENTS`, `CMakeLists`, and
  `AGENTS` by their basename as a pseudo-extension.

## Relevant code

| Component | Path |
|-----------|------|
| Telemetry writer | `.pi/extensions/sts-telemetry/index.ts` |
| Summarizer | `tools/summarize_agent_context.py` |
| Tests | `tools/test_agent_telemetry.py` |

## Data-quality invariants

The summarizer maintains:

```
sum(reads_by_extension) == total_read_operations_with_file_extension
```

Implemented as an assertion in `summarise()`. A synthetic `(no ext)` bucket
catches read events with missing or empty paths.

## Tests

46 unit tests in `tools/test_agent_telemetry.py` covering:
operation classification, extension counts (reads-only), interval merging
(overlap, disjoint, nested, adjacent), duplicate-line counting, hot-region
bucket spanning, unknown-range reporting, per-session aggregation,
repeated-search counting, cross-agent unavailability flag,
backward compatibility, CODE_MAP-first classification, malformed JSONL
safety, sensitive-field exclusion, and write-failure non-fatality.

Run with:
```bash
PYTHONPATH=. python3 tools/test_agent_telemetry.py -v
```

## Open questions

- When `agent` and `parent_session` metadata land in new sessions (post
  2026-08-09), what architect-vs-investigator overlap will we see?
- Should hot-region analysis drive extraction of specific `one_combat.cpp`
  regions (e.g., lines 1401-1600, 4601-4800) into focused include files?
- Should frequently duplicated KB pages be restructured based on duplication
  ratios?
