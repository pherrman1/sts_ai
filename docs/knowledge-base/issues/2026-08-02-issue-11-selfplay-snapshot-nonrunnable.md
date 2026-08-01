# Issue 11: Checked-in self-play snapshot cannot run

- **Status:** closed
- **Tier:** High
- **Last verified:** 2026-08-02
- **Source:** [`operations/selfplay-loop.md`](../operations/selfplay-loop.md), "Blocking discrepancies"

## Symptom

`selfplay/state.env` records iteration 10, seed offset 1008002, and 8002 runs,
but this checkout lacks `selfplay/current/`, the core buffer/candidate/model/
log/gate directories, `./one_combat.elf`, and the initialization sources
`build/v_combat_fair_trees.txt` and `build/policy_fair_trees_c.txt`. Because
`state.env` exists, the first-run copy branch is skipped, so the snapshot cannot
resume without a deliberate bootstrap repair.

## Evidence

- `selfplay/loop.sh`: first-run branch is skipped when `state.env` exists;
  gates invoke `./one_combat.elf` while CMake produces `build/one_combat`.
- `selfplay/state.env` present; `selfplay/current/` absent (checked-in tree).

## Why it matters

A stated resumable self-play loop is the deployment mechanism for learned
promotion. The checked-in state is neither runnable bootstrap nor valid
resumption, so any claim that the loop is "running" or resumable is false.

## Candidate fix direction

Define a bootstrap repair path (e.g., a `--reset`-style option or explicit
"state.env present but current/ absent" handling) and a supported binary
location (`build/one_combat` or a defined copy step).

## Relevant code

- `selfplay/loop.sh`, `selfplay/state.env`, `selfplay/config.env`
- `CMakeLists.txt` (no `one_combat.elf` target)

## Resolution (2026-08-02)

Fixed: `selfplay/loop.sh` now defaults `BIN` to `build/one_combat` (overridable via `ONE_COMBAT_BIN`/`STS_BIN`), preflights the binary, and the bootstrap state machine refuses repair cases with diagnostics instead of silently skipping the copy branch.

## Closed by

*Fixed in the 2026-08-02 working tree (uncommitted); re-run the referenced focused checks before committing.*
