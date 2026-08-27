# 2026-08-27 — workflow retrospective corrections

Date: 2026-08-27
Session/task: Remove repeated review, evidence, and Windows/WSL workflow costs.

## Decision

Add three narrow operating checks to the maintained workflow: enumerate small
input-contract truth tables before publication, order final evidence around one
candidate SHA without unnecessary base synchronization or copying volatile CI
state into the PR description, and make the Windows-Git/WSL-build boundary,
per-worktree submodule initialization, and provenance-appropriate
link-completion check explicit.

## Rationale

PR #63 needed an extra correction because the paired binary-provenance check
covered either argument missing but not both missing. The same session repeated
final-SHA evidence and encountered avoidable uncertainty around linked-worktree
Git paths, uninitialized per-worktree submodules, and a long, quiet link step.
These are recurring workflow boundaries,
while the repository already has adequate ccache presets, CI checks, and review
infrastructure.

## Alternatives considered

- Add a generic validation or orchestration framework — rejected because the
  missed states are cheaply covered by a small explicit truth table.
- Add another watcher or evidence script — rejected because bounded CI polling
  and the existing PR evidence packet already cover execution.
- Put all details in `AGENTS.md` — rejected to keep the root contract concise;
  the routed operations pages are the maintained destination.

## Evidence

- `tools/agent/check_benchmark_canary.py` — explicit required-field contract and
  negative self-tests corrected during PR #63.
- `docs/knowledge-base/operations/agent-context-and-workflow.md` — workflow-v2
  review, publication, and evidence procedure.
- `docs/knowledge-base/operations/build-and-debugging.md` — checked-in WSL GCC,
  linked-worktree, ccache, and executable verification procedure.

## Status and follow-up

- Implemented as documentation-only operating guidance; no new tooling or
  gameplay verification is required.
