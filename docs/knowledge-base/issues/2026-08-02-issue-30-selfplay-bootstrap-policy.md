# Issue 30: Self-play bootstrap policy for stale `state.env` is undefined

- **Status:** closed
- **Tier:** Low
- **Last verified:** 2026-08-02
- **Source:** [`operations/selfplay-loop.md`](../operations/selfplay-loop.md), "Open questions"

## Symptom

The loop's first-run branch is skipped when `selfplay/state.env` exists, but no
explicit policy defines what to do when `state.env` exists while current models
and directories do not (the current checkout's situation; see Issue 11).

## Evidence

- `selfplay/loop.sh`: first-run copy branch guarded by absence of `state.env`.
- `selfplay-loop.md` "Open questions": "What exact bootstrap policy should
  apply when `state.env` exists but current models/directories do not?"

## Why it matters

Without a defined repair path, every stale snapshot requires manual
intervention, and the loop cannot be restarted reproducibly after a partial
checkout or cleanup.

## Candidate fix direction

Define an explicit bootstrap state machine: fresh start, resume, and repair
(stale `state.env`) branches with validation of the directories each branch
requires.

## Relevant code

- `selfplay/loop.sh`, `selfplay/state.env`

## Resolution (2026-08-02)

Fixed: three-branch bootstrap state machine (fresh / resume / repair) in `selfplay/loop.sh`; repair cases refuse with instructions rather than silently skipping the first-run branch.

## Closed by

*Fixed in the 2026-08-02 working tree (uncommitted); re-run the referenced focused checks before committing.*
