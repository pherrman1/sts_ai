# Issue 18: `bestBench` banner/comment describe an older stack

- **Status:** closed
- **Tier:** Medium
- **Last verified:** 2026-08-02
- **Source:** [`architecture/out-of-combat.md`](../architecture/out-of-combat.md), "Known limitations"; [`evaluation/benchmark-protocol.md`](../evaluation/benchmark-protocol.md)

## Symptom

The `BEST stack` banner and adjacent source comment in `bestBench` still
describe server-backed cards, an old skip default, and optional `restV`, while
startup currently defaults to native OOC, skip `-0.5`, and the default
`g_restWin=true` win-rest layer. The banner is not complete configuration
provenance.

## Evidence

- `apps/one_combat.cpp::bestBench` (line 2551): banner text mentions
  "shop-V" and optional "rest-V" only.
- `apps/one_combat.cpp::runFullRunOOC`: `g_restWin` branch is the default win
  rest layer (`g_restWin = true`, line 1452).
- `benchmark-protocol.md`: "The `bestBench` source comment and its `BEST stack`
  banner are stale and incomplete."

## Why it matters

Anyone reading benchmark output (or pasting it into the ledger) may record a
configuration that was not executed, corrupting provenance.

## Candidate fix direction

Replace the banner with a configuration line emitted from the parsed flags and
load messages (revision, model paths, `STS_*` flags, threads), per the protocol
checklist.

## Relevant code

- `apps/one_combat.cpp::bestBench`, `main`
- `evaluation/benchmark-protocol.md`

## Resolution (2026-08-02)

Fixed: `bestBench` banner and adjacent comment are emitted from parsed flags/load messages (skip threshold, rest/win layer, shop-V, path mode, native OOC, searcher, threads, model paths). Verified in `bestbench` output.

## Closed by

*Fixed in the 2026-08-02 working tree (uncommitted); re-run the referenced focused checks before committing.*
