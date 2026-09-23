# OOC CTM final-token optimization (2026-09-23)

## Change under review

This PR retains only the final-layer global-token optimization in
`apps/one_combat/combat_transition_runtime.cpp`. Layer 1 is unchanged. In layer
2, Q is computed only for token 0; K/V are computed for all tokens; attention,
projection, normalization, and FFN run only for token 0; the trunk still consumes
token 0. The contiguous-workspace experiment was reviewed and rejected because
its total Release preparation change was noise-sized. It is not in the PR's
runtime code. Its retained local raw screen files (`raw/workspace-*.json`) show
the basis for that decision.

## Exact parity

The Release `near-full` probe output is byte-identical to the baseline across 31
fixture rows. Baseline and candidate JSONL SHA-256 are both
`dbcee67b1037c86e3f9e96b99c2baac47437e812ebb2629feb257a692fe2dd26`. The probe
checks prepared/reference sample output, complete persistent state, and RNG
post-state for 128 draws per supported fixture. The focused near-full artifact
test also passes.

Fixture `tests/fixtures/combat_transition_near_full.jsonl` SHA-256:
`d464bcc043bd3f9964a2300696f05356a602eb3fb98f01070800cb025e9226ee`.
Model `combat_transition_near_full_except_smoke_v2.native` SHA-256:
`e9a18951710fdfe9e1a81a2703090a41f039067c670a1d8a0393b5e7e8e0ddfd`.

## Release prepare measurement

The same single supported fixture
`/tmp/ooc-final-token-one-fixture.jsonl` (SHA-256
`3cef5d069e1caffeea88eff24b98d3c5c873cf02c899bb6ef660a1f508b30018`) and the
same Release probe command were used once at baseline and once with the
candidate. The measured `prepare()` call was 2.132574 ms at baseline and
1.609938 ms with the candidate (-24.5%, one observation per arm). During each
probe, 128 prepared/reference draws also passed complete persistent-state and
planner-RNG parity. This is a single-fixture, single-observation timing result;
its size should be treated as an initial signal, not a stable aggregate.

Raw probe outputs are `raw/prepare-baseline.jsonl` and
`raw/prepare-candidate.jsonl`. Their SHA-256 values are
`8de87a04ebfb04d9ef08cb3db4b40a7545229497147aeed13ba06a1c3919cfe0` and
`357751c17d529769734d8d1b0dc1fad758eea9d2f3f3437d5de0ed3850de9fed`.
The baseline and candidate Release probe binary SHA-256 values are
`53618f62d20df07acf5a95c3e76e92b1919952147be9ad4d23594bda3cc8e1da` and
`4569f8b3a2ad6d0b5cc8e4b4eb2911e2af1c074ae62df71e6b2d54f7d6479e15`.
The probe writes other diagnostic fields; `preparedParity.preparationNs` is the
measured duration.

## Earlier Debug microbenchmark

Before the Release `prepare()` measurement, a one-fixture Debug component screen
used ten encoder calls per process and three process repetitions. Median summed
encoder time changed from 26.695 ms to 16.465 ms (-38.3%). Raw outputs are
`raw/final-token-*.jsonl`. This is a component microbenchmark, not an end-to-end
preparation or gameplay measurement.

## Focused commands and limits

```text
cmake -S . -B /tmp/ooc-ctm-combined-release -DCMAKE_BUILD_TYPE=Release
cmake --build /tmp/ooc-ctm-combined-release --target combat_transition_runtime_probe one_combat -j2
ctest --test-dir /tmp/ooc-ctm-combined-release -R 'combat_transition_runtime_loader|combat_transition_near_full_artifact' --output-on-failure
```

Both focused CTests pass. The native-contract test fails during Python import
with `RuntimeError: native write-back set changed; repeat legality audit`; the
same failure was reproduced on the untouched baseline. No full CI run or
whole-game seed was run. This is bounded exact-parity and timing evidence, not
gameplay or production qualification.
