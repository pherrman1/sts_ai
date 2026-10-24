# Current research status

Last verified: 2026-10-24 for Act-4 combat strength and the Act-4 strong default (§681, §682, ADR-0060); 2026-10-24 for the A20 CTM HP-head fine-tune as the A20 default (§679, ADR-0059) and the CTM-calibration guard at A20 (§676); 2026-10-23 for synthetic infinity-oracle feasibility (§671); 2026-10-23 for the A20 CTM against real fights (§670) and its calibration as the A20 default (ADR-0058), the stage 1–2 leaf-compare replay (§663) and the M0 leaf calibration as the A20 default (ADR-0057) and the calibrated-leaf (M0) × SR_w1 blend A/B (§661) and the OOC value head's ranking-selected recipe on two more seeds (§649); 2026-10-22 for the OOC leaf's death price (§660); 2026-10-22 for the OOC value head as a leaf ranker (§641), its common-seed recapture (§644) and the retrain on those labels (§645); 2026-10-18 for the Act-4 CTM survival model A/B (§534) and A20 default (ADR-0048); 2026-10-17 for per-category chance widening (§518); 2026-10-17 for the AlphaZero-loop open requirements (potion discard output); 2026-10-17 for A0 Ritual artifact custody, corrected producer growth, coverage pilots and the Ritual refit (§511, §512, §505–§508); 2026-10-17 for the Arm C value fine-tune (§509); 2026-10-17 for the §494 student leaf A20 A/B (§504); 2026-10-17 for the outcome head as a sibling-leaf ranker (§502); 2026-10-17 for the development value-head comparison (§501); 2026-10-17 for development weighting ablation (§500); 2026-10-17 for one-shot observed-outcome holdout and early calibration (§499); 2026-10-17 for observed Heart-outcome value-head fitting (§498); 2026-10-16 for recovered Heart-outcome corpus import and class coverage (§497); 2026-10-16 for the NOT_SHOWN Arm C rollout-policy Heart pilot (§493) and software-fault recovery of the A20 Heart rollout-distillation pilot (§§491–492); 2026-10-14 for conditional leaf target stability (§471, #507); 2026-10-13 for bounded observational leaf capture (#507); 2026-10-13 for OOC MCTS `combo` at A20 (§457) and with the Lizard-capable A20 CTM (§458); 2026-10-12 for the A20 V4 at A0 and V4 margin sweep (§448), the public X2-B as rollout3 win model (§449), deep OOC MCTS with uniform prior and leaf policy (§441), the A20 short-branch label corpus (§445), the rollout3 fresh-seed confirmation (§433) and the CTM cost in rollout3 (§439); 2026-10-11 for Lizard Tail support in the default OOC MCTS CTM (§435), the #401 tree-input audit (§438) and the rollout3 CPU profile (§436) and exact native fallback batching (§437); 2026-10-11 for the rollout3 one-setting variants (§427–§430), independent branch futures and short-branch labels at A20 (§432), OOC MCTS on the A20 gold decisions (§425), rollout3 at 512 simulations (§424) and the Lizard-capable CTM inside rollout3 (§423); 2026-10-10 for the rollout3 OOC MCTS replication (§422); 2026-10-09 for the OOC MCTS root-selection × cpuct screen (§414) and the #418 retrained CTM live A/B (§412); 2026-10-08 for default ascending fallback REMOVE ordering; 2026-10-08 for fair native OOC decision quality (§395) and the blocked boss-relic selection-precision attempt (§398); 2026-10-03 for the #397 v_win information-boundary audit, card domain, history families and derived probabilities and the MLP follow-up (§§371, 373–376, 378); 2026-10-03 for learned Silver stopping (§370, v2 §372, v3 live §377); 2026-10-02 for the #400 Silver search-parameter screen (§369); 2026-10-01 for A3 offline v_win model tooling; 2026-09-28 for OOC MCTS equivalent-outcome merging (§367);
2026-09-27 for the active-Lizard fresh native Stage-C
qualification, valid DeepSets/Brew integration canary, Gate 2 provenance-bound
promotion, and default-stack plumbing; 2026-09-26 for the current-main
teacher-transfer gate, frozen Stage-C plan and checkpoint recovery, and the
closed OOC MCTS reroot-opportunity measurement;
2026-09-25 for the active Lizard frozen q/r qualification (§381), the OOC
contextual semantic-prior offline qualification,
the `v_win` terminal-pricing post-review additions,
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

## Act-4 combat strength (§681, §682; A20 default "Act 4 strong" since ADR-0060)

Replays of 128 Shield and Spear (S&S) and 128 Heart entry states from the §676 guard, 8 copies each:
- S&S: prior playouts at 10k lose 4.5 HP less than production's greedy playouts [+3.1, +5.9]; budget alone saves about
  1 HP, a raised node cap nothing.
- Heart: 40k with prior playouts and the tree-reuse cap at 262,144 wins +2.4 pp [+0.6, +4.2] over production 10k
  (63.2% vs 60.9%); at the 32,768 cap 40k gained +0.9 pp (the tree was dropped at ~30% of reroots).
- Decks: 15 of 128 Heart decks lose every fight in every cell; under production 67 of 128 are mixed (coin flips).
- Philipp adopted both stronger settings as the A20 default without a run-level A/B (ADR-0060; `STS_SILVER_ACT4_STRONG=0`
  restores the learned stop). A Heart fight now costs about 4 min CPU instead of about 1.

## Same-turn infinity oracle — synthetic feasibility (§671)

A standalone research utility detects bounded same-turn card cycles and certifies
only real simulator victories. The Dropkick, near miss, stall, phase-break and
budget fixtures pass; no production/default/model path changed. Existing archived
wire roots reconstruct, but the eight sampled information-set roots are outside
v0's concrete-state support. This establishes synthetic correctness, not natural
frequency or broad recall. [Design, limits and raw evidence](../../experiments/evidence/combat_infinity_oracle_20261023/REPORT.md).

Independent review's two corrections are applied: damaging recurrences are
PRODUCTIVE_CYCLE_CANDIDATE (not known infinites), and the oracle fails closed
outside Ironclad/red-color-domain roots with proven no-Shard provenance.
Qualify realistic recall and public-state handling before any natural-root
annotation; the current shuffle quotient also excludes exhausted-down decks.
No infinity reward, model head, AZ annotation or OOC integration follows from
this result.

## AlphaZero-style OOC loop: open requirements

Recorded 2026-10-17 at Philipp's request ("write down that this is something we'll need to fix in
the alpha zero loop"). The loop and its target form are fixed by
[ADR-0043](../../../decisions/0043-az-loop-gumbel-policy-target.md).

- **Potion discard has no policy output.** heart1 has no discard action, so neither has student C
  (`mapPriorLogits` puts reward/shop discards at heart1's lowest logit; heart1full nodes whose
  heart1 scoring fails stay uniform). The policy-target capture (`heartoutcomegen ... policy`,
  #601) records discard candidates with `heart1Map: "discard_potion"` and no heart1 token. The
  loop's network needs a discard output trained from those rows; rows where search chose or
  scored a discard must be kept, not dropped as unmappable. Until then,
  `STS_OOC_MCTS_POTION_KEEP_PRIOR=1` (research option, default off) is a hand-set stopgap prior
  from ADR-0039 keep values; see
  [out-of-combat.md](../architecture/out-of-combat.md) (potion pickup).

## AlphaZero-style OOC loop: generation schedule and search re-tuning (plan)

Agreed with Philipp 2026-10-21 13:39Z ("Yes write these things into the plan"). This applies from gen 3. The gen-2
paired A/B (`../../experiments/evidence/az_gen2_ab_20261021/PREREG.md`) runs as planned first: gen 1b showed no
online gain (§589), so one real gain should be seen before generations run without a per-generation test.

### Generations: every game is training data, a full test only every third generation
- **Why not gate each generation.** A realistic gain per generation is about 1 pp. A paired A20 A/B detects about
  4 pp at 1,024 seeds and 2.8 pp at 2,048 (80% power; from gen 1b's A/B, where 20.9% of seeds were discordant). A
  per-generation gate would mostly read NOT_SHOWN and still cost as much as the generation. AlphaZero itself dropped
  AlphaGo Zero's per-generation evaluation gate. AlphaGo Zero's gate had used 400 games at 55%.
- **Each generation's self-play is a paired block.** About 1,000–1,500 fresh seeds per generation. Each seed is
  played by the newest net and by the last tested net, with the same exploration settings in both arms
  (`STS_OOC_MCTS_ROOT_NOISE`, `STS_OOC_MCTS_PLAY_SAMPLE`, #741). Both arms' rows train the next generation; gen 2
  already trained on both arms of gen 1b's A/B. Seed folds stay as in gen 2: validation `seed % 8 == 7`, selection
  `== 6`, with both arms of a seed in the same fold.
- **Free signals per block.** Each block reports:
  - the paired Heart-kill difference;
  - floor reached, a lower-variance secondary: every run contributes, not only the ~21% discordant seeds.
  Within one block these only catch a collapse. A block whose newest arm is clearly worse (McNemar p < 0.05) stops
  the loop for a look.
- **Every third generation, a real test.** Pool the paired evidence of the blocks since the last tested net, or run
  one dedicated paired A/B of the newest net against the last tested net, pre-registered with its seed count. Its
  games are training data too.
- **Each new A/B needs a fresh seed block.** Once a seed's games are training data, that seed never judges a later
  net.
- **The offline gate stays per generation** and costs minutes:
  - selection-fold KL(π' ‖ net) below the previous net's;
  - value BCE below the constant guess;
  - native parity of the export.
- **Risk accepted.** Up to two generations of compute can go to a net that is no better, as happened with gen 1b.
  The per-block collapse check and the third-generation test bound that.

### Search settings: re-tune them on a schedule, separately from the net
The OOC search was tuned against student_sel and the X2-B leaf. Several of its parts depend on the net and can go
stale as the net changes.
- **Depends on the prior's shape** (student_sel today: median top prior 0.993, prior argmax executed 90.5%):
  - cpuct and prior temperature;
  - progressive widening (`WIDEN_K`, `WIDEN_ALPHA`);
  - root selection, visits vs Q (Q lost twice under student_sel, §414, §532).
- **Depends on the value scale:**
  - the learned OOC stop, which was trained on X2-B's scale. It must be retrained when the leaf or the root
    temperature changes; it refuses a temperature other than 1.
  - Q-based root selection, once a learned value replaces X2-B as the leaf.
  - The value-leaf A/B (gen-1b value head as the rollout3 end value) is the first test of that switch.
- **Depends mostly on the game:**
  - rollout depth (`LEAF_COMBATS`);
  - the Silver budgets of imagined fights.
  - Re-check these only when combat models change.
- **Drift monitors, read every generation from the capture rows:**
  - the fraction of searched roots where the search's move differs from the prior's argmax;
  - the early-stop rate and the mean sims at stop;
  - root visit entropy and Q spread;
  - prior top-1 against π' on the selection fold.
  The thresholds are set when the gen-3 block is frozen. A monitor that crosses its threshold queues the dependent
  settings for re-tuning.
- **Re-tuning happens at the third-generation checkpoint, with the net fixed.**
  1. **Offline screen first.** Take a few thousand stored root states and run one high-budget reference search per
     state (≥ 4× the deployed sims). Score each candidate setting by how close its root distribution and chosen move
     come to the reference, per unit of CPU. CPU only, no games.
  2. **Then online, at most one or two survivors**, as a third arm in the next paired block: same net, new setting.
     Its games stay training data.
  3. **Order by expected effect:** leaf evaluation, then cpuct/temperature, the stop rule, widening, and rollout depth.
- **Never test a search change and a net change in the same arm.** A search change also changes the training targets
  (π' and z). That is expected in an AlphaZero loop, but the A/B must still be able to attribute a gain.
- **Data-generation config vs deploy config.** Data generation wants good targets: exploration on, full budget on
  recorded roots. Only full-budget roots become policy rows today (8.4k of 8.5k per arm in gen 1b's A/B), so the
  1024 fast-root cap does not touch targets. Deployment wants strength per CPU: greedy, early stop, cap. Gates are
  read on the deploy config.
- **Search provenance belongs in every capture row.** The `.env` per run already records the full config, and rows
  carry `root.fullBudget` and `root.fastRootCap`. A config hash per row would let training mix or down-weight rows
  from older search configs. This is not built yet.

## Observed Heart-outcome supervision (§497)

The recovered native Claude delivery has passed independent import/seal review:
**TRAIN_VALIDATION_READY**. Exactly 49 accepted deliveries cover 1,800 planned
sources (41 original workers plus 8 replacement halves for lost 7/8/27/34).
TRAIN has 126 Heart wins/954 losses across 1,080 runs; VALIDATION has 47/313 across
360 runs. All 228,146 actual public state records in these 1,440 development runs
pass framing, schema, provenance, Arm C runtime and real-driver trace checks.
The unchanged TRAIN 20/20 and VALIDATION 5/5 class gates pass.

§499 has now opened all 49 accepted TEST archives exactly once, after independent
source/design and exact-freeze approval. All 360 TEST sources and 55,718 actual
observations pass deep receipt/trace/schema/model-use/activation-clock/support
checks: 43 Heart wins, 317 losses. The four superseded partial archives remain
opaque. All 53 archive bytes remain unchanged. The never-merge transport branch
`claude/heart-outcome-data` at `e3b649c` remains separate from main. §497/498
closed-TEST statements are preserved historical snapshots, not current custody.

The teacher remains fixed exact 10k Silver, Arm C prior+rollout and calibrated
A20 CTM/public X2-B-guided search; outcome labels are actual Heart results.

§498 fitted a 4,225-parameter 64 → 64 ReLU → 1 probability head on the frozen original
Arm C pooled representation. **VALIDATION_ONLY**, positive against the TRAIN
win-rate constant: BCE 0.350551 vs 0.388347, Brier 0.103368 vs 0.113704, AUROC 0.7153.
Two fixed 2,000-update initializations completed; validation selected init 1/step 300.
All 79 original tensors, validation pooled features and policy logits remain
bitwise equal. V1's unsupported deterministic CUDA sampler failed before any
optimizer update/score; v2 prospectively repaired CPU sampling and reused only
its exact bound feature cache. Independent source/design and result reviews PASS.

§499 exact verdict: **HOLDOUT_SIGNAL_CALIBRATION_NOT_SHOWN**. The frozen head
passes the preregistered source-balanced aggregate signal criterion on unseen
runs: BCE 0.327599 vs 0.365854, Brier 0.095877 vs 0.105185, AUROC 0.7311; both paired
source-bootstrap upper bounds for model-minus-constant are below 0. Visitation-
weighted diagnostics also improve. No model/normalization/candidate changed.

The three fixed source-uniform early landmarks all fail the marginal mean-bias
interval-within ±5 pp gate. At start, mean prediction 7.19% vs 11.94% observed Heart
outcomes; Act 1 floor≥8 gives 7.15% vs 12.01%; floor≥16 gives 6.11% vs 12.61%. Start
and floor 8 ranking is near chance (AUC 0.519/0.516); proper losses there are worse
than the frozen constant. No native leaf, gameplay/speed, conditional calibration,
RL or promotion is qualified. The current TEST is consumed and must not be used
to select/regrade a revised candidate.

§500 tested the weighting hypothesis on the existing TRAIN/VALIDATION cache:
two fixed initializations per arm, unchanged normalization/architecture/policy,
equal-source vs equal-state sampling, and common validation visitation-BCE
selection. **VALIDATION_WEIGHTING_NOT_SHOWN**. Equal-state weighting improves
validation visitation BCE 0.462407 → 0.453411 and Brier 0.143088 → 0.141157;
start bias improves −4.80 → −1.09 pp, and Act 1 floor≥8 −3.83 → −2.32 pp.
But floor≥16 bias worsens −1.03 → −4.18 pp, failing the fixed requirement that
all three absolute point biases improve. Only start passes the treatment's
descriptive marginal ±5 pp interval gate. Independent source/design and exact
result/custody reviews PASS. The retrained control uses the same common selection
rule as treatment; it is not §498's immutable selected head.

This is reused-validation development evidence, not new holdout qualification.
Inverse future-length weighting may contribute to some early mismatch, but its
removal does not uniformly fix it; representation, source count and checkpoint
selection remain alternatives. A separately specified loss giving explicit weight
to early reached states could be tested on development data; any changed candidate
needs fresh prospective holdout evidence. The consumed TEST is excluded from §500.
Stop before native integration; no RL, policy/trunk update or default change.

§501 compared fixed development arms on the same cache (pre-registered,
reused VALIDATION). Adding 37 public scalars/counts (HP, gold, keys, boss, act,
screen, deck/relic/potion counts) to the pooled Arm C features improves
validation visitation BCE 0.45341 → 0.42983 [−0.0414, −0.0062] and AUROC
0.669 → 0.725: **REPRESENTATION_LOSS_SIGNAL**. The block alone is not
distinguishable from the pooled features. The Arm C value input is a mean over
all tokens, which cannot carry set sizes directly; relic counters, act, battle
encounter and memory slots are not encoder inputs. Doubling act-1 state weight
makes early biases worse (NOT_SHOWN). Validation BCE falls from 135 to about 540
TRAIN sources; 540 → 1,080 is unresolved. Early-landmark ranking stays near
chance in every arm, and none of this qualifies a search leaf (§502 sibling
ranking is the binding gap).

§502 applied the §498 head to the §494 sibling leaves (777 TRAIN+VALIDATION groups,
64-rollout mean targets, no seeds or fits): concordance 0.527 vs X2-B 0.601 and one
rollout3 0.565; head − X2-B −0.074 [−0.097, −0.048]; near chance on act 1 (0.504) and
card rewards (0.506), ahead only on map screens. The four §501 development heads score
0.507–0.530, including pooled+public at 0.521. **HEAD_RANKS_WORSE_THAN_X2B**: no outcome
head is a leaf candidate; within-sibling discrimination, not marginal calibration, is the
gap. `one_combat heart1score` exports the pooled vector, and the native student plus head
reproduces §498 per-source validation means to 3.9e-9, so the public-record encoding
matches natively; parity with live search states beyond public records is still open.
`tools/outcome_head_sibling_check.py` scores further head JSON files the same way.

§509 fine-tuned the whole Arm C network (trunk and its never-trained value head) on the
outcomes, with a KL guard on the policy and a pairwise ranking loss on sibling 64-rollout
means, on §497 and then §497 + round-2 (§503) TRAIN. **NOT_SHOWN**: checkpoints selected by
VALIDATION BCE reach 0.418 (combined; 0.435 on §497 VALIDATION, below the frozen-trunk 0.453)
but rank round-2 VALIDATION siblings at 0.566–0.580 vs X2-B 0.633. Outcome BCE overfits after
about one pass while ranking keeps improving; the combined ranking-weight-2 fit reaches 0.648
at its last step with BCE worse than the constant (descriptive, VALIDATION-selected, no
bootstrap). Policy top-1 agreement stays 0.97–0.98. A ranking-selected candidate would need a
new frozen protocol and the sealed round-2 CONFIRM.

The original encoder ignores public battle/memory extras; counterfactual leaf
support remains unqualified. Recovery/one-way-export
and unverified cross-CPU byte parity limitations remain explicit. Prior §491–496
verdicts are unchanged.

[Import evidence](../../experiments/evidence/heart_outcome_import_20261016/REPORT.md),
[value-head evidence](../../experiments/evidence/heart_outcome_value_20261017/REPORT.md),
[one-shot holdout evidence](../../experiments/evidence/heart_outcome_holdout_20261017/REPORT.md),
[weighting evidence](../../experiments/evidence/heart_outcome_weighting_20261017/REPORT.md),
[sibling-ranking evidence](../../experiments/evidence/outcome_head_sibling_rank_20261017/REPORT.md),
[value fine-tune evidence](../../experiments/evidence/arm_c_value_finetune_20261017/REPORT.md).

## Arm C rollout-target distillation (§494)

The fresh native-session continuation **completed collection, fit and one-shot TEST: NOT_SHOWN**
(student vs X2-B on TEST: concordance 0.656 vs 0.630, regret 0.0171 vs 0.0194, 6.8x cheaper
than one rollout3, but the regret-improvement bootstrap [−0.0016, +0.0080] includes zero; no
promotion; ledger §494 "Fit and one-shot TEST"):
seeds `110164000..063` (40/8/16), 3600s/source and one six-hour deadline; qualification
canaries `110163994/995` passed and were independently reviewed. The Codex preflight
(blocked on export and capacity) is in the
[preflight evidence](../../experiments/evidence/arm_c_native_preflight_20261016/REPORT.md).
The old `110163xxx` cohort must not be resumed or pooled.
The initial Codex-only preflight exposed four CPU-equivalents and32GiB, with
unknown session lifetime and no available artifact-publication tool. That route
was blocked; the project's hosted threads subsequently supplied the qualified
capacity and project-share transport used by the completed campaign.
The [local review](../../experiments/evidence/arm_c_native_preflight_review_20261016/REPORT.md)
records preparation corrections and verifies the old local stop receipts.
The project's hosted cloud threads (4 vCPU/15 GiB each, mixed Intel/AMD CPUs) rebuild
the original producer byte-identically (`86a7569f…`), score the synthetic record
identically to the Codex AMD build, and passed a cross-container 300 MiB export round
trip through the project share; see the
[native campaign qualification](../../experiments/evidence/arm_c_native_campaign_20261016/QUALIFICATION.md).
`tools/heart_distill_native_worker.py` adds bundle, deadline, canary and fixed-shard
worker execution (rerun-once on lost attempts). After independent review and canary
review, **collection completed 64/64 sources** (all rc 0, attempt 1, one CPU model;
TRAIN 663 / VALIDATION 114 groups); raw corpus and sealed TEST are on the project
share; see the
[collection report](../../experiments/evidence/arm_c_native_campaign_20261016/REPORT.md).
`tools/heart_distill_native_fit.py` fit the unchanged six-fit grid once on Philipp's GPU and ran
TEST once on the collection CPU model behind a global latch.

A separately authorized continuation uses the exact frozen Arm C for both tree
priors and rollout decisions. The [prospective protocol](../../experiments/evidence/arm_c_rollout_distill_20261016/PROTOCOL.md)
keeps the six-fit public-record student grid and X2-B decision/cost gates, but
collects fresh source-disjoint targets under the new rollout policy. §491/492
V4 targets and §493 gameplay outcomes are excluded. Repeated-label child counters
verify actual C use; independently reviewed observational canaries precede the
64-source 40/8/16 split and one-shot TEST. The completed result above did not
qualify the student. Arm C is the chosen research teacher; §493's NOT_SHOWN verdict and production
defaults remain unchanged. No RL loop or automatic student deployment follows.
The completed corpus is permanently sealed against another TEST dispatch by
manifest/result identity. Retry recovery refuses unknown ownership and live
producer groups; workers require the reviewed CPU/canary pair before dispatch.
See [campaign guard operations](../operations/ooc-label-pipeline.md#arm-c-native-campaign-guards).
No further experiment or native integration is authorized by these guard repairs.

## A20 Shield and Spear search gap vs heart1's engine (§528, §530) — closed

**Closed (2026-10-18, Philipp).** On the 32 recorded A20 Shield-and-Spear entry states our Silver search lost about 7 HP
more per fight than heart1's engine at the §528 commit. Ruled out: monster code, evaluation, budget, rollout table,
tree reuse, two rollouts per leaf, three facing changes in the rollout, and draw-pile sampling (same information-set
code and chance constants as heart1; the fair root view audited correct). On current main the gap is −3.5 HP
[−8.0, +0.8], not shown; a full-information root loses 2.9 HP less (−2.9 [−5.6, +0.0]). Reopen only with a new
mechanism. What remains is the entry state (deck, lower max HP) from OOC play, which accounts for about half of the
Shield and Spear excess and the max-HP deficit (A20 loss audit F1,
`/mnt/project-files/audit-2026-10-17/a20-loss-analysis.md`).

## AZ loop status — gen 2 as prior NOT_SHOWN (§621, 2026-10-22); student_sel stays the OOC prior

Gen 2 (student_sel fine-tuned on all 2,688 runs of gen 0 and both gen-1b A/B arms, offline selection KL 0.0554 vs
student_sel 0.103) vs student_sel on 1,024 paired A20 seeds: Heart kills 21.5% vs 20.9% (+0.6 pp [−2.2, +3.3], p 0.73)
at 1.01× wall, below the +1.0 pp extension trigger. Both arms' rows join the gen-3 window. Runs averaged ~775 s (half of
gen 1b's) with the 2026-10-21 speed defaults. Offline value-head work (teacher distillation, search-value targets,
monotonicity) moved to the "Value head research" thread; the gen-3 exploration block is drafted in
`docs/experiments/evidence/az_gen3_explore_20261022/PLAN.md` (root noise + early-floor play sampling, #741 flags).
The exploration block ran 2026-10-22 (§640, 1,024 A20 runs, student_sel): 15.7% Heart kills vs 20.9% greedy, the
played move left the most-visited one at 22.7% of floor-0..6 roots, root noise doubled prior overrides (13.0% vs 6.6%).
Gen-3 training should keep its policy rows and down-weight its value rows.
Gen-3 prior training (§643, offline, 2026-10-22) on all 5,760 AZ runs beat both gen-2 nets in selection KL (0.0506 vs
0.0525 / 0.0547). But it changes student_sel's top choice at only ~3% of validation roots, and 70% of those are the same
moves gen 2 picks (gen 2 was NOT_SHOWN). The search already plays about half of those moves; at the rest its own q
prefers student_sel's move. No A/B recommended; prior-only generations wait for an evaluation (leaf) change
([result](../../experiments/evidence/az_gen3_train_20261022/RESULT.md)).

### Earlier: gen 1b as prior NOT_SHOWN (§589)

Gen 1b (student_sel fine-tuned on gen 0's Gumbel π' targets and Heart-kill value, §573) replaced student_sel as OOC
prior and rollout net inside gen 0's search stack. On 512 paired A20 seeds it killed the Heart 22.3% vs 23.2%
(−1.0 pp [−4.9, +3.0], McNemar p 0.70) at 1.04× wall: NOT_SHOWN. Both arms captured policy rows (≈34k searched roots
each), which with gen 0 form the gen-2 training window. Self-play exploration flags exist for gen-2 data runs
(`STS_OOC_MCTS_ROOT_NOISE`, `STS_OOC_MCTS_PLAY_SAMPLE`, #741, off by default).

## AZ gen-1b value head as the rollout3 end value (opt-in) — §615 A/B NOT_SHOWN, +3.1 pp lean

`STS_OOC_MCTS_LEAF_HEART1_VALUE=<weights.bin>` (default unset) ends each rollout3 leaf in sigmoid(value head) of the
given heart1-format weights instead of X2-B; rollouts and prior are unchanged. Offline on unseen §494/§503 data, gen 1b's
head ranks sibling leaves worse than X2-B (concordance 0.547 vs 0.633 on 11,493 round-2 groups; better only on map
parents) and predicts the run's Heart kill about as well (AUC 0.710 vs 0.694, CI includes 0; Act 1 weaker) (§577).
Online, in gen 0's search stack with the learned OOC stop off, 512 paired A20 seeds: Heart kills 24.0% vs 20.9%
(+3.1 pp [−1.0, +7.2], McNemar p 0.16) at 1.07× wall: NOT_SHOWN. No act-1 penalty (9.8% vs 9.4%), unlike §522. X2-B
stays the leaf value. The search overrode the prior less often with the value leaf (2,302 vs 3,043 roots), consistent
with its compressed Q scale ([result](../../experiments/evidence/az_gen1b_value_leaf_ab_20261020/RESULT.md),
[offline](../../experiments/evidence/az_gen1b_value_leaf_ab_20261020/OFFLINE.md)).

## OOC value head as a leaf ranker — the ranking-selected head is level with X2-B and its blend beats X2-B offline (§641, §644, §645, §649, 2026-10-23); no online test yet

Offline only, on round-2 sibling groups (§503; targets are 64-rollout3 means, so they end in X2-B). The metric is the
§577 sibling concordance on round-2 VALIDATION, where X2-B scores 0.633.
- **Earlier heads:** they ranked siblings at about 0.55. Fixing their slopes did not help (§622).
- **Blend flag:** `STS_OOC_MCTS_LEAF_HEART1_VALUE_WEIGHT=w` (§636, default off) blends w·logit(head) into X2-B's logit
  at rollout3 ends.
- **Sibling-ranking loss:** a RankNet loss over round-2 TRAIN sibling groups, added to the M0.3 recipe.
  - At weight 1 the head alone reaches 0.644, 0.645 and 0.618 over three seeds (mean 0.636): level with X2-B, not
    above it (the CI includes 0). The third seed was stopped early by the value-only selection.
  - Its blend is +0.032 to +0.040 over X2-B for every seed (seed 0: 0.673, +0.040 [+0.030, +0.049]).
  - Weights 0.1 and 0.3 reach 0.586 (just above the 0.585 bar) and 0.613.
  - Auxiliary outcome heads give no ranking gain.
  - The weight costs monotonicity (gold +50 is valued higher in only 65–84 % of cases over the seeds, vs 94 %; max
    HP +5 in 42–54 %, vs 67 %) and calibration (leaf BCE against the run's Heart kill 0.47–0.50, about a constant's
    0.475 or worse).
- **Label noise:** a perfect evaluator would reach about 0.84 on round 2 (#812's model). §644 corrects §641's 0.81,
  whose inflation counted rows with equal X2-B values as one public state; most of them differ publicly.
- **Common-seed recapture (§644, 320 new A20 sources):**
  - With `STS_OOC_SIBLING_COMMON_SEEDS` (§639, default off), 32 repeats carry as little stream noise in sibling
    differences as about 89 independent ones. Hidden state is small (2–4 % of a row's stream variance); the ceiling
    is 0.80–0.87.
  - On its VALIDATION, X2-B ranks siblings at 0.664. The SR_w1 head alone is below it (0.645, −0.019
    [−0.031, −0.008]). Its blend still gains +0.026 [+0.020, +0.032] (+0.018 to +0.026 over the three seeds).
  - The evidence README lists lessons for future label captures.
- **Retrain on the common-seed labels (§645):** both pre-registered arms FAIL.
  - The head alone reaches 0.640 on the recapture's labels and 0.649 with round 2's added, level with SR_w1. So
    cleaner labels did not lift it.
  - The value objective stops training while the holdout ranking still rises.
  - The ranking-selected epoch of the mixed run (exploratory, one seed) is level with X2-B alone (0.660). Its blend
    scores 0.703, +0.014 [+0.009, +0.019] over SR_w1's.
- **Ranking-selected recipe, seeds 1–2 (§649):** REPLICATED under a pre-registered rule.
  - The recipe trains SR_crn_r2 for 20 epochs and keeps the epoch with the best holdout ranking, with selection-fold
    BCE ≤ 0.570.
  - Both seeds' blends beat SR_w1's: +0.013 [+0.008, +0.019] and +0.014 [+0.009, +0.020]. Alone they score 0.663
    and 0.667, level with X2-B.
  - The epochs a value-based stop would have kept gain nothing, so the gain needs the longer training.
- **Status:** X2-B stays the leaf. The online candidate is now seed 2's epoch-20 blend (w 0.10, data branch
  `gen2/value-sr-crn/weights/SR_crn_r2_s2_ep20/student.bin`) instead of SR_w1's. All of this is offline, and in §504
  and §615 offline concordance and online play disagreed in direction. An online test needs Philipp's go
  ([evidence](../../experiments/evidence/value_sibling_rank_20261022/README.md),
  [recapture](../../experiments/evidence/ooc_sibling_crn_capture_20261022/README.md),
  [retrain](../../experiments/evidence/value_sr_crn_20261022/README.md),
  [seeds](../../experiments/evidence/value_sr_crn_seeds_20261022/README.md)).

## OOC leaf level: the search over-prices a death (stage 0, §660, 2026-10-22); the calibrated leaf wins the A/B (§661) and is the A20 default (ADR-0057, 2026-10-23); the leaf-compare metric does not qualify (§663)

A rollout3 leaf scores a death 0, a Heart kill 1 and a surviving end X2-B, whose level is far above the Heart rate
(decision roots: 0.75 vs 0.22 in act 1, 0.91 vs 0.38 in act 3). Calibrated against the run's Heart kill
(σ(a_act + b · logit X2-B), b ≈ 1.05; the held-out check passes), the search over-prices a death 3.3× in act 1, 4.0×
in act 2 and 7.7× in act 3. Offline on §644's capture:
- A per-act calibrated leaf (M0, `STS_OOC_MCTS_LEAF_CALIBRATION`; the A20 default since ADR-0057) would change about
  7% of root picks, three quarters of them toward the sibling that dies more often in rollouts.
- Predicted Heart kills per run: +1.8 pp if the calibration holds between siblings, −6.1 pp if today's price is right.
- The shortcut M0′ (survivors on X2-B's scale, a death worth a per-act constant) inverts at the act 3 → 4 border.

**2×2 A/B** (M0 × the SR_w1 blend at w 0.1, learned OOC stop on, 1,024 paired seeds, §661):
- Heart kills: A 23.2%, M 24.6%, S 21.9%, MS 24.8%.
- **M0 main effect +2.15 pp [+0.10, +4.25], IMPROVED**, close to stage 0's +1.8 pp. The blend main effect is −0.6 pp
  (NOT_SHOWN).
- Under M0, deaths move from act 3 to acts 1–2 and Act 4 is won more often (60.7% vs 57.1% of arrivals).
- M0 also leans the search on the prior: fewer picks off the prior's argmax, and the learned OOC stop fires earlier.
  The A/B cannot separate that from the death price.
- Wall: M 0.95×, MS 1.04× of A.
- The learned OOC stop stays valid on M0's scale (offline check: at p ≥ 0.99, 99.8% same action as the full search
  vs 99.6% under X2-B; no fast-root stop changed a pick). It fires more often because M0's searches settle earlier.
- **Status: M0 is the A20 default** for the rollout3 X2-B leaf, offline and in the live advisor (ADR-0057;
  `STS_OOC_MCTS_LEAF_CALIBRATION=0` restores raw X2-B). Philipp chose it on 2026-10-23 without the fresh-seed
  confirmation, which would have come out IMPROVED only about one time in three at a true +1.4 pp. Later value
  candidates are tested against M0
  ([stage 0](../../experiments/evidence/value_death_price_20261023/README.md),
  [A/B result](../../experiments/evidence/value_level_ab_20261023/RESULT.md),
  [stop check](../../experiments/evidence/value_m0_stop_check_20261023/README.md)).

**Leaf-compare replay** (stages 1–2, 256 games of arm A, seven side searches per searched root, §663):
- **NOT QUALIFIED.** No rollout referee matches real play. Full-game rollouts (R_full) kill the Heart from act-1 roots
  at 0.08 against a real 0.23. Stopping them at the act's end and taking M0's value there (R_act) misses by 0.05–0.07
  in acts 1–2 and by 0.21 in acts 3–4.
- Exploratory: both referees predict M0's gain close to the A/B's M − A (+0.9 and +1.4 pp against +1.4).
- A leaf changes the played pick at 4–6% of searched roots, about as often as re-seeding the search (4.7%).
- No leaf changes an act-4 pick, because no act-4 rollout reaches a leaf. Act-4 OOC decisions depend only on the
  rollouts, and their level there is 0.49 against a real 0.70.
- Stage-4 candidates are therefore gated on the guardrails and on paired A/Bs, not on this metric
  ([result](../../experiments/evidence/value_leaf_compare_20261023/RESULT.md)).

## Heart leaf (opt-in) — §515 VALIDATION and CONFIRM gates FAIL

`STS_OOC_MCTS_LEAF_HEART_MODEL=<manifest>` (default off, issue #605) values rollout3 leaf ends
with a residual on the public X2-B margin, trained by fitted TD on rollout3 tails from §503 MAP
root snapshots and anchored on real Heart outcomes; it sees Act 4 boss distance, keys and key
reachability, Ritual Dagger damage and Searing Blow level. Key value comes only from the Heart
labels (no hand-set bonus, Philipp 2026-10-17). `models/candidates/heart_leaf_td1` beats Platt
X2-B on §503 VALIDATION BCE (0.3065 vs 0.3133) and AUC (0.724 vs 0.699) but over-predicts Act 3
(0.240 vs 0.202) and fails the pre-registered gate. heart1's value head ranks states within an
act better than both but has almost no level change between acts. The retrained
`heart_leaf_td2` adds a tree distillation of that critic as an input and an Act-4 offset. On the
§503 CONFIRM set (640 runs) it beats Platt X2-B on BCE (0.3345 vs 0.3479) and AUC (0.750 vs
0.726) and calibrates acts 2-4, but under-predicts Act 1 (0.093 vs 0.130) and fails the gate;
CONFIRM is spent. Philipp asked for a paired A20 A/B of td2 against the X2-B leaf anyway; §522 (512 pairs) is NOT_SHOWN
(reached Act 4 124 vs 137, Heart kills 42 vs 46) with more Act-1 deaths (114 vs 69).
td1/td2 also read the hidden encounter queue (`nextEliteId`, `nextFight0..2`), real in the §503
roots but sampled in play; `heart_leaf_td3` (feature schema v4) zeroes those columns and matches
td2 on VALIDATION (BCE 0.3034, AUC 0.731).
See the [result](../../experiments/evidence/heart_leaf_td_20261017/RESULT.md).

## Act-4 CTM survival model (A20 default, ADR-0048) — §527 offline FAIL, §534 A20 A/B NOT_SHOWN

`models/candidates/ctm_act4_survival_trees.txt` replaces the CTM survival probability of
Shield and Spear and the Heart. Offline it fixes the Heart (TEST death 0.70 predicted vs 0.68 observed, CTM 0.17) but
not Shield and Spear (§527). In the A20 student_sel stack at 512 simulations (512 paired seeds) it won 75 Hearts
against 82 for the control, NOT_SHOWN (McNemar p = 0.09, 3 vs 10 discordant). Both arms played identically through
Act 2. Philipp made it the A20 default afterwards (ADR-0048; `STS_CTM_ACT4_SURVIVAL_MODEL=0` restores).

## A20 CTM against today's real fights (§670, offline, 2026-10-23) — pessimistic at bosses; a per-fight calibration, A20 default since ADR-0058, does not lose at 512 seeds (§676)

Over the 97,561 real fights of the stage-3 A/B (§661), the deployed A20 CTM stack (Lizard correction, §470 boss shift,
Act-4 model) predicts too many deaths at most bosses and too much HP loss in Acts 2–4. On the odd seeds:
- The Heart: 0.486 predicted deaths against 0.370 observed. Act-1 bosses 0.093 against 0.050; Shield and Spear 0.080
  against 0.051.
- Act-3 bosses: 0.189 against 0.148, and the mean HP after a won fight 19 HP too low.
- It under-predicts deaths at the Awakened One, Reptomancer, Gremlin Leader, Slavers and event fights.

The table `models/candidates/ctm_calibration_pathb_a20_v1.json` (`STS_CTM_CALIBRATION`) adds a per-fight death-logit shift and HP-loss scale (34 groups: the encounter for elites and bosses, else
act and room). Out of sample it predicts better in both seed folds (odd seeds: death log loss 0.0731 → 0.0685,
won-fight HP error 8.5 → 7.7; even seeds 0.0717 → 0.0684, 8.5 → 7.7). On the 256 held-out stage 1–2 games it goes
0.0733 → 0.0698 and 8.2 → 7.6; the Heart 0.458 → 0.358 against 0.337 observed. Below 20 HP it makes Act-3 fights look
safer than they are (0.43 predicted against 0.47 observed; the CTM 0.49), and an HP term in the shift did not help.
A 10-seed smoke leaned against it (the control got further on all four seeds whose games ended differently), which
is no evidence at that size. Philipp judged the CTM by its precision, not by winrate, and made the table the A20
default (ADR-0058, 2026-10-23; `STS_CTM_CALIBRATION=0` restores the raw CTM, which older comparisons need).

The pre-registered 512-seed paired A20 guard against `=0` (§676, 2026-10-24; only WORSE would have turned the default
off) found no loss: Heart kills 26.2% against 24.0%, +2.15 pp [−1.17, +5.66], NOT_SHOWN, so the default stays. With
the calibration the search reached Act 4 more often (+3.71 pp [+0.20, +7.23], descriptive) and fought more Act-3
elites, at the same HP entering fights; kills per Act-4 arrival were the same (59.0% against 59.1%). A playing-strength
gain is still not shown. On the guard's own 24,186 real fights (new seeds, today's engine with fixes #831, #833, #835
and #836) the table again predicted better: death log loss 0.0711 → 0.0660, won-fight HP error 8.65 → 7.75, the
Heart 0.512 → 0.403 against 0.378 observed. Act-1 bosses improved there too; Act-2 elites, Slime Boss, Gremlin Nob
and Slavers got slightly worse
([evidence](../../experiments/evidence/ctm_calibration_20261023/README.md),
[PREREG](../../experiments/evidence/ctm_calibration_20261023/PREREG.md),
[smoke](../../experiments/evidence/ctm_calibration_20261023/SMOKE.md),
[guard result](../../experiments/evidence/ctm_calibration_20261023/RESULT.md)).

## A20 CTM HP-head fine-tune (§672, offline; A20 default since ADR-0059, §679) — the same deaths, closer HP after won fights

§672 fine-tuned only the HP head of the A20 fast CTM on the stage-3 A/B's 97,561 real fights and refitted the
calibration table on its scores (`models/candidates/ctm_finetune_hp_pathb_a20_v1.native` and
`ctm_calibration_pathb_a20_ft_hp_v1.json`). Its deaths are the old net's byte for byte, and both tables shift deaths
alike, so only the predicted HP after a won fight changes. Survival fine-tunes did not beat the §670 table.
Against ADR-0058's arrangement (old net + its table):
- on the 256 held-out stage 1–2 games, won-fight HP error 7.60 → 7.45 (−0.16 [−0.23, −0.09]);
- on the guard's 24,186 fresh fights (§676, played after both were frozen), 7.75 → 7.59 (−0.16 [−0.20, −0.12]), with
  the same death log loss (0.0660). The gain sits at bosses (Act-3 bosses 16.50 → 15.40, the Awakened One 19.19 →
  17.24, Act-2 bosses 17.07 → 16.57) and Shield and Spear (18.21 → 17.29). The Heart got slightly worse (18.45 →
  18.58), which the search cannot use: a won Heart ends the run.

Philipp judged the CTM by precision and made the fine-tune with its own table the A20 default (ADR-0059, 2026-10-24;
`STS_CTM_A20_HP_FINETUNE=0` restores the §470 artifact with the ADR-0058 table, which older comparisons need).
Playing strength is not measured
([fine-tune](../../experiments/evidence/ctm_finetune_20261023/README.md),
[default](../../experiments/evidence/ctm_finetune_default_20261024/README.md)).

## §494 student as a native OOC MCTS leaf (opt-in) — loses to rollout3 at A20 (§504)

`STS_OOC_MCTS_LEAF_STUDENT=<weights.bin>` (default off) scores non-terminal OOC
MCTS leaves with the §494 rollout-target student instead of rollout3
(`apps/one_combat/rollout_student.{h,cpp}`; weights exported from the §494
`selected.pt` by `tools/rollout_student_export.py`, not vendored). Native scores
match a float64 reference within 2.2e-7 on all 21,291 §494 TRAIN+VALIDATION leaves;
a one-seed A20 act-1 smoke used about 3.4x less MCTS CPU per decision with no
fallbacks. The pre-registered A20 paired A/B (§504, 128 seeds, Arm C environment) found
it **WORSE** than rollout3 at equal simulations (reached Act 4 31 vs 45, −10.9 pp
[−20.3, −1.6]) and **NOT_SHOWN** at 1536 simulations (32 vs 45), with act-1 deaths about
doubling; see the [result](../../experiments/evidence/rollout_student_leaf_20261017/RESULT.md).
It stays research-only: the §494 student does not replace rollout3 in this setup.

## Arm C inside A20 Heart rollouts (§493)

The completed 32-pair pilot is **NOT_SHOWN**: Arm C rollouts killed the Heart on
2/32 sources versus 1/32 for the existing chain, +3.125 pp with paired bootstrap
95% CI [0, +9.375] pp and exact McNemar p=1.0. Only one pair differs on the primary
outcome; improvement and noninferiority are unqualified. Mean floor 33.281 vs
30.875 is descriptive, not an alternative promotion endpoint.

Both arms used Arm C tree priors, exact-10k Silver real combat, three CTM leaf
combats and native X2-B. Their shared 0.25 thread-CPU-second OOC decision allowance
passed resource gates: every nontrivial completed search stopped on budget, no
ceiling hits or aborts; median simulations 28 with C vs 161 with the chain.
Actual median CPU was 254.74 vs 251.50ms. Total CPU/run was 40.550 vs 37.002s,
including different trajectory/decision counts, not equal-total-CPU matching.
All 511,121 C rollout steps and both arms' model-prior builds scored with no
fallback. No training, extension, default change or promotion follows.

The explicit `LEAF_POLICY=heart1` feature remains optional; legacy `prior` still
uses V4. A stopped initial canary exposed a no-search boundary classification
bug in the validator; the preserved failed attempt was excluded, and a narrow
reviewed repair preceded fresh accepted canaries and the untouched cohort.
[Evidence](../../experiments/evidence/arm_c_rollout_20261016/README.md),
[protocol/amendment](../../experiments/evidence/arm_c_rollout_20261016/PROTOCOL.md).
The evidence applies to greedy C rollouts at this allowance; sampling and larger
allowances remain open questions.

## A20 Heart rollout distillation (§§491–492)

The selected public heart1-record student is **NOT_SHOWN** after the user-authorized
software-fault recovery in §492. The same already-opened 16-source holdout yielded
7,716/7,716 valid rows and 259 groups. The frozen count MLP blended 50/50 with X2-B
cuts rollout-target MSE by 54.67% (0.019559 vs 0.043148), but concordance gains just
0.002225 (required 0.02), regret is 0.025438 vs X2-B 0.023040, and regret-improvement
95% CI [-0.007125, +0.002174] spans zero. Complete measured Python speedup is 1.493×
(required 4×); feature construction dominates tensor inference. All candidate
conditions fail. Lower prediction error does not establish better choices.

The original §491 evaluation crashed after its opening latch because per-source
metrics shadowed the token tensor. Its `INVALID_TEST_EXECUTION` bundle remains
unchanged. The user explicitly authorized one isolated retry with that bug fixed;
independent review approved unchanged weights, vocabulary, data, selection and
gates. §492 reran only the normal corrected evaluation, with separate producer
and recovery-analysis provenance; no collection, fitting or tuning was repeated.
This is recovery of the same opened holdout, not fresh independent replication.
[Recovery evidence](../../experiments/evidence/heart_rollout_distill_recovery_20261016/README.md)
and [amendment](../../experiments/evidence/heart_rollout_distill_recovery_20261016/PROTOCOL.md).

The A20 Heart/key-collection producer uses distilled heart1 Arm C as **tree prior
only**, with V4 rollout chain fixed. The original 64 sources and six fits completed
locally. Earlier interrupted V4-prior data remains excluded; Opus §490 is a frozen
historical reference with unavailable raw cloud corpus. Labels are rollout3
surrogates ending in X2-B, not true Heart-win probabilities. Public/native parity,
Heart-win prediction, native speed and gameplay improvement remain unqualified.
No port, gameplay A/B, default promotion or student-driven policy iteration follows
from this failed candidate gate.

## Fair native OOC decision quality (§395)

The controlled non-MCTS research reference uses public-eight-future native
fallback scoring and the optional-Ruby-Recall eligibility correction with keys
off. Both remain opt-in. At base `a4b3df35`, `STS_FAIR=1` alone does not remove
actual unrevealed encounter identities from native floor/win fallback inputs;
historical reference scores cannot qualify this changed profile. The wrapper
passes hidden-state invariance and source/RNG preservation checks, within its
documented conditional-sampler scope.

Fresh development rejected broad REST-gate removal, the shop feature correction
as a strength candidate, and their combination. Narrow full-health REST
exclusion and shop-gate removal each gained one win in 128 pairs. Reversing
fallback `REMOVE` acquisition-weight ordering gained two wins in its separate
128-pair cohort and was selected by the frozen exploratory rule. Its one
fixed 512-pair confirmation is **CONFIRMED_IMPROVEMENT**: 395/512 versus
381/512, 27 candidate-only and 13 control-only wins, +2.734375 pp with paired
95% interval [+0.390625, +5.2734375]. The lower bound and predeclared 2 pp floor
both pass. This applies to immutable `d35b42b1` and its corrected-fair profile;
development was not pooled, and no live-game or merged-source qualification
follows automatically. All pairs and runtime gates passed; search safety-limit
endpoints remain documented diagnostics.
Card win-head ranking with preserved floor take/skip lost its discovery screen.
The original campaign changed no production defaults. After reviewing the
confirmation, the user authorized ascending fallback REMOVE ordering as the
default in a separate implementation change. `STS_OOC_REMOVE_LOW_OBTAIN_WEIGHT=0`
retains the legacy ordering for rollback and reproduction. This promotion
does not extend the frozen result to other profiles or qualify live-game parity.

The completed 32-source GEN2 experiment did not establish conditional selection
gain: rollout-selected −1.171875 pp, source-cluster 95% [−5.46875, +3.125]. The
large gap between selection and independent evaluation supports concern about
small-K selection optimism. Queue-blind historical P0/F2 model results do not
identify a useful replacement. Their retained latent counters and older
privileged-teacher labels remain scope limits; this conditional diagnostic does
not qualify the current fair runtime. Calibration bias does not by itself
explain ranking quality.
Exact profiles, alternatives, decision audits and limitations are in the
[original research packet](../../experiments/evidence/ironclad_a0_overnight_20261008/README.md).

### Boss-relic selection precision (§398) — execution blocked

The separately authorized K4-versus-K16 follow-on attempted all 32 fresh
sources (`610084200..610084231`) using the unchanged `3ed91ab3` producer,
at most one boss-relic state per source and common futures. Selection was
allocated k0–3 versus k0–15, followed by shared independent evaluation k16–31.
Thirty-one sources completed; source `610084217` exceeded its fixed
1,800-second cap. The all-source contract is `INVALID` and the primary is
**`EXECUTION_BLOCKED`**. Neither choices nor efficacy evaluation were produced;
there is no quality verdict and no completed-31 substitute analysis.

Collection used six one-thread workers for 100.414696 minutes elapsed.
Observed emitted CPU was 9.184214 core-hours, censored by unavailable timeout
source and unfinished continuation costs. The timeout's saved branches averaged
17.4739 CPU seconds, 2.43 times the planning average. Recorded profiles support
a compute-cost tail without a recorded fatal fault; interrupted work remains
uncertified. All allocated attempts and partial files were preserved, with no
retry, replacement, cap change or remaining game worker.

Selection precision remains unresolved. The earlier RemoveLow confirmation
is unchanged, and no new training, deployment or automatic continuation is
qualified. Future efficacy use requires a new authorized protocol that
discloses this failed allocation and addresses per-source runtime tails.
See [ledger §398](../../experiments/ledger-06.md) and the
[follow-on evidence and reviews](../../experiments/evidence/ironclad_a0_k_precision_20261008/README.md).

## Live OOC MCTS on vs off (§384) — MCTS loses

**Measured (2026-10-06, §384).** This is a paired 128-seed pilot
(`48000000..48000127`, §377 live profile, act-3 stop). Live OOC MCTS ran at
2048 sims with the default `screengbm` leaf, against the same flat exact-10k
Silver pipeline with MCTS off.

MCTS lost **−21.9 pp wins, 95% [−32.0, −11.7]** (56.3% vs 78.1%). Floor was
−1.46 [−3.16, +0.27], at 2.0x the time. Against learned stopping without MCTS,
the gap was −17.2 pp [−28.9, −4.7] at 4.7x the time. Flat exact-10k versus
learned stopping was +4.7 pp [−4.7, +14.1], so the exact-10k precondition
costs time, not detectable strength.

MCTS losses concentrate on boss floors, and MCTS wins end with less HP. The
CTM's training on vendored Silver from before ADR-0021 is one candidate cause
(**Open question**, #418). OOC MCTS stays off, and #399 and #415 have no
qualified teacher.
[Evidence](../../experiments/evidence/ooc_mcts_vs_off_pilot_20261006/README.md).

**#418 retrained CTM (2026-10-09, §412).** The CTM retrained on the Path B
learned-stop corpus (pathb-r2, escape capability only) passed the offline A/B
(mostly a better fit to the current teacher's boss HP). In live OOC MCTS on
128 new pairs it was `NO_DIFFERENCE_DETECTED` against the production CTM,
+5.5 pp [−2.3, +13.3], non-inferior at 10 pp. Neither MCTS arm beat MCTS off
(cand −1.6 pp [−10.9, +7.8], production −7.0 pp [−16.4, +2.3]), so the
refreshed CTM does not establish a reason to turn OOC MCTS on (**Inference**).
Philipp chose to swap the production CTM pins to pathb-r2; OOC MCTS stays off.
[Evidence](../../experiments/evidence/ctm_live_ab_418_20261009/README.md).

The A0 Writhing Mass/Ritual Dagger intersection remains unqualified in both
selected pathb-r2 artifacts. The standard artifact's downstream tensors match
`95e07d97c34a2b220a2ed5d570b2680b190f647c5a5cca945c52a2109e8cd0f0`,
the checkpoint bound by the failed exposure report in §412. The fast artifact's
downstream tensors instead match the later S19 checkpoint
`06709aed52532085e99a47c5c7f07174a915038227232954cc16d60fa35809d4`.
Its conditional validation gate does not establish intersection exposure
qualification; the standard checkpoint's failure is not a measured failure
of that different fast checkpoint. The earlier sparse Ritual head was only
a warm start for these refits. Extending that warm start's fit cannot be
interpreted as repairing either deployed head. Capability guards stay in
place pending stack-specific composition and native qualification.
[Artifact custody](../../experiments/evidence/ctm_ritual_validation_20261017/custody.json).
A frozen 32-draw VALIDATION diagnostic (§511) scores 143 rows from 68 sources
with near-zero exposure gap, but every observed Dagger increment is zero.
A TRAIN/VALIDATION census has only three positive increments in 1,238 rows.
This does not qualify growth, standard-Brew coverage or active-Tail
composition. Deterministic fixtures subsequently reproduced lost final-kill
Ritual growth and false half-dead growth in the producer. The fixed transfer,
eligibility and shared native kill budget match vanilla semantics. Old rows
lack the action history needed to repair them, and later pre-state decks also
reflect the old growth. Corrected-source data is required before renewing
affected Ritual growth qualification; the existing artifacts are preserved.
[Diagnostic evidence](../../experiments/evidence/ctm_ritual_validation_20261017/REPORT.md).
The reviewed corrected-source canary (§512) completes one reused TRAIN source
in 16.344 s with 24 valid RAW rows and zero quarantine. It observes two +3
increments, including Writhing 18→21. This establishes positive producer
behavior only. Key collection was ON by the current compiled default, so it
is not historical-teacher reproduction; future collection must freeze that
objective explicitly. Controlled upgraded/multicopy and Brew/Smoke coverage
and a reviewed Ritual-only fit/export adapter remain prerequisites. Neither
the old all-zero cohort nor this one source qualifies changed weights.
[Corrected canary evidence](../../experiments/evidence/ritual_corrected_canary_20261017/REPORT.md).
Follow-up (2026-10-17):
- Controlled coverage pilots §505/§506 reached coverage in every non-Smoke cell. With a Smoke Bomb held, Silver
  escapes in about 87% of fights.
- The Ritual-only refit (§507) cut Writhing NLL from 0.514 to 0.350. The non-Writhing margin was waived by owner
  override.
- A 64-seed A/B (§508) was identical on every pair, because no run held a Dagger.
- The refit pair is now the A0 default (ADR-0044).
[Refit evidence](../../experiments/evidence/ctm_ritual_refit_20261017/REPORT.md).

**Root selection × cpuct (2026-10-09, §414).** On 128 new paired seeds with the
pathb-r2 stack, picking the OOC MCTS root option by mean Q instead of visits
loses 30–44 pp at every cpuct (cpuct 1.5: 41.4% vs 78.9%). With visits, cpuct
0.5 and 1.0 tie 1.5, and 3.0 is worse (−10.9 pp). The Q arms skip about a third
of card rewards, so the screen leaf's own preferences are worse than the V4
prior's (**Inference**). Root selection stays `visits`, cpuct 1.5.
[Evidence](../../experiments/evidence/ooc_mcts_q_select_screen_20261009/PREREG.md).

## Screen-aware OOC leaf value (#379) — offline preparation

At current-main baseline `a59d7e47`, the frozen 1,024-source DECISION corpus
passes its narrow custody audit; DECISION TEST remains numerically unopened.
Exact current S0 uses the actual adapter continuation with explicit X2-B.
Both historical producer versions pass seven-file byte-identical reconstruction
canaries. A 1,024-state VALIDATION S0 pilot passes; reconstruction dominates cost.

The provisional direct-value mask is `boss_relic`, `rest`, `shop`, `treasure`.
Events, selectors and rewards retain fallback because the frozen public screen
schema omits some visible offers or known suspended parent effects. This is a
representation decision, not a predictive-quality verdict. S1/S2 tooling uses
one fixed small typed encoder and changes only per-screen versus shared heads.
All three fixed initializations for each arm have completed, without selection.
The first full VALIDATION recovery stopped after 14 exact replays: 13 S0 passes
and one strict Golden Idol public-state mismatch. Historical producers infer
that event's trap phase from relic possession; current main uses `info.phase`.
The original snapshots are preserved. A version-bound offline import adaptation
must pass review and regression before a new protocol reuses qualified replays.
No model is qualified or integrated, and no default or gameplay claim changes.
See [ledger §382](../../experiments/ledger-06.md) and the
[evidence packet](../../experiments/evidence/screen_leaf_379_preflight_20261005/README.md).

## OOC MCTS tree reuse / rerooting (#339) — closed after measurement

**Closed (2026-09-26, §361).** On the representative 2-seed OOC 2048 workload:
- Full-state (RNG-counter) identity never matches the previous search's tree.
- Public-state identity matches 58% of searched decisions, but only within
  noncombat stretches.
- Rerooting to the single matched particle keeps a median of 30 visits, 0.90%
  of searched simulations. Direct selected-branch rerooting is not implemented.

Merging publicly identical particles (upper bound 26.6%) would be a separate,
semantics-changing proposal; it is an open question.
[Evidence](../../experiments/evidence/ooc_reroot_opportunity_2026-09-26/README.md).

## OOC MCTS prior guidance at A20 (§532, §557) — max-Q root pick WORSE, temperature 3 not shown in full runs

With the student_sel prior the search spends a median 97.8% of root visits on the prior's top move, and the executed
move is the prior argmax in ~90% of roots. In an Act-1 A20 screen (64 paired seeds), `STS_OOC_MCTS_ROOT_SELECTION=q`
lost 20 HP and 25 more Act-1 runs, and q with prior temperature 3 still lost 9 HP, so the leaf's Q ranks options worse
than the prior. `STS_OOC_MCTS_TEMPERATURE=3` (visit pick) was +3.1 HP [−2.1, +8.3] with ~13% more OOC CPU: a screen
pass. The full-run A20 confirmation (§557, 256 paired seeds) gave 37 vs 42 wins, −2.0 pp [−6.6, +2.7]:
NOT_SHOWN. Defaults unchanged (temperature 1, visit pick).

## OOC MCTS equivalent-outcome merging (#384) — opt-in, inconclusive

**Measured (2026-09-28, §367).** Pooling search-equivalent sampled particles
(`STS_OOC_MCTS_MERGE_OUTCOMES=1`) removes the 49-55% duplicate decision nodes
and deepens trees from 4 to 11-15 levels at the same budget. A paired
128-seed cohort (`38410000..38410127`) found no detectable play-strength
change: `floor + 10*won` -0.25, 95% [-2.46, +1.96]; wins 86 vs 83; about 13%
slower. Default stays off. Open question: whether it matters once #379
replaces the playout leaf.
[Evidence](../../experiments/evidence/ooc_merge_outcomes_2026-09-28/README.md).

## OOC MCTS contextual deck-prior offline qualification

The newly trained 3,200-parameter contextual deck block is
**`CONTEXTUAL_SEMANTIC_PRIOR_PASS`** against PR #329's saved authoritative
prior trace. On 6,317 unique prior-covered non-singleton inputs, top semantic
action agreement was 98.89%, median TV 0.000109, and p90 TV 0.018815. The
historical source-policy gate also passed at 97.95% agreement, median TV
0.003128, and p90 TV 0.034804. All broad-screen guards passed; SHOP agreement
was 97.70% with median/p90 TV 0.002183/0.016985. The missing old student
checkpoint was not recreated; this is a new seed-0, 30-epoch representation
student frozen outside the worktree. This qualifies offline fidelity only. No
native contextual inference, MCTS/gameplay smoke, policy-strength test, or
default change was made. A separate native implementation and parity/runtime
task is the next step. See [ledger §356](../../experiments/ledger-06.md) and
the [evidence packet](../../experiments/evidence/ooc_contextual_semantic_prior_2026-09-25/README.md).

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

## rollout3 OOC MCTS (§422) — replicated, about 16x CPU, not a default

OOC MCTS with the V4 prior, 2048 simulations and a native `v_win` leaf after 3 additional CTM
combats (`STS_OOC_MCTS_LEAF_COMBATS=3`, `LEAF_VALUE=native`) won 115/128 vs 101/128 for MCTS off
on the current pathb-r2 CTM (control: MCTS off on the §411 research base with flat exact-10k Silver,
not the production defaults, so 78.9% is not the default stack's win rate): +10.9 pp [+2.3, +19.5], boss deaths 11 vs 23. It cost about 936 s
per run on one CPU (off: 57 s) at §422; exact batching of the native shop/card/removal valuation inside the
rollouts (§437, bitwise identical play) cuts that by a seed-dependent 1.13–1.7x per run (1.38x over four seeds), and about 20% of OOC decisions fall back to V4 on Lizard Tail
support aborts. This reproduces §277 (old V2 CTM) and contrasts with the `screengbm` leaf (§384,
−22 pp) and the 0/1 boss-rollout leaf (§391, 9/32, saturated value). Pricing the Lizard states with a
Lizard-capable research CTM (§423, `lizardFairy` + `lizardBrew`) removes the aborts (fallback 2.4%) but
does not win more: 86.7% vs 89.8%, −3.1 pp [−10.9, +4.7], NOT_SHOWN. Since §435 that Lizard-capable artifact is the default OOC MCTS CTM, so
rollout3 on the automatic stack no longer aborts on active Lizard Tail states (A0 census: 47 aborts → 0 on 8 seeds). §422 and §424–§430
ran the automatic stack when it was the #418 model; to reproduce them on a commit after §435, add
`STS_OOC_MCTS_COMBAT_MODEL=selfplay/models/combat_transition_deepsets_pathb_r2.native`,
`STS_OOC_MCTS_BREW_FALLBACK_MODEL=selfplay/models/combat_transition_near_full_escape_pathb_r2.native` and
`STS_OOC_MCTS_ACTIVE_LIZARD=1` (or run their recorded commits). Likewise a rollout3 promotion based on §433 rests
on the #418 model; enabling rollout3 after §435 also brings in the Lizard model, whose win-rate effect §423 did
not show either way, so a promotion note must name the CTM it was measured with. At 512 simulations (§424, 331 s per run)
rollout3 lands between off and 2048: 84.4% wins, +5.5 pp [−3.9, +14.8] over off and −5.5 pp [−12.5, +1.6] vs 2048,
both NOT_SHOWN. One-setting variants on the same seeds (§427–§430): fewer sampled outcomes per chance node
(`WIDEN_K=1`, `WIDEN_ALPHA=0.25`) is WORSE, −10.9 pp [−19.5, −2.3] (p = 0.02 uncorrected, 0.08 Bonferroni over four arms), back to the off win rate; 4096 simulations
(+3.1 pp, about 1.9x CPU), more outcomes (`WIDEN_K=4`, `WIDEN_ALPHA=0.75`, +1.6 pp, about the same CPU) and 5 rollout
combats (−2.3 pp, 37% V4 fallback, mostly Lizard Tail support aborts) are NOT_SHOWN against 2048. With the Lizard-capable CTM (§446, rollout5
vs rollout3 both rerun on one commit after #496) rollout5's fallback drops to 2.9% but it is still NOT_SHOWN: 113/127 vs
111/127, +1.6 pp [−4.7, +8.7], at about 1.5x the CPU. Runs from §422–§430 do not rerun byte for byte on commits after
#480 (Face of Cleric fix `c7641b07`), so later comparisons rerun their controls. On 256 fresh seeds
(§433) 4096 simulations with the broad widening won 87.5% vs 77.7% for off, +9.8 pp [+3.9, +16.0], CONFIRMED; plain
rollout3 won 83.2% (+5.5 pp [−1.2, +12.1] over off, combo − rollout3 +4.3 pp [−1.6, +10.2]) at about half the CPU
(893 vs 1,536 s per run). `STS_OOC_PUBLIC_FUTURES` was off, which favours `off` (#397). Open: choosing between the two
for a default proposal, prior-only and merging variants. With the V4 prior and the V4 leaf policy both replaced by uniform choices
(§441, 128 of the §433 seeds), `combo` loses wins: 85.2% vs 93.0%, −7.8 pp [−15.6, −0.8], WORSE (McNemar p = 0.064);
that search ties plain rollout3 at lower CPU (about 0.5–0.8x on equal binaries, **Inference**). Prior and leaf policy
changed together, so which one carries the loss is open.
Swapping the leaf and fallback win model `STS_WIN_NET` from B0 `v_win` to the public X2-B (§444) in `combo` (§449,
128 fresh paired seeds, `STS_OOC_PUBLIC_FUTURES=8` in both arms) is NOT_SHOWN: 114/128 vs 111/128, +2.3 pp
[−5.5, +10.2], McNemar p = 0.70, at the same CPU. The data do not argue against X2-B, but do not show a gain either.
Philipp made it the OOC MCTS default win model (ADR-0029); `STS_WIN_NET=1` reproduces earlier B0-based OOC MCTS results.
On 128 fresh paired seeds (§451, B0 leaf) neither 8192 simulations (117 vs 118 wins, −0.8 pp [−7.0, +5.5], 2x
MCTS CPU) nor `WIDEN_K=8`, which samples a fresh chance outcome on every visit (119 vs 118, +0.8 pp [−5.5, +7.0], same
CPU), is shown better than `combo`; `combo` won 92.2% there.
At A20 (§457, 128 paired seeds, floors reached) `combo` with today's default CTM, which sees almost no A20 death risk,
is WORSE than off by 6.2 floors [−9.4, −2.9]; with the §443 A20 candidate CTM it is not shown different from off (−0.5
[−2.7, +1.6]), but missing Lizard Tail support sends 65% of its decisions to V4.
With Lizard Tail support added to that A20 CTM (§458, same seeds, V4 fallback 2.2%) `combo` reaches 6.0 floors
further than off [+2.7, +9.4], mostly by surviving act 1; wins 12 vs 9 of 128 are not separated.
Where the CPU goes (§436, one seed, `gprofng`): `CompactTreeNet::predict` about 32%, the CTM encoder about 28%,
the V4 network about 25%, the Silver simulator only about 5%. A bit-identical vectorized CTM `linear` cuts a
rollout3 run by about 10%. On top of §436/§437 the CTM was still about a quarter of rollout3 CPU, almost all in the
DeepSets per-token MLPs of unprepared leaf-rollout samples; an exact per-token memo plus reuse of the shared HP
encoder (§439, bitwise identical play) makes the CTM 2.8x cheaper and a rollout3 run 1.20–1.24x faster, leaving
the CTM at about 10%. With the V4 rollout policy the floor-model calls of the native shop plan, card pick and removal pick
were about 20% of rollout3 CPU after §437 (8% with a uniform rollout policy, which rarely reaches the planner); a
packed tree layout halves them, bit-identically, 1.13–1.19x per run (§442). The largest remaining rollout3 cost is
the V4 network in the rollout gates (about 21%); cached deck tokens and transposed dense layers cut it about
2.8x, bitwise identically, 1.29–1.41x per run (§450). On the A20 winrate-check stack (student_sel as rollout
policy) student forwards inside rollout3 leaves were about 70% of a run and real Silver combat 2–3%; exact kernels
halve the forward and cut OOC MCTS CPU 1.67–1.77x per unit with identical play (§533); an output memo and AVX-512 projections take another 1.15x of run CPU (§535).

## OOC MCTS on the A20 gold decisions (§425) — not shown better than the heuristic

Scored offline on the §419 gold labels (386 verified decisions; every option was meant to be played out 16 times,
but §432 found the futures shared encounters and battle RNG, so each label has far fewer than 16 effective samples),
OOC MCTS with A0-trained models picks options with mean floor regret 4.35 (`prod` settings) and 4.22
(`rollout3`) vs 4.55 for the heuristic and 4.88 for random; both differences have CIs spanning zero.
`rollout3` aborts about a quarter of its A20 searches (Lizard Tail, `hp_envelope`). **Open question:**
whether A20-trained leaf/prior models change this; the replay tooling (`STRATEGIC_MCTS_TARGETS`) reruns
the same decisions with any model environment.

## A20 rollout-leaf compression (#507) — four early MAP targets measured; compression untested

The selected research teacher is PR #524's §458 `combo_liz`: the A20
Lizard-capable CTM pinned by
[ctm_artifacts.txt](../../experiments/evidence/ooc_a20_lizard_458_20261013/ctm_artifacts.txt)
at data commit `c507cebb000cbb308e9ad833721c85ea357af0f1`, with the
[unchanged arm environment](../../experiments/evidence/ooc_a20_lizard_458_20261013/arm_env.sh).
That means 4096 OOC simulations, widening K=4/alpha=0.75, three additional CTM
combats, V4 prior/continuation and native public X2-B bootstrap. The candidate
remains **NOT_QUALIFIED**; selecting it for research does not waive its A20
boss/Lizard gates or promote a default.

Preserved §458 summaries and the §445 decision-root short-branch labels do not
contain the required internal leaf input/target pairs. CTM combat-transition
and gate corpora serve different purposes and are not leaf training data.
The first implementation milestone is the bounded
[leaf capture interface](../architecture/out-of-combat.md): exact returns from
existing evaluations, candidate inputs, provenance and final search status.
The [§461 one-seed A20 collector canary](../../experiments/evidence/ooc_leaf_capture_461_20261013/README.md)
passed: capture off/on had identical deterministic results, decisions, root
statistics and work counts. The bounded first 64 roots produced 286 structurally
valid leaf samples (207 Act 1, 79 Act 2), with no capture errors or root aborts.
Five continuations ended terminal; their inputs were still decision boundaries.
Observed CPU was 267.8 vs 270.9 seconds (+1.18% in one pair, descriptive only).
This reused historical seed is diagnostic, not a holdout or a quality comparison.

The [§462 one-leaf replay](../../experiments/evidence/ooc_leaf_replay_462_20261014/README.md)
also passed: decision 0, sampled ordinal 1025, an initially nonterminal MAP
leaf, returned exactly `0.6771143269743937` in the parent and isolated child.
Forking before evaluation preserved the original model/state ID, callbacks,
policy, caches and RNG; endpoint, combat/step counts and final RNG matched,
with source state/path unchanged. The diagnostic stopped before a real action
and used 0.907 CPU seconds. This proves only one inherited-memory replay;
the JSONL remains an incomplete observation, not a serialized replay snapshot.

The [§471 conditional target pilot](../../experiments/evidence/ooc_leaf_stability_471_20261014/README.md)
returned **STABILITY_MEASURED** for the first four distinct MAP candidate inputs
from the first two historical roots. These are correlated Neow-transform
variants at Act 1/floor 0, not a representative MAP cohort. Each had sixteen
fresh planner streams and one exact original-RNG control. All controls and
both full parent-root records matched; all 64 new-stream evaluations were
supported and nonterminal. Per-leaf sample SD was 0.0433–0.0873 and estimated
SE16 was 0.0108–0.0218. All met the prespecified descriptive SE16≤0.05 flag,
which is not a training gate or error guarantee. The four means span only
0.01997; reliable sibling ranking has not been shown.

This measures the teacher's iterative future-redraw kernel conditional on
complete inherited snapshots, including fixed hidden counters and pool
membership. It does not estimate an expectation conditioned only on the public
input. The next evidence needed is separately bounded coverage across distinct
source runs and later MAP states, with terminal/support coverage and explicit
public-input sufficiency (#506). No such expanded run is preregistered by §471.
A seed-disjoint student fit, ranking/calibration, latency and matched-CPU
gameplay remain untested. Seeds/RNG/endpoint values must never enter student
predictors. The teacher remains NOT_QUALIFIED and no scientific compression
verdict exists.

## V4 OOC token net at A20 (§419) — keep the A0-trained net

The deployed V4 was trained on A0 only (ascension input clamps to +8 at A20). Neither
feeding training-constant inputs as 0 (`STS_OOC_STRATEGIC_TOK_CONST_GUARD`, −1.2 floors,
CI spans 0) nor a Q-head retrain on A20 full-run one-ply labels helped: on 4.9k labeled
decisions NOT_SHOWN (−1.1 floors), on 10.0k decisions RETRAIN_WORSE (−5.6 floors
[−7.75, −3.38], wins 16 vs 29 of 256). Offline no retrain beats the heuristic action it
overrides (strict Q top-1 0.30 vs 0.34). **Inference:** these labels are too noisy for this
route; a better A20 OOC policy needs a different label source, not more of the same data.
§432 found one reason: the corpus's 4 branch futures shared their combats and differed only in out-of-combat choices.

At A0 (§448, map gate on, 128 paired seeds) the gate margin matters more than the training ascension: A20 V4 wins
55/64/83/94/98/90 and A0 V4 70/76/78/78/96/98 of 128 at margins 0/0.25/0.5/1/2/4, heuristic only 86; playing every
V4 argmax (margin 0) loses runs, including to Knowing Skull HP payments. On the Gold2 decisions V4's gains over the
heuristic come from events (mostly Neow), shop and rest-vs-smith, its losses from map and upgrade targets;
§425 OOC MCTS picks also gain on the map. **Open question:** whether the map gate costs wins at margin 1 (no
same-seed map-off arm).

## Independent branch futures and short-branch labels at A20 (§432)

`strategicgen2` branch futures only varied the agent RNG, so `STRATEGIC_BRANCH_FUTURES>1` shared encounters
and battle RNG and diverged only through out-of-combat choices; `STRATEGIC_BRANCH_RESEED=1` (default off) gives each future its own battle RNG and act
encounters. On a rerun of the 262 gold seeds with 16 independent futures, short-branch labels (3 fights,
8 independent futures, then the floor value trees) pick options with 1.25 floors regret vs 2.26 for the
heuristic (+1.01 [+0.56, +1.52]) and 1.98 for the deployed V4; A20-fit and A0 floor trees tie in this role.
**Open question:** whether a policy trained on such labels plays better live.

On 53.5k such labels from fresh A20 seeds (§445), the best learned picker, a GBM on the strategic row, reaches
1.73 floors regret on the same gold set: better than the heuristic (+0.53 [+0.25, +0.84]) but not shown better
than V4 (+0.25 [−0.20, +0.69]). V4 Q-head retrains on these labels match V4, and halving the data barely moves
the GBM on Gold2; more labels give small held-out gains that Gold2 cannot resolve (Inference). Played live on every OOC decision at
A20 (§447), the GBM wins 3 of 128 runs vs 16 for the current stack (floors −2.21 [−5.29, +0.80], NOT_SHOWN by
the pre-registered rule), so Gold2 regret did not predict whole-run play.

## CTM vs low-sim Silver as a combat model (§408) — forecast accuracy needs a corrected comparison

**2026-10-14 mechanism correction:** the §408 producer changed six
`GameContext` RNG streams but retained `gc.seed`. Both the frozen producer
revision and current `BattleContext::init` initialize four ordinary combat
streams from `gc.seed + floorNum`, overwriting those redraws. Silver forecasts
therefore shared part of the reference fight's hidden future, unlike the CTM's
marginal prediction. The historical numbers below remain as-run measurements;
their accuracy advantage does not establish independent-future forecasting
superiority. This finding does not reclassify §411 gameplay without checking
its separate OOC future resampling. The bounded [A20 teacher protocol](../../experiments/evidence/a20_teacher_comparison_20261014/PROTOCOL.md)
uses a corrected, A20-only initialization kernel and keeps the old modes
unchanged. The user selected completed gen6 E from PR #541; its v2 support is
integrated from `main` merge `531db3e3`. The [bounded A20 attempt](../../experiments/evidence/a20_teacher_comparison_20261014/gen6E-attempt-1/RESULTS.md)
(§480) passed actual-model parity and its excluded canary, but one of four
cohort sources hit the fixed 180-second CPU cap. The exact verdict is
**INVALID_OR_INSUFFICIENT**. The completed sources are not a replacement panel;
there is no teacher-quality or optimal-budget conclusion. All outputs are
preserved, with no retry, extension, training or default change.

The user authorized a separately frozen [v2 follow-up](../../experiments/evidence/a20_teacher_comparison_20261014/PROTOCOL-V2.md)
with flushed replay progress, 600 CPU/900 wall seconds per source, canary
`97150801` and four fresh sources `97150810–97150813`. It preserves the model,
controller settings, source/reference and analysis, and does not pool §480.
The [completed follow-up](../../experiments/evidence/a20_teacher_comparison_20261014/gen6E-attempt-2/RESULTS.md)
(§481) is **DESCRIPTIVE_COMPARISON_MEASURED**: 14 supported states (6/4/2/2
per source), all exact controls/progress/custody checks pass. Principal
equal-source HP RMSE: CTM 9.246, plain2k 6.605, prior2k 8.171, plain10k
6.397, prior10k 8.276. Four-future search CPU is 0.587/0.622/3.279/3.275s
for the Silver conditions; CTM expectation is 0.0795ms, with different timer
scopes. Prior-minus-plain HP/death contrasts are −0.286/+2.083pp at 2k and
+0.495/−2.604pp at 10k. The cost/prior effects remain descriptive and mixed;
two early Act 1 sources carry half the fixed equal-source weight, and only
one source has Act 3 coverage. No population winner, optimal budget, training,
OOC decision-value or promotion conclusion follows. Plain2k is an inexpensive
candidate for a subsequent selective Silver decision-value audit, not a
qualified teacher replacement.

The prospective [larger-study contract](../../experiments/evidence/a20_teacher_comparison_20261014/PROTOCOL-LARGE.md)
compares the calibrated A20 CTM with plain2k and gen6 E prior2k on 32 fresh
source clusters and 16 paired futures per fight. Eight fixed sources also
compare both 10k settings. Source-cluster bootstrap intervals and explicit
later-act coverage gates supersede pilot-only point estimates for this new
panel; the pilot remains preserved separately. The old uncalibrated CTM RMSE
does not describe the calibrated manifest. This contract makes no training,
OOC decision-value, gameplay or default-promotion claim.

The [completed larger study](../../experiments/evidence/a20_teacher_comparison_20261014/gen6E-large-1/RESULTS.md)
(§482) is **DESCRIPTIVE_COMPARISON_MEASURED**: 32 sources, 147 matched fights,
5,696 forecast replays, all controls/custody/progress/caps pass. Main later-act
coverage passes (17 Act 2 boss / 13 Act 3 boss sources). Equal-source HP RMSE
is CTM 12.017 [10.441,13.511], plain2k 11.853 [10.011,13.606], prior2k
11.599 [9.692,13.396]; all paired main fidelity intervals include zero.
Neither superiority nor equivalence is established. Gen6 E2k has a nominal
paired controller benefit: +0.796 [0.247,1.348] RAW HP and −0.921
[−1.784,−0.068]pp death, for +0.00597s/fight search CPU. The eight-source
10k subset has 31 states but only two sources at each later boss; its
28.6–29.6s/16-future forecast cost is about 5.4–5.6× the 2k conditions,
with incremental controller benefit unresolved. **Inference:** retain CTM
for bulk evaluation and nominate gen6 E2k for a selective OOC decision-value
audit; do not infer training-teacher qualification or increased run wins.
Total CPU including excluded canary was 5,074.70s; largest source 918.11s
under the 1200s cap. Earlier attempts remain separately preserved and excluded.

The subsequent [selective MAP-choice audit](../../experiments/evidence/ooc_selective_silver_audit_20261014/run-1/RESULTS.md)
(§483) is **INVALID_OR_INSUFFICIENT**: the excluded canary completed two roots
with exact source and baseline controls, but provenance hashing utility children
left0.011785s outside itemized child CPU settlement. The analyzer rejected it;
the eight-source cohort never launched. A narrow tested accounting repair
records measured utility-child CPU inside unchanged caps and tolerance.
The failed canary remains excluded/invalid, without a decision-quality result
or retry. The first matched CTM arm also hit4096 paired futures at0.474× Silver
cost, leaving matched compute unresolved. A newly authorized freeze/canary
must precede future cohort execution; no training or default change follows.

The authorized [renewed E2500 audit](../../experiments/evidence/ooc_selective_silver_audit_20261014/run-2/RESULTS.md)
(§484) has a valid fresh canary with exact provenance CPU settlement, but an
**INVALID_OR_INSUFFICIENT** cohort. Both initially dispatched sources fail:
one Act2 Silver evaluation and one Act3 plain10k reference, normal child exit125
with the underlying exception erased. Six remaining sources never launch.
No teacher-quality conclusion or gen6-specific attribution is supported.
The audit-only fork callback now transports bounded errors and retains failure
cost/candidate/future metadata, with real seed-free tests. Original data and
verdict stay sealed. A later exact-prefix replay of the two failed sources
[found the cause](../../experiments/evidence/ooc_selective_silver_audit_20261014/run-2/ROOT_CAUSE.md):
the audit sampler rejected a played Discovery (`undefinedBehaviorEvoked`) as a
health failure. With that fixed, the authorized
[run 3](../../experiments/evidence/ooc_selective_silver_audit_20261014/run-3/RESULTS.md)
on fresh seeds completed: Silver8 beats the baseline OOC MAP choice on the
plain10k-Silver surrogate reference (+0.0225 [+0.0064,+0.0404], 8 sources,
15 roots). CTM rescoring with up to 4096 futures reaches nearly the same
(Silver8−matched +0.0038, interval includes zero) at about 0.6× the CPU, so a
compute-matched Silver advantage is not shown. The reference is plain10k Silver
and may share Silver's biases. Pre-ADR-0035/0036 Silver.
No training/default promotion.

On 6,750 real fight entries (256 fresh runs), forecasting the exact-10k Silver
outcome, four low-sim Silver playouts under that partially redrawn RNG beat the production
CTM stack on post-combat HP (RMSE 8.5 vs 11.7; biases −2.6 and +2.3) and on every
post-combat field (potions, relic counters, max HP, gold, deck), and tie it on
deaths. The CTM costs 0.6 ms per forecast, versus 64 ms per prior-256 playout
and 23 ms per prior-64 playout. No default changed; the open questions are the
Run 2 retrained CTM on the same states and a matched-CPU OOC MCTS gameplay test
([§408](../../experiments/ledger-06.md), `one_combat ctmsilvergen`; its "production CTM" arm stays
pinned to the pre-#418 stack after the #418 swap, so §408/§410 reproduce).

Both follow-ups ran. The Run 2 (Path B) CTM is clearly better than production on the same states
(post-combat HP RMSE 9.1 vs 11.7, bias +0.2, better deaths and potions) but still behind four prior-256
playouts on HP after act 1 and on every non-HP field ([§410](../../experiments/ledger-06.md)). Inside live
OOC MCTS a Silver combat resolver (64 sims + prior per imagined combat, research-only
`STS_OOC_MCTS_COMBAT_RESOLVER=silver`) was not detectably better at matched simulations (+3.1 pp, 10x the
MCTS CPU) and pointed worse at matched CPU (−8.6 pp [−17.2, 0.0]) on 128 pairs; no MCTS arm beat MCTS off
([§411](../../experiments/ledger-06.md)). The CTM stays; its value is speed.

**Opening hand and first-search screens (ledger §529, #460, 2026-10-18).** On the Stage-4 A20 corpus an
XGBoost outcome model gains nothing measurable from the realized opening hand (death log loss +0.00015
[−0.00025, +0.00057], HP-lost MSE −0.25 [−0.62, +0.15] of 129), and averaging over sampled hands is slightly worse,
so an opening-hand latent is not worth a CTM schema change for OOC MCTS (the OOC tree would not get wider either: its
chance-node width depends only on visits). The endpoint distribution of the first 10k Silver search of a fight is a
biased forecast on 1,048 A20 fights compared with the calibrated A20 CTM: death Brier 0.063 vs 0.026 and about
12 HP too pessimistic on wins, although Silver sees the hand. On the CTM's post-heal scale its spread matches the
CTM's once the bias is removed (RMSE 12.07 vs 11.97; log score −0.13 [−0.25, −0.01]), so a bias-corrected Silver
label is not ruled out (Inference), at ~400x the CPU.

## Merged DeepSets CTM Brew-fallback quality confirmation

The independent 512-pair gameplay confirmation is **`OOC_HYBRID_QUALITY_CONFIRMED`**.
The frozen local paired run completed on 2026-09-25: C won 277/512 and H won
292/512; H minus C was +2.9297 pp with paired bootstrap 95% CI
[-1.7578, +7.6172] pp, passing the preregistered -5.0 pp non-inferiority margin.
This does not establish superiority or change the opt-in default. The former
GCP blocker describes preparation only; no server restoration or resume is
needed. Frozen preparation manifests remain historical evidence. See
[the completed evidence packet](../../experiments/evidence/deepset_entropic_brew_hybrid_confirmation_2026-09-24/README.md).

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

**Removed with the vendored model (ADR-0022, 2026-09-25) and carried over to
native Silver** ([§354](../../experiments/ledger-06.md)): native one-action
roots are committed without search by default; the paired 128-seed check
showed no detectable gameplay difference (86/128 vs 82/128, +3.1 pp, 95% CI
[−1.7, +8.0]) and 6.5% less time per run. The record below is history.

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

### Learned Silver stopping (§370, §372, §377, 2026-10-03)

**`LEARNED_STOP_PASS`**, research-only and default off. With
`STS_SILVER_LEARNED_STOP=1`, each multi-action root is searched to the
250..10k checkpoints. Search stops at a strict visit lock or when the risk
from the compiled GBT model is below its threshold (v1 `gbt-b91dcfea64e1` at 0.03), and this
applies to fresh roots too. In the frozen fight-replay A/B over 2,437 fights
(seeds `42000000..42000095`), learned stopping used 19.4% fewer simulations
than #199 [18.3, 20.5]. The signedOutcome difference was +0.0019 per fight
[−0.0009, +0.0048].

Against flat 10k:
- #199: −0.0029 [−0.0054, −0.0004];
- learned stopping: −0.0010 [−0.0040, +0.0021].

128 live paired runs were descriptive only: 75.8% vs 70.3% wins and 23% less
CPU per run. Most of the offline saving comes from the strict lock alone. The
model overfits its training seeds, and the gate is non-inferiority with about
80% pass probability at zero true effect.

**v2 (§372):** the compiled model is now `gbt-770201c31f7b` (threshold
0.0323). It was trained on 160 seeds with 4 trend features and chosen by
seed-grouped cross-validation. A fresh confirmation on seeds
`44000000..44000127` (3,385 fights) also passed: 21.3% fewer simulations
than #199 [20.3, 22.3] at −0.0007 signedOutcome per fight
[−0.0031, +0.0018]. A lock-only arm used 12.7% more simulations than #199, so
the model carries the saving. Live (128 paired, descriptive): 77.3% vs 76.6%
wins and 25% less time per run. **v3 live (§377):** a 1,024-pair live run against #199 gave
`PROMOTE_learned`: +0.49 floors (98.33% CI [+0.08, +0.91]), 80.3% vs 78.3%
wins, 19% less time per run. The earlier −1 floor lean did not replicate.
Neither variant tested for boss fights did better than plain v2: falling back
to #199 in boss rooms, or allowing up to 30k simulations
(`STS_SILVER_LEARNED_STOP_BOSS_FALLBACK`, `_BOSS_MAX`). Both options stay
research-only, and the 10k cap stays. Philipp made learned stopping the whole-run default
([ADR-0026](../../../decisions/0026-learned-silver-stopping-default.md)).

See [ledger §370, §372 and §377](../../experiments/ledger-06.md), the
[v1 packet](../../experiments/evidence/silver_learned_stop/README.md) and the
[v2 packet](../../experiments/evidence/silver_learned_stop/v2/README.md) and the [v3 packet](../../experiments/evidence/silver_learned_stop/v3/README.md).

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

The tracked artifact at `selfplay/models/combat_transition_near_full_except_smoke_v2.native` (the default until #418 replaced it with the escape-capable pathb-r2 pair, §412; kept for rollback) uses the targeted attention-HPO survival component (artifact SHA256 `e9a18951710fdfe9e1a81a2703090a41f039067c670a1d8a0393b5e7e8e0ddfd`). All other component checkpoints are unchanged. Frozen TEST survival NLL/Brier improve from 0.060412/0.017986 to 0.058878/0.017384. The full final-support composition and RAW gates were rerun: all nonempty exposure slices pass, the established exact correction resolves the one Monte Carlo gold zero, and 1,633,152 transitions have zero hard-validity violations. Python/native CPU FP32 probabilities pass at 1e-4 tolerance (maximum error 2.38e−6); complete RAW state, planner stream and scalar/prepared parity pass on 3,904 draws, including 127 recursive Brew cases and three unsupported/no-draw fixtures. The executed native support predicate still exactly matches both corpus/TEST ordered-index hashes.

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

The four other streams are recreated on every battle entry. At the time of
this evidence the normal controller had no reachable same-floor combat chain:
Colosseum was disabled and unimplemented, event callbacks ended at rewards/map,
and A20's second boss increments floor. Colosseum is now enabled and its Nob
fight continues the slaver fight's streams (see
[RNG ownership](../behavior/determinism-and-rng.md)); that chain is not
covered by this evidence. There are zero same-floor pairs among 485,031 consecutive
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

## Active Lizard minimal CTM qualification (2026-09-25)

The frozen 128-source qualification cohort completed, but classification is
**`ACTIVE_LIZARD_QUALIFICATION_INCONCLUSIVE`** with subclass
**`LIZARD_QUALIFICATION_INCONCLUSIVE_RARE_EVENT`**. It produced 9
`LOSS_CONSUMED` outcomes from 9 sources, below the fixed requirement of 20
from 10. The pooled q/r three-class NLL mean improved over B1, but its
source-bootstrap 95% CI crosses zero; the q consumption model was worse than
B1 on pooled NLL and Brier point estimates. The pooled r score gate passed,
and frozen T2 also passed fresh numeric checks on 36 consumed wins, but neither
rescues the overall gate. HARD96 and BROAD32 counts, all NLL/Brier intervals,
the signed B1 numerical-epsilon audit, and source-level retained-win checks are
in the [qualification evidence packet](../../experiments/evidence/lizard_tail_minimal_ctm_qualification_2026-09-25/README.md)
and [analysis JSON](../../experiments/evidence/lizard_tail_minimal_ctm_qualification_2026-09-25/fresh_qualification_analysis.json).

No Phase 6 ancestral qualification, native integration, Python/native parity,
support promotion, or live seed `13027029` smoke was run. The production
`active_unqualified_lizard` support reason remains in place for nondeterministic
active Tail. Fairy Potion plus active Tail remains unqualified, and Mark of the
Bloom retains its existing exact path. If qualification continues, use the
designated GCP/large-research procedure with the frozen artifact and gates;
this local 128-source budget is closed. See [ledger §381](../../experiments/ledger-06.md).

A follow-up keeps the PR #326 learned `r` and T2 rule frozen while setting
`q = 1 - pOrdinaryWin`. On the exact archived 128-row vendored cohort, the
mechanical-q candidate improved pooled three-class NLL and Brier against B1,
with exact q parity and support on all rows; the 9 `LOSS_CONSUMED` labels from
9 sources remain below the qualification floor. This archived post-hoc screen
is development evidence only. The first native-Silver transfer attempt
replayed the campaign and failed to reach an archived fight index after the
native outcomes changed the later trajectory. That is a harness failure, not
a teacher-transfer result; it produced no native pair rows or scores. The
corrected plan directly restores the 119 exact non-burning PR #326 persistent
snapshots and excludes only the nine burning-elite targets whose archived
states lack `burningEliteBuff`. PR #331 made native Silver update
`simulationCountTotal`; merged PR #332 default-initializes that counter to
zero. Retry 4 saved 116 pairs, then stalled on three Event-room snapshots
because the direct snapshot lacked `curEvent` and the event-option callback:
the generic `afterBattle()` callback recursively called `regainControl()`. A
neutral post-capture return-to-map continuation fixed the collector. Retry 5
reran all 119 exact non-burning snapshots with the then-current native teacher
pinned to `0eed6993999386737d87f040e38fb241623b5cf3` and one executable; all 119
rows had exact support and mechanical-q parity. Its predeclared analyzer
decision was `PROCEED_TO_FRESH_NATIVE_QUALIFICATION`; this is historical
transfer evidence, not qualification. Current main is
`6bae3a67c63d1f724908e2ee87b27d51e32d30a0`. PR #327 changed native Silver's
equivalent-copy reroot behavior, which the frozen exact-root-budget setting
does not disable; PR #362 changed `SilverWireState` and `SilverConversion` to
preserve pending card queues at card-selection roots and settle Guardian Mode
Shift before replay. Retry 6 then reran the exact same 119 states against
current native Silver (baseline `6bae3a67c63d1f724908e2ee87b27d51e32d30a0`):
119/119 exact snapshots, support, and mechanical-q parity; 80
`WIN_RETAINED`, 30 `WIN_CONSUMED`, and 9 `LOSS_CONSUMED`. The frozen transfer
analysis passed the proceed gate with no clear candidate, learned-r, or T2
regression. Its 19/119 vendored/native label disagreements remain descriptive;
teacher rows are not pooled. Stage B permits the fresh run, but does not
qualify the candidate. The frozen fresh 320-source assignment remains disjoint
from 367 prior Lizard sources. Following ADR-0024, the user authorized its
local execution. The original scientific plan freezes the candidate,
assignment, selection rules, and gates in
`stage_c_preoutcome_plan.json` (SHA-256
`54784e141ef029e132d07c5aa0300d5f7440034a49d427c19438a6096355736c`). The
collector uses eight independent source processes with one OpenMP thread each;
completed sources are saved with per-seed manifests and checksums for resume.
The first candidate attempt completed eight source shards but failed when its
write-once artifact helper refused to replace the mutable progress index. All
eight data/manifest/provenance/log sets validated against the then-frozen
producer; no target selection/scoring, pair collection, or qualification
analysis ran. Afterward, main advanced to `212aa25485bc6e8f0a5a91eb35edc7485056cb5a`
through PR #366. Its OOC MCTS observer is opt-in, and
`STS_OOC_MCTS_REUSE_TRACE` is unset in the frozen teacher config; Stage B retry
6 remains the proceed diagnostic. The merged PR source was clean-built at
producer commit `45ff412f2f48ee4ff8b14325b8e317688a3a2880`, executable
SHA-256 `8965131f93e6d56544c8a127ce7308decc66b8ef61ff511845d2760f88aa35ea`,
and teacher-manifest SHA-256
`c271a3edc7adb8237ca1e6a8611c7e97be1ba2efadd6d5179fa80dcad476dbc8`. The
older eight shards are preserved but excluded so all Stage-C rows share that
one producer and executable hash. The corrected current-main plan
`stage_c_preoutcome_plan_retry2_current_main_indexfix.json` (SHA-256
`2c4d5eb54ee0277573ddef9e21359852ac965cbd0a5a9df9496086432f2a3ee2`)
records the base advance and supersedes the earlier execution amendment without
changing the candidate, assignment, selection rule, worker topology, or gates.
Its attempt record is
`stage_c_candidate_collection_attempt2_main_advance.json` (SHA-256
`58024b987d90783e6b5fc633cc0b110e71f302f9eb0b273111fc8b8cbc3c9972`). The
current-main Stage-C run completed with one producer commit and executable:
320/320 source candidate shards, 6,509 candidate rows, 4,674
prospective-support eligible states, and 320 outcome-blind selected targets
(288 HARD288 plus 32 BROAD32). The selected-target file SHA-256 is
`68c4e6e4c20596464338e3b8ab44ea0bae8bc4a431d7f3de765a944dc8063493`. The
separate frozen pair plan SHA-256 is
`dc1084ea262769500f7fd37852cfd237ecc89cd4e74267c54adc0929d4dabd07`; the
current-main native-Silver teacher manifest is
`c271a3edc7adb8237ca1e6a8611c7e97be1ba2efadd6d5179fa80dcad476dbc8`. Pair
collection completed all 320 exact-10k fair native-Silver pairs using eight
subprocesses with one OpenMP thread each. All 320 rows passed execution,
support, and mechanical-q checks. Labels were 195 `WIN_RETAINED`, 105
`WIN_CONSUMED`, and 20 `LOSS_CONSUMED` from 20 distinct sources; all 125
consumed rows were B1-scoreable.

The frozen analyzer classified the candidate
`ACTIVE_LIZARD_MECHANICAL_Q_LEARNED_R_T2_NATIVE_QUALIFIED`. Candidate-minus-B1
pooled three-class NLL was `-12.99026` (source-bootstrap 95% CI
`[-23.75822,-4.36279]`) and multiclass Brier was `-0.05266` (CI
`[-0.07482,-0.03239]`). Learned-r NLL and Brier deltas on 125 consumed rows
were `-1.85084` (CI `[-3.26182,-0.71950]`) and `-0.11904` (CI
`[-0.16692,-0.07162]`). T2-minus-T0 on 105 supported consumed wins was
`-1.06154` HP NLL (CI `[-1.47307,-0.67843]`), `-3.18088` HP CRPS (CI
`[-4.85606,-1.51303]`), and `-2.84107` expected-HP absolute error (CI
`[-4.77866,-1.02229]`). The rare-event floor, exact-support, q-parity,
primary, learned-r, and T2 gates passed; no clear HARD288 or BROAD32
degradation was detected. The 32 BROAD32 outcomes were all retained wins and
therefore contain no consumed-tail rows. Stage C is offline qualification
only and did not itself integrate runtime support. The subsequent DeepSets plus
standard-Attention Brew integration added the qualified correction and passed
deterministic parity, including after the branch was re-synced with current
main. The original eight-pair whole-run canary was invalid because the forced
Tail was inserted spent; its treatment did not exercise the correction. The
disjoint follow-up cohort `991008..991015` passed the predeclared Gate 2
integration checks after the forced-Tail initializer was corrected. All 16 runs
completed; treatment had 120,708 Lizard preparations and samples with zero
Lizard support failures. A single treatment seed recorded 41
`active_unqualified_lizard` aborts on the predeclared Fairy/Mark exact-path
boundaries; those matched the 41 boundary exclusions, with no abort from an
eligible correction state. Both arms won 8/8, which is descriptive only.

After Gate 2, the exact qualified DeepSets payload was packaged as
`selfplay/models/combat_transition_deepsets_lizard_t2.native`. Its tensor
payload remains SHA-256
`429f9dc018a6b9de231657df4aba787bddc2de2e4cecb2e7989e167c37813139`; package
metadata is pinned to the Gate 2 PASS result hash. With `STS_OOC_MCTS=1` and
the combat model unset, this was the default stack (DeepSets, the standard
Attention Brew fallback, and the active-Lizard correction) until #418 (§412)
swapped the default to the escape-capable pathb-r2 pair
(`combat_transition_deepsets_pathb_r2.native` `90806c25…`,
`combat_transition_near_full_escape_pathb_r2.native` `b9188de0…`, pinned by the
runtime's built-in manifest `d9d8377e…`, so default runs report identity
`production` and skip the Smoke Bomb masking). Rollback: set
`STS_OOC_MCTS_COMBAT_MODEL` to this `lizard_t2` file,
`STS_OOC_MCTS_BREW_FALLBACK_MODEL` to the `except_smoke_v2` file and
`STS_OOC_MCTS_ACTIVE_LIZARD=1`. The live advisor still uses the pre-#418 stack. `STS_OOC_MCTS` itself remains
off by default. On those stacks active Lizard + Entropic Brew, Fairy Potion, and
Mark of the Bloom are excluded or exact-path boundaries; since §435 the default
stack prices Brew and Fairy (`lizardBrew`, `lizardFairy`), and Bloom stays on
its exact path. The original invalid cohort
remains preserved separately from the successful follow-up.

Two no-model-override Gate 3 smokes on frozen implementation
`529c214562fd7eda4842f4386c05303c4d3d3d47` reported the automatic stack in the
startup line and combat telemetry. The ordinary case had no forced relic; the
forced-Tail case recorded 17,610 Lizard preparations and 17,608 samples. It
also recorded two existing `unsupported:smoke_bomb` exclusions, with no fast or
Brew-fallback support counter failures. The auxiliary `[ooc-mcts-config]` line
is malformed JSON, although its text shows the expected model/fallback/active
fields. The ordinary case produced complete outputs and its final `BEST`
summary, but the wrapper did not save its subprocess exit code after failing
while parsing that line; the seed was not repeated. See the
[Gate 3 smoke packet](../../experiments/evidence/lizard_tail_mechanical_q_ctm_integration_2026-09-27/gate3_default_smokes_2026-09-27/README.md).

After current main advanced with the Match and Keep policy, the merged branch
again passed frozen Gate 1 parity, the 31-row Brew fixture, and focused
combat-transition/OOC tests. See [ledger §364](../../experiments/ledger-06.md)
for Stage C, [ledger §365](../../experiments/ledger-06.md) for the original
integration attempt, [ledger §366](../../experiments/ledger-06.md) for the
follow-up/default, and the [mechanical-q evidence packet](../../experiments/evidence/lizard_tail_mechanical_q_qualification_2026-09-25/README.md).

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

Per-context search constants (#400 Stage 1, ledger-06 §369) are
**`ADAPTIVE_SEARCH_PARAMS_NOT_JUSTIFIED`**: across 3,360 replayed fights, choosing
exploration/widening per room class × act beat the best global arm by only
+0.0044 signedOutcome per fight (CI [-0.0003, +0.0089]), and no tested arm
(exploration 12.5/50, widening alpha 0.40/0.65) beat the defaults globally.
No per-combat controller is built; revisit only with a learned prior.
Splitting the widening constants by chance-node category (ledger-06 §518, A20,
gen-6 prior at 2,500 simulations, 3,043 paired fights: end-turn wider, other
nodes narrower, and spire-mentor's constants) is NOT_SHOWN on all three
contrasts, with score CIs within ±1.8; the shared defaults stay.
Per root (ledger-06 §526, A20, 5,954 probed roots on 52 smoke seeds, regret of the 2,500-simulation pick
against two independent 20k references): no constant setting differs from base on average, per-root heterogeneity
is not shown once selection and scoring use different references (oracle per-root choice 0.032 [−0.014, +0.079],
against 0.124 for 4x simulations), and LightGBM on cheap root features (act, room, turn, HP, actions, energy, hand,
monsters, base visit share) recovers nothing, so no per-root parameter controller is built.

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

### `v_win` refresh implementation status (#334)

The opt-in `vwinrefreshgen` and `bossheadroom347gen` producers now encode the
accepted exact-10k/V4 data contract, deferred semantic siblings, victory-boundary
`WIN_RAW` capture, chosen-replay parity, and paired #347 boss-budget arms.
Revision 5 adds opt-in `DECISION` rows with public screen contents and semantic
candidates on source/branch trajectories, including sequential shop states and
compound selectors, for later #379 work. These rows are not used to train #334.
The bundle validator and Stage-1 paired-bootstrap analyzer are implemented.
The A3 offline model tooling now supports strict mixed-producer corpus access,
TRAIN-only feature selection, validation-selected X1/X2/M1, mandatory selected-
checkpoint VALIDATION resource qualification, runtime/Git-bound one-time TEST
opening, clustered predictive/resource/sibling evaluation, and the X1
half-TRAIN data-sufficiency diagnostic. See the
[A3 operational contract](../operations/ooc-label-pipeline.md#a3-offline-model-training-and-evaluation).
This is tooling status: full candidate training and real TEST predictions
remain unopened pending independent review. Lookup-table fidelity, MCTS leaf
coverage/timing, and gameplay/default-promotion gates remain separate later
work. No result from the tracked model's §353 audit is changed by this tooling.

#397 Stage 1 (ledger-06 §371) classified the rich `v_win` state: only
`nextEliteId`/`nextFight0..2` are hidden future; the remaining V4-excluded
counts are public. Retraining the A3 X1 recipe without the four hidden fields
was `INCONCLUSIVE` (3-seed mean VALIDATION NLL 0.4458 versus 0.4485 with them),
with no sign the leak helps. XGBoost seed noise (~0.007-0.010 NLL) exceeds the
question's 0.002 materiality and the A3 X1 grid spread, so single-seed A3
selection should not be over-interpreted. The public-history/derived-probability
stages of #397 were tested on that baseline in §§374–376 and §378; no family was adopted.
Live (ledger-06 §434): the native fallback's use of the realized queue is not shown to
change wins; legacy 103/128 vs `STS_OOC_PUBLIC_FUTURES=8` 104/128, Δ +0.8 pp [−4.7, +6.3].
#396 Stage 1 (ledger-06 §418): removing the forward-map block from that
baseline was `INCONCLUSIVE` (+0.0050 NLL, CI includes 0, about twice the
retraining null), removing `bossId` also `INCONCLUSIVE` (+0.0012). Stage 2
richer map encodings are not pursued; no default is affected (heuristic
pathing, tracked `v_win_trees.txt` unchanged).
Stage 1b (§373) found the TRAIN mask already excludes every unreachable card,
relic and potion column. Stage 2 (§374): raw relic/event/encounter history
each worsened a 5-seed ensemble slightly (`INCONCLUSIVE`, none adopted);
Stages 2b–2d (§§375–376): Java-verified potion, rarity, next-elite,
next-hallway, ?-room and remove-price features gave no held-out gain (none
adopted); a monotone duplicate column alone shifted the ensemble by +0.0056
NLL, which bounds the method's resolution on this corpus. Event-eligibility
distributions were not built.
The A3 M1 MLP follow-up (§378) also found no qualifying family; relic
history (relics seen but not owned) is the one direction worth re-testing on a
larger corpus or in the replacement model.
#401 (ledger-06 §438) audited the tree value inputs on 78,643 A20 `strategicgen` runs: relics,
deck cards and HP carry most unique signal for both final floor and win. B0 and the A20 floor tree use
the hidden future-encounter fields (the A20 win tree does not), but a refit without the ten hidden,
queue and RNG-counter columns shows no detectable loss (floor +0.18 MSE [−0.08, +0.45], win −0.0005
NLL; refit noise about ±0.05–0.15 MSE). Adding the 12 forward-map columns, the only missing group
tested, cuts A20 floor MSE by 2.15 [1.80, 2.51] (win borderline). These are offline error changes on
the generator's own runs, not win-rate changes; the A0 refit on the #334 fragment resolves nothing.
No model or contract changed; the forward map is the recommended addition for the next A20 retrain.
#401 Stage 1 for the deployed learned models (ledger-06 §546, permutation on each model's own held-out split):
student_sel reads mainly the offered cards and `select_screen_type`; its `--extra-inputs` (relic counters, act,
deck misc) and the map node tokens contribute about nothing, and its value head is untrained (output about −0.03;
no search path reads it, only diagnostic annotations show it; it is to be trained in the AlphaZero loop). g7f_E reads the candidate card,
monster slots (intent, HP, id) and candidate action/targeting; gold, maxHp and pile counts are dead, and
most groups are about 1.5–3x weaker on Act-4 roots, where its CE is worst. The A20 fast CTM child prices survival mostly by act
and room type, then deck, HP, relics and encounter id; gold and several token side fields are ≈ 0. Descriptive
only; removal candidates need refit ablations.

The opt-in MCTS leaf-state trace remains outside this implementation until the
open #363 adapter/profile seam is available. No inference should be made from
the new OOC branch/action trace about leaf-state coverage or in-context
`v_win` latency. See the [collector and validation contract](../operations/ooc-label-pipeline.md#v_win-refresh-and-347-boss-headroom-collector).

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
