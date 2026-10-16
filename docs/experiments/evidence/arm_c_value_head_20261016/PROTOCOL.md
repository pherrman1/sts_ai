# Arm C frozen-encoder value-head fit

User authorized fitting Arm C's existing value head on the collected targets,
after inspection established that the original Arm C distillation optimized
policy KL only (`tools/distill.py`, original checkpoint commit `68fe88be`).
No native integration, gameplay, new source collection or RL loop is authorized
by this protocol. Prior §491–494 verdicts remain unchanged.

## Hypothesis and scope

Arm C's policy-trained representation may support a useful cheap value estimate
through its existing affine value head. Alternative: the representation lacks
the needed value information and freezing it prevents a useful fit. Only
`value_head.weight` (1×64) and `value_head.bias` (1) may change. Shared encoder,
policy, auxiliary head and `value_head_norm` stay byte-identical. This is a
65-parameter linear probe using the existing dual-head architecture.

## Existing evidence and custody

Use completed §494 native corpus manifest
`cd8929b1226531390d06a6c38250065f9d6e37d00c1903dd688b9ae4c5f11c19`,
and only `corpus-train-validation.tar`, hash
`03d29264509ae66d934690c163415436e955660e73505902298e33df80380686`.
Verify its per-source archive, share receipt, local receipt and capture hashes.
TRAIN is exactly `110164000..039` (40 sources); VALIDATION exactly
`110164040..047` (8). The original 16 TEST sources remain retired: the tool has
no TEST subcommand and never opens or hashes their sealed archive. Do not use
the interrupted local §494 corpus, prior V4-rollout corpora, §493 gameplay or
Opus value-reference targets. Existing completed §494 TRAIN/VALIDATION satisfy
the requested Arm C teacher and coverage; recollection is unnecessary.

Load exact original Arm C checkpoint SHA256
`53739a4375380001fce0323935c187906b5c1d5efd65691f9d75f2dd8884e020`.
Use the existing silverbot checkout `84ab3ead9d88c01c4be09a6773fb9a947f57d5ff`,
bind all local silverbot Python sources and compiled module by hash. Load the
checkpoint strictly (dim64, 2 layers, 4 heads, FF256). Trim passed map rows as
in the original Arm C training; use silverbot's own encoder, mask and pooling.
No surrogate token encoder, seed or hidden RNG input is supplied to the network.
Labels are the mean of 64 independent Arm C/CTM rollout3 continuation values
ending in X2-B; they are **not actual Heart outcomes**. Capture records retain
their existing `recordPublicParityQualified=false` limitation.

## Fit, resources and decision

Freeze reviewed source, model/corpus/tool/dependency/runtime identities before
fitting. No game seeds run. Local GPU encodes each TRAIN/VALIDATION row once in
fixed batches of32, eval mode, float32, deterministic kernels, no TF32. Cache
the existing pooled64 representation. Local CPU solves source-balanced least
squares with a free bias and L2 weight penalty at exactly
`alpha = [0, 1e-6, 1e-4, 0.01, 1, 100]`. No architecture or optimizer search.
Each source contributes equal total MSE weight. Select the candidate with
minimum source-balanced **raw-output VALIDATION MSE**, ties in alpha order.
Cast fitted head to checkpoint float32 before validation and saving.
Fit cap1800 seconds enforced by an external `timeout --signal=TERM
--kill-after=10s 1800s` wrapper as well as cooperative internal checks; two CPU
threads, no retries/resumption/adaptive expansion.
One exclusive fit-started latch precedes corpus row reading.

Report raw MSE plus [0,1]-clamped sibling concordance/regret against X2-B,
initial untrained head, and TRAIN-mean constant using the existing source-
balanced metrics. These are development/validation diagnostics, not fresh
holdout qualification or a gameplay win claim; verdict is `VALIDATION_ONLY`.
Whole VALIDATION forward pass after replacing the head must preserve policy
logits and pooled features bitwise and match cached-head values within1e-5.
All checkpoint tensors other than the two permitted keys must be exactly equal.
Record checkpoint/cache/freeze/custody hashes and raw outcomes. Preserve failed
attempts, and stop on any identity, support, parity or budget failure.

Success means a trained reproducible checkpoint and honest validation evidence,
even if the frozen representation performs poorly. It does not authorize
native deployment, a32-seed pilot, default changes or joint RL training.
