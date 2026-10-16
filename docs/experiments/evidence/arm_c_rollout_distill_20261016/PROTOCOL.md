# §494 Arm C rollout-target distillation (2026-10-16)

Status: prospective. Baseline main `bcdfaedd3044d6da351c084adb540f94a3fe0ebf`.
User authorization: continue distillation using Arm C for both tree prior and
rollout decisions; local CPU/GPU, independent review and PR merge are authorized.
The §493 greedy-policy pilot remains NOT_SHOWN. Choosing this teacher for
research does not establish better gameplay or promote a production default.

Hypothesis: public-input value students can compress the expected three-combat
continuation under Arm C, preserving sibling action ranking more cheaply than
replaying that policy. The baseline remains X2-B on the SAME fresh leaf states.
The one conceptual intervention relative to §491 is the rollout teacher policy;
the source distribution consequently changes. This is not a paired comparison
with historical §491/492 or a comparison of true Heart-win probabilities.

Inventory: preserved §491/492 has 64 V4-rollout sources, six fits and an opened,
software-fault-recovered TEST with NOT_SHOWN. Its labels are the wrong teacher
and cannot be pooled, relabeled adaptively, or reused as this study's TEST.
§493 has 32 completed paired gameplay sources, but no repeated sibling targets;
its outcomes cannot train this student. Opus §489/490 remains a frozen historical
out-of-domain reference only: old keys-off Act3 or V4 targets, unavailable raw
cloud corpus, selection using validation. Its tracked checkpoint may be reported
as a fixed diagnostic, never used to select this study's model.

Teacher: exact published Arm C d64/4 heads/256 hidden/2 layers/trim1, native
SHA256 `eff2f74f57dc2f566bbd44be30988592503cc8db51e51ff1e70cd2dec4636509`,
checkpoint `53739a4375380001fce0323935c187906b5c1d5efd65691f9d75f2dd8884e020`
from `68fe88be8271fa1f9b515f7a9abcf0fb9755e25f`.
Set `STS_OOC_MCTS_PRIOR=heart1`, `STS_OOC_MCTS_LEAF_POLICY=heart1` and load
`studentc.bin`. Retain mandatory Heart/key rules, existing legal candidate set,
argmax and fallback semantics from §493. Verify actual model load, >=90% scoring
among attempted qualified tree-prior calls AND rollout calls, positive scored
counts, and zero legacy V4 prior-leaf steps on every source/canary.

Forked label generation additionally records `rolloutPolicy`, `heart1RolloutSteps`
and `heart1RolloutFallbacks` around the 64 repeats only, excluding the scheduled
search leaf and annotation/long-rollout work. New-study row validation requires
`heart1`, nonnegative integer counters and >=90% scoring if any attempts occur.
A terminal or rule-only row may have zero calls; each source must have positive
Arm C scoring among its retained repeated labels. Drop the entire captured
parent if any captured sibling is invalid. Metadata/counters are never inputs.

Regime: A20 Ironclad, collect keys, full Heart objective, project-fair native
Silver for real combats with EXACT 10000 root simulations, allocated reuse cap
32768, adaptive/learned stopping and direct learned leaves off. Calibrated A20
CTM, native X2-B leaf, 3-combat continuations, OOC source search 512 simulations,
fixed early-stop=1, PUCT1.5, widening K4/alpha0.75, depth32, visits selection,
temperature1 and tree rules1. CPU_SECONDS is UNSET: wall/CPU-timed stopping cannot
be combined with capture or prove observational parity. This source collection
is not the §493 matched-CPU gameplay experiment.

Capture: every fourth searched decision, max64 captured leaves/root, depth<=1,
64 fresh repeat rollout3 labels/leaf, no rollout5. Record schema
heart1-public-record-v2, public fixed observation/deck/upgrades/relic counters/
potions/offers/actions/map links/burning elite and current public battle/memory
extensions. No seed, RNG, parent/action identity, outcomes or teacher costs in
features. X2-B is an explicit scalar residual input. Public/native input parity
is unqualified; offline success cannot authorize deployment.

Canaries: `110162994` capture OFF/ON for exact decision-trace/action byte parity
(timing excluded), then `110162995` capture ON. Max1200s/unit. Both require
nonempty multi-action sibling groups, >=80% valid rows, runtime and repeated-label
policy contracts. Stop on any crash, mismatch or failed gate. Independent review
of source/design precedes launch; a second independent canary/custody PASS bound
to freeze.json and canary.json is required before the cohort. Review wait cap
1800s; no automatic approval. No canary replacement/retry in this protocol.

Fresh cohort: 64 source seeds `110163000..110163063`:
TRAIN `110163000..039` (40), VALIDATION `110163040..047` (8),
TEST `110163048..063` (16). No replacement, extension, pooling or adaptive seeds.
Three single-thread workers, max1200s/source clamped to remaining21600s cohort
wall cap. Arm C inference is materially more expensive than the old V4 teacher;
these limits allow a bounded local campaign without changing label/model grids.
All seed commands use the copied repository seed guard. Preserve incomplete
runs; missing sources stop fitting/TEST. Source receipts/hashes only may be read
for TEST before selection; raw TEST JSONL stays opaque until its opening latch.

Fit protocol is unchanged from §491/492: counts MLP, pooled typed token means,
and dim64 two pre-norm transformer layers/4heads/FF128 attention; two
initializations 0/1 each. Public encoder and clipping fixed; vocabulary fitted
TRAIN only. Same residual logit head with two hidden128/ReLU layers; within-parent
centered MSE +0.1 absolute MSE, AdamW lr0.001/decay0.0001,30epochs, whole-parent
batches <=512 leaves, dropout0. VALIDATION alone selects model/epoch and X2-B
blend weights0.25/0.5/0.75/1 by per-source action regret quantized1e-6, then MSE,
then fewer parameters. No selection using TEST or Opus diagnostic. Six fits only.
Fit wall cap1200s including preprocessing, <=2GiB estimated CPU tensor allocation,
conservative GPU allocation <=min(4GiB,80% free VRAM), no adaptive architecture or
batch changes. Local RTX3060Ti may be used; no cloud or student-driven rollouts.

Require >=500 TRAIN/100 VALIDATION complete multi-action groups, >=80% retained
rows and a multi-action group from every source before fitting. Freeze metadata-
only corpus hashes, selected weights/vocabulary/blend and tool/runtime/model/
source/binary/build/protocol identities before TEST. Exclusive test-opened.json
is created before its first JSONL parse. One TEST, max600s; no automatic retry.
Require >=200 complete TEST groups, >=80% valid rows and all16source coverage.

Primary offline candidate gate: concordance gain >=0.02 over X2-B, regret <=0.9x
X2-B, source-bootstrap regret-improvement95% lower bound >0 (2000 resamples,
RNG20261016), AND >=4x measured end-to-end Python compression including encoding,
vectorization, inference and required X2-B. Positive finite teacher CPU required.
Aggregate leaves per distinct action before sibling comparison, then aggregate
by source. MSE, strata/noise, batch1/32 latency, frozen Opus and fixed 50/50
single-scheduled-rollout hybrid are descriptive. Tensor-only speed is insufficient.

Record exact OFFLINE_CANDIDATE/NOT_SHOWN/INSUFFICIENT or execution failure unchanged.
Even OFFLINE_CANDIDATE requires a separately frozen native parity, speed and
matched-CPU gameplay study before runtime promotion. No native student port,
default change, new cohort from a failed gate, AlphaZero or iterative RL loop.
All old bundles remain immutable. Ledger §494, evidence and maintained research
status are the durable destinations; temporary process state remains local.
