# §500 — outcome weighting result

**VALIDATION_WEIGHTING_NOT_SHOWN.** Equal-state fitting improves aggregate
validation losses and start/floor8 bias, but worsens floor16 bias. The registered
success rule requires every early landmark's absolute point bias to improve;
it fails. This is reused TRAIN/VALIDATION development evidence. §499's consumed
TEST was not read, regraded or used in this comparison, and its verdict remains
unchanged. No gameplay, native integration, RL, policy/trunk update or promotion.

The [prospective protocol](PROTOCOL.md) fixed two arms × two initializations ×
2,000 updates, with the same architecture, original Arm C cached representation,
TRAIN normalization, initial tensors/bias, optimization budget and common
validation visitation-BCE selection. The only intervention is training sampling
weight. Source-balanced control selects init1/step800; equal-state treatment
selects init1/step600. The control is newly fitted with the common selection
rule, not the immutable §498 selected checkpoint.

| VALIDATION metric | Source-weighted fit | Equal-state fit |
| --- | ---: | ---: |
| Visitation BCE |0.462407|0.453411|
| Visitation Brier |0.143088|0.141157|
| Visitation AUROC |0.665120|0.668981|
| Source-balanced BCE |0.355095|0.353966|
| Source-balanced Brier |0.104525|0.103939|

Constant TRAIN126/1080: visitation BCE0.498733/Brier0.155509. Paired source-cluster
ratio-bootstrap deltas treatment−control: BCE−0.008996,95%[−0.015750,−0.002421];
Brier−0.001931,[−0.003488,−0.000267]. These are descriptive development intervals,
not adjusted for checkpoint selection/reused validation, not new holdout evidence.

| First actual landmark | Reached/wins | Control prediction | Treatment prediction | Outcome | Treatment bias95% (pp) | Treatment marginal gate |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| Index0 |360/47|8.25%|11.97%|13.06%|[−4.66,+2.28]|PASS|
| Act1floor≥8 |358/47|9.29%|10.81%|13.13%|[−5.88,+1.13]|FAIL|
| Act1floor≥16 |350/47|12.40%|9.25%|13.43%|[−7.85,−0.61]|FAIL|

All adequacy gates pass. Absolute point bias at floor16 worsens1.03→4.18pp;
treatment floor8's absolute point bias improves but its interval crosses the
−5pp gate. No missing landmark is fabricated. Treatment landmark AUROCs are
0.5253/0.5011/0.5135; mean-bias PASS alone would not prove ranking or conditional
calibration. This experiment does not establish calibrated counterfactual value.

Only1,080 independent TRAIN outcomes/126 wins support171,442 correlated training
states. Validation has360 outcomes/47 wins. Changing the weighting partly
improves early marginal predictions, but does not uniformly solve them.
**Inference:** weighting alone is insufficient in this fixed comparison;
representation, independent source count and checkpoint selection remain plausible
contributors. A separately frozen development loss can explicitly weight early
reached states. Any candidate confirmation needs fresh prospective holdout data.
No further fits or native work follow this result automatically.

Execution source `94c0bf784568a817f298fe29aa1ebc5840863273` versus baseline
`3c2c42098727110e42e3fc310c6a1d3372662be2`. All four best checkpoints,80 history
records and selected TRAIN/VALIDATION predictions persist. Paired initial tensors
match, frozen normalization matches §498, original/cache/runtime custody is
unchanged. No raw archive readers or encoder forwards run. Cached policy hashes
are preserved; this makes no new composed-forward/native parity claim.

Local RTX3060Ti,2CPUthreads, deterministic float32/TF32off/CUBLAS4096:8 and
CPUfloat64 sampling. Fit/analytics/custody17.063s; external900s wrapper exit0 in
22.962s. Reused cache avoids ~6minutes encoding; none of these timings measure
native inference speed. Original and failed historical runs remain intact.

Python68/68PASS2.086s, including pinned actual encoder/head synthetic CPU/CUDA.
Independent11/11PASS0.790s. A source-review tie-order finding was repaired before
freezing and covered by a regression test. One earlier full-suite setup attempt
omitted STS_OUTCOME_TRAINING_ROOT and had one error; corrected setup passed before
any real fits. No C++/gameplay tests: no runtime changes. No GitHub CI pass claimed.

Compact evidence and hashed inventory are adjacent. Raw checkpoints/predictions/
logs remain under `/home/philippherrmann/Documents/sts/sts_lightspeed/build/heart-outcome-weighting-20261017-v1`,
with checks and execution wrapper in the sibling `-verification` directory.
Independent exact-result/custody review PASS: [receipt](result-reviewed.json).
It reproduces candidate selection, all aggregate/landmark metrics, AUC/calibration
and10,000-resample intervals without fits, encoding or TEST access. Source/design
[approval](source-reviewed.json) and [raw artifact hashes](raw-artifacts.json) are
separate from the unchanged negative scientific verdict.
Stop before native integration. Knowledge impact: current weighting evidence,
cache-only development procedure and consumed-TEST exclusion; no default change.
