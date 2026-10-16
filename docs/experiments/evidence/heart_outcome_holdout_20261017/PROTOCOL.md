# §499 — one-shot Heart-outcome holdout and early calibration

The user authorized this follow-up after §498's VALIDATION_ONLY result. TEST is
closed until exact independent source/design review PASS and a frozen clean
commit. An independent final freeze audit and opening-reviewed.json binding its
SHA and source approval are required before the irreversible opening. Native integration, new gameplay seeds, fitting/recalibration, model
selection, RL and default promotion are excluded. No TEST retry or adaptation.

## Hypothesis and immutable candidate

The selected nonlinear Arm C head retains its positive constant-baseline
comparison on unseen full-run outcomes. A separate calibration question tests
whether the same head gives useful early-run probabilities without conditioning
weights on the run's future length. Alternatives: validation selection overstated
the gain, frozen policy features generalize poorly, or inverse-length fitting
leaves fixed-landmark probabilities miscalibrated. Report each axis separately.

Only §498 init1/step300 is evaluated. Checkpoint SHA256
68c20b521b53a72896293b72442839eb5abfbb7c43222030556874b0a7593de1,
portable head2c478bca6692e8c69cd70c78cf7cf1758c07c3ed884a97bb64d813424019942c,
result eeee2c1ace7382fa5fa3c4f51b4caeb6e08ea3d04bc54553d299e7f7e22c356c,
review c3cc779e11a641b2e6b0e84137ccdd71309e2c28575062f99e5e9e5b42b9b669.
Keep original Arm C checkpoint, fixed encoder, TRAIN normalization, policy and
all tensors unchanged. Baseline is exactly TRAIN126/1080, never TEST's win rate.
No old TEST or surrogate targets, affine alternatives or additional candidates.

## Custody and single opening

Retain the never-merge transport e3b649ced5a392f78e9412787a84d458cffd60a1 and
independently audited §497 import. Only49 accepted SEALED-test.tar.gz archives
are opened, assigned exactly360 sources110181440–110181799 by the frozen plan:
41 originals plus8 replacements for lost7/8/27/34. Four superseded partial
archives stay opaque forever in this protocol. All53 raw hashes are checked
before and after. Pre-opening code must not list/parse/decompress TEST members.

Freeze exact source/tool/tests/protocol, import report/review/manifest, candidate
checkpoint/result/review/portable head, encoder/runtime/dependencies and all
archive hashes. Independently review a synthetic strict-reader/analytics fixture
and actual CPU/CUDA encoder bridge before opening. Reuse the TRAIN companion
identity from §498; labels, source IDs and terminal metadata never enter inputs.
Create the exclusive test-opened.json durable exclusive latch (file and directory fsync) in the fixed canonical local
import root BEFORE
any TEST parser call; bind exact freeze and approval. A consumed latch prevents
all repeated launches, including other output roots. Reject copied/symlink import
roots; no distributed or cross-host atomicity is claimed. No resume after failure.

Strict reader accepts only canonical test/seed-N plus the eight frozen source
suffixes; reject links, unsafe/duplicate/unknown members, members over64MiB or archives
over256MiB, cross-split
sources and missing files. Deep-audit all360 units using §497's unchanged
receipt/process/binary/runtime/model-use, actual trace, header/footer/public
schema checks, including original activation clocks. Require all sources healthy,
exactly complete and100% supported. Do not filter or relabel to pass. If any unit,
identity, coverage, finite-value, wall or runtime gate fails, report
INVALID_TEST_EXECUTION, preserve everything and stop without partial efficacy.

## Fixed measurements and decision

Encode every TEST observation once with fixed batch32 plus the genuine TRAIN
companion. Save frozen pooled features, metadata and logits for independent
recomputation. No training. Check all original Arm C and head tensors unchanged,
portable/checkpoint tensor equality and finite logits. Runtime is local RTX3060Ti,
two CPU threads, deterministic float32/TF32off/CUBLAS4096:8, same qualified
encoder/runtime as §498. Cooperative3600s gate plus external
`timeout --signal=TERM --kill-after=10s 3600s`; no extension. Offline timings only.

Primary population repeats §498: choose source uniformly, then one recorded
state uniformly within it. Report stable-logit BCE, Brier, AUROC and10-bin
calibration, per-source, by act/screen. Confirmatory aggregate signal requires
at least5 TEST wins and5 losses and the upper endpoint of BOTH paired
source-cluster bootstrap95% intervals for model-minus-constant BCE and Brier
strictly below0. Use10,000 uniform source resamples, RNG499. No individual-state
independence claim. Also report visitation-weighted metrics as a fixed diagnostic,
with source-cluster bootstrap ratios of resampled loss sums to state counts.

Fixed landmarks: (1) index0 for all360 sources; (2) first actual Act1 observation
with floor>=8; (3) first actual Act1 observation with floor>=16. One observation
per reached source per landmark, no future-length weights. Runs dying before a
landmark are reported as not reached, never assigned invented states/labels.
Report source counts, Heart counts, mean probability/outcome, stable BCE/Brier/
AUROC, ten calibration bins and signed probability bias mean(p−y).
Use10,000 whole-source/landmark resamples, RNG500/501/502 respectively. A landmark
is adequate only with>=100 sources and>=5 of each outcome; the initial landmark
additionally requires all360. The marginal earlyMeanBiasPass gate requires ALL3 adequate and each
bias95% interval entirely within[−0.05,+0.05]. Five percentage points is a
prospective coarse absolute-error tolerance, not proof of conditional calibration, early ranking or decision utility. A constant
predictor can pass this marginal gate.
Intervals are pointwise, not a claim of simultaneous full-model calibration.
No calibration slope/temperature/bias fit or post-hoc new landmarks.

Verdict order: insufficient total classes→INSUFFICIENT_TEST_CLASS_COVERAGE;
aggregate criterion unmet→NOT_SHOWN; aggregate met but early gate unmet→
HOLDOUT_SIGNAL_CALIBRATION_NOT_SHOWN; both met→OFFLINE_HOLDOUT_PASS.
Regardless of verdict, this is fixed-behavior actual-trajectory prediction only,
not native leaf/public parity, counterfactual support, optimal value, gameplay or
speed qualification. No automatic native integration follows a PASS.

Independent exact-result/custody review precedes ledger/KB and scoped draft PR.
Preserve §497/498 evidence, record the precise verdict unchanged and stop before
native integration. Knowledge impact: holdout evidence/calibration boundary and
single-use evaluation procedure; no default change.
