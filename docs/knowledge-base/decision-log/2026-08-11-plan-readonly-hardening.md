# 2026-08-11 — Plan read-only hardening: deny Bash entirely

Date: 2026-08-11
Session/task: Correct the `plan` agent in `opencode.json` so it is genuinely
read-only.

## Decision

- The prior intention was correct: OpenCode `plan` should be genuinely
  read-only (see `2026-08-11-agent-workflow-supersedes-pi.md`).
- The selective Bash allowlist did not establish that property: allowed shell
  commands can still produce filesystem side effects (e.g.
  `git diff --output=file.patch`) and shell redirection is not restricted by
  command-prefix allowlists.
- Correction: `agent.plan.permission.bash` is now `"deny"` — `plan` cannot
  invoke arbitrary shell commands at all and inspects the repository through
  OpenCode-native read/search/listing tools instead. `edit`/`task`/web access
  remain denied.
- This supersedes only the Plan-Bash implementation detail in
  `2026-08-11-agent-workflow-supersedes-pi.md`; the broader Build/Plan
  workflow decision remains adopted.

## Rationale

- **Inference**: a Bash permission allowlist gates on the command string, not
  on the command's side effects; the only robust way to guarantee read-only is
  to deny Bash outright. OpenCode's native `read`/`grep`/`glob`/`list` tools
  cover repository inspection without a shell.
- `"bash": "deny"` is valid per the OpenCode config schema
  (`PermissionRuleConfig` accepts a plain action string, same shape as the
  existing `"edit": "deny"`).

## Alternatives considered

- Keeping the selective git-allowlist — rejected: `git diff --output=...`,
  redirection, and similar allowlisted forms can still write files.
- Building a more elaborate "safe Bash command" allowlist — rejected: it
  cannot be proven side-effect-free; denial is the smallest robust
  implementation.

## Evidence

- `opencode.json` (`agent.plan.permission.bash`), verified with
  `python3 -m json.tool` and against the OpenCode config schema
  (`PermissionRuleConfig` anyOf plain action string or glob map).
- Prior statement superseded: `docs/knowledge-base/decision-log/2026-08-11-agent-workflow-supersedes-pi.md`
  ("Plan is optional genuinely read-only planning mode: `edit`, `task`, and
  all but an explicit read-only git-inspection bash subset are denied").

## Status and follow-up

Implemented. Build agent permissions, seed limits, and the rest of the
workflow decision are unchanged.
