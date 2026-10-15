# Issue 78: Escalation limit is not a rejection condition

- **Status:** open
- **Tier:** Medium
- **Date:** 2026-08-10
- **Source:** Investigator audit 2026-08-10, `.pi/extensions/sts-cycle/index.ts`

## Symptom

After `MAX_SOL=3` senior (reviewer-pro) FIX rounds, the cycle proceeds to
final verification and `accepted(ctx)` — no REJECTED branch. Inconsistent
with the normal loop's `latestLuna.verdict === "FIX" → REJECTED`.

Additionally: `activeVerifFile`/`activeFingerprint` are not refreshed after
escalation fixes, so the senior reviewer reads stale artifacts.
`verificationHistory` is hardcoded `[]` in `shouldEscalate`.

## Evidence

- `index.ts`: escalation loop → accepted after MAX_SOL.
- `index.ts`: `verificationHistory: []` hardcoded.
- `policy.ts`: `MAX_SOL_REVIEW_ROUNDS` semantics unclear.

## Candidate fix directions

Add REJECTED path after MAX_SOL FIX rounds. Refresh artifacts before senior
review. Pass actual verificationHistory.

## Relevant code

- `.pi/extensions/sts-cycle/index.ts`
