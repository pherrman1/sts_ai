# 2026-08-22 — Controlled task-branch first push

Date: 2026-08-22
Session/task: Permit Codex to publish newly created task branches after successful implementation and verification

## Decision

The repository workflow permits a controlled first push using exactly
`git push --set-upstream origin HEAD` when the current task created a
non-`main` branch, the task changes are verified and committed, `origin` is
the intended remote, no unrelated pre-existing commits would be published,
and the remote branch has no unexpected or unrelated history. Once an
upstream exists, subsequent pushes use plain `git push`. Successful
nontrivial branch work defaults to commit, permitted push, and draft pull
request creation or update when supported.

## Rationale

The previous rule blocked the normal first publication of an isolated task
branch even after the task was complete. The replacement preserves the
important boundary—no publication of unrelated history—and keeps review
centered on pull requests. `main`, force-pushes, history rewrites, branch
deletion, and global Git `autoSetupRemote` remain prohibited.

## Alternatives considered

- Enable Git `push.autoSetupRemote` globally — rejected because implicit
  upstream creation is broader and less auditable than one explicit guarded
  command.
- Permit arbitrary remote/refspec pushes — rejected because it weakens remote,
  branch, and provenance safeguards.
- Require every first push to be manual — rejected because it leaves completed
  task branches stranded locally despite successful verification.

## Evidence

- `AGENTS.md` critical safety and Git rules.
- `docs/knowledge-base/operations/agent-context-and-workflow.md` Modification
  and Git procedure and PR completion rules.
- `.clinerules/hooks/PreToolUse` and `tools/agent/cline_guardrails.py` for
  existing force-push and `main` protections.

## Status and follow-up

- Implemented in the repository workflow contract. Future first pushes must
  record the branch, intended `origin`, baseline, and remote-branch state
  before publishing.
