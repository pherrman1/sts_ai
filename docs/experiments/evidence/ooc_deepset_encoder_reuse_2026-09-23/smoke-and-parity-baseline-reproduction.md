# All-fixture generic smoke failure reproduction

The `smoke-and-parity` mode fails on both preparation call paths with the same
artifact and fixture input. On each run, it emits eight complete fixture rows
and then exits with status 1 and stderr `invalid_relic_counter`.

Inputs:

- PR 295 baseline source: `ae167e1e2eef6e988a61a12a2ef00d5d2d44a301`.
- Candidate source: `86b9f60a55ddbee4b20f41532d3706dc301bff4c`.
- Artifact: `/tmp/ooc-deepset-stack-provenance-review.native`, SHA-256
  `3f6d174950f1e4a8b042cebc78bd8525c7e112a13e31865670a39df4b0f2f586`.
- Fixtures: `fixtures-128draws.jsonl`, SHA-256
  `a78db761198b56cb8b57eff11b0bbbfbf6fa2c0dd741e3565d28c1b6d90ae720`.

The baseline reproduction used a separate managed worktree checked out at the
exact PR 295 head above, then ran `cmake --preset linux-gcc-release` and built
`combat_transition_runtime_probe` in Release mode. This is the untouched PR 295
source. Its output includes the inherited `preparedEncoderCalls: 4` field;
that field is derived from artifact metadata and is not instrumented. It agrees
with code inspection of the four-call baseline path, but is still not a
measured count. The candidate probe field was removed in the
evidence-correction commit.

The baseline run used:

```text
cd /tmp/pr295-baseline-pr297
build/linux-gcc-release/combat_transition_runtime_probe \
  /tmp/ooc-deepset-stack-provenance-review.native \
  /home/philippherrmann/.codex/worktrees/cc23/sts_lightspeed/docs/experiments/evidence/ooc_deepset_encoder_reuse_2026-09-23/fixtures-128draws.jsonl \
  smoke-and-parity
```

The candidate run used the same command from
`/home/philippherrmann/.codex/worktrees/cc23/sts_lightspeed`, with the fixture
argument relative to that worktree.

| Preparation path | Exit | Complete rows | Stderr | Raw stdout SHA-256 |
| --- | ---: | ---: | --- | --- |
| PR 295 baseline commit, Release binary SHA-256 `91f8f1c9c91ca69ee092489d8e507209348972e35f010d9b420e59c3d9351509` | 1 | 8 | `invalid_relic_counter` | `9b85651013bd5b69c07ab4b4485ac23dd60ce99a9cdf7823a2b2e85851dd5e1f` |
| Shared-encoder candidate | 1 | 8 | `invalid_relic_counter` | `93bede47610971a3b11f438b1e1839b80dac6fee6c90065da897b33ffa21d388` |

Compressed JSONL stdout prefixes are retained as
`smoke-and-parity-baseline-prefix.jsonl.gz` and
`smoke-and-parity-candidate-prefix.jsonl.gz`. This reproduces the failure on
the baseline call path, so the observed generic-smoke error is not specific to
the encoder-reuse change. The `near-full` mode remains the successful
all-fixture prepared/reference parity check.
