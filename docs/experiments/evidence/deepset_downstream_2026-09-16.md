# DeepSets downstream qualification (2026-09-16)

Decision: **`DEEPSET_DOWNSTREAM_GO`**.

This experiment replaced only the downstream state input with the frozen qualified 64-dimensional DeepSets representation and retrained the existing downstream heads with the reference recipe. The DeepSets encoder, maxHP/HP heads and HP delta embedding were not trained; potion representation, traces, labels, masks, support and native target helpers were unchanged.

Baseline: `852a96d22cf52a0588a355cae86eed3dd26ff668`; implementation SHA: `4876568a4b35daae09284079ba04da0ab66c3b59`; final head SHA: `4876568a4b35daae09284079ba04da0ab66c3b59`.

TRAIN: 150404 rows / 18286 sources. VALIDATION: 17950 downstream-eligible rows. TEST inference rows: 0.

## Metrics

| Output | Rows | Reference NLL | Candidate NLL | Relative NLL | Singleton rows | Candidate accuracy | Accuracy delta |
|---|---:|---:|---:|---:|---:|---:|---:|
| turns | 4635 | 1.234442094 | 1.221927125 | -1.0138% | 1173 | 0.277067 | -0.000853 |
| attacks | 6075 | 2.181672738 | 2.184066051 | +0.1097% | 6075 | 0.165432 | +0.005926 |
| cards | 2536 | 2.312143972 | 2.305762149 | -0.2760% | 2536 | 0.116325 | +0.009858 |
| shuffles | 2478 | 0.875157608 | 0.857762428 | -1.9877% | 2478 | 0.577078 | +0.006053 |
| writhing | 413 | 0.584365814 | 0.573275541 | -1.8978% | — | — | — |
| ritual | 1243 | 0.070339128 | 0.065175237 | -7.3414% | — | — | — |
| gold | 6921 | 0.586937788 | 0.581060089 | -1.0014% | — | — | — |
| joint | 17950 | 1.364212489 | 1.358647974 | -0.4079% | — | — | — |

Finite/legal checks: `True`. Fixed gates: principal NLL ≤2%, singleton accuracy drop ≤0.005, joint/important-slice NLL ≤2%/5%.

No TEST, native export, runtime/default change, gameplay, OOC MCTS, potion retraining or encoder fine-tuning was performed. This is offline downstream evidence only.

Remaining uncertainty: one fixed offline fit and one eligible source-grouped VALIDATION cohort; no TEST, runtime, native, gameplay, OOC MCTS or default qualification was performed.

Knowledge impact: current research status and experiment evidence only; qualified components and executable defaults remain unchanged.
