# §500 — TRAIN/VALIDATION weighting ablation

User authorized testing the proposed weighting hypothesis after §499. This is a
new development experiment, not a retry of the consumed TEST. No TEST artifact,
archive, prediction or outcome is read; no native integration, fresh gameplay,
collection, RL, original policy/trunk updates or default change. Preserve §499's
HOLDOUT_SIGNAL_CALIBRATION_NOT_SHOWN unchanged. Stop and report before native work.

## Question and fixed controls

Hypothesis: giving every recorded state equal training weight, rather than
inverse final trajectory-length weight within equally weighted sources, reduces
early underprediction while retaining useful all-state predictions. Alternatives
include frozen representation limitations, few independent wins, and selection
noise. This isolates training sampling/loss weighting; it cannot identify an
optimal deployment population or qualify counterfactual CTM leaves.

Reuse the independently approved §498 v2 development feature cache, byte hash
`a066eb69a74c16fc5e2d4e75b3c269937e269be1b82e5d2cbfb667cdbd442a25`.
TRAIN is exactly 1,080 sources110180000–110181079,171442 states,126 wins;
VALIDATION360 sources110181080–110181439,56704 states,47 wins. All are actual
healthy full-run Heart outcomes under fixed exact10k Silver, Arm C prior+rollout,
calibrated A20 CTM. §497 importer remains the provenance authority. Bind exact
import report/review/source manifest and §498 freeze/result/result review/head;
validate full cached ownership, labels, per-source order and counts. The cache
binds act/floor metadata and pooled features. No raw archive access is necessary.
The four superseded partial archives remain untouched. Existing recovery/export
and unverified cross-CPU parity limitations remain. No labels enter encoder inputs.

Freeze original Arm C checkpoint53739a43…e020 and encoder84ab3ead, exact
encoder/runtime/dependency and new tool/tests/protocol hashes. Reuse unchanged
§498 TRAIN-only source-balanced normalization buffers, not new arm-dependent
normalization. A new 64→64 ReLU→1 head (4225 params) is trained from scratch;
original Arm C and policy are accessed only through unchanged cache/model bytes,
with no encoder forward or gradient. Cached policy hashes are recorded. This
experiment makes no new composed-forward/public-native parity claim.

## Fixed paired grid and checkpoint selection

Two arms: source weight1/(1080 × observations in source), and visitation weight
1/171442. Sampling with replacement from normalized float64 CPU weights makes
unweighted minibatch BCE an estimator of the chosen objective. Same minibatch512,
AdamWlr0.001/weightDecay0.001,2000updates, check every100. Two inits0/1 per arm:
exactly four fits/8000updates/80 checkpoint records, no extension, temperature
fit, alternative head or additional seeds. Every paired initialization has
identical initial tensors, frozen normalization and bias logit(126/1080). Its
independent CPU sampler generator is seeded with that init in both arms; actual
sampled indices differ because distributions differ. All RNGs here are training
or statistical RNGs, not new game seeds.

Both arms select minimum COMMON validation visitation-weighted stable-logit BCE;
earlier step wins ties, then init0. This control is retrained under the same
selection rule as treatment and is not the unchanged §498 selected checkpoint
(which used source-balanced validation selection). Do not conflate those comparisons.
Save all four best checkpoints, all histories and selected TRAIN/VALIDATION
logits. Inits are optimization repeats on the same sources, not independent
corpus replications. Validation is reused development data.

## Measurements and prospective interpretation

For each selected arm report TRAIN/VALIDATION visitation and source-balanced
BCE, Brier, AUROC, ten-bin marginal calibration. The fixed TRAIN constant126/1080
is a reference, never a fit to validation. Separately report the same three
predefined actual early landmarks: index0, first Act1floor≥8, first Act1floor≥16;
one record per reached source, no invented states for sources not reaching one.
Report counts/wins/not-reached, proper scores/AUROC, signed mean bias and10000
source bootstrap interval (RNG500/501/502). Adequacy≥100sources,≥5of each class;
start additionally requires all sources. The descriptive mean-bias interval must
be entirely within±.05 to pass that marginal gate. It does not establish
conditional calibration or ranking; a constant may pass it.

Primary development verdict: VALIDATION_WEIGHTING_SIGNAL only if treatment's
selected validation visitation BCE AND Brier are strictly lower than control,
and all THREE landmark absolute point mean biases strictly smaller. Otherwise
VALIDATION_WEIGHTING_NOT_SHOWN. Report gates separately; no automatic promotion
from either verdict. Also report treatment-minus-control BCE/Brier with10000
paired uniform source-cluster ratio bootstrap resamples (RNG500), plus paired
landmark mean-prediction changes (RNG510/511/512). Intervals are descriptive,
pointwise and do NOT adjust for checkpoint/arm selection or reused validation;
no new holdout/generalization/causal calibration claim. Other diagnostics never
change the fixed rule. Future confirmation needs genuinely fresh prospective
holdout evidence, not the now-consumed TEST.

## Custody, limits and completion

Independent implementation and scientific design PASS precedes a clean frozen
commit and exact approval binding source/tool/protocol. Runtime matches §498:
local RTX3060Ti,2CPUthreads, deterministic CUDA float32/TF32off/CUBLAS4096:8 and
CPU sampling. Reusing features avoids ~6minutes of redundant encoding. Four
fits should take seconds; local compute is sufficient. Cooperative600s for fit
and analytics, external900s TERM+10sKILL for run including hashing; no resumption
or automatic retry. Exclusive fit-started latch before optimization; retain any
failure and all old runs. Recheck source/runtime/cache/model hashes afterward.
No active collection or evaluation campaign is restarted.

Independent exact-results/custody review, raw evidence, ledger§500, maintained
research/pipeline/tool routing and scoped draft PR complete this task. Knowledge
impact: development weighting evidence and consumed-TEST boundary; no default.
