# All-fixture generic smoke failure reproduction

The `smoke-and-parity` mode fails on both preparation call paths with the same
artifact and fixture input. On each run, it emits eight complete fixture rows
and then exits with status 1 and stderr `invalid_relic_counter`.

Inputs:

- PR 295 baseline source: `ae167e1e2eef6e988a61a12a2ef00d5d2d44a301`.
- Candidate source before this evidence correction: `90b3ee3c19f65cad966f437f1a384cc89cd6dbce`.
- Artifact: `/tmp/ooc-deepset-stack-provenance-review.native`, SHA-256
  `3f6d174950f1e4a8b042cebc78bd8525c7e112a13e31865670a39df4b0f2f586`.
- Fixtures: `fixtures-128draws.jsonl`, SHA-256
  `a78db761198b56cb8b57eff11b0bbbfbf6fa2c0dd741e3565d28c1b6d90ae720`.

The baseline reproduction restored the PR 295 `NativePrepared` call path
(survival, maxHP, HP encoding, and potion encoding) and rebuilt
`combat_transition_runtime_probe` in Release mode. The probe harness retained
the candidate-only tensor diagnostic helper; the exercised reference
`sampler.sample()` path is unchanged by PR 297.

Both runs used:

```text
build/linux-gcc-release/combat_transition_runtime_probe \
  /tmp/ooc-deepset-stack-provenance-review.native \
  docs/experiments/evidence/ooc_deepset_encoder_reuse_2026-09-23/fixtures-128draws.jsonl \
  smoke-and-parity
```

| Preparation path | Exit | Complete rows | Stderr | Raw stdout SHA-256 |
| --- | ---: | ---: | --- | --- |
| PR 295 baseline call path | 1 | 8 | `invalid_relic_counter` | `01b406fca80422f8a286b7a3d5148e15bccddb17c6ae9edccec8f87b3eae6437` |
| Shared-encoder candidate | 1 | 8 | `invalid_relic_counter` | `93bede47610971a3b11f438b1e1839b80dac6fee6c90065da897b33ffa21d388` |

Compressed JSONL stdout prefixes are retained as
`smoke-and-parity-baseline-prefix.jsonl.gz` and
`smoke-and-parity-candidate-prefix.jsonl.gz`. This reproduces the failure on
the baseline call path, so the observed generic-smoke error is not specific to
the encoder-reuse change. The `near-full` mode remains the successful
all-fixture prepared/reference parity check.
