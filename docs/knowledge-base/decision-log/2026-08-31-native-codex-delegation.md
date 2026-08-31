# 2026-08-31 — Native Codex delegation

Date: 2026-08-31
Session/task: Clarify native Codex task delegation under workflow-v2

## Decision

One coordinating Codex session may use native subtasks under an accepted
design. Delegate only independent inspection, non-overlapping implementation,
or verification where useful. Subtasks do not redesign the accepted plan or
expand its scope. Same-change subtasks may share the coordinator's worktree;
independent branches or experiments retain separate worktrees.

## Evidence

- `AGENTS.md`
- `.agents/skills/codex-implementation/SKILL.md`
- `docs/knowledge-base/operations/agent-context-and-workflow.md`

## Status and follow-up

- Accepted operating policy; no new ADR is required.
