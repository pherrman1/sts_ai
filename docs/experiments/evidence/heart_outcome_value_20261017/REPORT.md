# §498 — nonlinear Arm C head on observed Heart outcomes

**VALIDATION_ONLY; positive development comparison against the constant baseline.**
A 4,225-parameter value head learned useful outcome information on the frozen
Arm C representation. This is not a qualified native leaf, calibrated start-state
win probability, gameplay improvement, TEST result, or AlphaZero training loop.
Independent implementation/design and exact-result/custody reviews PASS.

## Data and fixed behavior

Reuse only the independently audited §497 recovered corpus: 1,080 TRAIN sources
(126 Heart wins, 171,442 states), 360 VALIDATION sources (47 wins, 56,704 states).
All observations are actually visited public driver boundaries in completed
A20 Ironclad Heart runs. Each state's label is its run's observed Heart outcome.
The 41 original deliveries and 8 replacement halves are unchanged. The data
transport branch `claude/heart-outcome-data` at `e3b649c` is never merged.

The collection policy remains exact native 10k project-fair Silver real combats,
Arm C tree prior and rollout policy, calibrated A20 CTM, rollout3/public X2-B
search guidance, 512 OOC simulations/earlystop1, keys/full-run. X2-B never supplies
these new training targets. No new game seeds were run for this experiment.
All 49 TEST archives and 4 superseded partials remain opaque hashes only.

## Fixed fit and selection

The original Arm C checkpoint/trunk/policy remain frozen. TRAIN-only,
source-balanced feature normalization feeds 64 → 64 ReLU → 1 logits, interpreted with
sigmoid. Source-balanced BCE gives every source equal total weight and divides
that weight across its states. Two initializations, 0/1, each completed exactly
2,000 AdamW updates;40 validation checkpoints in total were considered. Minimum
validation BCE selected initialization 1, step 300. Initialization 0 independently
selected step 300 with validation BCE 0.3512420. No adaptive extra fits occurred.

| Source-balanced metric | TRAIN selected | VALIDATION selected | VALIDATION constant |
| --- | ---: | ---: | ---: |
| BCE / log loss, lower better |0.312713|0.350551|0.388347|
| Brier, lower better |0.090373|0.103368|0.113704|
| Weighted state AUROC |0.749243|0.715277|0.500000|

The constant is TRAIN's source win rate 126/1080 = 0.1166667. Validation reductions
are 9.73% BCE and 9.09% Brier. Paired whole-source 1,000-resample bootstrap selected
minus constant: BCE −0.0377961, descriptive 95%[−0.0557265,−0.0194511];
Brier −0.0103355,[−0.0172529,−0.00358405]. These are descriptive after validation
checkpoint selection, not independent confirmatory intervals.

## Limits that matter for a future leaf

| Current act | States | Model BCE | Constant BCE | Model AUROC |
| --- | ---: | ---: | ---: | ---: |
|1|24209|0.275951|0.284352|0.577098|
|2|18811|0.355614|0.386661|0.706955|
|3|12017|0.537666|0.640449|0.666817|
|4|1667|0.652038|1.004078|0.666139|

Act 1 discrimination remains weak. Act 4 mean prediction 0.3748 is below its
conditional weighted outcome rate 0.4347. The train/validation loss gap remains.
Two initializations on the same data are not independent data replications.
No exact native X2-B baseline was fabricated from clipped public records.

**Calibration population:** source-uniform then within-run-state-uniform
sampling differs from visitation weighting or fixed-landmark sampling. Inverse
*total future trajectory length* can change conditional outcome probabilities.
Thus the head estimates outcomes under this registered weighted state population;
aggregate gain does not establish calibrated native `V_pi(s)` or initial-run win
probability. Act/screen diagnostics condition that global weighted population,
without separately equalizing sources within each subgroup. Fixed-landmark
calibration needs a separate prospective protocol; no reweighting or retraining
was added after these results.

Original encoder limitations remain: public battle/memory extras are ignored;
public-record/native parity and counterfactual CTM leaf support are unqualified.
The supervised distribution is the fixed collector's actual trajectories, not an
improved or optimal policy. The §497 recovery/export and cross-CPU limitations
remain unchanged. No deployment or inference-speed conclusion follows from fit
throughput. A reviewed one-shot TEST/calibration evaluation is the next evidence
step; native integration remains outside this completed task.

## Preserved software fault and prospective repair

V1 source `449573acd77300f3e8a68fb39da64a2166472ed2` encoded all 228,146 states in
359.96 s, then failed at the first CUDA multinomial call: strict deterministic
CUDA cumsum is unsupported by the installed Torch. No loss evaluation, optimizer
update, candidate score/checkpoint or TEST opening occurred.
**INVALID_SOFTWARE_BEFORE_UPDATES** is retained with its latches, failure, exit,
log and cache. It is not a negative model result and was not resumed.

A separately reviewed prospective v2 source
`c7e857216cd2c450c388c265c1951e5d97cc25e8` changes sampling to deterministic CPU
multinomial from the same source-balanced distribution, with indices copied to
GPU. Actual CUDA ten-update repeatability passes before launch. The unchanged
v1 cache is reused only under exact cache/freeze/source/runtime/import/companion/
failure bindings and fresh exclusive latches. Both fixed fits then complete.
The full validation encoder pass is still repeated after fitting.

V2 exits 0 in 106.899 s; fitting takes 5.118 s, cache/parity/provenance work 97.941 s.
The external 4,200 s TERM/10 s KILL guard and original phase caps remain in force.
These are local RTX 3060 Ti offline timings, not single-leaf inference latency.
All 79 original Arm C tensors, validation pooled features and policy logits are
bitwise equal. Cached versus composed head probability max error 5.96e-8.

## Identity and reproducibility

- Original Arm C checkpoint SHA256:
  `53739a4375380001fce0323935c187906b5c1d5efd65691f9d75f2dd8884e020`.
- Encoder silverbot: `84ab3ead9d88c01c4be09a6773fb9a947f57d5ff`; exact Python,
  compiled binding, Torch/CUDA libraries, driver and runtime hashes in freeze.
- V2 freeze:`b5d2e023ecb4c4ba8ff82c827c43a0aa4c5a11b5d5106d5bec79c0984d2b2a44`.
- Result:`eeee2c1ace7382fa5fa3c4f51b4caeb6e08ea3d04bc54553d299e7f7e22c356c`.
- Selected checkpoint:`68c20b521b53a72896293b72442839eb5abfbb7c43222030556874b0a7593de1`.
- Portable head:`2c478bca6692e8c69cd70c78cf7cf1758c07c3ed884a97bb64d813424019942c`.
- Original/reused pooled cache:
  `a066eb69a74c16fc5e2d4e75b3c269937e269be1b82e5d2cbfb667cdbd442a25`.

[Protocol](PROTOCOL.md),[freeze](freeze.json),[command](command.json),
[result](result.json),[portable head](head.json),[source/recovery review](source-reviewed.json)
and[result review](result-reviewed.json) are the compact evidence packet.
Raw original checkpoints/caches/process receipts remain under
`/home/philippherrmann/Documents/sts/sts_lightspeed/build/heart-outcome-value-20261017-v1`
and sibling `heart-outcome-value-20261017-v2`; never rerun their consumed latches.

Focused Python 41/41 PASS in 1.265 s, independent 14/14 PASS in 1.194 s plus six recovery
negative cases. Independent cached-head CPU recomputation reproduces both splits,
selection/normalization/bootstrap and archive/seal custody; the full encoder
parity is reviewed guarded-run evidence, not an independently repeated pass.
No C++ code changed; full native build/gameplay/TEST/inference benchmarks were
not run. GitHub Linux GCC is not claimed by these local Python checks.

**Knowledge impact:** current result/limitations, source-calibration boundary,
offline fitting/recovery procedure and tool routing. No production baseline or
prior experiment verdict changes.
