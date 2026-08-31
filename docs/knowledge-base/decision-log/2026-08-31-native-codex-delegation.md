# 2026-08-31 — Native Codex delegation

Date: 2026-08-31
Session/task: Clarify native Codex task delegation under workflow-v2

## Decision

One coordinating Codex session may use native subtasks under an accepted
design. Delegate only independent inspection, non-overlapping implementation,
or verification where useful. Subtasks do not redesign the accepted plan or
expand its scope. Same-change subtasks may share the coordinator's worktree;
independent branches or experiments retain separate worktrees.

## Rationale

Native Codex delegation can reduce execution time and duplicated orchestration
while preserving the existing ChatGPT-owned design boundary. Keeping
same-change subtasks under one coordinator/worktree avoids unnecessary branch
and worktree overhead.

## Alternatives considered

- One worktree/session per subtask — rejected because it adds coordination and
  Git overhead without improving isolation for one accepted change.
- Let subtasks independently redesign or explore alternatives — rejected
  because conceptual scope remains the ChatGPT/design-layer responsibility.
- Add custom orchestration/MCP infrastructure — rejected because native Codex
  capabilities cover the identified need with less complexity.

## Evidence

- `AGENTS.md`
- `.agents/skills/codex-implementation/SKILL.md`
- `docs/knowledge-base/operations/agent-context-and-workflow.md`

## Status and follow-up

- Accepted operating policy; no new ADR is required.
