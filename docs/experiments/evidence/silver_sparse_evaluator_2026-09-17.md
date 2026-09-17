# Silver sparse policy/value evaluator screen

## Question and bounded protocol

The merged Phase-A result showed that the dense native implementation was too
slow for per-leaf use. This screen tested only whether the same fixed model
function could be computed more cheaply by transposing the first-layer weights
and skipping zero state inputs. It did not change feature semantics, weights,
model width, action outputs, quantization, incremental accumulators, training,
gameplay, or runtime search.

The existing schema-only corpus and the same 16 supported `PLAYER_NORMAL`
leaves were reused. The benchmark used one thread, fixed synthetic weights,
200 iterations, 3,200 calls, and 13,000 legal action scores. Sparse-input
preparation (scanning the 1,768 state inputs and accumulating only nonzero
features) was included in the sparse model timing.

Command:

```text
build/linux-gcc-release/silver_policy_value_phase_a \
  build/phase_a_final_omp1/source.corpus.jsonl \
  build/silver_sparse_eval_screen/examples.jsonl \
  build/silver_sparse_eval_screen/benchmark.json 16 \
  > build/silver_sparse_eval_screen/phase_a.log 2>&1
```

## Results

| Measurement | Mean per call |
| --- | ---: |
| Dense encoder/value plus action scoring | 78.019 µs |
| Sparse encoder/value plus action scoring | 6.377 µs |
| Clean `PLAYER_NORMAL` rollout at the 1k operating point | 2.981 µs |

The sparse path was approximately 12.2x faster than the dense model path, with
an average of 39 nonzero state inputs. It matched the dense reference on every
tested value and action logit: maximum absolute value error was
`4.66e-10`, and maximum absolute logit error was `1.16e-10`, below the declared
`1e-5` tolerance. The sparse model-plus-action call is nevertheless about
2.14 rollout-equivalents, so it does not provide an inference-throughput gain
for per-leaf replacement.

## Decision

**`PV_SPARSE_NOT_FEASIBLE_PER_LEAF`** for the throughput-oriented screen. The
sparse computation is a valid parity-preserving optimization, but its complete
model-plus-action cost remains above the clean rollout cost. Per the declared
stop rule, the offline adapter/native-state optimization was not attempted.
Root-only learned guidance remains the next distinct architectural direction;
it is a decision-quality experiment, not a continuation of this throughput
screen.

## Provenance

- Implementation commit: `fb467614a2804114520dc76992cdefe9a975d6d0`
- Input corpus SHA-256: `f19f012bc0acc9c7bac517de7d4270a85a00fde4d7d2967fc9e18f41bed2a843`
- Benchmark executable SHA-256: `f4a9900ac91d9bd4a7c6da759ac5dbbb9de25e88985b8ee466c849680f271788`
- Benchmark JSON SHA-256: `5f75d992f100277ab84a36f2437a43fd8f31c0338e48a5a64c7942cf96155539`
- Raw benchmark log SHA-256: `26398d0964d0f4941c53dd615b95b2bed1c432f8e09f24a7c659781d776cdcab`
- Parity tolerance: `1e-5`

The generated JSON, log, and example output remain ignored build artifacts;
the hashes above bind the result to the local receipt and executable.

Knowledge impact: current research status, architecture guidance, and this
experiment evidence were updated; no runtime default changed.
