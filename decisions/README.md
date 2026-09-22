# Architectural decision records

This directory contains durable, evidence-backed architectural decision records
(ADRs). These ADRs capture only the small set of decisions whose current rationale is directly supported by repository evidence. New durable choices belong here.

Git-tracked Markdown is authoritative. Derived local indexes never replace an
ADR, source code, tests, curated knowledge-base pages, or raw evidence.

## What belongs here

Create an ADR only for a current, durable architecture or operating boundary
with a meaningful alternative and repository evidence. Every record must name
affected files and exact evidence. Do not promote a one-off bug fix, temporary
plan, dated run state, unresolved investigation, or experimental outcome.
Experiment measurements remain in [`EXPERIMENTS.md`](../EXPERIMENTS.md) and its
ledger shards; maintained technical understanding remains in
[`docs/knowledge-base/`](../docs/knowledge-base/).

## Lifecycle

Use the deterministic `0001-<slug>.md` filename scheme and the standard ADR
sections. If a decision changes, add a new ADR that states what it supersedes
and links the historical record; do not rewrite the old ADR or chronological
entry. Mark the earlier ADR `superseded` only when current evidence establishes
the replacement.

## Current architecture ADRs

- [ADR-0015](0015-live-silver-equivalent-copy-reroot.md) preserves retained
  live Silver visits when the human plays a different equivalent physical card
  copy, without relaxing global search-state or transposition identity.
- [ADR-0014](0014-live-ooc-visit-lock-stopping.md) enables live strict visit-lock
  stopping through an explicit policy override while retaining the false
  non-aborting provider guarantee and a rollback switch.

## Current routing ADRs

- [ADR-0017](0017-silver-quiescent-queue-item-identity.md) accepts
  quiescent Silver queue-item identity without retained-root rewriting.
- [ADR-0016](0016-silver-settled-queue-item-identity.md) records the rejected
  settled Silver queue-item identity candidate and consumed HOLDOUT evidence.

- [ADR-0012](0012-frozen-session-decision-log.md) routes historical session material to Git history and new knowledge to canonical maintained destinations.
- [ADR-0011](0011-mcp-free-codex-skillopt-pilot.md) defines the MCP-free Codex
  path, authoritative tracked KB, bounded SkillOpt proposal pilot, and
  independent evaluator gate. It supersedes only ADR-0010's active tool routing.
- [ADR-0010](0010-codex-chatgpt-agent-workflow.md) remains authoritative for
  the ChatGPT/Sol handoff, bounded Codex preflight, evidence-packet review
  boundary, session continuation rules, and reviewed-SHA freeze. Its tool
  routing is historical and superseded by ADR-0011.
- [ADR-0008](0008-guarded-cline-serena-repowise-routing.md) is retained as the
  historical Cline-era routing decision and is superseded by ADR-0010 for
  harness/routing policy.
