# §462 — One A20 MAP leaf: inherited-memory replay PASS

The parent and isolated child returned exactly **0.6771143269743937** from the
same pre-evaluation snapshot, with identical endpoint, work counts and complete
final planner RNG. The original leaf state/path stayed unchanged. This is a
deterministic replay gate for #507, not a target-stability or compression result.

## Design and custody

- Historical seed **87000000**, A20, real decision **0**, sampled ordinal
  **1025**, original model state ID **1025**, initially nonterminal MAP.
  No replacement leaf, extra seed, independent future or retry was allowed.
- Reviewed producer: `1125d07db5f5d6597759af291d2fdc4c6981f066`.
  Release binary SHA256:
  `abd6f14d42668cc67ebda3604687300feaef36e234fb38812db96f6bf8ef1bed`.
- Same PR #524 / §458 teacher as §461: data commit
  `c507cebb000cbb308e9ad833721c85ea357af0f1`, A20 Lizard-capable FAST4L/STD2,
  4096 OOC simulations, widening K=4/alpha=.75, three CTM combats, V4
  prior/continuation and native public X2-B bootstrap. The selected CTM remains
  **NOT_QUALIFIED**. Model hashes and complete environment are in
  [manifest.json](manifest.json).
- The previous off-arm environment was retained, except for removing the
  decision/MCTS/profile traces and adding the new source declaration and
  exclusive capture path. Effective policy and the complete STS environment
  were checked against those exact expectations.
- Linux single OS thread, verified at the fork boundary. Fork happened before
  either evaluation, preserving the actual model, state ID, path, opaque
  callbacks, policy state, caches and RNG. The child closed unrelated file
  descriptors, evaluated once and exited; the parent then performed its one
  scheduled evaluation and stopped before selecting/executing a real action.
- Limits: parent 20 plus child 10 CPU seconds, 60 wall seconds total; child
  transport bounded to 64 KiB and 10 wall seconds. The [protocol](PROTOCOL.md),
  runner, analyzer, source/binary custody and historical reference were frozen
  in [freeze.json](freeze.json) and independently reviewed before launch.

## Results

| Field | Parent | Child |
|---|---:|---:|
| Value | 0.6771143269743937 | 0.6771143269743937 |
| Terminal | false | false |
| Endpoint floor | 5 | 5 |
| Endpoint HP / max HP | 66 / 75 | 66 / 75 |
| Resolved CTM combats | 3 | 3 |
| Projection steps | 21 | 21 |
| Source state/path unchanged | true | true |

Full final planner RNG states matched exactly. The new initial/final RNG,
state ID and recorded evaluation fields also match the historical §461 sample;
that cross-build comparison is descriptive and was not an additional pass gate.

The process returned zero after **0.907232 CPU seconds** and **0.966319 wall
seconds**, below both limits. The capture contains exactly a provenance header
and one replay report, with no completed root or gameplay result. Frozen file
hashes, native teacher artifacts, loaded CTM identity, effective policy and
complete runtime environment all verified. An independent read-only result
audit agreed with [report.json](report.json). The timing describes this one
root-prefix diagnostic, not general replay overhead or teacher latency.

Implementation checks: Debug builds of `one_combat`, `one_combat_advisor`,
`test_live_ooc_policy` and `live_ooc_parity_test` passed. Six focused CTests
passed in 8.34 seconds: existing adapter, capture startup, live policy/parity,
replay selftest and replay startup. Release replay selftest and all 16 startup
rejection cases passed. A synthetic controller-interruption check confirmed
owned-process cleanup and preservation of a failure receipt. These checks
launched no game beyond this separately frozen single scientific attempt.

## Interpretation and next gate

The selected leaf's evaluation can be repeated exactly from an inherited
in-memory snapshot. Fork isolation is necessary because the continuation also
touches shared CTM counters, caches and callback state. This does not create a
portable serialized replay artifact: the capture retains
`replayability:unavailable` and `publicParityQualified:false`.

The next gate is a separately bounded independent-future target-stability
study for MAP leaves. No student training, public-input qualification, CTM
promotion, gameplay comparison or default change follows from this result.
The reused historical seed is diagnostic and cannot be a future holdout.

## Raw evidence

[raw.tar.gz](raw.tar.gz) preserves 20 files under their original
`build/issue507-replay/` layout: frozen protocol/tooling/manifest/reference,
review packets, focused check logs, launch latch, raw capture/log, receipt and
report. [raw.sha256](raw.sha256) records each file hash. Archive SHA256:
`2765f4d225b7bf7865966409f9d115deb1312cb496468b8673d26157b9d67b96`.

The frozen binary is preserved locally at
`/home/philippherrmann/.codex/worktrees/d8c5/sts_lightspeed/build/issue507-replay/one_combat`.
The unchanged native models remain at the manifest paths in the preserved
§461 bundle. Neither executable nor model binaries are duplicated in this
archive; their hashes remain in its custody records. Raw JSON comparison needs
no game launch. The original analyzer creates its report exclusively; use a
separate scratch copy for any reanalysis and preserve the original evidence.
Do not rerun the game command or overwrite the completed attempt.

Knowledge impact: §462 records the experiment; the maintained research page
records its limited result and next gate; architecture/CODE_MAP document the
explicit diagnostic interface. No model or runtime default changed.
