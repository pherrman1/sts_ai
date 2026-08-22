# 2026-08-22 — Retire runtime Cline compatibility

## Decision

Retire the repository-owned Cline rollback integration after the Codex pilot:
remove `.cline/`, `.clinerules/`, and `.clineignore`, and remove their current
operational documentation. Do not add a Codex hook adapter. Keep
`tools/agent/cline_guardrails.py`, its tests, and the
`guardrail-command-policy` task because the maintained, model-agnostic
coding-agent evaluator and CI still invoke them; they are evaluation fixtures,
not active runtime enforcement.

Remove repository-scoped RepoWise MCP startup. Independent review established
that RepoWise 0.42.0 discovers an ancestor workspace even when started with the
exact worktree path, and an unregistered linked worktree falls back to the
workspace's primary alias. Its MCP command exposes no force-single-repo option.
RepoWise remains opt-in and manual only after exact path verification; otherwise
use Git, `rg`, and focused reads.

## Acceptance evidence

- Read-only: this task first verified every registered worktree, branch, HEAD,
  upstream, and status. The primary checkout and `origin/main` were both
  `931d2b65ff924c2c07bde67e7c2dac7c18392b3e`, with a clean `main`; edits then
  moved to a dedicated non-main worktree.
- Implementation and correction: [PR #40](https://github.com/pherrman1/sts_ai/pull/40)
  changed C++ behavior and tests, preserved scientific evidence, corrected the
  first failing CI run in commit `a82e4d4`, and finished with a successful
  `Linux GCC` check.
- Research: [PR #42](https://github.com/pherrman1/sts_ai/pull/42) recorded an
  invalid smoke result rather than reinterpreting it, revised the diagnostic,
  froze a 24-seed cohort, published results and artifacts, supplied an evidence
  packet, and finished with successful `Linux GCC` CI.
- Review status: neither PR has a GitHub review object, so their correction
  behavior and final CI gates do not prove independent review-correction; PR
  #42 also began before the workflow-v2 merge. Independent review of
  `e6927a63cdee82a371d9ad7bac80423f71ae12af` verified the Cline retirement and
  retained evaluation fixture but found a P1 RepoWise routing error. This
  correction addresses that finding, but migration acceptance remains pending
  fresh independent review of the corrected SHA.

## Tool-routing evidence

- Serena 1.7.0 activated the exact task-worktree path with C++ and Python LSPs.
  A semantic lookup resolved `tools/agent/eval.py::safe_rel`; a reference query
  returned callers in `load_tasks`, `prepare`, and `grade`. Fresh worktrees do
  not have a C++ compilation database by default, so C++ definitions are
  available but caller/reference completeness is not established; keep the
  documented Git/`rg` fallback.
- RepoWise 0.42.0 resolved the original `mcp ..` configuration to the parent
  workspace's default `sts_lightspeed` alias, which points at the primary
  checkout rather than the active task worktree. That index was 166 commits
  behind current `main`.
- A mock-embedding, no-prose local index reported the exact task-worktree path
  and baseline `931d2b65`, with zero model tokens or cost. A broad workflow and
  safety-boundary query completed, but it still classified superseded ADR-0008
  as active; `repowise doctor` also reported 20 stale pages plus SQL/vector/FTS
  drift. These results demonstrate index limitations, not configured MCP
  routing.
- Independent review then showed that `mcp .` also discovers the ancestor
  workspace and falls back to `sts_lightspeed` because the task worktree is not
  registered there. `repowise mcp --help` exposes no `--no-workspace` or other
  force-single-repo option, so the repository-scoped MCP entry is removed.
  RepoWise remains non-authoritative and may be used manually only after exact
  worktree routing is established.

## Alternatives considered

- Delete the Python guardrail and tests with the runtime files: rejected because
  the current evaluator task and CI are non-Cline callers.
- Keep RepoWise in parent-workspace mode and require an alias check every time:
  rejected because a missing worktree alias silently selected another checkout.
- Keep RepoWise at `mcp .`: rejected after independent review proved that
  ancestor workspace discovery still selected the primary checkout.
- Add a Codex hook adapter: rejected as out of scope and still unsupported by
  protocol fixtures.

## Status and follow-up

Pending acceptance. Historical Cline decision logs and ADRs remain unchanged.
The runtime deletions and retained evaluation fixture are implemented, and the
misrouted repository-scoped RepoWise entry is removed. The corrected SHA must
pass CI and fresh independent review before migration acceptance is complete.
RepoWise remains opt-in/manual with exact-path verification; otherwise the
Git/`rg` fallback is authoritative.
