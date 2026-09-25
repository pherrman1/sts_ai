# Current research status

Last verified: 2026-09-25 for the `v_win` terminal-pricing post-review additions,
the corrected Silver rollout-cost protocol and default-off status, and correction
review of the merged DeepSets Brew-fallback quality-confirmation preparation;
2026-09-24 for the experimental DeepSets Brew-fallback mechanism/timing smoke;
2026-09-23 for the frozen Silver prior online gameplay screen;
2026-09-21 for the complete frozen Silver internal-node FPU cohort and local 80-source learned-prefix scale validation;
2026-09-20 for the tactical-prefix Silver oracle headroom screen
and contextual first-action Silver selector headroom/policy screen; 2026-09-19 for forced-action historical artifact recovery and
the PR #247 evaluator preflight; 2026-09-18 for the OOC 20% gap-stop quality
gate and frozen
six-arm Silver root-mechanism replay;
2026-09-17 for shared transition-encoder historical chronology,
staged retained-root adaptive Silver N32 scalar sweep and N16 Pareto held-out inspection;
2026-09-16 for retained-root adaptive Silver deployment-gate N32,
final near-full support/native qualification,
paired old/new-V2 OOC MCTS gameplay, and shared transition-encoder distillation;
2026-09-14 for exact supported-v1 RNG continuation
and the stochastic signed-HP distribution, expanded-support offline composition,
and fresh64 fixed10000 live MCTS gate;
2026-09-13 for the Phase-2 stochastic persistent-state support
audit and the corrected whole-combat transition model rerun after independent
review;
other sections retain their prior verification and linked evidence.

**Vendored Silver removed (2026-09-25, [ADR-0022](../../../decisions/0022-remove-vendored-silver.md)).**
Every Silver research line below that ran in the vendored model — forced-action
targets, rollout variance, first-action and tactical-prefix selectors,
learned prefixes, Phase-A policy/value, budget/reuse-cap, visit-lock/rho
stopping, root mechanism, internal-node FPU, the learned root prior, and the
§349 rollout scratch piles — is closed: its tools were removed and its results
are history. Reopening one means porting it to native Silver first. OOC research
contracts now bind native Silver teachers.

## OOC 20% gap-stop quality gate

The merged opt-in rule `512 -> stop when the top-two root visit gap is at
least 20%, otherwise continue toward 2,048` has **mechanism/speed PASS** and
the final independent quality confirmation is **`OOC_GAP_STOP_20_FINAL_PASS`**.
At frozen source `495fa147517fdc42e631c513bde5a87b3bb25144` and the exact
control/treatment configuration, the 16-pair OMP1 smoke reduced total OOC
simulations by 41.4%, median MCTS CPU by 36.6%, and median full-run CPU by
13.0%. Its 9/16 treatment versus 10/16 control result is smoke-only (three
control-only versus two treatment-only wins) and is not a gameplay-quality
conclusion. The full `12003000..12003063` quality gate did not complete:
control seed `12003058` became a long-tail runtime pathology under OMP12;
isolated OMP1 reproduction also exceeded the bounded runtime without a
completed row, while four other OMP12-to-OMP1 control parity checks matched
all non-time MCTS counters and outcomes. The pathology boundary is unknown.
No evidence from this incomplete cohort supports rejecting the 20% rule; its
quality result is unresolved and it authorizes no default promotion.

The original `12003000..12003063` cohort remains closed as
**`OOC_GAP_STOP_20_QUALITY_INCONCLUSIVE_RUNTIME`**: control seed `12003058`
became pathological and was not replaced. Its partial rows are diagnostic
only. The independent `12004000..12004063` confirmation then completed all
128 runs under the same frozen artifact, using one OMP1 process per seed, up
to 12 external workers, and a 600-second per-process ceiling. Control and
treatment each won 44/64; the paired win-rate delta was **0.0 pp**, with
bootstrap 95% CI **[-12.5, +12.5] pp**. Discordant pairs were 16/64 (8
control-only, 8 treatment-only). Mean floor changed by **-0.75** (CI
[-2.61, +1.05]) and mean ending HP by **-6.56** (CI [-15.39, +2.13]); these
point estimates warrant attention in the final confirmation but are not a
convincing quality regression. The rule is therefore **PROMISING**, not
“equivalent”; no default promotion has yet been made.

The final independent paired cohort `12005000..12005127` completed all 256
processes with valid provenance and clean exits. Control won 95/128 and
treatment 88/128; the paired win-rate delta was **-5.47 pp**, with deterministic
paired-bootstrap 95% CI **[-12.50, +1.56] pp** and exact discordant-pair
binomial p **0.189**. Mean floor changed **+0.06** (CI [-1.26, +1.33]) and
mean ending HP changed **-1.47** (CI [-7.01, +3.97]). Treatment produced
11,777 gap stops across all 128 seeds; control produced zero. The result is
**`OOC_GAP_STOP_20_FINAL_PASS`**: no meaningful quality regression was detected
at this bounded confirmation, combined with the previously established speed
benefit. This is not equivalence proof and does not promote the flag to the
default; independent review remains required. See [ledger §315](../../experiments/ledger-06.md)
and [the final evidence packet](../../experiments/evidence/ooc_gap_stop_20_final_20260918/README.md).
The packet also records an unresolved self-test-only RNG assertion seen when
the full Silver environment was supplied to `oocmctsselftest`; the 256 actual
gameplay processes passed runtime/provenance validation, but the assertion is
not considered cleared.

Semantic confirmation section verified 2026-09-10 at producer `a6c2abb`;
other sections retain their prior verification and linked evidence.

## Merged DeepSets CTM Brew-fallback quality confirmation

The independent 512-pair gameplay confirmation is **`PREPARATION_COMPLETE_RUN_BLOCKED`**.
The frozen source, artifacts, clean C/H manifests, analyzer, and local
mechanism/provenance checks are prepared and reviewed. No canary or quality
seed has run. The designated GCP research instance `sts-test` was not found in
`sts-ai-502709/europe-west3-c`; no replacement host or local seed run was
used. The gameplay-quality result is therefore **unknown**, and the opt-in
DeepSets treatment remains unqualified. Resume only on the designated instance
after verifying and inventorying its existing checkout and output paths. See
[the evidence and resume packet](../../experiments/evidence/deepset_entropic_brew_hybrid_confirmation_2026-09-24/README.md).

## Purpose

The [latest OOC CPU profile and exact V4-prior optimizations](../../experiments/evidence/ooc_v4_prior_uniform_leaf_optimization_2026-09-24/README.md)
profile fixed seed12002032 with V4 prior and uniform leaf policy. A singleton
prior fast path and state-prefix policy-head reuse preserve the fixed-work
trace; the singleton change reduced mean MCTS thread CPU by 7.9% against the
prefix-only build, with modest/noisy whole-process CPU movement. The separate
prefix-only comparison reduced mean MCTS thread CPU by 10.6% and whole-run
wall by 6.0%. This is one-seed runtime evidence, not gameplay-quality evidence
or a production benchmark. The [previous OOC CPU profile](../../experiments/evidence/ooc_cpu_profile_2026-09-18/README.md)
reuses only historical seeds12002032/12002033, with exact workload reproduction
and frozen opt-in instrumentation on main589a7a7. Real Silver combat accounts
for54–57% of full CPU; V4 prior/continuation inference for17–19%; all CTM
preparation for under9%. Prioritize real-combat execution and V4 inference for
future behavior-preserving speed experiments, not further CTM inference first.
No optimization or gameplay-quality conclusion was tested; measured full CPU
is3.2–3.6% above supplied Stage-B timings and is not a production benchmark.

The 8-seed OOC root-checkpoint diagnostic is complete. It preserves the live
2,048-simulation policy and uses a discarded same-root shadow search to observe
128/256/512/1024/2048 prefixes. Across 1,133 completed roots, checkpoint
agreement with final 2,048 is 92.41%, 93.65%, 95.41%, 97.18% and 100.00%;
top-two gap and observed leader stability are useful risk discriminators. On
the 898-root multi-action cohort, the conservative candidate `512 -> 2048 when
gap < 20%` retains 98.11% agreement and saves about 42.1% additional
simulations versus existing live early stopping. It is not deployed or
gameplay-qualified; singleton roots are descriptive only for this gap analysis.
One expected smoke-bomb shadow abort remains separately reported. See
[the evidence packet](../../experiments/evidence/ooc_root_checkpoints_2026-09-18/README.md).

This page routes current research work: what is active, what is plausibly
parked, what is closed to avoid repetition, and where the authoritative
evidence lives. Use [current-baselines.md](current-baselines.md) for executable
configurations and benchmark numbers, the [research graph](../research/README.md)
for topic synthesis, and the [experiment ledger](../../../EXPERIMENTS.md) for
chronology.

## Silver forced-action target and historical regression blocker

The fresh-population forced-action target audit is **`FORCED_ACTION_TARGET_PASS`**,
but the exact historical harmful-root regression remains
**`HISTORICAL_FORCED_ACTION_REGRESSION_BLOCKED_ARTIFACT_UNAVAILABLE`**. The
required frozen 64-root snapshot and its provenance hash were not recovered
from the canonical checkout, retained local worktrees, local research
directories, or the designated GCP path. The `sts-test` instance was
unavailable during the 2026-09-19 recovery attempt. Do not recollect or
substitute the historical root when it is unavailable. Local work may verify
the existing evaluator/analyzer machinery, but learned-policy training remains closed until
the exact artifact is recovered and the preregistered regression is run. The
standalone PR #247 merge commit predates the PR #246 forced-action audit and
therefore is not itself a valid evaluator snapshot for this regression.
Current `main` after PR #246 contains both the live-reroot changes and the
corrected forced-action evaluator/analyzer. When the historical artifact
becomes available, verify that the current forced-action path remains
equivalent to the reviewed PR #246 implementation before running the
regression. See
[ledger §321](../../experiments/ledger-06.md) and the
[forced-action evidence packet](../../experiments/evidence/silver_forced_action_target_2026-09-19/README.md).

## Silver rollout variance/bias diagnostic

The frozen hard-combat rollout diagnostic initially classified as
**`INCONCLUSIVE`** on the global variance/bias rules. Its bounded causal
follow-up classifies **`FIRST_ACTION_BIAS_MATERIAL`** on the targeted stable
subset. It evaluated
32 complete sibling groups / 247 leaves from the 64-root DEV snapshot set,
with 32 fixed SimpleAgent replicates per leaf and independent A/B 25k-Silver
teachers. One-rollout noise is material descriptively: 85.64% of within-sibling
teacher margins were below the one-rollout noise estimate. Moving from `k=1`
to `k=4` reduced mean teacher regret by 23.10% and improved pairwise
concordance from 0.6346 to 0.6719, but the clustered bootstrap interval did
not satisfy the predeclared variance rule; the systematic-error and
not-primary rules also failed. In the follow-up, forcing Teacher A's first
semantic action on the highest-residual leaf from each of the first eight
distinct groups removed 74.65% of aggregate absolute residual across the
three leaves whose Teacher A/B first actions agreed; the five unstable leaves
were excluded from the causal decision. This is a mechanistic finding on a
targeted frozen subset, not a policy qualification. A fresh matched
`hard64-holdout` cohort then evaluated the one narrow
`SPOT_WEAKNESS_FIRST_V1` intervention on 32 complete groups / 251 leaves (112
active leaves). The corrected result is **`INCONCLUSIVE` / not promotable**:
k=32 mean teacher regret improved from `1.8767` to `1.2212` (`34.93%`), and
the grouped-bootstrap probability of lower treatment regret was `95.37%`, but
pairwise concordance fell from `0.7049` to `0.6892`. Top-leaf agreement
improved descriptively. The <5% runtime gate is unmeasured because baseline
canonical `rollout_wall_micros` and treatment `totalWallMicros` include
different setup scopes; the raw treatment stream lacks a comparable
treatment-only timer. This does not validate the exact Spot Weakness rule or
erase the earlier targeted first-action finding; no tuning or broadening should
follow from this holdout. Do not infer a rollout-policy, model, search budget,
or default change from either diagnostic. See [ledger §322](../../experiments/ledger-06.md)
and the [diagnostic evidence packet](../../experiments/evidence/silver_rollout_variance_20260920/README.md).

The subsequent frozen-DEV contextual first-action screen is
**`FIRST_ACTION_POLICY_HEADROOM_INSUFFICIENT`** after correcting the
variance-matched comparator. Its cross-fitted first-action oracle reduced
k=32 Teacher-A regret from `1.51332` to `1.41354` (`6.59%`) across 32 groups,
with pairwise concordance `0.74241 -> 0.75176`, top agreement
`0.56250 -> 0.62500`, and Teacher-B direction consistent. The corpus contains
32 groups from 20 source seeds, with 11 source seeds shared by multiple groups;
regenerated folds/bootstrap use `source_seed` clusters where needed. The retained fixed linear selector,
trained on exact forced-action `q0` values under the historical group-id fold
assignment, produced k=1 regret `3.65020` versus `2.33796` and k=32 regret
`1.63434` versus `1.51332`; its source-seed-clustered bootstrap interval for
baseline-minus-candidate regret is `[-1.33542, 0.93203]`, with the largest
regression `14.57257`. The candidate path's raw `1.74940x` timing is
non-production-comparable because it includes diagnostic semantic-action
resolution through a fresh `BattleSearcher.search(1)`; the `<5%` runtime gate
is unmeasured, not failed. This rejects the tested feature/scoring formulation
and does not establish that all small linear contextual policies fail. Do not
tune additional selectors or launch fresh gameplay confirmation from this
result. See [ledger §323](../../experiments/ledger-06.md) and the [selector
evidence packet](../../experiments/evidence/silver_first_action_selector_20260920/README.md).

The follow-up coordinated-prefix oracle screen is **`SHORT_PREFIX_HEADROOM_PRESENT`**.
It reused the same frozen 32-group / 247-leaf / 20-source-seed DEV corpus and
allowed common semantic `CARD`/`END_TURN` prefixes of length one through three,
with canonical `CARD_SELECT` handling and fail-closed unsupported states. The
all-replicate prefix intersection evaluated 689,856 accepted rows. Cross-fitted
selection/evaluation reduced Teacher-A k=32 regret from `1.51332` to `0.56665`
(`62.56%`) at depth 2 and to `0.58686` (`61.22%`) at depth 3; Teacher-B
reductions were `29.05%` and `33.24%`. All 247 leaves had complete monotonic
coverage at both qualifying depths, and the source-seed-clustered bootstrap
intervals for baseline-minus-oracle regret were `[0.23573, 2.13812]` and
`[0.24809, 2.10558]`. The generalized depth-1 seam exactly reproduced all
40,512 paired PR #254 counterfactual rows, with zero missing/unmatched rows and
zero absolute difference.

The exact-length secondary views change the scientific interpretation: exactly
length 2 gives only `6.91%` Teacher-A reduction and a `-34.76%` Teacher-B
change, while exactly length 3 gives `48.69%` and `21.16%` respectively on
245 leaves represented across 32 groups but only 31 scorable sibling groups,
with bootstrap intervals crossing zero. Selected-length counts in
the up-to-depth-2 oracle are 148/99 and 138/109 (length 1/2) across the two
cross-fit directions; at up-to-depth 3 they are 130/49/68 and 120/45/82
(length 1/2/3). The large result is therefore evidence for variable-length
headroom, not for always forcing exactly two actions. This is an upper-bound
diagnostic, not a deployable policy: the oracle observes cross-fitted rollout
values per leaf. Do not promote a rollout policy, selector, search default,
model, budget, or gameplay behavior from this result. The next distinct
question is a bounded causal mechanism that learns both the sequence and
whether to extend the prefix, with explicit cost measurement. See [ledger
§324](../../experiments/ledger-06.md) and the [tactical-prefix evidence
packet](../../experiments/evidence/silver_tactical_prefix_oracle_20260920/README.md).

The bounded variable-prefix Phase-A screen is **`BOUNDED_PREFIX_SELECTOR_INSUFFICIENT`**.
It reused the same frozen PR #256 robust common-prefix packet and tested all
preregistered `FLAT_K1/K2/K4/K8/K16` and hierarchical
`BEAM{1,2}_K1_{1,2}_K2_{1,2}` arms with disjoint Stage-1/Stage-2 selection
replicates, explicit STOP finalists, opposite-half evaluation, and
source-seed-clustered bootstrap. `FLAT_K16` exactly reproduced the #256
up-to-depth-2 oracle (`0.56665` Teacher-A regret, `1.04505` Teacher-B regret,
and `[0.23573, 2.13812]` clustered interval). The best bounded arm recovered
only `26.82%` of measured oracle gain; its Teacher-B regret reduction was
`-38.77%` and its clustered lower bound was `-0.40184`. The cheapest beam
(`BEAM1_K1_1_K2_1`) used `9.40` mean continuation calls but recovered only
`18.30%`, with clustered lower bound `-0.24005`. Flat `K4` recovered `60.56%`
but cost `100.31` mean calls and had no positive clustered support. No arm
cleared the 50% gain, positive-CI, Teacher-B, and 12-call gate together, so
Phase B native causal confirmation was not run. The next direction is a cheap
learned pair-plus-STOP/value evaluator; do not add rollout-heavy tactical
control, use gameplay or hard64 evidence, or change Silver defaults from this
screen. See [ledger §325](../../experiments/ledger-06.md) and the [bounded
variable-prefix evidence packet](../../experiments/evidence/silver_bounded_variable_prefix_20260920/README.md).

The offline learned prefix-value experiment is **`LEARNED_PREFIX_SCORER_INSUFFICIENT`**.
It reused the frozen 6,194-candidate PR #256 surface (1,266 length-1 and
4,928 length-2 candidates), constructed causal state/action features without
provenance or card-instance identifiers, and used fixed five-fold
source-seed cross-fitting. The three preregistered arms were Ridge, a small
flat MLP, and a factorized `Q1 + Delta2` MLP; all covered 247/247 leaves and
remained below 100k parameters after the fixed 32-wide deployment bottleneck.
The flat MLP recovered `68.87%` of the frozen Teacher-A oracle gain and
reduced Teacher-B regret by `34.52%`, but its source-seed-clustered
baseline-minus-model interval was `[-0.09000, 1.83122]`, so the positive-support
gate was not met. Ridge recovered `9.20%` with a boundary lower endpoint of
`0.00000`. Review found that the original factorized Q1 loss repeated each
length-1 target once per child; the corrected arm masks Q1 supervision to
length-1 rows and recovers `-42.23%`, changes Teacher-B by `-53.29%`, and has
interval `[-1.59667, 0.71646]`. The corrected packet therefore remains
insufficient and does not qualify a learned selector. The refreshed pure
forward per-leaf timings are flat MLP `0.109/0.241 ms` median/p95, Ridge
`0.077/0.148 ms`, and factorized `0.155/0.315 ms`, with input tensors and
leaf indices precomputed outside the timers. Do not run gameplay, promote a
model, alter Silver/MCTS, or use hard64 holdout from this result; the next
research step, if pursued, is a richer causal state encoding with the same
held-out contract. See [ledger §327](../../experiments/ledger-06.md), the
[original experiment §326](../../experiments/ledger-06.md), and the
[corrected learned-scorer evidence packet](../../experiments/evidence/silver_learned_prefix_scorer_20260920/README.md).

## Silver learned-prefix scale validation (#260)

The local 80-source external validation is **`FLAT_MLP_GENERALIZATION_FAILED`**.
On the preregistered locked 40-source cohort, recovered-oracle fractions were
negative for all three fits: TRAIN20 `-98.76%`, TRAIN40 `-106.19%`, and TRAIN60
`-108.21%`. This is not a case where adding more training seeds repaired the
frozen MLP: all five TRAIN60 initialization diagnostics were negative. The
selected locked corpus had complete baseline32, Teacher-A/B, and prefix
coverage for **525/525 leaves**, with exact 40 locked source seeds represented.
This is bounded offline evidence only; it authorizes no native integration,
gameplay qualification, model retraining, search change, or default promotion.
See [ledger §329](../../experiments/ledger-06.md) and the
[scale-validation evidence packet](../../experiments/evidence/silver_prefix_scorer_scale_20260920/README.md).

## Silver policy/value Phase-A cost diagnostic

The corrected clean-baseline result is **`PV_COST_NOT_FEASIBLE_CLEAN_BASELINE`**:
the conversion-inclusive candidate was much slower than the approximately
3-microsecond clean `PLAYER_NORMAL` rollout. A bounded stage decomposition on
the same fixture measured 1.242 microseconds for conversion, 40.944 for
feature/vector preparation, 72.158 for the `1768 -> 64 -> 64` encoder plus
value head, and 4.212 for action scoring. The neural stage alone is therefore
about 24.2 times the rollout cost. Do not pursue a conversion-only
Silver-native representation for this exact model boundary; no training,
runtime, gameplay, or default change is implied. See
[ledger §290](../../experiments/ledger-06.md) and the
[Phase-A evidence packet](../../experiments/evidence/silver_policy_value_phase_a_2026-09-16.md).

The bounded parity-preserving sparse evaluator screen is now also closed for
per-leaf throughput: it computes the same outputs at 6.377 microseconds per
model-plus-action call, versus a 2.981-microsecond clean rollout mean. It is a
valid optimization of the dense function, not a throughput win. Do not extend
the adapter/native-state optimization under this hypothesis; root-only learned
guidance is the next distinct direction. See
[ledger §292](../../experiments/ledger-06.md) and the
[sparse evaluator evidence](../../experiments/evidence/silver_sparse_evaluator_2026-09-17.md).

## Silver budget comparison at selected 128k cap

The requested four-arm paired 32-seed comparison is complete at fixed 128k
lazy GC. Flat 1k / 1/2/5k / flat 10k / 10/20/50k win 17/20/21/24 of 32;
average seconds/run are 2.65/6.62/31.36/81.46. The targeted low schedule has
an attractive descriptive cost/outcome point (one fewer win than flat 10k at
about one-fifth runtime), without established quality equivalence. The highest
schedule has most observed wins, substantial extra compute, 4.34 GiB peak
four-worker process RSS, and 252 retained-cap fallbacks. All six exact paired
tests have adjusted p>=0.3926; no established ranking or default/model
qualification. Zero bridge failures and full budget/config/seed validation.
The cohort is seeds 16–47; preceding N16 outcomes are not pooled. Root-regret
and fresh confirmation remain unmeasured. See
[ledger §266](../../experiments/ledger-06.md) and
[full paired packet](../../experiments/evidence/silver_budget_four32_128k_2026-09-15/README.md).

## Silver reuse-cap experiment

Production remains 32,768 with explicit experimental 128k opt-in. The exploratory
exact 10k paired 16 comparison at frozen `2b29e972` gives 11/16 wins at 32k versus 13/16
at 128k: two 128k-only wins/no 32k-only, exact discordant-pair p=0.5. Cap fallbacks
fall 214→0, while four-worker peak process RSS rises 1.078→2.501GiB. Diagnostic
prefixes match until 32k pressure; zero bridge failures. This is encouraging
but not established superiority; prior 1k seeds were reused, no root-regret
measurement or frozen teacher/model qualification was performed. Keep 32k
and require fresh matched quality/resource evidence before promotion.
See [ledger §265](../../experiments/ledger-06.md) and
[paired packet](../../experiments/evidence/silver_cap_pair10k_16_2026-09-15/README.md).

## Retained-root adaptive Silver search

The earlier bounded checkpoint diagnostic remains **`NO_USEFUL_SIGNAL`** for a
whole-fight or fresh-root early-stop policy. Its 500-simulation observations
were continuation checkpoints on a 10k-generated trajectory, not independent
fresh searches, and cannot establish deployed-policy equivalence. The
fresh-root subgroup is rejected for early stopping.

A separate frozen prospective policy now has a live N16 smoke and fresh N32
qualification result: **`PER_DECISION_SIGNAL_PROMISING`** for retained-root
adaptive search only.
Fresh roots and one-action/forced roots run exact 10k; retained non-forced
roots run 500 new simulations and stop when the top-two visit-gap share is at
least `0.2932885906040268`. With fresh paired seeds 64–79, fair Ironclad A0,
exact-root budgets, allocated cap 131,072, native OOC, CTM adaptive budgeting
off, and OOC MCTS off, the treatment reduced added Silver simulations by
41.05% and wall time by 40.99% relative to flat 10k. It stopped 2,804/6,800
live decisions, with all stops satisfying retained/non-forced/threshold
invariants. Outcomes were 10/16 wins for control versus 11/16 for treatment;
the five win disagreements and N16 size were descriptive only.

The fresh N32 qualification on seeds80--111 reduced added Silver simulations by
39.34% and wall time by 42.33%; it stopped6,093/14,403 decisions with all
invariants passing. Control won22/32 versus treatment24/32, with three
treatment-only wins and one control-only win. This supports the retained-root
compute-saving candidate at this bounded gate, but does not promote a default,
establish universal safety, or claim action equivalence. No expensive shadow
10k searches were collected. See [ledger §280](../../experiments/ledger-06.md),
[N16 packet](../../experiments/evidence/silver_retained_adaptive_pair16_2026-09-16/README.md),
and [N32 packet](../../experiments/evidence/silver_retained_adaptive_pair32_2026-09-16/README.md).

### Vendored singleton-root search bypass (2026-09-24)

**Removed with the vendored model (ADR-0022, 2026-09-25).** Native Silver
still searches single-action roots; porting the bypass to native needs its own
paired evaluation. The record below is history.

Since ADR-0021, plain `one_combat` uses native Silver by default. This bypass
is in the vendored `SilverLiveBackend` and applies when that backend is
selected, such as with `STS_NATIVE_SILVER=0` or a vendored-only
`STS_SILVER_*` option. For a validated singleton edge surface, the vendored
live backend commits the sole legal root action without running Silver search.
This applies to forced `END_TURN` and one-option selections. If a retained
root's edge surface does not match the sole live semantic action, ordinary
live play discards that predecessor and retries the full-budget search from
the live observation; it accepts the retry only if it selects that same sole
live action. Hard-combat and root-mechanism capture modes remain fail-closed on
a surface mismatch.
Full-budget per-root and checkpoint diagnostic modes continue to search for
complete observations. The tracked [32-run deployment packet](../../experiments/evidence/silver_retained_adaptive_deployment_pair32_2026-09-16/README.md)
records 510 one-action roots among 13,945 decisions; all 510 still ran 10,000
simulations. The user-provided breakdown is 489 forced `END_TURN` and 21
one-option selections, with 471 of 502 continuing forced roots followed by a
next decision that started from scratch. The user reports this as 6.3% of
Silver compute. The supplied 64-fight, exact-10k comparison reports 59/64 wins
in each arm, no paired flips, treatment ending HP +0.3, 4.6% fewer simulations
and 6.7% lower wall time. This report predates the retained-session correction
that preserves `previousBest` across zero-search singleton roots; it is
pre-correction descriptive evidence and does not confirm the corrected
implementation. That 64-fight raw packet and candidate/baseline SHAs were not
available in this checkout, so the breakdown and comparison results were not
independently verified here. The tracked 32-run packet's measurements remain
historical results from before the bypass.

A first post-correction exact-10k replay compared main at `01f6f164` with the
corrected implementation at `2da8eed6` on the frozen `hard64-holdout` cohort.
All 64 cases were attempted, but case `12100109/21` failed with the same
deterministic-state mismatch in both arms, leaving 63 valid pairs. Both arms
won 57/63 with no outcome flips; treatment skipped 62 searches, used 3.19%
fewer simulations, and had 2.99% lower summed per-case replay wall time. Mean
ending HP changed by +0.16 and action traces matched on 60/63 valid pairs.
This is a bounded replay result, not a complete valid N64 confirmation or a
live-game quality claim. See the
[post-correction hard64 packet](../../experiments/evidence/silver_singleton_reroot_hard64_holdout_2026-09-25/README.md).

A follow-up exact-10k replay after merging newer main compared current main
`46684659` with the merged treatment at `be47b2a1` on the same frozen cohort.
All 64 cases were attempted; the same deterministic-state mismatch failed in
both arms, leaving 63 valid pairs. Both arms won 57/63 with no outcome flips;
treatment skipped 62 searches, used 3.185% fewer simulations, and had 3.371%
lower summed per-case replay wall time. Mean ending HP changed by +0.159 and
action traces matched on 60/63 valid pairs. These are bounded descriptive
results, not equivalence or default-promotion evidence. See the
[current-main hard64 packet](../../experiments/evidence/silver_singleton_reroot_hard64_holdout_2026-09-25_main46684659/README.md).
Main then advanced to `8ed346ea`; rebuilding the replay target from that head
and from merged treatment commit `4b1b27f6` produced the same control and
treatment binary hashes used for these rows. No more seeded replays were collected after
the local 128 arm-case allowance was used. The packet preserves the original
run SHAs and the later byte-identity check. After main advanced to `03ae0297`,
Release rebuilds at that main head and merged treatment `b0393b03` again
matched the recorded control and treatment hashes. Main later advanced to
`18232bf0`; its rebuilt replay binary and the treatment at `b6242a65` differ
from the binaries used in the N63 run. Source review found the unsorted-rollout
option default-off and disabled for the recorded replay, with the remaining
changes limited to diagnostic timing defaults and an isolated simple-rollout
probe. No new hard64 screen was run; the N63 outcomes and simulation counts
remain historical results for their recorded binaries, and the 3.371% wall-time
result is not reverified on the newer harness. Main later advanced through PR
#322 to `856b3f8f` and PR #323 to `f8fa4a3f`. Release replay rebuilds at `f8fa4a3f`
and the merged treatment tree remained byte-identical to the `18232bf0` control
and treatment hashes (`f0367213…` and `ba4ef57d…`). PR #322 changes `one_combat`
backend dispatch and PR #323 adds documentation; neither changes the replay
binary. No new hard64 screen was needed, and the N63 observations remain tied
to their recorded binaries.

The follow-up exact-10k sequential-checkpoint diagnostic on fresh seeds
112--127 is **`LOGISTIC_DYNAMIC_RULE_REJECTED`** for the bounded offline
question. It records cumulative 250/500/1,000/2,000/4,000/8,000/10,000
checkpoints on the same private root, with the full 10k action as the label
reference. The held-out logistic controller stopped no primary decisions at
1% or 2% risk; at 5% it saved only 0.5393% nominal simulation with zero
observed action disagreements. The frozen #199 retained-root rule saved
40.7610% with 1.9124% held-out disagreement under the same offline label.
The requested exact visit-lock analysis found 2,003/2,422 held-out primary
decisions with a strict lock, 53.8026% nominal savings, and zero observed
disagreements. Descriptive rho and rho/leader-stability tables are recorded
in the packet, but no soft threshold was tuned. This does not overturn the
separately qualified retained-root compute-saving candidate; it rejects this
logistic dynamic rule while leaving exact-lock and empirical-risk sequential
stopping open. Fresh and one-action/forced roots remain controls, not part of
the quality claim. No gameplay A/B, runtime stopping API, threshold tuning,
or default change was made. See [ledger §285](../../experiments/ledger-06.md)
and the [sequential stopping evidence packet](../../experiments/evidence/combat_sequential_stopping_2026-09-16/README.md).

The staged retained-root follow-up is **`STAGED_PARETO_GAMEPLAY_GATE_FAIL`**.
At frozen source `41f26f8`, all nine scalar thresholds in the requested grid
were tested on discovery seeds 272--303, with cumulative
250/500/1,000/2,000/4,000/8,000/10,000/20,000/50,000 checkpoints and the
allocated 32,768-node production cap. Offline enumeration over 2,952 retained
non-forced discovery decisions produced maximum-saving schedules at 1%, 2%, and
5% checkpoint-to-50k disagreement. On held-out seeds 304--319, the flat 50k
reference won 10/16; the 1%, 2%, and 5% schedules won 8/16, 8/16, and 7/16,
respectively, with lower mean floor and ending HP in each arm. The staged
runtime is therefore not promoted; its rejected live runtime/configuration path
has been removed while the analyzer and frozen evidence are retained. Current
#199 500->10k and the 32k cap remain the production defaults. See [ledger §294](../../experiments/ledger-06.md)
and the [staged sweep packet](../../experiments/evidence/silver_staged_grid_2026-09-17/README.md).

The default-off prospective implementation was tested behind
`STS_SILVER_EXACT_VISIT_LOCK=1` at frozen source
`8adbfe9f6b58145c853e53248fa5979a4e1991fa`. It uses the caller's maximum
new-simulation budget and a 2.5/5/10/20/40/80/100% same-session polling
schedule, with an additional zero-new-simulation retained-root check. Only
retained roots with more than one complete legal root action are eligible;
fresh and one-action/forced roots remain full-budget controls. The lock is the
strict integer predicate `N1 - N2 > Bmax - Bused`; no `rho`, soft threshold,
logistic model, or fixed 10k controller rule is used. Focused fixtures cover
strict-boundary semantics, 1k/3.7k/10k caller budgets, zero-new-simulation
accounting and sequential selection.

The fresh paired N16 smoke on seeds 128--143 achieved 34.80% compute and
34.43% wall-time reduction, marginally below the nominal 35% compute target.
All mechanism/gameplay checks passed: 4,980 exact locks, 362 zero-use locks,
no invalid/fresh/forced locks, and zero bridge failures. Because the protocol
called the threshold approximate, N32 was run as an explicitly documented
extension; this was not a nominal 35% compute pass. The fresh N32 follow-up on
seeds 144--175 had zero lock/accounting/bridge violations but saved only
28.77% of control Silver simulations and 31.59% wall time. Control won 24/32
versus treatment 22/32, with two control-only wins and no treatment-only wins.
The earlier PR #202 offline 53.8026% reduction covered only retained,
non-forced decisions: 2,422 of 3,778 evaluation decisions. Its all-decision
equivalent was approximately 34.5%, making the live N16 result consistent
with the offline prediction. The N32 28.77% result is a moderate live
degradation, not a collapse from 53.8% to 28.8%; the descriptive rho
extension remains a justified follow-up hypothesis without supporting
promotion of the runtime policy.
Classification is **`LIVE_EXACT_VISIT_LOCK_REJECTED`** for the frozen bounded
gate because the N32 compute reduction is below the approximately 40%
requirement. This does not establish universal gameplay harm or invalidate
the current-root proof, but it does not support promotion; the feature and
exact-lock-only remains default-off. See the [paired evidence packet](../../experiments/evidence/silver_exact_visit_lock_pair_2026-09-16/README.md).

The frozen offline rho follow-up then evaluated exactly candidates A
(`rho >= 0.75`), B (`rho >= 0.50` plus two consecutive same-leader
checkpoints), and C (`rho >= 0.50` plus three). On discovery seeds 112--119,
B was selected before evaluation because it passed the <=2% and >=100-soft-stop
requirements and maximized all-decision savings. On held-out seeds 120--127,
B had 1,070 soft stops, 1.4953% disagreement, and 8.2319 percentage points
of additional all-decision nominal saving beyond exact locking. This is
**`RHO_RACING_OFFLINE_PROMISING`** post-hoc engineering evidence only.

The default-off runtime mode `STS_SILVER_RHO_RACING=1` was frozen at
`ae97d56a74a9b70ac34b87478a87de5e3a9ee893` and tested with fresh N16 seeds
176--191 and N32 seeds 192--223. N16 passed its incremental compute and
gameplay gate, saving 9.9341% additional simulations versus exact-only. The
N32 three-arm result saved 13.4237% additional simulations versus exact-only
and 40.8764% versus flat 10k, but produced five exact-only wins versus zero
rho-only wins and lower mean floor/HP. The result is
**`RHO_RACING_COMPUTE_PASS_GAMEPLAY_CONCERN`**: rho is not promoted and is not
strong enough to replace the frozen #199 preferred experimental path. The
mode and exact-lock-only mode remain default-off.
See the [rho-racing evidence packet](../../experiments/evidence/silver_rho_racing_2026-09-16/README.md)
and [ledger §288](../../experiments/ledger-06.md).

The final normal-production deployment screen for PR #199 used fresh paired
seeds 224--255, the 32,768 allocated reuse cap, ordinary boss budgeting, and
`STS_SILVER_EXACT_ROOT_BUDGETS=0`. Control won 21/32 and treatment won 22/32;
the treatment had five treatment-only versus four control-only wins, mean
floor 48.40625 versus 48.28125, and mean ending HP 32.90625 versus 29.34375.
It reduced Silver simulations from 202,860,000 to 81,633,000 (59.7589%) and
wall time from 395.72s to 132.08s (66.6229%). All 6,086 500-simulation stops
passed retained/non-forced/threshold validation, all fresh and one-action/
forced roots reached 10k, and all bridge failure counters plus exact-lock/rho
counters were zero. Classification: **`RETAINED_ADAPTIVE_DEFAULT_GO`**.
The policy is now the normal live Silver default, while `STS_SILVER_ADAPTIVE=0`
restores flat Silver. This remains a deployment screen, not a formal
equivalence proof or superiority claim. See [ledger §288](../../experiments/ledger-06.md)
and the [deployment packet](../../experiments/evidence/silver_retained_adaptive_deployment_pair32_2026-09-16/README.md).

## Current priority / active line

The corrected all-Act boss leaf has a mechanism pass and paired N8 smoke:
**CORRECTED_MECHANISM_PASS_PAIRED_N8_SMOKE**. Three identical leaf states
produce materially different boss/native values and all root Qs change on an
identical 64-simulation fixture. Fresh fixed512 seeds12003064--12003071 give
native6/8 versus boss4/8; every terminal and non-timing trace row differs, so
the treatment is now exercised. The boss arm is about26.6x slower by mean
elapsed seconds/run. N8 is mechanism evidence only, not a quality conclusion;
defaults remain unchanged. See [ledger §276](../../experiments/ledger-06.md)
and the [evidence packet](../../experiments/evidence/ooc_mcts_boss_leaf_corrected_smoke_2026-09-15/README.md).

The all-Act boss leaf N32 follow-up is
**INVALID_TREATMENT_NOT_EXERCISED**. Live `checkpointLeaves=true` bypassed the
boss evaluator and called native `v_win` in both arms. Its exact terminal and
trace equality is a bug signal, not evidence of no effect. Raw evidence remains
provenance-only. See
[ledger §275](../../experiments/ledger-06.md) and the
[paired packet](../../experiments/evidence/ooc_mcts_all_act_boss_leaf_pair32_2026-09-15/README.md).

The current-act boss leaf N32 experiment is also
**INVALID_TREATMENT_NOT_EXERCISED** for the same checkpoint bypass. Both arms
executed native `v_win`; its 24/32 versus24/32 and exact traces are not an A/B
result. See [ledger §274](../../experiments/ledger-06.md) and the
[paired packet](../../experiments/evidence/ooc_mcts_boss_leaf_pair32_2026-09-15/README.md).

The fresh current-main V2 rollout confirmation on seeds
`12003000..12003031` is complete. MCTS-512 is **NO_CONFIRMATION**: 22/32 versus
V4 24/32, -6.25pp, paired95% CI [-28.125,+15.625]pp. At fixed 2048 simulations,
rollout0 and rollout1 each give 26/32 (+6.25pp versus V4, intervals crossing
zero), but rollout1 has zero observed win gain over rollout0 at 23.19x elapsed
time. Rollout3 gives 28/32, +12.5pp versus V4 with CI [-3.125,+28.125]pp and
+6.25pp versus rollout1 with a crossing-zero interval at another 2.35x cost.
Rollout0 is the practical larger-confirmation candidate; rollout3 is only a
high-cost research candidate. No arm is gameplay- or deployment-qualified.
See [ledger §277](../../experiments/ledger-06.md) and the
[evidence packet](../../experiments/evidence/ooc_mcts_confirmation_v2_2026-09-15/README.md).

The fresh64 fixed10000 live OOC MCTS versus matched V4 gate is complete:
**OOC_MCTS_WINRATE_INCONCLUSIVE**. MCTS42/64 versus V448/64,−9.375pp,
paired95% CI[−23.4375,+4.6875]pp. Both fresh arms use frozen native models and
fair exact-10k Silver, A0/keysOFF/Act3; no historical control is pooled. Mechanical
source/config/seed/trace/support validation and independent reproduction pass
with zero bridge failures and battleLeaves. Maxdepth6..23,7240owned decisions,1551 support aborts; total V4
fallback rate33.5658%. Descriptive mean elapsed game ratio4.50565. Negative point
estimate and crossing-zero interval provide no demonstrated improvement; no
basis to enable MCTS. Default OFF/existing512 and frozen exclusions are preserved.
Copied hidden noncombat RNG remains a planning limitation. See
[ledger-06 §249](../../experiments/ledger-06.md),
[fresh64 evidence](../../experiments/evidence/live_ooc_mcts_fresh64_10000_2026-09-14.md).
The prior reused32 fixed2048 regression remains preserved and inconclusive
[§247](../../experiments/ledger-06.md); it is not a causal comparison of budgets
against this fresh cohort.

## Completed recent line

### Strong-WD DeepSets survival online speed screen

**DEEPSET_ONLINE_TRADEOFF_STOP** on user-reviewed frozen SHA
`471ba9a119de2a4f6ae691329467acae1b0f70a0` after Linux GCC passed. Exact #217
width-64 strong-WD re-export reproduced `c870e4c…`; Stage A was not rerun.
Native survival median improved 1.143383→0.128041 ms, but matched end-to-end
CPU/run median improved only 50.88→50.29 s (ratio 0.988404, **1.1596%**), below
the 10% gate. Two historical #187 seeds were replayed twice per arm at the same
2048-MCTS/10k-Silver profile, with one-thread isolated timing. These are not
fresh quality-gate seeds. No 16/64 paired gameplay gate or quality bootstrap ran;
no equivalence, non-inferiority, or promotion claim. See
[Stage-B report and raw evidence](../../experiments/evidence/deepset_survival_online_stage_b_2026-09-18/README.md)
for timing variability, support telemetry, and the shared legacy V1 diagnostic
warning. Defaults and all source code remain unchanged after review.

### Near-full combat support: qualified except initial/pre-Smoke and Writhing/Ritual

**NEAR_FULL_EXCEPT_SMOKE_QUALIFIED** for offline composition and the native combat boundary. The V2 pre-state support predicate excludes initial Smoke Bomb, pre-existing `smokeBombUsed`, and Writhing Mass with any Ritual Dagger. Exact support is **505,935/510,030 (99.197106%)** overall and **51,036/51,441 (99.212690%)** TEST. All 41,454 old #179 TEST states are retained and recomposed with the selected maxHP refit. Every nonempty final slice gate is ≤0.1 nat, including tiny Transmutation+ and recursive Brew slices; the largest is Writhing +0.094656. Seven retained observed ESCAPE rows pass applicable gates.

On the exact supported TEST set, 1,633,152 draws have zero recorded hard-validity violations. One original Monte Carlo gold zero was resolved by a restricted exact ancestral marginal (target mass 0.0010596961), without changing weights or sampling; the original diagnostic and corrected receipt are both preserved. The earlier Writhing repair and all final TEST diagnostics are reused development evidence, not pristine holdout confirmation.

The accepted Brew contract draws a fresh full-width hypothetical native potion RNG from planner RNG on first use, reuses it through recursion and retains its advanced state in sampled RAW. Generated Smoke/ESCAPE remains supported; initial/pre-Smoke states stay excluded. Historical RNG reconstructs teacher labels only. Native generation audited 3,208 Brew rows and 3,106 rounds, including 112 proven recursive cases. Transmutation upgrade status conditions shared learned HoG mechanics, while native payouts remain exact 20/25.

The tracked default artifact at `selfplay/models/combat_transition_near_full_except_smoke_v2.native` now uses the targeted attention-HPO survival component (artifact SHA256 `e9a18951710fdfe9e1a81a2703090a41f039067c670a1d8a0393b5e7e8e0ddfd`). All other component checkpoints are unchanged. Frozen TEST survival NLL/Brier improve from 0.060412/0.017986 to 0.058878/0.017384. The full final-support composition and RAW gates were rerun: all nonempty exposure slices pass, the established exact correction resolves the one Monte Carlo gold zero, and 1,633,152 transitions have zero hard-validity violations. Python/native CPU FP32 probabilities pass at 1e-4 tolerance (maximum error 2.38e−6); complete RAW state, planner stream and scalar/prepared parity pass on 3,904 draws, including 127 recursive Brew cases and three unsupported/no-draw fixtures. The executed native support predicate still exactly matches both corpus/TEST ordered-index hashes.

A fresh prospective 64-seed paired gameplay gate compared the prior V2 artifact with this attention-promoted V2 under the locked 2,048-simulation OOC MCTS reference profile and exact 10k Silver combat search. Both arms won 49/64; both-win47/both-lose13/old-only2/new-only2 gives a new-minus-old delta of 0.0pp and paired bootstrap95% [-6.25pp,+6.25pp]. This establishes neither gameplay improvement nor harm. It is bounded online evidence that observed play was preserved at this gate's resolution, not equivalence proof or unbiased-planning qualification. See [ledger-06 §271](../../experiments/ledger-06.md) and the [paired evidence](../../experiments/evidence/combat_transition_v2_ooc_mcts_pair64_2026-09-15/README.md).

The original full-union Smoke/relic gap +0.242637 and three failed bounded repairs +0.199237/+0.201889/+0.209178 remain historical evidence; none of those repair checkpoints is promoted. The failing Writhing/Ritual intersection is excluded by visible pre-state rather than hidden by aggregates. No fourth Smoke repair or new data was used. V1 support remains 413,799 overall/41,454 TEST when that artifact is selected. The V2 artifact is the default model file, but live OOC MCTS remains OFF by default. Exact #180 state replay is unavailable and aggregate subtraction cannot estimate root-abort improvement. See [ledger-06 §270](../../experiments/ledger-06.md) and the [promotion report](../../experiments/evidence/combat_transition_attention_promotion_2026-09-15.md).

### Live OOC MCTS paired Silver gameplay gate

**`OOC_MCTS_WINRATE_DOWN`** in the first fixed 32-seed paired Act-3 engineering
A/B, with normal real Silver combat in both arms. The opt-in MCTS implementation
uses the qualified native combat sampler only in detached imagination and is
OFF by default. The primary paired win-rate CI is strictly negative. Preserve
the frozen implementation and return for independent review; a bounded audit of
changed strategic choices and native leaf/boundary behavior should precede any
new experiment. No parameter sweep or automatic additional seeds are authorized.
This is actual gameplay evidence under copied hidden noncombat RNG, with no
unbiased-planning or deployment qualification claim. See
[ledger-06 §243](../../experiments/ledger-06.md) and the
[full paired Silver evidence](../../experiments/evidence/live_ooc_mcts_2026-09-14.md).

### Whole-combat transition model v1

The corrected offline comparison on the existing 25,000-source
`combat_transition_row_v2` corpus is classified
**`STRUCTURED_NEURAL_WINS_NO_CLEAR_FAMILY`**. XGBoost is rejected as
sufficient: both DeepSets and attention clearly improve Phase-1 prediction on
the corrected frozen TEST split. Attention was the validation finalist, but
attention versus DeepSets remained overlapping, so there is no evidence that
attention improves over DeepSets. DeepSets is selected as the Phase-2 default
by a simplicity tie-breaker. The frozen source-grouped 80/10/10 split was
reused after independent review. The corrected run uses canonical 372/181/48
card/relic/potion domains, fail-closed ID validation, categorical global
encoding, and equal TRAIN+VALIDATION refits for XGBoost, DeepSets, and
attention. This is an offline model-selection result only: no runtime
integration, Silver replacement, model export, gameplay gate, or new corpus
collection is authorized. If Phase 2 is later authorized, DeepSets is the
default candidate; no Phase-2 implementation is authorized by this result. See
[ledger-06 §§227–228](../../experiments/ledger-06.md) and the
[corrected compact evidence report](../../experiments/evidence/combat_transition_model_v1_2026-09-12.md).

A targeted attention-only hyperparameter optimization on the same frozen
source split subsequently selected the original width-64/two-layer/four-head
architecture with winning-HP loss weight doubled from 1.0 to 2.0. Its
validation composite was `0.164160725` versus `0.168567730` for the matched
attention baseline. After equal TRAIN+VALIDATION refit, all three historical
TEST error deltas against the frozen attention checkpoint had negative paired
source-bootstrap intervals. This is classified
**`ATTENTION_HPO_IMPROVES_FROZEN_ATTENTION_POSTHOC`**: the historical TEST was
already inspected, no tuned-versus-DeepSets prospective comparison was run,
and no runtime export, composition, or gameplay qualification was performed.
The existing no-clear-family conclusion and DeepSets simplicity tie-break
therefore remain unchanged. See [ledger-06 §267](../../experiments/ledger-06.md)
and the [HPO evidence report](../../experiments/evidence/combat_transition_attention_hpo_2026-09-15.md).

### Phase-2 persistent-state transition surrogate support audit

The final v1 boundary excludes every source-audited predictor-visible path
that can change persistent gold: Looter/Mugger encounters (`LOOTER`,
`TWO_THIEVES`, `EXORDIUM_THUGS`), Hand of Greed, colorless-pool routes through
Jack of All Trades or Transmutation, Toolbox, and Colorless Potion. It also
retains the corrected exclusions for Writhing Mass, Ritual Dagger, Smoke Bomb,
Entropic Brew, and pre-combat `smokeBombUsed == true`. The learned schema
remains `combat_predictor_input_v1`; `pre.smokeBombUsed` and `pre.stolenGold`
are adapter/support-gate fields, not learned features.

On the unchanged 510,030-row corpus, the source-audited predicate supports
413,799 rows (81.1323%) and falls back 96,231, a loss of 71,367 rows relative
to the immediately preceding 95.1250% boundary. Support is 15,384/18,133
deaths (84.8398%), with Act 1/2/3 rates 82.5107% / 79.4053% / 80.7983%; room
rates for EVENT/ELITE/MONSTER/BOSS are 83.9126% / 84.0875% / 79.5760% /
83.7653%.

The complete audit has zero supported `gold` mutations, zero supported
`stolenGold` mutations, and zero supported deck-structure, card-misc, or
`smokeBombUsed` mutations. All supported copy-through checks are exact. Gold
and `stolenGold` are therefore v1 fallback/copy-through fields, not learned
heads or Phase-2 pass metrics.

The remaining Phase-2 DeepSets fit and point-control fit used validation-only
epoch selection (9 and 12 epochs), equal TRAIN+VALIDATION refits, and fixed
TEST evaluation. Phase-2 improves HP distribution CRPS (0.048484 versus
0.071822 point-control), and the relic head is promising on changed slices;
the potion changed slice improves but potion full-vector accuracy does not.
Shared multitask training degrades survival (Brier 0.0208797 versus 0.0189359
for point control), so the final classification is **`CORE_REGRESSION`**. The
durable conclusion removes the post-hoc absolute `+0.005` survival tolerance;
the existing 5% relative check also fails on these numbers. The stochastic HP
head works, and the potion head should probably use copy-through/change gating.
The next experiment should protect the core predictor, for example by freezing
or separating the survival encoder/trunk before training transition heads. This
follow-up was not run. Runtime inference is not implemented, and
`combatRng[6]` now has an exact supported-v1 continuation contract, described
below; the runtime adapter and multi-fight qualification remain unimplemented.
See [ledger-06 §231](../../experiments/ledger-06.md)
and the [gold-boundary fit report](../../experiments/evidence/combat_transition_surrogate_phase2_gold_boundary_2026-09-13.md).

### Winning-combat HP target representation

The frozen HP-only comparison tests signed absolute HP change against final
HP fraction on every globally supported victory, conditioning both arms on
the true observed max-HP delta. Nested TRAIN+VALIDATION sources train both
models from scratch; nested HOLDOUT is reused engineering data, with no epoch
selection. Three paired seeds and ten fixed AMP epochs isolate target
representation. The fits returned **`HP_TARGET_INCONCLUSIVE`**: delta minus
fraction raw HP MAE averaged -0.040494283 HP (-0.7414%), source-bootstrap
95% CI [-0.054637538, -0.025676357]. The first seed favored fraction
(+0.011898292 HP); the other two favored delta (-0.071289462 and -0.062091678
HP), so required all-seed agreement failed. On zero-max-HP-change victories,
the descriptive difference was -0.043772844 HP; healing rows favored fraction
(+0.187107964 HP), and delta produced more raw above-max predictions
(10.2746% versus 2.0529%). No target change is qualified by this decision.
Max-HP modeling, survival, potion,
relic support, corpus, and simulator behavior are unchanged. See the
[frozen protocol and evidence](../../experiments/evidence/hp_target_comparison_2026-09-14.md).

### Exact supported-v1 combat RNG continuation

The full frozen 510,030-row audit is **`RNG_COUNTER_DELTA_EXACT`** with exact
encounter initialization replay, and requires **no learned RNG target**.
Plain native `setCounter(post.counter)` matches both inherited streams on all
510,030 rows and all 413,799 current supported rows. However, a native parity
fixture proves that actual combat bound 3 can reject an underlying draw, so
plain counter advancement is not a universal continuation algorithm.

The exact contract copies pre.potionRng (unchanged on every supported row) and
replays the native encounter-specific misc initialization draw schedule from
pre.miscRng, including bounded rejection. Its counter delta is deterministic
from visible encounter, not predicted. This replay matches 510,030/510,030
full-corpus misc post states, including 413,799/413,799 supported states, without
using post counters. The 97,154 supported misc changes rule out literal
copy-through, but do not require learned RNG state or a new support gate.

The four other streams are recreated on every battle entry. The normal
controller has no reachable same-floor combat chain: Colosseum is disabled
and unimplemented, event callbacks end at rewards/map, and A20's second boss
increments floor. There are zero same-floor pairs among 485,031 consecutive
source-ordered corpus fights. Intervening OOC reads of card-random/shuffle
also occur after their floor/boss-treasure reset. No support change is needed;
no runtime adapter, model training or multi-fight qualification ran.
See [ledger-06 §238](../../experiments/ledger-06.md),
[exact evidence](../../experiments/evidence/combat_rng_continuation_2026-09-14.md)
and [RNG ownership](../behavior/determinism-and-rng.md). Existing deployment
qualification remains **`NOT_QUALIFIED`**.

### Offline composed combat-transition sampler

**`COMPOSED_TRANSITION_QUALIFIED`** on the original reused engineering TEST after
exact HP exposure correction, reviewed SHA
`dc1499f36055491fec8ff44143f879c124bf230d`. HP NLL analytically marginalizes over
all 11 frozen maxHP classes using their predicted weights and native HP masks.
Exact marginal NLL 2.383993276 minus teacher-forced 2.371751655 gives
+0.012241622 nat, 95% source-bootstrap CI [+0.009743450, +0.014807776], passing
the unchanged 0.1 gate. The retained diagnostic is: 8/31,150 rows received zero
empirical mass with 32 ancestral draws. All have positive exact mass; the
empirical infinity is excluded from classification.

Potion exposure +0.000810765 nat, CI [+0.000591005, +0.001033385], and
normalized relic exposure -0.001521621, CI [-0.004191767, +0.001475988], pass.
All eleven hard validity counts are zero over 1,029,248 complete draws.
These and all other original component/diagnostic/latency evidence are unchanged
from reviewed execution `abe2c6ea50f55d37e4d594ceb6575247e91c32fa`.
Only HP exposure/bootstrap was recomputed; teacher NLL reproduces exactly and
all artifact/data hashes match. No models, seeds, transitions or gameplay change.
The original distribution qualification used 32,164/51,441 TEST rows
(62.526001%). The subsequent potion-generation support correction admits
41,454/51,441 (80.585525%) on original TEST and 413,799/510,030 (81.132286%)
overall, retaining every independent exclusion. All supported corpus rows,
including deaths, have zero potion creations/swaps/substitutions; preserved
RNG, copy-through and victorious relic checks also pass. Of the previous
116,302 potion-certification failures, 113,094 recover certification and
91,155 recover full support. Remaining full fallback is 96,231 rows.
This census corrected the contract; expanded distribution/exposure qualification
is now recorded below. It did not rerun gameplay qualification. See the
[full source/provenance/accounting audit](../../experiments/evidence/potion_generation_support_2026-09-14.md)
and [maintained potion-generation contract](../behavior/combat-potion-generation.md).

**`EXPANDED_COMPOSED_TRANSITION_QUALIFIED`** on #178's complete
41,454-row original engineering TEST support, reviewed scoring SHA
`66d62987308e200f1abbfaa92d3fff67b3370ac7` (§248). OLD (32,164 rows/2,474 sources)
reproduces the recorded #174 component/exposure metrics and row teacher NLLs
exactly: all reproduction errors are zero. RECOVERED is 9,290 rows/893 sources;
EXPANDED is 41,454 rows/2,512 sources, with row-ID disjoint union and historical
OLD membership proven. Frozen model/corpus/split/prepared hashes match.
RECOVERED HP/potion/relic mean gaps are +0.019484613/+0.000565261/-0.002278852 nat;
EXPANDED gaps are +0.013832688/+0.000723143/-0.001336405. Each passes its independent
0.1-nat mean gate; source-bootstrap CIs remain descriptive. All eleven hard
validity counts are zero over 1,326,528 EXPANDED draws, including 297,280
RECOVERED draws. Independent raw-output reproduction passes.

Recovered component diagnostics are weaker than OLD, but composition exposure
passes the frozen criterion. The recovered census has only COMBUST and BRUTALITY
outside the historical card-color whitelist (both GREEN in simulator metadata);
this result does not establish accuracy for other off-color IDs. Act, combat
type, card-count and common-card slices are diagnostic. The two rows with four
metadata off-color cards have no informative relic trajectory rows, explicitly
reported without a score. #174 remains the original 62.526% subset qualification;
this experiment extends the offline composition prerequisite to 80.586% support.
The original TEST is reused engineering validation, not untouched holdout evidence.

This satisfies the offline composition prerequisite for a next fresh MCTS
gameplay gate; it does not establish win-rate improvement, change MCTS defaults,
or replace that gate's runtime/readiness/provenance requirements. No models,
support, runtime, data or gameplay changed. See
[expanded evidence](../../experiments/evidence/composed_transition_expanded_support_2026-09-14.md)
and [JSON](../../experiments/evidence/composed_transition_expanded_support_2026-09-14.json).

The native runtime adapter is now qualified for the combat boundary (§242);
the opt-in live OOC MCTS engineering gameplay gate is recorded in §243.
Offline composition qualification does not establish runtime or gameplay
performance. Full evidence and limitations are in the
[executed evidence](../../experiments/evidence/composed_transition_2026-09-14.md)
and [JSON](../../experiments/evidence/composed_transition_2026-09-14.json).

`tools/combat_transition_composed.py` composes the fixed protected attention
survival, historical maxHP attention head, 20260912 stochastic signed-HP,
joint potion consumption decoder and 20260912 shared relic trajectory decoder.
Full support is decided before survival. Sampled deaths terminate before every
downstream encoder/head. Victories propagate sampled maxHP, signed HP/ending
fraction and potion mask into later factors; relics reuse the HP encoder state.
Native reconstruction copies supported fields, derives potion count, shares
trajectory residues and emits exact inherited potion/misc OOC continuation
RNG. It does not emit the four recreated battle-local RAW RNG streams.
Nondeterministic active Lizard Tail fails closed. The targeted 111-source
qualification attempted only the existing Lizard head after supported
non-Lizard composition exposure passed its existing gates. The fixed head-only
fit was rejected against the TRAIN-only prior (+0.50675 nat TEST NLL gap,
source-bootstrap 95% CI [+0.37380, +0.61081]); the production guard and frozen
artifacts remain unchanged. No runtime integration or live support smoke was
run. The potion support predicate also excludes actual generation routes
(explicit Alchemize and Entropic Brew), allowing harmless off-color cards.
See the [active Lizard evidence packet](../../experiments/evidence/active_lizard_ctm_2026-09-23/README.md).

A separate 32-pair rescue pilot found two no-Tail deaths; both active-Tail
treatments won, but one retained Tail, consistent with the relic changing the
policy trajectory. Ordinary CTM mean death probability was `0.05704` versus
`0.0625` observed deaths; Tail consumption was `0.03125` of pairs. This is too
small to calibrate a rescue head, and the single Tail-consumed win cannot assess
conditional post-combat heads. It does not alter the prior qualification
rejection or runtime guard. See the [paired pilot packet](../../experiments/evidence/lizard_tail_rescue_pilot_2026-09-23/README.md)
and [ledger §344](../../experiments/ledger-06.md).

A follow-up risk-targeted cohort paired 128 unique fights. The ordinary arm died
27 times; active Tail won 22 of those, consuming Tail in 14 and retaining it in
8. Tail was consumed in 32/128 pairs overall. Silver's first action changed in
59/128 pairs and its full committed-action trace in 122/128, so Tail-aware
policy adaptation is frequent. On 71 retained-Tail pairs where both arms won,
the conditional post-head score deltas did not meet the preregistered material
shift threshold, but the intervals do not establish equivalence and relic
subgroups remain small. This supports testing small survival/consumption
corrections that account for policy adaptation; it does not qualify reuse of
existing heads, a Tail model, or runtime support. See the [targeted cohort
evidence packet](../../experiments/evidence/lizard_tail_targeted_rescue_2026-09-23/README.md)
and [ledger §345](../../experiments/ledger-06.md). The prior Lizard-head
qualification rejection and production fail-closed guard remain unchanged.

A same-cohort minimal three-state diagnostic found a promising fixed
`T2` revive-HP conditioning input for consumed-Tail wins: HP NLL improved by
`1.084` nat on 22 supported rows, while its CRPS interval crossed zero. `T1`
was not retained because it showed clear paired degradation in three sparse
relic constraint groups. Source-grouped q/r calibration slightly improved
three-class NLL/Brier over the coherent mechanical reserve baseline, but both
paired intervals included zero. Six Fairy Potion rows remained exact-boundary
fallbacks, and the five `LOSS_CONSUMED` examples leave rescue prediction
data-limited. The offline 32-draw diagnostic had zero impossible or invalid
Tail-state transitions on 98 supported sources; 30 sources used existing
support/native fallbacks. Classification is
`LIZARD_MINIMAL_CORRECTION_DATA_LIMITED`; no production support or model
qualification changed. See the [Phase A-C packet](../../experiments/evidence/lizard_tail_targeted_rescue_2026-09-23/README.md#minimal-three-state-correction-diagnostic),
[analysis JSON](../../experiments/evidence/lizard_tail_targeted_rescue_2026-09-23/minimal-correction-analysis.json),
and [ledger §346](../../experiments/ledger-06.md).

The fixed-B1 candidate-pool extension reused 475 unique paired fights from the
same 2,700-row pool after dropping 35 repeated source/fight keys, with repeated
sources kept together for five-fold CV and source bootstrap. The 35 overlapping
replays are exact combat-observation duplicates; only their `targetRiskBand`
selection metadata differs. There are 13 `LOSS_CONSUMED` examples total (eight
new), short of the 20-additional target.

The broad, post-boundary descriptive comparison covers 451 rows from 124
sources and scores q/r NLL `0.3544` / Brier `0.1994` against B1 `1.9122` /
`0.2158`. On the prospective runtime domain—`full_support_reasons()` after
removing Lizard Tail from both pre-state and predictor input, plus Fairy/Bloom
exact-boundary exclusions—24 additional unsupported rows are excluded. The
remaining 427 rows from 124 sources contain 12 `LOSS_CONSUMED` examples; q/r
scores NLL `0.3427` / Brier `0.1932` against B1 `1.9890` / `0.2096`, with
source-bootstrap intervals favoring q/r. The 1,611 remaining supported and
coherent candidate rows held only `1.4045` summed fixed-B1 loss mass, so no more
trajectories were generated. The 34 new `WIN_CONSUMED` observations remain
confirmation data for frozen T2; a future T0-vs-T2 analysis can score them
without retuning. This remains promising but data-limited evidence, not
qualification, and the production `active_unqualified_lizard` guard is
unchanged. See the [B1-ranked extension
packet](../../experiments/evidence/lizard_tail_targeted_rescue_2026-09-23/README.md#b1-ranked-candidate-pool-extension),
[prospective-domain analysis](../../experiments/evidence/lizard_tail_targeted_rescue_2026-09-23/b1-qr-runtime-support-analysis.json),
[broad analysis](../../experiments/evidence/lizard_tail_targeted_rescue_2026-09-23/b1-qr-combined-analysis.json),
and [ledger §347](../../experiments/ledger-06.md).

The [frozen composed qualification protocol](../../experiments/evidence/composed_transition_2026-09-14.md)
uses the original source-grouped **reused engineering TEST**, exact HP marginal
over 11 maxHP classes, and 32 ancestral draws for potion/relic and complete states,
individual HP/potion/relic exposure gates at 0.1 nat and zero hard sampled-state
invalidity. Source-bootstrap CIs and full-state distribution/latency diagnostics
are descriptive. Historical component qualifications remain distinct from
composed and runtime qualification.

### Frozen shared state representation for signed HP

The proposed cheap collapse of the dedicated signed-HP encoder into the frozen
pre-#187 survival representation is **`SHARED_ENCODER_HP_REJECTED` for the
exact tested checkpoint**. On the
same source-grouped full-union TRAIN/VALIDATION population, with byte-identical
fresh HP decoders and no encoder gradients, the survival representation is
7.3626% worse in VALIDATION NLL, 12.9631% worse in CRPS and 0.6310 HP worse in
expected ending-HP MAE. Healing and low-HP slices regress more. Do not proceed
to the maxHP/potion shared-encoder stage or runtime consolidation from this
representation. The candidate selected the final allowed epoch, so the result
does not distinguish intrinsically absent information from information that is
harder or slower to decode under this head/optimizer. No extra epochs are
warranted within the frozen screen. #187 subsequently replaced only the
survival component (`e150180a…` to `ccc3c210…`), so this screen does not
directly evaluate the current promoted survival encoder. This does not rule out
a separately designed shared architecture. See [ledger-06 §272](../../experiments/ledger-06.md) and the
[frozen-representation evidence](../../experiments/evidence/shared_frozen_hp_encoder_2026-09-15.md).

### Purpose-trained shared maxHP and signed-HP encoder

The initial 12-epoch joint-training follow-up was **`SHARED_TRANSITION_ENCODER_REJECTED`**.
One current-style 64/2/4/128 Attention encoder initialized from the dedicated HP
specialist was distilled against the frozen current maxHP and HP specialists on
the exact source-grouped final-union TRAIN/VALIDATION victories. The copied HP
branch remains close to its teacher: NLL +0.2715%, CRPS +0.4813%, expected MAE
+0.021105 HP, with all important slices inside their gates. The fresh maxHP
branch misses its NLL gate: +6.5932% versus the 2% limit, despite accuracy
-0.1070pp, expected MAE +0.005442 HP and nonzero accuracy -0.9056pp remaining
inside bounds. The rejection is driven by maxHP under-learning; HP degradation
remains within all preregistered gates. Combined KL improved through the final
epoch12, and the NLL miss is too large for the narrow epoch12 inconclusive
exception.

That rejected the exact 12-epoch recipe, not the later authorized variants.
No TEST, runtime/export, model promotion or gameplay ran. See
[ledger-06 §273](../../experiments/ledger-06.md) and the
[distillation evidence](../../experiments/evidence/shared_transition_encoder_distill_2026-09-15.md).

The subsequent 40-epoch continuation aborted at epoch 19 with a non-finite
gradient norm: **`EXTENDED_TRAINING_NUMERICALLY_UNSTABLE`**, without a selected
checkpoint or quality decision. The one-variable overflow-handling follow-up
then completed all 40 epochs, allowing GradScaler to skip seven non-finite
gradient updates while retaining the finite forward-loss guard. Epoch 37
passed all fixed gates: **`SHARED_TRANSITION_ENCODER_GO`**, with maxHP NLL
+1.2492% and HP NLL +0.1303%. This is the historical offline shared Attention
qualification, not runtime/export or default-model promotion. The four
unchanged evidence files are recovered from PR #197's frozen commit
[`013db3d8a8f1180adfe16003f24c36742a9d0ed7`](https://github.com/pherrman1/sts_ai/commit/013db3d8a8f1180adfe16003f24c36742a9d0ed7),
which preserves PR #197's final corrected state. The actual overflow run used
`b58a03920fb84aee84f7fcde3ef300366221feb8`, as recorded in the recovered receipt.
The later `013db3d…` correction changes only skipped-batch TRAIN metric
accounting, not optimizer updates, validation results, checkpoint selection,
or the GO decision; no rerun is needed. Today's generic distillation tool is
not reverted. See [ledger-06 §295](../../experiments/ledger-06.md),
the [continuation evidence](../../experiments/evidence/shared_transition_encoder_distill_40_2026-09-15.md),
and the [overflow evidence](../../experiments/evidence/shared_transition_encoder_overflow_40_2026-09-15.md).
The later DeepSets follow-up below became the cheaper qualified maxHP+HP
direction; it does not erase the preceding Attention qualification.

### Purpose-trained shared maxHP and signed-HP DeepSets encoder

The authorized architecture follow-up remains **`CHEAP_ENCODER_QUALITY_GO`**
and **`CHEAP_ENCODER_SPEED_GO`** after a same-session correction. One fixed
40-epoch temperature-1 distillation run replaced only the shared state encoder
with the existing historical `DeepSetsEncoder` (94,424 encoder parameters,
output width 64); the frozen teachers, source split, loss, optimizer, AMP
behavior and selection rule were unchanged. The correction uses
`cache["ids"][train]` for TRAIN normalization and initializes the HP delta
embedding plus HP head from the specialist used by the Attention control. On
VALIDATION, corrected maxHP NLL was +1.2413% relative to the dedicated
specialist, HP NLL +0.3378%, HP CRPS +0.5568%, and expected ending-HP MAE
+0.026469 HP. All fixed accuracy, support, slice and MAE gates passed; epoch
40 was selected. The same CPU implementation screen on identical 512-row
batches measured 21.73x encoder and 20.74x complete maxHP+HP-forward median
speedups over the shared Attention control. These are offline implementation
timings, not native/OOC speedup claims. This result does not authorize
downstream substitution, export, native CTM work, gameplay or default
promotion: downstream consumers must be retrained for the new representation
in a separate experiment. No TEST rows were inferred. See
[ledger-06 §286a–§286b](../../experiments/ledger-06.md), the
[correction evidence](../../experiments/evidence/shared_transition_deepset_distill_correction_2026-09-16.md),
and the [superseded original packet](../../experiments/evidence/shared_transition_deepset_distill_2026-09-16.md).

The reverse frozen substitution also fails: a fresh linear maxHP-delta head on
the dedicated HP representation is **`SHARED_HP_ENCODER_MAXHP_REJECTED`**.
Relative to the dedicated maxHP representation, VALIDATION NLL is 272.3032%
worse, accuracy falls 1.2492 percentage points and expected post-maxHP MAE
worsens 0.1528 HP. Nonzero-delta accuracy falls from 63.1307% to 0.0647%.
Because this first sequential screen failed, the analogous HP-encoder potion
screen did not run. The candidate selected final epoch 12, so intrinsic absence
of maxHP information is not established; the fixed linear-head/training recipe
is rejected. #187 changed only survival; the tested maxHP and HP component
hashes are unchanged on current main, so no scientific rerun is required. See
[ledger-06 §278](../../experiments/ledger-06.md) and the
[maxHP evidence](../../experiments/evidence/shared_frozen_maxhp_encoder_2026-09-15.md).

### Shared maxHP+HP representation for native downstream consumers

Stage A is **`SHARED_HP_DOWNSTREAM_FAIL`**. On the exact current final-union
source-grouped eligible VALIDATION cohort (17,950 rows), the PR #197 epoch-37
shared representation was substituted only for the dedicated HP representation
at frozen relic/event/gold downstream consumers. Joint downstream NLL worsened
from 1.364212394 to 1.448260307 (**+6.1609%**, above the +2% gate). Turns,
attacks and shuffles exact-label accuracy fell 2.6428pp, 1.3663pp and 6.0533pp;
shuffles NLL worsened 11.5188%, Ritual 20.6457%, and gold 24.6343%. All outputs
were finite/legal, but the principal, accuracy and important-slice gates failed.

The native 3-encoder runtime experiment was therefore not implemented or
timed. Separate maxHP and HP encoders remain in the runtime; survival, potion,
downstream models, support predicates and defaults are unchanged. This rejects
the exact frozen substitution, not every possible jointly trained shared
architecture. See [the evidence packet](../../experiments/evidence/shared_hp_downstream_2026-09-16.md)
and [ledger-06 §285a](../../experiments/ledger-06.md).

The experiment is replayable with the tracked
[`shared_hp_downstream` driver](../../../tools/combat_transition_shared_hp_downstream.py);
its receipt records the artifact/cache bindings, exact row selection, isolated
`z` substitution, driver SHA, and a maximum replay metric difference of
`9.53e-08`. The historical dedicated `z` cache remains the metric reference
because the original cache used different inference arithmetic than the CPU
replay; the regenerated-versus-cache difference is recorded explicitly.

### Retrained downstream consumers for the qualified DeepSets representation

The exact downstream retraining follow-up is **`DEEPSET_DOWNSTREAM_GO`** on the
same eligible source-grouped VALIDATION cohort of 17,950 rows. It precomputed
only the frozen corrected PR #205 DeepSets encoder output (`[N,64]`) and
retrained the existing relic/turn/card/attack/shuffle, Writhing, Ritual and
gold consumers with the same 12-epoch, batch-512, AdamW recipe. The DeepSets
encoder, maxHP/HP heads and HP delta embedding were excluded from the
optimizer. Potion representation, decoder, traces, labels, support predicate,
candidate generation, legality masks and native-rule helpers were unchanged.

Relative to the hash-verified dedicated-HP downstream reference, joint NLL
improved 0.4115%. Turns, attacks, cards and shuffles stayed within the fixed
2% NLL and 0.005 singleton-accuracy gates; their NLL changes were −1.0592%,
+0.1175%, −0.3111% and −1.9974%, and their accuracy deltas were +0.1705pp,
+0.7407pp, +0.8675pp and +0.8071pp. Writhing, Ritual and gold NLL changed by
−1.8988%, −7.3414% and −1.0014%, each inside the fixed +5% important-slice
gate. All outputs had finite metrics, normalized probabilities and positive
exact legal target mass under the existing masks; TEST rows were neither
encoded nor inferred.

This qualifies the frozen DeepSets representation for these retrained offline
downstream consumers only. It does not qualify the full CTM, potion or
survival sharing, native runtime, gameplay, OOC MCTS, speedup or default
promotion. The actual downstream-eligible TRAIN fit population was 150,404
rows / 18,286 sources; the separate 393,677-row population is retained only
as the DeepSets encoder's bound TRAIN normalization population. See the
[downstream evidence report](../../experiments/evidence/deepset_downstream_2026-09-16.md),
[machine-readable receipt](../../experiments/evidence/deepset_downstream_2026-09-16.json)
and [ledger §287](../../experiments/ledger-06.md).

### Shared maxHP+HP representation for potion decoding

The sequential frozen substitution screen is **`SHARED_ENCODER_POTION_REJECTED`**.
PR #197's qualified epoch-37 shared maxHP+HP Attention encoder was frozen and
compared with the dedicated potion encoder using fresh decoder-only fits on
the exact current final-union TRAIN/VALIDATION winning rows. Validation exact
trajectory NLL was 0.507205895 for the dedicated potion representation and
0.530769047 for the shared representation (**+4.6457%**, above the fixed 2%
limit). The recursive-Brew slice regressed 22.3968%. No-change Brier and
action-mode accuracy remained within bounds; illegal probability was exactly
zero and normalization remained within tolerance.

Both decoder fits selected epoch 12. The shared validation curve descended at
every epoch, but the absolute gap did not close (0.02344 NLL at epoch 11,
0.02356 at epoch 12), so this is not evidence that the shared arm was catching
up faster under the fixed recipe. A longer decoder-only epoch-cap diagnostic,
if desired, is a separate experiment.

The teacher-forced gate therefore stopped the planned ancestral diagnostic.
There was no TEST inference, joint fine-tuning, runtime/export, gameplay or
promotion. This rejects the exact frozen substitution and decoder recipe, not
all shared architectures or intrinsic information absence. The dedicated
potion encoder and all qualified current components remain unchanged. See
[ledger-06 §282](../../experiments/ledger-06.md) and the
[screen evidence](../../experiments/evidence/shared_potion_encoder_screen_2026-09-16.md).

### Qualified DeepSets representation for potion decoding

The sequential frozen DeepSets substitution screen is also
**`DEEPSET_POTION_REJECTED`**. The corrected qualified PR #205 DeepSets
representation was frozen, the dedicated potion encoder was used only for the
control representation, and both arms trained fresh byte-identically
initialized potion decoders with the exact existing 64-action trajectory DAG
and fixed 12-epoch decoder-only recipe. This is a distinct result from the
earlier shared-Attention screen.

On the exact final-union winning TRAIN/VALIDATION population, selected epoch
12 validation trajectory NLL was 0.506803228 for the dedicated control and
0.537569223 for DeepSets (**+6.0706%**, above the fixed +2% gate). Normal
action-mode accuracy dropped 1.2154 percentage points, beyond the 0.01 gate;
no-change Brier remained within its limit. Brew, Smoke and trajectory-special
NLL changes were +2.7248%, +4.9113% and +3.0868%, while recursive Brew
regressed **+19.1859%**, an obvious slice regression. Legal probability was
exactly zero and normalization remained within tolerance.

The follow-up that jointly trained a potion-specific DeepSets encoder and
trajectory decoder is a **narrow miss**. The warm-start arm reached validation
trajectory NLL `0.487162724` (`-3.8754%` versus the dedicated Attention
reference), improving on the frozen substitution result, while scratch reached
`0.498382425` (`-1.6616%`). The existing teacher-forced gate still rejects both
arms because recursive Brew regressed `+13.3126%` for warm start and
`+33.4429%` for scratch (12 validation rows); warm-start Brew also regressed
`+7.0897%`, while Smoke improved `-16.5479%` and trajectory-special regressed
`+3.1766%`. The run retained zero TEST encoding/inference rows; no TEST scoring,
export, native parity, latency, gameplay, OOC MCTS, or default promotion
occurred. The loader reads the prepared cache as a whole, but TEST examples did
not enter encoding, evaluation, selection, or debugging. This result supports
only a bounded next experiment after inspecting the recursive-Brew validation
cases. A review hypothesis is that the encoder's `z` retains initial potion
inventory information at recursive DAG nodes while the decoder's separate
current-inventory input changes; this is unverified and should be tested before
choosing an architecture change. It does not qualify the model or establish
the cause of the remaining slice gap. See
[ledger-06 §338](../../experiments/ledger-06.md) and the
[potion-specialist evidence](../../experiments/evidence/potion_specialist_deepsets_2026-09-23.md).

### Potion-pooled-blind DeepSets follow-up

The paired warm-start follow-up is **`POTION_DEEPSET_POTION_BLIND_REJECTED`**.
The control reproduced PR #298 W closely (validation NLL `0.486931329` versus
`0.487162724`). P zeroed only the pooled potion identity/slot block before the
same trunk; global inputs, including `potionCount` and `potionCapacity`, stayed
unchanged as specified. P retained strong overall validation trajectory NLL
`0.489927014` (`-3.3299%` versus Attention), improved no-change Brier and kept
illegal probability exactly zero. The existing teacher-forced gate still
rejects P: recursive-Brew NLL was `3.026048` versus Attention `2.412967`
(`+25.4078%`) and control C `2.985346` (`+0.040702` nat paired mean). P
improved on 5 of the 12 cases and worsened on 7, so no consistent case-level
fix appeared. This weakens the hypothesis that the pooled potion block alone
causes the recursive-Brew regression; it does not isolate the remaining global
potion-count/capacity signal or establish another cause. The raw receipt records
zero TEST encoding/scoring/teacher-metric rows. No ancestral stage, TEST use,
export, native parity, runtime change, or gameplay qualification was run.
See [ledger-06 §339](../../experiments/ledger-06.md), the
[experiment report](../../experiments/evidence/deepset_potion_blind_2026-09-23.md),
and its [raw receipt](../../experiments/evidence/deepset_potion_blind_2026-09-23.json).

### Experimental DeepSets CTM with Entropic Brew fallback

An opt-in hybrid implementation now uses the PR #298 W potion-aware specialist
for predictor-visible pre-combat inputs without Entropic Brew and dispatches
the whole transition to the current standard Attention CTM whenever Brew is
present. Specialist parity and hybrid/direct-child state/RNG identity passed on
the frozen 31-row fixture set. On the same 10 non-Brew fixture rows supported
by fast DeepSets, median preparation was 3.715 ms standard and 0.491 ms fast
(7.57x). In the subsequent canonical 64-pair OOC engineering screen at frozen
source `9ce11fdbe50f32b4b2646dd8a0803c6dc0c3f351`, standard won 40 and hybrid
39; paired win delta was `-1.56 pp` (95% CI `[-14.06,+10.94] pp`), an
**inconclusive** quality estimate. Across 1,135,061 OOC hybrid preparations,
4,219 used Brew fallback (`0.372%`) in this 64-seed cohort. Observed mean
bestbench elapsed time was lower (641.4 vs 439.7 s/seed), as was mean MCTS CPU
(139.35 vs 94.85 s/seed); this is
runtime evidence under changed search trajectories, not a matched-work causal
estimate. The observed 64-pair difference was small, but its uncertainty still
includes a sizable win-rate regression. The screen is not equivalence evidence
or a default-promotion gate. The specialist
remains offline-rejected; the hybrid remains unqualified and opt-in only. A
separate larger confirmation is warranted before any promotion. See
[ledger-06 §342](../../experiments/ledger-06.md) and the
[mechanism/timing/paired OOC packet](../../experiments/evidence/deepset_entropic_brew_hybrid_2026-09-24/README.md).

### Qualified DeepSets representation for survival prediction

The matched frozen survival-head screen is **`DEEPSET_SURVIVAL_REJECTED`**.
The TRAIN-only full-union survival Attention encoder and the corrected
qualified PR #205 DeepSets encoder were frozen. Only fresh byte-identically
initialized survival heads were trained with the same 12-epoch, batch-512,
FP32 AdamW recipe and identical epoch permutations on all original
TRAIN/VALIDATION rows. No TEST rows were encoded or scored.

Arm A selected epoch 10 at validation NLL `0.059312280`; Arm B selected epoch
12 at `0.083209150`, a **+40.2899%** degradation. Brier worsened **+37.5178%**.
Observed-death NLL worsened **+44.2850%**, and the supported low-pre-HP slice
(`756` rows, `292` deaths) worsened **+55.8470%**. All four fixed gates failed.
The original dedicated survival component's recorded validation NLL was
reproduced as `0.059494425`, and the selected heads reloaded from disk without
metric drift.

This rejects the exact frozen victory-distilled DeepSets representation plus
matched survival-head recipe for survival. It does not establish intrinsic
information absence and does not authorize fine-tuning, a replacement runtime
encoder, or a broader architecture search. The next clean option, if pursued,
is a separately designed survival-specific representation. No TEST, runtime,
native export, gameplay, OOC MCTS or promotion work occurred. See
[ledger-06 §290](../../experiments/ledger-06.md) and the
[DeepSets survival evidence](../../experiments/evidence/deepset_survival_screen_2026-09-16.md).

### Converged linear survival probe

The S1 follow-up remains **diagnostic, not a qualification**. Full-batch
strong-Wolfe L-BFGS with identical L2 `1e-4` was fit on TRAIN for both existing
frozen embeddings, with validation evaluated once after convergence. The
DeepSets arm improved from the fixed-12-epoch probe's validation NLL `0.083209150`
to `0.079102747`; the Attention control was `0.059344385`. The relative NLL
gap narrowed from **+40.2899%** to **+33.2944%**, but death NLL and low-pre-HP
NLL still regressed **+37.6878%** and **+41.4150%**. This reduces but does not
eliminate the stopping-rule explanation. Proceed to the matched tiny nonlinear
S2 decoder before changing the encoder. See [ledger-06 §291](../../experiments/ledger-06.md)
and the [S1 evidence](../../experiments/evidence/deepset_survival_lbfgs_2026-09-16.md).

The scale-neutral S1b follow-up also remains **diagnostic**. Independent
TRAIN-only z-scoring and unregularized L-BFGS reduced the DeepSets validation
NLL gap to **+29.4618%**; Brier, observed-death NLL and low-pre-HP NLL gaps
were +28.6715%, +32.9193% and +33.1960%. Eleven DeepSets dimensions were
constant on TRAIN and were safely centered with unit scale. The residual gap
is therefore not explained by the raw-feature-scale/L2 interaction alone.
S2 is justified next on the same frozen embeddings. See [ledger-06 §292](../../experiments/ledger-06.md)
and the [S1b evidence](../../experiments/evidence/deepset_survival_s1b_2026-09-17.md).

### Nonlinear survival decoder over frozen representations

The matched S2 decoder is **`S2_NONLINEAR_DIAGNOSTIC`**. A fresh
`Linear(64,64) → ReLU → Linear(64,1)` decoder recovered part of the scale-neutral
S1b gap: DeepSets validation NLL moved from **+29.4618%** to **+21.3171%**
relative to the Attention control. Brier remained +21.8116%; observed-death
NLL +17.6745%; low-pre-HP NLL +20.9588%. The nonlinear head therefore recovers
real interactions, but the remaining gap is still clearly above the `10%`
stop threshold and is concentrated in the important death/low-HP slices.

Stop trying to decode survival from this frozen victory-distilled general
representation. The next clean route is a survival-specific DeepSets encoder
trained on all TRAIN combats including deaths, optionally with the qualified
Attention specialist as a soft teacher. See [ledger-06 §293](../../experiments/ledger-06.md)
and the [S2 evidence](../../experiments/evidence/deepset_survival_s2_2026-09-17.md).

### Survival-specific DeepSets fit

The fixed warm-start survival adaptation is **`SURVIVAL_DEEPSET_REJECTED`**.
Training the corrected PR #205 encoder on all survival TRAIN rows selected
epoch 23, but DeepSets VALIDATION NLL remained +5.9990% and Brier +6.0802%
above the Attention specialist, failing the fixed +2% and +5% gates. Death
NLL (+6.2773%) and low-pre-HP NLL (+3.8294%) passed. The candidate remains
offline-only, with zero TEST inference and no runtime change. By the
preregistered miss routing, Attention-teacher distillation is the plausible
next separate hypothesis, not a rescue adjustment to this run. See
[ledger-06 §294](../../experiments/ledger-06.md) and the
[fit evidence](../../experiments/evidence/survival_specific_deepset_fit_2026-09-17.md).

The subsequent six-arm LR/weight-decay sweep also rejects all candidates.
Strong-WD (`1e-4` encoder LR, `1e-3` head LR, `1e-3` decay) is best at
epoch 20: NLL `0.062930815` and Brier `0.018841730`, still +5.7760% and
+5.7627% above Attention. This improves baseline NLL only 0.2104%; lower
learning rates did not close the gap within the fixed 40-epoch budget.
The much-lower-LR arm selected epoch 39 at the cap, so its convergence is
not established. These results reject the tested settings, not DeepSets
as an architecture. Optional LR-decay continuation remains untested; no
distillation, TEST, runtime or promotion followed. See [ledger-06 §296](../../experiments/ledger-06.md)
and the [sweep report](../../experiments/evidence/survival_deepset_sweep_2026-09-17.md).

Five-fold source-grouped Platt calibration of frozen strong-WD does not close
the gap: cross-fitted NLL `0.062660988` (+5.3225%) and Brier `0.018729319`
(+5.1317%) still fail the original overall limits. Death/low-HP gates pass.
This removes only about 8% of excess NLL, disfavoring global affine calibration
as the main explanation. It is diagnostic only: the calibrators exclude each
scored source, but the model/epoch were already selected on this VALIDATION
set. See the
[calibration evidence](../../experiments/evidence/survival_platt_crossfit_2026-09-17.md).

The paired 64-wide joint survival/HP experiment also rejects both arms.
Both recompute normalization on all 408,183 TRAIN rows, use identical fresh
heads and epoch orders, and select solely by VALIDATION survival NLL.
The historical PR #161 optimizer schedule (batch 2048, AdamW 1e-3/1e-4,
cap 12, patience 3, seed 20260911) favors the PR #205 warm-start over scratch:
warm epoch 12 NLL `0.063309319` (+6.4122%), scratch epoch 4 NLL `0.069789790`
(+17.3048%). Both fail NLL, Brier and death NLL; scratch also fails low-HP NLL.
Warm's best epoch is at the cap, so convergence is not established. The
experiment isolates initialization within this joint-loss setting, not the
individual effects of HP auxiliary loss or normalization. No widening or
runtime qualification follows. See [paired evidence](../../experiments/evidence/survival_deepset_aux_paired_2026-09-17.md).

The requested smallest architecture increase—joint fine-tuning strong-WD with
a `64→64→1` ReLU head—also rejects. Selected epoch 6/12 has NLL
`0.063041106` (+5.9614%) and Brier `0.018754756` (+5.2745%); death NLL fails
at +15.8636%. This one joint run cannot isolate head architecture from
additional encoder updates, but it does not materially close the gap. No trunk
widening follows without a new explicit plan. See
[MLP evidence](../../experiments/evidence/survival_mlp_joint_2026-09-17.md).

The requested frozen-encoder head-only diagnostic also rejects: epoch 10/16
NLL `0.062951967` (+5.8115%), Brier `0.018761696` (+5.3135%), death NLL
+13.6766%. It isolates a nonlinear head from encoder updates, but the unchanged
strong-WD representation still does not pass. No widening follows without a new
explicit plan. See [head-only evidence](../../experiments/evidence/survival_mlp_head_only_2026-09-17.md).

The authorized width-96 scratch survival-only experiment also rejects. With
unchanged embeddings, entity outputs 96, trunk 384→192→96 and a linear head,
the strong-WD schedule selects epoch 14/20: NLL `0.065301903` (+9.7614%),
Brier `0.019292932` (+8.2954%), death NLL +21.4414%; low-HP +8.1272% and
validity pass. All-TRAIN normalization is fixed throughout. No speed screen
ran. This tests the requested wider scratch recipe, not an isolated width
effect versus the warm-started width-64 baseline. It does not prove interaction
structure is necessary. Further scaling/tuning is not part of this experiment.
See [width-96 evidence](../../experiments/evidence/survival_wide96_2026-09-17.md).

The authorized width-96 maxHP/HP pretraining followed by strong-WD survival
fine-tuning also rejects. It preserves PR #205's victory-only population,
normalization, teacher hashes, equal-weight KL objective and 40-epoch AMP
schedule. Only the specialist 8-D delta embedding is copied; the compatible
HP MLP is fresh 104→64→304, and maxHP is fresh 96→11. Only the selected encoder
transfers to a fresh linear survival head, retaining pretraining normalization.
The existing survival NLL selection and fixed gates are unchanged. Pretraining
selects epoch 39/40 and passes its diagnostic gates; survival selects 14/20:
NLL 0.062599011 (+5.2183%), Brier 0.018578166 (+4.2833%), death NLL +16.0179%,
low-HP +3.2761%. NLL and death gates fail; Brier, low-HP and validity pass.
Pretraining improves on scratch width-96 but does not qualify survival.
Stop this scaling direction rather than add optimizer or width sweeps. This
does not establish pairwise interactions as necessary. No speed screen, matched
width-64 control, TEST, runtime export, gameplay or promotion ran.
See [pretrained width-96 evidence](../../experiments/evidence/survival_wide96_pretrained_2026-09-17.md).

### Jointly adapted shared maxHP+HP+potion representation

The requested follow-up is **`SHARED_TRANSITION_POTION_REJECTED`**. Starting
from PR #197's qualified epoch-37 shared Attention encoder, one fixed FP32
12-epoch run jointly adapted the shared encoder, maxHP/HP heads, and the
existing exact 64-action potion decoder. TRAIN-only calibration normalized the
three losses with `s_max=0.0021965544365230016`,
`s_hp=0.011543620959855616`, and `s_potion=2.281699538230896`; no task-weight
sweep or second seed was used.

All 12 epochs remained inside the PR #197 maxHP/HP preservation gates, with
epoch 12 the earliest strict minimum potion validation trajectory NLL. Against
the current dedicated potion specialist on the same VALIDATION rows, however,
exact trajectory NLL was 0.524099650 versus 0.504024366 (**+3.9830%**, gate
+2%), and recursive Brew was **+20.5168%**. No-change Brier, action-mode
accuracy, legality, and normalization passed their individual checks, but the
primary NLL and obvious recursive-Brew slice gates failed. The mandatory
ancestral qualification was therefore not run.

This closes the specified one-seed jointly adapted architecture/recipe, not
the possibility of every shared architecture or intrinsic potion information
absence. No TEST, runtime/export, promotion, native C++ or gameplay work ran;
qualified components and executable defaults remain unchanged. See
[ledger-06 §283](../../experiments/ledger-06.md) and the
[joint-fit evidence](../../experiments/evidence/shared_transition_encoder_potion_2026-09-16.md).

### 24-epoch jointly adapted shared maxHP+HP+potion representation

The same jointly adapted architecture, population, seed, calibration,
optimizer, and gates was then run for 24 epochs, changing only the epoch
horizon. All 24 checkpoints preserved the maxHP/HP gates, with epoch 23
selected at potion NLL 0.520021881. The dedicated specialist remained better
at 0.504024366, a **+3.1740%** regression above the fixed +2% limit, and
recursive Brew regressed **+20.2797%**. The teacher-forced potion gate failed
again and ancestral qualification was not run. This confirms rejection of the
specified 24-epoch treatment, not every possible shared architecture or
intrinsic potion information absence. See
[ledger-06 §284](../../experiments/ledger-06.md) and the
[24-epoch evidence](../../experiments/evidence/shared_transition_encoder_potion_24_2026-09-16.md).

### Shared relic trajectory residues

**`RELIC_TRAJECTORY_QUALIFIED`** on the audited offline composed support.
Three fixed FP32 decoder fits use the frozen #172 20260912 HP state encoder
and existing certified joint potion model. Mean HOLDOUT decoder-minus-prior
joint relic NLL is −0.010460229; the 1,000-repetition source bootstrap 95% CI
is [−0.013335116, −0.007743432]. Ancestral HP→potion→relic qualification is
`ANCESTRAL_OK`: mean group-normalized exposure −0.002407001 nat, with all
native-domain, shared-residue, unsupported-mutation and deterministic mismatch
counts zero across 16 draws per row per seed. Max HP remains observed.

Native reconstruction shares turn/attack/card/shuffle residues across related
relics; partial labels intersect modular constraints. Certified victories:
TRAIN 224,715 / 17,718 sources; HOLDOUT 25,398 / 1,979 sources. Full relic-vector
mode exact is 0.805667113 versus native+copy-through 0.792700213; these are
secondary metrics. This pre-existing relic corpus has no eligible active Lizard
Tail rows; the later targeted cohort also failed the Lizard-head proper-score
gate, so that head remains unqualified and the offline adapter fails closed.
Inserter has no corpus tokens; its source-derived reconstruction shares the
qualified turn residue but has no relic-specific empirical score.

This is component qualification, not runtime integration. Survival, max-HP,
HP, potion weights, supported-v1 exact combat-RNG continuation and gameplay
remain unchanged. See the [source mapping, fixed protocol and results](../../experiments/evidence/relic_trajectory_2026-09-14.md)
and [machine-readable scores/calibration/slices/hashes](../../experiments/evidence/relic_trajectory_2026-09-14.json).

### Stochastic signed-HP distribution

Signed absolute ΔHP is the engineering parameterization for the next HP-only
experiment; this does not change the historical `HP_TARGET_INCONCLUSIVE`
result above. The categorical model in
`tools/combat_transition_stochastic_hp.py` retains the #170 attention encoder
and observed max-HP-delta embedding, replacing only the scalar output with
304 integer classes, [-160, 143]. The domain is derived from predictor-visible
HP on globally supported states and the frozen max-HP-delta classes, without
post-HP targets. All 398,415 supported winning targets pass its structural
check. Row-specific illegal classes are masked before softmax. Sampling
returns legal post HP and derives ending HP fraction for the existing potion
decoder.

The frozen comparison uses all 286,581 nested TRAIN+VALIDATION victories and
32,345 reused engineering HOLDOUT victories, three seeds, ten AMP epochs,
and the saved #170 signed-delta point controls. Primary scoring is discrete
CRPS against rounded/native-clamped point HP; the safety metric compares
expected-HP MAE with continuous point HP. Rowwise paired differences are
averaged over seeds before source bootstrap. Qualification requires the CRPS
95% CI strictly below zero and the MAE CI not strictly above zero; either CI
strictly above zero rejects. Independent implementation/design review passed
on execution SHA `521e364a08735ad095ed99682e3d5058a6748a46`; all three
fixed fits completed. The result is **`STOCHASTIC_DELTA_HP_QUALIFIED`**:
CRPS difference -1.686834344 HP, 95% CI [-1.715728962, -1.658630531];
expected-HP MAE difference +0.011839528 HP, CI [-0.007041513, +0.029256256].
The safety CI includes zero; this is not a mean-accuracy improvement claim.
All 1,552,560 categorical samples are legal; unsupported probability is zero.
Equal-tail interval coverage is above nominal levels. Healing CRPS improves
for every seed, while healing mean-accuracy results are mixed.

This qualifies the HP distribution under the specified offline engineering
rule on reused HOLDOUT and observed max-HP conditioning. It does not qualify
sampled-upstream composition, multi-fight planning or deployment. Survival,
max-HP modeling, potion weights, relic support and RNG contracts are unchanged.
No runtime C++ integration or gameplay qualification was performed. Relic
training remains a separate future task. See [ledger-06 §239](../../experiments/ledger-06.md)
and the [full scores, calibration, slices and hashes](../../experiments/evidence/stochastic_signed_hp_2026-09-14.md).

### Phase-2 attention representation ablation

The authorized attention ablation used the same final support boundary,
`combat_predictor_input_v1`, source-group split, losses, optimizer, and frozen
TEST as the DeepSets Phase-2 fit. The known Phase-1 attention encoder was
width 64 with two Transformer layers, four heads, FF width 128, typed GLOBAL /
CARD / RELIC / POTION tokens, explicit relic order and potion slots, and no
arbitrary positions for exchangeable card tokens. No new data or runtime
integration was used.

Attention Phase-2 selected 11 epochs and attention point-control selected 10;
both were refit from scratch on TRAIN+VALIDATION. On TEST, Phase-2 survival
Brier/log loss were `0.019920463/0.066628456` versus
`0.019039775/0.063621797` for its point-control: absolute degradations
`+0.000880687/+0.003006653`, relative degradations `+4.6255%/+4.7258%`.
Source-seed bootstrap 95% intervals were strictly positive for both primary
error deltas, so the result is **`ATTENTION_CORE_REGRESSION`**, not
`ATTENTION_AVOIDS_CORE_REGRESSION`. AUC and HP errors improved, while the HP
distribution CRPS improved from the point-control degenerate `0.070421` to
`0.045763`; potion full-vector exact remained below copy-through, while relic
full-vector and changed-counter metrics improved. This supports the generic
multitask-interference hypothesis: do not enlarge or switch the Transformer;
the next experiment should freeze or separate the core predictor. The exact
RNG continuation audit above resolves the state contract; runtime multi-fight
integration and qualification remain pending. See
[ledger-06 §232](../../experiments/ledger-06.md) and the
[attention ablation evidence report](../../experiments/evidence/combat_transition_surrogate_attention_ablation_2026-09-13.md).

### Frozen attention survival composition and potion support

The inference-only frozen A/B/C diagnostic is
**`REPRODUCED_AND_CORE_PRESERVED`** for composition and
**`INSUFFICIENT_AFTER_CORRECTION`** for potions. B preserves point-control
survival and the Phase-2 conditional distribution exactly; joint alive-HP
error improves on the reused engineering TEST. This is an implementation
invariant and paired diagnostic, not new learning or causal proof of gradient
interference. C removes substantial invalid potion support and improves NLL,
exact accuracy, and no-change-event Brier, but vector exact remains below
copy-through and potion-count accuracy regresses. Certification is conservative
and never narrows the 413,799-row global eligibility set.

Deployment remains **`NOT_QUALIFIED`**. The subsequent native legality gate
checked all 510,030 frozen rows with zero counter contradictions among the
unchanged 413,799 supported rows. Intersecting historical relic logits with
native reachable post-counter states removes 24 invalid modes (including the
eight Sundial cases) and improves counter-token NLL `0.452449 → 0.422720` on
reused global TEST victories. This inference correction does not retrain the
relic head, prove joint counter reachability, or solve RNG continuation.

The authorized prospective potion-decoder comparison now has a frozen split
nested exclusively inside original TRAIN: 15,971 / 2,001 / 2,014 sources.
The implementation uses a fixed ten-epoch TRAIN-only attention point-control
state encoder and compares independent Bernoulli versus exact 32-mask heads
with identical full five-slot inventory features, hidden width and
teacher-forced upstream conditioning. The independent head outputs all five
Bernoulli logits from that shared representation; the candidate outputs 32
categorical logits, isolating the distribution-family comparison. Validation joint-mask NLL
selects head epochs; fresh nested HOLDOUT supplies the primary paired source
bootstrap decision. Ancestral qualification is separate and uses historical
upstream checkpoints, which previously saw these original TRAIN sources.
The reviewed fit executed exactly
`9f15dba5c348f775725232d33e72d2cf8e1b6127`. On all 25,398 fresh nested
HOLDOUT victories, independent NLL is `0.5189140431` and joint NLL is
`0.5166171565`; joint minus independent is `−0.0022968866`, paired source
bootstrap 95% CI `[−0.0042045537, −0.0006352932]` (1,979 eligible sources,
1,000 resamples). The interval is entirely below zero, so the frozen primary
classification is **`JOINT_MASK_WINS`**. Both heads selected 12 epochs;
the ten-epoch encoder remained TRAIN-only and frozen. Separate ancestral
classification is **`ANCESTRAL_OK`** under the unchanged exposure criterion,
with zero invalid potion samples or identity creation/swaps. Secondary metrics
and ancestral behavior do not override the primary rule. Runtime RNG continuation
remains unimplemented and deployment remains `NOT_QUALIFIED`. See
[ledger-06 §236](../../experiments/ledger-06.md),
[fit evidence](../../experiments/evidence/potion_decoder_fit_2026-09-13.md),
and the [frozen protocol](../../experiments/evidence/potion_decoder_v1_2026-09-13.md).

## Current baseline

Use [current-baselines.md](current-baselines.md) as the sole pointer for the
recommended executable configuration and qualified benchmark numbers. Do not
infer a baseline from historical plans, model filenames, or local artifacts.

## Parked lines

### Semantic OOC confirmation and first frozen scorer

The fresh 1,024-decision confirmation at merged producer `a6c2abb` is
**SEMANTIC CONFIRMED for the frozen probe on the natural, reward-dominated
mixture**: semantic macro pairwise is 0.5732 versus primitive 0.5304, paired
95% difference interval [0.0293, 0.0561]. Mean regret is slightly lower but
uncertain; formal regret noninferiority and all-family superiority are not
established. SHOP's earlier weakness was not reproduced, while EVENT remains
an adverse, uncertain slice. No runtime policy or production model changed.

The same fights yielded 7,652 combat rows with zero additional Silver
simulations. **COMBAT LABELS ADEQUATE** passes the inherited row-count screen:
348 nonambiguous deaths, including 48 test rows. Those test deaths represent
only 10 source groups; one contributes 19 rows, so independent loss coverage
remains limited. The subsequent counterfactual combat-evaluator feasibility
study is recorded separately in [ledger-06 §219](../../experiments/ledger-06.md):
it is promising for survival and winning HP but inconclusive on the loss tail,
and is not deployed. The bounded comparison then trained the prespecified
factorized-XGBoost, direct-signed-XGBoost, source-balanced-XGBoost, and compact
multitask-MLP finalists. It found **NO CLEAR MODEL IMPROVEMENT**: the best
tuned factorized finalist was slightly worse than the frozen baseline on TEST,
and every conditional loss model remained at or above the trivial death-mean
baseline. The larger-capacity fits improved TRAIN without improving held-out
value, which is a capacity-not-the-bottleneck signal under this corpus. The
comparison packet was corrected after independent review for its Brier
bootstrap, NN direct-head selection, and truth-tied concordance; the corrected
analysis still reaches the same conclusion. No runtime model, Silver
replacement, or gameplay qualification is authorized. See [ledger-06 §§218–222](../../experiments/ledger-06.md), the [coverage packet](../../experiments/evidence/semantic_combat_confirmation_2026-09-10.json),
and the [model-comparison evidence](../../experiments/evidence/combat_evaluator_model_comparison_2026-09-10.json).

The first offline semantic action scorer is now frozen and passes its fresh
model holdout: training on the 1,024 development decisions produced 1,831
features (1,017 state plus 814 semantic action), and the untouched
993024–993151 cohort contains 128 decisions and 935 rows with zero validator
failures. Semantic macro pairwise is 0.5550 versus primitive 0.4903 and the
state-only null 0.5000; mean selected regret is 0.0430 versus primitive
0.0451. The paired 5,000-replicate 95% interval for semantic-minus-null
pairwise is [+0.0113, +0.0989]. This is an **offline model pass**, not a
runtime, win-rate, or production-compatibility result. Compound-containing
decisions (12) and EVENT (8) remain small/noisy slices; the semantic compound
regret point estimate is worse than primitive despite better pairwise ranking.
No runtime policy or C++ model export changed. See [ledger-06 §220](../../experiments/ledger-06.md)
and the [frozen model evidence packet](../../experiments/evidence/semantic_ooc_model_v1_2026-09-10.json).

### Silver CPU optimization qualification

The exact-search CPU pass has a bounded local pilot at implementation
`f8873cd`: diagnostic gating, exact widening/UCB shortcuts, and compact sorted
status storage preserve the checked labels and search traces. GCC PGO is
available as an opt-in build experiment. Broader production qualification remains parked. The compact chance-node
follow-up at `255d8f1` now separates reusable decision-state storage from
logical node bookkeeping: the local three-seed pilot reduces peak RSS by
7.3–17.6% with essentially unchanged CPU cost. This is a memory improvement,
not a demonstrated additional CPU speedup. New PGO profiles would be required
for the changed source/layout. See
[the original CPU evidence](../../experiments/evidence/silver_exact_search_2026-09-10.json),
[the storage evidence](../../experiments/evidence/silver_chance_storage_2026-09-10.json),
and [ledger-06 §§215–217](../../experiments/ledger-06.md).

The direct final-layout confirmation against current main `3bec0b1` at frozen
PR head `4224c03` meets the predeclared 5% aggregate CPU bar: 6.32% lower CPU
with PGO off and identical matched labels/telemetry. This is a three-seed,
two-repeat selected-workload check, not broad qualification. See the
[final-layout packet](../../experiments/evidence/silver_final_layout_ab_2026-09-10.json).
The earlier PGO result still belongs to its earlier source revision.

The follow-up chance-replay diagnostic is **mixed and parked**. On the real
Silver chance-selection path, weighting capped replay by fresh-generator
multiplicity lowered synthetic value RMSE by roughly 21–43% at budgets 32–512
across 50/50, 80/20, deduplicated, and 16-state high-entropy fixtures, but it
reduced close root-action accuracy on the 0.60-versus-0.58 fixture from
76.6–78.9% to 71.1–73.4%. The treatment remained default-off and no gameplay
screen was originally authorized. At the user's explicit request, a follow-up
32-seed gameplay screen then ran at 1,000 simulations per root: A won 19/32
seeds versus B's 15/32. B's mean floor was slightly higher (47.47 versus
46.53), but it had more lost fights (17 versus 13) and five A-win/B-loss
disagreements against one A-loss/B-win. This is unfavorable on wins and does
not qualify the treatment at 1,000 simulations. A requested 10,000-simulation
follow-up on the same seeds then reversed the small-screen direction: A won
19/32 and B won 22/32, with B also higher in mean floor (49.28 versus 47.47),
ending HP (30.31 versus 28.53), and lower in fights lost (10 versus 13).
This is an encouraging budget-interaction signal, but the initial 32-seed
result alone did not qualify B. The fresh 32-seed block met the
predeclared +4 net paired-win escalation trigger, so a second fresh block was
run. Across 64 fresh seeds, B won 46 versus A's 41, with 9 A-loss/B-win
versus 4 A-win/B-loss disagreements (net +5); B's mean ending HP was 38.91
versus 30.83 and fights lost were 18 versus 23, at a mean cost of 47.28
seconds per run. This is a 64-seed signal supporting a proper promotion test,
not a production qualification; the default remains A and no parameters were
tuned between screens. See
[ledger-06 §§223–226](../../experiments/ledger-06.md),
the [synthetic raw matrix](../../experiments/evidence/silver_chance_frequency_2026-09-11.csv),
the [1k paired gameplay rows](../../experiments/evidence/silver_chance_gameplay_screen_2026-09-11.csv),
the [prior 10k paired gameplay rows](../../experiments/evidence/silver_chance_gameplay_screen_10k_2026-09-11.csv),
and the [10k 64-seed aggregate](../../experiments/evidence/silver_chance_gameplay_screen_10k_fresh32-95_2026-09-11.csv).
The experiment-only runtime flag, fixture executable, and searcher hook were
removed before merging the evidence; no B implementation or opt-in runtime
path remains.

The separate §349 rollout-cost candidate tested an early energy rejection (A)
and rollout-only unsorted unknown piles (B). A preserved deterministic outputs
but had no speed gain and was reverted. The original instrumented fixed-work
screen measured about 11% lower B CPU, but its reported 35/59-versus-40/59
action comparison was invalid: control's 1k search was a prefix of its same-seed
10k teacher, while B mapped the same RNG values to different cards. Those
counts are withdrawn as a quality result, not evidence of a B regression.

The planned independent-teacher DEV follow-up is complete under the disclosed
execution seed transform. An evidence audit found that its helper used
`teacher/NN` and `arm/NN` hash path components, while the committed protocol
specified `teacher-NN/NN` and `arm-NN/NN`; no durable pre-run amendment was
retained. All identities remain deterministic and pairwise distinct per root,
but exact preregistration fidelity is unresolved (details are in the follow-up
packet). B remains explicitly default-off. On 52 roots with teacher-majority
consensus, matched fixed-work first-action agreement was 54.3% control versus
58.7% B, a paired
mean of `+4.3 pp` with a root-cluster 95% interval of `[-1.4,+10.1] pp`. The
non-negative mean triggered a conditional 1,000-control/1,100-B
equal-time-equivalent screen, which measured 54.3% versus 61.5% (`+7.2 pp`,
95% interval `[+1.0,+13.5] pp`). Four uninstrumented 1k CPU pairs measured
mean user CPU of `0.740 s` control versus `0.675 s` B (`-8.8%`), with B lower
in all four pairs. These are DEV first-action and local CPU signals; no
complete-combat gameplay, holdout, or default qualification was run. A separate
instrumented profile estimated `getIncomingDamage` at 2.6% inclusive, so no
fragile cache was implemented. Chance duplicate counters were exposed by
category, but exact support exhaustion was not established. B remains
experimental and is not qualified for promotion. See [ledger-06 §349](../../experiments/ledger-06.md),
the [corrected follow-up protocol](../../experiments/evidence/silver_rollout_cost_20260924/review_followup/PROTOCOL.md),
the [follow-up results and raw evidence](../../experiments/evidence/silver_rollout_cost_20260924/review_followup/README.md),
and the [complete rollout-cost packet](../../experiments/evidence/silver_rollout_cost_20260924/README.md).
The native Silver analogue (draw pile only) was rejected at its profile
gate: removable rollout-only sort work is about 2% of native search CPU
([ledger-06 §350](../../experiments/ledger-06.md)).

### Whole-Act OOC evaluator

The corrected evaluator passed its serial/parallel and worker-coverage canary,
but the full corrected run was aborted after about 88 minutes because
occurrence-level exact-state evaluation expands to roughly 164,800 combat
cells. No valid scientific result exists; the line is parked pending either a
cheaper decision-relevant evaluation design or explicit authorization for the
required compute. See [PR #111](https://github.com/pherrman1/sts_ai/pull/111),
[ledger-06 §213–§214](../../experiments/ledger-06.md), and the
[current evaluator contract](../architecture/out-of-combat.md#offline-whole-act-encounter-distribution-evaluator).

### Encounter-marginalized strategic labels

Matched M1 encounter-marginalized labels did not separate from M0 fixed-world
labels at 2,000 source seeds and remained below deployed V4 on the corrective
same-block calibration. Further scaling is not justified without a new premise
that identifies the binding label, controller, feature, capacity, optimization,
or horizon constraint. See the
[maintained synthesis](../research/ooc/encounter-marginalization.md) and
[ledger-06 §168–§169](../../experiments/ledger-06.md).

### Silver reuse-cap scaling

Active-pool accounting causally removed the sticky allocated-cap reroot failure,
but did not establish agent value and exceeded the runtime limit; allocated
accounting remains the default. The next narrow question is whether cap-fallback
decisions improve against a high-budget fresh-root reference, not a promotion
gate or runtime optimization. See the
[frozen evidence](../../experiments/evidence/silver_reuse_cap_scaling_2026-08-26.json)
and [ledger-06](../../experiments/ledger-06.md) (search for "Silver reuse-cap
scaling experiment").

### Searcher3 belief filtering and rejuvenation

Closed: Searcher3 was removed (ADR-0019).

Exact real-observation filtering is semantically promising but remains opt-in;
persistent transfer is not in the executable, and single-child AI_RNG
rejuvenation stayed mixed/inconclusive with possible downside tail risk. A new
action/quality confirmation with an explicit downside rule is required before
promotion or broader rejuvenation work. See the
[belief-state synthesis](../research/combat-search/belief-state.md) and
[ledger-06](../../experiments/ledger-06.md) (search for "AI1 single-child
confirmation").

### Searcher3 particle count

Closed: Searcher3 was removed (ADR-0019).

128 particles remains directionally promising but unconfirmed; 64 remains the
default. The next justified action is a full-block confirmation on the current
stack before studying a particle-by-simulation interaction. See the
[particle-budget synthesis](../research/combat-search/particle-budget.md) and
[ledger-01 particle-count sweep](../../experiments/ledger-01.md).

## Closed / rejected lines

### Explicit K1/H1 OOC action selection

K1 exact-10k and H1 were selected as the economical clean-label schedule and
the issue-19 pipeline passed its health pilot, but the resulting explicit
one-combat planner lost its preregistered action-selection screen against V4.
Do not proceed to planner productionization, tuning, replacement-corpus
generation, or training from this result. See
[ledger-06 §207–§212](../../experiments/ledger-06.md), the
[pipeline-health evidence](../../experiments/evidence/ooc-clean-pilot-healthy-2026-09-01.json),
and the [planner evidence](../../experiments/evidence/ooc-v4-h1-explicit-planner-2026-09-02.json).
The closed `ooccleanpilot`, `oocv4h1collect`, and `oocv4h1ref` implementation
was removed after the evidence was preserved; the separately parked whole-Act
evaluator remains available.

### Phase-13A counterfactual teacher-strength audit

The corrected H=8 reference rejected the high-confidence M0 improvement
signal. It did not distinguish teacher/target failure from model-learning
failure, and no new labels, threshold tuning, or gameplay gate was justified.
The collector and short/reference evaluator modes were removed after their raw
evidence was preserved in
[`phase13a-teacher-audit`](../../experiments/evidence/phase13a-teacher-audit/)
and [ledger-06 §173](../../experiments/ledger-06.md).

### Silver root allocation and learned action guidance

Earlier lower root exploration, Sequential Halving, progressive unpruning,
hard candidate pruning, learned ordering, and grouped/rank-4 visit-PUCT priors
produced no stable promotable advantage; ordinary c=25 remains the default.

The complete frozen internal-node finite FPU screen is **`INTERNAL_FPU_INCONCLUSIVE`**.
At the preregistered root metric, 1k CONTROL agreed with 10k CONTROL in 45/64
cases while 1k FPU agreed in 39/64; among 22 1k CONTROL/FPU disagreements, FPU
moved toward the 10k CONTROL reference 6 times and away 12 times. Full 1k and
10k `hard64-dev` cohorts were accepted 64/64 per arm, but whole-combat
nodes/wall/simulation totals are trajectory-confounded after root divergence.
The fixed FPU formulation remains unchanged and is not a production default;
park this particular formulation pending a new hypothesis. Do not tune,
promote, spend holdout budget, or run gameplay qualification from this result.
See
[ledger-06 §332](../../experiments/ledger-06.md) and the
[complete internal-FPU evidence packet](../../experiments/evidence/silver_internal_fpu_20260921/README.md).

The later six-arm root-mechanism replay was a **single-source-seed offline
signal**, not a multi-seed confirmation: informative Teacher-A visit PUCT
beats uniform PUCT (`C-E` mean B-regret delta `-0.412311`, 95% CI
`[-0.717735,-0.139643]`), while uniform PUCT loses to ordinary UCT (`E-A`
`+0.352288`, 95% CI `[+0.092162,+0.653903]`). Informative PUCT versus ordinary
UCT is near zero (`C-A` `-0.060023`, CI crossing zero). Root bootstrap units
were correlated decisions from source seed `0`, so current classification is
**`ROOT_GUIDANCE_INCONCLUSIVE`** and multi-seed confirmation is required. Do
not train a policy, run gameplay, or change the default from this result.
See [ledger-06 §303](../../experiments/ledger-06.md) and the
[six-arm replay evidence](../../experiments/evidence/silver_root_mechanism_2026-09-17.md).

A visit-weighted T20 ensemble of A/A2 versus an independent J50 ensemble of
B/B2 also fails the zero-search screen: top-action agreement is `44/64`, T20
mean J50-regret is `0.534197` versus `0.495031` for original A, and the known
harmful root remains misranked. The proposed ensemble ordering arm is therefore
not run. See the [ensemble audit](../../experiments/evidence/silver_root_teacher_ensemble_audit_2026-09-18.md).

The replacement target premise has now passed its fresh-population audit.  On
32 hash-selected roots from 16 fresh source seeds, an independent eight-by-5k
forced-action ensemble improved over same-root Teacher-A under a disjoint
eight-by-10k judge: mean J-regret delta `-0.328487`, source-seed-clustered 95%
CI `[-0.727297,-0.038122]`; corrected pairwise-concordance delta `+0.119398`,
CI `[+0.062275,+0.194979]`.  Tail and stochastic-action gates also passed.
The evaluator was corrected to retain original-root effective-gold/max-HP
victory utility; rerunning the same frozen roots left regret, selections, tails
and every gate unchanged.  This is a **fresh-population target signal**, not
authorization to train a model.  No model, replay integration, gameplay, or
default change is qualified.  The separate known-harmful-root regression is
still outstanding
because the exact frozen snapshots were unavailable; do not replace it with
recollected roots or interpret the primary pass as that regression.  See
[ledger-06 §321](../../experiments/ledger-06.md) and the
[forced-action evidence](../../experiments/evidence/silver_forced_action_target_2026-09-19/README.md).

The frozen `SilverPriorNetV1` T2/seed-20260922 candidate passed its one-time
LOCKED_TEST expected-regret gates: on 1,494 held-out L roots the model-minus-
uniform delta was `-3.23423` (95% source-seed CI `[-3.53464,-2.93676]`), and on
64 preselected J roots it was `-2.89553` (`[-3.58717,-2.26012]`). The L target
itself improved locked-J regret over uniform by `4.11938` points; the student
recovered 70.29% of that soft-prior headroom. This is frozen offline
generalization evidence, not gameplay qualification or default promotion.
LOCKED_TEST is consumed and must not be used for tuning; the evaluator command
is now disabled for every output path. A bounded root-replay mechanism screen
then evaluated the frozen T2 prior on 64 preselected VALIDATION roots. The
L-target oracle beat uniform PUCT (`-0.26776`, 95% source-seed CI
`[-0.56135,-0.07144]`), while learned-minus-uniform crossed zero
(`-0.03390`, `[-0.11794,0.03651]`) and learned-minus-ordinary-UCT also
crossed zero (`+0.05916`, `[-0.28676,0.37000]`). Its predeclared
classification is **`LEARNED_PRIOR_SEARCH_HEADROOM_NOT_CAPTURED`**: root PUCT
has usable headroom on this development population, but the learned prior did
not capture it. Stop the deployment line based on this mechanism screen. A
separately requested downstream whole-run gameplay diagnostic was subsequently
allowed; that authorization does not revise this screen or establish
deployment. VALIDATION was used for model selection, so this is a mechanism
screen rather than fresh generalization evidence. No gameplay or default
search changed by the offline experiment. See the [root-replay packet](../../experiments/evidence/silver_prior_root_replay_20260923/README.md),
the [ledger-06 result](../../experiments/ledger-06.md), and the
[locked-test evidence packet](../../experiments/evidence/silver_prior_locked_test_v1_20260922/README.md).

The separate pre-review gameplay integration smoke used two explicitly
reserved, non-scientific seeds. The corrected parser sums every combat record:
all four runs completed; treatment telemetry recorded 901 prior evaluations
and 901 root-PUCT decisions total with zero surface failures, while control
made no model calls. Treatment mean inference latency was 6.679 ms/call and
6.930 ms/call on the respective seeds. The legacy logs lack raw per-call
samples, so exact pooled median/p95 are unavailable. Their CSV metadata reports
executable SHA `1dc14cef9f5b6602fe84bd2a266347757245d78c`, not the then-current
candidate `fb9e0cf9510ac612fdc3f521076ca093d1fb55b5`; this is working-tree
integration evidence, not candidate-SHA evidence. The user's 5 ms waiver
allowed the bounded smoke to complete. This confirms runtime execution and
retained reroot operation only.
The subsequent user-authorized full-run online screen completed the frozen 32
paired seeds `24100000..24100031` at reviewed source
`57a824349fd99c917cf22d67e929a8630f001a9d`, exact binary/model hashes, and
fixed project-fair A0 / 1,000-simulation settings. CONTROL won 21/32 and LEARNED
15/32; the paired table was 1 learned-only, 7 control-only, 14 both-win, and 10
both-lose. The `-6` net discordant count yields the preregistered
**`ONLINE_LEARNED_PRIOR_UNFAVORABLE`** classification; paired win-rate delta is
`-18.75 pp` (95% bootstrap CI `[-34.375,-3.125] pp`), exact two-sided p is
`0.0703`. Treat this as the bounded screen's classification, not conventional
statistical significance or broad model invalidity. It does not qualify or
promote a default. The offline `LEARNED_PRIOR_SEARCH_HEADROOM_NOT_CAPTURED`
result remains unchanged. See the [complete online packet](../../experiments/evidence/silver_prior_online_screen_20260923/README.md)
and [ledger result](../../experiments/ledger-06.md).

### Combat leaf/model variants

Raw deep-search utility targets, repeated DAgger, residual correction, sampled
terminal-endHP relabeling, and the initial DeepSets combat VNet failed to
improve the recorded online gates or failed under MCTS distribution shift.
Reopen only with a new premise. See the
[leaf-evaluation synthesis](../research/combat-search/leaf-evaluation.md), the
[model-alternatives synthesis](../research/combat-models/pvnet-and-alternatives.md),
and [ledger-06 §157–§158 and §166](../../experiments/ledger-06.md).

### Prior rollout leaf variants

K-rollout, one-turn bootstrap, policy-filtered rollout, and related variants
were null or negative. Reopen only with a new premise; see the
[leaf-evaluation synthesis](../research/combat-search/leaf-evaluation.md).

### Silver terminal/value audit

The bounded 20-source development audit following PR #260 is
**`TERMINAL_REWEIGHT_HEADROOM_INSUFFICIENT`**. It replayed 247 preserved
leaves with 32 paired SimpleAgent continuations each and added an exact raw
`SilverTerminalValueFeatures` decomposition of the current terminal utility.
The constrained compatible reweight worsened cross-fitted Teacher-A regret
from `1.51332` to `1.71113`; the untied diagnostic also failed to improve
regret (`1.61666`) after corrected nested source-grouped lambda selection.
Teacher B worsened for the compatible arm, and the corrected
source-clustered baseline-minus-candidate interval was `[-0.46891, 0.00000]`.
Against an optimistic zero-regret ceiling, the compatible arm recovered
`-13.07%` of the baseline gap; its development-only fit also left 48/75
ordinary-loss leaves at or above the minimum victory value. The preserved
corpus omits act, HP-band, and source-rollout-length metadata, so those
subgroup diagnostics remain unavailable rather than inferred.
This measures fixed rollout trajectories against the existing Silver objective;
it is not a claim that Teacher A/B are the true game objective.

The result is not a 100-source development qualification or an external
holdout: the committed #260 expansion/locked prefix rows do not include
replayable leaf wires, so they were not silently reused as terminal-feature
data. No fresh holdout, hard64 replay, live gameplay, production override, or
default promotion is authorized by this result. The current next target is
continuation trajectory/policy quality. See [ledger-06 §330](../../experiments/ledger-06.md)
and the [terminal/value audit packet](../../experiments/evidence/silver_terminal_value_audit_20260921/README.md).

### `v_win` terminal-pricing audit

The tracked compact win model is **`VWIN_W1_NEEDS_SMOOTHING`** under the
pre-registered W1 input-readiness thresholds. In 128 project-fair Silver
E2c-v2 seeds, 63.77% of RAW HP sweeps were monotone (95% seed-bootstrap CI
60.18–67.35%), below the 95% requirement; median longest flat run was 5 HP,
within the 10-HP limit. HP slope and held-potion value were positive with
intervals above zero in all three acts. This does not establish gameplay
quality or runtime suitability, and no lookup table or runtime change was
made.

The first collection process left 93 row-bearing seeds without final
aggregate health/quarantine counters; the remaining 35 seeds have complete
sidecar accounting. E2c emits rows only for runs passing `trainingRunValid`,
which rejects unresolved runs and simulator-health failures; each of the 93
represented seeds passed that predicate. The missing sidecar still prevents reconstruction of attempted/completed
counts or any unrepresented quarantines, and the interruption cause is unknown. Telemetry
`prior_model_loaded=0` measures the optional Silver learned root prior, which
was off by default, not the separate compact policy trees. Compact-policy load
status is **Unverified** from retained logs. A separate 600-row Python/native
parity gate passed exactly. Calibration was weakly powered and underpredicted
the cohort's observed run-win rate; zeroing the hidden-future fields passed the
rank-correlation threshold but can be out-of-distribution.

The pre-collection inventory found vrich and the named rest/path/card
counterfactual files absent from the checked local checkout/worktrees. The
ledger-referenced E2c GCP path is not mounted on this host; current remote
existence and historical dataset byte sizes are unverified. Under the
specified zero-hidden-future sensitivity, per-act HP slopes were
0.000675/0.002274/0.002355 probability per HP and held-potion equivalents
were 15.59/13.55/4.45 HP; those fair-regime values are OOD-prone. The packet
contains the artifact inventory and interval table.

W1-relevant interpretation: only a monotonically smoothed HP curve remains a
candidate `v_win` input, and only for non-act-boss victories. Silver's native
evaluator prices A0 act-boss wins after healing HP to max; the boss
`s_HP_span` median POST/RAW ratio is 0.7833, so the win-tree slope shifts about
22% across that boundary. Near realized HP, 14.5–21.6% of rows by room type
have a drop above 0.005 within ±20 HP, and the 95th-percentile largest drops
are 15–29 HP-equivalents. Gold is a possible secondary input, but its corrected
mean/median is only 0.23/0.10, 0.06/0.03, and 0.04/0.00 HP-equivalents per gold
across Acts 1–3. Held-potion mean/median values are 4.5/1.5, 4.3/1.7, and
4.8/0.6; max-HP-only values are 0.61/0.31, −0.06/0, and −0.48/0. Potion-type
and max-HP prices are not usable terminal prices. RAW-row AUC is 0.708 and
first-row-per-seed AUC is 0.638; with 128 seeds discrimination is weak, and
the model underpredicts cohort run-win rate.

The fair-regime rank-correlation gate does not validate price levels; act-level
potion HP-equivalents change by factors 2.31, 2.01, and 0.66 from recorded to
zeroed hidden fields. In Q4, the `curHp` coefficient interval excludes zero
(`−3.36e−4` per HP), about 17% of the mean `s_HP=0.00195`, so RAW-to-POST HP
pricing differs across states although the formal gate passed through low
`R²`.

For A4, the adjacent-floor, same-act drop proxy classified all 147 unmatched
full-belt rows with known drops as potion drops, with no classified unmatched
residual. RAW belt capacity was full in 15.3% of matched rows and 95.3% of
unmatched rows. One matched full-belt drop is explained by Potion Belt (`r159`)
increasing capacity before the potion choice; 216 unmatched rows remain
unclassified. The belt was full in 759/3,069 RAW rows (24.7%); among 301
full-belt rows with classifiable adjacent-floor status, 148 (49.2%) had a
potion drop. The run policy takes a potion only when a slot is available and
has no discard/swap path. This supports the conditional behavior in the current
full-run reward chain:
when capacity remains full through the potion decision, the dropped potion is
not claimed or swapped. E2c `captureE2cPost` returns while
gold, relic, or potion rewards are pending, so an unclaimed potion also blocks
POST capture. The proxy-confirmed minimum is 147/3,069 = 4.79% (4.8%) of RAW
fights. If all 199 unmatched full-belt rows with unknown proxy status also
represent forfeited drops, the code-path upper count is 346/3,069 = 11.27%
(11.3%). This is conditional, not an estimated rate; 17 unmatched
space-available rows show that other causes of missing POST exist, so the exact
cohort forfeiture rate remains unknown.

The current tracked 1,060-tree artifact contains counter-value splits on
multiple relic fields, contrary to the zero-split statement in historical
ledger §§109–110. The current enum maps r116 to Neow's Lament and r131 to
Thread and Needle. The historical run's exact model artifact is not
provenance-bound, so its result is not rewritten. See [ledger
§353](../../experiments/ledger-06.md) and the [complete evidence
packet](../../experiments/evidence/vwin_terminal_pricing_audit_20260924/README.md).

## Routing / evidence

- [Current baselines](current-baselines.md) — executable configuration and
  qualified headline measurements.
- [Research graph](../research/README.md) — maintained topic-level conclusions
  and open questions.
- [Experiment ledger](../../../EXPERIMENTS.md) — chronological experiment index
  and shard routing.
- [Evidence directory](../../experiments/evidence/) — retained frozen reports
  and machine-readable evidence.

Policy-quality claims still require paired common seeds and an explicitly
labelled fair or known-RNG regime. Missing provenance remains unknown, and an
artifact path alone does not prove that the artifact exists, loaded, or was
used.
