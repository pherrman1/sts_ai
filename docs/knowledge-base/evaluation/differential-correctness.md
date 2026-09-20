# Java/native differential correctness

Last verified: 2026-09-21 against the differential trace implementation.

## Purpose

The differential harness is a debug correctness boundary between a fixed-seed
vanilla Ironclad run and sts_lightspeed. It records stable MCP decision
boundaries as versioned JSONL and lets a native adapter compare state,
re-enumerated legal semantic actions, and the selected action without
resynchronizing random streams.

## Current implementation

tools/live_game_driver.py --differential-trace adapts the existing live
driver. The ordinary Silver/OOC provider and deterministic fallback policy are
unchanged. Run-control rows are excluded; each stable decision contains
normalized pre/post state, the complete captured legal candidate set, the
canonical selected identity, and the concrete MCP tool call.

Combat identities use the existing Silver fingerprint. OOC identities use the
provider's existing semanticKey; MAP retains its primitive x,y identity. An
action without a native-replayable identity is recorded as
UNSUPPORTED_BOUNDARY instead of being guessed.

tools/differential_replay.py consumes a trace and a native JSONL adapter. The
adapter receives one decision row at a time and returns state, legalActions,
after, and optionally rng/postRng. The replay compares the pre-action state,
legal identity set, unique selected-action resolution, and post-action state,
stopping at the first difference. It reports STATE_DIVERGENCE,
RNG_CONSUMPTION_DIVERGENCE, LEGAL_ACTION_SET_DIVERGENCE,
RECORDED_ACTION_NOT_FOUND, RECORDED_ACTION_AMBIGUOUS,
UNSUPPORTED_BOUNDARY, or RUN_COMPLETE_EQUIVALENT.

Hidden RNG is separate from public observations. --capture-hidden-rng records
only an inspector-supplied debugRng object under the differential trace
record. tools/differential_rng.py verifies the installed vanilla
Random.counter, RandomXS128.seed0/seed1, and getState(int) contract. No RNG
values are imported into Silver, OOC observations, policy scoring, or native
execution.

## Verification

Focused checks:

    python3 -m unittest tests.test_differential_trace tests.test_live_game_driver -q
    ctest --test-dir <build-dir> -R differential_trace --output-on-failure

The trace test replays a native self-fixture and covers precise state diffs,
RNG-only diagnostics, missing and ambiguous identities, legal-set mismatch,
schema round-trip, hidden-RNG isolation, and vanilla-JAR preflight.

## Known limitation

The JSONL adapter is the native replay seam; the full one_combat seed
constructor/stepper is not yet connected to this first instrumentation slice.
Until that adapter is supplied by a native replay executable, a real live
trace cannot be claimed equivalent to the simulator. This is an explicit
implementation gap, not simulator-correctness evidence.

Knowledge impact: this page documents the new debug schema and current replay
boundary; no gameplay or policy behavior changed.
