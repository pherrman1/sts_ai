# Current research status

Last verified: 2026-09-17 for shared transition-encoder historical chronology,
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
Semantic confirmation section verified 2026-09-10 at producer `a6c2abb`;
other sections retain their prior verification and linked evidence.

## Purpose

This page routes current research work: what is active, what is plausibly
parked, what is closed to avoid repetition, and where the authoritative
evidence lives. Use [current-baselines.md](current-baselines.md) for executable
configurations and benchmark numbers, the [research graph](../research/README.md)
for topic synthesis, and the [experiment ledger](../../../EXPERIMENTS.md) for
chronology.

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
Nondeterministic active Lizard Tail fails closed. Models remain frozen; the
potion support predicate now excludes actual
generation routes (explicit Alchemize and Entropic Brew), allowing harmless
off-color cards. No production dispatch change is implied by this correction.

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

The Stage-A teacher-forced gate therefore stopped the planned 32-draw
ancestral stage. This rejects only the exact frozen DeepSets representation
plus current potion-decoder recipe. It does not justify fine-tuning DeepSets,
reinterpret the Attention result, claim intrinsic information absence, or
qualify potion sharing for runtime. No TEST, export, C++, gameplay, OOC MCTS
or default-promotion work occurred. See
[ledger-06 §289](../../experiments/ledger-06.md) and the
[DeepSets potion screen evidence](../../experiments/evidence/deepset_potion_screen_2026-09-16.md).

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
and the [S1 evidence](../../experiments/evidence/deepset_survival_lbfgs_2026-09-17.md).

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
secondary metrics. No eligible active Lizard Tail exists, so its stochastic
head is unqualified and the offline adapter fails closed on that support.
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

Exact real-observation filtering is semantically promising but remains opt-in;
persistent transfer is not in the executable, and single-child AI_RNG
rejuvenation stayed mixed/inconclusive with possible downside tail risk. A new
action/quality confirmation with an explicit downside rule is required before
promotion or broader rejuvenation work. See the
[belief-state synthesis](../research/combat-search/belief-state.md) and
[ledger-06](../../experiments/ledger-06.md) (search for "AI1 single-child
confirmation").

### Searcher3 particle count

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

Lower root exploration, Sequential Halving, progressive unpruning, hard
candidate pruning, learned ordering, and the tested grouped/rank-4 visit-PUCT
priors produced no stable promotable advantage; ordinary c=25 remains the
default. Do not restart these frozen treatments without an independent new
hypothesis. See [ledger-06 §186–§205](../../experiments/ledger-06.md) and the
[action-pruning evidence](../../experiments/evidence/silver_action_pruning_retention_2026-08-28.json).

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
