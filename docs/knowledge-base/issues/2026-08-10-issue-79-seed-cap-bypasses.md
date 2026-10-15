# Issue 79: Seed-cap bypasses in verification and safety hooks

- **Status:** open
- **Tier:** Medium
- **Date:** 2026-08-10
- **Source:** Investigator audit 2026-08-10, `.pi/extensions/sts-cycle/policy.ts`, `.pi/extensions/sts-safety.ts`

## Symptom

Multiple bypasses: (a) seed-taking modes not in the arg-index map
(`leafdiag`, `leafref`, `rollouttrace`, `frontiergen`) bypass seed-count
validation; (b) wrapper invocations (`python -c "subprocess.run([...])"`,
`$BIN bestbench ...`, renamed binaries) defeat both layers; (c) `sts-safety.ts`
off-by-one: reads `argv[relativeIdx+1]` (ascension) instead of `argv[3]`
(nseeds) for `check_replay.py`; (d) cap is per-check, not per-session.

## Evidence

- `policy.ts:575-593`: seed-count validation for mapped modes only.
- `policy.ts:755`: wrong argv index for check_replay.py.
- `sts-safety.ts:121`: same off-by-one.
- `verification.ts`: `validateAllVerification`/`checkSeedCap` have no call sites.

## Candidate fix directions

Add unmapped modes to arg-index map; add structural argv scanning for
`one_combat` invocations; fix argv[3] for check_replay.py; add per-session cap.

## Relevant code

- `.pi/extensions/sts-cycle/policy.ts`
- `.pi/extensions/sts-safety.ts`
