# §499 — frozen Heart-outcome holdout and early mean bias

**HOLDOUT_SIGNAL_CALIBRATION_NOT_SHOWN.** The fixed head's aggregate prediction
improvement generalizes to the held-out runs, but all three prospective early
mean-bias equivalence gates fail. Do not treat it as a qualified native leaf.
No fitting, recalibration, gameplay, RL or native integration followed this result.

## Fixed candidate and actual evaluation

Evaluate exactly §498 initialization 1/step 300, 4,225-parameter nonlinear head on
the original frozen Arm C pooled encoder/policy. The candidate and TRAIN-derived
normalization are unchanged. Baseline remains TRAIN 126/1080 = 0.1166667.
The data are previously collected A20 Heart+keys native simulator trajectories
under exact 10k project-fair Silver real combat, Arm C tree prior+rollout,
calibrated A20 CTM, rollout3/public X2-B search guidance, 512 OOC sims/earlystop1.
The evaluated head did not play new games; Heart counts are corpus outcomes.

One exclusive durable opening covers 49 accepted TEST archives and 360 unique
sources 110181440–110181799. All 360 full source units pass receipt/process/binary/
policy/model-use, complete healthy footer, public schema, actual driver trace,
100% support and original activation-clock checks: 55,718 actual observations,
43 Heart wins and 317 other completed outcomes. No filtering or replacement.
All 53 archive hashes remain unchanged. Four superseded partials remain opaque.
The `claude/heart-outcome-data` transport is never merged.

## Confirmatory aggregate comparison

| Source-balanced metric | Selected head | TRAIN-rate constant |
| --- | ---: | ---: |
| BCE / log loss, lower better |0.327599|0.365854|
| Brier, lower better |0.095877|0.105185|
| Weighted state AUROC |0.731109|0.500000|

BCE improves 10.46%, Brier 8.85%. With the fixed 10,000 whole-source bootstrap,
model-minus-constant BCE is −0.038255, 95% [−0.054678,−0.022273]; Brier is −0.009308,
95% [−0.015599,−0.003251]. Both upper endpoints are strictly below 0: the preregistered
aggregate signal criterion passes. These refer to source-uniform then within-
run-state-uniform sampling, matching training and validation.

The fixed visitation-weighted diagnostic also improves (BCE 0.438777 vs 0.474808,
Brier 0.135249 vs 0.146448; AUROC 0.687712). Its source-cluster ratio-bootstrap
model-minus-constant intervals are BCE [−0.059152,−0.013570] and
Brier [−0.020064,−0.002599]. It is diagnostic, not a second selected population.

## Fixed early-game landmarks

One observation per reached source removes inverse-total-future-length weights
from these checks. Landmark predicates were fixed before TEST: initial index 0,
first actual Act 1 record at/above floor 8, and first actual Act 1 record at/above
floor 16. Runs not reaching a landmark receive no fabricated state or negative
label. All three have adequate source and outcome coverage.

| Landmark | Sources | Mean prediction | Observed Heart outcome | Bias 95% interval | AUC |
| --- | ---: | ---: | ---: | --- | ---: |
| Initial observation |360|7.19%|11.94%|[−8.13,−1.47] pp|0.5193|
| First Act 1 floor≥8 |358|7.15%|12.01%|[−8.30,−1.61] pp|0.5158|
| First Act 1 floor≥16 |341|6.11%|12.61%|[−10.04,−3.07] pp|0.6408|

None of the bias intervals fits entirely within the prospective ±5 percentage-
point tolerance. The early mean-bias gate fails; early ranking is also weak.
At the initial and floor 8 observations, BCE and Brier are worse than the frozen
constant. This blocks an overall offline PASS despite aggregate improvement.
The gate concerns marginal mean bias only: passing it would not prove conditional
calibration, ranking, search decision value or calibrated native `V_pi(s)`.

**Inference, not a proven diagnosis:** inverse-future-length weighting during
training may contribute to early underprediction. Frozen policy features and
limited independent outcome data are alternative explanations. This evaluation
does not isolate their contributions. A future TRAIN/VALIDATION-only comparison
of visitation/fixed-landmark weighting is reasonable; any revised candidate needs
fresh prospective holdout evidence. Do not retrain on or select against this now-
opened TEST cohort, change the thresholds, or quietly regrade this result.

## Custody, execution and checks

- Baseline publication: `0e3c31879e66cd701a09923d1f878bde5d407ba4`.
- Independently reviewed frozen evaluation source:
  `8f79207b7a04ed0f96773608099166c854e152dd`.
- Freeze: `70f489ef026f2f12ee5834a5ef0b2ba50109b262bba4b99608c295826d0921a1`.
- Candidate: `68c20b521b53a72896293b72442839eb5abfbb7c43222030556874b0a7593de1`.
- Result: `8b658f7d73bde12c45dc1031c5b1fe5fcab9a45b0b65b589814ece27a659f4e3`.
- Predictions: `8be7b7a261bb6c4a3f76a1655b8cfcc60cf5dc7e21580e2a4bcdc9ed27469fc6`.
- TEST source manifest:
  `8584bf879de1388c13591c3be8eab5ea53aedaf62d7104fce6b33395eccf6044`.
- Canonical opening latch:
  `c750603b79c21f75c5fea543cdb0b29cc2d02c6bd904a8c2128af137bcbc58e2`.

Source/design review and final exact-freeze review passed before opening; the
latter blocked tar parsing while checking every opaque archive hash. The fixed
canonical local import root owns the file+directory-fsynced O_EXCL latch, so
another output root cannot replay the opening. Copied/symlink import roots are
rejected. This is a local single-host guarantee, not distributed atomicity.
Never remove this consumed latch to retry a failed or unfavorable TEST.

All original Arm C and selected-head tensors remain unchanged. Local RTX 3060 Ti,
two CPU threads, strict deterministic float32/TF32off/CUBLAS4096:8. External
3,600 s TERM/10 s KILL guard; complete evaluation 134.870 s, wrapper exit 0/139.116 s.
These offline times include deep audit/encoding/analytics and do not qualify
single-leaf latency. No C++ code or runtime model defaults changed.

Focused 57/57 Python tests PASS in 2.016 s; independent 16/16 PASS in 1.738 s plus a complete
360-source synthetic run/second-invocation rejection fixture. These include
actual frozen encoder/head synthetic scoring, strict canonical tar validation,
pre-parser seal checks, durable/copied-root/symlink/repeat refusal, landmarks,
stable proper losses, clustered intervals and verdict distinctions.
Independent exact-result/custody review PASS: all 360 raw unit receipts/seven-file
hashes and 55,718 state metadata/labels/order match the saved prediction cache;
CPU head recomputation agrees to numerical roundoff, and all aggregate/subgroup/
landmark metrics, 10,000-resample intervals and exact verdict reproduce. The
encoder/evaluator were not rerun; the four partials remain opaque. Failing the
interval-within-tolerance criterion is not proof absolute bias exceeds 5 pp: start
and floor 8 point biases lie inside that margin, while their intervals cross it.

The checked-in source-health report covers frozen source 8f79207b before result
publication; exact publication-head health is recorded separately for PR handoff.
Native build, gameplay, inference timing and training were not run.

[Protocol](PROTOCOL.md),[freeze](freeze.json),[opening approval](opening-reviewed.json),
[command](command.json),[raw result](result.json),[source manifest](test-sources.jsonl)
and[independent result review](result-reviewed.json) form the compact evidence.
Raw prediction tensors and process receipts remain under ignored local
`build/heart-outcome-holdout-20261017-v1`; corpus transport stays never-merge.
Prior §497/498 artifacts are historical snapshots and are preserved unchanged.

**Knowledge impact:** current holdout verdict, exposed TEST custody, calibration
limitations, and single-use offline procedure. No production default/promotion.
Stop here before native integration.
