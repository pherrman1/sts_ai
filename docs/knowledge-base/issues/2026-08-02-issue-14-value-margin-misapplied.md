# Issue 14: `VALUE_MARGIN=-0.5` applies to every value candidate

- **Status:** closed
- **Tier:** High
- **Last verified:** 2026-08-02
- **Source:** [`operations/selfplay-loop.md`](../operations/selfplay-loop.md), "Known limitations"; [`behavior/invariants.md`](../behavior/invariants.md)

## Symptom

The checked-in `VALUE_MARGIN=-0.5` is applied to every value candidate even
though comments describe it as latency-specific; code does not enforce a
latency condition. A sufficiently precise zero-delta value candidate can
qualify under the negative margin.

## Evidence

- `selfplay/loop.sh::gate_stats` and the value gate call site: `VALUE_MARGIN`
  is used unconditionally.
- `invariants.md`: "`VALUE_MARGIN=-0.5` is not programmatically restricted to
  latency candidates."
- `benchmark-protocol.md` "Gate protocol": equality at the margin does not
  promote, but a negative margin means a zero-delta candidate can qualify.

## Why it matters

Promotion rules are the safety contract of self-play. A candidate that should
be inconclusive (or latency-exempt) can be promoted, changing the deployed
model set on unintended evidence.

## Candidate fix direction

Make `VALUE_MARGIN` conditional on measured latency evidence, or separate the
quality margin from the latency allowance; assert margin sign by arm.

## Relevant code

- `selfplay/loop.sh::gate_stats`, value gate block
- `selfplay/config.env`

## Resolution (2026-08-02)

Fixed: a negative `VALUE_MARGIN` is honored only when `VALUE_MARGIN_LATENCY=1`; otherwise it is clamped to `PROMOTE_MARGIN` with a warning. The checked-in `config.env` snapshot predates the latency gate.

## Closed by

*Fixed in the 2026-08-02 working tree (uncommitted); re-run the referenced focused checks before committing.*
