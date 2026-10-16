# §498 — observed Heart-outcome value head, frozen Arm C

Hypothesis: a small nonlinear head on Arm C's fixed pooled representation can
predict observed full-run Heart returns better than the TRAIN win-rate constant
on disjoint VALIDATION sources. Alternatives: the frozen policy representation
lacks necessary value information, or the 126 TRAIN wins are insufficient.
This is an offline development experiment, not leaf/gameplay qualification.

Use only the independently audited §497 recovered corpus: 1,080 TRAIN sources
110180000–110181079 (171,442 states), 360 VALIDATION sources
110181080–110181439 (56,704 states). The accepted 41 originals and 8 replacement
halves, import review, manifest and trajectory/archive hashes are immutable.
All 49 TEST and 4 superseded partial archives are opaque bytes only. Reuse the
completed import audit; rehash the raw archives and verify individual trajectory/
receipt hashes while encoding, rather than rerunning the full audit for each fit.
No additional game seeds, source replacements, old surrogate data/cache or TEST.

Original Arm C checkpoint 53739a4375380001fce0323935c187906b5c1d5efd65691f9d75f2dd8884e020
and pinned silverbot 84ab3ead9d88c01c4be09a6773fb9a947f57d5ff supply a frozen
64-dimensional pooled representation. Preserve all checkpoint tensors exactly.
Use original trim-map preprocessing and a genuine TRAIN choice companion for
empty-choice batches; discard companion outputs. Record the first eligible
TRAIN companion source/index/public-record hash. Only public records enter the
encoder. Seed, terminal label, final floor and provenance remain outside it.
Extra public battle/memory fields are not encoded by this original encoder.
This does not qualify public-record/native parity or counterfactual leaf support.

Fit exactly two initializations (optimizer RNG 0,1), architecture
64→64 ReLU→1 sigmoid probability (4,225 trainable parameters).
Normalize features using TRAIN-only, source-balanced mean and variance, floor
standard deviation at 1e-6. Binary cross entropy against each run's completed
Heart-kill indicator. Every source has equal total weight; states within a source
share that weight. No class rebalancing, X2-B input/residual or policy training.
AdamW lr .001, weight decay .001, batch 512; sample states with replacement on CPU from
source-balanced weights (indices moved to GPU for fitting); exactly 2,000 updates per initialization. Evaluate every
100 steps; choose the lowest source-balanced VALIDATION BCE, ties by earlier
initialization/step. Save both candidates and all 40 checkpoint metric records.
No adaptive hyperparameters, extra fits, early stopping or resumption/retries.

Baseline: constant TRAIN source win rate (126/1080). Report source-balanced BCE,
Brier, weighted AUROC and ten-bin calibration; BCE is always computed stably
from logits without clipping loss; by current act and screen, plus
per-source losses. Subgroups condition the globally source-balanced state
population; they do not separately equalize sources within each subgroup. Diagnostic 1,000 paired whole-source bootstrap resamples,
RNG 498, for selected-minus-baseline BCE/Brier; intervals are descriptive after
validation selection, not independent confirmatory significance. No exact X2-B
comparison can be reconstructed from clipped public inputs. Compare TRAIN/VAL
loss to expose overfit. Primary development signal is BOTH BCE and Brier below
the constant; result remains VALIDATION_ONLY regardless of that signal.

Source/design review must PASS before committing/freeze/encoding. Freeze exact
clean source, tool/test/protocol, import report/review/manifest, original model,
encoder/dependency and Python/Torch/CUDA runtime hashes; verify them before and
after. Exclusive cache/fit latches prohibit implicit restart. Local RTX3060Ti,
two CPU threads, deterministic float32 CUDA, TF32 off, CUBLAS :4096:8. Encoding/
validation repeat cap 3,600 seconds; fitting cap 600 seconds. Launch under
`timeout --signal=TERM --kill-after=10s 4200s` for an external total hard cap;
record exit status and preserve failures, with no implicit retries. Stop on any failed
identity, coverage, finite-value or wall gate; preserve artifacts. VALIDATION is
encoded again after fitting to verify identical pooled features and policy logits,
and composed head predictions against the cached head. Check frozen tensors
bitwise. Optional diagnostic Python timing only; no native speed claim.

Independent exact-result/custody review precedes documentation/PR completion.
Stop and report before native integration, TEST opening, gameplay, RL or default
promotion. Recovery/export and cross-CPU limitations from §497 remain unchanged.
Knowledge impact: current research status and offline fitting procedure.


## Prospective v2 software-fault recovery

V1 completed both fresh feature encodings (359.96 seconds), then failed at the
first CUDA sampler call before loss evaluation or any optimizer update. PyTorch
2.5.1 CUDA cumsum does not implement the requested strict determinism. No
candidate checkpoint, validation model score or TEST content was produced.
Preserve v1 freeze/cache/latches/failure/exit/log unchanged, classified
INVALID_SOFTWARE_BEFORE_UPDATES. This is not a negative model-quality result.

V2 changes only the sampling implementation to deterministic CPU multinomial
with the same source-balanced distribution. A real CUDA ten-update repeatability
regression must pass before launch. Reuse the exact v1 public feature cache
SHA a066eb69a74c16fc5e2d4e75b3c269937e269be1b82e5d2cbfb667cdbd442a25,
bound to original source449573acd77300f3e8a68fb39da64a2166472ed2,
freeze fbe456e5fca242e6c9e0da6728813a18cffc6295098a8909372d974d16d6932e,
parent failure/exit/log, import custody, encoder/runtime and companion identity.
Validate cached public metadata against every source's audited label/count/order.
A separate recovery approval and new reviewed clean SHA/freeze/exclusive latches
are required. Use a new v2 root; never clear or resume v1. No new source collection,
score-guided change, hyperparameter/grid extension, TEST read or native integration.
Full VALIDATION re-encoding/policy/tensor parity remains required. All scientific
choices, 2×2000 updates and budgets above are unchanged. No implicit v2 retry.
