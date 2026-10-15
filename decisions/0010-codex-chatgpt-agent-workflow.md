# ADR-0010: ChatGPT/Sol handoff and bounded Codex workflow

Date: 2026-08-22
Status: accepted
Supersedes: [ADR-0008](0008-guarded-cline-serena-repowise-routing.md) for
harness and routing policy; ADR-0008 remains historical and is not rewritten.

## Context

The repository has adopted Codex CLI as the interactive implementation harness
while retaining Cline files during the pilot. The previous ADR routed work by
harness and tool, but did not define the handoff boundary, bounded preflight,
review evidence, or the transition from implementation review to expensive
scientific execution.

## Decision

Use a repo-grounded ChatGPT/Sol handoff as the accepted design plan when it
contains the baseline, goal/hypothesis, verified repository facts, required
behavior, non-goals, and verification criteria. Codex performs a bounded local
preflight and does not restart broad research or planning unless local evidence
materially contradicts that handoff.

The draft PR is the Codex-to-reviewer handoff and must contain an evidence
packet. Minor review corrections continue the same Codex session; conceptual
redesigns, new hypotheses, or changed success criteria start a new session.
After repeated failures or conceptual ambiguity, the agent stops and reports
the blocker. After implementation review passes, the reviewed SHA is frozen
before expensive scientific runs.

Serena is optional and high-leverage for semantic navigation. RepoWise is
opt-in for broad architecture, dead-code, history, or risk work, not routine
tasks. CI remains authoritative for full-repository verification; local Codex
runs the cheapest proving checks. Legacy Cline files remain during the pilot,
and no Codex hook adapter is claimed or added by this decision.

## Rationale

This separates research/design authority from local implementation work,
reduces repeated context gathering, and makes the reviewed commit an explicit
scientific reproducibility boundary.

## Alternatives considered

- Restart broad research in every Codex session — rejected because it repeats
  accepted work and obscures the actual local contradiction, if any.
- Require the implementer to perform a second broad self-review — rejected;
  independent review is more useful and cheaper.
- Make RepoWise mandatory for routine work — rejected because targeted reads
  and maintained documentation are sufficient for bounded tasks.
- Remove Cline compatibility or add hook adapters now — rejected until the
  pilot has representative-task evidence and protocol tests.

## Consequences

Handoffs and draft PRs must carry enough evidence for an independent reviewer.
Agents must distinguish implementation failure from scientific null or
inconclusive results. A missing or contradictory handoff can block execution,
but the agent should report that blocker rather than inventing a new design.

## Affected files

- `AGENTS.md`
- `docs/knowledge-base/operations/agent-context-and-workflow.md`
- `.agents/skills/research-experiment/SKILL.md`
- `.agents/skills/implementation-review/SKILL.md`
- `.github/pull_request_template.md`

## Evidence

- `AGENTS.md` — defines authority hierarchy, CI authority, seed guard, and
  workflow-v2 boundary.
- `docs/knowledge-base/operations/agent-context-and-workflow.md` — defines
  bounded preflight, evidence packet, session routing, and SHA freeze.
