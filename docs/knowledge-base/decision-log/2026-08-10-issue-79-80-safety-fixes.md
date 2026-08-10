# 2026-08-10 — issues 79, 80 fixed (seed-cap bypasses, sts-safety protection gaps)

Date: 2026-08-10
Session/task: Fix issues 79 and 80 in `.pi/extensions/sts-cycle/policy.ts` and
`.pi/extensions/sts-safety.ts` (implementation agent under the deterministic
orchestrator)

## Decision

- **Issue 79(a) — unmapped seed-taking modes:** `leafdiag` (nSeeds @ argv[2]),
  `leafref` (nSeeds @ argv[5]), `rollouttrace` (nSeeds @ argv[4]) and
  `frontiergen` (nSeeds @ argv[2]) were added to
  `KNOWN_ONE_COMBAT_SEED_SWEEP_ARG_INDEX` in `policy.ts`, so both
  `knownSeedSweepArgIndex`/`validateSeedCount` and the live interactive hook
  (`sts-safety.ts::oversizedSeedSweep`) validate their seed counts against
  `MAX_AUTOMATED_SEEDS = 128`. The argv positions were verified against the
  `one_combat.cpp` mode dispatch before adding.
- **Issue 79(b) — check_replay.py off-by-one:** `sts-safety.ts`
  `oversizedSeedSweep` read the seed token at
  `tokens[scriptIndex + relativeSeedIndex]` (argv[4] = ascension); map values
  are absolute argv indices (script expected at argv[1]), so the token is at
  `tokens[scriptIndex + relativeSeedIndex - 1]` (argv[3] = nseeds, confirmed
  from `check_replay.py` `main(argv)` with `argv = sys.argv[1:]`:
  `sims, nseeds, asc = argv[0], argv[1], argv[2]`).
- **Issue 80(a) — protected-path gaps:** added
  `.pi/extensions/sts-cycle/{artifacts,git-state,types,verification}.ts` to
  `PROTECTED_PATHS` in `sts-safety.ts` (policy.ts and index.ts were already
  listed).
- **Issue 80(b) — bash redirect bypass:** added
  `REDIRECT_TO_PROTECTED_PATTERN` (derived from `PROTECTED_PATHS`, matching
  `>`/`>>` optionally through leading directories) to
  `DANGEROUS_BASH_PATTERNS`, closing the write/edit-tool bypass where a bash
  `>`/`>>` writes a protected path.
- **Issue 80(c) — `rm -r` without `-f`:** added
  `/\brm\s+-[A-Za-z]*r[A-Za-z]*\b/i` to `DANGEROUS_BASH_PATTERNS` (the old
  pattern required `r` and `f` in one flag token, or `--recursive`).

## Rationale

- The 128-seed cap and protected-path write protection are the two layers the
  investigator audit found bypassable; both are cheap to close in the single
  authoritative definition (`policy.ts` map) and the live interactive hook
  (`sts-safety.ts`). Modes were added only after matching their argv layout in
  `apps/one_combat.cpp` (executed code is authoritative).
- Redirect rules are derived from `PROTECTED_PATHS` so a future protected-path
  addition cannot silently reopen the redirect bypass.

## Alternatives considered

- **Structural argv scanning for `one_combat` wrappers** (`$BIN bestbench`,
  `python -c "subprocess.run([...])"`): noted in issue 79 as a fix direction
  but out of scope for this change; the interactive hook still blocks the
  underlying oversized command when the inner argv is spelled out.
- **Fixing `policy.ts::validateSeedCount`'s identical off-by-one:** it has no
  live call sites (`verification.ts::checkSeedCap` is uncalled), so it was
  left unchanged to keep the change minimal; flagged as an open concern.

## Evidence

- `apps/one_combat.cpp`: `leafdiag` `nSeeds = argv[2]`; `leafref`
  `nSeedsRef = argv[5]`; `rollouttrace` `nSeedsRef = argv[4]`; `frontiergen`
  `nSeeds = argv[2]`.
- `check_replay.py`: `sims, nseeds, asc = argv[0], argv[1], argv[2]` on
  `sys.argv[1:]` ⇒ full-command argv[3] is nseeds.
- 45 focused assertions run against the actual file contents under Node 24
  TS type-stripping (map entries, seed-cap flags, redirect/rm patterns,
  protected-path checks) all passed.

## Status

- Applied. Issues 79 and 80 remain open as audit records (no convention flips
  status to closed).
