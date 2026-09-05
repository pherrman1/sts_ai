# ADR-0012: Retain historical evidences in Git history

- Status: accepted
- Date: 2026-09-04
- Last verified: 2026-09-05

## Decision

The dated per-session historical evidence was historical and is now removed from the
active tree. New repository
knowledge goes to the maintained knowledge base, durable workflow or
architecture choices to ADRs, benchmarked results to `EXPERIMENTS.md`,
reproducible unresolved diagnoses to investigations, and temporary task detail
to pull requests or commits only. Historical content is recoverable with
`git show <commit>:` when provenance is
explicitly required.

## Evidence and consequence

This boundary is enforced by `tools/repo_health.py`, which hard-fails newly
tracked paths under the deleted historical evidence prefix, and is documented in
`AGENTS.md`, the KB index, and `operations/agent-context-and-workflow.md`. It
prevents recreation while preserving Git history.
