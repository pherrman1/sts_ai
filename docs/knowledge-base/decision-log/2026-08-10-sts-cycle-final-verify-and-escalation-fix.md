# 2026-08-10 — sts-cycle FINAL_VERIFY no-op fixed; escalation limit now rejects

Date: 2026-08-10
Session/task: Fix issues 77 and 78 in `.pi/extensions/sts-cycle/index.ts`
(implementation agent under the deterministic orchestrator)

## Decision

- **Issue 77 (FINAL_VERIFY no-op):** the final phase now runs the plan's
  `expensive` verification tier as the real final gate instead of
  `new Set()`:
  - `runVerification(plan, new Set(["expensive"]), ...)` replaces
    `new Set()`; `expensive_gate_enabled` is now `true`.
  - The phase writes `state.state = "FINAL_VERIFY"` before running, matching
    the state-machine comment.
  - If the plan defines no expensive checks, a `FINAL_VERIFY` progress
    warning reports that zero checks ran (gate is vacuous).
  - If `required_checks_passed` is false, the cycle returns `REJECTED`
    instead of silently accepting.
- **Issue 78 (escalation limit not a rejection):**
  - After `MAX_SOL=3` senior-review rounds, a latest verdict of `FIX`
    returns `REJECTED` (previously the cycle fell through to final
    verification and accepted). This matches the normal loop's
    `latestLuna.verdict === "FIX" → REJECTED` and the legacy
    `ai_cycle.py` `return 2` when `sol_round > MAX_SOL_REVIEW_ROUNDS`.
  - `shouldEscalate` now receives the real verification history:
    `verificationReports` accumulates every `runVerify` report from the
    normal loop (including failed ones, matching legacy
    `verification_reports(session_dir)`), replacing the hardcoded `[]`.
  - `activeVerifFile`/`activeFingerprint` are refreshed after each
    escalation fix + re-verification so the next senior-review round reads
    the current working tree.

## Rationale

- The final phase was a silent no-op: `required_checks_passed` is `.every()`
  over an empty list, so it was vacuously true and the `final-expensive`
  artifact recorded nothing. The artifact name, the header state-machine
  comment (`FINAL_VERIFY → ACCEPTED/REJECTED`), the architect prompt
  ("Expensive checks are final validation gates"), and the legacy rollback's
  `--allow-expensive` path (`costs_to_run={"expensive"}`) all agree that the
  expensive tier is the intended final gate.
- Safe to run automatically: `validatePlan` (called in `runArchitect`)
  already rejects plans whose checks violate the executable allowlist or the
  128-seed cap, so the final gate only ever executes pre-validated commands.
- **Inference:** with the gate active, plans with failing required expensive
  checks now reject instead of accepting, which closes a real
  false-acceptance hole in the orchestrator.
- `validateAllVerification`/`checkSeedCap` remain unused (pre-existing dead
  code noted in issue 77); wiring them was out of scope for this fix.

## Alternatives considered

- Keeping the empty set and only adding a warning comment (issue-77 option
  b): rejected because the expensive tier is genuinely defined by plans
  (architect prompt, existing `.ai/cycles/*/plan.json` evidence) and the
  documented workflow promises a final expensive gate.
- Adding a repair loop for failed final-expensive checks (legacy
  `MAX_EXPENSIVE_REPAIRS` behavior): rejected as out of scope; the minimal
  fix rejects on gate failure. The orchestrator can add repair rounds
  later if needed.

## Evidence

- `.pi/extensions/sts-cycle/index.ts::runCycle` — final phase, escalation
  loop, `verificationReports` accumulation, `shouldEscalate` input.
- `.pi/agents/architect.md` — "Expensive checks are final validation gates,
  not inner-loop debugging checks."
- `tools/ai_cycle.py` — `--allow-expensive` path runs
  `costs_to_run={"expensive"}`; `return 2` when
  `sol_round > MAX_SOL_REVIEW_ROUNDS`.
- Behavior check (Node type-stripped load + `runVerification`): empty set →
  vacuous pass (bug); `{"expensive"}` with a failing required expensive
  check → `required_checks_passed=false`; plan without expensive checks →
  zero checks run (warning path).

## Status and follow-up

- Issues 77 and 78 are fixed in code; they close with the fixing commit per
  the issues-directory convention.
- Follow-up candidate (not done): consider an explicit expensive-gate
  disable switch or repair rounds for the final gate, mirroring legacy
  `--allow-expensive`/`MAX_EXPENSIVE_REPAIRS`.
