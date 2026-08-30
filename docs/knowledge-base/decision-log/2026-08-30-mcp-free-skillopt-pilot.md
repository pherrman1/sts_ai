# 2026-08-30 — MCP-free Codex and SkillOpt pilot

Date: 2026-08-30
Session/task: Simplify the local agent harness and add a bounded SkillOpt-Sleep pilot.

## Decision

Use an MCP-free Codex implementation path backed by the tracked knowledge base.
Pilot SkillOpt-Sleep only on demand, targeting bounded proposals within the
implementation skill and requiring independent evaluator and human review
before normal PR-based adoption.

## Rationale

Git, `rg`, focused reads, diagnostics, and focused tests cover the bounded local
workflow. Separating tracked project truth from staged procedural proposals
keeps each change attributable and avoids a second memory system.

## Alternatives considered

- Retain repository MCP routing — rejected because it adds configuration and
  worktree routing without being required for the accepted workflow.
- Automate sleep cycles or adoption — rejected while SkillOpt is preview
  software and transcript-derived tasks require review.

## Evidence

- `tools/agent/eval.py::prepare` — clean-baseline skill overlay with hidden
  `evals/` removal preserved.
- `tests/agent/test_agent_eval.py::AgentEvalTests` — focused overlay, hash,
  prompt, baseline, hidden-boundary, and fail-closed checks.
- `docs/knowledge-base/operations/skillopt-sleep.md` — pinned pilot and adoption
  boundary.
- `decisions/0011-mcp-free-codex-skillopt-pilot.md` — durable decision.

## Status and follow-up

- Implemented as an on-demand integration pilot. No coding-quality improvement
  claim and no provider-backed optimization run.
