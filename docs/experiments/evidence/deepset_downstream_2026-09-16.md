# DeepSets downstream qualification (2026-09-16)

Decision: **`DEEPSET_DOWNSTREAM_GO`**.

This experiment replaced only the downstream state input with the frozen qualified 64-dimensional DeepSets representation and retrained the existing downstream heads with the reference recipe. The DeepSets encoder, maxHP/HP heads and HP delta embedding were not trained; potion representation, traces, labels, masks, support and native target helpers were unchanged.

Baseline: `066264dc25bf2046aecd5ca7a94a8e82d5031e7b`; implementation SHA: `e036a32af068e8a99cd3c3edbfe1aeb35fdab58c`; final head SHA: `1bc53ea33588f107804347ffd871ec34a03f37fd`.

TRAIN: 150404 rows / 18286 sources. VALIDATION: 17950 downstream-eligible rows. TEST inference/encoding rows: 0.

## Metrics

| Output | Rows | Reference NLL | Candidate NLL | Relative NLL | Singleton rows | Candidate accuracy | Accuracy delta |
|---|---:|---:|---:|---:|---:|---:|---:|
| turns | 4635 | 1.234442094 | 1.221367363 | -1.0592% | 1173 | 0.279625 | +0.001705 |
| attacks | 6075 | 2.181672738 | 2.184236159 | +0.1175% | 6075 | 0.166914 | +0.007407 |
| cards | 2536 | 2.312143972 | 2.304951572 | -0.3111% | 2536 | 0.115142 | +0.008675 |
| shuffles | 2478 | 0.875157608 | 0.857677231 | -1.9974% | 2478 | 0.579096 | +0.008071 |
| writhing | 413 | 0.584365814 | 0.573269898 | -1.8988% | — | — | — |
| ritual | 1243 | 0.070339128 | 0.065175238 | -7.3414% | — | — | — |
| gold | 6921 | 0.586937788 | 0.581060082 | -1.0014% | — | — | — |
| joint | 17950 | 1.364212489 | 1.358598545 | -0.4115% | — | — | — |

Finite/legal checks: `True` (finite metrics/losses, normalized head probabilities, and positive exact legal target mass under the existing masks). Fixed gates: principal NLL ≤2%, singleton accuracy drop ≤0.005, joint/important-slice NLL ≤2%/5%.

No TEST encoding or inference, native export, runtime/default change, gameplay, OOC MCTS, potion retraining or encoder fine-tuning was performed. This is offline downstream evidence only.

Remaining uncertainty: one fixed offline fit and one eligible source-grouped VALIDATION cohort; no TEST, runtime, native, gameplay, OOC MCTS or default qualification was performed.

Knowledge impact: current research status and experiment evidence only; qualified components and executable defaults remain unchanged.
