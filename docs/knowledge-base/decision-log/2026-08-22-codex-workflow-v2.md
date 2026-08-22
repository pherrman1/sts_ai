# 2026-08-22 — Codex workflow v2 handoff boundary

Date: 2026-08-22
Session/task: Implement PR 1 of the Codex/ChatGPT workflow-v2 migration.

## Decision

Adopt the repo-grounded ChatGPT/Sol handoff as the accepted design plan when
it includes the baseline, goal/hypothesis, verified repository facts, required
behavior, non-goals, and verification criteria. Codex uses a bounded local
preflight, the draft PR carries an evidence packet to the reviewer, and the
reviewed SHA is frozen before expensive scientific runs. Minor corrections
continue the same session; conceptual redesigns or new hypotheses start a new
session.

## Rationale

This prevents accepted research and planning from being repeated locally while
preserving a contradiction check against current code. It also makes the
implementation/review/science boundaries explicit and auditable.

## Alternatives considered

- Repeat broad research in Codex for every handoff — rejected as redundant.
- Require a second broad self-review by the implementer — rejected in favor of
  independent review.
- Make RepoWise mandatory for routine tasks — rejected; it remains opt-in for
  broad architecture, dead-code, history, and risk work.
- Remove Cline compatibility or add Codex hook adapters — rejected during the
  pilot because no adapter protocol tests exist.

## Evidence

- `AGENTS.md` — authority, bounded workflow boundary, CI authority, and safety rules.
- `docs/knowledge-base/operations/agent-context-and-workflow.md` — bounded preflight and SHA-freeze procedure.
- `.agents/skills/research-experiment/SKILL.md` — separate external-handoff and Codex-originated paths.
- `.agents/skills/implementation-review/SKILL.md` — independent review and session routing.
- `.github/pull_request_template.md` — evidence-packet fields.
- `decisions/0010-codex-chatgpt-agent-workflow.md` — durable routing decision superseding ADR-0008.

## Status and follow-up

- Implemented as documentation/process policy; no gameplay, model, or hook changes.
- Validate through representative pilot tasks and CI; retain legacy Cline files until that evidence exists.
