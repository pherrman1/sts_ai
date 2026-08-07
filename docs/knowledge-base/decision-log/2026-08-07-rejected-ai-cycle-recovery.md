# 2026-08-07 — Rejected AI cycle recovery

Date: 2026-08-07
Session/task: Turn semantic-review exhaustion into a bounded manual-intervention checkpoint.

## Decision

Keep the ordinary Luna review limit at two. A second Luna FIX stops before
another implementer call, prints the latest ELI5 and a `--continue-rejected`
command, and preserves the existing task and architecture plan. That resume
mode runs one Sol adjudication and permits at most one durable DeepSeek
recovery-fix attempt, followed by one cheap check, one Luna review, one final
Sol audit, and the configured final gate.

## Rationale

Repeated cheap-review-fix loops can oscillate and spend API/local compute
without resolving whether the implementation or the review is wrong. Sol is
used here as an adjudicator rather than silently expanding the normal limit.
Attempt markers and candidate fingerprints ensure interruption cannot replenish
the one-fix or paid-review budget.

## Alternatives considered

- Raise the ordinary review limit — rejected because it permits unbounded oscillation rather than adjudicating disagreement.
- Restart the Architect — rejected because implementation-level objections do not invalidate the existing plan.
- Automatically fix a final Sol FIX — rejected because that would create another recovery cycle.

## Evidence

- `tools/ai_cycle.py` + `reject_after_semantic_limit`, `continue_rejected_workflow`, and `RejectedRecoveryExhausted`.
- `tools/test_ai_cycle.py` + `RejectedRecoveryTests`.
- `.opencode/prompts/reviewer-sol.md` + escalation/adjudication mode distinction.

## Status and follow-up

- Implemented. A final Sol FIX or failed post-fix gate returns control to manual intervention or a deliberate architecture revision.

## Addendum (same day)

- A token outage interrupted a paid recovery review and consumed the durable single-attempt budget (`recovery-exhausted.json`). Added explicit manual escape hatch `--retry-recovery` (`--resume SESSION --continue-rejected --retry-recovery`): clears only incomplete attempt markers (`recovery-*-candidate.json`, incomplete logs, interrupted fix marker) and preserves completed adjudications, fixes, and verification reports. The durable bound remains for unattended runs; retrying is a deliberate user decision.
