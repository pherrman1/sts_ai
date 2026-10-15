# Issue 77: Final verification is a no-op in sts-cycle

- **Status:** open
- **Tier:** Medium
- **Date:** 2026-08-10
- **Source:** Investigator audit 2026-08-10, `.pi/extensions/sts-cycle/index.ts`, `verification.ts`

## Symptom

`runVerification(ctx.plan!, new Set(), ...)` in the final phase executes zero
checks. `required_checks_passed` is `.every()` over an empty list → always
`true`. Expensive checks are never run (`expensive_gate_enabled=false`).
`FINAL_VERIFY` exists only in the header comment.

## Evidence

- `index.ts`: `runVerification` called with `new Set()` (empty).
- `verification.ts`: `runVerification` iterates empty set → no checks.
- `verification.ts`: `validateAllVerification` and `checkSeedCap` have zero
  call sites (dead code).

## Candidate fix directions

Define the final verification checks and ensure they run, or rename the phase
to reflect actual behavior.

## Relevant code

- `.pi/extensions/sts-cycle/index.ts`
- `.pi/extensions/sts-cycle/verification.ts`
