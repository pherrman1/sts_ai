# Issue 15: Repeated gate looks are not multiplicity-adjusted

- **Status:** closed
- **Tier:** High
- **Last verified:** 2026-08-02
- **Source:** [`operations/selfplay-loop.md`](../operations/selfplay-loop.md), "Known limitations"; [`evaluation/benchmark-protocol.md`](../evaluation/benchmark-protocol.md)

## Symptom

The self-play gate evaluates `mean ± GATE_Z*SE` at adaptive looks (two-iteration
cadence with a 500-seed adaptive cap) without any sequential multiplicity
correction. `GATE_Z=2.58` is called "safe" in a comment, but it is not a proven
99% sequential guarantee.

## Evidence

- `selfplay/loop.sh`: repeated `gate_stats` calls across iterations on
  accumulating data.
- `benchmark-protocol.md` "Gate protocol": "The repeated looks are not
  multiplicity-adjusted, so `GATE_Z=2.58` is not a proven 99% sequential
  guarantee."
- `invariants.md`: nominal normal-theory intervals without a sequential
  correction.

## Why it matters

Adaptive stopping without correction inflates the false-promotion rate over
the run of looks; candidates that are actually equal to baseline can cross the
interval under repeated inspection.

## Candidate fix direction

Use a sequentially valid method (e.g., alpha-spending / O'Brien-Fleming style
boundaries) or bound the number of looks; record the chosen correction in
`EXPERIMENTS.md` and the protocol page.

## Relevant code

- `selfplay/loop.sh::gate_stats`, adaptive look loop
- `evaluation/benchmark-protocol.md` "Gate protocol"

## Resolution (2026-08-02)

Fixed: promotion is allowed only on the final hard-cap gate look; earlier promote signals are advisory. `GATE_LOOKS` is recorded in gate state. Cost: promotable candidates always pay the full seed budget.

## Closed by

*Fixed in the 2026-08-02 working tree (uncommitted); re-run the referenced focused checks before committing.*
