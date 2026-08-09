# Decision: keep parsing Pi stdout after the retention cap (2026-08-09)

## Decision

`runPiChild` now separates JSONL parsing from event-history retention. It
always drains and parses child stdout, forwards every event to live progress,
and retains lifecycle/completed-message events even after dropping excess
streaming deltas. Idle detection starts when the process starts. Pi-native
cycle state is persisted as `ARCHITECT` before the architect call.

## Rationale

The reported DeepSeek API stall was not supported by reproduction. An exact
architect invocation continued emitting thinking deltas and tool events for
the full 210-second observation and exceeded 1 MiB of JSONL. The runner's old
`outputBytes >= MAX_OUTPUT` branch then stopped processing all stdout, so live
progress froze and later `message_end`/`agent_end` events could be lost. This
local truncation bug is sufficient to explain the symptom without assuming an
API stall.

## Alternatives considered

- Idle timeout only: retained as defense in depth, but it cannot diagnose an
  actively streaming model and previously did not cover pre-first-event stalls.
- Switching DeepSeek models: rejected; both Pro and Flash reproduced long,
  continuously streaming reasoning.
- Raising the 1 MiB cap: rejected because it postpones the same correctness
  failure and weakens the memory bound.

## Evidence

- `.pi/extensions/subagent/runner.ts::runPiChild`: old stdout callback returned
  permanently after `MAX_OUTPUT`; parsing and bounded retention are now
  separate.
- `.pi/extensions/subagent/runner.test.mjs`: emits more than 1 MiB of delta
  events followed by final `message_end`/`agent_end`; the final response and
  all live callbacks are observed.
- `.pi/extensions/sts-cycle/index.ts::runArchitect`: persists the active stage
  before child invocation.

## Status

Implemented and covered by a focused regression test. The upstream model can
still take a long time while actively generating; role hard timeouts bound that
case, while the UI now continues to show elapsed time and character progress.
