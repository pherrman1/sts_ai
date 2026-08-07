# 2026-08-07 — Risk-gated multi-model AI cycle

Date: 2026-08-07
Session/task: Make the repository AI cycle cheaper by default while escalating semantic risk and deferring expensive checks.

## Decision

Use Luna-high for architecture and ordinary semantic review, DeepSeek V4 Flash
for edits, and Sol-medium only after deterministic escalation. Run only cheap
verification before each semantic review; run enabled expensive checks once as
the final gate. Cap every declared automated game-seed sweep at 128 seeds and
store both structured and ELI5 review artifacts.

## Rationale

The orchestrator, rather than the cheaper reviewer, owns escalation. Candidate
fingerprints make paid Luna/Sol reviews and successful final gates reusable on
resume while invalidating them after code changes. **Inference:** this should
reduce API and local compute cost for low-risk tasks without allowing tests or
the first review to be the sole authority over research-sensitive changes.

## Alternatives considered

- Run Sol for every task — rejected because ordinary work does not justify the API cost.
- Run expensive checks in each repair loop — rejected because failures must first return through cheap checks and semantic review.
- Infer seed counts from every numeric argument — rejected because simulation counts, offsets, and timeouts may legitimately exceed 128.

## Evidence

- `tools/ai_cycle.py` + `complete_candidate_workflow`, `should_escalate_to_sol`, `run_verification`, and `validate_plan`.
- `tools/test_ai_cycle.py` + focused validation, phase-isolation, escalation, ELI5, and resume tests.
- `opencode.json` + `architect`, `reviewer`, and `reviewer_sol` agent configuration.

## Status and follow-up

- Implemented. Broader-than-128 scientific sweeps remain manual follow-ups outside the automated workflow.
