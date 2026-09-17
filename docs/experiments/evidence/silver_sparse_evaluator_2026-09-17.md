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

## Timer-boundary correction

The first run of this screen started the outer end-to-end timer before the
parity checks and sparse benchmark, while dividing by only the dense-call
count. That inflated its top-level mean and made its percentiles incomparable.
The minimal correction moved that timestamp immediately before the dense timed
loop; parity, sparse timing, and stage timestamps were already independently
bounded and were not affected.

On the corrected run, the dense conversion-inclusive end-to-end report was
120.636 µs mean, 119.208 µs median, 124.404 µs p90, and 173.634 µs p99. The
separately bounded sparse model-plus-action timing was 6.355 µs/call. The
corrected stage means were 1.300 µs conversion, 41.418 µs feature/vector
preparation, 73.341 µs dense encoder/value, and 4.291 µs action scoring. Sparse
parity remained `4.66e-10` maximum value error and `1.16e-10` maximum logit
error. Thus the timer correction changes only the top-level end-to-end report;
it does not invalidate the sparse-vs-dense model-computation conclusion.

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
- Timer correction commit: `d0b956b019d9fcf8a5696971e35466f3fa854bc3`
- Input corpus SHA-256: `f19f012bc0acc9c7bac517de7d4270a85a00fde4d7d2967fc9e18f41bed2a843`
- Corrected benchmark executable SHA-256: `b5bd7687a9644c5e033111b6a7d537fe2fedda00f8067d96f53f6e0d969ec30e`
- Corrected benchmark JSON SHA-256: `389ed5a003e6a221ec77620569497b64f8d197f21fe73ca901edfff6656cde63`
- Corrected raw benchmark log SHA-256: `bc04e75ba0afa4955837803cbae6191b13d5697d5a0b43f0c665c96752e0649d`
- Parity tolerance: `1e-5`

The generated JSON, log, and example output remain ignored build artifacts;
the hashes above bind the result to the local receipt and executable.

Knowledge impact: current research status, architecture guidance, and this
experiment evidence were updated; no runtime default changed.
