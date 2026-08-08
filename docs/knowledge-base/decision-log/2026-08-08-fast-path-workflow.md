# Fast-path workflow for trivial non-behavioral tasks

- **Date**: 2026-08-08
- **Context**: AI cycle orchestration optimisation. Implemented per
  `AI_CYCLE_FAST_PATH_HANDOFF.md`.

## Decision

Added a deterministic fast-path classification and workflow to
`tools/ai_cycle.py` so that genuinely trivial / non-behavioral tasks skip the
architect and Pro escalation and run a reduced implementer → cheap
verification → Flash reviewer flow.

## Rationale

The full architect → implementer → verification → reviewer → escalation
cycle is necessary for semantic and research-sensitive changes but is
expensive (API cost + latency) for wording, typo, comment, and documentation
edits. A narrow deterministic classification rule, checked before any LLM
call, plus a post-implementation diff confirmation that the change really is
comment/docstring/whitespace-only, provides a safe fast path that never
weakens the existing safety rules.

- **Inference**: The existing reviewer still performs semantic review; the
  fast path only removes the architect and path-based escalation triggers,
  not the review itself.

## Alternatives considered

- **Let the LLM decide**: rejected because the orchestrator must be
  deterministic and an LLM could misclassify a semantic task as trivial.
- **No fast path at all**: rejected because trivial non-behavioral tasks
  are common (typo fixes, comment improvements, README edits) and wasting
  Pro architect + escalation calls on them adds latency and cost without
  benefit.

## Implementation

- `classify_fast_path_task()` — deterministic keyword-based classification;
  no LLM call.
- `create_trivial_plan()` — minimal plan compatible with existing
  `validate_plan` and implementer/reviewer interfaces.
- `confirm_trivial_diff()` — parses `git diff` and checks every changed
  line in source files is a comment/docstring/whitespace; doc files allow
  normal prose; config/build/schema/protected paths reject immediately.
- `run_fast_path_workflow()` — implementer → diff confirmation → cheap
  verification → Flash reviewer (1 round on PASS, 1 fix round on FIX).
- `should_escalate_to_sol(…, confirmed_trivial=False)` — when
  `confirmed_trivial=True`, suppresses path-name and plan-term escalation
  triggers but retains all hard safety rules (verification failure, CRITICAL
  review issues, reviewer uncertainty HIGH, etc.).
- `main()` branches on `classify_fast_path_task()` before the architect
  call; prints `Task class: TRIVIAL_CANDIDATE` or `NORMAL`.

## Evidence

- `tools/ai_cycle.py`: `classify_fast_path_task`, `create_trivial_plan`,
  `confirm_trivial_diff`, `persist_fast_path_classification`,
  `persist_diff_confirmation`, `run_fast_path_workflow`,
  `should_escalate_to_sol(confirmed_trivial=…)`, `FAST_PATH_MAX_FILES`,
  `FAST_PATH_MAX_LINES`.
- `tools/test_ai_cycle.py`:
  `FastPathClassificationTests` (12 tests),
  `FastPathDiffConfirmationTests` (14 tests),
  `FastPathOrchestrationTests` (15 tests). 126 total tests pass.
- `docs/knowledge-base/operations/ai-cycle.md` — updated with fast-path
  section.
- `docs/knowledge-base/decision-log/2026-08-08-fast-path-workflow.md` —
  this entry.

## Status

Implemented. OpenCode rollback path, hard seed cap (128),
verification allowlisting, clean-tree check, and reviewer behaviour are all
unchanged for non-trivial tasks.
