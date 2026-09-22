# Silver prior v1 one-time LOCKED_TEST evaluation

## Result

`PRIOR_MODEL_LOCKED_TEST_CONFIRMED` under the frozen decision rule. One candidate was evaluated: `SilverPriorNetV1`, T2, seed `20260922`, temperature `1.179975000005129`, checkpoint SHA-256 `b756c3e6576bdb53085f24aeb1102e4e2fe55fd7469c55546c99f068ccf40e24`.

The run used all **1,494 non-quarantined LOCKED_TEST L roots from 64 source seeds** and all **64 preselected LOCKED_TEST J roots from 64 source seeds**. It used 5,000 deterministic source-seed-cluster bootstrap replicates. The locked labels were read exactly once after the reviewed evaluator wrote the durable create-only receipt.

## Primary contrasts

| Evaluation | Model expected regret | Uniform expected regret | Model − uniform (95% source-cluster CI) |
| --- | ---: | ---: | ---: |
| LOCKED_TEST L | 2.01271 | 5.24694 | -3.23423 [-3.53464, -2.93676] |
| LOCKED_TEST J | 1.63873 | 4.53427 | -2.89553 [-3.58717, -2.26012] |

Both predeclared upper confidence bounds are below zero. The classification uses only these two gates.

## J diagnostics

The frozen L-target distribution had LOCKED_TEST J regret **0.41489**, versus **4.53427** under uniform; teacher-minus-uniform was **-4.11938 [-4.89133, -3.39374]**. Soft-prior headroom recovery was **70.29%**. Model argmax J regret was **1.06369 [0.57714, 1.66233]**, L-argmax J regret was **0.21211 [0.09003, 0.36171]**, and pairwise concordance between model logits and J values was **0.73752 [0.67221, 0.79854]**.

These diagnostics show the student improves over uniform while retaining a meaningful gap to the frozen L target. They do not alter the predeclared pass rule.

## Validation-to-locked diagnostics

These are descriptive comparisons only. Validation values are loaded from the fixed-hash Stage-A T2 summaries.

| Contrast | Validation mean (95% CI) | LOCKED_TEST mean (95% CI) |
| --- | ---: | ---: |
| L model − uniform | -3.57885 [-3.89616, -3.30330] | -3.23423 [-3.53464, -2.93676] |
| J model − uniform | -3.64892 [-4.17707, -3.14134] | -2.89553 [-3.58717, -2.26012] |

The locked advantages are smaller in point estimate but still satisfy both gates. Top-action agreement was 44.98% on L; it was descriptive and not a gate.

## Provenance and limits

See [provenance.json](provenance.json), [locked-l-summary.json](locked-l-summary.json), [locked-j-summary.json](locked-j-summary.json), and [decision.json](decision.json). Detailed per-root metrics and the consumption receipt remain in the durable external directory named in `provenance.json`; this Git packet contains aggregate summaries, not raw predictions.

Phase-A review initially requested the validation-to-locked comparisons. They were added and independently reviewed at `f458ef51029ea53f9baaf361e87fba67c743d5a2` before the run. No LOCKED_TEST label, outcome, prediction, or shard was opened before that review. No training, tuning, temperature selection, or alternate-candidate evaluation occurred.

**LOCKED_TEST is now consumed and must not be used for model tuning.** Any future model change must use TRAIN/VALIDATION only. This result does not promote the model to Silver default and does not establish native inference cost or gameplay impact. After this pass, the next experiment is the separate oracle/native prior integration experiment described in the handoff.
