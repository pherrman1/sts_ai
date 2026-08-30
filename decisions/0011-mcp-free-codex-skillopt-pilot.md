# ADR-0011: MCP-free Codex workflow and bounded SkillOpt-Sleep pilot

Date: 2026-08-30
Status: accepted
Supersedes: [ADR-0010](0010-codex-chatgpt-agent-workflow.md) only for active
tool routing. ADR-0010 and [ADR-0008](0008-guarded-cline-serena-repowise-routing.md)
remain historical records.

## Context

The tracked knowledge base already provides authoritative project memory, and
the coding-agent evaluator already tests repository outcomes in disposable
repositories with hidden deterministic graders. Active repository-tool routing
adds startup and worktree complexity that bounded Codex tasks do not require.

## Decision

ChatGPT/Sol owns research, architecture and experiment design, scientific
interpretation, orchestration, and independent review. Codex CLI remains the
local implementation, build/test, Git, and draft-PR harness. The normal Codex
path is MCP-free and uses Git, `rg`, focused reads, compiler diagnostics, and
focused tests. The tracked KB remains authoritative project truth.

The deliberately small, on-demand SkillOpt-Sleep pilot may propose bounded
procedural edits only within the implementation skill's `Learned guidance`
section. Its internal validation is followed by independent `sts_ai` evaluator
comparison and human review. SkillOpt may not automatically edit the KB or
adopt a skill proposal; accepted edits use the normal branch, draft PR, and CI
workflow.

## Rationale

This separates durable project knowledge from bounded procedural learning,
keeps the local harness inspectable, and lets hidden deterministic graders test
repository outcomes without adding orchestration or memory infrastructure.

## Alternatives considered

- Keep repository MCP routing — rejected because focused native tools cover the
  active workflow with less configuration and worktree risk.
- Add automatic harvesting or adoption — rejected because transcript-derived
  tasks and preview optimization require inspection and attributable review.
- Treat SkillOpt replay as final evidence — rejected because the repository
  evaluator independently tests scoped outcomes behind a hidden boundary.

## Consequences

Serena and RepoWise leave the active workflow. SkillOpt remains an external,
pinned, local-only staging tool. The pilot can prove integration and
no-regression comparison, but cannot by itself prove general quality gains.

## Affected files

- `AGENTS.md`; `.codex/config.toml`; `.agents/skills/`
- `docs/knowledge-base/operations/agent-context-and-workflow.md`
- `docs/knowledge-base/operations/skillopt-sleep.md`
- `tools/agent/eval.py`; `tests/agent/test_agent_eval.py`

## Evidence

- `tools/agent/eval.py` preserves the four-task hidden-grader boundary and adds
  only a clean-baseline skill overlay.
- `tools/agent/skillopt_sleep_config.example.json` bounds edits and disables
  memory evolution, retrieval, dream augmentation, and auto-adoption.
