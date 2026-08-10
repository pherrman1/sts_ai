# Issue 80: sts-safety.ts protection gaps

- **Status:** open
- **Tier:** Medium
- **Date:** 2026-08-10
- **Source:** Investigator audit 2026-08-10, `.pi/extensions/sts-safety.ts`

## Symptom

Multiple gaps in the interactive safety hook: (a) protected-path list misses
`.pi/extensions/sts-cycle/{artifacts,git-state,types,verification}.ts`; (b)
bash `>` redirects bypass write/edit protection (no redirect-rule in
`DANGEROUS_BASH_PATTERNS`); (c) `git stash/rebase/merge/cherry-pick`, `pkill`,
`chmod` not blocked; (d) `rm -rf` pattern requires r+f in one token — `rm -r`
alone not blocked.

## Evidence

- `sts-safety.ts`: `isProtectedPath` exempts whole sts-cycle dir but only
  policy.ts/index.ts listed.
- `sts-safety.ts`: `DANGEROUS_BASH_PATTERNS` missing redirect patterns.
- `sts-safety.ts`: no git-dangerous or process-kill patterns.

## Candidate fix directions

Add missing protected paths, `>`/`>>` redirect patterns, `git stash/rebase`
etc., `pkill`/`chmod` patterns, and `rm -r` standalone detection.

## Relevant code

- `.pi/extensions/sts-safety.ts`
