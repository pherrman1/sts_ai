# Java/native differential correctness

Last verified: 2026-09-28 against the native adapter and a bounded live capture.

## Purpose

The differential harness is a debug correctness boundary between a fixed-seed
vanilla Ironclad run and sts_lightspeed. It records stable MCP decision
boundaries as versioned JSONL and lets a native adapter compare state,
re-enumerated legal semantic actions, and the selected action without
resynchronizing random streams.

## Current implementation

tools/live_game_driver.py --differential-trace adapts the existing live
driver. The ordinary Silver/OOC provider and deterministic fallback policy are
unchanged. Run-control actions execute without requiring a native decision identity or
post-action canonical state. Their rows are excluded; each stable decision contains
normalized pre/post state, the complete captured legal candidate set, the
canonical selected identity, and the concrete MCP tool call.

Combat identities use the existing Silver fingerprint. OOC identities use the
provider's existing semanticKey; MAP retains its primitive x,y identity.
The trace records the OOC policy in header provenance and each OOC decision;
missing, unknown, or conflicting policy tags fail closed. MCTS retains its
semantic target candidates, while V4 uses its current-screen primitive
identities. Replay applies only the selected source primitive, leaving any
following selector to its own recorded decision. Each OOC decision also records
whether it uses a fresh policy score or the advisor's retained compound target.
Retained selectors enumerate all physical card occurrences; independently
scored MCTS selectors group equivalent copies just as the provider does.
An action without a native-replayable identity is recorded as
UNSUPPORTED_BOUNDARY instead of being guessed.

tools/differential_replay.py consumes a trace and a native JSONL adapter. The
adapter receives one decision row at a time and returns state, legalActions,
after, and optionally rng/postRng. The replay compares the pre-action state,
legal identity set, unique selected-action resolution, and post-action state,
stopping at the first difference. It reports STATE_DIVERGENCE,
RNG_CONSUMPTION_DIVERGENCE, LEGAL_ACTION_SET_DIVERGENCE,
RECORDED_ACTION_NOT_FOUND, RECORDED_ACTION_AMBIGUOUS,
UNSUPPORTED_BOUNDARY, or BOUNDED_PREFIX_EQUIVALENT. Replay requires one header,
one closing summary, consistent trace identities, increasing decision indices,
and a matching summary count and content hash. A trace with no decision records
fails with TRACE_OR_SCHEMA_ERROR (`no_decisions_captured`). An errored or
truncated capture cannot report equivalence; capture exceptions retain an
explicit failed boundary, including failures after a command executes.

Only a successfully bounded capture (`outcome=max_steps`) can return
BOUNDED_PREFIX_EQUIVALENT. It does not claim complete-run parity. Terminal
post-states currently have no qualified shared representation and are recorded
as `UNSUPPORTED_BOUNDARY: terminal_state_unqualified`, instead of comparing raw
MCP output with native canonical state. No full-run equivalent result is emitted.

Hidden RNG is separate from public observations. --capture-hidden-rng records
only an inspector-supplied debugRng object under the differential trace
record. tools/differential_rng.py verifies the installed vanilla
Random.counter, RandomXS128.seed0/seed1, and getState(int) contract. No RNG
values are imported into Silver, OOC observations, policy scoring, or native
execution.

Canonical OOC comparison excludes unobserved reward-pity counters, including
importer placeholders, and room fields the public importer does not populate. Details are restricted to the active screen, and sold
shop slots use a common unavailable representation. This is a public-state
projection, not equality of hidden counters or stale simulator storage.

## Verification

Focused checks:

    python3 -m unittest tests.test_differential_trace tests.test_live_game_driver -q
    ctest --test-dir <build-dir> -R differential_trace --output-on-failure

The trace test replays a native self-fixture and covers precise state diffs,
RNG-only diagnostics, missing and ambiguous identities, legal-set mismatch,
schema round-trip, hidden-RNG isolation, and vanilla-JAR preflight.

## Native replay and current boundary

`one_combat differentialreplay` now constructs an Ironclad run from the trace's
numeric seed and ascension, resolves recorded semantic actions uniquely, and
steps the current native simulator. Combat legal actions use native Silver's
root enumeration without running search. OOC source identities share the live
policy's identity contract. A trace must start at the initial Neow
boundary; replay does not reconstruct an arbitrary resumed run.

Set `STS_DIFFERENTIAL_TRACE=1` in the advisor environment to emit canonical
comparison states. It is off by default. Set `STS_DIFFERENTIAL_DEBUG_RNG=1` in
the game's environment when requesting hidden-RNG diagnostics. RNG tuples are
captured on the game thread with the immutable observation and retained when
its asynchronous advisor response arrives; they never enter the public
observation, its hash, or the advisor request.

The focused `native_differential_replay` check exercises native self-replay.
It establishes adapter plumbing, not Java/native equivalence. Live capture
must retain the first precise mismatch or unsupported boundary; do not change
simulator semantics or resynchronize RNG to make the harness pass.

The real Java fixture `tests/fixtures/differential/neow-intro-unsupported.jsonl`
records seed 0 / A0 stopping at the initial Neow Talk page with
`EVENT_PHASE_UNREPRESENTABLE:Neow:1`. Two native replays return the identical
unsupported result. There is one captured boundary and zero compared supported
decisions. This is evidence for precise failure reporting, not Java/native
parity or a complete-run pass. The adjacent receipt records executable hashes.

Knowledge impact: documents the native replay connection, opt-in comparison
state, and separation between capture/replay plumbing and gameplay parity.
