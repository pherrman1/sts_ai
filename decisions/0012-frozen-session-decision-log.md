# ADR-0012: Freeze the per-session decision log

- Status: accepted
- Date: 2026-09-04
- Last verified: 2026-09-04

## Decision

The dated per-session decision log is historical and frozen. New repository
knowledge goes to the maintained knowledge base, durable workflow or
architecture choices to ADRs, benchmarked results to `EXPERIMENTS.md`,
reproducible unresolved diagnoses to investigations, and temporary task detail
to pull requests or commits only. Existing dated entries are retained.

## Evidence and consequence

This boundary is enforced by `tools/repo_health.py`, which hard-fails newly
tracked dated decision-log entries, and is documented in `AGENTS.md`, the KB
index, and `operations/agent-context-and-workflow.md`. It prevents unbounded
session-log growth without deleting historical evidence.
