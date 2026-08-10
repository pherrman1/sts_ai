# 2026-08-10 — default completion: focused commit + plain upstream push

Date: 2026-08-10
Session/task: Agent-workflow change: default commit+push on successful handoffs

## Decision

- `AGENTS.md` gained a "Default completion: commit and push" contract: a
  successfully completed coding handoff that changed the repository is
  committed (focused, task-scoped) and pushed to its configured upstream with
  plain `git push` by default. No explicit `git commit`/`git push` request is
  needed.
- `.opencode/prompts/implementer.md` now points the agent at that contract and
  dropped "do not commit/push unless the user explicitly asks".
- `opencode.json` bash permission rules for both agents (`default`, `strong`):
  `git commit *` allow, `git commit --amend*` deny, `git push *` deny, `git
  push` allow, plus targeted deny rules for explicit-git-path and
  git-option push forms (`*/git push*`, `git -C * push*`,
  `git --git-dir=* push*`, `git --work-tree=* push*`, `git -c * push*`,
  `git --no-pager push*`).

## Rationale

- **Inference** (verified against opencode v1.18.15 source
  `packages/opencode/src/permission/index.ts::evaluate` and
  `packages/core/src/util/wildcard.ts::match`): bash permission patterns match
  the full command string with last-match-wins across the ruleset
  (`.findLast`). A pattern ending in ` *` matches bare command and
  argument-bearing forms alike (`( .*)?`), so `git push *` deny + `git push`
  allow (in that order) yields: bare `git push` allowed, every
  argument-bearing/dangerous push form denied.
- Task-scoped staging is enforced by contract (inspect pre-edit `git status`,
  never assume every dirty file belongs to the task) plus the unchanged
  destructive-git denies.

## Alternatives considered

- Substring deny `*git push*` — rejected: it would also deny legitimate
  commands whose text contains "git push" (e.g. a commit message mentioning
  push policy), breaking the very commit path this change enables.
- Allowing only `git push *` deny with no bare-push exception — rejected:
  bare `git push` would stay denied because the trailing ` *` is optional.

## Evidence

- `opencode.json` (both agents), `AGENTS.md` ("Default completion: commit and
  push"), `.opencode/prompts/implementer.md`.
- Permission matrix (46 cases) run against the actual config in both agents:
  all required ALLOW/DENY outcomes hold, including `git push` ALLOW,
  `git push --force` / `--force-with-lease` / `origin HEAD` / `-u` /
  `--set-upstream` / `origin --delete` DENY, direct `one_combat` DENY,
  `tools/seed_guard.sh *` ALLOW, and destructive git/rm denies unchanged.
- Seed guard unchanged; `guard-only` run returns exit 0 at 8 seeds and exit 1
  at 129 seeds.
- Residual unblockable bypass forms (whitespace variants, `cd && git push`,
  `bash -c`, env prefixes, `sudo`) are documented; the permission layer is a
  compliance backstop, not an absolute security boundary.

## Status and follow-up

Closed. OpenCode config requires an opencode restart to take effect. No
gameplay/model/training code touched.
