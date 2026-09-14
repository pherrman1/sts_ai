# Current research status

Last verified: 2026-09-14 for exact supported-v1 RNG continuation
and the stochastic signed-HP distribution;
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

## Current priority / active line

No research line is currently authorized as the active priority.

## Completed recent line

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
Original TEST support is 32,164/51,441 (62.526001%).

Next separately scoped work: native runtime adapter / OOC MCTS integration.
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
Nondeterministic active Lizard Tail fails closed. Models and support remain
frozen; this is an offline interface, with no production dispatch change.

The [frozen composed qualification protocol](../../experiments/evidence/composed_transition_2026-09-14.md)
uses the original source-grouped **reused engineering TEST**, exact HP marginal
over 11 maxHP classes, and 32 ancestral draws for potion/relic and complete states,
individual HP/potion/relic exposure gates at 0.1 nat and zero hard sampled-state
invalidity. Source-bootstrap CIs and full-state distribution/latency diagnostics
are descriptive. Historical component qualifications remain distinct from
composed and runtime qualification.

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
