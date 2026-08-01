# Issue 08: `OocCheckpointNet::load` reports success on truncated payloads

- **Status:** closed
- **Tier:** Critical
- **Last verified:** 2026-08-02
- **Source:** [`architecture/out-of-combat.md`](../architecture/out-of-combat.md), "Known limitations"; [`behavior/invariants.md`](../behavior/invariants.md)

## Symptom

`OocCheckpointNet::load` validates the header and dimensions but not every
payload read; a truncated file can still set `ok=true` and be used as an
action policy with partially initialized weights.

## Evidence

- `apps/ooc_checkpoint_net.h::OocCheckpointNet::load` (line 37): header
  validation without per-read checks, per the knowledge base.
- Same limitation recorded in `behavior/invariants.md` and
  `architecture/training-and-inference.md`.

## Why it matters

A corrupt or truncated checkpoint silently changes OOC action policy while
startup still prints success. Model-load verification is a documented
precondition for valid benchmarks; this breaks it for the checkpoint path.

## Candidate fix direction

Check every payload read and the final stream state; fail `load` and terminate
startup when reads are incomplete. Consider checksums (see related open
question in `out-of-combat.md`).

## Relevant code

- `apps/ooc_checkpoint_net.h::OocCheckpointNet::load`

## Resolution (2026-08-02)

Fixed: every payload read in `OocCheckpointNet::load` is now checked; truncated files fail load with a `[ooc-cp-net] truncated payload` error and the net is not used. Verified with a truncated checkpoint file.

## Closed by

*Fixed in the 2026-08-02 working tree (uncommitted); re-run the referenced focused checks before committing.*
