# 2026-08-22 — Retire runtime Cline compatibility

## Decision

Retire the repository-owned Cline rollback integration after the Codex pilot:
remove `.cline/`, `.clinerules/`, and `.clineignore`, and remove their current
operational documentation. Do not add a Codex hook adapter. Keep
`tools/agent/cline_guardrails.py`, its tests, and the
`guardrail-command-policy` task because the maintained, model-agnostic
coding-agent evaluator and CI still invoke them; they are evaluation fixtures,
not active runtime enforcement.

Change repository-scoped RepoWise startup from parent-workspace mode (`mcp ..`)
to exact-worktree single-repo mode (`mcp .`). A missing or stale local index
must cause RepoWise to be skipped in favor of Git, `rg`, and focused reads, not
silently routed to a sibling checkout.

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
- Review-correction provenance is limited to PR/commit/CI chronology: neither
  PR has a GitHub review object, so reviewer identity and same-session
  continuity are unverified. PR #42 also began before the workflow-v2 merge.
  These caveats do not block retirement because the correction behavior and
  final gates are directly evidenced, and the current workflow treats the
  legacy runtime as optional rollback rather than a safety dependency.

## Tool-routing evidence

- Serena 1.7.0 activated the exact task-worktree path with C++ and Python LSPs.
  A semantic lookup resolved `tools/agent/eval.py::safe_rel`; a reference query
  returned callers in `load_tasks`, `prepare`, and `grade`. Fresh worktrees do
  not have a C++ compilation database by default, so C++ definitions are
  available but caller/reference completeness is not established; keep the
  documented Git/`rg` fallback.
- RepoWise 0.42.0 resolved the previous `mcp ..` configuration to the parent
  workspace's default `sts_lightspeed` alias, which points at the primary
  checkout rather than the active task worktree. That index was 166 commits
  behind current `main`. After the configuration change, a mock-embedding,
  no-prose local index reported the exact task-worktree path and baseline
  `931d2b65`, with zero model tokens or cost. A broad `repowise why` workflow
  and safety-boundary query completed, but its results still classified the
  superseded Cline-era ADR-0008 as active. `repowise doctor` also reported 20
  stale pages plus SQL/vector/FTS drift. RepoWise routing is therefore fixed
  and advisory queries function, but index quality remains imperfect and its
  conclusions are not authoritative.

## Alternatives considered

- Delete the Python guardrail and tests with the runtime files: rejected because
  the current evaluator task and CI are non-Cline callers.
- Keep RepoWise in parent-workspace mode and require an alias check every time:
  rejected because a missing worktree alias silently selected another checkout.
- Add a Codex hook adapter: rejected as out of scope and still unsupported by
  protocol fixtures.

## Status and follow-up

Adopted. Historical Cline decision logs and ADRs remain unchanged. New
worktrees may create an ignored, no-prose RepoWise index when its broad advisory
queries are useful; otherwise RepoWise remains opt-in and the Git/`rg` fallback
is authoritative.
