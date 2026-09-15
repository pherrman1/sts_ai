# Targeted combat-transition attention hyperparameter optimization

Date: 2026-09-15. This is an offline, attention-only optimization on the
existing Phase-1 whole-combat transition corpus. No simulator collection,
gameplay evaluation, runtime export, support change, or deployment change was
performed.

Knowledge impact: the completed model-selection result is recorded here, in
the experiment ledger, and in the maintained current-research status. It does
not change a runtime model or qualified default.

## Decision

**`ATTENTION_HPO_IMPROVES_FROZEN_ATTENTION_POSTHOC`.** Doubling the
winning-HP MSE weight from `1.0` to `2.0` won the frozen VALIDATION comparison.
The architecture remained width 64, two Transformer layers, four heads,
feed-forward width 128, dropout 0.1, and trunk width 64. The winner selected
epoch 13 with validation composite `0.164160725`, versus `0.168567730` for the
matched baseline candidate, a reduction of `0.004407005` (2.61%).

After selection, the winner was refit on TRAIN+VALIDATION for 13 epochs. On
the historical TEST split it improved all three primary errors relative to the
frozen corrected attention checkpoint, and every paired source-bootstrap 95%
interval was below zero. This is post-hoc confirmation: TEST was already
inspected in the earlier v1 model study. It does not establish an untouched
prospective result, attention superiority over DeepSets, runtime compatibility,
or gameplay value. The existing `STRUCTURED_NEURAL_WINS_NO_CLEAR_FAMILY`
family conclusion and DeepSets simplicity tie-break remain unchanged.

## Frozen protocol and provenance

- Reviewed experiment-code SHA: `55f980c49a0637802edf54a12bde6d4a51faa43e`.
- Corpus: 510,030 rows / 24,999 completed sources; SHA256
  `74c08aa0a3c30342d86cd45355fe17ffa9046963ad7c8cf71b1938f9cdc1cfde`.
- Prepared array: SHA256
  `a642671d0956f36405b837755cdf3dfb3c4870cde4a1d6f251046ffc8205a1c9`.
- Frozen source split: 408,183 TRAIN rows, 50,406 VALIDATION rows, and
  51,441 historical TEST rows; split-manifest SHA256
  `e9043bcceb9d95027711e6ff33afbfe1cae3cf9528f820c0ff68bddbb419db32`.
- Frozen corrected attention checkpoint: SHA256
  `a4545c54c8b99afb059b64c6ee36523f472e2e636040e166b32ded4218614b6f`.
- Eight candidates used matched seed `20260911`, row permutations, batch
  2,048, CUDA FP32, 16-epoch cap, and patience 4. Candidate selection minimized
  survival Brier + winning-HP MAE + joint alive-HP MAE on VALIDATION only.
- Git cleanliness, reviewed SHA, array/checkpoint hashes, exact source-to-split
  membership, row counts, and immutable output-directory behavior fail closed.
  CUDA kernels were not asserted bitwise deterministic.

## Validation selection

| Candidate | Changed setting | Selected epoch | Parameters | Composite |
| --- | --- | ---: | ---: | ---: |
| `hp_weight_2` | winning-HP loss weight 2.0 | 13 | 114,178 | **0.164160725** |
| `width96` | width/trunk 96, FF 192, LR 8e-4 | 13 | 223,138 | 0.167717187 |
| `ff256` | FF width 256 | 13 | 147,202 | 0.168153005 |
| `depth3` | 3 layers, LR 8e-4 | 13 | 147,650 | 0.168203941 |
| `baseline` | original configuration | 16 | 114,178 | 0.168567730 |
| `no_dropout` | dropout 0.0 | 13 | 114,178 | 0.169234952 |
| `lower_lr` | LR 5e-4 | 15 | 114,178 | 0.170868000 |
| `higher_lr` | LR 2e-3 | 7 | 114,178 | 0.170878278 |

## Historical TEST comparison

| Model | Survival AUC / Brier / logloss | Winning-HP MAE / RMSE / bias | Joint alive-HP MAE / RMSE / bias |
| --- | --- | --- | --- |
| Frozen attention | 0.978805 / 0.017901 / 0.060792 | 0.072575 / 0.107032 / +0.000318 | 0.078781 / 0.120692 / +0.001465 |
| Tuned attention | **0.980058 / 0.017384 / 0.058878** | **0.069709 / 0.104013 / -0.000974** | **0.075665 / 0.117100 / -0.001296** |

Paired tuned-minus-frozen-attention point deltas and source-bootstrap 95%
intervals (negative favors tuned) were:

| Metric | Point delta | Source-bootstrap 95% |
| --- | ---: | --- |
| Survival Brier | -0.000516582 | [-0.000841769, -0.000225118] |
| Winning-HP MAE | -0.002865523 | [-0.003100919, -0.002633325] |
| Joint alive-HP MAE | -0.003116697 | [-0.003415866, -0.002849630] |

## Command, cost, and artifacts

```text
/usr/bin/time -v -o /home/philippherrmann/sts_sweep/runs/attention-transition-hpo-20260915.time.txt python3 tools/combat_transition_attention_hpo.py --prepared-dir /home/philippherrmann/sts_sweep/runs/combat-transition-model-v1 --baseline-checkpoint /home/philippherrmann/sts_sweep/runs/combat-transition-model-v1/attention.pt --reviewed-commit 55f980c49a0637802edf54a12bde6d4a51faa43e --output-dir /home/philippherrmann/sts_sweep/runs/attention-transition-hpo-20260915 --device cuda --threads 8 --batch 2048 --epochs 16 --patience 4 --training-seed 20260911 --bootstrap-reps 1000
```

The command exited 0 after 3:09:00 wall time, used 10,370.75 seconds
user+system CPU, peaked at 8,561,580 kB RSS, and did not swap. External outputs:

- Tuned checkpoint: `attention_tuned.pt`, SHA256
  `005f860d847a773c363170d2473fc8f3f77b4beab501c5db44833d2ac8e1e987`.
- Structured evidence: `attention_hpo_evidence.json`, SHA256
  `3a4ac8859f9e31f5912449a6c8a1376e7f4e3306791c7e60508cc7e9d956a24c`.
- Directory: `/home/philippherrmann/sts_sweep/runs/attention-transition-hpo-20260915/`.

Focused implementation tests passed before the run, and the harness passed an
independent scientific/implementation review after repairs. No runtime export,
native parity, composed-transition qualification, gameplay benchmark, or new
data collection was run because those are outside this targeted optimization.
