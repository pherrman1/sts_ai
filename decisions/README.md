# Architectural decision records

This directory contains durable, evidence-backed architectural decision records
(ADRs). It is intentionally separate from the chronological session log in
[`docs/knowledge-base/decision-log/`](../docs/knowledge-base/decision-log/).
The chronological log records decisions and discoveries when they happen;
these ADRs distill only the small set of decisions whose current rationale is
directly supported by repository evidence.

Git-tracked Markdown is authoritative. RepoWise may index these ADRs to supply
structural and rationale context, but its generated index is derived local
state and never replaces an ADR, source code, tests, curated knowledge-base
pages, or raw evidence.

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

## Current routing ADRs

- [ADR-0010](0010-codex-chatgpt-agent-workflow.md) defines the ChatGPT/Sol
  handoff, bounded Codex preflight, evidence-packet review boundary, session
  continuation rules, optional Serena/RepoWise routing, and reviewed-SHA freeze.
- [ADR-0008](0008-guarded-cline-serena-repowise-routing.md) is retained as the
  historical Cline-era routing decision and is superseded by ADR-0010 for
  harness/routing policy.
