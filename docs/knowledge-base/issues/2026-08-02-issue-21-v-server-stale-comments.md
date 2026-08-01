# Issue 21: `v_server.py` comments describe an old layout

- **Status:** closed
- **Tier:** Medium
- **Last verified:** 2026-08-02
- **Source:** [`architecture/out-of-combat.md`](../architecture/out-of-combat.md), "Known limitations"; [`architecture/training-and-inference.md`](../architecture/training-and-inference.md)

## Symptom

`v_server.py` contains comments describing older 392/372-value layouts even
though its implemented `RAW` layout is 1,017 values. The comments are stale
documentation of a schema that is a model interface.

## Evidence

- `v_server.py::RAW` implements 1,017 values; header comments describe older
  layouts (`out-of-combat.md`).

## Why it matters

Schema comments are a documented trap: consumers who trust them rather than
`vFeatCsv`/`RAW` will misalign features. This is a standing producer/consumer
contract hazard.

## Candidate fix direction

Update the comments to the implemented 1,017 layout and link to
`apps/one_combat.cpp::vFeatCsv` as the schema owner; optionally add an
automated width assertion.

## Relevant code

- `v_server.py::RAW`
- `apps/one_combat.cpp::vFeatCsv`

## Resolution (2026-08-02)

Fixed: `v_server.py` comments now document the implemented 1,017-value `RAW` layout with `apps/one_combat.cpp::vFeatCsv` as the schema owner.

## Closed by

*Fixed in the 2026-08-02 working tree (uncommitted); re-run the referenced focused checks before committing.*
