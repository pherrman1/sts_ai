# Issue 20: `runtrace` is not a mirror of `runFullRunOOC`

- **Status:** closed
- **Tier:** Medium
- **Last verified:** 2026-08-02
- **Source:** [`architecture/out-of-combat.md`](../architecture/out-of-combat.md), "Known limitations"; [`operations/build-and-debugging.md`](../operations/build-and-debugging.md)

## Symptom

`runTraceRun` logs but does not use some event/treasure scores, omits some
fallthrough policy layers, and its draft logger calls the server-only `M`
endpoint (which can retry when no server is present). It is a debugger, not a
baseline reproduction of `runFullRunOOC`.

## Evidence

- `apps/one_combat.cpp::runTraceRun` (line 2360), `tr_logDraft` (line 2247).
- `out-of-combat.md`: "`runtrace` is not a wrapper around `runFullRunOOC`".
- `build-and-debugging.md`: "Treat it as a debugger, not baseline
  reproduction."

## Why it matters

Traces are used to diagnose policy decisions; a divergence from the executed
policy can make a trace mislead about what the run actually decided, and the
server dependency adds an unannounced failure mode.

## Candidate fix direction

Either make `runTraceRun` share `runFullRunOOC`'s policy execution or clearly
mark traced decisions as diagnostic; guard `tr_logDraft` against missing server.

## Relevant code

- `apps/one_combat.cpp::runTraceRun`, `tr_logDraft`, `runFullRunOOC`

## Resolution (2026-08-02)

Fixed: `tr_logDraft` is guarded by `vConnect()` so server-less traces skip draft logging without retry; `runTraceRun` prints a prominent diagnostic header stating it does not exactly reproduce `runFullRunOOC`. It remains a debugger, not a baseline mirror.

## Closed by

*Fixed in the 2026-08-02 working tree (uncommitted); re-run the referenced focused checks before committing.*
