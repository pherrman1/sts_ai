# Fixed Stage A separability audit

Decision: **PRIOR_ANCHOR_NOT_SEPARABLE**. Selected gate: None.

Skip probabilities/ranks use the existing planner semantic action set after its ordinary forced-gold and tree-rule reward collection. Each audited root then has three card takes and one skip. Log gaps use unnormalized weights, which give the same log probability gaps. Ties use deterministic action ID.

| Case | decision / state index | floor | deck | burden | skip p | rank | log gap | value mean ± SE | gap | paired SE | P4 | P2 | V5 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|:---:|:---:|:---:|
| 032/11111 | 11 / 14 | 4 | 12 | 10 | 5.9381e-08 | 4 | 16.6225 | null ± null | null | null | yes | no | null |
| 032/11111 | 16 / 20 | 5 | 12 | 10 | 1.04314e-05 | 2 | 11.4707 | null ± null | null | null | yes | no | null |
| 032/11111 | 32 / 38 | 10 | 13 | 11 | 4.90311e-07 | 4 | 14.3729 | null ± null | null | null | yes | no | null |
| 032/11111 | 39 / 46 | 12 | 13 | 11 | 1.20424e-09 | 2 | 20.5374 | null ± null | null | null | yes | no | null |
| 032/11111 | 54 / 64 | 16 | 14 | 12 | 4.54053e-11 | 4 | 23.7757 | null ± null | null | null | yes | no | null |
| 326/13-skip | 1 / 1 | 0 | 11 | 10 | 5.81408e-08 | 2 | 16.6604 | 0.150276 ± 0.00906174 | 0.0052334 | 0.00190298 | yes | no | yes |
| 326/13-skip | 3 / 4 | 1 | 11 | 10 | 4.55759e-08 | 3 | 16.9039 | null ± null | null | null | yes | no | null |
| 326/13-skip | 61 / 71 | 20 | 19 | 17 | 0.00155787 | 2 | 6.4626 | null ± null | null | null | yes | no | null |
| 326/13-skip | 70 / 82 | 22 | 19 | 17 | 0.00197153 | 3 | 5.9694 | null ± null | null | null | yes | no | null |
| 326/13-skip | 77 / 90 | 24 | 19 | 17 | 0.031578 | 2 | 3.4230 | null ± null | null | null | yes | no | null |
| 326/13-skip | 93 / 107 | 27 | 20 | 17 | 0.00506979 | 4 | 5.2110 | null ± null | null | null | yes | no | null |
| 326/R1 | 3 / 4 | 1 | 12 | 11 | 5.19971e-08 | 3 | 16.7720 | null ± null | null | null | yes | no | null |
| 326/R1 | 11 / 13 | 3 | 14 | 12 | 6.59999e-10 | 2 | 21.1388 | null ± null | null | null | yes | no | null |
| 326/R1 | 32 / 37 | 10 | 15 | 12 | 1.17561e-07 | 3 | 15.8541 | null ± null | null | null | yes | no | null |
| 326/R1 | 40 / 47 | 12 | 16 | 13 | 1.23124e-11 | 4 | 25.1204 | null ± null | null | null | yes | no | null |
| 326/R1 | 52 / 60 | 16 | 16 | 13 | 3.57189e-09 | 3 | 19.4501 | null ± null | null | null | yes | no | null |
| 326/R1 | 71 / 83 | 22 | 17 | 17 | 8.67869e-05 | 3 | 9.1700 | null ± null | null | null | yes | no | null |
| 326/R1 | 78 / 91 | 24 | 17 | 17 | 0.000124427 | 2 | 8.9916 | null ± null | null | null | yes | no | null |

All skip actions preserve the displayed deck size and burden. Full candidate before/after counts, semantic identities, prior statistics, value availability and particle arrays are in audit.json.

Later CRN values are null because retained public records lack exact replay snapshots and latent transition/continuation state. They were never sent to the value evaluator. The exact initial Neow root requires full restored public-record equality and uses the current deployed rollout3/CTM/X2-B+M0 stack. If V5 admits this known destructive action, that alone fails its required separation condition; missing positive values cannot change that failure.

Gate results: `{"P2": {"destructive_eligible": false, "positive_eligible": [false, false, false, false, false], "status": "FAIL"}, "P4": {"destructive_eligible": true, "positive_eligible": [true, true, true, true, true], "status": "FAIL"}, "V5": {"destructive_eligible": true, "positive_eligible": [null, null, null, null, null], "status": "FAIL"}}`.

Resource counts: `{"actions": 72, "evaluation_cpu_seconds": 1.160120286, "leaf_evaluations": 256, "positive": 5, "states": 18, "terminal_particles": 0, "transitions": 256, "value_evaluated_states": 1, "value_qualified_states": 1}`.

This Stage A audit contains no Stage B planner, positive challenge, negative challenge or current-policy campaign result. Historical later 326 skips are not labeled individually destructive.
