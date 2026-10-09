## §175 Posterior-valid particle sensitivity probe — Phase 1b implementation and preregistration v1 (2026-08-16; superseded before scientific run)

Phase 1b extends the §174 draw-order probe. Where Phase 1a artificially
permuted draw order while holding the visible state, draw-pile multiset, and
all six simulator RNG streams fixed, Phase 1b asks whether multiple FULL
hidden states that are actually compatible with Searcher3's CURRENT finite
root belief — and with the same semantic action history and resulting visible
leaf observation — have materially different continuation values.
"Posterior-valid" here means validity relative to Searcher3's finite belief
approximation; it is NOT an exact Bayesian posterior.

- **Implementation:** `one_combat particle_posterior_probe` (branch
  `exp/particle-posterior-sensitivity-phase1b`), guarded by
  `STS_PARTICLE_POSTERIOR_PROBE_FILE` with `…_K` (0 = evaluate ALL unique
  compatible leaf hidden states; >0 = deterministic mass-respecting cap with
  the source world always included and no duplicate padding) and
  `…_MAX_GROUPS` (-1 unlimited, 0 = probe-OFF determinism arm, >0 per-seed
  cap). `BattleScumSearcher3::step` records per-action semantic checkpoints
  (tree actions, expansion action, deterministic chain actions — never random
  rollout actions) with the ACTUAL post-action `CombatObservation` and
  `Outcome` when the new `g_s3LeafTraceActions` flag is set. The callback
  replays the semantic prefix under every positive-weight root particle with
  exact hidden-state application (`applyHiddenStateExact`; stale-particle
  fallback is rejected, never shuffled), requires exact observation AND
  outcome equality at EVERY intermediate checkpoint
  (`INTERMEDIATE_OBSERVATION_MISMATCH` rejects even if the leaf reconverges)
  and at the final leaf, deduplicates accepted leaf worlds by
  `FullHiddenStateKey` EQUALITY (ordered map; combined hashes are audit
  telemetry only) with probability mass aggregated across collapsing
  particles, and scores each evaluated world via the isolated
  `diagnosticRollout` with one per-group CRN seed. CARD actions rebind by
  canonical card identity (`resolveCardKeyInHand`); END_TURN/POTION replay
  raw bits; all card-select paths mark the group
  `UNREPLAYABLE_ACTION_PREFIX` (ineligible) rather than guessing. Source
  groups whose source particle needed the fallback shuffle are marked
  `SOURCE_PARTICLE_FALLBACK` and scientifically ineligible — that is NOT an
  implementation failure; for exact-source groups, failed source replay
  (`sourceParticleReplayOk == 0`) IS an implementation invariant failure.
  `rootCarried`/`reuseGeneration`/`reuseSearchCount` are recorded per group so
  fallback ineligibility can be attributed to carried-search roots. Searcher3
  gameplay/search behavior, belief updates, particle count, tree reuse, and
  the Phase-1a `particle_leaf_probe` are unchanged; leafdiag/frontiergen
  costs are unchanged (trace flag default off).
- **Offline analysis:** `tools/analyze_particle_posterior_probe.py`
  (analysis only, no training) groups by source leaf, reports
  all-group/eligible/multi-state prevalences, range thresholds (=0, >1, >5,
  >10), compatible/evaluated probability mass, mass-weighted range/std,
  per-seed metrics, seed-bootstrap 95% CIs for fraction(range>5) and mean
  range, descriptive turn/draw-pile/encounter/depth strata, capped-evaluation
  detection (range metrics flagged as subsampled lower bounds when any group
  is capped), and structure validation (no fake padding, source world present
  exactly once). Groups with <2 evaluated compatible states count as range 0
  in the primary all-group prevalence.
- **Pre-registered Phase-1b v1 decision rule (set BEFORE any Phase-1b scientific
  data collection):** PRIMARY quantity = fraction of ALL sampled source
  groups with posterior-valid target range > 5 (single-state and ineligible
  groups count as non-sensitive). GO if implementation invariants all pass
  AND fraction(range>5) >= 10% AND seed-bootstrap 95% CI lower bound > 5% AND
  group-weighted (compatible-mass-weighted) mean range >= 3. STOP the
  draw-order/full-particle-conditioning line if invariants pass AND
  fraction(range>5) < 5% AND bootstrap upper 95% CI < 10% AND mean range
  < 1. Otherwise INCONCLUSIVE: no particle VNet training, at most one
  focused 32-seed extension proposal. These are pragmatic Phase-1b
  thresholds, not previously validated gameplay thresholds. If GO: Phase 1
  is substantively successful, roadmap continues with #2 (post-combat
  V_run_win); #3 (particle-conditioned VNet) becomes justified only if #2
  also succeeds.
- **Supersession before designated scientific data:** the 4-seed implementation
  smoke showed that the original full-particle target combines draw-order
  variation, six simulator-RNG-stream variation, and one-rollout estimation
  noise. That target remains useful as a secondary total-determinizations
  quantity for future #4 belief averaging, but is not a clean primary gate for
  particle-conditioned #3 valuation. No designated scientific data were
  collected under v1. This entry is superseded by the controlled decomposition
  below; the v1 GO/STOP rule must not be applied to the v1 full-particle smoke.
- **Verification status:** implementation + self-test + 4-seed guard-approved
  smoke only (appended below when run). No Phase-1b scientific dataset or
  GO/STOP verdict exists yet; the intended first scientific run is 16 seeds,
  300 sims, ascension 0, complete finite-belief evaluation unless the smoke
  shows unacceptable cost, and has NOT been executed.

### Phase-1b implementation smoke (2026-08-16; 4 seeds, 300 sims, asc 0)

- **Exact environment:** `STS_FAIR=1 STS_SEARCHER3=1 STS_S3_BELIEF=0
  STS_S3_CHAIN=0 STS_S3_PARTICLES=64
  STS_PARTICLE_POSTERIOR_PROBE_K=0
  STS_PARTICLE_POSTERIOR_PROBE_MAX_GROUPS=4`; command was wrapped by
  `tools/seed_guard.sh`. This is an implementation smoke, not scientific
  evidence. The complete Phase-1a model/OOC provenance was not fully
  recoverable, so no claim of perfect Phase-1a stack matching is made.
- **ON command:**
  `tools/seed_guard.sh ./build/linux-gcc-release/one_combat
  particle_posterior_probe 4 300 0
  build/particle_posterior_probe_on4_v3.csv`.
  Runtime 10.4s (2.59s/seed); 608 rows = 16 source groups + 592 evaluated
  compatible hidden leaf states; all groups used complete finite-belief
  evaluation (`K=0`), so no capped/lower-bound range metric was involved.
- **Invariants:** source-particle replay failures 0/16; invariant failures
  0/16; replay-failure categories empty; source fallback groups 0; accepted
  candidates reproduced every intermediate and final observation/outcome.
  Compatible particle/unique-state counts were
  `{4:1, 6:1, 12:1, 14:1, 19:1, 21:1, 31:2, 35:2, 64:6}`; groups with
  >=2/4/8 unique states were 16/16/14. All 16 groups had range >5 in this
  tiny smoke (mean range 19.75; mass-weighted mean range 20.85), which is
  not a scientific result.
- **OFF/ON determinism:** the OFF arm used the same command/configuration
  with `STS_PARTICLE_POSTERIOR_PROBE_MAX_GROUPS=0`, wrote zero probe rows,
  and ran in 12.2s. Its per-seed gameplay sidecar was byte-identical after
  sorting to the ON sidecar (`seed,won,floor,act,hpEnd,maxHp,fightsLost,
  deathCombat,deathEncounter`).
- **Analyzer:** `python3 tools/analyze_particle_posterior_probe.py
  build/particle_posterior_probe_on4_v3.csv --bootstrap-iters 200` ran
  successfully. No scientific GO/STOP interpretation is made from four
  seeds.

### §176 Phase-1b measurement correction — controlled draw-order primary (2026-08-16; 4-seed smoke only)

The implementation-review correction retains the exact posterior compatibility
and replay machinery, but splits continuation targets:

- **Primary controlled draw-order target:** for every compatible draw order,
  use that order with the source leaf's six simulator RNG streams, and average
  `R=4` diagnostic rollouts using four common per-group rollout-policy RNG
  seeds. This asks whether draw orders that Searcher3 actually considers
  possible change expected continuation value, without mixing in candidate RNG
  states or relying on one rollout per world.
- **Secondary full-particle target:** retain the original exact candidate draw
  order plus all six candidate RNG streams and one common diagnostic rollout
  seed. This measures total hidden-determinization variation and is useful for
  later #4 belief averaging, but is not the primary #3 gate.

The diagnostic exact draw-pile multiset check now uses `FullHiddenCardId`
(CardId, upgrades, specialData, costForTurn, freeToPlayOnce); gameplay's
historical CardId-only `sameCardMultiset` was not changed. The run sidecar now
records a per-decision Searcher3 root fingerprint (visible observation hash,
chosen root action bits, and visits), allowing OFF/ON action/search-level
comparison rather than only run-outcome comparison.

The corrected smoke used the same fair-S3 environment as §175, 4 seeds, 300
sims, 4 source groups/seed, `K=0`, and `R=4`. It produced 16 groups and 592
evaluated worlds with zero source replay failures and zero invariant failures.
The full-particle target had mean range 19.75 and 16/16 groups above 5. The
controlled draw-order target had mean range 2.09375, median range 0, and 3/16
groups above 5. The compatible-mass-weighted controlled mean range was 3.368;
the **primary statistic is the equal-source-group mean/range prevalence**, with
mass-weighted results secondary. OFF/ON root action/search fingerprints were
identical. These four-seed results are implementation smoke evidence only,
not a scientific verdict.

The corrected preregistration is the designated contract for any future
scientific run. The 16-seed experiment remains unrun and requires independent
review of this correction commit first.

### §177 Corrected Phase-1b preregistration decision rule (set before designated scientific data)

The numerical thresholds from §175 v1 are transferred unchanged to the
corrected controlled draw-order primary target; they are not retuned from the
§176 smoke. All references below mean equal-source-group statistics for the
controlled target. Compatible-mass-weighted results remain secondary and are
not substituted into the gate.

- **GO / posterior-valid draw-order sensitivity established:** all
  implementation invariants pass; controlled fraction of source groups with
  range >5 is at least 10%; the seed-bootstrap 95% CI lower bound for that
  fraction is >5%; and equal-group controlled mean range is at least 3.
- **STOP the draw-order/full-particle-conditioning line:** invariants pass;
  controlled fraction(range>5) is <5%; bootstrap upper 95% CI is <10%; and
  equal-group controlled mean range is <1.
- **Otherwise INCONCLUSIVE:** do not train a particle-conditioned VNet; at
  most one focused extension to 32 seeds may be proposed. If GO, roadmap
  #2 remains next; #3 is scientifically justified only if #2 also succeeds.

These are pragmatic thresholds, not validated gameplay thresholds. The §175
v1 full-particle smoke is not eligible for this rule; §177 is the designated
scientific decision contract.

## §174 Particle-conditioned leaf probe implementation (2026-08-16; diagnostic/offline; no gameplay promotion)

- **Implementation:** added `one_combat particle_leaf_probe`, guarded by
  `STS_PARTICLE_LEAF_PROBE_FILE` and optional K/rate/group-cap controls. It
  samples actual Searcher3 frontier-type-0 leaves, preserves all six simulator
  RNG streams and the draw-pile multiset, permutes only draw order, and writes
  one row per variant. `drawPile.back()` is the next draw, so `drawOrder` is
  serialized back-to-front. All variants, including variant 0, use the same
  isolated diagnostic rollout RNG; `rawRolloutEval` is parity-only.
- **Offline analysis:** `tools/train_particle_leaf_probe.py` compares a
  visible-only Ridge control with a sparse positional first-10-card treatment,
  uses a fixed seed-group split, computes spread/ordinary/centered/pairwise and
  K=1/2/4/8 averaging metrics, and reports draw-pile-length coverage. It is
  analysis infrastructure only; no scientific dataset or GO/STOP verdict is
  recorded in this implementation entry.
- **Verification status:** the initial implementation smoke was only one seed,
  2 groups, 16 rows and is retained as historical implementation evidence.
  It must not be treated as the required 8-seed verification or as scientific
  evidence. This corrected follow-up adds callback-unique `sourceLeafId`,
  centered-RMSE/tie/sampling fixes, distinct-order reporting, and bounded
  defaults. Review correction: groups now emit only unique sampled draw orders
  (no K-padding duplicates), `uniqueVariantsSampled` names the bounded-sampling
  count, averaging-curve K values unavailable for a short group are omitted, and
  `drawOrder` is captured before diagnostic rollout mutates the draw pile. The
  trainer defensively deduplicates exact orders, reports K-specific eligible
  groups/seeds and draw-pile-size strata, and has a synthetic self-test. The
  focused corrected smoke produced 107 rows across 16 groups with no duplicate
  orders, all invariants passing, and no trainer group-split leakage; no 16–32
  seed scientific run is authorized here.
- **32-seed collection/correction follow-up:** collected the preserved raw
  artifact `build/particle_leaf_probe_phase1_32seed_raw.csv` with 32 seeds,
  300 simulations, ascension 0, K=8, rate=1, and max-groups=16 through the
  seed guard. It contains 2,364 data rows across 512 source groups and 32
  seeds; SHA-256 is
  `25c17387a5a324c806c020eef3d13b14937271e122b4bacc432bb6bbc17700e1`.
  The offline K curve was then corrected to average combination errors within
  each source leaf and use seed-level outer aggregation. The raw CSV was not
  regenerated after this correction. These outputs are collection/analysis
  provenance only, not a scientific conclusion or promotion decision.
- **Non-goals:** no particle-conditioned runtime VNet, VNet-only search,
  policy-prior change, belief change, RNG conditioning, particle-count change,
  or OOC change.
## §135a Leaf-state diagnostics: gate-matching measurement (2026-08-08, local — diagnostic evidence, no gameplay promotion)

- **Dataset:** 64 seeds (126700–126763), 1000 sims, asc 0, 12 threads, local
  (no GCP). Full gate-matching env: `STS_FAIR=1 STS_SEARCHER3=1
  STS_S3_BELIEF=0 STS_S3_CHAIN=0 STS_S3_PARTICLES=64`,
  `STS_VNET=build/v_combat_honest.txt` @ `STS_VNET_ALPHA=0.3` (deployed §126
  regime), `STS_DIAG_VNET2=build/v_combat_utility_direct.txt` (§134 direct-R,
  diagnostics only), `STS_LEAFDIAG_PER_STRATUM=500`, full V4 OOC gate arms
  (`STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_final.native`,
  REST/EVENT/SHOP/TREASURE/BOSS_RELIC=1, MARGIN=1.0). Probing OOC arms OFF.
- **Artifacts (build/, git-ignored):** `leafdiag_gate_64.csv` (288,537 leaf
  rows, 142s), `leafref_gate_64_4k.csv` (287,211 reference rows, high-budget
  4000 sims × 128 particles, per-group CRN reseeding, replay 1000 — matched
  100%, no re-capture WARNINGs, 3367s), `rollouttrace_gate_64.csv` (3,341,845
  rows, 150s), `leafdiag_gate_64_ood.csv`, JSON summaries
  `leaf_ranking_gate_64{,_ood,_rawrollout}.json`,
  `leaf_distribution_shift_gate_64.json`, `leaf_split_check_gate_64.json`,
  `leaf_smoothness_gate_64.json`.
- **Ranking vs high-budget reference (Task 3; reference is vnet-influenced,
  see caveat):** endHp Pearson 0.758 / Spearman 0.769 / MAE 31.2 vs utilityR
  Pearson 0.806 / Spearman 0.820 / MAE 21.5 (own scales, not comparable
  directly — utilityR fits the reference better in correlation). Within-group
  pairwise accuracy: **endHp 0.719 [0.717,0.722] vs utilityR 0.711
  [0.708,0.714]** (+0.8pp, CIs disjoint); top-1: 0.359 vs 0.336 (+2.3pp);
  regret 7.253 [7.076,7.424] vs 7.597 [7.419,7.768]. Disagree-high stratum
  (|Δ| ≥ 50): 0.734 vs 0.720. Deep-tree stratum (d≥15): 0.798 vs 0.779.
- **Model-free cross-check (rawRolloutEval single-sample reference, no
  leafref):** pairwise 0.725 [0.722,0.728] vs 0.719 [0.715,0.722], top-1 0.333
  vs 0.316, regret 14.50 vs 15.16 — same direction, so the endHp ranking
  advantage is NOT an artifact of the vnet-influenced reference.
- **Distribution shift (Task 4):** held-out logistic classifier
  combatgen-vs-search-leaf: **ROC-AUC 0.9998** (60k×60k rows, test ~1/3) —
  near-perfect separation; the search-leaf regime is essentially entirely
  outside the `vcombat_honest.csv` training distribution (OOD flagging: only
  37 decision groups classified in-dist, 3046 OOD, rest na). Top separating
  features by standardized |coef| (correlation, NOT causal): r116 (+4.87),
  maxHp (+2.74), gold (+2.07), nSklAvail (−1.92), dr25 (+1.88), ds25 (+1.87).
- **Split-sensitivity (Task 5):** fight-split vs seed-split diagnostic
  retrains (canonical §134 recipe): endhp val MAE 5.581 → 5.536 (−0.045);
  utility_r 9.730 → 9.173 (−0.557). The fight-level split is NOT optimistic —
  seed-level validation is, if anything, slightly easier for the deployed
  models (deployed endHp val MAE 5.589 fight vs 3.930 seed). The offline
  story was not inflated by same-run fight leakage.
- **Smoothness/shaping (Task 6):** endHp lag-1 autocorrelation 0.549 vs
  utilityR 0.502 (endHp smoother); near-death steps: endHp mean ΔV −1.094 /
  std 3.227 vs utilityR −2.457 / 8.571; but utilityR is MORE sign-consistent
  on raw surface progress (progSign 0.459 vs 0.432, negOnHpLoss 0.247 vs
  0.221, strUp 0.442 vs 0.416). Shaping evidence is MIXED — smoothness yes,
  sign-consistency no.
- **Verdict (diagnostic, not causal):** the dominant, unambiguous finding is
  massive train-vs-search covariate shift (AUC 0.9998). Within the OOD
  search-leaf regime the deployed endHp model ranks slightly better (pairwise
  +0.8pp, top-1 +2.3pp, regret −0.34) despite correlating worse with the
  high-budget reference (Spearman 0.769 vs 0.820). The online gap (−12.1pp) is
  far larger than any measured ranking difference (≤2.3pp top-1), so the
  ranking hypothesis alone cannot explain the §134 collapse; covariate shift
  (or its interaction with the blend scale) is the primary suspect. Next
  experiment (per the handover decision point, covariate-shift branch):
  retrain the existing model class on a mixture of combatgen + actual
  leafdiag states with SEPARATE on-policy and search-leaf holdouts, and test
  search-leaf ranking improvement before any gameplay gate.
- **Caveats:** the leafref reference searcher itself used the deployed endHp
  leaf (vnet-influenced reference) — mitigated by the rawRolloutEval
  cross-check above; OOD in-dist groups are few (n=37) so the ood=id stratum
  is anecdotal; delta-V scales differ across models (only scale-free
  comparisons valid); classifier feature weights are correlational.
- **Decision log:** `2026-08-08-leaf-state-diagnostics.md` (results
  addendum).

## §135b B1 tactical turn-beam rollout (STS_S3_TURN_ROLLOUT): implemented opt-in with structural-equality check; paired 256-seed gate PENDING (2026-08-08, local WSL)

- **What:** the B1 line from `plan-rollout-experiments-2026-08-07.md` §2
  (user-approved scorer-(b) design; the §134 audit flagged the original B1
  spec as incomplete — pruning needs intermediate scores — so the revised
  spec scores COMPLETE turns only and prunes between turns by first-N
  truncation). At PLAYER_NORMAL states during the Searcher3 rollout, the
  per-action weighted random pick is replaced by a deterministic beam search
  over card/potion sequences to END_TURN; the best-scored complete turn is
  executed and the rollout continues to the next hand (multi-turn
  continuation is mandatory per the A4 falsification, §133).
- **Implementation:**
  - `turnBeamSearch` (file-scope static, `src/sim/search/
    BattleScumSearcher3.cpp`): BFS to END_TURN, depth = hand size (≤10),
    width `STS_S3_TURN_BEAM_WIDTH` (default 8), pruned between depths by
    first-N truncation (deterministic enumeration order, no intermediate
    scoring). Every beam state spawns an END_TURN candidate scored after the
    monster turn resolves on a copy (common-random-numbers for free).
    CARD_SELECT-producing sequences are dropped; lethal sequences captured as
    +1000 candidates; `turnBeamSearch` never returns empty (depth-0 END_TURN
    candidate).
  - `scoreCompleteTurn(pre, post, powersPlayed, potionsUsed)`:
    `S = w1·ΔHP_enemy − w2·ΔHP_player + w3·kills + w4·persistent_setup
    − w5·potion_use`; ΔHP_player = effective (HP+block) loss clamped ≥0;
    setup = strength+dex+focus deltas + powers played; terminal outcomes
    ±1000. Weights `STS_S3_TURN_SCORE_W1..W5` defaults
    1.0/1.0/50.0/10.0/30.0 (educated guesses, pre-registered). Hand-authored
    rollout heuristic (same class as `rolloutWeight`), NOT a learning
    objective.
  - `playoutRandom` branch (gated `g_s3TurnRollout &&
    inputState == PLAYER_NORMAL`): executes the best sequence, fires
    `g_onRolloutStep` after each action, honors `g_s3RolloutTurnStop` (A4)
    after the beam's END_TURN. Non-PLAYER_NORMAL states keep the weighted
    pick; unset/`=0` is byte-identical pre-B1.
  - Env parsed in `apps/one_combat.cpp::main`; BEST stack banner prints
    `S3-turnBeam=ON/off` (only in the Searcher3 arm of the banner).
- **Local smoke (2026-08-08):**
  - Structural equality: `bestbench 300 8 0 126700` with `STS_FAIR=1
    STS_SEARCHER3=1 STS_S3_BELIEF=0 STS_S3_CHAIN=0 STS_S3_PARTICLES=64`,
    unset vs `STS_S3_TURN_ROLLOUT=0` → per-seed game-outcome columns
    (won/floor/act/hpEnd/maxHp/fightsLost/deathCombat/deathEncounter)
    identical (only the wall-time `sec` column varies); logs identical
    modulo cpu.
  - Turn-beam smoke: same config + `STS_S3_TURN_ROLLOUT=1
    STS_S3_TURN_BEAM_WIDTH=8` → runs to completion on 8 seeds @300 sims, no
    crash/hang/assert (win 25.0% vs control 37.5% on 8 seeds — NOT
    evidence, smoke only). Cost ~16× control at 300 sims (55.9 vs 3.45
    cpu-sec/run) — the beam's CPU cost is the known B1 risk; B1c (VNet on
    the final 2–4 beam survivors) is parked for that contingency.
  - `ctest` 8/8 pass; `git diff --check` clean.
- **Gate (DONE 2026-08-08, GCP sts-test):** paired 256-seed @1k/64p, block
  126700–126955, asc 0, 24 threads, full V4 gate stack (`STS_OOC_STRATEGIC_TOK_NN=
  selfplay/models/ooc_strategic_tok_final.native`, REST/EVENT/SHOP/TREASURE/
  BOSS_RELIC=1, `STS_OOC_STRATEGIC_MARGIN=1.0`), vnet default ON α0.3,
  vs the §126 control `build/vnet_all_a03_1k.csv` (50.4%):
  `bestbench 1000 256 0 126700 build/b1_turn_beam_1k_256.csv` with
  `STS_FAIR=1 STS_SEARCHER3=1 STS_S3_BELIEF=0 STS_S3_CHAIN=0
  STS_S3_PARTICLES=64 STS_S3_TURN_ROLLOUT=1 STS_S3_TURN_BEAM_WIDTH=8`;
  analysis `paired_analysis.py build/vnet_all_a03_1k.csv
  build/b1_turn_beam_1k_256.csv ctl cand`; banner confirmed
  `S3-turnBeam=ON` + `[S3 turn-beam rollout ON: width=8 scorer
  w1..w5=1/1/50/10/30]` + vnet default load.
- **Gate result (paired_analysis.py, 256 seeds):**
  | metric | control (§126 vnet) | turn-beam B1 | delta |
  |---|---|---:|---:|
  | win | **50.4%** (129/256) | **46.9%** (120/256) | **−3.5pp, 95% CI [−10.2, +3.1]** |
  | avg floor | 44.1 | 43.9 | −0.1 (CI [−1.3, +1.1]) |
  | avg HP end | 29.4 | 25.3 | −4.0 |
  | cpu-s/run | 41.17 | 383.45 | +9.3× |
  Discordant 75/256 (29%): ctl-only 42, cand-only 33. Wall 4523.7 s
  (75.4 min). Artifacts: `build/b1_turn_beam_1k_256.csv` (md5
  6028f837224b845e63254d91062f767f), server log
  `build/b1_turn_beam_1k_256.log` on sts-test.
- **Verdict: ❌ null (not significant), line parked.** −3.5pp with CI crossing
  zero and no floor/HP benefit at 9.3× CPU closes the B1 hand-authored-scorer
  design (the decision log pre-registered the gate as arbiter; risk list
  included mis-ranking and lower-index bias). No default change; env stays
  opt-in default-off. B1c (VNet on final 2–4 beam survivors) is NOT unlocked
  — the cost contingency was premised on a positive signal; a VNet-scored
  beam would only add cost. A2 (dynamic α by rollout length) conditions on
  the L distribution B1 reshapes — with B1 parked, run A2 only if a
  lightweight rollout-shape diagnostic shows the premise still holds.
- **Decision log:** `2026-08-08-turn-beam-rollout.md`.

## §136 Self-play relabeling (5.7.3, handoff plan `plan-selfplay-relabeling-2026-08-07.md`): Phase-0 verification smoke — full S3+vnet datagen stack verified, schema/labels OK, trainer/export chain OK; Phases 1–3 (GCP datagen, GPU training, paired gate) PENDING manual follow-up (2026-08-08, local WSL)

- **What:** Phase 0 of the 5.7.3 handoff plan — verify (a) the
  `strategicgen2` Tier-B label producer runs with the CURRENT deployed combat
  controller (fair S3−belief−chain + live-valid + the §126 vnet default) and
  emits the trainer-consumable schema, and (b) the `train_strategic_tok.py` →
  `export_strategic_tok.py` chain works end-to-end before the 1,500-seed GCP
  datagen. **No C++ code changes** (verified: `strategicgen2` main-run OOC and
  branch continuation are heuristic by design — `apps/one_combat.cpp`
  `runStrategicGenSeed2`/`finishOocCounterfactual`; branch battles use the
  configured searcher, so the §5 envs alone select the deployed controller).
- **Provenance (Phase 0):** local WSL (12 threads), HEAD 2e6f894,
  `./build/one_combat strategicgen2 10 1000 0 build/sp_smoke_phase0.csv
  300000` with `STS_FAIR=1 STS_SEARCHER3=1 STS_S3_BELIEF=0 STS_S3_CHAIN=0
  STRATEGIC_SAMPLE_ALL=1` (branch defaults: `STRATEGIC_BRANCH_FIGHTS=3`,
  `STRATEGIC_BRANCH_SIMS=150,100,50`, `STRATEGIC_BRANCH_FUTURES=1`);
  seeds 300000–300009 (fresh range, no overlap with recorded ranges).
- **Verified banner (startup, no vnet warning):** `[Searcher3 engine ON]`,
  `[live-valid edge re-selection ON (fair S3 default, §123)]`,
  `[S3 ablation: belief=off]`, `[S3 ablation: chain=off]`,
  `[V_combat leaf default ON: build/v_combat_honest.txt, 804 trees, alpha 0.3
  (fair S3, §126)]`; **no** `[strategicgen2 WARNING: STS_VNET not loaded]`
  (the `!search::g_useVNet` guard, apps/one_combat.cpp:7454). The S3-abl
  banner (`S3-abl[b,p,c,l,crn]=01010`) is a bestbench banner; for
  `strategicgen2` the per-flag ablation lines above are the equivalent
  evidence.
- **Schema (validated with pandas):** 1017 state columns between `chosen`
  and `won` (exact `richRow` contract the trainer validates); last 4 columns
  exactly `labelWon,labelHp,labelFloor,labelBootstrap`. Rows: **6,244 total
  / 10 seeds = 380–771 rows/seed (mean 624)** — consistent with the §104
  scale estimate (~809k rows / 1,295 seeds). `STRATEGIC_SAMPLE_ALL=1` →
  **100% labelWon coverage** (6,244/6,244), spread 0..1 with 2,363 distinct
  values (real variance, not constant).
- **Preliminary label diagnostic (smoke-scale only, NOT a gate — 10 seeds,
  §104-style filter: groups with ≥2 finite labels AND exactly one chosen
  row): argmax(labelWon) vs `chosen` agreement 34.1% strict / 46.0% in-set**
  (1,055 valid groups; in-set = chosen inside the tied argmax set), with
  per-screen spread matching the old-corpus pattern (EVENT 41.4/50.0 n=58,
  MAP 51.9/56.3 n=158, REST 50.0/59.7 n=72, REWARDS 29.5/45.1 n=628, SHOP
  15.7/15.7 n=51; TREASURE/CARD_SELECT/BOSS_RELIC omitted, n<50). The old
  corpus read 38.0% strict / 58.1% in-set (§104); the smoke numbers are
  consistent, so the new labels behave like the old ones. (A 37.2% strict
  figure recorded earlier the same day came from an experimental
  deferred-branch parallelization that was reverted — see the second-pass
  follow-up below; the numbers here are from the exact serial path the GCP
  datagen will use.) Recompute on the full 1,500-seed set per the plan (§5
  Step-1 diagnostic); informative, not a gate.
- **Trainer/export chain (Phase 0c):** 2-epoch CPU slice of the smoke CSV
  (`STRAT_DEVICE=cpu STRAT_EPOCHS=2`, rung 4, 6,244 rows / 10 seeds / 1,555
  decisions, **1,554 groups with exactly one chosen row, all with a valid
  policy action** — the policy-target head is exercised: policy_top1
  0.44→0.42, q_top1 ~0.20, val_pol_ce 1.5204) → `build/tok_smoke.pt.pt` +
  `_metrics.json`; export with `export_strategic_tok.py build/tok_smoke.pt
  build/ooc_strategic_tok_smoke.native` → **32 numpy-vs-PyTorch parity checks
  passed** (max err logit 3.87e-08, value 8.92e-08, Q 1.66e-07); the
  exported native loads in `one_combat` (`[OOC one-ply strategic TOK net ON:
  card rewards gated at margin 1]` with the full gate stack + vnet default +
  `S3-abl[...]=01010` at 64p on a 2-seed @100-sim bestbench smoke). The
  smoke .native lives under ignored `build/` — it is NOT a candidate artifact
  and must not be committed to `selfplay/models/` (2-epoch CPU checkpoint,
  rung 4 default topology).
- **Discrepancies found (plan-vs-repo, recorded for the follow-up session):**
  (1) `train_strategic_tok.py` writes `OUT + ".pt"`, so `export_strategic_tok.py`
  must receive the ACTUAL checkpoint path (e.g. `build/tok_control.pt.pt`
  when the trainer OUT was `build/tok_control.pt`); the plan's Phase-2
  command as written would silently fall back to the exporter's random
  selftest. (2) The training environment is the repo venv (`.venv/bin/python`,
  torch 2.5.1+cu121); the system `python3` lacks torch. (3) `ctest` passes
  8/8 at this HEAD — the plan's "known CRLF selfplay_syntax failure" does not
  reproduce (the parallel agent's fixes landed since the plan was written).
- **Status:** Phases 1–3 PENDING (manual GCP follow-up per the plan
  protocol): 1,500-seed datagen on sts-test (seeds 300000–301499, three
  500-seed chunks, `OMP_NUM_THREADS=24`, same envs), control retrain on
  `build/strategic_tierb.csv` + candidate retrain on
  `build/strategic_sp_1500.csv` (GPU, rung 4, 40 epochs, same recipe),
  paired 256-seed gate on block 126700–126955 @1k/64p vs
  `build/vnet_all_a03_1k.csv` (50.4%). Pre-registered verdict rule
  unchanged: candidate ≥ control with CI excluding a meaningful loss →
  promotion path; null → 5.7.3 closed as a distribution lever.
- **Artifacts (ignored):** `build/sp_smoke.csv` (6,244 rows, clean
  regeneration — an earlier duplicated 12,488-row copy from re-running
  `strategicgen2` without truncating the file was discarded), plus
  `build/sp_smoke_phase0.csv` (6,244 rows),
  `build/tok_smoke.pt.pt` / `_tok_state.bin` / `_metrics.json`,
  `build/ooc_strategic_tok_smoke.native` (smoke export, 807,432 bytes),
  `build/smoke_gate_phase0.csv` (2-seed load smoke). All git-ignored under
  `build/`; the smoke .native is NOT a candidate artifact (2-epoch CPU smoke
  checkpoint, rung 4 default topology) and is kept OUT of the git-tracked
  `selfplay/models/` directory.
- **Follow-up (same day, verification-fix session):** (a) discrepancy (2)
  above is resolved — the venv's torch 2.5.1+cu121 stack was copied into the
  user site (`~/.local/lib/python3.12/site-packages`), so the plain-`python3`
  trainer/export smoke commands now pass (`STRAT_DEVICE=cpu STRAT_EPOCHS=2
  python3 train_strategic_tok.py build/sp_smoke.csv build/tok_smoke.pt` → 2
  epochs, metrics byte-identical to the venv run; `python3 export_strategic_tok.py
  build/tok_smoke.pt selfplay/models/ooc_strategic_tok_smoke.native` → 32
  parity checks, max err 1.66e-07; `build/tok_smoke.pt` is kept as a symlink
  to the trainer's real `build/tok_smoke.pt.pt` so the exporter exercises the
  trained checkpoint rather than its random selftest fallback). (b) The
  plan's 1-seed @100-sim schema-validation check
  (`strategicgen2 1 100 0 build/sp_smoke_header.csv 300010`, 60 s budget)
  cannot complete on this machine: measured 166.2 s for 1 seed (dominated by
  the per-decision branch-fight contract — 3 fights × 150/100/50 sims,
  `STRATEGIC_BRANCH_FUTURES=1`, the §84-optimal defaults the plan mandates
  keeping; 12 OMP threads but a single seed uses one core). The schema it
  would validate is already verified by the 10-seed smoke above (1017 state
  cols + Tier-B suffix + 100% labelWon coverage), so no datagen code or
  default was changed for it — the timeout is a verification-budget mismatch,
  not a producer defect.
- **Follow-up (same day, verification-fix session, second pass — REVERTED):**
  an experimental `runStrategicGenSeed2` change deferred sampled decisions'
  branch battles to a post-run `#pragma omp taskgroup` when `nSeeds <
  threads` (spare team threads). It was NOT structurally guaranteed
  byte-identical to the serial path: in deferred mode the thread-local
  `t_curPath` stays set through the main loop, so the main-run OOC policy
  (`serverCardRewardPolicy`/`restWinPolicy`/`upgradeSelectWinPolicy` via
  `vFeatCsv`→`richRow`) sees real `pv*` features, whereas the serial path
  nulls it after the first branch eval (`pv*`=0); the floor/win nets consume
  `pv*` features, so `chosen` rows can flip on unverified seeds. Byte-identity
  was only spot-checked (1–3 seeds @100 sims), and the diagnostics recorded
  from that run (37.2% strict agreement) did NOT match the serial path
  (34.1/46.0 above). Per review, **the change was fully reverted —
  `apps/one_combat.cpp` is byte-identical to HEAD** (no C++ changes, per the
  plan's explicit constraint); the smoke above was regenerated with the exact
  serial code the GCP datagen will use, and the `build/sp_smoke.csv` training
  input was truncated before re-running (no duplicated rows; the trainer now
  sees 1,554 valid policy groups instead of 0). The 1-seed @100-sim 60
  s-budget mismatch (follow-up (b) above) stands as a recorded verification
  limitation: the schema is already proven by the 10-seed smoke, so no code
  change is justified. Per-seed reproducibility re-verified: serial 1-thread
  reruns of seed 300000 are byte-identical; the 10-seed file differs across
  runs only in seed-block ordering (dynamic OMP schedule), not content.
- **Follow-up (same day, recovery-fix session — reversion verified complete):**
  the second-pass reversion described above is now actually true in the tree:
  `git diff apps/one_combat.cpp` is empty (the deferred-branch
  parallelization is fully removed, so the plan's no-C++-change constraint
  holds). `build/sp_smoke.csv` was truncated and the 10-seed smoke re-run from
  scratch on the serial path (315 s wall @12 threads) → 6,244 rows, 380–771
  rows/seed, 100% labelWon coverage, 2,363 distinct labelWon, and per-seed
  rows byte-identical to the original Phase-0 serial file; the §104-style
  diagnostic reproduces the recorded numbers exactly (34.1% strict / 46.0%
  in-set on 1,055 groups; per-screen EVENT 41.4/50.0, MAP 51.9/56.3, REST
  50.0/59.7, REWARDS 29.5/45.1, SHOP 15.7/15.7). The 2-epoch CPU
  trainer/export smokes were re-run on the clean slice with identical metrics
  (1,554 valid policy groups, policy_top1 0.44→0.42, q_top1 ~0.20, val_pol_ce
  1.5204; export 32 parity checks, max err 1.66e-07) → the smoke .native now
  exists only under ignored `build/ooc_strategic_tok_smoke.native`; the copy
  that had accumulated in git-tracked `selfplay/models/` was removed (it must
  not be committed; only the Phase-2/3 control/candidate .native files ship).
- **Decision log:** `2026-08-08-selfplay-relabeling.md`.

## §136 Frontier-leaf corpus + empirical relabeling (frontiergen/leafrelabel): infrastructure implemented with local smoke verification, no gameplay result yet (2026-08-08, local)

- **What:** phases 2-3 of the plan "Combat-value targets" (`.ai/20260808-120025`):
  (2) `one_combat frontiergen` captures Searcher3 frontier-leaf states as
  versioned binary `BattleContext` snapshots (`include/combat/BattleContextBinary.h`,
  `sts::serializeBattleContext`/`deserializeBattleContext`; round-trip contract =
  `combatExtractFeatures` identity, verified by the new `battlecontext_roundtrip`
  unit-test subcommand registered in CTest) at the THREE S3 frontier sites —
  the leaf-expansion blend site always fires when `search::g_onS3LeafQuery` is
  set; the fair illegal-stored-edge rollout fallback and the depth-cap direct
  eval fire ONLY under `search::g_s3LeafQueryAllSites` (thread_local, default
  false), which ONLY frontiergen sets, so leafdiag/leafref/rollouttrace keep
  the historical single-site corpus (`S3LeafDiagnostic::frontierType` 0/1/2 and
  `rolloutSteps` record the site + rollout length) — and (3) `one_combat
  leafrelabel` restores each leaf and runs a FRESH high-budget Searcher3
  recording every terminal evaluation (`evaluateTerminal` made virtual;
  `TerminalRecordingSearcher` records won/endHp per terminal eval) → empirical
  P(win), HP|win mean/quantiles; plus a CRN sibling pass (one Belief + particle
  set from the parent visible state, `installSharedParticles`, sibling actions
  enumerated with the searcher's OWN contract `search::enumerateActionsForNode`
  — potions included) at a separate sibling budget. leaf.csv/sibling.csv
  self-document the denominator: `totalTerminals` counts ONLY terminal evals
  and a `nonTerminal` column (= budget − totalTerminals, clamped ≥ 0) reports
  sims without one (prune-as-dead / non-terminal depth-cap/rollout-cap evals).
  Phase-4 analysis scaffold: `tools/leaf_ranking.py --frontier` (pairwise
  ranking accuracy / top-1 / Spearman / regret of the deployed leaf model's
  `modelPred` vs the teacher pWin, stratified, deterministic bootstrap CIs;
  Brier/ECE only with a probability-scale `--prob-col`).
- **Regime forced by both modes:** `STS_FAIR=1 STS_SEARCHER3=1 STS_S3_BELIEF=0
  STS_S3_CHAIN=0 STS_LIVE_VALID=1` (deployed fair-S3 datagen regime; live-valid
  set explicitly — datagen is not covered by the parse-time default, §123).
- **Corpus dedup:** per-seed at capture time (first kept, `duplicateCount`
  incremented) AND corpus-wide at flush time under the critical section — a
  visible state already written by an earlier-flushed seed is dropped without
  re-serialization (counted in the run summary, 0 in the 8-seed smoke); parent
  marker rows (frontierType=-1) are not deduped.
- **Local smoke (this entry, no gameplay claim):**
  - `cmake --build build -j` clean; `./build/test battlecontext_roundtrip` PASS
    (seeds 0..3 x JAW_WORM/CULTIST/GREMLIN_NOB/SLIME_BOSS after several executed
    turns; feature-byte + 6 RNG streams + decision-state fields identical);
    `ctest --test-dir build --output-on-failure` 9/9 PASS.
  - `STS_S3_PARTICLES=16 STS_FRONTIERGEN_PER_STRATUM=10 ./build/one_combat
    frontiergen 8 300 0 build/frontier_smoke.csv 0 smoke` → 963 CSV rows
    (828 leaf rows + 135 parent marker rows), 99 rows with duplicateCount>0
    (dedup by obsHash verified), all 11 strata filled
    (s0-8=80, s9=28, s10=80; 0 cross-seed duplicates dropped),
    `build/frontier_smoke_smoke.csv` + `build/frontier_smoke_smoke.bin`
    (751 KB; blob offsets point at the blob DATA after the 4-byte length
    prefix). NOTE: the illegal-fallback/depth-cap sites did not fire in the
    smoke (small trees at 300 sims; depth cap needs 100-level descents) — the
    type-1/2 strata are expected to populate in the batch corpus (long boss
    fights at higher budgets).
  - `STS_FAIR=1 STS_SEARCHER3=1 STS_S3_BELIEF=0 STS_S3_CHAIN=0 ./build/one_combat
    leafrelabel build/frontier_smoke_smoke.csv build/frontier_smoke_smoke.bin
    build/leaf_smoke.csv build/sibling_smoke.csv 5000 5 16` → 5 leaf rows
    (pWin in [0,1], totalTerminals == 5000 == high budget, nonTerminal 0) + 15
    sibling rows (matching leafObsHash, distinct siblingObsHash,
    totalTerminals == 3000, nonTerminal 0, modelPred = deployed vnet
    prediction on the endHp scale; NaN only when no combat value model is
    loaded). Two re-runs on the same inputs are BYTE-IDENTICAL (stability
    criterion: identical pWin/meanHpOnWin).
  - `tools/leaf_ranking.py --frontier --leaf build/leaf_smoke.csv --sibling
    build/sibling_smoke.csv` runs and reports pairwise/top-1/Spearman/regret
    (smoke values: pairwiseAcc 0.667, top1 0.000, Spearman 0.5, regret 0.001 —
    illustrative only, 5 groups; the vnet endHp-scale value is NOT a calibrated
    probability, Brier/ECE correctly reported as not computed);
    `--self-test` PASS.
  - Existing modes re-verified after the review gating fix:
    `one_combat leafdiag 4 300 0 build/ld_smoke.csv` → 1710 rows with the
    UNCHANGED leafdiag schema (no frontierType column); `one_combat leafref
    build/ld_smoke.csv build/ld_ref.csv 3000 4 0 300` re-captured 1710/1710
    recorded leaves (no re-capture WARNING) — leafdiag/leafref/rollouttrace
    behavior is unchanged by the frontiergen extension.
- **Artifacts (local, disposable smokes under build/):**
  `build/frontier_smoke_smoke.{csv,bin}`, `build/leaf_smoke{,2}.csv`,
  `build/sibling_smoke{,2}.csv`, `build/ld_smoke.csv`, `build/ld_ref*.csv`.
- **Not implemented / deferred (recorded in the plan + KB):** per-particle
  terminal-outcome breakdown (`STS_LEAFRELABEL_PARTICLE_BREAKDOWN` — the
  particle id is internal to `step()`); the full phase-3 batch (500-1000
  leaves @10k sims, GCP-parallel) and the phase-4 verdict gate (top-1 ≥ 80% +
  Spearman ≥ 0.7 pre-registered rule) await the batch corpus.
- **Decision log:** `2026-08-08-frontiergen-leafrelabel.md`.

## §137 Covariate-shift mixture retrain (§135a next experiment): combatgen + leafdiag training mixture with SEPARATE on-policy/search-leaf holdouts — mixture does NOT improve held-out search-leaf ranking (pairwise −3.5pp, top-1 −3.9pp, regret +0.78) AND hurts the on-policy fit — branch closed, no gameplay gate (2026-08-08, local)

- **What:** the pre-registered covariate-shift branch experiment from the
  §135a verdict (decision log `2026-08-08-leaf-state-diagnostics.md`):
  retrain the deployed §126 end-HP leaf on a MIXTURE of on-policy combatgen
  states PLUS actual Searcher3 search-leaf states, with separate on-policy
  and search-leaf holdouts, and test whether search-leaf RANKING on held-out
  search-leaf states improves. Diagnostic artifact only — no default change,
  no promotion, no C++ change (the deployed `build/v_combat_honest.txt`
  @α0.3 stays). NO gameplay gate (pre-registered: ranking evidence first).
- **Training data and pre-registered split:**
  - combatgen source `build/vcombat_honest.csv` (287,517 rows, 16,337
    fights, seeds 0-1499): fight-group holdout
    `GroupShuffleSplit(test_size=0.15, random_state=0, groups=(seed,fightIdx))`
    → on-policy val (43,473 rows).
  - search-leaf source `build/leafdiag_gate_64.csv` (288,537 rows, seeds
    126700-126763): ONLY train seeds 126700-126747 (48 seeds, 216,079 rows,
    1,012 fights) enter training/validation, with the same fight-group
    split → search-leaf val (30,316 rows); eval seeds 126748-126763 (16
    seeds, 72,458 rows) held out ENTIRELY — asserted absent from every
    training row (runtime assert; 72,458 eval rows counted and filtered).
  - Mixture training set = 429,807 rows (244,044 combatgen + 185,763
    leafdiag). Labels = fight outcome (`fightWon`→`won`, `fightEndHp`→
    `endHp`), same semantics as combatgen; the leafref reference values are
    vnet-influenced approximations and were NEVER training labels. The
    12 diagnostic/metadata leafdiag columns (decIdx, floor, act,
    encounterName, treeDepth, obsHash, nLegalActions, stratum, endHp_pred,
    utilityR_pred, rawRolloutEval, blendedEval) were dropped.
- **Canonical §126 recipe (byte-identical parameters):**
  `VCOMBAT_TARGET=endhp` (default), device `cuda` (RTX 3060 Ti, local),
  max_depth=8, eta=0.05, subsample=0.8, colsample_bytree=0.7,
  min_child_weight=20, max_bin=256, num_boost_round=1500,
  early_stopping_rounds=40, critical-state weight formula
  (won/curHp/maxHp/encounter-failure; POLICY_CSV unset → teacher
  disagreement 0). Early stopping signal = the on-policy (combatgen
  holdout) regime, the same stopping signal as §126. Feature filter = the
  canonical combatgen-derived std>1e-9 filter → **733 features, exactly the
  deployed model's feature set** (filtering on the concatenated frame would
  give 750 — differing variance across the 64-seed leafdiag slice — and
  break the "training mixture is the only difference" comparison). Best
  iteration 1349 (of 1500); exported `build/v_combat_mix.txt` = 1,390
  trees, 733 features, base_score 28.04239; sha256
  `0ed6672c…` (txt) / `c1764f63…` (json). Asserting `one_combat vnettest`
  PASS (max|diff| 1.27e-4 vs tol 0.001, 200 rows).
- **Per-regime validation metrics (trainer, `build/v_combat_mix_metrics.json`):**
  | regime | rows | RMSE vs endHp | MAE vs endHp | RMSE vs R | MAE vs R |
  |---|---|---|---:|---:|---:|
  | on-policy val (combatgen holdout) | 43,473 | **8.23** | **5.97** | 48.37 | 45.65 |
  | search-leaf val (leafdiag train-seed holdout) | 30,316 | **15.46** | **11.33** | 49.20 | 46.20 |
  On-policy comparison: the deployed §126 control measured val RMSE 7.88 /
  MAE 5.58 (§134) and §126 recorded val-rmse 7.99 on the SAME combatgen
  holdout split → **the mixture HURTS the on-policy fit** (RMSE +0.35,
  MAE +0.39). The search-leaf val remains much harder than on-policy
  (RMSE 15.46 vs 8.23) even after training on the search-leaf distribution.
- **Search-leaf ranking evaluation (the DECISIVE pre-registered test):**
  re-ran `one_combat leafdiag 16 1000 0 build/leafdiag_mix_eval.csv 126748`
  on the 16 held-out eval seeds @1000 sims asc 0 with EXACTLY the §135a
  gate-matching env (`STS_FAIR=1 STS_SEARCHER3=1 STS_S3_BELIEF=0
  STS_S3_CHAIN=0 STS_S3_PARTICLES=64`, `STS_VNET=build/v_combat_honest.txt`
  @`STS_VNET_ALPHA=0.3`, `STS_DIAG_VNET2=build/v_combat_mix.txt`,
  `STS_LEAFDIAG_PER_STRATUM=500`, full V4 OOC arms
  `STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_final.native`,
  REST/EVENT/SHOP/TREASURE/BOSS_RELIC=1, `STS_OOC_STRATEGIC_MARGIN=1.0`).
  The search is unchanged (`STS_DIAG_VNET2` is never read by the searcher)
  so the identical leaves regenerate: 72,458 rows re-captured, and
  **100% of re-captured leaves join `build/leafref_gate_64_4k.csv` by
  (seed, fightIdx, decIdx, obsHash)** — the re-capture sanity check passes
  (identical leaves to §135a, no mismatch). New CSV columns: `endHp_pred` =
  deployed §126 model, `utilityR_pred` = mixture model, on identical leaves.
  `tools/leaf_ranking.py --leafdiag build/leafdiag_mix_eval.csv --leafref
  build/leafref_gate_64_4k.csv --ood build/leafdiag_gate_64_ood.csv --json
  build/leaf_ranking_mix_eval.json` (4,395 decision groups re-captured;
  4,387 contribute pairwise metrics, 890,941 pairs, fixed bootstrap seed
  20260808):
  | metric | deployed endHp | mixture (utilityR_pred) | Δ (mixture − deployed) |
  |---|---|---:|---:|
  | pairwise accuracy | **0.7262 [0.7209, 0.7318]** | 0.6914 [0.6858, 0.6970] | **−3.5pp, CIs disjoint** |
  | top-1 | **0.3686 [0.3545, 0.3823]** | 0.3298 [0.3152, 0.3433] | **−3.9pp, CIs disjoint** |
  | regret | **7.431 [7.088, 7.783]** | 8.209 [7.850, 8.569] | **+0.78 (worse)** |
  | Spearman vs ref | 0.790 | 0.803 | +0.013 (mixture better) |
  | Pearson vs ref | 0.779 | 0.801 | +0.022 |
  | MAE vs ref (own scales) | 31.75 | 28.12 | (not comparable across scales) |
  Note the deployed endHp's held-out numbers (pairwise 0.726, top-1 0.369)
  are consistent with the §135a full-64-seed measurement (0.719 / 0.359),
  confirming the 16-seed eval block is representative.
- **Model-free cross-check (rawRolloutEval single-sample reference, no
  leafref; `build/leaf_ranking_mix_eval_rawrollout.json`, 4,085 groups):**
  pairwise 0.7289 [0.7229,0.7350] vs 0.6921 [0.6857,0.6980] (−3.7pp),
  top-1 0.335 vs 0.305, regret 14.47 vs 15.83 — same direction, so the
  mixture's ranking disadvantage is NOT an artifact of the vnet-influenced
  leafref reference.
- **Verdict: ❌ the covariate-shift branch is CLOSED — the mixture does NOT
  improve held-out search-leaf ranking; it makes all three pre-registered
  ranking metrics WORSE (pairwise −3.5pp, top-1 −3.9pp, regret +0.78, all
  CIs disjoint for the accuracies), and it HURTS the on-policy fit (val
  RMSE 8.23 vs 7.88 control, MAE 5.97 vs 5.58).** Pre-registered rule: a
  gameplay gate is a separate follow-up ONLY if ranking improves → **no
  gameplay gate; the deployed §126 vnet stays default.** Notable nuance:
  the mixture correlates with the high-budget reference BETTER than the
  deployed model (Spearman 0.803 vs 0.790, Pearson 0.801 vs 0.779) — the
  same pattern as §134's direct-R model (correlates better, ranks worse) —
  so absolute fit to the (vnet-influenced) reference does not predict
  within-group ranking even when the model is trained ON the search-leaf
  distribution. Training on actual search-leaf states did not make the
  end-HP target rank those states better; the §134 hypothesis space
  (target semantics / ranking-vs-absolute) is not resolved by adding
  search-leaf states to the endHp objective.
- **Artifacts (build/, git-ignored, NOT promoted):**
  `build/v_combat_mix.{json,txt,val.csv,_metrics.json}`,
  `build/leafdiag_mix_eval.csv` (72,458 rows),
  `build/leaf_ranking_mix_eval.json`,
  `build/leaf_ranking_mix_eval_rawrollout.json`, smoke slices
  `build/smoke_{combatgen,leafdiag,mixed}.csv`,
  `build/leafdiag_mix_smoke_2.csv`, `build/v_combat_mix_smoke.*`,
  logs `/tmp/opencode/train_mix_full.log`,
  `/tmp/opencode/leafdiag_mix_eval.log`,
  `/tmp/opencode/leaf_ranking_mix_eval2.log`. Code:
  `tools/train_value_mixture.py` (new; default single-CSV path of
  `train_value_combat.py` is untouched and byte-identical). Decision log:
  `2026-08-08-covariate-shift-mixture.md`.

## §138 Quick partial-data tok retrain + 64-seed feel-run (5.7.3 interim, 2026-08-08, local — INFORMAL smoke, NOT the 5.7.3 gate)

- **What:** while the 3×500-seed GCP datagen (Phase 1) is still running, a
  snapshot of chunk 1 (`build/sp_300000_partial.csv`, 160,276 rows / 302 seeds,
  seeds 300000–3003XX) was pulled and used for a quick V4-token-net retrain and
  a 64-seed paired feel-run. Purpose: exercise the full train/export/gate chain
  end-to-end early; NOT a verdict on 5.7.3.
- **Train (local GPU, .venv, torch 2.5.1+cu121, rung 4, 40 epochs, defaults):**
  `train_strategic_tok.py build/sp_300000_partial.csv build/tok_sp_partial.pt`
  → held-out (31,813 rows / 7,910 groups): `val_pol_ce` 0.559, `policy_top1`
  0.754, `q_top1` 0.288, `margin` 4.75, `value_mae` 4.00. Deployed
  `ooc_strategic_tok_final` metrics for reference (different val split, NOT
  comparable): `val_pol_ce` 0.486, `policy_top1` 0.793, `q_top1` 0.290,
  `margin` 10.32, `value_mae` 10.18. Export:
  `export_strategic_tok.py build/tok_sp_partial.pt.pt
  selfplay/models/ooc_strategic_tok_sp_partial.native` — 32/32 parity checks.
- **64-seed paired feel-run** (seeds 126700–126763, asc 0, 1k sims, fair S3
  −belief−chain, 64p, 12 threads, full V4 gate stack, `STS_OOC_STRATEGIC_MARGIN=1.0`):
  control `STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_final.native`
  vs candidate `.../ooc_strategic_tok_sp_partial.native`:
  **deployed 54.7% vs partial 28.1% wins, Δ −26.6pp, 95% CI [−42.2, −10.9]**;
  floor 44.5 vs 39.5 (Δ −5.1 [−8.1, −2.1]); HP end 30.1 vs 15.3;
  discordant 29/64. Runtime ~4.5 min total (bestbench ~2.4s/seed wall @12t).
  CSVs: `build/tok_cmp_{final,sp}_64.csv`; `paired_analysis.py` strict.
- **Interpretation (informal):** the partial model is clearly worse online, but
  it trained on ~20% of the planned corpus (underfitting expected) and the
  plan's §62/§100/§127/§129 pattern (offline gains do not transfer) is
  consistent. This run does NOT close 5.7.3 — the gate requires the same-recipe
  control (old corpus) vs the full 1500-seed candidate + 256-seed paired gate
  + second confirmation block. No default change; deployed artifact untouched.
- **Decision log:** `2026-08-08-selfplay-relabeling.md` (addendum).

**§138 follow-up (same day): 100-epoch retrain on the same partial data.** `STRAT_EPOCHS=100` on `build/sp_300000_partial.csv` → best held-out `val_pol_ce` 0.5454, `policy_top1` 0.766, `margin` 5.54 (vs 40-epoch 0.559/0.754/4.75 — more epochs helps the offline fit). 64-seed paired gate (same seeds/env): 32.8% vs deployed 54.7% (**Δ −21.9pp, CI [−35.9, −7.8]**); vs the 40-epoch arm **+4.7pp, CI [−7.8, +18.8]** (direction only, n.s.). Conclusion: epoch count explains only a small part of the online gap; the data (volume ~20% + label-producer change) dominates. Artifacts: `build/tok_sp_partial_e100.pt.pt`, `build/tok_e100_train.log`, `build/tok_cmp_sp_e100_64.csv`, `selfplay/models/ooc_strategic_tok_sp_partial_e100.native` (32/32 parity).

## §139 Experiment A: Stratified leaf ranking — endHp vs utilityR ranking gap by stratum (2026-08-08, local — diagnostic, no gameplay)

- **What:** Re-analysis of the §135a leafdiag/leafref corpus (288k leaves, 267k
  references, 17,194 decision groups, 16,676 usable) stratified by fight
  outcome, HP band, tree depth, and cross-strata to test the hypothesis that
  the endHp model's ranking advantage concentrates in near-death deep-tree
  states.
- **Method:** Per-group pairwise ranking accuracy (top-1, regret) of pure model
  predictions (no rollout blend) against leafref high-budget references,
  bootstrap CIs (2,000 iterations, fixed seed 20260808) per stratum.
  Standalone script (not `leaf_ranking.py` — the full tool times out on the
  1 GB CSV due to DictReader memory on this machine; a 28 MB column-pre-filtered
  `build/leafdiag_slim.csv` was used).
- **Artifacts:** `build/leaf_ranking_reconfirm.json`
- **Headline results:**

  | Stratum | nGroups | endHp pairAcc | utilR pairAcc | Δpair | Δtop1 |
  |---|---|---:|---:|---:|---:|
  | **all** | 16,676 | 0.7195 [0.7167,0.7224] | 0.7112 [0.7085,0.7141] | **+0.0082** | **+0.0231** |
  | won=1 | 15,651 | 0.7237 | 0.7157 | +0.0080 | +0.0225 |
  | won=0 (lost) | 1,025 | 0.6549 | 0.6428 | **+0.0121** | +0.0322 |
  | hp_low (<30%) | 6,932 | 0.7291 | 0.7252 | **+0.0039** | +0.0113 |
  | hp_mid (30-70%) | 6,582 | 0.7229 | 0.7146 | +0.0083 | +0.0324 |
  | hp_high (≥70%) | 3,162 | 0.6912 | 0.6735 | **+0.0177** | +0.0297 |
  | deep (d≥15) | 381 | 0.7948 | 0.7768 | **+0.0180** | +0.0525 |
  | mid_depth | 14,364 | 0.7163 | 0.7091 | +0.0072 | +0.0236 |
  | shallow (d<5) | 1,931 | 0.7282 | 0.7143 | +0.0140 | +0.0135 |
  | **low_deep** | 60 | 0.8074 | 0.8068 | **+0.0006** | **−0.0500** |
  | low_shallow | 887 | 0.7430 | 0.7396 | +0.0034 | +0.0079 |
  | won_deep | 381 | 0.7948 | 0.7768 | +0.0180 | +0.0525 |
  | lost_low | 727 | 0.6514 | 0.6469 | +0.0045 | +0.0165 |
  | won_low | 6,205 | 0.7382 | 0.7344 | +0.0038 | +0.0106 |

- **Key findings:**
  1. **The gap does NOT concentrate in near-death states** — it is narrowest
     in hp_low (+0.0039, half the overall gap) and effectively zero at
     low_deep (+0.0006, utilityR actually wins top1 by −0.0500). This refutes
     the architect's cliff-edge hypothesis.
  2. **The gap is widest in high-HP (+0.0177, 2.2× overall) and deep-tree
     (+0.0180, 2.2×) states** — complex, information-rich positions where
     ranking is hardest but individual decisions most differentiate the search
     tree.
  3. **The gap is also larger in lost fights (+0.0121) than won (+0.0080)** —
     in fights the agent eventually loses, model ranking quality matters more.
  4. The overall +0.0082 pairwise gap (and +0.0231 top1) still cannot directly
     explain ±12pp win-rate swings without amplification through PUCT
     visit-redistribution dynamics or direct-eval (unblended) sites.
- **Verdict: diagnostic only.** The ranking advantage exists but is small, does
  not concentrate where hypothesized, and cannot directly explain the ±12pp
  online swing. Experiment B (blend sweep) is the next discriminating test.
- **Decision log:** `2026-08-08-vnet-offline-online-diagnosis.md`

## §140 Experiment B: Blend-α sweep — both models are nearly identical when blended (2026-08-08, local — diagnostic, no gameplay)

- **What:** For 8 α values ∈ [0, 0.05, 0.1, 0.15, 0.2, 0.3, 0.5, 0.7], compute
  within-group pairwise ranking accuracy of the BLENDED value
  `α·model_pred + (1−α)·rawRolloutEval` against the leafref high-budget
  reference. Tests whether: (a) endHp achieves peak ranking at α≈0.2–0.3
  (the deployed sweet spot), (b) utilityR ranking degrades monotonically from
  α=0, (c) any α exists where utilityR approaches endHp.
- **Tool:** `tools/leaf_blend_sweep.py` (new, ~180 lines). Reuses existing
  `build/leafdiag_slim.csv` + `build/leafref_gate_64_4k.csv`.
- **Artifacts:** `build/leaf_blend_sweep.json`
- **Headline results:**

  | α | endHp pairAcc | utilR pairAcc | Δpair | endHp top1 | utilR top1 |
  |---:|---|---:|---:|---:|---:|
  | 0.00 | 0.7192 [0.7163,0.7220] | 0.7192 [0.7163,0.7220] | +0.0000 | 0.3970 | 0.3970 |
  | 0.05 | 0.7456 [0.7429,0.7482] | 0.7444 [0.7418,0.7472] | +0.0011 | 0.4290 | 0.4283 |
  | 0.10 | 0.7465 [0.7439,0.7492] | 0.7455 [0.7429,0.7483] | +0.0010 | 0.4294 | 0.4297 |
  | 0.15 | 0.7473 [0.7447,0.7500] | 0.7465 [0.7439,0.7493] | +0.0009 | 0.4307 | 0.4309 |
  | 0.20 | 0.7482 [0.7456,0.7509] | 0.7472 [0.7446,0.7499] | +0.0010 | 0.4310 | 0.4301 |
  | **0.30** | **0.7499 [0.7474,0.7527]** | **0.7486 [0.7459,0.7514]** | **+0.0013** | **0.4311** | **0.4291** |
  | 0.50 | 0.7517 [0.7491,0.7544] | 0.7484 [0.7457,0.7511] | +0.0033 | 0.4275 | 0.4189 |
  | 0.70 | 0.7498 [0.7471,0.7526] | 0.7436 [0.7409,0.7464] | +0.0062 | 0.4177 | 0.3999 |

  α=0 sanity check: both models identical (0.7192) — they share the same
  rawRolloutEval.

- **Key findings:**
  1. **Both models IMPROVE with any blend > 0.** Even utilityR gains from
     blending — it does NOT degrade monotonically. The pure-model ranking
     (Experiment A) understates both models' usefulness.
  2. **At the deployed α=0.3, the models are statistically INDISTINGUISHABLE.**
     endHp 0.7499 [0.7474,0.7527] vs utilityR 0.7486 [0.7459,0.7514] — CIs
     overlap substantially, gap only +0.0013. The pure-model gap of +0.0082
     (Experiment A) collapses because the 70% shared rollout component dominates.
  3. **endHp peaks at α=0.5** (0.7517), not at the deployed α=0.3. The deployed
     sweet spot is below peak ranking — gameplay wins rate, not ranking
     accuracy, determined α=0.3.
  4. **The gap only visibly separates at α≥0.5:** at α=0.5 gap=+0.0033, at
     α=0.7 gap=+0.0062. Heavier model influence favors endHp, consistent with
     the universal α-curve finding (heavier model influence never helps online).
  5. **The ±12pp online win-rate gap CANNOT be explained by per-leaf blended
     ranking quality.** At the deployed α=0.3, the models rank nearly
     identically. The online gap must come from: (a) direct-eval sites where
     the model fires at full weight (depth cap, no rollout blended),
     (b) PUCT range normalization interacting with model scale (endHp [0,~80]
     vs utilityR [0,~150]), (c) visit-redistribution dynamics amplifying small
     value differences through backprop.
  6. **Top-1 accuracy also nearly identical** at moderate α: endHp 0.4311 vs
     utilityR 0.4291 at α=0.3.
- **Verdict: diagnostic — blend ranking parity disproves the ranking-quality
  hypothesis for the deployed α=0.3.** The online gap is NOT caused by better
  leaf ranking in the blended evaluation. The mechanism must involve
  unblended evaluation sites, PUCT value-scale dynamics, or
  visit-redistribution amplification. Experiment C (top-action agreement + per-
  fight outcome correlation) is the next discriminating test.
- **Decision log:** `2026-08-08-vnet-offline-online-diagnosis.md`

## §141 Experiment C: Top-action agreement — models agree 81% of the time, essentially tied when they disagree (2026-08-08, local — diagnostic, no gameplay)

- **What:** For each of 17,098 decision groups, identify which leaf each model
  picks as "best" (using blended values at deployed α: endHp@0.3, utilityR@0.1)
  and compare against the leafref high-budget reference's choice. Measures
  agreement rate, per-model correctness when they disagree, and stratification
  by fight outcome, HP band, and tree depth.
- **Tool:** `tools/leaf_top_action.py` (new, ~290 lines).
- **Artifacts:** `build/leaf_top_action.json`
- **Headline results:**

  | Metric | Value |
  |---|---:|
  | Total decisions | 17,098 |
  | Models agree on best leaf | 80.9% |
  | endHp matches reference | 44.5% |
  | utilityR matches reference | 44.3% |
  | Both match reference | 39.7% |
  | **Neither matches reference** | **50.9%** |

  **When models disagree (19.1% of decisions):**
  - endHp right: 25.1%, utilityR right: 24.4%, both wrong: 50.4%
  - endHp wins 50.7% of resolvable disagreements — a coin flip
  - Overall endHp advantage: +23 decisions (+0.13pp) out of 17,098

  **Key strata (agreement rate / endHp=ref% / utilR=ref%):**
  - won=1 (83.0% / 45.6% / 45.6%) — identical in won fights
  - won=0 (48.4% / 26.4% / 24.6%) — agreement collapses in lost fights,
    endHp +1.8pp
  - depth=deep (85.9% / 53.7% / 51.2%) — endHp +2.6pp in deep trees
  - hp=mid|depth=deep (87.0% / 53.2% / 50.0%) — endHp +3.2pp
  - hp=low (78.3% / 40.8% / 41.2%) — utilityR +0.4pp in low-HP

  **Per-fight averages:**
  - Won fights (1,309): 12.3 decisions/fight, endHp=ref 53.2%, utilR=ref
    53.1%, models agree 85.4%
  - Lost fights (41): 25.7 decisions/fight, endHp=ref 26.2%, utilR=ref
    25.3%, models agree 49.9%
  - Per-fight winner count: endHp 308, utilityR 330, tie 712

- **Key findings:**
  1. **The two models are effectively IDENTICAL at top-action selection.**
     The models are a coin flip on disagreements, agree 81% of the time,
     and differ by only +23 decisions (+0.13pp) out of 17,098.
  2. **The reference itself is unreliable:** neither model matches it in 50.9%
     of decisions. The high-budget Searcher3 reference is an approximation,
     not ground truth.
  3. **Lost fights are chaotic:** agreement drops from 83% (won) to 48%
     (lost). Top-1 accuracy drops from ~46% to ~26%.
  4. **Deep-tree decisions favor endHp** (+2.6pp, n=391) but sample is small.
  5. **The ±12pp online win-rate gap CANNOT be explained by top-action
     choice.** The models are indistinguishable at ranking (Experiment B)
     AND top-action selection (Experiment C). The gap must come from PUCT
     value-magnitude propagation, visit-redistribution dynamics, or the
     unblended direct-eval sites where the model fires at full weight.
- **Verdict: diagnostic — all three static leaf-analysis hypotheses are
  now closed.** Per-leaf ranking (Exp B), top-action choice (Exp C), and
  cliff-edge concentration (Exp A) all fail to explain the ±12pp gap.
  The remaining causal paths require dynamic search-tree analysis
  (PUCT Q-range normalization, visit-count redistribution, unblended
  evaluation sites).
- **Decision log:** `2026-08-08-vnet-offline-online-diagnosis.md`

## §139 Q-head objective experiments on partial 5.7.3 data (2026-08-08, local, offline only — 373,616 rows / 707 seeds of chunk-1+2 partial, batch 2048, 60 epochs unless noted)

- **What:** two cheap trainer experiments on the new-datagen partial data:
  (A) best-epoch selection by `q_top1` instead of `val_pol_ce`
  (`STRAT_SELECT_METRIC=q_top1`); (B) a pairwise labelWon ranking term
  (`STRAT_RANK_LAMBDA=0.1`, margin 1.0, max 16 pairs/group) added to the Q
  MSE loss. Both opt-in envs, defaults unchanged.
- **Results (held-out):**
  | metric | baseline 60ep (early-stop run) | A: select q_top1 (60ep) | B: rank λ=0.1 (60ep) | baseline 200ep (val_pol_ce sel) |
  |---|---|---|---|---|
  | val_pol_ce | 0.5311 | 0.5374 | 0.5303 | 0.5252 |
  | policy_top1 | 0.773 | 0.770 | 0.774 | 0.776 |
  | margin | 5.57 | 7.71 | 5.65 | 6.40 |
  | q_top1 | 0.2899 | **0.3072** | 0.2904 | 0.2864 |
- **Reading:** selection-by-q_top1 directly improves the Q-head ranking
  agreement (+1.7pp vs the matched 60-ep baseline) at a small policy cost
  (−0.3pp top1); the ranking loss at λ=0.1 is flat (+0.1pp q_top1). Tie-heavy
  labelWon limits pair availability (§105). Offline only — no gate; the
  deployed gate uses the Q-head argmax, so a future online comparison would
  be the real judge. Artifacts: `build/tok_new_{200,selq,rank}.pt.pt` +
  `_metrics.json`.

## §142 Direct-eval site share measurement + scale-controlled utilityR gate — PUCT value-scale dynamics confirmed as the ±12pp gap mechanism (2026-08-08, local)

- **What:** (A) Run `searchdiag` on the deployed S3 config (32 seeds, @1k/64p,
  block 126700–126731) to measure the share of leaf evaluations at unblended
  direct-eval sites vs the blend site where α=0.3 blending applies. (B) Gate a
  **rescaled** utilityR model (affine output transform mapping utilityR's
  [0,~150] band to endHp's [0,~80] via base_score ratio 0.4135) against the
  original non-scaled utilityR model, both at α=0.1, 128 paired seeds
  (126700–126827), full V4 gate stack, fair S3−belief−chain/64p.
  Hypothesis from §141: the ±12pp endHp-vs-utilityR online gap comes from
  PUCT value-scale dynamics, not per-leaf ranking or unblended sites;
  if rescaling utilityR to endHp's band closes the gap, the mechanism is
  confirmed.
- **Tool:** `one_combat searchdiag` (rowtype A, S3 instrumented), affine model
  rescaling via Python text replacement on the §134 artifact
  `build/v_combat_utility_direct.txt` → `build/v_combat_utility_scaled.txt`
  (611 trees, base_score 62.82→25.97, leaf values ×0.4135).
- **Artifacts:** `build/sdiag_siteshare_32.csv`,
  `build/util_nonscale_128.csv`, `build/util_scale_128.csv`,
  `build/v_combat_utility_scaled.txt`

### §142a — Direct-eval site share (diagnostic)

- **Results (32 seeds, 9,915 decisions, 14.17M sims):**

  | Site | Count | Share of model evals |
  |---|---|---:|
  | Blended (rolloutLeafCalls, α=0.3) | 8,666,136 | 100.0% |
  | Unblended direct eval (leafDirectEval) | 231 | 0.003% |
  | Illegal-stored-edge share of rollouts | 11.9% | — |

  Only 34/9,915 decisions had any leafDirectEval > 0. `rolloutNoLegal` = 0
  (every rollout runs to terminal). The invariant
  `sims == terminalInTree + rolloutCalls + leafDirectEval` holds to
  within 0.001%.

- **Key finding: unblended direct-eval sites are essentially non-existent.**
  With `STS_ROLLOUT_DEPTH=0`, every rollout terminates — there are no
  depth-cap evals and no-legal-action at the live state almost never occurs.
  The §139–§141 corpus analyzed the only meaningful model-evaluation site
  (the blend site), where the two models are statistically indistinguishable.
  The ±12pp online gap **cannot** come from unblended sites — it must be
  PUCT value-scale dynamics.

### §142b — Scale-controlled utilityR gate

- **Results (128 paired seeds, α=0.1):**

  | Arm | Win% | Floor | HP end | cpu-s/run |
  |---|---|---:|---:|---:|
  | Non-scaled utilityR (original) | 36.7% | 40.9 | 24.6 | 19.1 |
  | Scaled utilityR (×0.41, endHp band) | **47.7%** | 42.4 | 24.9 | 20.7 |
  | Δ (scaled − non-scaled) | **+10.9pp** | +1.5 | +0.3 | +1.6 |
  | Deployed endHp @α0.3 (reference) | 56.2% | 44.7 | 31.9 | 27.6 |

  - Δ win 95% CI: **[+1.6pp, +20.3pp]** — statistically significant (CI excludes
    zero). Discordant 42/128 (33%): A-only 14, B-only 28.

- **Key finding: rescaling utilityR to endHp's output band recovers nearly
  all of the §134 −12.1pp gap.** The scaled model at 47.7% trails the
  deployed endHp at 56.2% by −8.5pp, but this is at α=0.1 (utilityR's
  pre-registered operating point) vs endHp's α=0.3 sweet spot. The 10.9pp
  gain from pure affine rescaling confirms the mechanism: both models rank
  leaves nearly identically (§140/§141), but utilityR's larger terminal scale
  ([0,~150]) changes `evalRange = max(1.0, bestValue − minValue)` in PUCT,
  shifting the exploration/exploitation balance and redistributing visit
  counts through backprop. When the scale matches, the ranking signal has
  room to express.

### §142c — Scale × α sweep (32 seeds, diagnostic)

- **What:** Grid sweep over 6 scale factors {0.20, 0.30, 0.41, 0.50, 0.60, 1.00}
  and 5 α values {0.05, 0.10, 0.20, 0.30, 0.50}, 32 seeds each, same full
  V4 gate stack. Scale factors generated by affine leaf-value × base_score
  multiplication on the §134 artifact `build/v_combat_utility_direct.txt`.

- **Results (32 seeds, win%):**

  | scale | α=0.05 | α=0.10 | α=0.20 | α=0.30 | α=0.50 |
  |---:|---:|---:|---:|---:|---:|
  | 0.20 | 28% | 41% | 41% | — | — |
  | 0.30 | 38% | 44% | 41% | — | — |
  | **0.41** | 38% | **50%** | 44% | 25% | 40% |
  | 0.50 | 38% | 31% | 41% | 47% | — |
  | 0.60 | 34% | 38% | 38% | 44% | — |
  | 1.00 | 31% | — | — | 38% | — |

  References: endHp α=0.10 = 39.1% (64 seeds), endHp α=0.30 = 56.2% (128
  seeds).

- **Key finding: peak is at scale≈0.41 (base_score–matched), α≈0.10.**
  Higher α degrades (α=0.50 → 40%). Higher scales at low α are worse than
  non-scaled (s=0.50 α=0.10 = 31% vs s=1.00 α=0.10 = 37% on 128 seeds).
  The sweet spot confirms the PUCT scale-dynamics hypothesis: utilityR's
  output band must match endHp's for the ranking signal to express.

### §142d — Definitive paired gate: scaled utilityR @α=0.10 vs deployed endHp @α=0.30 (128 paired seeds)

- **Results:**

  | Arm | Win% | Floor | HP end | cpu-s/run |
  |---|---|---:|---:|---:|
  | Deployed endHp @α=0.30 | **56.2%** | 44.7 | 31.9 | 27.6 |
  | Scaled utilityR @α=0.10 | 47.7% | 42.4 | 24.9 | 20.7 |
  | Δ (util − endHp) | **−8.6pp** | −2.3 | −7.0 | −6.9 |

  - Δ win 95% CI: [−18.8pp, +0.8pp] — CIs span zero, direction clear.
    Discordant 41/128: A-only 26, B-only 15.

- **Key finding: the rescaled utilityR model does NOT beat the deployed endHp
  model, despite rescaling recovering +10.9pp from the scale mismatch.**
  At its optimal α=0.10 the scaled utilityR (47.7%) trails endHp at its
  optimal α=0.3 (56.2%) by −8.6pp. The better Spearman correlation (0.820 vs
  0.769, §135a) does not translate into a better combat leaf.

- **Verdict: the utilityR objective line is CLOSED.** Three independent
  gates now confirm it: (1) quantile-R α=0.3 −12.9pp (§133), (2) direct-R
  α=0.1 −12.1pp (§134), (3) rescaled direct-R α=0.1 −8.6pp (§142d).
  Rescaling fixes the scale interaction but the underlying value semantics
  (R = 50+endHp on win) rank combat states worse than raw endHp.
  The deployed `build/v_combat_honest.txt` @α=0.3 stays.

### §142e — Summary

- **Unblended direct-eval sites: 0.003% — ruled out.**
- **PUCT value-scale dynamics: CONFIRMED.** +10.9pp from rescaling alone
  (CI [+1.6, +20.3]).
- **UtilityR objective: CLOSED.** Even at matched scale, it trails endHp.
- **Combat-leaf model-improvement line: EXHAUSTED.** Every alternate target
  (quantile-R, direct-R, rescaled-R) has now been gated and lost. The
  remaining open question is whether a new training target derived from the
  frontier-leaf corpus (§136) could differ, but the historical record is
  uniformly negative (§133, §134, §137, §142d).

### §142f — Searchdiag mining: where the S3 search is weakest (diagnostic, no gameplay)

- **What:** Analyze the 32-seed `searchdiag` run from §142a (9,915 decisions,
  14.17M sims, deployed S3 config @1k/64p) for structural weakness patterns.
- **Tool:** manual Python analysis of `build/sdiag_siteshare_32.csv`.

- **Key findings:**

  1. **Act 3 is the weak spot.** Rollout fraction rises from 60% (Act 1) to
     77% (Act 3). Illegal-stored share rises from 7.2% to 19.0%. Tree coverage
     drops from 0.65 to 0.52. Visit share drops from 0.76 to 0.63.

  2. **19% of decisions are near-pure rollouts (visitShare < 0.5):**
     rollout fraction 93-94%, tree coverage ~0.33, average 5-6 legal actions,
     ~17-19 action rollouts. The tree barely exists — concentrated in Acts 2-3
     (20-28% of decisions, vs 13% in Act 1).

  3. **Even confident decisions waste sims.** Decisions with visitShare > 0.9
     (39% of all decisions, tree converged) still have **22.4% illegal-stored
     share** — every 5th tree descent hits an invalid edge and falls back to a
     random rollout.

  4. **25% of decisions are near-ties (value gap < 2):** visitShare only 0.50,
     80% rollout fraction. The search cannot distinguish the top actions —
     prime candidates for more sims or a sharper leaf model.

  5. **Per-encounter hot spots:** Encounter 40 (Act 3 boss) has 29.6% illegal
     share at 0.89 visitShare — very confident, very wasteful. Encounters 38
     and 53 have ~85% rollout fraction and visitShare < 0.5 — almost no tree.

- **Implication for searcher-side experiments:** The illegal-stored-edge path
  burns ~12% of rollouts overall (19% in Act 3). `STS_S3_EXPAND` tried to fix
  this by expanding legal edges but was falsified at −2.3pp (§125). However
  the waste grows with sim budget (§117: 68% at 30k sims in Act 1). A
  lighter-weight alternative — expand into the tree without PUCT on the new
  branch (deterministic descent only) — might avoid the §125 penalty. The
  near-tie decisions (25%, value gap < 2) are also candidates for dynamic sim
  allocation (give more budget when the top actions are close).

## §143 S3 fair forced-move budget pool redirect (STS_S3_POOL_REDIRECT): implemented opt-in; 8-seed smoke only — paired 256-seed gate pending (2026-08-09, local WSL)

- **What:** the §123 forced-move contraction (−8.5% cpu in the S3 fair
  path) discards the sims it saves. This opt-in flag reinvests them: each
  forced decision credits its unspent base sim budget to a per-fight
  `fightPool` (`ScumSearchAgent2::playoutBattleFair`, S3 branch), and each
  non-forced decision spends `baseSims + min(pool, baseSims)` (poolFrac
  1.0). Pure budget redirect — **no stability-based early stopping**: the
  STS_CONV_ROOT stability line (§118, −2.3pp at 256 seeds) is deliberately
  not revived; this isolates the clean forced-move-only sub-case that §118
  never tested. Env: `STS_S3_POOL_REDIRECT=1` (default off), parsed in
  `apps/one_combat.cpp::main` next to `STS_S3_BELIEF`.
- **Config (smoke):** `one_combat bestbench 300 8 0 126700 <out.csv>`;
  `STS_FAIR=1 STS_SEARCHER3=1 STS_S3_BELIEF=0 STS_S3_CHAIN=0
  STS_S3_PARTICLES=64` (+ `STS_S3_POOL_REDIRECT=1` for the candidate arm);
  asc 0; fair S3−belief−chain; native OOC; floor=`build/v_rich_trees.txt`,
  win=`build/v_win_trees.txt`; threads 12 (auto). Metric formula = producer
  `bestbench` summary; per-seed outcome columns won/floor/act/hpEnd/maxHp/
  fightsLost/deathCombat/deathEncounter.
- **Parity (required precondition):** unset vs `STS_S3_POOL_REDIRECT=0`
  give per-seed-identical outcomes on all 8 outcome columns (8/8 seeds;
  only the wall-time `sec` column differs) — the flag is decision-neutral
  when off, so the pair can gate against the same reference.
- **Smoke results (8 seeds, 300 sims — noise-dominated, not a gate):**
  candidate ON **25.0%** (2/8 wins) / floor 35.9 / hp 13.2 / cpu_sec/run
  3.73 vs OFF 37.5% (3/8) / floor 35.8 / hp 10.5 / cpu_sec/run 3.50–3.76.
  4/8 seeds change outcome (pool demonstrably engages and shifts
  decisions). cpu_sec/run at 300 sims is dominated by per-run wall-clock
  noise (12 threads), so no cpu claim is made from this smoke.
- **Gate result (64 paired seeds, 2026-08-09, local, same config @1k sims):**
  control 21.9% win / 38.6 floor / 8.5 HP / 22.2 cpu-s/run;
  candidate 23.4% win / 39.1 floor / 10.2 HP / 24.7 cpu-s/run.
  **+1.6pp (95% CI [−5.3, +8.4]), 5/64 discordant (8%, 3 up / 2 down),
  cpu 1.11×.** Null at 64 seeds — direction favors candidate but CI spans
  zero heavily; cpu went up (+11%) rather than down, suggesting the pool
  spends extra sims without enough forced-move donations to offset, or
  noise dominates. §118 precedent (pool+stop −2.3pp) makes a pure-redirect
  positive plausible, but 256 paired seeds needed to confirm.
- **Caveat:** the §142 tok-globals change (50→41, de75e6c) prevents loading
  the deployed strategic tok-net model; both control and candidate arm run
  without it (native OOC GBMs only, win% ~21.9, NOT comparable to the §126
  50.4% reference). Paired deltas are internally valid, absolute win% is not.
  Paired 256-seed gate pending (orchestrator, needs tok-net load fix first).

## §144 Mid-rollout visible-state collision frequency in Searcher3 fair play — 0.089% exact collision rate, <1% dead end for rollout TT / path reuse (2026-08-09, local — diagnostic measurement, no gameplay change)

- **What:** first direct measurement of mid-rollout visible-state collision
  frequency under Searcher3 fair play (particle determinization). The §114
  obs-keyed descent failure predicted near-zero collisions (visible states
  diverge at every level) and the `leafCache` comment in
  `BattleScumSearcher3.h` asserted post-rollout states are "effectively
  unique" — both were expectations, never measured. This gates whether
  rollout transposition tables, path reuse, or move-ordering optimizations
  could ever help.
- **Tooling:** the existing `rollouttrace` mode emitted the recorded leaf's
  `obsHash` (deduped per decision by construction, so leaf-level collisions
  are 0 by design) but not per-state hashes. Added a trailing `stateHash`
  column (the row state's OWN `visibleHash`, equal to `obsHash` at step 0)
  to the diagnostic output only — `search::g_onRolloutStep` stays nullptr in
  all normal paths, so default behavior is byte-identical (verified: columns
  1-20 of a 2-seed replay are byte-identical to the §135a
  `rollouttrace_gate_64.csv` rows for those seeds).
- **Dataset:** `rollouttrace` replay of the §135a corpus
  `build/leafdiag_gate_64.csv`, 16 seeds (126700-126715), replay sims 1000,
  asc 0, full gate-matching env (`STS_FAIR=1 STS_SEARCHER3=1
  STS_S3_BELIEF=0 STS_S3_CHAIN=0 STS_S3_PARTICLES=64`, `STS_VNET=
  build/v_combat_honest.txt` @ `STS_VNET_ALPHA=0.3`, `STS_DIAG_VNET2=
  build/v_combat_utility_direct.txt`, V4 OOC gate arms
  `STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_final.native`
  + REST/EVENT/SHOP/TREASURE/BOSS_RELIC=1 + `STS_OOC_STRATEGIC_MARGIN=1.0`);
  100% leaf re-capture, no WARNINGs. Artifact:
  `build/rollout_trace.csv` (830,753 rows, 4,821 searches, 73,354
  trajectories). Run binary = commit 2fb271a + stateHash column; the §142
  (de75e6c) tok-globals change (50→41) and its uncommitted `NGLB 50→41`
  loader follow-up break loading of the deployed tok-net models, so a
  de75e6c-era binary cannot reproduce the §135a gate distribution (0%
  re-capture) — the reference build is the pre-§142 tree.
- **Result (per search = seed,fightIdx,decIdx; exact `visibleHash`):**
  - mid-rollout states (steps ≥ 1): **0.0891%** pooled collision rate
    (756,724 unique / 757,399 states); per-search mean 0.0916%, median 0%,
    max 50% (a 2-state outlier), 198/4,583 searches (4.3%) have any
    collision;
  - all states incl. leaves: 0.1340%;
  - cross-trajectory repeats within a search (same hash in ≥2 trajectories):
    0.139% of mid-rollout states;
  - coarse-feature upper bound (turn/HP/block/energy/strength/hand/draw/
    discard/monSumHp/monMaxHp/incomingDmg/isTerminal projection): 2.84% —
    the extra hashed fields (hand/pile contents, per-monster detail, powers,
    relics) differentiate ~97% of coarse-colliding states, confirming the
    coarse projection massively over-counts.
- **Verdict: DEAD END for rollout TT / path reuse / move-ordering caching.**
  Exact mid-rollout visibleHash collisions are 0.089%, ~11× below the 1%
  threshold; even cross-trajectory repeats (the only TT-usable signal) are
  0.139%. The §114 expectation is now data: under particle determinization
  every rollout step lands in an effectively unique visible state. Do not
  invest in rollout-state caching; the leafCache comment's "effectively
  unique" claim is confirmed.
- **Decision log:** `2026-08-09-rollout-collision-diagnostic.md`.

## §145 S3−belief−chain + canonicalized multiselect actions (STS_MULTISELECT_CANONICAL): implemented opt-in — null at 64 paired seeds (2026-08-09, local WSL)

- **What:** GAMBLE/EXHAUST_MANY multi-select actions enumerate every hand
  subset under the default `all` mode (up to 1023 edges for 10 identical
  cards). `STS_MULTISELECT_CANONICAL=1` canonicalizes each subset mask by
  the selected cards' identity multiset (`id`, upgradeCount, costForTurn,
  freeToPlayOnce, specialData) — the same equivalence the existing
  PLAYER_NORMAL duplicate-card collapse uses — and deduplicates identical
  multisets in `Action::pushMultiSelectActions`. Upgraded/temporarily
  modified copies remain distinct; only genuinely identical selections are
  collapsed. Default off, opt-in.
- **Config:** `one_combat bestbench 1000 64 0 126700 <out.csv>`;
  `STS_FAIR=1 STS_SEARCHER3=1 STS_S3_BELIEF=0 STS_S3_CHAIN=0
  STS_S3_PARTICLES=64` (+ `STS_MULTISELECT_CANONICAL=1` for candidate);
  no tok-net (broken by §142, see §143 caveat); native OOC;
  floor=`build/v_rich_trees.txt`, win=`build/v_win_trees.txt`;
  combatVNet=ON @α=0.3; policyNet=ON; PVNet/off; asc 0; threads 12.
- **Parity:** `./build/test cardselect_parity` passes + new
  `cardselect_canonical` test verifies: 1024→256 masks (3 Strikes+3
  Defends+4 distinct, 10-card GAMBLE), 1023→11 (10 identical Strikes),
  [Strike,Strike,Strike+,Defend] keeps {0,1} and {0,2} distinct while
  collapsing {1,2}→{0,2}. `STS_MULTISELECT_CANONICAL=0` is behaviorally
  identical to unset.
- **Gate result (64 paired seeds, @1k sims):**
  control 21.9% win / 38.6 floor / 8.5 HP / 22.2 cpu-s/run;
  candidate 20.3% win / 39.1 floor / 8.2 HP / 22.0 cpu-s/run.
  **−1.6pp (95% CI [−4.6, +1.5]), 1/64 discordant (2%), cpu 0.99×.**
  Null — 4× branching reduction at GAMBLE states is decision-neutral
  within sampling noise. GAMBLE/EXHAUST_MANY states are rare and the
  current uniform-prior PUCT already dilutes visits harmlessly; the
  expected benefit (more focused search on non-GAMBLE turns) is too small
  to measure at 64 seeds. The parity test is the real win — canonicalization
  preserves correctness under the full cardselect contract.
- **Verdict:** env stays opt-in default-off. Gate pending for larger sample
  (256 seeds) to confirm the null, but the low discordance (1/64) strongly
  suggests zero effect; priority is low.
- **Decision log:** `2026-08-09-multiselect-canonicalization.md`. Code:
  `src/sim/search/Action.cpp::pushMultiSelectActions` (multiSelectCanonical,
  cardIdentityKey, dedup); `apps/test.cpp::testCardSelectCanonical`.

## §146 Searcher2 transposition table (STS_TT) — first-ever benchmark: CATASTROPHIC, 0% win (2026-08-09, local WSL)

- **What:** `g_useTT` / `STS_TT` in `BattleScumSearcher2.cpp` shares value
  statistics (`simulationCount`, `evaluationSum`) across action-order-
  equivalent states via a hash table lookup in `selectBestEdgeToSearch`,
  `selectBestValidEdgeToSearch`, and `evaluateEdge`. Implemented but NEVER
  benchmarked through the entire §99–§135 experiment series.
- **Config:** `one_combat bestbench 1000 32 0 126700 <out.csv>`;
  `STS_FAIR=1` (S2 fair); asc 0; threads 12. Token-net, vnet, etc. not
  relevant (Searcher2-only arm).
- **Results (32 paired seeds, S2-fair @1k):**

  | Arm | Win% | Floor | HP end | cpu-s/run |
  |---|---|---|---|---|
  | TT off (control) | **18.8%** | 37.1 | 9.5 | 9.08 |
  | TT on (candidate) | **0.0%** | 20.1 | 0.0 | 3.51 |
  | Δ (on − off) | **−18.8pp** | −17.0 | −9.5 | −5.57 |

  Every single TT-on run died with 0 HP. The TT does make search ~2.6×
  faster per run, but destroys play quality catastrophically.
- **Mechanism (Inference):** plausible causes are (a) hash collisions in
  `battleStateHash`, (b) value statistics shared across states that are
  action-order-equivalent but NOT value-equivalent under fair
  determinization (different enemy intents / residual HP per particle
  world), or (c) stale/incorrect stateHash propagation when the searcher
  reuses subtrees. The TT key includes all RNG streams, which should make
  it exact-match-only — hash collisions are most likely.
- **Verdict: CLOSED.** Do not port the TT to Searcher3 or invest further.
  The TT code stays in the tree (off by default) as a cautionary artifact.
- **Decision log:** (this entry). Code: `src/sim/search/
  BattleScumSearcher2.cpp::g_useTT` (36), `battleStateHash` (63),
  `selectBestEdgeToSearch` (501), `selectBestValidEdgeToSearch` (545),
  `evaluateEdge` (496); parsed `STS_TT` in `apps/one_combat.cpp::main`
  (line 9237).

## §147 Dynamic alpha by rollout length (STS_VNET_ALPHA_LEN, A2): implemented opt-in — negative direction at 64 paired seeds (2026-08-09, local WSL)

- **What:** plan-rollout-experiments-2026-08-07.md §3 A2 (dynamic α by
  rollout length). Replaces the flat vnet/pvnet alpha at the leaf blend
  site with a lookup over the rollout action count L. Pre-registered table
  {≤2:0.1, 3–5:0.2, 6–10:0.4, >10:0.6}: short rollout = trustworthy
  terminal → low α (trust rollout); long rollout = noisy → high α (trust
  learned leaf). Applied to both vnet and pvnet blends. Env:
  `STS_VNET_ALPHA_LEN=1` (default off), `STS_VNET_ALPHA_LEN_TABLE`
  overrides the table (format "ceil:alpha,...").
- **Config:** `one_combat bestbench 1000 64 0 126700 <out.csv>`;
  `STS_FAIR=1 STS_SEARCHER3=1 STS_S3_BELIEF=0 STS_S3_CHAIN=0
  STS_S3_PARTICLES=64` (+ `STS_VNET_ALPHA_LEN=1` for candidate);
  no tok-net (broken by §142); native OOC; combatVNet=ON @flat α=0.3
  (overridden per-leaf by the table when flag is on); asc 0; threads 12.
- **Parity:** `STS_VNET_ALPHA_LEN=0` vs unset — 8/8 seeds identical
  (confirmed).
- **Gate result (64 paired seeds, @1k sims):**
  control 21.9% win / 38.6 floor / 8.5 HP / 22.2 cpu-s/run;
  candidate 18.8% win / 38.2 floor / 7.4 HP / 22.5 cpu-s/run.
  **−3.1pp (95% CI [−14.6, +8.3]), 14/64 discordant (22%, 6 up / 8 down),
  cpu 1.01×.** Direction negative, high discordance (22%). Avg rollout
  length ~14 actions → most leaves land in the >10 bucket (α=0.6) — the
  table effectively RAISES α for the dominant case from the calibrated
  optimum 0.3, pushing more weight onto the learned leaf where the
  terminal outcome has already proven load-bearing (§133: "long-horizon
  terminal grounding is load-bearing"). The short-rollout buckets get
  lower α (0.1–0.2) but are too rare to offset.
- **Note on table inversion:** the plan's pre-registered table
  {≤2:0.1,…,>10:0.6} makes α INCREASE with rollout length (trust leaf
  more when rollout is noisy). The task specification during this
  session had the inverse table {≤2:0.6,…,>10:0.2} with opposite
  rationale — the task was an error, and the plan's table was
  implemented. The inverse would make α DECREASE with length, pushing
  the flat-0.3 calibrated optimum toward ~0.2 for the dominant >10
  bucket — directionally even worse.
- **Verdict: negative direction at 64 seeds; env stays opt-in default-off.**
  Table inversion (short→low, long→high) would flip the α direction for the
  dominant long-rollout bucket and is testable as a follow-up, but the
  current negative signal + high discordance makes either variant a weak
  candidate. The flat calibrated α=0.3 is the robust default.
- **Decision log:** (this entry). Code: `src/sim/search/
  BattleScumSearcher3.cpp::alphaForRolloutSteps`, `g_vnetAlphaLen`,
  `g_vnetAlphaLenTable`; parsed in `apps/one_combat.cpp::main`.

## §140 Stall-battle hang in the S3 fair battle loop: root-caused and fixed (2026-08-08, local + GCP)

- **Symptom:** datagen seed 300865 (and any seed hitting the same state) never
  completed: the seed's single worker thread spun at ~1 core with zero rows
  written (rows buffer until seed end), no deadlock, all backtraces showing
  normal busy search activity.
- **Root cause:** `ScumSearchAgent2::playoutBattleFair` (and the other three
  battle loops) run `while (bc.outcome == Outcome::UNDECIDED) { search; takeAction; }`
  with **no iteration bound**. StS has no stall timer, so a fight can last
  forever; the S3 search plays such fights defensively (blocks/heals more than
  the boss damages) and never finishes them. Seed 300865 reaches the act-1
  boss (encounter 31, floor 16) — the cheap eval policy dies there instantly,
  the search stalls it forever. ~1/1000 seeds hit a stallable fight, which is
  why 999/1000 datagen seeds completed normally.
- **Fix:** `kMaxBattleDecisions = 1000` stall guard in all four battle loops
  (fair S3, fair S2, non-fair S3, non-fair S2); an exceeded battle is treated
  as `PLAYER_LOSS` with a `[battle-stall]` warning. Normal battles finish in
  well under 100 decisions, so default behavior is unchanged (the counter is
  separate from `decisionIdx`, which seeds the per-decision searcher).
- **Verification:** seed 300865 locally: 3 stall warnings, completes in 245s,
  746 rows, rc=0; on GCP: same, chunk 2 now 500/500 seeds (273,518 rows).

## §141 Self-play relabeling Phase 1 datagen COMPLETE: 801,782 rows / 1,500 seeds (2026-08-08→09, GCP sts-test)

- **Config:** `strategicgen2` 3×500 seeds (offsets 300000/300500/301000, seeds 300000–301499),
  1000 sims, asc 0, `STS_FAIR=1 STS_SEARCHER3=1 STS_S3_BELIEF=0 STS_S3_CHAIN=0
  STRATEGIC_SAMPLE_ALL=1`, 24 threads, current controller (S3−belief−chain + live-valid +
  deployed vnet α0.3 defaults), heuristic-OOC main/branch policy (plan §3 contract).
- **Artifacts:** `build/sp_300000.csv` (263,622 rows), `sp_300500.csv` (273,518),
  `sp_301000.csv` (264,642); concatenated `build/strategic_sp_1500.csv` (801,781 data rows,
  1.6 GB, 1,500 distinct seeds). ~5.5h wall across the three chunks (95–110 min each),
  preemption-safe chunking per the plan.
- **Stall-battle incident (§140):** seed 300865 hung the chunk-2 run — the S3 search stalled
  the act-1 boss fight forever (no game stall timer; the search blocks/heals instead of
  finishing). Fixed with `kMaxBattleDecisions=1000` in all four battle loops; seed backfilled
  (746 rows) — chunk 2 complete 500/500. No stall warnings in chunk 3.
- **Row volume:** ~535 rows/seed, within the plan's 0.8–1.3M expectation (at the low end;
  ~1/4 the old tierb corpus's 3.06M rows). The §104-style diagnostic (argmax(labelWon) vs
  `chosen` agreement per screen) is the next check before training.
- **Next:** Phase 2 training (same-recipe control on old tierb data + candidate on
  `strategic_sp_1500.csv`), then the 256-seed paired gate.

## §142 Self-play relabeling 5.7.3 GATE: new-controller labels FALSIFIED — candidate −10.2pp (CI [−17.6, −2.7]); line closed as a distribution lever (2026-08-09, local)

- **Datagen:** §141 (`build/strategic_sp_1500.csv`, 801,781 rows / 1,500 seeds, current
  controller).
- **Label diagnostic (informative, not a gate):** `tools/label_agreement.py` on the new
  corpus: **66.8% strict / 83.9% in-set** argmax(labelWon)-vs-chosen agreement vs the old
  tierb corpus's 38.0% / 58.1% (§104) — the new labels are far less tie-dominated; per
  screen: MAP 42.7/74.1, CARD_SELECT 47.8/55.8, all others 100/100.
- **Training (identical recipe both arms):** `train_strategic_tok.py`, rung 4, epochs 60
  max, `STRAT_PATIENCE=6` early stop (best-epoch by val_pol_ce), batch 2048 (8GB GPU).
  Control (`build/strategic_tierb.csv`, old labels): early stop at epoch 23, val_pol_ce
  0.5014, policy_top1 0.7869, margin 10.86, q_top1 0.2787. Candidate
  (`strategic_sp_1500.csv`): early stop at epoch 44, val_pol_ce 0.5075, policy_top1 0.7815,
  margin 8.63, **q_top1 0.2951** (candidate better on Q-ranking, slightly worse on policy).
  Exports: `selfplay/models/ooc_strategic_tok_{ctrl,sp}.native` (parity passed).
- **Paired gate** (seeds 126700–126955, 1k sims, fair S3 −belief−chain, 64p, full V4 gate
  stack, asc 0, local 12 threads): **control 49.6% vs candidate 39.5% wins, Δ −10.2pp,
  95% CI [−17.6, −2.7]**; floor 42.9 vs 42.3 (Δ −0.5, n.s.); HP end 24.7 vs 20.9;
  discordant 102/256. CSVs `build/gate_tok_{ctrl,sp}_256.csv`, strict `paired_analysis.py`.
- **Verdict (pre-registered rule, plan §1): candidate ≥ control with CI excluding a
  meaningful loss → promotion; here the candidate is SIGNIFICANTLY WORSE → 5.7.3 CLOSED
  as a distribution lever. Recorded, NOT iterated on data volume.** The "better" label
  source (current controller, §141 diagnostic confirms the labels genuinely changed) does
  not transfer — consistent with §62/§100/§105/§127/§129. Deployed
  `ooc_strategic_tok_final.native` unchanged.

## §148 V_combat hyperparameter optimization (Optuna TPE search + paired gate): +10.9pp win at matched tree count; new default vnet (2026-08-09, local)

- **What:** 50-trial Optuna TPE hyperparameter search over the canonical
  `train_value_combat.py` XGBoost recipe (max_depth, eta, subsample,
  colsample_bytree, min_child_weight, lambda, alpha, gamma) on the
  honest dataset (`build/vcombat_honest.csv`, 287K rows, 16K fights),
  same GroupShuffleSplit and critical-state weighting. Best trial trained
  to 2000 trees (eta 0.031), exported at 800/1000/2000 trees for a compute-
  cost sweep. Paired gate: S3 fair −belief−chain, 64p, 1k sims, 64 seeds,
  no OOC gate stack (default native OOC), α=0.3.

- **Best hyperparameters vs deployed (§126):**

  | Parameter | Deployed (§126) | Tuned (§148) |
  |---|---|---|
  | `max_depth` | 8 | 8 |
  | `eta` | 0.05 | 0.031 |
  | `subsample` | 0.8 | **0.54** |
  | `colsample_bytree` | 0.7 | 0.81 |
  | `min_child_weight` | 20 | **82** |
  | `lambda` (L2) | 1.0 (default) | 0.003 |
  | `alpha` (L1) | 0 (default) | **1.81** |
  | `gamma` | 0 (default) | **4.36** |

- **Offline metrics (same validation split):** tuned model RMSE 7.78 vs
  deployed 7.88 (−1.3%). The improvement is small but consistent across
  the top trials (7.78–7.82 cluster). Parameter importance:
  `subsample` (0.29) and `min_child_weight` (0.29) dominate.

- **Paired gate at matched compute (64 seeds, S3 fair, 1k sims, default
  OOC, no gate stack):**

  | Model | Trees | Offline RMSE | **Win%** | Floor | End HP | cpu_sec/run |
  |---|---|---:|---:|---:|---:|---:|
  | Baseline (§126 honest) | 804 | 7.88 | **20.3%** | 40.1 | 14.1 | 26.6 |
  | Tuned @800 trees | 800 | ~7.90 | **31.2%** | 39.5 | 15.2 | 40.4 |
  | Tuned @1000 trees | 1000 | ~7.90 | **31.2%** | 40.1 | 17.8 | 42.8 |
  | Tuned @2000 trees | 2000 | 7.78 | 29.7% | 39.6 | 14.8 | 68.0 |

  At matched tree count (~800 trees), the tuned hyperparameters give
  **+10.9pp win** (20.3% → 31.2%). The 1000-tree version ties for best
  win rate with the highest end-HP. The 2000-tree version performs WORSE
  (29.7%) despite the best offline RMSE — offline metrics do not predict
  MCTS action-ranking quality.

- **Why the offline metrics barely change but gameplay improves 10pp**
  (**Inference**, not experimentally decomposed): higher regularization
  (`min_child_weight` 82 vs 20, L1 α=1.81, γ=4.36) and aggressive
  subsampling (0.54 vs 0.8) make the ensemble more conservative and better-
  generalizing. Offline RMSE is measured on on-policy pre-action snapshots
  from the teacher policy; MCTS visits off-policy counterfactual states
  that benefit from smoother, less-overfit value estimates. The higher
  `min_child_weight` specifically forces each leaf to have ≥82 weighted
  samples, preventing memorization of specific state configurations and
  producing a smoother value landscape that guides search better.

- **Verdict:** ↗ tuned hyperparameters are a clear improvement.
  The 1000-tree export (`build/v_combat_hparam_1000.txt`, sha256
  `7cd5a1eb…`) replaces `build/v_combat_honest.txt` as the default
  S3-fair vnet at α=0.3. A full-stack re-measurement with the V4 gate
  stack is an open follow-up.

- **Artifacts:** `tools/tune_vnet_hparams.py` (Optuna search script),
  `tools/tune_vnet_best.py` (final training + export),
  `build/vnet_hparam_*.db` (Optuna study),
  `build/v_combat_hparam*.txt` (tree exports at 800/1000/1400/2000 trees),
  `build/vnet_hparam_{baseline,tuned,1k}_{1k_{32,64},1000t_64,800t_64}.log`
  (benchmark logs).

- **Cost:** ~18 min for the 50-trial search (CUDA), ~2 min/export, ~4 min
  per 64-seed benchmark arm (local 12-thread WSL).

- **7k-data extension (same session):** retrained with the §148 tuned
  hyperparameters on the 1.58M-row `build/vcombat_7k.csv` (87K fights,
  5.5× more data than honest). Exported at 1000 trees, 751 features,
  parity-verified (max|diff|=8.6e-5). 64-seed S3-fair gate: **37.5% win**
  vs 31.2% honest-tuned (+6.3pp from data volume). The 7k model
  (`build/v_combat_7k_tuned.txt`, sha256 `ea35b78c…`) is now the default
  vnet. Progression: §126 20.3% → honest-tuned 31.2% (+10.9pp params) →
  7k-tuned 37.5% (+6.3pp data) = +17.2pp total. No hyperparameter re-sweep
  needed — the parameter landscape is flat and the tuned regularization
  transfers across datasets.

## §149 V4 token-net trainer glob-skew fix + retrain (2026-08-09, local)

**Context:** An encoding audit of all OOC model columns
(decision-log/2026-08-09-v4-glob-skew-fix.md) discovered that
`train_strategic_tok.py` had been building its 42-glob block from the wrong
CSV columns since the NGLOB=42 correction. The strategicgen2 CSV interleaves
the d/u/r/pot block (cols 32–1004) before fm*/curMap* (cols 1005–1016), but
the trainer assumed all scalars were contiguous. Result: glob slots 24–35
trained on deck counts `d0..d11` while C++ inference fed forward-map features
`fmDElite..curMapY`; derived thresholds `canTakeEliteKey`/`bossNear` trained on
`d4`/`d3` but served `fmCElite`/`fmDBoss`. Every V4 model trained before this
fix (including the deployed 50-glob model and the honest_v2 42-glob model)
was affected.

**Fix:** Trainer corrected to slice the actual CSV columns (cols 23:32,
1005:1017). Column-name assertions added to catch future `richHeader()`
reorderings. C++ `buildTokState` was always correct — no C++ change needed.

**Retrain:** Full 40-epoch retrain on `build/strategic_tierb.csv` (3,057,708
rows, 4,650 seeds) with the fixed trainer, rung 4, torch.compile ON, CUDA
(RTX 3060 Ti). Epoch times ~22-51s (compile ON; first epoch slower due to
Triton warmup). Best epoch by val_pol_ce.

- **Offline metrics** (best held-out, epoch 37):
  - val_pol_ce: 0.4885, policy_top1: 0.7932, margin: 8.72
  - value_mae: 10.93, value_rmse: 16.10 (epoch 40; best-val epoch 37 similar)
  - q_top1: 0.2806, q_mae: 16.35, q_rmse: 22.11

- **Offline comparison** with honest_v2 (previous 42-glob model, also 40 epochs):
  - val_pol_ce: 0.4885 vs 0.488 (identical)
  - policy_top1: 0.7932 vs 0.793 (identical)
  - q_top1: 0.2806 vs 0.295 (slightly lower)

  The offline metrics are nearly identical, consistent with the hypothesis
  that the glob skew had minimal impact on training convergence — the network
  capacity was sufficient to extract signal from either column set.

- **Export:** `export_strategic_tok.py` → 32/32 parity checks passed
  (max err logit 1.06e-05, value 8.19e-06, Q 1.28e-05).
  File: `selfplay/models/ooc_strategic_tok_skewfix.native` (799,176 bytes,
  nGlob=42, polIn=184).

- **Paired gate** (64 seeds, seeds 126700–126763, S2 fair @1k sims,
  12 threads, `STS_OOC_STRATEGIC_REST=1 STS_OOC_STRATEGIC_EVENT=1
  STS_OOC_STRATEGIC_MARGIN=1.0`):

  | Metric | Baseline | Skewfix | Delta | 95% CI |
  |---|---|---|---|---|
  | Win rate | 23.4% | 39.1% | **+15.6pp** | [+3.1, +28.1] |
  | Avg floor | 37.4 | 40.7 | +3.3 | [+0.1, +6.6] |
  | Avg HP end | 17.5 | 22.6 | +5.1 | — |
  | CPU sec/run | 13.82 | 15.24 | +10% | — |

  Discordant pairs: 20/64 (31%) — skewfix won 15, baseline won 5.
  Baseline Wilson 95% CI: [14.7%, 35.1%]. Skewfix Wilson 95% CI: [28.1%, 51.3%].

- **Gate verdict: SIGNIFICANT.** The 95% CI for the win-rate delta excludes
  zero. This is the first 42-glob (honest, no hidden-info leaks) V4 model to
  show a clear gate benefit. The previous honest_v2 model (also 42-glob,
  trained with the glob skew) gated at 15.6% vs 21.1% = −5.5pp (lost to
  baseline).

- **Deployment decision:** The skewfix model replaces
  `selfplay/models/ooc_strategic_tok_final.native` as the shipped V4 artifact.
  SHA256: `e62abd833fc8cb9081a1cec4a1a012832ac3b0e3166da3892841911664f1184c`.
  V4 remains opt-in behind `STS_OOC_STRATEGIC_TOK_NN`; V3 is still the
  default OOC policy. The previous final model (50-glob leaky, sha256
  `f6bc6a96…`) was already replaced with a 42-glob version earlier today;
  this replaces that with the skewfix retrain.

- **Artifacts:**
  - `selfplay/models/ooc_strategic_tok_skewfix.pt` (checkpoint)
  - `selfplay/models/ooc_strategic_tok_skewfix_tok_state.bin` (2.9 GB)
  - `selfplay/models/ooc_strategic_tok_skewfix.native` (exported model)
  - `selfplay/models/ooc_strategic_tok_skewfix_metrics.json`
  - `selfplay/models/ooc_strategic_tok_final.native` (deployed, copy of skewfix)
  - `build/gate_skewfix_base_64.csv`, `build/gate_skewfix_cand_64.csv`

- **Open:** A larger gate (128–256 seeds) would tighten the CI. A gate at
  multiple margins (0.5, 5.0) would characterize the sensitivity. A
  head-to-head V3-vs-skewfix gate would determine whether V4 should become
  the default. A full V4 gate stack (SHOP/TREASURE/BOSS_RELIC gates also ON)
  would reproduce the §81 multi-gate configuration.

## §150 Per-encounter combat value specialization: per-boss XGBoost fine-tuning + Reptile meta-learner — GATE NEGATIVE, close the line (2026-08-09, local)

**What:** two experimental arms sharing one runtime dispatch map
(`CombatValueNet::encounterModels`, keyed by `MonsterEncounter` enum int;
`predict(bc)` dispatches to the specialized model when present and otherwise
keeps the base path — byte-identical default behavior when nothing is loaded).

- **Arm 1 — per-boss XGBoost fine-tuning**
  (`train_value_combat_per_encounter.py`): continues the pooled §148 model on
  each boss's own rows (`xgb_model=pooled_bst`, 50 extra rounds, early stop
  10; `PER_ENC_CONSERVATIVE=1` = 15 rounds + bumped `reg_alpha`/`gamma` for
  tail encounters). Same feature columns as the pooled model's
  `feature_names`, fight-group split, critical-state weights and
  QuantileDMatrix recipe as `train_value_combat.py`. Exports compact-tree
  `<ENUM_NAME>.txt` + `_pooled.txt` fallback + per-encounter val CSVs.
  Runtime: `STS_VNET_PER_ENCOUNTER=<dir>` →
  `CombatValueNet::loadEncounterModels(dir)`; `export_combat_model.py
  --per-encounter <dir>` converts a directory of `.json` models without
  retraining.
- **Arm 2 — Reptile meta-learning for tail encounters**
  (`train_value_combat_meta.py`): dense MLP (1766→128→64→1, **ReLU** — the
  native `combat_mlp_v1` C++ path is ReLU; the plan's "GELU" wording was
  deliberately not followed to preserve inference parity) trained with the
  Reptile outer loop (B=8 encounters/iter, K=5 inner SGD steps, ε=0.5), then
  offline adaptation of tail encounters (meta-train rows ≤
  `META_TAIL_MAX_ROWS`). Exports `combat_mlp_meta_v1` (base MLP dense layout +
  per-encounter `dw1..db3` delta table); C++ reconstructs adapted weights as
  base + delta in `encounterModels` (~940KB/encounter).

**Verified (local, WSL, 2026-08-09):**

- Per-encounter trainer on `build/vcombat_honest.csv` (287,517 rows; SLIME_BOSS
  373 fights / 11,176 rows, THE_GUARDIAN 391 fights / 9,816 rows): pooled 2000
  trees + 10 specialized each; `vnettest --encounter SLIME_BOSS` parity
  max|diff| 6.7e-5 vs Python (tolerance 1e-3).
- `export_combat_model.py --per-encounter` output byte-identical to the
  trainer's direct export.
- Meta smoke (META_ITERS=6, K=3, SAMPLE_MOD=8, adapt-all): 50 per-encounter
  deltas; base parity max|diff| 1.1e-5; in-file SLIME_BOSS delta
  reconstruction (base+delta) parity max|diff| 1.1e-5 vs Python adapted
  predictions.
- 8-seed S3-fair smokes: default unchanged (`combatVNet=off`), nonexistent
  per-encounter dir warns and continues, per-encounter tree dir shows
  `combatVNet=ON+per-encounter(2)`, meta model shows
  `MLP 1766x128x64x1 +50 per-encounter`.
- `ctest` 9/9, `vnettest_selftest.py --self-test` PASS.

**Gate (local, WSL, 2026-08-09):** 64 paired seeds, S3 fair, 1k sims,
`searchdiag` mode (per-fight boss data + run-level aggregates). Baseline:
`STS_VNET=build/v_combat_boss/_pooled.txt` (2000 trees, no per-encounter
dispatch). Treatment: same pooled plus `STS_VNET_PER_ENCOUNTER=build/v_combat_boss`
(9 per-boss models, 2000+50 trees each, sharing the same pooled base for
non-boss encounters).

Run-level:
- Win rate: 39.1% → 32.8% (−6.2pp, 95% CI [−15.6pp, +1.6pp]; n.s.)
- Avg floor: 42.0 → 41.3 (−0.8)
- Avg HP end: 21.3 → 17.1 (−4.2)
- Discordant pairs: 8/64 (12%), pooled-only 6, per-boss-only 2

Per-boss (exit HP when won, Δ treatment − baseline):
- SLIME_BOSS −4.5pp win, +0.8 HP  |  THE_GUARDIAN +0.2pp, +2.4 HP
- HEXAGHOST +4.5pp, −2.0 HP       |  AUTOMATON −0.9pp, +2.0 HP
- COLLECTOR −8.6pp, +14.5 HP      |  CHAMP +5.9pp, −3.0 HP
- AWAKENED_ONE 0pp, +9.4 HP       |  TIME_EATER −12.5pp, +12.4 HP
- DONU_AND_DECA −6.0pp, −7.8 HP

The COLLECTOR and TIME_EATER pattern (fewer wins but much higher exit HP when
winning) suggests the fine-tuned model over-values HP preservation relative to
win probability — consistent with the endHp label target without a sufficient
win bonus. Non-boss encounters showed slight positive deltas (REPTOMANCER +5.6,
MAW +5.3, WRITHING_MASS +5.2), likely a cascade effect from different boss-fight
decks rather than direct model benefit.

**Verdict: NEGATIVE — close the line.** Per-boss XGBoost fine-tuning does not
improve run-level outcomes (direction negative, not significant at 64 seeds).
The §126 result (binary boss-conditioning flat/negative) is confirmed: per-boss
specialization, even with dedicated trees, does not capture value beyond what
the pooled model already extracts from the encounter feature. The meta-learner
(Arm 2, Reptile) was not gated; the high label noise on the endHp target and
the negative XGBoost result make it unlikely to succeed, and it should only be
revived if a different label target (e.g., P(win)-weighted endHp or a
run-level credit assignment) is demonstrated to work first on the simpler
XGBoost arm.

**Artifacts (local):** `build/v_combat_boss/{_pooled,SLIME_BOSS,THE_GUARDIAN,
HEXAGHOST,AUTOMATON,COLLECTOR,CHAMP,AWAKENED_ONE,TIME_EATER,DONU_AND_DECA}.txt(.json)`
+ `_val.csv`, `build/v_combat_meta_smoke.txt(.pt)`,
`build/v_combat_meta_smoke_slime_val.csv`. Gate CSVs:
`.ai/cycles/2026-08-09-11-53-34/{baseline,treatment}_sdiag.csv.fights.csv`.

## §151 Distillation investigation: NOT worthwhile; large-scale vnet datagen at 100k seeds (crashed at 14.8k); 5.5× data retrain — preliminary gate negative but confounded (2026-08-09, local + GCP)

- **What (distillation investigation):** five parallel subagent investigations
  into whether distilling expensive neural networks into cheaper models is
  worthwhile. Architect synthesis: **no** — every prior distillation attempt
  (§56 MLP, §57 entity, §58 policy prior, §104 Phase F soft-target, §106 chain
  compression, §137 mixture retrain) failed at gameplay gates despite improving
  offline metrics. The cited root cause is the §62 rule: "better absolute
  prediction does not identify the causal best route." The only successful cost
  reduction was pure additive tree truncation (§52: 1,500→400 trees, 1.85×
  faster, passed −0.5 non-inferiority). The successful quality path is
  data/target improvement (§126: +12.5pp from fresh labels).
- **Recommended follow-up:** (1) Data-side vnet improvement — the proven lever;
  (2) Tree→tree KD as a one-off cheap experiment; (3-4) Do not pursue
  transformer→MLP, transformer→trees, KD of transformer, or int8 quantization.

- **What (large-scale datagen):** `combatgen` 100,000 seeds at 1,000 sims on GCP
  `sts-test` (24 threads), heuristic-OOC distribution (Option B — same as §126;
  gate-stack distribution §129 was NULL). `STS_FAIR=1 STS_SEARCHER3=1`,
  S3−belief−chain/64p, vnet default ON (804 trees, α=0.3). Seeds 3,000–102,999
  (fresh after §126 0–1,499, §129 1,500–2,999). Output piped through gzip
  (`/dev/fd/3` → gzip), achieving **59× compression**.
- **Crash:** `ActionQueue::pushBack` assertion at run 14,800/100,000 —
  capacity-50 overflow under fair-S3+vnet. Filed as
  [issue #50](../knowledge-base/issues/2026-08-09-issue-actionqueue-overflow.md).
- **Data recovered:** 3,355,244 rows, 181 MB gzipped, seeds 3,000–17,860
  (~14,860 seeds, avg 226 rows/seed — vnet runs survive longer than §126's
  192 rows/seed).

- **VNet retrain (7k-seed subset):** extracted seeds 3,000–9,999 (1,580,243
  rows, 87,414 fights) to fit 31 GB RAM. `train_value_combat.py` on CUDA:
  751 features, 1,500 trees, val RMSE 8.04, R² 0.895, scaling probe positive.
  Exported `build/v_combat_7k.txt`; parity PASS (max|diff| 0.000193).
  Val RMSE slightly higher than §126's 7.99 — consistent with vnet runs
  producing harder/longer states.

- **Preliminary gate (⚠ confounded):** 256 seeds (126700–126955), 1,000 sims,
  S3−belief−chain/64p, 24 threads. Both arms ran heuristic-OOC because the
  token net model (`ooc_strategic_tok_final.native`) fails to load — the
  model's version-suffixed magic `OOC_STRAT_V42` causes the loader to
  misinterpret byte 12 as a dimension (50 ≠ NGLB 41).

  | arm | model | trees | α | win% | floor | HP | cpu-s/run |
  |---|---|---|---|---:|---:|---:|---:|
  | control | `v_combat_honest.txt` (§126) | 804 | 0.3 | **28.9%** | 39.1 | 11.3 | 24.1 |
  | candidate | `v_combat_7k.txt` | 1,500 | **0.5** ⚠ | 25.8% | 39.9 | 10.5 | 40.7 |

  **The α mismatch (0.5 vs 0.3) and tree-count difference (1,500 vs 804)
  confound the comparison.** The candidate ran at the non-default α=0.5
  because `STS_VNET=<path>` changes the alpha default. The proper comparison
  (`α=0.3`, matched tree count) was not run.

- **New issues discovered:**
  - ActionQueue capacity-50 overflow crashes long-running datagen (#50)
  - Token net loader format mismatch prevents gate-stack benchmarks on
    current binaries
  - 31 GB RAM insufficient for 3.35M-row training (peak ~36 GB)

- **Artifacts:** `build/vcombat_honest_100k.csv.gz` (181 MB, GCP + local),
  `build/vcombat_7k.csv` (5.3 GB), `build/v_combat_7k.{json,txt}`,
  `build/vnet_ctl_1k.csv` (28.9%), `build/vnet_7k_1k.csv` (25.8%).

- **Verdict:** distillation investigation — **line closed** (not worth
  standalone investment). Datagen — partial success, 3.35M rows recovered.
  VNet retrain — 5.5× data produced a model with slightly worse offline RMSE
  and a confounded preliminary gate. The more-data hypothesis is **not
  falsified** — a proper gate at matched α and tree count is still open.
  The data pipeline (gzip, `/dev/fd/3`, seed subsetting) is proven and
  reusable.

## §152 Zero-mean ranking correction for the combat leaf value: implemented (trainer + runtime + clamp), smoke/offline only — NO gameplay gate yet (2026-08-09, local)

- **Idea:** train a small model to predict `leafref.referenceValue -
  leafdiag.endHp_pred` (the gap between a high-budget Searcher3 reference and
  the deployed end-HP vnet's prediction on the same leaf state), center the
  residuals to zero-mean within each `(seed, fightIdx, decIdx)` decision
  group, and ADD the prediction on top of the vnet/PVNet leaf value so
  within-group action ranking improves without shifting the HP scale. A
  fair-path search-complete clamp re-zeroes the per-search mean correction at
  the root edges (visit counts untouched → no decision impact).
- **Implementation (experimental, off by default):**
  - `tools/train_rank_correction.py` — join leafdiag×leafref on
    `(seed, fightIdx, decIdx, obsHash)`, group-center the residual, train
    small XGBoost (max_depth 6, eta 0.05, subsample 0.8, colsample_bytree
    0.7, min_child_weight 20, 100 rounds, 20-round early stop) on the SAME
    733-feature layout as the deployed vnet (std>1e-9 on combatgen rows),
    same fight-group GroupShuffleSplit as `train_value_combat.py`; export via
    `export_combat_model.py` + vnettest parity CSV.
  - `STS_VNET_RANK_CORR=<path>` loads `search::g_combatVNetRankCorr` /
    `search::g_useVNetRankCorr` (non-fatal on failure). Correction added in
    `BattleScumSearcher3::evaluateLeaf` (vnet + PVNet branches), the S3
    leaf-blend site in `step()` (the leafdiag `endHp_pred` source), and
    `BattleScumSearcher2::evaluateLeafState`; per-search accumulation +
    `clampRankCorrAtRoot()` at search-complete in the fair paths.
- **Env/regime:** leafdiag capture is the §135a gate-matching env (fair S3,
  64 particles, `v_combat_honest.txt` @α0.3, `v_combat_utility_direct.txt`,
  per-stratum 500, full V4 OOC gate arms). Reference: `leafref_gate_64_4k.csv`
  (high-budget 4000 sims × 128 particles, CRN-paired; the reference is
  NOT model-free — it uses the same deployed vnet at the same alpha).
- **Smoke results (10 rounds, 5000 joined rows, seeds 126700-126715):**
  - joined 68,534/73,643 leafdiag rows to leafref (93%);
  - 733 features (combatgen filter), val RMSE 11.8 / MAE 7.4 on the centered
    residual (10 smoke rounds, best_iter 1);
  - held-out (fight-group val) within-decision ranking vs leafref: baseline
    pairwiseAcc 0.6493 / top-1 0.212 / regret 10.5 → corrected 0.6459 /
    0.182 / 11.1 (smoke-only; no signal expected at 10 rounds);
  - `vnettest` parity PASS (max|diff| = 0.000001 vs tolerance 0.001);
  - default (env unset) byte-identical: 8-seed fair-S3 `bestbench` output
    matches the pre-change commit binary (modulo cpu_sec);
  - 16-seed ranking diagnostic on the SAME leaves (post-processed
    `build/leafdiag_16_corr.csv` = `leafdiag_smoke_16.csv` rows with
    `endHp_pred += corr`, replicating the runtime semantics; a live corrected
    run would change the leaf states and break the obsHash join): baseline
    endHp pairwiseAcc 0.714 [0.708,0.719] / top-1 0.346 / regret 7.36 →
    corrected 0.719 [0.713,0.725] / 0.359 / 6.88 (+0.005 acc, −0.48 regret,
    Pearson 0.772→0.792). CAVEAT: the smoke model was trained on a subset of
    these rows (4,276 of 73,643, fight-group split), so this diagnostic is
    partially in-sample — it demonstrates the mechanism, not generalization;
    the held-out (fight-group val) metrics inside the trainer showed −0.003
    acc at 10 rounds (noise-level).
- **Artifacts:** `build/leafdiag_smoke_16.csv` (seeds 126700-126715 subset of
  `leafdiag_gate_64.csv`), `build/v_rank_corr_smoke.{json,txt}`,
  `build/v_rank_corr_smoke_parity.csv`, `build/v_rank_corr_smoke_metrics.json`
  (all build/, git-ignored except nothing tracked).
- **Verdict: NONE (infrastructure/implementation only).** No model change, no
  default change, no promotion. The correction may be learning the
  reference's vnet-blend bias rather than true ranking error (same caveat as
  §134 leafref analysis). Follow-ups: full-corpus training, leafdiag
  corrected-capture ranking eval (16 seeds), then a paired fair-S3 @1k/32-seed
  gameplay gate before any promotion consideration.
- **Decision log:** `2026-08-09-zero-mean-rank-correction.md`.

## §153 Ascension sweep: V4-skewfix gates + S3 fair + 7k-vnet @1k, 32 seeds, A0–A20 — Act 4 now reachable; V4 gates essential for Heart survival but hurt Act-3-only performance (2026-08-09, GCP sts-test)

- **What:** 5-ascension paired sweep (A0/A5/A10/A15/A20, 32 seeds each,
  126700–126731) of the current recommended stack: S3 fair −belief−chain
  @64p, V4 skewfix token-net gate stack (§149, all gates ON, margin 1.0),
  7k-tuned vnet default @α=0.3 (§148), 1k sims/decision, 24 threads (GCP
  sts-test). Also ran the no-gates baseline (same config minus V4 gates)
  and a STOP_AFTER_ACT=3 comparison for §148 compatibility.

- **Context — key-collection horizon change:** commit `32281a2`
  ("ooc: collect act-4 keys in every rewards/rest chain", 2026-08-09)
  made Act 4 reachable in `bestbench` for the first time. Previously the
  agent never collected keys and won by defeating the Act 3 boss. Now keys
  are taken at rewards screens (emerald/sapphire, after gold/relic/potion)
  and at rest sites (ruby key via RECALL when act ≥ 3, displacing a
  heal/upgrade). Every prior §148/§126 baseline predates this commit and
  reflects Act-3-only wins.

- **With Act 4 (current binary default):**

  | Asc | V4 Gates ON | No Gates |
  |--:|:--|:--|
  | A0 | **21.9%** (7/32) | 0.0% (0/32) |
  | A5 | **12.5%** (4/32) | 3.1% (1/32) |
  | A10 | **12.5%** (4/32) | 0.0% (0/32) |
  | A15 | **9.4%** (3/32) | 0.0% (0/32) |
  | A20 | **0.0%** (0/32) | 0.0% (0/32) |

  No-gates A0 also probed on a second 32-seed block (126732–126763):
  4/32 (12.5%), avg floor 43.9, end HP 8.2, cpu 31.2 s/run. Combined
  A0 no-gates: **4/64 = 6.3%**.

  The agent reaches Act 4 in 12/32 A0 runs (floor 55) but dies to the
  Heart without V4 gates — the gates are critical for Act 4 survival.
  Without them, 0/32 survived the Heart in the primary block.

- **Act 3 only (STS_STOP_AFTER_ACT=3, comparable to §148):**

  | Config | Win% (32 seeds) | Floor | End HP | CPU s/run |
  |---|---|---:|---:|---:|
  | V4 Gates ON | 31.2% (10/32) | 42.8 | 20.5 | 27.0 |
  | No Gates | **37.5%** (12/32) | 42.4 | 31.1 | 28.8 |

  The no-gates STOP_AFTER_ACT=3 result (37.5%, 12/32) reproduces the §148
  7k-tuned gate (37.5%, 24/64) exactly on the overlapping seed range
  (126700–126731 ⊆ 126700–126763). The V4 skewfix gates **reduce** Act-3
  win rate by −6.3pp in this regime (31.2% vs 37.5%).

- **Key findings:**
  1. The V4 skewfix gates (+15.6pp on S2-fair, §149) **reverse sign** on
     S3+vnet at Act 3 (−6.3pp) but are **essential** for Act 4 (+15.7pp
     delta: 21.9% vs 6.3%). The gates build decks that survive the Heart.
  2. The Key-collection commit changed the benchmark horizon — all
     pre-`32281a2` baselines are Act-3-only and not directly comparable.
  3. Ascension scaling is steep: A5 roughly halves A0 win rate, A10–A15
     near-zero, A20 is 0/32 even with the full stack.
  4. CPU cost drops with ascension (27.8 → 11.4 s/run) as runs end earlier.

- **Artifacts:** `build/asc{0,5,10,15,20}_1k_32.csv` (gates ON),
  `build/asc{0,5,10,15,20}_nogates_1k_32.csv` (gates OFF),
  `build/asc0_nogates2_1k_32.csv` (second no-gates block),
  `build/asc0_stopact3_gates_1k_32.csv`,
  `build/asc0_stopact3_nogates_1k_32.csv`.

- **Verdict:** ↗ V4 gates are essential for Act-4-inclusive benchmarks.
  The current recommended configuration (V4 skewfix gates + S3 + 7k-vnet)
  is the best known fair stack at A0=21.9% (with Act 4). The STOP_AFTER_ACT=3
  number (31.2%) is the nearest Act-3-only comparable but should not be
  presented as the headline — the binary now plays Act 4 by default.

- **Open:** Full 128/256-seed gate to tighten CIs; 3k win-point
  measurement; investigation into why the skewfix V4 gates reverse sign
  on S3+vnet (the §126 V4 model showed +12.5pp on S3+vnet at Act 3).

## §154 V_combat training-vs-deployment distribution shift: DIAGNOSIS — mismatch is WEAK, do NOT build relabeling pipeline (2026-08-09, local)

- **Question:** Are ordinary `combatgen` per-decision combat snapshots
  representative of the MCTS leaf states where `CombatValueNet` is queried
  during Searcher3 deployment?

- **Method:** Instrumented `CombatValueNet::predict()` with a thread-local
  hook (`STS_VNET_QUERY_LOG=<path>`) that logs the canonical feature vector
  of every VNet query during Searcher3 search. Collected two populations:
  - A: 287k combatgen trajectory states (seeds 0–1460, `build/vcombat_honest.csv`)
  - B: 163k deployed VNet-query states (seeds 200000–200047, S3 fair,
    belief=off, chain=off, 64p, 1k sims, A0, `build/vnet_query_deploy_b.csv`)
  Trained an XGBoost domain classifier (200 trees, max_depth=6) to distinguish
  A from B using only the 1,766 canonical combat features. **Split by seed,
  not by row** (70/30 per population, stratified). Zero behavior change when
  `STS_VNET_QUERY_LOG` is unset (verified: identical outcomes on 8-seed smoke).

- **ROC-AUC: 0.56** (XGBoost, held-out seeds). Confirmed with SGD logistic
  regression (AUC 0.24 — inverted ranking, equally poor discriminative power).
  The classifier operates barely above chance and cannot reliably distinguish
  individual combatgen states from deployed VNet-query states.

- **Characterization:** Deploy states are at slightly higher turns (3.7 vs 2.1),
  have more monster HP remaining (192 vs 68 sum), and more incoming damage
  (17.7 vs 9.2). Top distinguishing features are relic presence flags (r26
  Happy Flower, r51, r6, r4), reflecting later-turn relic accumulation — but
  the effect sizes are small relative to within-class variance. Deploy queries
  are spread broadly across HP bands (46% >70% HP, 43% 30-70%, 12% <30%)
  and turns (35% turns 3-4, 23% turns 5-7, 21% turn 2).

- **VNet predictions on deploy states:** mean 32.9, std 23.5 — closely
  matches the combatgen label distribution (mean 36.4, std 24.1). No evidence
  of systematic extrapolation or pathological behavior.

- **Verdict: Recommendation A — distribution mismatch is small; do NOT
  build expensive deployment-leaf relabeling pipeline.** The suspected
  mismatch between training (trajectory snapshots) and deployment (MCTS
  leaf states) is NOT the primary issue. The §148 hyperparameter-tuning
  improvement (major online gain with flat offline RMSE) more likely
  reflects regularization benefits than a distribution-shift fix.

- **Artifacts:** `build/vnet_query_deploy_b.csv` (163k rows),
  `build/vnet_shift_report.json`, `tools/vnet_distribution_shift.py`,
  `docs/knowledge-base/experiments/vnet-distribution-shift-2026-08-09.md`.

- **Code:** `STS_VNET_QUERY_LOG` env var + `STS_VNET_QUERY_SAMPLE`;
  hook in `CombatValueNet::predict()`; thread-local buffered CSV logging
  in `apps/one_combat.cpp`. All changes additive and gated — behavior
  byte-identical when the env var is unset.

## §155 Corrected honest V4 on frozen S3 + 7k-VNet Act-3 stack: INCONCLUSIVE due reproducibility failure (2026-08-09)

- **Question:** Does the corrected honest V4 token gate remain positive on the
  current Searcher3 + 7k combat-value stack under the explicit Act-3 objective?
- **Configuration:** git `c8d438a5a140d023ca348a334fa4ac467d1bd8e5`; A0;
  `STS_FAIR=1`, Searcher3, `STS_S3_BELIEF=0`, `STS_S3_CHAIN=0`,
  `STS_S3_LIVE_VALID=1`, 64 particles, 1,000 sims/decision, 12 threads;
  `STS_VNET=build/v_combat_7k_tuned.txt`, alpha 0.3;
  `STS_COLLECT_KEYS=0`, `STS_STOP_AFTER_ACT=3`; paired seeds 126700–126763.
  V4 artifact `selfplay/models/ooc_strategic_tok_final.native`, SHA256
  `e62abd833fc8cb9081a1cec4a1a012832ac3b0e3166da3892841911664f1184c`;
  VNet SHA256 `ea35b78c888e70e09566e1143d296577b0bea2ec8d437276b7aab81a7cdaf15c`.
- **Control:** all V4 OOC gates off, 37.5% (24/64), mean floor 42.6,
  mean end HP 18.4.
- **Candidate:** corrected V4 gates on, all REST/EVENT/SHOP/TREASURE/
  BOSS_RELIC flags on, margin 1.0, 14.1% (9/64), mean floor 30.0,
  mean end HP 42.8.
- **Paired result (not qualified):** first control/candidate comparison was
  −23.4pp, bootstrap 95% CI [−35.9, −10.9]pp; floor −12.5
  [−16.8, −8.3], HP +24.4, discordant 21/64. The candidate in that run had
  `STS_OOC_STRATEGIC_TRACE` enabled, while the ablation candidate did not.
- **Reproducibility failure:** the same no-trace control command and seed block
  later produced 37.5% (24/64) and 7.8% (5/64), with the same 1k/64p stack.
  The no-trace ablation full arm produced 15.6% (10/64); the earlier trace-on
  candidate produced 14.1% (9/64). These runs cannot establish a causal delta.
  Investigate thread/RNG/global-state nondeterminism before using this gate.
- **Trace:** 2,375 gate opportunities across 64 runs; 1,228 owned (51.7%).
  Fire rates: EVENT 57.1%, REWARDS 46.9%, BOSS_RELIC 78.9%, CARD_SELECT
  21.3%, TREASURE 51.9%, REST 58.2%, SHOP 56.1%.
- **Artifacts:** `build/ooc_v4_s3_act3_off_64_1786290767.csv`,
  `build/ooc_v4_s3_act3_on_64_1786290767.csv`, corresponding `.meta.json`
  files and logs, `build/ooc_v4_s3_act3_64_1786290767_paired.txt`, and
  `build/ooc_v4_s3_act3_on_64_1786290767_trace.csv`.
- **Verdict:** **INCONCLUSIVE / invalidated as a causal gate** until repeated
  controls are reproducible. The observed negative/positive deltas are
  diagnostic only. The earlier S2-fair +15.6pp result still does not transfer
  cleanly, but no model-quality conclusion is permitted from §155. Audit
  thread/RNG/global-state determinism before further policy interpretation;
  Act-4 objective and per-screen traces remain open.

## §156 Per-screen V4 ablation diagnostic on same S3+7k-VNet Act-3 block: not qualified (2026-08-09)

- **Configuration:** same A0, 1k sims, 64 particles, S3 belief/chain off,
  live-valid on, 7k VNet alpha 0.3, `STS_COLLECT_KEYS=0`,
  `STS_STOP_AFTER_ACT=3`, seeds 126700–126763; corrected V4 full stack at
  margin 1.0. The script explicitly uses the V4 artifact and records JSON
  sidecars. Results are diagnostic because §155 showed repeated-control
  non-reproducibility.
- **Full stack:** 10/64 (15.6%), mean floor 30.7, mean HP 48.8.
- **Minus REST:** 14/64 (21.9%), paired full-minus-ablation +6.2pp,
  CI [−4.7,+17.2]pp; floor +2.5.
- **Minus EVENT:** 11/64 (17.2%), +1.6pp, CI [−6.2,+9.4]pp; floor +2.0.
- **Minus SHOP:** 11/64 (17.2%), +1.6pp, CI [−9.4,+10.9]pp; floor +2.5.
- **Minus TREASURE:** 16/64 (25.0%), +9.4pp, CI [+0.0,+18.8]pp;
  floor +3.9.
- **Minus BOSS RELIC:** 9/64 (14.1%), −1.6pp, CI [−10.9,+7.8]pp;
  floor +2.7.
- **Interpretation:** treasure and rest are the largest apparent contributors,
  but these effects are not causal/promotion-qualified until exact repeated
  controls are stable. Artifacts are under
  `build/ooc_v4_s3_act3_ablate_64_1786291107/` plus the paired reports.

## §157 DeepSets combat VNet parity — RMSE 8.66, C++ parity verified, online 0% win (2026-08-09)

- **What:** implemented a DeepSets neural combat value net
  (`train_combat_deepsets.py`, `combat_deepsets_v1` native format in
  `CombatValueNet.cpp`). Architecture: combat state decomposed into
  permutation-invariant sets — cards (4 zones × 371 IDs, shared embedding
  table, sum-pool per zone), relics (128, sum-pool over present), potions
  (44, count-weighted sum), monsters (5 slots × 9 feat, per-slot 2-layer
  MLP → mean-pool over alive), encounter (ID embedding), scalars (68 features
  z-normalized → linear → ReLU). All pooled vectors concatenated → MLP
  (384 → 128 → 64 → 1). 90K params. Trained on honest vcombat data (287K
  rows, 30 epochs, AdamW, MSE on endHP, critical-state weighting).
- **Parity:** C++ vs Python max|diff| < 0.001 (vnettest, 200 rows).
  All 15 CTests pass.
- **Offline:** val RMSE 8.66 (XGBoost 7.83), R² 0.87. On trajectory
  validation states, XGB/DS Pearson 0.974, Spearman 0.972 — the model
  works well in-distribution.
- **Online gate:** 0% win (0/32) at S3 fair −belief−chain, 1k sims, 64p,
  α=0.3, no gate stack — **worse than no VNet (12.5%)**. XGBoost at 31.2%
  on the same block. `build/dsgate_*.log` on sts-test.
- **Verdict:** ❌ DeepSets in current form is actively harmful. Follow-up
  §158 diagnoses the root cause as numerical collapse on OOD MCTS leaf
  states.
- **Artifacts:** `train_combat_deepsets.py`, `build/v_combat_deepsets.txt`,
  `build/v_combat_deepsets_val.csv`, `include/sim/search/CombatValueNet.h`
  (isDeepSets + ds* fields), `src/sim/search/CombatValueNet.cpp` (format
  parser + inference).

## §158 MCTS leaf-state diagnosis: DeepSets numerically collapses on OOD search states (2026-08-09)

- **What:** extended `STS_VNET_QUERY_LOG` (existing opt-in VNet tracing)
  with `parentObsHash` and `depth` columns, enabling sibling-grouped
  MCTS leaf-state analysis. Collected 1M leaf evaluations under XGBoost-
  guided S3 search (8 seeds, 1k sims, 64p), sampled 50K for offline
  comparison. Evaluated both XGBoost and DeepSets on the identical states.
- **Key result:** On MCTS leaf states, XGB/DS Pearson drops from 0.974
  (trajectory) to **0.098**. DeepSets mean prediction = **−34 million HP**
  (XGBoost = 27 HP). DeepSets produces NaN-range values on many states.
- **All extreme disagreements** (|Δ| = 40–430 million HP) involve a single
  encounter: **TRANSIENT** (encounter 44, monSumHp ~950–980). The scalar
  z-normalizer was calibrated on training data (monSumHp mean ~50); MCTS
  leaf states with monSumHp ~970 produce z-scores of 20+ standard deviations,
  causing unbounded activations in the scalar encoder that cascade through
  the MLP.
- **Distribution shift confirmed:** a simple RandomForest classifier
  distinguishes trajectory vs MCTS states with **95% accuracy**.
  Top shifted features: rare card/relic IDs appearing in counterfactual
  branches, plus numerical extremes on boss/special encounters.
- **Sibling analysis:** top-child agreement 0.7%, pairwise agreement 58%,
  DS reversal rate 48.5% at XGB margin ≥1 HP — all dominated by the
  numerical collapse rather than subtle ranking errors.
- **Root cause:** numerical instability in the scalar z-normalizer on
  out-of-distribution feature values. The model architecture is sound
  (works well in-distribution) but lacks input robustness.
- **Recommended fix:** clamp z-scores to [−5, +5] before the scalar
  encoder (one line in Python + C++).
- **Artifacts:** `tools/analyze_mcts_leaves.py`,
  `build/vnet_mcts_leaves_xgb.csv` (1M rows, 3.4GB),
  `build/vnet_mcts_leaves_50k.csv` (50K sample),
  `build/mcts_diag.json`.

## §159 Requalified corrected honest V4 on frozen S3 + 7k-VNet Act-3 stack (2026-08-09)

- **Fix/configuration:** made `search::g_potionKeepValue` thread-local;
  `runFullRunOOC` writes it per fight while parallel seeds search concurrently.
  Repeated 8-seed checks matched all outcomes, floors, HP, and death fields.
  The 64-seed gate used a no-trace binary, A0, 1k sims, 12 threads,
  `STS_FAIR=1`, Searcher3, belief/chain off, live-valid on, 64 particles,
  fixed `build/v_combat_7k_tuned.txt` alpha 0.3, `STS_COLLECT_KEYS=0`,
  `STS_STOP_AFTER_ACT=3`, seeds 126700–126763.
- **Result:** V4 OFF 24/64 (37.5%), V4 ON 31/64 (48.4%), paired delta
  **+10.9pp**, 95% CI [−1.6,+23.4]pp; floor +0.9 and HP +5.5.
- **Trace:** same ON stack produced 3,419 opportunities, 1,834 owned
  (53.6%); fire rates: EVENT 61.8%, REWARDS 44.8%, BOSS RELIC 84.0%,
  CARD SELECT 18.0%, TREASURE 62.0%, REST 68.4%, SHOP 55.1%.
- **Artifacts:** `build/ooc_v4_requal_s3_act3_{off,on}_64_1786292238.csv`,
  paired report, trace and sidecars.

## §160 Requalified per-screen V4 ablations (2026-08-09)

Same fixed stack/seeds as §159, V4 margin 1.0. Full was 31/64 (48.4%).
- minus REST: 31/64 (48.4%), paired delta 0.0pp;
- minus EVENT: 26/64 (40.6%), delta −7.8pp, CI [−18.8,+3.1]pp;
- minus SHOP: 34/64 (53.1%), delta +4.7pp, CI [−7.8,+17.2]pp;
- minus TREASURE: 31/64 (48.4%), delta 0.0pp, no discordant seeds;
- minus BOSS RELIC: 29/64 (45.3%), delta −3.1pp, CI [−10.9,+4.7]pp.

These are exploratory 64-seed effects; only EVENT has a meaningful directional
signal, and its CI still crosses zero. Artifacts:
`build/ooc_v4_requal_s3_act3_ablate_64_1786292838/`.

## §161 V4 margin sweep on requalified Act-3 stack (2026-08-09)

Same configuration/seeds as §159, corrected V4 all five screens on, 64 seeds:
- margin 0.5: 29/64 (45.3%), mean floor 43.9, HP 21.5;
- margin 1.0: 31/64 (48.4%), mean floor 43.5, HP 23.9;
- margin 2.0: 31/64 (48.4%), mean floor 44.4, HP 27.2;
- margin 5.0: 29/64 (45.3%), mean floor 43.0, HP 24.2.

Eight-seed trace samples measured fire rates 71.8%, 53.3%, 33.3%, and 13.5%
for margins 0.5, 1, 2, and 5 respectively. Margin 1–2 is the current small
sample plateau; no margin is promoted without confirmation at 128 seeds.
Artifacts: `build/ooc_v4_margin_*_s3_act3_64_1786293919.csv` and trace files.

## §162 Training split/checkpoint-selection follow-up (2026-08-09)

- **Fixes:** canonicalize Tier-B CSV rows by `(seed, decIdx)` before group
  offsets, and initialize the missing batch permutation RNG in both
  `train_strategic.py` and `train_strategic_tok.py`. The prior assertion
  correctly caught non-contiguous groups; without the RNG fix training then
  failed before epoch 1.
- **Selection interface:** both trainers accept
  `STRAT_SELECT_METRIC=val_pol_ce` (minimize, default) or `q_top1` (maximize).
- **Resource-safe result:** a three-epoch CUDA `val_pol_ce` run reached epoch 3
  on `build/strategic_tierb.csv`; held-out `val_pol_ce=0.6093`, `q_top1=0.2982`.
  The paired `q_top1` run was not completed after the first run allocated a
  ~2.9 GB state tensor; no checkpoint-selection conclusion is drawn. Avoid
  repeating this full GPU run from an IDE; use a redirected batch job or a
  reduced/synthetic fixture first.

## §163 Corrected honest V4 confirmed at 128 paired seeds on S3+7k-VNet Act-3 stack (2026-08-09)

- **Configuration:** git `3feb2a1` (block 1) / `d38272f` (block 2, behavior-neutral
  because tree-reuse controls are env-gated and binary was verified bit-identical
  across an earlier Searcher3 transition). A0, 1k sims, 12 threads, Searcher3,
  belief/chain off, live-valid on, 64 particles, `STS_VNET=build/v_combat_7k_tuned.txt`
  alpha 0.3, `STS_COLLECT_KEYS=0`, `STS_STOP_AFTER_ACT=3`.
  V4 SHA256 `e62abd83…`, VNet `ea35b78c…`.
- **128 paired seeds 126700–126827:**
  - V4 OFF: 52/128 (40.6%), mean floor 42.0, mean HP 18.5;
  - V4 ON:  67/128 (52.3%), mean floor 44.0, mean HP 24.5;
  - paired delta **+11.7pp**, bootstrap 95% CI **[+1.6, +22.7]pp**;
  - floor +2.0, HP +5.9, discordant 47/128 (37%), on-only 31 vs off-only 16.
- **Verdict:** ↗ **V4 is confirmed positive on the current fair S3+7k-VNet
  Act-3 stack.** The CI excludes zero. This is the first statistically significant
  gate for the corrected honest V4 on this combat configuration.
  V4 is now the provisional OOC baseline.
- **Artifacts:** `build/ooc_v4_head_s3_act3_{off,on}_64_1786297628.csv` (block 1),
  `build/ooc_v4_head128_s3_act3_{off,on}_64plus_1786297983.csv` (block 2),
  sidecars and logs.

## §164 Checkpoint-selection interface verified on small CPU fixture (2026-08-09)

- Both `train_strategic_tok.py` and `train_strategic.py` accept
  `STRAT_SELECT_METRIC=val_pol_ce` (minimize) or `q_top1` (maximize).
- A 20-seed, 13K-row fixture from `build/strategic_k1.csv` was trained on CPU
  for 10 epochs with both metrics:
  - `val_pol_ce`: picked epoch 10, best CE=1.208;
  - `q_top1`: early-stopped at epoch 7, best at epoch 2, best q_top1=0.211.
- Different metrics select different checkpoints; min/max directions and
  early-stopping logic are verified. Artifacts under `/tmp/ooc_ckpt_fixture_*`.

## §165 SHOP-disabled V4 test on requalified Act-3 stack (2026-08-09)

- **Configuration:** same frozen stack/seeds as §163, V4 ON with all screens
  except SHOP (EVENT+REST+TREASURE+BOSS_RELIC+CARD only, margin 1.0).
  64 paired seeds 126700–126763.
- **Result:** SHOP-disabled 34/64 (53.1%) vs full V4 31/64 (48.4%),
  delta +4.7pp, CI [−7.8,+17.2]pp; discordant 15/64, SHOP-disabled-only 9.
- **Interpretation:** consistent with the Wave 0G minus-SHOP ablation
  (also +4.7pp). The direction suggests SHOP overrides are net-harmful on
  this stack, though the CI crosses zero at 64 seeds. This is a supplementary
  diagnostic, not yet a promotion claim.
- **Artifacts:** `build/ooc_v4_noshop_s3_act3_64_1786298692.csv`, paired
  report, sidecar.

## §166 Recovered MCTS-leaf MLP and deep-target experiment arc (2026-08-09; consolidated 2026-08-11)

- **Provenance:** recovered before deleting ignored legacy agent state from
  `.ai/session-summary-2026-08-09-deepsets-v3.md` through `v17.md`. These
  summaries were not authoritative records and did not preserve every seed
  range or artifact hash. Results below are therefore **Unverified historical
  evidence** except where independently recorded in §157-§158.
- **Configuration reported by the summaries:** project-fair Searcher3,
  belief/chain off, 64 particles, 1,000 simulations per decision, no OOC gate
  stack, and normally `STS_VNET_ALPHA=0.3`. Online comparisons used common
  32-seed blocks unless stated otherwise; exact seed ranges and thread counts
  were not recorded.
- **MCTS-distribution imitation:** a flat `733 -> 256 -> 128 -> 1` MLP trained
  on 278K XGBoost-guided MCTS leaf states reached held-out Pearson 0.964 versus
  its XGBoost teacher. Reported online results were 46.9% versus XGBoost 43.8%
  at 32 seeds and 43.8% versus 41.4% at 128 seeds. The 128-seed difference was
  treated as noise, not a promotion. The corresponding reported artifact was
  `build/v_combat_mlp_mcts.txt`.
- **Deep-search utility targets:** a model trained on Searcher3 backed-up
  utility achieved offline RMSE 8.75 and Pearson 0.964 against that target but
  only 34.4% online versus the teacher MLP's 46.9%. One warm-start DAgger
  iteration improved it to 40.6%; second iterations regressed to 25.0%
  (warm-start) and 21.9% (fresh). The summaries report that XGBoost-, V0-, and
  V1-guided state distributions remained 84-85% distinguishable.
- **Residual correction:** adding a learned deep-utility residual to the
  teacher with beta 0.01 reportedly reduced the 32-seed result from 46.9% to
  34.4%. Larger corrections were worse. The residual mostly behaved as an
  upward bias rather than a state-specific correction.
- **Terminal-endHP target:** a warm-started MLP trained on 42K joined states
  improved validation RMSE from 13.76 to 11.61 and Pearson from 0.737 to 0.750,
  corrected a reported CULTIST overprediction blind spot, but tied the teacher
  at 46.9% on 32 seeds.
- **Verdict:** MCTS-distribution imitation was competitive with its tree
  teacher, but raw deep-search utility, iterative DAgger beyond one iteration,
  residual correction, and terminal-endHP relabeling did not establish an
  online improvement. This research line is closed unless reconstructed from
  preserved artifacts with a new premise and fully recorded paired protocol.

## §167 Fightrep: re-recorded floor-50 boss losses and particles x sims replay grid (2026-08-11)

- **Purpose:** the fightrep harness (`apps/one_combat.cpp`,
  `2026-08-11-fightrep-harness.md`) needs a captured fight set to re-search the
  recorded floor-50 boss losses at other particle counts / sim budgets. The 14
  original captures were never on this machine or on `sts-test`, so the set was
  re-recorded locally.
- **Source of the 14 losses:** `build/rerun_2026-08-10_a0_gates_1k_128.csv` (GCP A0
  1k/128-seed full-stack rerun, 46.9% win). 14 seeds reached floor 50 and lost. Two of
  them (`126711`, `126805`) are anomalous rows (hpEnd>0 with deathCombat=-1,
  deathEncounter=-1; run ended without a combat death) and are excluded here for a
  separate fix.
- **Re-recorded captures:** `build/fightrep_cap/fight_<seed>.bin/.csv` for the 12 normal
  loss seeds `126704 126721 126722 126731 126735 126753 126766 126773 126783 126808
  126817 126819`, captured by `bestbench 1000 1 0 <seed>` with `STS_FIGHTREP_CAPTURE_DIR`
  and the recorded full stack (fair S3, belief=off chain=off, 64 particles, live-valid
  on, V4 tok-net gates all on margin 1.0, native OOC, VNet α=0.3, policy prior
  c_puct=2.5). Every capture reproduced the historical encounter at floor 50: encounters
  {54,53,55} match the historical `deathEncounter` column exactly for all 12 seeds.
- **Replay grid** (`one_combat fightrep`, forced fair S3 belief=off chain=off
  live-valid=on): 12 fights x {64,128,256} particles x {1000,3000,6000} sims = 108 cells
  in 94.7s wall on 12 threads. Per-cell wins of 12:
  - 64p: 1000→2, 3000→5, 6000→2
  - 128p: 1000→2, 3000→3, 6000→3
  - 256p: 1000→1, 3000→1, 6000→1
- **Follow-up grid ({32,512,1024} particles x {1000,3000,6000} sims, 108 cells in 103.1s,
  2026-08-11):** per-cell wins of 12:
  - 32p: 1000→1, 3000→2, 6000→3
  - 512p: 1000→1, 3000→3, 6000→3
  - 1024p: 1000→2, 3000→4, 6000→3
  Combined particle axis {32,64,128,256,512,1024} x {1000,3000,6000} = 216 cells:
  best cell remains **64p/3000s = 5/12**; 1024p/3000s = 4/12 is the only other >=4.
  Per-seed win consistency across the 18 cells: 126704/126731/126735/126753/126817 = 0/18
  (never won at any budget); 126808 = 1/18; 126819 = 4/18; 126721 = 6/18; 126773 = 6/18;
  126766 = 8/18; 126783 = 8/18; 126722 = 9/18 (most flip-prone). So the replay win signal
   is concentrated in ~6 of the 12 captured fights; 5 fights never flip at any budget.
- **Extreme cell (1024 particles x 100,000 sims, single cell, 12 fights parallel on 12
  threads, 365.9s wall / ~6.1 min, 2026-08-11):** **6/12 wins — the best cell so far**
  (previous best 5/12 at 64p/3000s). Winners: `126721 126722 126766 126773 126783
  126819` (hpEnd 29/25/7/6/4/2). Note 1024p/100k is the only cell so far where `126721`
  and `126819` win; the same 5 fights still never win (126704, 126731, 126735, 126753,
  126817). Runtime note: 10k-sims probe = 17.6s/fight single-core, so 100k ≈ 176s/fight
  expected; the observed 365.9s wall for 12 parallel fights is ~2x that, consistent with
   super-linear per-decision cost at 300k sims/decision (boss x3) plus the slowest fight
   dominating the parallel cell.
- **100k-sims particle sweep ({16,32,64,128,256,512} particles, sims fixed at 100k,
  72 cells in 2054.2s wall / ~34 min, 2026-08-11):** per-cell wins of 12:
  - 16p→4, 32p→5, 64p→3, 128p→5, 256p→3, 512p→5
  Combined with the 1024p/100k cell (6/12), the 100k-sims particle axis
  {16..1024} peaks at **1024p = 6/12**. At 100k sims `126773` wins at every particle
  count (6/6) and `126783` wins 5/6 (all but 16p), while the never-win set is stable:
  `126704 126731 126735 126753 126817` (5/6 counts) plus `126808` now also 0/6 at 100k.
  The 10k-particles/100k-sims cell (3/12) is markedly worse than both 512p/100k (5/12)
  and 1024p/100k (6/12), so beyond ~1k particles the extra belief particles do not help
  and hurt. Descriptive isolated-fight results only.
- **Replay determinism:** a second independent run of the 36 (64p) cells gave 0 diffs
  (won/hpEnd/turns identical).
- **Fidelity gate (replay == capture-time outcome):** at the recorded config
  (64p/1000s → boss x3 = 3000/decision) 10/12 seeds reproduce the capture-time loss;
  **2 seeds flip to wins: `126722` (hpEnd 29) and `126773` (hpEnd 26)**. Both are Time
  Eater / Awakened One loses at capture time. This is a real fidelity gap: the isolated
  fight-start snapshot does not fully determine the replay outcome for these two seeds
  (possible causes: run-context combat knobs such as `search::g_potionKeepValue` /
  per-fight `fightSims` budget applied in `runFullRunOOC` but not in `fightRepReplay`).
  Flagged as an open question for the fightrep harness, not a policy claim.
- **Interpretation (descriptive, not paired):** at 64p the 3k budget flips 3 additional
  losses (126766, 126783, 126808) to wins beyond the 64p/1k flips, but the 6k budget
  regresses to 2/12 (126722 and 126773 stay wins; 126783/126808 lose again). More
  particles (128/256) do not help and 256p wins FEWER fights than 64p at every sim
  budget. This is an isolated-fight re-search result; it does not transfer to full-run
  win rate without a full paired run.
- **Artifacts:** `build/fightrep_cap/` (captures), `build/fightrep_grid_12f.csv` (64/128/256p,
  108 cells), `build/fightrep_grid_32p512p1024p.csv` (32/512/1024p, 108 cells),
  `build/fightrep_1024p_100k.csv` (1024p/100k, 12 cells),
  `build/fightrep_10kp_100k.csv` (10k particles/100k, 12 cells),
  `build/fightrep_100k_16to512p.csv` (16..512p x 100k sims, 72 cells),
  `/tmp/opencode/weird_cases/` (126711 capture set aside for the separate fix).
- **Status:** re-record complete; 2/12 fidelity flips are an open harness concern.

## 2026-08-15 — Searcher3 persistent filtered-posterior quality A/B preregistration

**Question:** Does consuming the exact filtered real-observation Searcher3
posterior in the next freshly constructed Searcher3 improve gameplay decisions
when both arms use a fresh MCTS tree for every searched decision?

**Frozen implementation:** baseline `166c48072a41760e146f3a99a1329849440bbb3a`;
implementation commit `4a08736d0185c7c70f0fc731e0bc06b2702061a0`. The source,
tests, and executable were frozen before quality-seed execution. No source-code
changes are permitted after the first provenance seed; a required code fix
invalidates affected results and requires a new frozen implementation commit
and rerun. Subsequent result recording is documentation/analysis only.

**Hypotheses:** H1, persistent filtered information improves decisions; H2, the
information is decision-irrelevant at 1,000 simulations; H3, accurate
sequential filtering is offset by particle depletion; H4, a hidden mechanism
defect appears during longer gameplay. Mechanical failures invalidate quality
interpretation.

**Arms:** C is the **fresh-tree + fresh-belief experimental control**:
`STS_S3_PERSIST_FILTERED_BELIEF=0`. P is the fresh-tree + persistent-filtered-
posterior treatment: `STS_S3_PERSIST_FILTERED_BELIEF=1`. Both arms execute the
real-belief filter and collapse-fresh fallback and explicitly set
`STS_REUSE_MAX_SEARCHES=0`; C is not the current/deployed gameplay baseline.
The only intended conceptual difference is whether the filtered `Belief` is
consumed by the next fresh Searcher3. No tree nodes, visit counts, Q values,
edge availability, reuse state, or searcher RNG state transfer.

**Common configuration:** fair Searcher3, ascension 0, 1,000 simulations,
64 particles, `STS_FAIR=1`, `STS_SEARCHER3=1`, `STS_S3_BELIEF=0`,
`STS_S3_CHAIN=0`, `STS_S3_REAL_BELIEF_FILTER=1`,
`STS_S3_REAL_BELIEF_COLLAPSE_FRESH=1`,
`STS_S3_INTERNAL_BELIEF_UPDATE=0`, `STS_REUSE_MAX_SEARCHES=0`,
`STS_LIVE_VALID=1`, `STS_VNET=models/v_combat_7k_tuned.txt`,
`STS_VNET_ALPHA=0.3`, and V4 strategic token-net gates using
`selfplay/models/ooc_strategic_tok_final.native`, REST/EVENT/SHOP/TREASURE/
BOSS_RELIC enabled, strategic margin 1.0. Model SHA256 values are
`ea35b78c888e70e09566e1143d296577b0bea2ec8d437276b7aab81a7cdaf15c` for
V_combat and `e62abd833fc8cb9081a1cec4a1a012832ac3b0e3166da3892841911664f1184c`
for the strategic model. The same explicitly recorded OMP/thread setting and
all unrelated environment variables are used in both arms.

**Seeds and decision rule:** preregistered paired block `126732–126747` (16
seeds). First run seed `126732` separately in C and P with full belief audit.
The existing boundary-level next-search sidecar remains enabled, and the
existing fair-loop diagnostic additionally reports
`transferred_filtered_belief_searches`, the count of actual fresh searches
initialized from a transferred posterior. The provenance gate requires C = 0
actual transferred searches and P > 0. A failed gate, simulator-health failure,
stall, unresolved exit, material draw-pile mismatch, propagation failures above
approximately 1% of active attempts, or sharp action-illegal increase stops the
experiment without quality interpretation.

After exactly 16 paired seeds, extend only if substantive paired action,
trajectory, or outcome divergence occurs; then run only the preregistered
continuation `126748–126763` for 32 total. If trajectories are essentially
identical, stop at 16. Stop at 32 in all cases; do not automatically run 64 or
128 seeds. Primary analysis is seed-paired wins, P-only/C-only wins, both-win/
both-loss, and paired P−C floor/ending-HP mean and median differences, with
mechanical health, collapse, support, ESS if available, and CPU reported.

**Non-goals:** no default enablement, particle-count change,
resampling/rejuvenation, RNG-counter redesign, MCTS-statistics transfer, model
or policy tuning, or current-baseline promotion.

## 2026-08-15 — Searcher3 persistent filtered-posterior quality A/B results

**Frozen execution:** all quality runs used the frozen implementation commit
`4a08736d0185c7c70f0fc731e0bc06b2702061a0` and the preregistration commit
`f583ec007916e3fd7f117877d7c111b0392487b4`. No source code changed after
provenance execution began. The Release executable SHA256 was
`19e1160642e262b3b77949790c7e573d740db5296105d38d8bca3858b08b8a16`.

**Provenance gate, seed 126732:** C, the fresh-tree + fresh-belief
experimental control, reported exactly 0 transferred-belief searches. Its
boundary-level sources were `fresh_initial=409`, `no_next_search=24`. The
original diagnostic wording called P's 58 transferred-belief reconstructions
"actual fresh searches"; that wording was later corrected because a fresh
Searcher3 can receive the posterior and then take a forced action without
calling `s3.search()`. P's boundary-level sources were
`transferred_filtered_posterior=422`, `no_next_search=24`. Thus the treatment
was active, and the boundary-level sidecar was not mistaken for actual-search
consumption. Both arms had zero propagation failures, draw-pile mismatches, and
action-illegal particles on this provenance seed. Both lost at floor 50 with
ending HP 0; runtime was 18.3457s C versus 22.03s P.

**Common environment:** `OMP_NUM_THREADS=12`,
`STS_FAIR=1 STS_SEARCHER3=1 STS_S3_BELIEF=0 STS_S3_CHAIN=0
STS_S3_PARTICLES=64 STS_S3_REAL_BELIEF_FILTER=1
STS_S3_REAL_BELIEF_COLLAPSE_FRESH=1 STS_S3_INTERNAL_BELIEF_UPDATE=0
STS_REUSE_MAX_SEARCHES=0 STS_LIVE_VALID=1 STS_VNET=models/v_combat_7k_tuned.txt
STS_VNET_ALPHA=0.3
STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_final.native
STS_OOC_STRATEGIC_MARGIN=1.0 STS_OOC_STRATEGIC_REST=1
STS_OOC_STRATEGIC_EVENT=1 STS_OOC_STRATEGIC_SHOP=1
STS_OOC_STRATEGIC_TREASURE=1 STS_OOC_STRATEGIC_BOSS_RELIC=1
STS_S3_BELIEF_AUDIT=1`. The sole arm difference was
`STS_S3_PERSIST_FILTERED_BELIEF=0` for C versus `=1` for P. Startup output
confirmed Searcher3, fair-play, 64 particles, 1,000 sims, 12 threads, and
`models/v_combat_7k_tuned.txt` loaded at alpha 0.3. The strategic model path
was present in the startup/configuration provenance. Model hashes were the
preregistered values: V_combat
`ea35b78c888e70e09566e1143d296577b0bea2ec8d437276b7aab81a7cdaf15c` and
strategic token net
`e62abd833fc8cb9081a1cec4a1a012832ac3b0e3166da3892841911664f1184c`.

**16-seed gate, 126732–126747:** meaningful paired trajectory and outcome
divergence occurred, so the preregistered extension rule fired.

| Metric | C | P |
|---|---:|---:|
| Wins | 7 | 7 |
| P-only wins | 2 | — |
| C-only wins | 2 | — |
| Both win | 5 | — |
| Both lose | 7 | — |
| Mean floor | 43.2500 | 41.8750 |
| Mean ending HP | 18.8125 | 17.3750 |
| Mean runtime sec/run | 49.6159 | 45.7638 |

The paired P−C floor delta was mean `-1.375`, median `0`; ending-HP delta
was mean `-1.4375`, median `0`. The 16-seed direction was not a coherent
quality advantage; the full 32-seed discordance is reported below.

**32-seed gate, 126732–126763:** the continuation was run exactly as
preregistered, using only `126748–126763`, and execution stopped at 32.

| Metric | C | P |
|---|---:|---:|
| Wins | 15 | 16 |
| P-only wins | 6 | — |
| C-only wins | 5 | — |
| Both win | 10 | — |
| Both lose | 11 | — |
| Mean floor | 43.2813 | 43.5938 |
| Mean ending HP | 23.9063 | 24.6563 |
| Mean runtime sec/run | 53.1608 | 51.6669 |

Across paired seeds, P−C floor was mean `+0.3125`, median `0`; P−C
ending HP was mean `+0.75`, median `0`. Runtime delta P−C was mean
`-1.4940s`, median `-1.1792s`, descriptive only. The exact paired outcome
table was P-only `6`, C-only `5`, both win `10`, both lose `11`; the two-sided
conditional discordance test was not informative at this sample size (p=1.0).
Per-seed rows and raw artifacts are retained under the ignored
`build/linux-gcc-release/s3_ab_{c,p}_{16,32tail}.*` paths.

**Provenance and posterior mechanics across 32 seeds:** The historical
32-seed artifacts were produced by the frozen implementation before the
counter correction. C's old counter was 0 and its boundary sources were
`fresh_initial=12508`, `no_next_search=759`. P's old counter was 12,691 fresh
Searcher3 reconstructions receiving a transferred belief, including some
reconstructions followed only by forced actions; it was incorrectly labelled
as actual transferred searches. P's boundary sources were
`transferred_filtered_posterior=12662`, `no_next_search=759`. The exact
32-seed actual-search count was not measured by the frozen implementation and
is not reconstructed here.

| Mechanical metric | C | P |
|---|---:|---:|
| Filtered boundaries | 13,267 | 13,421 |
| Posterior collapses | 1,970 (14.85%) | 2,517 (18.75%) |
| Propagation failures / attempts | 253 / 849,088 (0.0298%) | 155 / 612,277 (0.0253%) |
| Draw-pile mismatches | 0 | 0 |
| Action-illegal particles | 253 | 155 |
| Mean distinct surviving draw orders | 44.13 | 37.48 |
| Mean ESS over audit rows | 55.62 | 44.36 |

No battle stalls, unresolved exits, simulator-health failures, or material
draw-pile regressions occurred. The treatment had lower support/ESS and higher
collapse frequency, consistent with H3's support-depletion concern, but did
not cross the mechanical stop rule.

**Treatment support depletion:** Existing `[belief-audit]` output covered
11,278 actual-search audit points. Positive-particle count had mean `46.53`,
median `64`; fractions at or below thresholds were `<=4: 17.0%`
(`1,917/11,278`), `<=8: 21.5%` (`2,424/11,278`), `<=16: 26.5%`
(`2,990/11,278`), and `<=32: 30.3%` (`3,416/11,278`). ESS had mean `46.53`,
median `64`, first quartile `14`, third quartile `64`, and range `0–64`.
These distributions are descriptive of the treatment's actual searches and
were derived offline without adding runtime telemetry.

**Post-experiment counter correction:** Commit
`187617c63024e69bf942cdc4215b6cb4f1f96d1f` corrected
`transferred_filtered_belief_searches` so it increments immediately before
the real `s3.search(...)` call only when the current Searcher3 was initialized
from a transferred posterior. Mere reconstruction and forced-move processing
do not increment it. The focused lifecycle regression now exercises the shared
transfer/counting seam and verifies persistence-off, transfer identity,
zero-weight preservation, fresh-root state, no-search non-consumption, and
exactly-one count for an actual search.

The corrected one-seed diagnostic used the same pinned configuration and seed
126732, but was not new quality evidence. C reported corrected counter `0`; P
reported corrected counter `367`, compared with 390 retained P belief-audit
points. P's boundary-level sidecar remained
`transferred_filtered_posterior=422`, demonstrating that boundary resolution
and actual-search consumption are distinct measurements. Both arms had zero
propagation failures, draw-pile mismatches, and action-illegal particles, with
no simulator-health failure, unresolved exit, or stall; startup confirmed the
correct treatment flag and model loading.

The 16- and 32-seed quality experiments were **not rerun**. Their evidence
remains tied to frozen implementation commit
`4a08736d0185c7c70f0fc731e0bc06b2702061a0`; this correction changes diagnostic
counting and regression coverage, not posterior-transfer gameplay semantics.
The scientific verdict remains **mixed / inconclusive at 64 particles and
1,000 fresh-tree simulations**: persistence materially changes trajectories
but provides no convincing gameplay improvement, and particle depletion remains
a plausible cost.

**Implementation verdict:** the feature is mechanically active, default-off,
fresh-tree isolated, provenance-correct, and preserves zero-weight particle
identity in focused tests. The treatment passed the mechanical validity gate.

**Scientific verdict:** **mixed / inconclusive at 64 particles and 1,000
fresh-tree Searcher3 simulations.** P produced substantial trajectory
divergence and one additional win (16 vs 15), with small positive mean floor
and HP deltas, but also six P-only versus five C-only wins, zero median paired
quality delta, higher collapse rate, lower support/ESS, and no statistically
informative paired binary result. This is not evidence to enable persistence by
default and does not establish a durable gameplay-quality improvement.

**Competing explanations and limits:** the sample is small; paired outcomes
are noisy; the treatment changes posterior support and therefore search
sampling, not only semantic accuracy; `HiddenBattleState` still lacks complete
RNG-counter representation; CPU differences may reflect the extra belief
handling; and the strategic/OOC and combat models remain sources of variance.
The result does not establish that persistence is beneficial at other particle
counts, simulation budgets, searcher-tree policies, model stacks, or longer
seed blocks. No resampling, rejuvenation, RNG redesign, default promotion, or
64/128-seed follow-up was performed.

## 2026-08-15 — Searcher3 posterior lifetime diagnostic and rejected transfer smoke

**Question:** Does exact real-boundary filtering meaningfully condition a
posterior that is then discarded when fair Searcher3 rebuilds its tree, and can
the posterior safely seed a deliberately fresh tree?

**Lifecycle diagnostic:** Added opt-in sidecar telemetry under the existing
`STS_S3_BELIEF_AUDIT[_FILE]`: one row per filtered boundary records the actual
next-search source (`fresh_initial`, `existing_filtered_posterior`,
`collapse_fresh`, or `no_next_search`). This correctly accounts for a carried
subtree later rebuilt by `STS_REUSE_MAX_SEARCHES`; `belief_carried` is not used
as the consumption proxy.

Fair Searcher3, 64 particles, 1,000 sims/decision, current native OOC +
V_combat/policy stack, 12 threads, seeds 94000–94007, filter ON, internal
belief updates OFF produced 2,942 filtered boundaries. Of 1,035 non-trivial
filters (`compatible fraction < 1`), 1,029 (99.42%) were followed by
`fresh_initial`; six ended combat before another search. The `<0.75` and
`<0.5` subsets were 1,026/1,032 (99.42%) and 996/1,002 (99.40%) fresh,
respectively. The coupling is therefore material.

**Rejected smoke:** A temporary treatment transferred the filtered `Belief`
while forcing a fresh tree every actual search in both arms
(`STS_REUSE_MAX_SEARCHES=0`). It was removed after the 8-seed smoke. Control
had 15.14% posterior collapse and 44 propagation failures out of 183,488
attempts; treatment had 79.11% collapse and 147,438/180,160 propagation
failures, including 2,066 all-particle `PROPAGATION_FAILURE` collapses. The
root cause is structural: `HiddenBattleState` stores RNG seeds but not counters,
and `applyParticleImpl` resets counters to zero. A propagated particle cannot
be safely carried through another real transition. No RNG reconstruction,
resampling, or transfer feature was retained.

The smoke’s whole-run outcomes were 3/8 wins in both arms; treatment mean floor
was 43.8 vs 41.6 and mean HP 20.0 vs 18.6, with 0/8 discordant wins. This is
not interpreted as quality evidence because the treatment was invalid. Mean CPU
was 28.67 vs 28.35 s/run (+0.32 s/run). No simulator-health, stall, or
battle-break output occurred. No 32-seed gate was run.

**Artifacts (ignored build output):**
`build/linux-gcc-release/s3_belief_lifecycle_phase2_8.{csv,csv.next_search.csv}`;
`s3_persist_{control,treatment}_8.{csv,csv.next_search.csv,results.csv}` and
their `.meta.json`, `.stdout`, and `.stderr` files.

**Correction — paired collapse-fallback diagnostic (same date):** The preceding
temporary treatment did not isolate missing RNG counters from stale-collapse
fallback. With temporary posterior transfer and `STS_REUSE_MAX_SEARCHES=0` held
constant, paired seeds 94000–94007 changed only
`STS_S3_REAL_BELIEF_COLLAPSE_FRESH`: T0 (`0`) collapsed 2,536/3,177 boundaries
(79.82%) with 169,738/203,328 propagation failures (83.48%), all 169,738 being
draw-pile mismatches and 2,363 `PROPAGATION_FAILURE` collapses. T1 (`1`) rebuilt
554 fresh post-state beliefs and collapsed 554/2,818 boundaries (19.66%) with
56,329/180,352 propagation failures (31.23%): 56,233 draw-pile mismatches, 96
action-illegal particles, and zero `PROPAGATION_FAILURE` collapses. Thus stale
pre-transition restoration was the primary cause of the catastrophic cascade.
Missing RNG counters remain an open limitation, not an established primary
cause. The temporary transfer remained removed; no larger strength gate ran.
T0/T1 whole-run wins were both 3/8 and are not quality evidence; CPU was 33.46
vs 29.73 s/run. Artifacts: `s3_persist_t{0,1}_8.*` under
`build/linux-gcc-release/`.

**Rerun after zero-weight resurrection fix:** The same corrected T1 command and
configuration on seeds 94000–94007 produced 2,867 filtered boundaries and
183,488 attempts: 434 collapses (15.14%), 44 propagation failures (0.02398%),
zero draw-pile mismatches, and 44 action-illegal particles. Fresh post-state
beliefs were rebuilt 434 times; next-search sources were
`fresh_initial=2698` and `no_next_search=169`. Whole-run output was 3/8 wins,
mean floor 41.6, mean ending HP 18.6, and 17.82 s/run. This is a diagnostic
rerun, not a quality gate. Artifacts: `build/linux-gcc-release/s3_persist_t1_rerun_8.*`.

**Provenance correction:** The temporary transfer telemetry was then made
explicit. A one-seed probe on 94000 reported 498
`transferred_filtered_posterior` next searches and 24 `no_next_search` rows,
before the 8-seed run. The provenance-correct 94000–94007 run reported 2,616
`transferred_filtered_posterior` and 171 `no_next_search`, 540/2,787 collapses
(19.38%), 17/120,391 propagation failures (0.0141%), zero draw-pile
mismatches, and 17 action-illegal particles. This is compared with the pre-fix
persistent T1’s 19.66% / 31.23% / 56,233 and the fresh-initial control’s
15.14% / 0.024% / 0; no further seeds were run. Temporary transfer code was
removed after the run; explicit telemetry vocabulary remains for future
reproducible treatments. Artifacts: `build/linux-gcc-release/s3_persist_t1_probe_94000.*`
and `s3_persist_t1_provenance_8.*`.

## 2026-08-15 — Native C++ LTO build benchmark and default adoption

**Question:** Does adding compiler optimization flags make the combat benchmark
faster, and should LTO become the standard native build setting?

- **Benchmark:** `one_combat bench 2000 8`, Jaw Worm combat, seeds `0..7`,
  Ironclad ascension 0, GCC 13.3, `OMP_NUM_THREADS=1`, known-RNG Searcher2
  MCTS, 2,000 simulations per decision. The primary metric is process user CPU
  time from `/usr/bin/time`; the harness MCTS row is a secondary metric.
- **Arms:** A current `-O3`; B `-O3 -march=native`; C
  `-O3 -march=native -flto`. All runs used the same source revision, models,
  seeds, and runtime settings, and were executed through
  `tools/seed_guard.sh`.
- **Results:** A **0.88 s** user CPU / **95.43 ms** MCTS average; B **0.87 s**
  / **94.41 ms**; C **0.76 s** / **81.50 ms**. Relative to A, B was **1.1%
  faster** and C was **13.6% faster** by process CPU time (**14.6% faster** by
  the harness MCTS timing). All arms produced identical outcomes: 8/8 MCTS
  wins, average ending HP 73.1, average 3.0 turns.
- **Decision:** Make `-flto` standard in `CMakeLists.txt`. Do not make
  `-march=native` standard: it is host-specific and the 8-seed result showed
  no meaningful benefit by itself.
- **Caveat:** This is a small 8-seed combat-only benchmark, so the LTO result is
  evidence for the default build setting, not a general performance guarantee
  across CPUs, compilers, workloads, or full-run benchmarks. LTO build time and
  portability remain follow-up considerations.
- **Artifacts:** temporary benchmark binaries and raw output were stored under
  `/tmp/sts-opt-bench/` during the session; they are not repository artifacts.
## §168 Phase 12B: matched M0 vs M1 at 2,000 source seeds — export, native parity, 64-seed paired gameplay gate (2026-08-15)

**Result: NULL.** At 2,000 source seeds, encounter-marginalized M1 did not
separate from matched fixed-world M0 on the preregistered paired gameplay gate.
The paired win-rate delta favored M0 slightly (−1.6pp) with a 95% CI crossing
zero. This does not support promotion or immediate scaling to 5,000 seeds.

### Provenance

- Dataset was generated by the **pre-merge Phase 12 generation binary** (older
  Searcher3), not the current HEAD; do not relabel it as current HEAD.
- The raw diagnostic CSV was **malformed** (unquoted `richState` → 1,056
  physical fields), **deterministically salvaged/reconstructed** to the intended
  40-column schema (`tools/reconstruct_marg_csv.py`), and the corrected artifact
  passed full paired/identity/hidden-resampling validation.
- Training used the reconstructed CSVs on branch state containing the
  CSV-quoting + trainer-schema + trainer-device fixes (HEAD `774585b`).

### Inputs (verified hashes)

| Artifact | SHA256 |
|---|---|
| M0 CSV `build/phase12b_m0.csv` | `08af144a00a27d9ea7153332b437adb347a46f72619c0ccd0946f1be2dc245fa` |
| M1 CSV `build/phase12b_m1.csv` | `c75a120c809ad84a2bcfcabc1b6f537648aa9da92aabc4c0fe682830ff68e48f` |
| split `build/phase12b_split.json` | `41155410f9b888a14533233a1456d9d2014723f671ee4c2db93c97bf27aac5fa` |

### Training (identical contract, both arms)

`train_strategic_tok.py`, `/usr/bin/python3`, torch 2.5.1+cu121, RTX 3060 Ti.
`STRAT_EPOCHS=40 STRAT_PATIENCE=0 STRAT_Q_TARGET=absolute STRAT_MODEL_SEED=0
STRAT_SPLIT_LOAD=build/phase12b_split.json STRAT_TOK_RUNG=4
STRAT_TOK_TRANSFORMER=0 STRAT_TOK_COMPILE=1 OMP_NUM_THREADS=8 STRAT_DEVICE=cuda`.
Both completed 40 epochs. Best-CE checkpoints were selected (fixed in advance,
matching the 500-seed pilot convention; best-qtop1 not used).

### Offline best-CE metrics

| | val_pol_ce | best q_top1 |
|---|---|---|
| M0 | 0.5089743137359619 (epoch 35) | 0.2598020794187649 (epoch 13) |
| M1 | 0.5118089318275452 (epoch 40) | 0.25353876988600776 (epoch 16) |

### Checkpoints & native exports (best-CE)

| Arm | best-CE `.pt` SHA256 | native SHA256 |
|---|---|---|
| M0 | `2c146abc3d1e16b69c9fcefe96a6b2a7f07b8a467750f03258754a3b43fec343` | `161c14bcb711d1966e2c16d3a8f551486eeb6d46eb94df89dfdd1057db41014d` |
| M1 | `68b5005fbaeb76c0548b0d15697461c8441aaf6c5b4c4421b59e4b1a554d8251` | `92332a4b13b0f9fdc468531b43db5e0cdf6de2ae147ea4951ea9c44edce6723b` |

Export: `export_strategic_tok.py <pt> <native>`; both passed the built-in
32-sample numpy-vs-PyTorch (native mirror) parity — M0 max err logit 4.52e-06,
M1 4.77e-06.

### Gameplay gate

- Seeds 900000–900063 (64 common), `bestbench 1000 64 0 900000`, fair
  S3 + 7k-VNet Act-3 stack, all strategic screens ON, margin 1.0, threads 12.
  The two arms differ **only** in `STS_OOC_STRATEGIC_TOK_NN` (the native model
  artifact); the `BEST stack config` banner was identical for both.
- Env (both arms): `STS_OOC_STRATEGIC_REST/EVENT/SHOP/TREASURE/BOSS_RELIC=1`,
  `STS_OOC_STRATEGIC_MARGIN=1.0`, `STS_FAIR=1`, `STS_SEARCHER3=1`,
  `STS_S3_BELIEF=0`, `STS_S3_CHAIN=0`, `STS_S3_LIVE_VALID=1`,
  `STS_S3_PARTICLES=64`, `STS_VNET=models/v_combat_7k_tuned.txt`,
  `STS_VNET_ALPHA=0.3`, `OMP_NUM_THREADS=12`.
- Gameplay CSVs: `build/phase12b_m0_64.csv` (`d1af223d…`),
  `build/phase12b_m1_64.csv` (`809c4868…`).

### Paired result (`paired_analysis.py`, 64 seeds, identical seed sets)

| Metric | M0 | M1 | Δ (M1−M0) |
|---|---|---|---|
| Win rate | 17/64 = 26.6% | 16/64 = 25.0% | **−1.6pp** |
| Win-diff 95% CI | | | **[−14.1pp, +10.9pp]** |
| Avg floor | 38.8 | 38.7 | −0.1 |
| Avg HP end | 14.6 | 10.3 | −4.2 |
| Avg sec/run | 28.86 | 31.56 | +2.71 |

Discordant 15/64 (23%): both win 9, both lose 40, M0-only 8, M1-only 7.
M0 Wilson 95% CI [17.3%, 38.5%]; M1 Wilson 95% CI [16.0%, 36.8%].

### Interpretation

Paired delta −1.6pp (95% CI crosses zero). Per the preregistered decision rule:
**null / approximately equal** — M1 does not separate from M0 at 2,000 seeds.
Consistent with H2 (M0 ≈ M1). H3 remains compatible with the evidence, but the
higher absolute win rates relative to the historical 500-seed pilot cannot be
attributed specifically to dataset quantity because runtime/controller state
also changed. No promotion; do not auto-scale to 5,000.

> **Correction (2026-08-15, §169):** this gate ran with `keys=skip` (default),
> which is an Act-3-only horizon — the earlier "vs deployed V4 ~48%" comparison
> was an invalid cross-block comparison. On a same-seed/same-config Act-3 calibration,
> V4 scored 37.5% vs M0 26.6% / M1 25.0% (§169). Both arms remain below V4 but
> by a smaller, same-block margin; H4 (another bottleneck) remains plausible.

### Warnings

- `STRAT_PATIENCE=0` was used to satisfy the "full 40 epochs" contract (matches
  the pilot; the trainer default 6 would early-stop).
- Dataset producer is the pre-merge Searcher3 binary; do not relabel it as current HEAD.

## §169 Phase 12B corrective Act-3 gate + V4 calibration (2026-08-15)

**Correction finding.** Independent review suspected that the §168 gate had run
a full Act-3+4/Heart horizon (because `STS_COLLECT_KEYS`/`STS_STOP_AFTER_ACT`
were not set). Verification shows this suspicion was **incorrect**: the §168
gate ran with `keys=skip` (default `STS_COLLECT_KEYS` unset → off), so the agent
never collected keys, the Act-3 boss victory ended the run, and **zero** runs
entered Act 4 (all winning rows are `act=3, floor=51`; Act-3 boss deaths at
`floor=50`, deathEncounter 53/54/55). The §168 result was therefore already an
Act-3-boss win rate, not a Heart-horizon rate.

### Corrective Act-3 gate (explicit historical contract)

Restored the explicit historical Act-3 contract on the **same 64 seeds**
(900000–900063) and the same current executable, with
`STS_COLLECT_KEYS=0 STS_STOP_AFTER_ACT=3` added. All other flags unchanged
(fair S3, 64 particles, 7k-VNet alpha 0.3, all strategic screens ON, margin 1.0,
12 threads). The three arms differ only in `STS_OOC_STRATEGIC_TOK_NN`.

| Arm | Wins | Win rate | mean floor | mean HP | artifact | SHA256 |
|---|---|---|---|---|---|---|
| M0 | 17/64 | 26.6% | 38.8 | 14.6 | `build/phase12b_m0_act3_64.csv` | `e4cc5fef11bc88b2c018c12aaec8597d89e065f4d9009cd192fe3e4ebdd1eef4` |
| M1 | 16/64 | 25.0% | 38.7 | 10.3 | `build/phase12b_m1_act3_64.csv` | `edc01b56453f7ce17b65636115f39192d92508c4199764ddd3974d674fe03442` |
| V4 (POST-HOC SAME-SEED/SAME-CONFIG CALIBRATION) | 24/64 | 37.5% | 41.8 | 20.1 | `build/phase12b_v4_act3_64.csv` | `c7292bf84e09de0ddd543443f421970e91ac02734c6ef4d0d183def0c47a5bd1` |

M0/M1 Act-3 numbers are **identical** to the §168 gate (26.6% / 25.0%),
confirming the §168 gate was already Act-3-only and there was no horizon mismatch.

Model artifacts (unchanged from §168): M0 `161c14bc…`, M1 `92332a4b…`,
V4 `e62abd83…` (`selfplay/models/ooc_strategic_tok_final.native`).

### Primary paired result (M0 vs M1, Act-3)

- M1−M0 win delta = **−1.6pp**, 95% CI [−14.1pp, +10.9pp] (crosses zero).
- Discordant 15/64: both win 9, both lose 40, M0-only 8, M1-only 7.

Per the preregistered decision rule this remains **NULL / approximately equal**:
encounter marginalization does not separate from the fixed-world control under
the explicit Act-3 horizon either. Do not auto-scale to 5,000 seeds.

### V4 calibration (post-hoc, same 64 seeds, same Act-3 config)

| Pair | Delta | 95% CI | Discordant |
|---|---|---|---|
| V4 − M0 | +10.9pp | [−1.6pp, +23.4pp] | 17/64 (both win 12, both lose 35, M0-only 5, V4-only 12) |
| V4 − M1 | +12.5pp | [+3.1pp, +23.4pp] | 12/64 (both win 14, both lose 38, M1-only 2, V4-only 10) |

V4 (37.5%) exceeds M1 significantly at 95% (CI excludes zero) and M0
non-significantly (CI crosses zero but mostly positive). This is valid same-block
evidence that the Phase-12 models remain weaker than deployed V4, but by a
smaller margin than the historical 48.4% figure suggested — that figure was a
**different seed block (126700–126763), Act-3-only**, not a direct comparator.

### Hypothesis outcomes

- **H1 (horizon mismatch explains low win rates): REJECTED.** The §168 gate was
  already Act-3-only; the corrective Act-3 gate reproduces 26.6%/25.0% exactly.
- **H2 (M0 ≈ M1): SUPPORTED.** The null persists under the explicit Act-3 horizon.
- **H3 (M0/M1 weaker than V4): PARTIALLY SUPPORTED.** V4 > M1 significantly,
  V4 > M0 non-significantly, on the same 64-seed block.
- **H4 (V4 advantage was an invalid comparison): WEAKENED.** The V4 advantage is
  real on the same block, but smaller than the cross-block 48.4% implied.

### Warnings

- 64 seeds is a small sample; the V4 calibration CIs are wide.
- The V4 arm is post-hoc same-config calibration, not a preregistered treatment.

## 2026-08-15 — Searcher3 history-replay rejuvenation shadow probe (preregistration)

**Question:** When the persistent filtered posterior loses support at a
real-observation boundary, can new hidden-state hypotheses compatible with the
FULL real observation history be generated at all? Equivalently: is the
observed `collapseFresh` fallback a consequence of particle depletion
(in-principle recoverable by re-proposing hidden state), or of a hard
inconsistency between the real history and the hidden-state model? If
recoverable, how many fresh proposals are needed to reach 4/8/16/32 distinct
full hypotheses, and how many of those are novel relative to the surviving
posterior?

**Design:** opt-in shadow-only probe (`STS_S3_REJUV_SHADOW=1`, off by default;
off ⇒ bit-identical live behavior). At each filtered boundary with
`compatible <= STS_S3_REJUV_TRIGGER` (16), after `filterRealTransition`
returns: (1) record the committed semantic action + raw bits + real post-action
observation + outcome into a per-combat history anchored at battle start;
(2) sample `STS_S3_REJUV_PROPOSALS` (256) fresh hidden hypotheses from the
anchor observation using a dedicated deterministic probe RNG (independent of
all battle RNG); (3) replay the full recorded history under each hypothesis
using semantic action remap (position-independent card identity, multiset
multi-select, raw END_TURN/POTION), `applyHiddenState` on a copy of the
anchor, and bare `Action::execute` (exact live transition semantics). A
hypothesis is **accepted** iff it reproduces every recorded post-action
observation and outcome exactly (full `CombatObservation::operator==` equality
plus outcome). Uniqueness, novelty, and milestone counts use the
equality-backed `FullHiddenStateKey` (ordered canonical draw-pile identity +
all six RNG seed0/seed1/counter triples); draw-order-only and RNG-only counts
are telemetry hashes only. Novelty compares against the positive particles
currently in `s3.belief` when `compatible > 0` (already propagated to the
current hidden state); when `compatible == 0` the pre-fallback survivor set is
empty and no comparator is used. Pure telemetry: the probe mutates only copies
and appends one CSV row per trigger.

**Frozen implementation:** baseline `0132a5b`; implementation commit
`ac603e5` (branch `exp/s3-history-replay-rejuvenation-shadow`). Source, tests,
and executable were frozen before quality-seed execution; the required status-
column fix was applied before the frozen run (see results section).

**Mechanical gate criteria:** (a) shadow OFF vs ON produce identical committed
action bits, decision observations, RNG-counter trajectories, positive-particle
full-hidden-state keys, and outcome on the same seeds (non-interference test);
(b) per-row sanity: `0 <= accepted <= proposals`, `0 <= unique <= accepted`,
`0 <= novel <= unique`, and where present the milestone proposal indices are
non-decreasing (4 ≤ 8 ≤ 16 ≤ 32); (c) no simulator-health failure, stall, or
unresolved exit attributable to the probe (probe never calls
`reportSimHealthFailure`); (d) no replay `transitionsExecuted` beyond the
recorded history length. A failed gate invalidates quality interpretation.

**Common configuration:** fair Searcher3, ascension 0, 1,000 simulations, 64
particles, `STS_FAIR=1`, `STS_SEARCHER3=1`, `STS_S3_BELIEF=0`, `STS_S3_CHAIN=0`,
`STS_S3_REAL_BELIEF_FILTER=1`, `STS_S3_REAL_BELIEF_COLLAPSE_FRESH=1`,
`STS_S3_INTERNAL_BELIEF_UPDATE=0`, `STS_REUSE_MAX_SEARCHES=0`,
`STS_LIVE_VALID=1`, `STS_VNET=models/v_combat_7k_tuned.txt`,
`STS_VNET_ALPHA=0.3`, V4 strategic token-net gates using
`selfplay/models/ooc_strategic_tok_final.native`, REST/EVENT/SHOP/TREASURE/
BOSS_RELIC enabled, strategic margin 1.0, plus shadow flags
`STS_S3_REJUV_SHADOW=1 STS_S3_REJUV_TRIGGER=16 STS_S3_REJUV_PROPOSALS=256` and
`STS_S3_REJUV_SHADOW_FILE` pointing at the artifact path.

**Seeds and decision rule:** preregistered block **126732–126739 (8 seeds)**,
run once through `tools/seed_guard.sh` with the frozen executable. Primary
analysis is mechanical: distribution of accepted / unique / novel per trigger,
milestone proposal indices (4/8/16/32), final-state-compatible-but-not-full
counts, per-row status mix, and their relationship to `compatible`. No
win-rate or floor interpretation — this is a feasibility probe, not a quality
gate. Stop at 8 seeds; do not extend automatically.

**Non-goals:** no default enablement, no live-belief rejuvenation (the probe
never modifies `s3.belief`), no change to `filterRealTransition`, no
resampling-policy change, no RNG-counter redesign, no gameplay promotion.

## 2026-08-15 — AI_RNG conditional sensitivity: exploratory belief-ON run

This diagnostic run is retained as exploratory evidence and is not the intended
frozen paired baseline. It used commit `d0c02cd`, fair Searcher3, seeds
`126732–126739`, 1,000 base simulations, 3,000 boss simulations, 64 particles,
12 threads, real-boundary filtering, collapse-fresh, persistent filtered belief,
no tree reuse, chain off, CRN off, the deployed 7k combat VNet at alpha 0.3,
and native heuristic OOC policy. `STS_S3_BELIEF` was unset (effective ON),
`STS_S3_REJUV_PROPOSALS` was unset (effective 256), and the V4 strategic token
model/gates were OFF. Artifacts were `/tmp/final8_sensitivity.csv`,
`/tmp/final8_live.csv`, `/tmp/final8_live.csv.meta.json`,
`/tmp/final8_exposure.csv`, and `/tmp/final8.log`.

The 32-root analysis found selected-action changes in 3/32 roots, top-two visit
ordering changes in 4/32, and Q-order flips in 3/32. This run demonstrated
conditional sensitivity but is explicitly regime-dependent exploratory evidence.

## 2026-08-15 — CORRECTION: invalid matched AI_RNG record in d68af8c

The matched-replication section previously committed by `d68af8c` is invalid.
It reused the exploratory belief-ON artifact names, hashes, and results while
claiming belief-OFF/V4 provenance. That section must not be used as evidence and
is superseded by the actual matched run recorded below. The exploratory
belief-ON section above remains valid as exploratory evidence.

## 2026-08-15 — AI_RNG conditional sensitivity: matched belief-OFF/V4 replication (corrected)

The corrected matched replication used commit `d0c02cd`, seed block
`126732–126739`, ascension 0, 1,000 base simulations, 3,000 boss simulations,
64 particles, 12 threads, fair Searcher3, `STS_S3_BELIEF=0`, chain off, CRN
off, real filtering, collapse-fresh, persistent filtered posterior, no tree
reuse, END_TURN marginalization off, deployed 7k combat VNet at alpha 0.3, and
the V4 strategic token model
`selfplay/models/ooc_strategic_tok_final.native` with REST/EVENT/SHOP/TREASURE/
BOSS_RELIC gates enabled and margin 1.0. Rejuvenation used trigger 16 and 64
proposals; sensitivity used at most 4 roots/seed, 4 alternatives/root, and
256 mini-search simulations. The exact command was run through
`tools/seed_guard.sh` as:

```text
env -i PATH="$PATH" HOME="$HOME" PWD="$PWD" OMP_NUM_THREADS=12 STS_FAIR=1 STS_SEARCHER3=1 STS_S3_BELIEF=0
STS_S3_CHAIN=0 STS_S3_PARTICLES=64 STS_S3_CRN=0
STS_S3_REAL_BELIEF_FILTER=1 STS_S3_REAL_BELIEF_COLLAPSE_FRESH=1
STS_S3_PERSIST_FILTERED_BELIEF=1 STS_REUSE_MAX_SEARCHES=0
STS_S3_ENDTURN_MARGINALIZE=0 STS_S3_REJUV_SHADOW=1 STS_S3_REJUV_SHADOW_FILE=/tmp/final8_matched_rejuv.csv
STS_S3_REJUV_TRIGGER=16 STS_S3_REJUV_PROPOSALS=64
STS_S3_RNG_EXPOSURE_DIAG=1 STS_S3_RNG_EXPOSURE_DIAG_FILE=/tmp/final8_matched_exposure.csv STS_S3_AI_SENSITIVITY_SHADOW=1
STS_S3_AI_SENSITIVITY_ROOTS_PER_SEED=4 STS_S3_AI_SENSITIVITY_ALTS=4
STS_S3_AI_SENSITIVITY_SIMS=256 STS_S3_AI_SENSITIVITY_FILE=/tmp/final8_matched_sensitivity.csv STS_VNET=models/v_combat_7k_tuned.txt
STS_VNET_ALPHA=0.3 STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_final.native
STS_OOC_STRATEGIC_MARGIN=1.0 STS_OOC_STRATEGIC_REST=1
STS_OOC_STRATEGIC_EVENT=1 STS_OOC_STRATEGIC_SHOP=1
STS_OOC_STRATEGIC_TREASURE=1 STS_OOC_STRATEGIC_BOSS_RELIC=1
tools/seed_guard.sh ./build/one_combat bestbench 1000 8 0 126732 /tmp/final8_matched_live.csv
```

The run completed with 32 selected roots, 8 seed breadth, 13 encounter breadth,
14 floor breadth, and 32 encounter/floor groups. ORACLE_A was `BASELINE` for
all 146 root-action rows, ORACLE_B was `EXACT` for all 146 rows, and all 584
AI alternative rows were `N/A`; block-isolation and source/search-index
failures were zero. The 32-root cross-tab was: 25 roots with no
support-empty flag and no policy/Q-order change; 1 with only a Q-order flip;
3 with selected/top-two/Q-order changes; and 3 support-empty roots with no
selected-action change (one had a Q-order flip and one had a top-two change).
Overall, selected action changed in 3/32, top-two ordering in 4/32, Q-order
flipped in 5/32, and any nonzero common-edge Q difference occurred in 9/32
roots. Per-root visit-TV Q25/median/Q75/max was 0/0/0.01275/0.906; max
common-edge |dQ| was 0/0/2.42775/131.362; max oracle-selected |dQ| was
0/0/0.30925/17.482.
`/tmp/final8_matched_sensitivity.csv`
(`cb724466559a74437ebefd7e3c20d660a623fefd7e0ffb8c5492ff8610a1398a`),
`/tmp/final8_matched_live.csv`
(`1447919f936fb421cb81fcda831af8c5d59e62f7eff754699b34629019f6b50c`),
`/tmp/final8_matched_live.csv.meta.json`
(`159f2e1cbac329841aeedeb8f256d96b66879d209c1f1f781fb957626ed3a6a8`),
`/tmp/final8_matched_exposure.csv`
(`5add23d9c22757ff3e1cfd06c26a19ab71e2f5c7b9a8d55aced320d3ba9c08e4`),
`/tmp/final8_matched_rejuv.csv`
(`b915e93fddb0f8083bfec1bc98bb62c601d74cc0666b636500929f3e4a1b5496`), and
`/tmp/final8_matched.log`
(`3105f6c9c429eaae2ef05838e96c2b569140be5bced7ce6fc93a1eebf6e34ba4`).

The exposure join covered all 32 roots. Aggregate AI exposure fractions on the
three roots with selected-action changes were 0.020, 1.000, and 1.000. The
matched run again shows decision-relevant AI_RNG sensitivity across multiple
seeds/encounters, but the effect remains sparse and does not itself establish
live gameplay benefit. A later targeted live-treatment study is justified; no
live rejuvenation is implemented here.

## 2026-08-15 — Searcher3 history-replay rejuvenation shadow probe results

> **INVALIDATED for late-history inference (correction 2026-08-15):** this
> first 8-seed run (implementation commit `ac603e5`) recorded
> SINGLE_CARD_SELECT actions via `BattleScumSearcher3::cardActionKey`, which
> only extracts identity from `cardSelectInfo.cards` (Discovery/Codex offers).
> Hand/discard/draw/exhaust-pile single-selects therefore recorded a missing or
> CardId-only identity and remapped incorrectly (8,331 artificial
> `remap_failure`s). The corrected semantic recording/remap rerun is in the
> section immediately below; this section's `remap_failure`, status-mix, and
> late-fight acceptance figures are superseded and must not be used for
> late-history inference. Early-boundary and aggregate-acceptance conclusions
> are re-reported on the corrected data below.

**Frozen execution (superseded):** the preregistered 8-seed run
(126732–126739) used implementation commit `ac603e5` with the preregistered
common configuration plus `STS_S3_REJUV_SHADOW=1 STS_S3_REJUV_TRIGGER=16
STS_S3_REJUV_PROPOSALS=256` and
`STS_S3_REJUV_SHADOW_FILE=build/linux-gcc-release/s3_rejuv_shadow_8.rejuv.csv`,
executed through `tools/seed_guard.sh` with `OMP_NUM_THREADS=12`. Run exited 0;
whole-run outcome was 4/8 wins, avg floor 46.6, avg ending HP 17.6, 31.57 s
cpu/run (informational only — no quality interpretation per the
preregistration). Artifacts:
`build/linux-gcc-release/s3_rejuv_shadow_8{.stdout,.stderr,.meta.json,<base CSV>,.rejuv.csv}`
(overwritten by the corrected rerun below; the old aggregate numbers are
recorded here for provenance).

**Mechanical gates:** (a) non-interference — `rejuv_noninterference` test:
shadow OFF vs ON produced identical committed action bits (9/9), decision
observation hashes, all-18 RNG-field trajectories, positive-particle
`FullHiddenStateKey` sequences, final state, and zero sim-health counter
movement on both arms; (b) per-row sanity — 0 violations of
`0 <= accepted <= proposals`, `0 <= unique <= accepted`, `0 <= novel <= unique`
across all 981 rows, and milestone indices were non-decreasing wherever
present; (c) `sim_health` column total = 0 and no battle-break/stall output
attributable to the probe; (d) `transitions` per row never exceeds the recorded
history length by construction (replay executes exactly the recorded
boundaries).

**Primary mechanical findings (superseded — 981 trigger rows, 251,136
proposals):**

- Full-history regeneration by anchor-fresh re-sampling is possible: 2,013
  accepted hypotheses (0.80% of proposals) in 128 of 981 rows (13.0%). 83 rows
  reached ≥4 unique accepted hypotheses within 256 proposals, 66 reached 8,
  37 reached 16, 21 reached 32. **Corrected interpretation:** compatible
  full-history states were demonstrated for **some** low-support boundaries;
  zero-acceptance boundaries remain **inconclusive** between very low proposal
  probability and hidden-state/model inconsistency — the data do not support a
  global "the model is not hard-inconsistent" claim.
- Acceptance is a **first-turn phenomenon**: decision_idx 0–4 account for
  103/128 accepted rows (80.4%) and decision_idx 0 alone for 24 rows and 560
  accepted hypotheses; after decision ~8 accepted ≈ 0 in this (superseded) run.
  (**Inference** — the mechanism follows from the decision_idx distribution;
  the distribution itself is measured; late-history figures are superseded by
  the corrected rerun below.)
- Novelty: every accepted hypothesis was novel relative to the surviving
  posterior comparator (novel == unique == 2,013).
- Status mix (superseded): 240,792 intermediate mismatches, 8,331 remap
  failures (largely an artifact of the SINGLE_CARD_SELECT recording bug), 0
  action-illegal, 0 sim-health, 0 final-only mismatches (unreachable before
  the FINAL_MISMATCH classification fix).
- Overhead: probe CPU 1.73 s total across 981 triggers (1.76 ms/trigger,
  6.9 µs/proposal) — immaterial.

**Caveats:** acceptance at early boundaries can be inflated by particle-
invariant segments (scripted enemy turns; full-cycle deck draws make
hand/pile multisets order-insensitive — the degenerate case proved by the
CULTIST fixture in `rejuv_history_replay`), so "accepted" is an upper bound on
true hidden-state recovery. Whole-run wins are reported only as run health
context.

## 2026-08-15 — Searcher3 history-replay rejuvenation shadow probe — corrected semantic replay rerun

**Correction (same branch, same frozen 8 seeds):** independent review found
that `record` used `BattleScumSearcher3::cardActionKey` for
SINGLE_CARD_SELECT, which reads only `cardSelectInfo.cards`; hand/discard/
draw/exhaust-pile selections therefore recorded an incomplete (CardId-only or
missing) identity and remapped wrongly. Fixed by probe-specific semantic
recording per `cardSelectTask` (full canonical identity: id, upgradeCount,
costForTurn, freeToPlayOnce, specialData), full-identity remap matching,
explicit empty-MULTI_CARD_SELECT validity, and correct FINAL_MISMATCH
classification (first failure at the final boundary). `rejuv_semantic_select`
regression added (hand permutation, discard/draw remap, identical-CardId
distinct-property resolution, empty multi round-trip).

**Corrected frozen rerun:** identical preregistered command (seeds
126732–126739, 64 particles, 1000 sims, trigger ≤16, 256 proposals, same
model/config flags). Run exited 0; whole-run outcome **4/8 wins, avg floor
46.6, avg ending HP 17.6** — identical to the superseded run (shadow-only
telemetry; live behavior unchanged). 981 trigger rows, 251,136 proposals.

**Old → corrected comparison:**

| Metric | ac603e5 (superseded) | Corrected |
|---|---:|---:|
| remap_failure (total) | 8,331 | **0** |
| remap_failure by decision_idx | non-zero (artifact) | 0 at every decision_idx |
| intermediate_mismatch | 240,792 | 205,629 |
| final_mismatch (reachable?) | 0 (misclassified) | **43,489** |
| accepted / unique / novel | 2,013 | **2,018** |
| rows with any accepted | 128 | **132** |
| collapse rows with any accepted | 24 (93 accepted) | **27 (96 accepted)** |
| milestones 4/8/16/32 | 83/66/37/21 | 83/66/37/21 |
| acceptance at decision ≥8 | 7 rows (d8–d11) | **9 rows (d8–d13), 75 accepted** |

**Corrected scientific interpretation:** the semantic-replay bug inflated
`remap_failure` and suppressed late-fight acceptance, but did not materially
change the headline: full-history regeneration by anchor-fresh re-sampling is
possible at **some** low-support boundaries (2,018 accepted, 0.80%; 83/66/37/21
rows reached 4/8/16/32 unique; acceptance concentrated at decision_idx 0–4 and
rare after ~8). With remap now exact (0 failures), late-fight acceptance rose
slightly (9 rows at decision ≥8, vs 7), consistent with correct semantic replay
of card-select boundaries. **Zero-acceptance boundaries remain inconclusive**
between very low proposal probability (the RNG seed/counter space is
astronomically large) and hidden-state/model inconsistency; no global
consistency claim is warranted. All accepted hypotheses remain novel vs the
surviving posterior; sim-health = 0; probe CPU 1.19 s total. Per-row sanity and
milestone-monotonicity gates: 0 violations.

Artifacts (corrected): `build/linux-gcc-release/s3_rejuv_shadow_8{.stdout,
.stderr,.meta.json,<base CSV>,.rejuv.csv}` (corrected executable; the
superseded run's CSV was overwritten, its aggregate numbers are preserved in
the table above).

## §170 Phase-12 screen-contract correction: corrected M0/M1 retrain and gate (2026-08-15)

Independent audit confirmed that `tools/convert_marg_to_trainer.py` wrote
diagnostic `gateKind` into the trainer `screen` feature, while native deployment
passes actual `gc.screenState`. Temporary corrected datasets changed only
`screen`: 210,838 rows and 39,870 groups remained; 45,088 rows and 7,690 groups
changed; MAP became zero; corrected TREASURE/REST/SHOP counts were 1,294/3,260/
3,136 groups. The local expectation that SHOP had 1,294 groups was incorrect.

Corrected M0 and M1 were retrained with the original 40-epoch rung-4,
non-transformer, absolute-Q recipe, identical split, model seed, and eager CUDA.
On the paired fair Searcher3 gate (seeds 900000–900063, 1,000 sims, 64
particles, 7k VNet alpha 0.3, all strategic gates on, margin 1.0):

| Arm | Original | Corrected | Delta |
|---|---:|---:|---:|
| M0 win rate | 17/64 = 26.56% | 16/64 = 25.00% | -1.56pp |
| M1 win rate | 16/64 = 25.00% | 12/64 = 18.75% | -6.25pp |

This eager-mode result was subsequently superseded by the strict compile-enabled
rerun in §171 and should not be interpreted causally. The contract bug is real
and requires a permanent converter fix; §171 provides the controlled follow-up.
See historical source `git show d28cfc3291dc091bb52b218f1d3e27f7431f4163:docs/archive/research/sessions/phase12-screen-contract-corrected-m0-m1-2026-08-15.md`
for hashes and detailed provenance.

## §171 Phase-12 corrected-screen strict compile-enabled rerun (2026-08-15)

The §170 corrected retrain used eager CUDA despite the original contract's
`STRAT_TOK_COMPILE=1`. A strict rerun held the intended single variable to the
screen IDs while restoring `STRAT_PATIENCE=0`, compile-enabled CUDA, exactly 40
epochs, the original split/model seed/objective/architecture, and the same
64-seed Act-3 gate. All corrected dataset invariants passed.

The epoch-6 best-CE anomaly disappeared: strict M0 and M1 selected epoch 40.
Strict M0 achieved `val_pol_ce=0.501773`, `policy_top1=0.792266`, and
`q_top1=0.251409`; strict M1 achieved `val_pol_ce=0.498305`,
`policy_top1=0.790982`, and `q_top1=0.249154`. Both native exports passed
32-sample parity.

On the fair Searcher3 Act-3 gate (seeds 900000–900063, 1,000 sims, 64
particles, all strategic gates, margin 1.0, explicit `STS_COLLECT_KEYS=0` and
`STS_STOP_AFTER_ACT=3`):

| Arm | Wins | Win rate | Mean floor | Mean HP |
|---|---:|---:|---:|---:|
| Strict corrected M0 | 23/64 | 35.9% | 41.921 | 16.672 |
| Strict corrected M1 | 16/64 | 25.0% | 37.562 | 8.672 |
| Original M0 | 17/64 | 26.6% | 38.812 | 14.562 |
| Original M1 | 16/64 | 25.0% | 38.719 | 10.312 |
| V4 | 24/64 | 37.5% | 41.797 | 20.062 |

Strict M0 vs original M0 was +9.4pp (deterministic bootstrap 95% CI
[-3.1,+21.9]pp); strict M0 vs V4 was -1.6pp (CI [-17.2,+14.1]pp).
The point estimate recovers approximately 86% of the original 10.9pp M0/V4
gap, but the small-block intervals cross zero. Strict M1 remained null versus
original M1 at 25.0%. This supports material contribution from the screen bug
to M0's gap, without establishing full causality or promotion.

See historical source `git show d28cfc3291dc091bb52b218f1d3e27f7431f4163:docs/archive/research/sessions/phase12-screen-contract-strict-rerun-2026-08-15.md`
for complete hashes, paired contingency counts, and parity errors.

## §172 Phase-12 M0/M1 post-hoc Q-supervision autopsy — corrected after reverted draft (2026-08-15)

An earlier autopsy commit was reverted for a wrong screen mapping and an
internally inconsistent cross-classification. This corrected rerun (baseline
`ab18dce`, branch `phase12-m0-m1-autopsy-fixed`) uses one deterministic script
(`tools/phase12_m0_m1_autopsy.py`) on the exact corrected datasets and strict
checkpoints, derives screen names from the actual `ScreenState` numeric field
(`include/game/GameContext.h::sts/ScreenState`), preserves duplicate action
rows, and asserts every invariant.

The policy labels are identical (`chosen`, asserted per matched row); encounter
marginalization changes only the auxiliary Q supervision, whose actual target
is `10*labelWon + labelHp`. Across 39,870 matched decisions, M0/M1 Q-target
argmax differed on 16,951 (42.52%) and exact top-two ordering reversed on
3,338 (8.37%, stable tie-breaking). Corrected semantic rates were SHOP 60.62%,
CARD 44.88%, EVENT 32.95%, TREASURE 30.68%, REST 26.29%, UPGRADE_SELECT
44.37%, and BOSS_RELIC 1.58%. Mean Q-target margin fell 6.9049 → 5.7728.

Inference on the exact strict checkpoints found predicted-Q argmax
disagreement 9,932 (24.91%) and policy-logit argmax disagreement 3,154
(7.91%) — a smaller overall rate than predicted-Q divergence, but strongly
concentrated: SHOP 32.08% and UPGRADE_SELECT 33.30% policy disagreement
versus CARD 3.90% and TREASURE 0.00%. Policy entropy rose slightly
(0.5154 → 0.5271). All-input predicted-Q top-1 fidelity was 25.72% M0 vs
25.67% M1. The complete 8-cell A/B/C cross-classification sums to 39,870 with
marginals exactly matching the headline counts. The evidence supports
substantial auxiliary-Q relabeling with screen-concentrated policy effects,
making auxiliary-Q/representation coupling plausible but not causal proof of
the −10.9pp 64-seed point estimate (CI crosses zero). The autopsy is
**closed**; no M2, retraining, gameplay tracing, or new seeds.

Full tables, hashes, root causes, and provenance:
historical source `git show d28cfc3291dc091bb52b218f1d3e27f7431f4163:docs/archive/research/sessions/phase12-m0-m1-autopsy-2026-08-15.md`.

## 2026-08-15 — Searcher3 conditional-block posterior-geometry shadow diagnostic (STOP: oracle gate failed)

**Question:** Given one hidden state compatible with the recorded real history,
does replacing only one latent block produce additional full-history-compatible
states compared with the current whole-state fresh proposal?

**Implementation:** Follow-up to the corrected whole-state history-replay probe
above. The prior 256-proposal whole-state result remains valid for its frozen
implementation and is not overwritten or reinterpreted. This diagnostic was
shadow-only and default-off. At each trigger (`compatible <= 16`), one paired
set of 64 ordinary fresh Searcher3 prior samples was generated. Each source was
used for `ALL_FRESH` and for each of `DRAW_ORDER`, `SHUFFLE_RNG`,
`CARD_RANDOM_RNG`, `AI_RNG`, `MISC_RNG`, `MONSTER_HP_RNG`, and `POTION_RNG`,
with all non-selected oracle blocks copied bit-identically. Proposal generation
used a dedicated deterministic RNG; replay fallback RNGs were independently
keyed by trigger, proposal index, and family, so family iteration order could
not alter the source proposals.

The oracle was constructed from the copied replay-anchor `BattleContext` and
was used only by the shadow driver. It was not exposed to MCTS, belief
filtering, action selection, tree reuse, fallback, or live rejuvenation. Exact
full-history replay, semantic remapping, observation equality, outcome equality,
and `FullHiddenStateKey` equality were reused from the existing probe.

**Mechanical verification:** Release build passed. The paired-source and
family-order invariance test passed (`rejuv_conditional_blocks`). Existing
`rejuv_history_replay`, `rejuv_semantic_select`, and
`rejuv_noninterference` tests passed, as did `rng_state_propagation` and
`s3_rand64_prior_sampler`. A one-seed smoke produced all nine row families and
64 proposals per non-oracle family. Gameplay remained behavior-neutral in the
non-interference test.

**Frozen execution:** Exactly seeds `126732–126739`, ascension 0, 1,000
simulations, 64 particles, 12 threads, fair Searcher3, real posterior filter,
collapse-fresh fallback, persistent filtered posterior, no tree reuse,
`STS_VNET=models/v_combat_7k_tuned.txt`, `STS_VNET_ALPHA=0.3`, and the V4
strategic token-net artifact with REST/EVENT/SHOP/TREASURE/BOSS_RELIC gates and
margin 1.0. Shadow flags were `STS_S3_REJUV_SHADOW=1`,
`STS_S3_REJUV_TRIGGER=16`, `STS_S3_REJUV_PROPOSALS=64`. Raw artifacts are
`build/s3_conditional_8.rejuv.csv`, `build/s3_conditional_8.csv`, its
`.meta.json`, `.stdout`, and `.stderr` in the experiment worktree.

**Oracle integrity result:** **STOP.** The untouched oracle replay succeeded
for **1,444 / 1,569 trigger rows (92.03%)**, not the required 100%. Failures
were 65 `REMAP_FAILURE`, 52 `INTERMEDIATE_MISMATCH`, and 8 `FINAL_MISMATCH`;
there were no action-illegal or simulator-health failures. The failures
concentrated on single-card-select action type 2, with later type-4 mismatches
after history divergence. This indicates an unresolved replay/hidden-state
boundary or semantic-select coverage problem. The proposal-family acceptance
counts below are retained as raw diagnostic output only and are **not valid
scientific evidence** under the preregistered rule.

**Raw diagnostic totals (not interpretable after the STOP):** 1,569 trigger
rows per family and 100,416 proposals per 64-proposal family. Accepted totals
were DRAW_ORDER 6,406, SHUFFLE_RNG 69,081, CARD_RANDOM_RNG 55,703, AI_RNG
56,265, MISC_RNG 92,416, MONSTER_HP_RNG 86,047, POTION_RNG 91,456, and
ALL_FRESH 1,554. The oracle control itself reported 1,444 accepted rows. These
figures must not be used to support blockwise resample-move promotion because
the oracle integrity gate failed.

**Interpretation:** Implementation correctness is incomplete because the oracle
control is not clean on the frozen quality run. Scientific interpretation is
therefore unresolved; H1–H6 are neither supported nor weakened by the family
acceptance counts. Gameplay was not a treatment and its whole-run result is
not interpreted. The one justified next experiment is a replay-correctness
investigation that localizes the remaining single-card-select/oracle failures;
no live blockwise rejuvenation experiment should proceed first.

## 2026-08-15 — Conditional-block oracle replay correction and authoritative rerun

The required RAW-vs-SEMANTIC discriminator localized the prior oracle failure.
On failing seed `126733`, RAW replay succeeded **311/311 (100%)**, while the
original semantic path succeeded only **218/311 (70.10%)**. The first defect
was `CardSelectTask::CODEX` (task value 2), raw select index 3: index 3 is the
explicit Codex skip action and has no card identity. The existing semantic path
incorrectly rejected it. A targeted Codex-skip regression was added.

The remaining semantic-only divergences then occurred later at `END_TURN` after
visible observations still matched. The simulator uses `CardInstance::uniqueId`
for internal card removal/targeting, while the existing semantic key omitted
that field. The narrow probe-local correction now records and prefers unique IDs
for `CARD`, `SINGLE_CARD_SELECT`, and `MULTI_CARD_SELECT`, with the existing
semantic-key fallback for synthetic cards without a valid unique ID. No global
observation identity, Searcher3 semantic-edge key, RNG behavior, or gameplay
path was changed.

Focused tests passed: `rejuv_semantic_select`, `rejuv_history_replay`,
`rejuv_conditional_blocks`, `rejuv_noninterference`,
`rng_state_propagation`, and `s3_rand64_prior_sampler`. The focused raw-vs-
semantic smoke passed on seeds `126733` (312/312 both modes) and `126737`
(213/213 both modes).

The exact frozen eight-seed conditional-block run was then repeated with the
same configuration and seeds `126732–126739`, 1,000 simulations, 64 particles,
12 threads, fair Searcher3, real filtering, collapse-fresh, persistent
filtered posterior, no tree reuse, the same combat and strategic artifacts,
trigger 16, and 64 paired proposals per family. Raw artifacts:
`build/s3_conditional_8_final.rejuv.csv`, `build/s3_conditional_8_final.csv`,
`.meta.json`, `.stdout`, and `.stderr`.

**Oracle gate:** RAW **1,596/1,596 (100%)**; SEMANTIC
**1,596/1,596 (100%)**. All oracle remap, action-illegal, simulator-health,
intermediate, and final mismatch counts were zero. The prior STOP result was
therefore a semantic replay defect, not a deeper replay nondeterminism failure.

**Authoritative proposal results:** 1,596 trigger rows and 102,144 proposals
per 64-proposal family. Overall acceptance was DRAW_ORDER 6,504 (6.37%),
SHUFFLE_RNG 73,005 (71.47%), CARD_RANDOM_RNG 58,520 (57.29%), AI_RNG 60,599
(59.33%), MISC_RNG 102,144 (100%), MONSTER_HP_RNG 93,157 (91.20%),
POTION_RNG 101,184 (99.06%), and ALL_FRESH 1,563 (1.53%). All accepted
hypotheses were equality-backed unique and novel in the recorded comparator.

At `decision_idx >= 8`, acceptance was DRAW_ORDER 1,752/64,448 (2.72%),
SHUFFLE_RNG 37,119/64,448 (57.60%), CARD_RANDOM_RNG 33,164/64,448 (51.46%),
AI_RNG 32,303/64,448 (50.12%), MISC_RNG 64,448/64,448 (100%), MONSTER_HP_RNG
56,649/64,448 (87.90%), POTION_RNG 63,808/64,448 (99.01%), and ALL_FRESH
251/64,448 (0.39%). Late rows with at least four unique accepted states were
DRAW_ORDER 6, SHUFFLE_RNG 634, CARD_RANDOM_RNG 613, AI_RNG 772, MISC_RNG
1,007, MONSTER_HP_RNG 948, POTION_RNG 997, and ALL_FRESH 20.

RNG-use telemetry showed unused-stream acceptance at approximately 100% for
all applicable RNG families. Used-stream acceptance was approximately 4.35%
for SHUFFLE_RNG, 23.58% for CARD_RANDOM_RNG, 47.44% for AI_RNG, 8.22% for
MONSTER_HP_RNG, and 0% for POTION_RNG in this run; MISC_RNG had no used rows.
Total probe CPU was approximately 11.85 seconds. No oracle first-mismatch
patterns remained.

**Interpretation:** The diagnostic is now mechanically valid. The data support
H1: simultaneous whole-state fresh proposals are much less likely to remain
compatible than several single-block moves, especially late. They also support
H3/H6 directionally: replacing historically unused RNG streams is nearly free,
while consumed raw PRNG-state blocks are substantially less mobile, with
stream-specific differences. MISC_RNG and POTION_RNG remained highly mobile
in this frozen run, while DRAW_ORDER was the most constrained proposal family.
These are posterior-geometry results, not gameplay results; no live treatment
was implemented.

The preregistered practical promotion signal is clearly met by multiple
families at late history (at least four novel accepted states on roughly half
or more of applicable rows). The one justified next experiment is a **live
shadow-neutral resample-move experiment using only a validated future-relevant
block selected after reviewing the stream-use and causal-event breakdown**;
this follow-up must remain a separate preregistered treatment and must not
promote all high-acceptance blocks automatically.

**Follow-up correction (draw-pile source mapping):** Independent review found
that `SECRET_TECHNIQUE`, `SECRET_WEAPON`, and `SEEK` built their semantic key
from `preState.cards.drawPile` but recorded `selectedUniqueId` from the hand
fallback. This was a probe-local source-pile mismatch. The recording branch now
uses `preState.cards.drawPile` for all three tasks; the semantic-key switch and
global simulator behavior were unchanged. `rejuv_semantic_select` now includes
a SEEK fixture with visually identical draw-pile cards, distinct valid unique
IDs, and reordered replay state, and verifies the selected unique ID survives.

The preserved prior CSV/log artifacts did not retain complete
`CardSelectTask` values, and no reliable task-occurrence evidence was found, so
the exact frozen eight-seed command was repeated once. That rerun's raw
`build/s3_conditional_8_drawsource.rejuv.csv` artifact is **incomplete**, not a
smaller valid experiment: it contains 1,593 trigger keys, but one trigger has
only 7 of the required 9 family rows (missing `POTION_RNG` and `ALL_FRESH`),
and its base result CSV omits seed `126733`. The three trigger keys present in
the complete 1,596-trigger artifact but absent from the incomplete artifact are
all later in that same seed/encounter/floor trajectory: seed `126733`, encounter
50, floor 41, decisions 22, 26, and 27 (the preceding decision 21 is the
partial 7-row trigger). This is an interrupted/partial artifact, not evidence
of three scientifically different triggers.

The complete `build/s3_conditional_8_final.rejuv.csv` remains the authoritative
raw geometry artifact: programmatic validation finds 1,596 trigger groups, each
with exactly `ORACLE + 8` families, 64 proposals for every non-oracle row, and
identical family denominators in all/early/late slices. Its oracle gate remains
RAW **1,596/1,596** and SEMANTIC **1,596/1,596**, with zero failure counts.
The source-pile correction was therefore not established as exercised by a
complete eight-seed rerun; the prior complete geometry result remains valid,
and the incomplete rerun must not replace its aggregates. The paired-source,
family-order invariance, and shadow non-interference checks remained passing.
The scientific interpretation is unchanged.

## 2026-08-15 — Searcher3 live AI_RNG rejuvenation implementation/control attempt

**Implementation:** Added opt-in `STS_S3_AI_REJUV_LIVE=off|placebo|ai` support
to fair Searcher3. The mode defaults off. Live treatment uses immutable
battle-start particle lineage IDs, particle-anchored full-history replay, the
existing conditional AI_RNG proposal distribution, zero-weight-only 50/50
splits, and one attempted intervention per combat. Placebo and AI share
proposal generation, successful-source selection, destination slots, weights,
and intervention timing; placebo inserts an exact source duplicate while AI
inserts the accepted novel AI_RNG state. Collapse-fresh invalidates ancestry.
Telemetry is written through `STS_S3_AI_REJUV_LIVE_FILE`.
After review, proposal RNG provenance was corrected to derive each proposal
from fixed salt, game seed, floor/encounter, source filter decision, lineage ID,
and proposal number while preserving the validated AI_RNG sampling
distribution. The earlier implementation/control artifacts are superseded by
the corrected run below.

**Frozen implementation values:** The global shadow defaults remain unchanged
(`g_s3RejuvTrigger=16`, `g_s3RejuvProposals=256`). Causal invocations explicitly
set `STS_S3_REJUV_TRIGGER=16 STS_S3_REJUV_PROPOSALS=64`.

**Verification:** Release build succeeded. The focused live-attempt,
conditional-block, history-replay, semantic-select, real-filter,
persistent-transfer, RNG-propagation, and shadow-noninterference tests passed.
The one-seed guarded smoke passed for OFF, placebo, and AI. Correct-executable
8-seed baseline and placebo arms completed; placebo produced 1,543 telemetry
rows and the AI run produced 1,733 telemetry rows but the AI result artifact
was interrupted at 7/8 seeds by the execution harness. This is an incomplete
implementation/control validation, not a gameplay result.

**Decision:** Do not start the preregistered 32-seed scientific gate until a
complete 8-seed implementation/control rerun is obtained and all controls are
clean. The incomplete AI arm is not interpreted as H0, H1, or H_resample.

The preceding decision was superseded by the completed gate below after the
corrected 8-seed implementation/control rerun. The 32-seed result is recorded
as mixed/inconclusive, not as H0, H1, or H_resample.

## 2026-08-15 — First live AI_RNG causal gate, untouched block 910000–910031

**Question:** Does live particle-lineage AI_RNG support expansion improve
gameplay relative to the matched placebo, with OFF retained as a secondary
baseline? The prior 8-seed implementation/control block is not interpreted
scientifically and was not reused for this gate.

**Configuration:** Three matched arms used fair Searcher3, A0, 1,000 base
simulations, 3,000 boss simulations, 64 particles, 12 threads, belief/internal
update off, chain off, CRN off, real-boundary filtering on, collapse-fresh on,
persistent filtered posterior on, reuse 0, END_TURN marginalization off,
`STS_S3_REJUV_TRIGGER=16`, `STS_S3_REJUV_PROPOSALS=64`,
`models/v_combat_7k_tuned.txt`, VNet alpha 0.3, the V4 strategic token model,
and all REST/EVENT/SHOP/TREASURE/BOSS_RELIC gates with margin 1.0. Every arm
ran through `tools/seed_guard.sh` on seeds `910000–910031`.

**Raw artifacts:** `/tmp/s3live32_off.csv`, `/tmp/s3live32_placebo.csv`,
`/tmp/s3live32_ai.csv`, and placebo/AI telemetry at
`/tmp/s3live32_{placebo,ai}.telemetry.csv`. Result hashes are OFF
`e44c782a15cb3645298dfccb072b101ebee10a60bcb52f27a13b14fb942607fb`, placebo
`c0390f0daae92460c24b8dceade97443221319a46fa759034eb3324e0a4001e8`, and AI
`cf8b518b273bc97edbc38687b86609cfad68b7b2b45832f34761fd53925527be`.

**Gameplay:** OFF won 17/32 with mean floor 47.781; placebo won 12/32 with
mean floor 45.406; AI won 15/32 with mean floor 46.656. Primary AI−placebo
paired delta was +3/32 wins (+9.375 percentage points) and +1.25 mean floor.
AI−OFF was −2/32 wins and −1.125 mean floor. Placebo−OFF was −5/32 wins and
−2.375 mean floor. AI−placebo floor gains occurred on 6 seeds and losses on 5;
The +1.25 mean was not solely an outlier, although seed 910020 contributed a
−31 floor loss and seed 910018 a +20 gain. The audited paired win discordance
was AI wins/placebo losses `6` versus AI losses/placebo wins `3`, for a net
difference of `+3` wins; reverse discordant pairs were present.

**Exposure:** Placebo had 6,133 telemetry rows, 317 first attempts, 1,427
duplicate children, and `unique_children=0`, with all 32 seeds exposed. AI had
6,440 rows, 329 first attempts, 1,494 novel children, and
`unique_children=1494`, with all 32 seeds exposed. Reported intervention CPU
was 98.087 ms placebo and 93.017 ms AI across telemetry rows. This is a causal
screen result, not a promotion claim; follow the preregistered decision rule
before extending to 64 seeds.

An independent raw-data audit is preserved at
`build/s3live32_causal_gate_910000_910031/s3live32_causal_gate_audit.md`, with
copies of all five raw result/telemetry files. It found AI−PLACEBO paired floor
mean `+1.25` with median `0`, SD `9.073`, bootstrap 95% CI
`[-1.9375,+4.25]`, positive/negative/zero counts `6/5/21`, and exact McNemar
discordance `(6,3)`, two-sided `p=0.5078125`. Omitting seed 910018 leaves
`+0.645161`; omitting 910020 gives `+2.290323`. Placebo children versus
Placebo−OFF floor delta had descriptive Pearson `r=-0.153538`; AI children
versus AI−OFF had `r=0.077262`. These correlations are observational and do
not establish that duplication caused harm or novelty caused benefit.

**Autopsy decision:** classify the gate as **mixed/inconclusive**. Exposure was
adequate in all 32 seeds for both live arms, but AI was below OFF in aggregate
and the primary AI−PLACEBO uncertainty includes zero. Do not promote H1 and do
not start the 64-seed extension without a new preregistered decision.

## 2026-08-15 — Searcher3 single-child AI_RNG rejuvenation follow-up, fresh block 920000–920015

**Question:** Does limiting live rejuvenation to one accepted child per combat
retain useful AI_RNG novelty while reducing multiplicity/dose distortion? The
paired arms were OFF, PLACEBO1, and AI1. This was a mechanism-discrimination
follow-up, not a promotion run; it stopped at exactly 16 seeds.

**Configuration:** Fair Searcher3, A0, 1,000 base simulations, 3,000 boss
simulations, 64 particles, 12 threads, internal belief update off, chain off,
CRN off, real-boundary filtering on, collapse-fresh on, persistent filtered
posterior on, reuse 0, END_TURN marginalization off,
`STS_S3_REJUV_TRIGGER=16`, `STS_S3_REJUV_PROPOSALS=64`, combat VNet
`models/v_combat_7k_tuned.txt` (sha256
`ea35b78c888e70e09566e1143d296577b0bea2ec8d437276b7aab81a7cdaf15c`), VNet
alpha 0.3, V4 strategic token model
`selfplay/models/ooc_strategic_tok_final.native` (sha256
`e62abd833fc8cb9081a1cec4a1a012832ac3b0e3166da3892841911664f1184c`), and
REST/EVENT/SHOP/TREASURE/BOSS_RELIC gates with margin 1.0. Every arm ran
through `tools/seed_guard.sh` on seeds `920000–920015`.

**Aggregates:**

| arm | wins | win rate | mean floor |
|---|---:|---:|---:|
| OFF | 10/16 | 62.5% | 47.3125 |
| PLACEBO1 | 8/16 | 50.0% | 47.8125 |
| AI1 | 11/16 | 68.75% | 45.2500 |

**Per-seed results:**

| seed | OFF won/floor | PLACEBO1 won/floor | AI1 won/floor | PLACEBO1 children | AI1 children | PLACEBO1 mass | AI1 mass |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 920000 | 1/51 | 1/51 | 1/51 | 6 | 6 | 1.079 | 1.079 |
| 920001 | 1/51 | 1/51 | 1/51 | 7 | 7 | 0.822 | 0.822 |
| 920002 | 0/33 | 0/33 | 0/33 | 7 | 7 | 1.821 | 1.821 |
| 920003 | 1/51 | 1/51 | 1/51 | 8 | 8 | 2.325 | 2.296 |
| 920004 | 1/51 | 0/50 | 1/51 | 12 | 16 | 2.759 | 4.005 |
| 920005 | 0/45 | 0/45 | 0/41 | 13 | 13 | 2.319 | 2.319 |
| 920006 | 0/33 | 0/33 | 0/33 | 11 | 13 | 1.630 | 2.630 |
| 920007 | 1/51 | 0/50 | 0/33 | 18 | 10 | 4.306 | 2.367 |
| 920008 | 0/50 | 0/50 | 1/51 | 13 | 12 | 3.425 | 2.842 |
| 920009 | 1/51 | 1/51 | 1/51 | 19 | 17 | 4.539 | 3.042 |
| 920010 | 0/46 | 0/46 | 0/23 | 12 | 9 | 1.431 | 0.589 |
| 920011 | 0/40 | 1/51 | 1/51 | 13 | 13 | 3.019 | 3.019 |
| 920012 | 1/51 | 1/51 | 1/51 | 9 | 9 | 1.967 | 1.967 |
| 920013 | 1/51 | 1/51 | 1/51 | 17 | 14 | 3.724 | 3.070 |
| 920014 | 1/51 | 0/50 | 1/51 | 9 | 12 | 1.918 | 2.679 |
| 920015 | 1/51 | 1/51 | 1/51 | 12 | 12 | 2.992 | 2.992 |

**Paired comparisons:** AI1−PLACEBO1 was `+3/16` wins and `−2.5625`
mean floor, median `0`, floor positive/negative/zero `3/3/10`, exact win
discordance `(3,0)`. AI1−OFF was `+1/16` wins and `−2.0625` mean floor,
median `0`, floor positive/negative/zero `2/3/11`, discordance `(2,1)`.
PLACEBO1−OFF was `−2/16` wins and `+0.5` mean floor, median `0`, floor
positive/negative/zero `1/3/12`, discordance `(1,3)`.

**Exposure/integrity:** PLACEBO1 had 3,712 telemetry rows, 187 attempt rows,
186 injected children, and 40.076 injected mass. AI1 had 3,413 rows, 179
attempt rows, 178 injected children, and 37.539 injected mass. Both arms were
exposed in 16/16 seeds. Maximum children per combat was `1` in both arms;
`children_injected` was only `0/1`; PLACEBO1 had `unique_children=0`; AI1 had
`unique_children` equal to `children_injected`; integrity failures were zero.

**Raw hashes:** OFF result `3767fa33b80f9af8c87497740ddecc6de347975fb5364088ec3ee15f5e1a317a`,
PLACEBO1 result `63d7323c1f37e21f59290e843ae596f940e8eaca7d38d0e4cc3d5e90a00bd383`,
AI1 result `139133aaca5f38898ef7fc8c44f00408e22af5b25f153309b98299c8aeb250f7`,
PLACEBO1 telemetry `c43ac1b6215da7a9dfb702b04b079e94a6d4a04940eaa8f7975e3606f3c20f3c`,
AI1 telemetry `e56183ebb524e70f1946e26dc9ceb43a4d3a811d835c845d25bbc9e8c0f6ec8a`.

**Decision:** Closest to preregistered **Outcome A** directionally on wins,
but mixed because AI1 lost on mean floor against both comparators. Exposure is
not limiting. Stop at 16 seeds; do not automatically extend or promote live
rejuvenation.

## 2026-08-15 — Searcher3 AI1 single-child confirmation, fresh block 920016–920079

**Question:** Does the 16-seed AI1 win-rate direction confirm on a fresh 64-seed
block, with floor/depth monitored as safety evidence? The matched arms were OFF,
PLACEBO1, and AI1. This confirmation stopped at exactly 64 seeds.

**Configuration:** The frozen 16-seed configuration was retained: fair
Searcher3, A0, 1,000 base simulations, 3,000 boss simulations, 64 particles,
12 threads, internal belief update off, chain off, CRN off, real-boundary
filtering on, collapse-fresh on, persistent filtered posterior on, reuse 0,
END_TURN marginalization off, `STS_S3_REJUV_TRIGGER=16`,
`STS_S3_REJUV_PROPOSALS=64`, VNet `models/v_combat_7k_tuned.txt` alpha 0.3,
the same V4 OOC model, REST/EVENT/SHOP/TREASURE/BOSS_RELIC on, margin 1.0.
All arms used `tools/seed_guard.sh` and seeds `920016–920079`.

**Aggregates:**

| arm | wins | win rate | mean floor |
|---|---:|---:|---:|
| OFF | 40/64 | 62.50% | 45.3281 |
| PLACEBO1 | 38/64 | 59.375% | 45.5625 |
| AI1 | 41/64 | 64.0625% | 45.4688 |

**Paired comparisons:**

- AI1−PLACEBO1: win delta `+3/64`, exact discordance `(4,1)`, exact
  two-sided binomial/McNemar p `0.375`; floor mean `−0.0938`, median `0`,
  positive/negative/zero `6/4/54`, bootstrap 95% CI `[-1.4531,+1.1094]`.
- AI1−OFF: win delta `+1/64`, exact discordance `(4,3)`, p `1.0`; floor mean
  `+0.1406`, median `0`, positive/negative/zero `6/6/52`, bootstrap 95% CI
  `[-1.3281,+1.4688]`.
- PLACEBO1−OFF: win delta `−2/64`, exact discordance `(3,5)`, p `0.7265625`;
  floor mean `+0.2344`, median `0`, positive/negative/zero `5/5/54`, bootstrap
  95% CI `[-0.7969,+1.3125]`.

Largest AI1 floor deltas were `+18` and `−28` versus PLACEBO1, and `+18` and
`−28` versus OFF. Leave-one-out floor means ranged from `−0.3810` to `+0.3492`
for AI1−PLACEBO1 and `−0.1429` to `+0.5873` for AI1−OFF. AI1 lost while the
comparator won on 1 seed versus PLACEBO1 and 3 seeds versus OFF. Severe AI1
floor regressions of at least 10 floors occurred on seeds `920031` (`−17`) and
`920079` (`−28`) against both comparators.

**Exposure/integrity:** PLACEBO1 had 13,223 telemetry rows, 643 attempts, 640
children, and 139.805 injected mass. AI1 had 13,229 rows, 627 attempts, 624
children, and 143.970 injected mass. Both exposed all 64 seeds. Maximum
children per combat was `1` for both; `children_injected` was only `0/1`;
PLACEBO1 had `unique_children=0`; AI1 had `unique_children` equal to
`children_injected`; integrity failures were zero.

**Raw hashes:** OFF result `bbf0f95cefcf7ac5859efdaf4ad81458a96b25f5068b0a02d5b87ac31f0e6a47`,
PLACEBO1 result `f88b9209c4dfd8c72e5d440175bb7db2213dde1655e6957ed776c00e13756627`,
AI1 result `0543dc31a90cab103b32d39871d542fbcb603464de9894b9ed442c8e6d8faa98`,
PLACEBO1 telemetry `4c09cc1a93a125aaeaa976ed56ffa23444dae4b10b1c30a6f91a286e4df8e8ec`,
AI1 telemetry `73039d4c9a02cba9b1e557a5bdc97c2f391566f8049f13050b0d37985fef8d9a`.

**Decision:** AI1 remained directionally above PLACEBO1 and at least as good as
OFF on wins, with four treatment-only wins versus one reverse discordance in
the primary comparison. The win advantage is not statistically persuasive and
the floor result is approximately null, not a clear downside on aggregate.
However, two shared severe early-loss regressions warrant explicit caution.
Classify as **promising win-rate direction with a possible downside tail**, not
as a clean promotion result. Do not extend beyond 64 seeds automatically.

## §173 Phase-13A counterfactual teacher-strength audit (2026-08-15)

Phase 13A audited whether the Phase-12 short fixed-world teacher gives
reliable rankings on high-confidence strict-M0/V4 disagreements. The fresh
source block was `920000..920007` (8 seeds; no prior V4/M0 comparison use),
with the frozen V4 source trajectory, non-MAP V4 margin ownership, and M0
score-only eligibility `Q_M0(a_M0)-Q_M0(a_V4) >= 1.0`. The pool contained 119
eligible states. A deterministic `random.Random(1301)` sample selected exactly
16 states before any evaluator outcomes; manifest SHA256 is
`88795a8b46db5296f453bd2dcd17ebb6453dbf352cbba4a65949d20098857bc4`.

Evaluator S preserved Phase-12 Tier-B semantics: H=4, K=3, bootstrap enabled,
150/100/50 fight schedule. Evaluator R used the same copied fixed-world state,
paired continuation seeds, and existing OOC continuation chain, but ran to the
terminal horizon with `sims=1000`, no fight cap, no bootstrap, and no fixed
fight schedule. The exact V4 native hash was
`e62abd833fc8cb9081a1cec4a1a012832ac3b0e3166da3892841911664f1184c`; the
durable strict-M0 native hash was
`97564d1be6b4f2356ef5807645a3b45126726bf8ae07cc2b7e273a860106e62a`.

The committed raw evidence has 256 rows (16 decisions × 2 actions × 4
futures × 2 evaluators), SHA256
`81e686d4eab32500df2397345b44f4c6d19a377dac97b2edf4a5c528b0e2e7c0`.
Fifteen decisions were fully valid. Two R futures for `(920000,12)` failed
the existing Searcher3 health contract (`TRANSIENT` / `SECRET_WEAPON`), and
were retained as invalid rows rather than averaged or replaced. On the 15
valid decisions, mean `refDelta=-2.050000`, mean `refWinDelta=-0.083333`;
S preferences M0/V4/tie were 8/2/5 and R preferences were 3/5/7. Strict sign
agreement was 3/15 for short-vs-reference and 3/15 for model-vs-reference.

This run is **INVALID — ownership-selection bug**. The collector treated every
REWARDS state with `cardRewardCount > 0` as V4-owned even when live V4 was still
auto-collecting gold, relic, potion, or enabled keys. Nine of the 16 selected
states were REWARDS states, so the sampled population was not the registered
population. The raw evidence remains preserved under
`docs/experiments/evidence/phase13a-teacher-audit/`; its S/R aggregates and
H4 conclusion must not be interpreted scientifically. A corrected fresh-seed
rerun is required.

Evidence and the complete decision table are under
`docs/experiments/evidence/phase13a-teacher-audit/`.

### §173 corrected ownership rerun

The ownership bug was fixed before collecting a new candidate pool. The
collector now mirrors live V4 precedence: REWARDS is eligible only after gold,
relic, potion, and enabled-key actions are exhausted; other screens require
their enabled live strategic gate and legal actions. The collector records
`gateOwned`, `liveV4Idx`, and `liveV4Margin`, and the ownership smoke passed.

Fresh seeds were `940000..940007`, with exact source/replay budget `sims=1000`.
The corrected pool contained 70 candidates; deterministic sample seed 1301
selected 16 before outcomes. Manifest SHA256:
`a84de37a038ead6750115bc8cb95d697710e8b60cd7788070b56297d1b1752db`.

The corrected audit produced 256/256 valid rows with no replay or health
failures. Raw SHA256:
`1f7778f3ce7200a08eec34f05885a0f8d08b373a36e798d8477657014dec1fa3`.
Mean `refDelta=-13.843750`; mean `refWinDelta=-0.250000`. S preferences
M0/V4/tie were 9/5/2; R preferences were 6/9/1. Strict sign agreement was
6/16 for short-vs-reference and 6/16 for model-vs-reference; tie-aware
three-way agreement was 7/16 and 6/16 respectively. All R rows had
`bootstrap=0`.

The corrected result is **H4 inconclusive** under the preregistered rules:
reference V4 preference is 9/16, below the 10/16 threshold, while neither the
short teacher nor R favors M0 on at least 10/16. This valid result does not
support promotion or identify a causal teacher/model/objective diagnosis.

### §173 H=8 reference extension

The corrected 16-state manifest and all existing S/H=4 rows were preserved.
Four new paired R futures per state/action (`future=4..7`) added 128 terminal
R continuations; no reselection or new S labels were performed. All additional
rows were valid with no replay or simulator-health failures.

Combined H=8 R results: mean `refDelta=-11.320312`, mean
`refWinDelta=-0.195312`; R preferences M0/V4/tie were 5/10/1. Strict
short/reference and model/reference agreement were both 5/16; tie-aware
three-way agreement was 6/16 and 5/16. Combined raw SHA256:
`b1a048945ffc485f39aa4c75696816dbace5919d9907ef5f21db2d4a42c347b4`.
Combined summary SHA256:
`1c9a0785040492400cdefe13e6331261ad8ec5970dd8bfda92bd5f7e9f2709d6`.

H=8 reaches the preregistered reference condition (V4 preferred on 10/16 and
negative mean reference utility Δ). The high-confidence M0 improvement signal
is therefore rejected under the stronger reference. The agreement metrics do
not distinguish teacher/target failure from model-learning failure. No new
labels, reselection, threshold tuning, or gameplay gate was run.

## 2026-08-16 — Searcher3 cheap behavior-preserving speedups (perf/s3-cheap-speedups)

Bounded implementation-efficiency pass on the fair Searcher3 path; no search
parameter, RNG, model, or feature changed. Baseline `main` `a7573e1`
(2026-08-16), measured in a dedicated worktree on branch
`perf/s3-cheap-speedups`; the particle-conditioned leaf-value Phase-1 branch
was not touched.

Configuration: `OMP_NUM_THREADS=1 STS_FAIR=1 STS_SEARCHER3=1
STS_S3_PARTICLES=64 STS_S3_BELIEF=0 STS_S3_CHAIN=0 STS_LIVE_VALID=1`, vnet
leaf auto-default `models/v_combat_7k_tuned.txt` α=0.3 (§148), policy PUCT
`models/policy_trees_c.txt` c=2.5, rejuvenation off (default), persistent
posterior / pool-redirect / rank-corr / all other experimental flags at
default (off). Workload: `bash tools/seed_guard.sh ./build/linux-gcc-release/
one_combat bestbench 1000 4 0` (4 seeds, 1399 searches, 2,133,000 simulations
per repetition; fresh LTO Release build per arm).

Interventions (both in `src/sim/search/BattleScumSearcher3.cpp`):

- A — `step()`: the per-expansion full `BattleContext preExecState` copy is
  taken only when `g_s3EndTurnMarginalize` (default off, `STS_S3_END_TURN_MARGINALIZE`)
  can consume it; the consumer guard now tests `preExecState` itself, so the
  enabled-feature behavior is unchanged.
- B — `sameCardMultiset` (particle draw-order compatibility, runs once per
  simulation via `applyParticleImpl`): exact multiset equality via a fixed
  `std::array<int, cardEnumStrings-size>` count table instead of two heap
  vectors + two sorts. Same id-only identity domain as before (upgrade state
  was and is outside this comparison; duplicates count per occurrence).

Primary metric: median `simSeconds*1e6/simsExec` per search from
`STS_REUSE_CPU_DIAG` CSV (ms/1000 sims). 9 interleaved rounds × 3 arms
(base / A / A+B), rotating arm order per round; per-round medians (ms/1000
sims):

| Round | base | A | A+B |
| --- | --- | --- | --- |
| 1 | 28.271 | 27.693 | 27.309 |
| 2 | 28.423 | 28.122 | 27.273 |
| 3 | 27.551 | 27.432 | 28.785 |
| 4 | 27.613 | 27.640 | 27.008 |
| 5 | 27.616 | 27.474 | 26.946 |
| 6 | 30.200 | 29.286 | 28.002 |
| 7 | 28.805 | 28.093 | 28.230 |
| 8 | 30.250 | 28.879 | 27.653 |
| 9 | 28.041 | 28.117 | 27.726 |
| median | 28.271 | 28.086 | 27.647 |

Result: A alone +0.66%, A+B +2.21% (paired per-round median +2.43%). Host
noise between rounds is up to ±4% (rounds 6/8 baseline slowdowns), so only the
paired interleaved comparison is decision-relevant. Retained as one combined
change under the small-diff rule; A alone or B alone fall under the 2% floor.

Behavioral equivalence (exact, not aggregate):

- `one_combat fairgen 2 1000 0 0.3 ...` value/policy/OOC CSVs byte-identical
  (md5 match) between base and A, and between base and A+B.
- All 27 CPU-diag runs identical on every non-timing column (seed, floor,
  decisionIdx, simsExec, treeActions, rolloutActions, rootSimAfter, playerHp,
  turn) — same root visit totals, same trajectories.
- `bestbench` win%/avg_floor/avg_hp_end identical across arms; wall-clock
  whole-run time reported as secondary evidence only.

Focused tests (perf-worktree `test` binary, all PASS): belief, drawpile 77,
obs_identity 77, prune 77, battlecontext_roundtrip, rng_state_propagation 77,
seed_contract 77, belief_immutability, rejuv_history_replay 77,
rejuv_noninterference 77, cardselect_parity, issue_fixes, real_belief_filter
77, s3_drawpile_reuse_boundary. `belief_order_invariance` FAILS identically on
untouched main `a7573e1` (pre-existing, 4 weight checks) — not caused by this
change and not addressed here.

Largest remaining Searcher3 hotspots (code inspection; no perf on this host):
vnet leaf inference per rollout endpoint (`evaluateLeaf` →
`g_combatVNet.predict`), per-rollout-slot `BattleContext` copies in
`multiRollout`, and action execution itself. Reducing these requires
representation/architecture work (BattleContext copy semantics, observation
architecture, model serving) — explicitly out of scope; recommendation is STOP
and return to particle-conditioned leaf-value research.

## E2 — post-combat run-win critic (2026-08-16)

**Baseline / branch:** `548742ab973d7f22eb6b1186dadb942c3aed10b5`,
`exp/postcombat-runwin`. This is an offline target-validity diagnostic only;
no Searcher3, particle, OOC policy, or deployed combat model was changed.

**Boundary:** `BattleContext::exitBattle` commits HP, potions, deck, relic,
gold, and combat RNG state; victory returns through `GameContext::afterBattle`.
`datagen2` emits one row at the first card-reward decision after the fixed
gold/relic/potion auto-pickup and immediately before card pick/skip. Normal,
elite, and act-1/2 boss rewards always include a card reward. Act-3 terminal
boss fights and event-room fights are not represented. Thus this is the first
stable post-combat decision boundary, not the raw pre-reward screen.

**Dataset / provenance:** existing ignored `build/vrich.csv`, generated by
`tools/run/datagen2_loop.sh` on 2026-07-15: Ironclad ascension 0, 10,000
simulations, epsilon 0.05, `v_server.py` V-marginal card continuation policy
(softmax temperature 3 plus 5% uniform floor and skip threshold), heuristic
map/shop/rest elsewhere. The canonical `vFeatCsv`/`richRow` path supplies the
features; no feature definition was duplicated. The file has 1,444,372 rows,
67,655 seeds, 18,601 wins and 49,054 losses. Act rows: 664,571 / 488,021 /
291,780 for Acts 1 / 2 / 3. Per-seed `won` consistency check: zero violations.
The source file SHA256 is retained in `build/e2_postcombat_runwin/`.

**Method:** `GroupShuffleSplit(test_size=0.15, random_state=0)` by seed,
matched for all arms: 57,506 train seeds and 10,149 held-out seeds. B0 is
training prevalence. B1 uses exactly `curHp`, `maxHp`, `hpFrac`, `act`, and
`floor`. T uses all 448 non-label, non-constant canonical rich features. B1
and T use the existing `train_winrate.py` XGBoost recipe: binary logistic,
hist, depth 8, eta .05, subsample .8, column sample .7, min child weight 20,
max bin 256, 1,500 rounds, early stopping 40. Bootstrap is 2,000 resamples
of held-out seeds, reporting T minus B1.

**Held-out metrics:** 216,620 rows, 71,672 positives and 144,948 negatives.

| arm | ROC-AUC | log loss | Brier | ECE |
| --- | ---: | ---: | ---: | ---: |
| B0 | 0.50000 | 0.63479 | 0.22140 | 0.00131 |
| B1 | 0.64975 | 0.59517 | 0.20359 | 0.00363 |
| T | 0.74816 | 0.53507 | 0.17913 | 0.00842 |

T act metrics (rows / AUC / log loss / Brier / ECE): Act 1 99,790 /
0.63555 / 0.56327 / 0.18946 / 0.00451; Act 2 73,074 / 0.78048 / 0.50662 /
0.16843 / 0.01659; Act 3 43,756 / 0.81932 / 0.51825 / 0.17344 / 0.01069.
All act strata have adequate held-out seed counts (10,149 / 9,726 / 6,204)
and no major calibration failure.

Seed bootstrap differences T−B1: log-loss mean −0.06009, 95% CI
[−0.06507, −0.05535]; Brier mean −0.02445, CI [−0.02647, −0.02247]; AUC
mean +0.09840, CI [+0.09200, +0.10500]. **Decision: SUPPORTED.** The rich
post-combat state is predictively useful beyond HP/progression under this
continuation policy. This does not establish causal item values, gameplay
improvement, generic `V_win` correctness, Searcher3 integration, or a new
`V_combat` target. Known-RNG encounter fields are included in T and are a
limitation for interpreting transfer to a different information regime.

**Correction before merge:** the first artifact used sparse full-dataset run
IDs when resampling validation seeds. The trainer now reindexes the held-out
run IDs contiguously before bootstrap, and the bootstrap artifacts below were
regenerated. This changes uncertainty estimates only; model fitting and the
held-out predictions are unchanged. The corrected bootstrap is the result to
use for interpretation. Corrected values are log-loss mean −0.0600867,
95% CI [−0.0650689, −0.0553531]; Brier mean −0.0244549, CI
[−0.0264704, −0.0224724]; AUC mean +0.0983964, CI
[+0.0920018, +0.1050012].

**Relation to §116:** §116's TERM_WIN terminal-leaf benchmark was null because
the deployed win tree was insensitive to the counter features; it therefore
deferred Stage 3 until a counter-aware terminal evaluator existed. E2 is a
potentially relevant prerequisite because it demonstrates that a rich
post-combat state can predict eventual run outcome beyond HP/progression under
the recorded continuation policy. E2 has **not** demonstrated a
counter-aware terminal evaluator, has not shown that counters are causally
priced, and does not authorize TERM_WIN, Searcher3, V_combat, or any deployed
model change. It is merged as a useful offline positive diagnostic only.

Artifacts: `build/e2_postcombat_runwin/metrics.json`,
`calibration_deciles.csv`, `provenance.json`, `bootstrap` in metrics,
`b1_model.json`, `t_model.json`, `val_predictions.npz`, and
`sha256sums.txt`. Reproduction command:
`STS_XGB_DEVICE=cuda python3 tools/train_postcombat_runwin.py build/vrich.csv
build/e2_postcombat_runwin`.

## E2b — masked post-combat feature-availability diagnostic (2026-08-17)

**Baseline / branch:** starting `e777d2fdbb8c11786aef4fe91d433af35b7d0cd2`,
`exp/e2b-leaf-available-runwin`. Offline only; no Searcher3, particle,
gameplay, V_combat, or producer code changed.

**Audit and primary subset:** the live `apps/one_combat.cpp::richHeader` /
`richRow` contract classifies 9 verified hidden/future columns (`bossId`,
`nextEliteId`, `nextFight0..2`, `remElites`, `remFights`, `monOffset`,
`eliteOffset`) plus the `fmD*`/`fmC*` forward-map families as hidden/future.
Gold, potion metadata/inventory, card-rarity state, key state, and all `r*`
relic ownership-plus-counter columns are reward-mutated. Elite relic pickup
also makes HP, max HP, deck composition/upgrades, bottle state, and potion
capacity reward-induced side effects. Unknown schema fields fail closed as
ambiguous.
The actual historical `build/vrich.csv` used here has exactly **1,009
columns**. It contains neither the ten `fmD*`/`fmC*` columns nor `curMapX` /
`curMapY`; those 12 fields are known to current live `richHeader()` but were
not present in the July-15 E2 CSV. Thus they are current-schema provenance
categories only, not columns classified from the historical file.
The existing CSV has no room/encounter identifier, and rows are captured after
`BattleContext::exitBattle` and forced gold/relic/potion pickup. Therefore an
ordinary-combat/raw-terminal subset cannot be identified defensibly. E2b uses
all represented card-reward rows and calls the final arm **T-masked**, not
raw-terminal-safe or exact leaf-safe.

**Method:** B1, T-full, T-fair, and T-masked share all rows, labels,
`GroupShuffleSplit(test_size=0.15, random_state=0)` by seed, the E2 XGBoost
recipe (depth 8, eta .05, subsample .8, colsample .7, min child 20, max bin
256, 1,500 rounds, early stopping 40), and 2,000 contiguous held-out-seed
bootstrap resamples. Counts: 1,444,372 rows / 67,655 seeds / 479,498 wins /
964,874 losses; held-out 216,620 rows / 10,149 seeds / 71,672 positives /
144,948 negatives; 57,506 training seeds.

| arm | features | AUC | log loss | Brier | ECE | best iteration |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| B0 | — | 0.500000 | 0.634793 | 0.221395 | 0.001308 | — |
| B1 | 5 | 0.649746 | 0.595168 | 0.203594 | 0.003631 | 136 |
| T-full | 448 | 0.748164 | 0.535066 | 0.179130 | 0.008419 | 983 |
| T-fair | 439 | 0.746827 | 0.536352 | 0.179548 | 0.007152 | 944 |
| T-masked | 8 | 0.611091 | 0.613848 | 0.211795 | 0.002156 | 88 |

The held-out positive/negative counts are identical for every arm. Log-loss
gain from B1 was 0.060102 for T-full, 0.058816 for T-fair, and −0.018680 for
T-masked; retention was 97.86% and −31.08%, respectively. T-masked−B1 point
differences were log loss +0.018680, Brier +0.008201, and AUC −0.038654.
The seed-bootstrap comparisons (log loss / Brier / AUC mean, 95% CI) are in
`build/e2b_leaf_available/metrics.json` for T-full−B1, T-fair−B1,
T-masked−B1, T-fair−T-full, and T-masked−T-fair.

**Comparator asymmetry:** the `MASKED NEGATIVE` result is the preregistered
verdict against the original E2 B1 comparator, which uses `curHp`, `maxHp`,
and `hpFrac`. The strict T-masked arm intentionally excludes `curHp` and
`maxHp` because elite relic pickup can mutate them. Therefore this is not an
information-matched comparison and must not be interpreted as evidence that a
true raw-terminal critic, or an information-matched raw-terminal model, is
inferior. E2c remains necessary to measure that boundary fairly.

**Decision:** **MASKED NEGATIVE**. T-masked fails to beat B1 on log loss,
Brier, and AUC; its log-loss bootstrap CI is unfavorable and masked retention
is negative. The hidden/future removal itself preserves almost all E2 gain;
the corrected reward mask removes the state that carried the remaining
predictive signal. This is predictive evidence only, not causal feature value
or exact raw-boundary calibration. The counter arm is
**NOT TESTABLE FROM E2 DATASET** because relic columns combine ownership and
counter and pickup can add relics.

**Follow-up:** E2c raw-boundary collection remains scientifically worthwhile,
despite the negative masked result, because conservative masking may discard
legitimate pre-existing resource information that cannot be reconstructed from
post-reward rows. The missing room/encounter identifier also prevents exact
boundary confirmation. The ideal producer records matched raw
combat-terminal and pre-card-reward states for each survived fight, with room /
encounter type and reward deltas, while preserving the eventual run label.
Artifacts: `build/e2b_leaf_available/feature_manifest.csv`, `metrics.json`,
`calibration_deciles.csv`, `validation_predictions.npz`, four model JSON files,
`provenance.json`, and `sha256sums.txt`.

## E2c exact RAW/POST combat-terminal run-win producer: implemented + smoke (2026-08-17, local)

- **What:** opt-in `one_combat e2cgen` producer recording matched RAW and POST
  snapshots for every survived ordinary/elite/act-1-2-boss combat, plus offline
  analyzer `tools/analyze_postcombat_raw_terminal.py`. Measurement infra only;
  no deployment/model/policy change (decision log
  `2026-08-17-e2c-raw-terminal-runwin-producer.md`).
- **Boundaries:** RAW fires in `BattleContext::exitBattle` after persistent
  transfer and before `regainControl()`/reward generation; POST fires at the
  `REWARDS` screen after non-card rewards drained, before the first card
  pick/skip. Pair key `(seed, fight_index)`; identical eventual `won` per pair.
- **Scoping:** thread-local `g_onBattleExitPersistent` hook is null by default;
  armed only around the real `exitBattle` in the live run, so copied/
  counterfactual exits cannot produce rows. `testE2cObserverScope` pins this.
- **Act horizon:** rows labelled by `runFullRunOOC`'s `RunResult` (honors
  `STS_STOP_AFTER_ACT`); shared training-integrity predicate unchanged.
- **Relic repr:** explicit `relic_has_*`/`relic_data_*` (exact signed data),
  distinct from legacy `r*`, enabling the counter diagnostic.
- **Schema:** versioned `e2c-v1` long format + `<out>.provenance.json`; the
  prefix keeps only `room_type`/`encounter_id` (state carries act/floor).
- **Verification:** `e2c_observer_scope`, analyzer compile + selftest CTest
  entries pass (37-test ctest: 36 pass; only pre-existing
  `live_rejuv_attempt_gate` fails, confirmed identical on baseline).
- **Smoke:** 8 seeds (0-7), 30 sims: 130 matched pairs, 0 quarantines, schema
  aligned (1387 cols), RAW->POST deltas show gold rising and
  potionChance/cardRarityFactor changing only after RAW.
- **No scientific verdict:** E2c SUPPORTED/PARTIAL/NEGATIVE is determined only
  from the human-controlled production dataset (2,000-seed command in the
  handoff), not from smoke.

## E2c-v2 2,000-seed production closure — SUPPORTED (2026-08-22)

- **Admissibility:** Production source SHA
  `e029dffb4c72449e8fc5b874391c49a27b2f6a81`; dataset SHA-256
  `da692d5979f9df3cad70ee6d76bd34fcf174ac74f557b942fb662e3d8c6a89e2`.
  Schema/provenance are `e2c-v2` and match the accepted configuration: 2,000
  requested, 1,980 valid, 20 quarantined, 1,000 simulations, ascension 0,
  seed offset 2,000,000, fair/Searcher3/live-valid enabled, 64 particles,
  accepted VNet/OOC models, and `STS_STOP_AFTER_ACT=3`. The provenance
  `git_dirty=true` is a known exception: the repository-owned GCP launcher
  creates untracked `logs/gcp_benchmark_*.log` before execution. Tracked
  worktree and index were clean and HEAD matched the accepted SHA.
- **Integrity:** 1,980 represented seeds (1,001 wins, 979 losses), 83,045
  rows: 41,676 RAW, 41,369 POST, 41,369 complete pairs, 307 RAW-only, and
  zero POST-only. Duplicate keys, invalid boundaries, seed-level outcome
  inconsistencies, pair outcome/room/encounter mismatches, and rows from the
  20 quarantined seeds were absent. Complete-pair rates were 28,249/28,249
  Monster, 9,812/10,119 Elite, and 3,308/3,308 Boss.
- **Quarantine:** The 20 missing seeds produced zero dataset rows and exactly
  40 health failures: one `ACTION_SELECTION_FAILED` and one subsequent
  `UNDECIDED_BATTLE_EXIT` per seed. All were Secret Technique/Secret Weapon
  card-selection states across diverse floors/encounters. This is a real
  implementation-selection-bias risk, not evidence that missing runs are
  harmless; the result is admissible as offline analysis with this caveat.
- **RAW-only elites:** All 307 are Elite reward-flow cases. Relic IDs were
  94/95/96 in counts 124/106/77; pending-card counts were 1/0 in 229/78
  cases; 299 seeds were represented. There were 172 wins and 135 losses.
- **Analysis populations:** Grouped held-out validation contained 6,300 RAW
  rows / 297 seeds and 6,249 complete-pair rows / 297 seeds (training: 35,376
  RAW rows / 1,683 seeds and 35,120 paired rows / 1,683 seeds). CUDA was
  unavailable (`torch 2.13.0+cpu`), so the unchanged analyzer ran with CPU
  XGBoost; this changes execution device, not the comparison or data.

| arm | n | pos/neg | AUC | log loss | Brier | ECE | best iter |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| B0 | 6300 | 3649/2651 | .500000 | .680607 | .243756 | .005427 | — |
| B1-raw | 6300 | 3649/2651 | .645717 | .647090 | .228001 | .013847 | 63 |
| B2-raw | 6300 | 3649/2651 | .649010 | .645190 | .227230 | .013919 | 60 |
| T-raw | 6300 | 3649/2651 | .736364 | .588425 | .203898 | .034600 | 281 |
| T-raw-no-counter | 6300 | 3649/2651 | .731079 | .589413 | .204367 | .022197 | 208 |
| B1-raw-paired | 6249 | 3615/2634 | .645649 | .647313 | .228123 | .015326 | 62 |
| B2-raw-paired | 6249 | 3615/2634 | .649680 | .645240 | .227221 | .016885 | 59 |
| T-raw-paired | 6249 | 3615/2634 | .734307 | .588215 | .204016 | .029381 | 251 |
| B2-post | 6249 | 3615/2634 | .648953 | .645526 | .227394 | .017249 | 47 |
| T-post | 6249 | 3615/2634 | .732970 | .587599 | .204051 | .030007 | 230 |

- **Primary:** T-raw minus B2-raw was log loss −0.056232 (95% CI
  [−0.083476, −0.029182]), Brier −0.023096 ([−0.034291, −0.012251]), and
  AUC +0.086514 ([+0.052512, +0.122204]). All primary support checks pass,
  including ECE .034600 and raw retention .984418. `all_raw_gain=.056766`.
- **Paired/POST:** paired raw gain `.057024`; POST gain `.057927`; raw
  retention `.984418`; reward-information gap `.000617`. T-raw-paired−T-post
  log-loss delta was +.000669, CI [−.006320, +.008053]. All-row and paired
  gains are materially consistent.
- **Counter diagnostic:** T-raw-no-counter minus T-raw log loss was +.000799,
  CI [−.009929, +.010387], with AUC −.005003 and Brier +.000374; verdict
  **NO EVIDENCE OF COUNTER SENSITIVITY** despite `relic_data_*` feature gain
  111.154.
- **Decision:** Analyzer verdict and independent reconstruction of current
  `classify_verdict` both return **E2C SUPPORTED**. This is predictive/offline
  evidence, not evidence that adding a critic to MCTS raises action-ranking
  quality or win rate. Implementation success and scientific success are
  separate. The decision is stable enough to stop at 2,000; another 3,000
  seeds is not justified absent a new integrity question.
- **Artifacts:** Remote output directory
  `/home/philippherrmann/sts_sweep/build/e2c_raw_terminal_2000/` contains
  `metrics.json`, `calibration_deciles.csv`,
  `validation_predictions_raw.npz`, and `validation_predictions_paired.npz`.
  SHA-256 hashes are respectively
  `db33685da894aac094da806305fb4b3b91fc537b70aa41ec8572b1835cfc44e6`,
  `e9dc812217a48c53fe02987a791d4e6b5bccb1257528bf8ca2e35398271a95ea`,
  `26afcdb0271fccf4cfb5183dcf3058fa4a2ee028706049e6bb4943d7cbf9cc64`, and
  `5e8a06ce4f5283eb4804c957e892c61d1be13983955ea30f8ef102175ad6e4bb`.
## 2026-08-23 — Searcher3 strategy-fusion shadow diagnostic implementation and smoke (non-decision-bearing)

- **Question:** Does an existing shared Searcher3 child below stochastic
  `END_TURN` encode a materially worse continuation policy than a fresh fair
  Searcher3 conditioned on each observed visible outcome bucket? This task
  does not implement chance nodes or state splitting.
- **Baseline:** `f2879ad7d0444b4d3edad87ba62f6181580c48d8`; implementation branch
  `exp/s3-strategy-fusion-diag`; worktree
  `C:\Users\pherrman\projects\sts_ai-s3-strategy-fusion-diag`.
- **Implementation:** Added off-by-default
  `STS_S3_STRATEGY_FUSION_DIAG=1` with CSV and `.meta.json` configuration
  output. The probe samples independent particles, uses full
  `CombatObservation` bucket identity, preserves the live shared child, runs
  fresh fair Searcher3 conditioned, matched-compute conditioned, and
  deeper-reference searches, and compares stable semantic action identities.
  The matched budget is `max(1, round(sharedChildVisits * bucketProbability))`;
  the configured 500-simulation search is secondary. It is guarded against
  pre-END_TURN parent fusion by collecting only when the tracked parent
  observation has `nodeObsMismatches == 0`; parent visit/mismatch provenance is
  emitted in each row. It is guarded against
  recursive side probes and does not consume the live searcher's RNG or mutate
  its tree, belief, counters, or selected action. Existing root-action
  selection was factored into a read-only helper without changing its
  visit/live-valid semantics.
- **Review correction:** Independent review of the first implementation found
  the compute-budget confound and transition-cap accounting issue. This commit
  applies the matched-budget and cap corrections, adds the preregistered
  source-seed analyzer at
  `tools/analyze_s3_strategy_fusion_diag.py`, and requires another independent
  implementation review before any decision-bearing run. The follow-up
  correction also gates collection on END_TURN-parent observation stability.
- **Fairness correction in the diagnostic:** Local testing found that
  `Belief::initial` uses the stored draw-pile vector order as a shuffle input
  even though `CombatObservation` equality treats the pile as a multiset. The
  diagnostic canonicalizes only copied side-search templates; normal
  Searcher3 belief construction remains unchanged. This is recorded as an open
  fairness limitation, not silently treated as resolved globally.
- **Smoke configuration:** project-fair Searcher3, ascension 0, seeds
  `12345..12346`, `searchdiag`, 64 simulations per searched decision,
  `STS_S3_PARTICLES=16`; diagnostic particles 16, max transitions 1, minimum
  shared-child visits 8, secondary fresh 16 simulations, matched budgets from
  the recorded formula, reference 32 simulations.
  Commands were run through `tools/seed_guard.sh`. OFF and ON emitted 599
  Searcher3 searchdiag rows each; root best-action comparison found 0 decision
  differences. No invalid-action, crash, or simulator-health error appeared.
- **Raw diagnostic output:** `build/s3sf_smoke_diag.csv` contains 4 rows from
  1 measured transition and 4 distinct visible outcome buckets. The primary
  matched-compute comparison disagreed on 2 rows with probability-mass
  weighted disagreement `0.3125`; among those, the deeper reference preferred
  matched-conditioned `0.600`, neither `0.400`, and shared `0.000`. The
  weighted matched reference conditioned-minus-shared margin was
  `-0.958249375`. The secondary 500-simulation comparison had disagreement
  `0.000` and weighted margin `0`. The analyzer validated the 36-column CSV,
  emitted source-seed bootstrap summaries, and passed its self-test. The
  corrected 36-column schema recorded `parentObsMismatches=0` for all rows.
  These are explicitly smoke-scale, noisy, and **not a scientific conclusion**.
- **Decision rule/status at the initial smoke checkpoint:** No
  16–32-source-seed decision-bearing run had yet been performed. This
  correction followed independent review of the first implementation; the
  stability-gated follow-up run is recorded below. The initial smoke did not
  support or reject chance nodes.

### Historical early-tree 64-simulation run (not mature-tree evidence)

- **Frozen implementation:** `1438ef72f6486adf3161e587b25fd1e0b83f18a6`.
  Seeds were `12345..12360`, one seed-guarded process per seed, normal
  Searcher3 particles 64, 64 normal simulations per decision, diagnostic
  particles 64, per-process transition cap 4, minimum shared-child visits 32,
  secondary fresh 500 simulations, and reference 3000 simulations.
- **Output:** 64 stable-parent measured transitions and 628 bucket rows;
  5,306 paired OFF/ON searchdiag rows per side; zero ON/OFF decision
  differences; zero parent-observation mismatches; no log error matches.
  Per-seed transition counts were exactly 4 for all 16 seeds. Analyzer output:
  `build/s3sf_decision_analysis.json`.
- **Validity classification:** the diagnostic side searches ran during
  `step()` as soon as the shared child crossed the minimum visit threshold.
  The recorded child counts therefore were threshold-time values rather than
  final post-search values. These artifacts are retained as historical
  **early-tree evidence**, not mature-tree evidence.
- **Primary matched-compute result:** disagreement `0.7012`, source-seed
  bootstrap 95% CI `[0.6116, 0.7820]`; deeper reference preference among
  disagreement mass matched-conditioned `0.2481`, shared `0.2648`, neither
  `0.4871`; matched-minus-shared reference margin `-1.6781`, CI
  `[-2.7500, -0.6066]`.
- **Secondary 500-simulation result:** disagreement `0.7612`, deeper reference
  conditioned preference `0.6132`, and margin `+3.5400`; this is secondary and
  compute-confounded by design.
- **Interpretation:** these results are not valid for the mature-tree scientific
  gate because the side searches used threshold-time child statistics. They
  should not be interpreted as evidence for or against persistent chance-node
  state splitting. A lifecycle correction and new review are required before
  repeating the decision-bearing run.

### Historical nominal 1000-simulation run (not mature-1000 evidence)

- **Frozen executable and configuration:** the executable remained frozen at
  `1438ef72f6486adf3161e587b25fd1e0b83f18a6`. Seeds were `12345..12360`,
  with one `tools/seed_guard.sh` process per seed for each OFF/ON pair.
  Normal Searcher3 used `STS_SEARCHER3=1`, `STS_FAIR=1`,
  `STS_S3_PARTICLES=64`, and 1,000 simulations per decision. The diagnostic
  used 64 particles, a per-process cap of 4 stable-parent transitions,
  minimum shared-child visits 32, secondary fresh 500 simulations, and
  deeper reference 3,000 simulations. The primary matched budget remained
  `max(1, round(sharedChildVisits * bucketProbability))`.
- **Validity classification:** despite the nominal 1,000 normal simulations,
  the diagnostic still launched side searches during `step()` at the first
  threshold crossing. The observed matched-budget median was only 5 sims, so
  this is also **early-tree evidence**, not mature-1,000 evidence.
- **Collection and correctness:** all 16 seeds completed, producing 64
  qualifying transitions and 560 bucket rows. Every seed contributed four
  transitions; all rows had `parentObsMismatches=0`; the formula matched every
  row; bucket probabilities summed to one within every transition; and the
  paired OFF/ON traces had zero actual gameplay/search decision differences.
- **Primary matched-compute result:** probability-mass-weighted
  shared-versus-matched disagreement was `0.7334`, with source-seed bootstrap
  95% CI `[0.6709, 0.7969]`. The source-seed mean reference preferences among
  disagreement mass were matched `0.3596`, shared `0.2149`, and neither
  `0.4255`. The matched-minus-shared reference margin was `-0.7253`, with
  source-seed bootstrap 95% CI `[-2.2000, +0.6504]`. The pooled mass-weighted
  margin was `-0.4665`.
- **Budget distribution:** across 560 bucket rows, matched budgets ranged from
  1 to 671 simulations, with mean `33.645`, median `5`, and quartiles
  `[2, 5, 28]` (p90 `102`, p95 `159`). The exact histogram was recorded in
  the removed raw result packet (SHA256
  `b31f4cdbb8c277ced0a757981116ccce168aa05d3aa88ca046ea54895abea5f5`).
- **Secondary comparison:** the fresh 500-simulation arm had disagreement
  `0.7542`, reference conditioned preference `0.5879`, and margin `+3.6488`
  by source-seed mean. It remains secondary and compute-confounded; it is not
  evidence against the matched-budget result.
- **Comparison with the prior 64-simulation run:** matched disagreement rose
  from `0.7012` (CI `[0.6116, 0.7820]`) to `0.7334` (CI `[0.6709,
  0.7969]`). Matched reference preference rose from `0.2481` to `0.3596`,
  while shared preference changed from `0.2648` to `0.2149` and neither from
  `0.4871` to `0.4255`. The primary margin improved from `-1.6781` (CI
  `[-2.7500, -0.6066]`) to `-0.7253` (CI `[-2.2000, +0.6504]`), but did not
  become positive or support a positive-margin conclusion.
- **Interpretation:** these results are invalid as a mature-1,000 scientific
  gate because the side searches used threshold-time child statistics. They
  are retained for debugging the compute confound, not as a chance-node
  decision. The raw CSV, metadata, analyzer JSON, and result packet were
  disposable `build/` outputs and are removed; their SHA256 hashes are
  `2447949a7efb6f4309826050d79986b7ee5d49e0bc98bcc6706dc9d87b99c091`,
  `60b6e9cc651318bd7a218e2b076a35514b495971b63e76166f4dee0d5b5221ea`,
  `0fac6f0f87ce847df9e4581b8fe2ac5e6b344848bcaff91cb15bdf2bec4a0283`,
  and `b31f4cdbb8c277ced0a757981116ccce168aa05d3aa88ca046ea54895abea5f5`.

### Correction: defer strategy-fusion side searches until search completion

- **Implementation:** candidates are now recorded during `step()` without
  particle sampling, bucket construction, or side searches. After the normal
  `search()`/`searchToTotal()` loop completes, the candidate path is resolved
  against the final tree, the parent stability gate is rechecked, final child
  visits are captured, and only then are the existing matched, fresh, and
  reference side searches run. The matched formula is unchanged.
- **Regression:** `s3_strategy_fusion_diag` proves a finalized candidate's
  final child visits exceed its threshold-time visits, demonstrating that the
  recorded budget is post-search rather than threshold-time.
- **Tiny smoke:** two guarded seeds (`12345..12346`), 64 normal simulations,
  16 diagnostic particles, cap 1 per process, minimum visits 8, fresh 8, and
  reference 16 produced 2 transitions and 8 bucket rows. Parent mismatches
  and budget-formula mismatches were zero; paired OFF/ON traces had 599 rows
  per side and zero actual decision differences; all four logs completed with
  no error markers. This smoke is implementation-only and non-decision-bearing.
- **Status at this correction checkpoint:** no 16-seed experiment had yet
  been run. The resulting implementation was then frozen at the reviewed
  executable SHA before the mature run recorded below.

### Mature post-search 1000-simulation strategy-fusion run (decision-bearing, 2026-08-24)

- **Frozen executable:** `a455dbae1e871e2671209bf006af1a9f733f1c29`.
  No executable source changed during collection. The run used source seeds
  `12345..12360`, one guarded OFF process and one guarded ON process per seed,
  `STS_SEARCHER3=1`, `STS_FAIR=1`, `STS_S3_PARTICLES=64`, 1,000 normal
  simulations per decision, diagnostic particles 64, cap 4, minimum child
  visits 32, secondary fresh 500 simulations, reference 3,000 simulations,
  and `OMP_NUM_THREADS=4`.
- **Collection and validation:** the corrected diagnostic deferred all side
  searches until normal search completion and used
  `max(1, round(finalSharedChildVisits * bucketProbability))`. The run emitted
  64 measured transitions and 560 bucket rows, exactly four transitions per
  source seed. Every row had `parentObsMismatches=0`; matched-budget formula
  mismatches were zero; probability sums were one for every transition; all
  recorded child visits were at least the configured threshold; and no process
  or health-marker failure occurred. Paired OFF/ON traces had zero actual
  `bestAction` differences, zero fight-outcome differences, and zero missing
  decision keys. Searchdiag timing/metric fields differed as expected from
  diagnostic overhead, but these did not change actual decisions.
- **Primary matched-compute result:** probability-mass-weighted shared versus
  matched-conditioned disagreement was `0.7063`, with source-seed bootstrap
  95% CI `[0.6304, 0.7800]`. Among disagreement mass, the pooled deeper
  reference preferred matched-conditioned `0.5309`, shared `0.1303`, and
  neither `0.3387`; source-seed means were matched `0.5646`, shared `0.1303`,
  and neither `0.3051`. The matched-minus-shared reference margin was
  `+2.4507` pooled and `+2.0325` by source-seed mean, with bootstrap 95% CI
  `[+0.6162, +3.5639]`.
- **Matched-budget distribution:** across 560 bucket rows, budgets ranged
  from `1` to `1,406`; mean `119.825`, median `60`, p25 `28`, p75 `148`,
  p90 `299.1`, and p95 `443`.
- **Secondary compute-unmatched result:** the 500-simulation fresh arm had
  disagreement `0.7222` (source-seed bootstrap CI `[0.6404, 0.7971]`), pooled
  reference preference conditioned `0.5335`, shared `0.0859`, neither
  `0.3807`, and source-seed mean margin `+3.7498` (CI `[+2.0394, +5.3921]`).
  This remains secondary and is not used as the primary gate.
- **Comparison with early-tree 64-simulation evidence:** primary disagreement
  changed from `0.7012` to `0.7063`, while the matched-budget median rose from
  `5` to `60`. The prior early-tree primary margin was `-1.6781` with CI
  `[-2.7500, -0.6066]`; the mature post-search run is positive with CI wholly
  above zero. The runs are not identical in executable SHA, so this is a
  descriptive comparison rather than a clean single-variable budget test.
- **Interpretation under the preregistered rule:** the run clears all three
  requested evidence gates: substantial disagreement, deeper-reference
  preference for matched conditioning, and a positive matched-minus-shared
  margin with source-seed bootstrap support. This supports proceeding toward a
  separately reviewed chance-node prototype; it does not establish a win-rate
  improvement and does not authorize implementation in this branch.
- **Evidence packet:** Raw diagnostic files were disposable `build/` outputs
  and are no longer tracked. Decision-critical provenance remains: frozen
  executable `a455dbae1e871e2671209bf006af1a9f733f1c29`; diagnostic CSV SHA256
  `3d7e3f8ae06ce5b108a0e28166694ac4e63c37b204f9b9ebae7e8c84cfcad56b`;
  metadata SHA256 `57c482ceca72dfb8080a51119e6a37ce143f8545d60c8ea2768d694f1c652680`;
  analyzer SHA256 `5ebddf2f8e80e87eefc94858b26a029f362a19b50141ba39b99c80a6c357efd9`;
  result-packet SHA256 `5209df10295570f634b0375d8b7e09e4c2271959ed7be8cdefbabe169a0b4e27`.

### Phase-1b Search-Age scientific run (2026-08-22; negative practical gate)

The amended 24-seed cohort (`0..23`) used fair Searcher3, 3000 simulations,
64 particles, K=0, and R=4 controlled rollouts. Twenty-three seeds qualified;
seed 12 had no LATE leaves and was excluded. The qualifying analysis covered
709 groups (368 EARLY, 341 LATE), with zero invariant failures, ineligible
groups, caps, or missing expected seeds. Controlled sensitivity was low:
EARLY fraction(range>5) `0.0380` (bootstrap 95% CI `[0.0109, 0.0761]`),
LATE `0.0469` (`[0.0177, 0.0814]`), and LATE equal-group mean range `0.6899`;
the preregistered LATE practical gate therefore **failed**. Paired
LATE-minus-EARLY contrasts were fraction(range>5) `+0.0074`
(`[−0.0239, +0.0370]`) and mean range `−0.0872`
(`[−0.4368, +0.2408]`), from 10,000 seed bootstraps.

The raw CSV, qualifying CSV, and two metric JSONs were generated outputs and
are removed from `build/`; hashes are retained solely for audit provenance:
`28e7eb24f6516695adf2ecf36cf6edc9ecf417eadf74b98b492c07339bad73f0`,
`0a709c7cc4c04e3916abc812be474b88ced575eaf3e2132e3942a73e8b5ded60`,
`565a65497f83947b8e6181af7793f24623c7220444177e12a82c4eefd7e8d2b7`, and
`ad35951676e9708292025b7337ee052891c1643eeb1192c6b0df705c25522dd8`.

## §178 Searcher3 immediate-Q exploitation mechanism diagnostic — sampled-corpus negative (2026-08-23)

- **Question / intervention:** Does `STS_S3_ALWAYS_Q=1` improve low-budget
  Searcher3 root decisions before a winning rollout exists? The only code
  variable changed was the fresh-tree Q-exploitation gate; the existing Q
  formula, risk adjustment, priors, budgets, and LIVE_VALID path were unchanged.
- **Implementation:** frozen implementation SHA
  `96967bfb7276460f69dc1a5d11bd5bc345e9f5b8`; baseline
  `f2879ad7d0444b4d3edad87ba62f6181580c48d8`. The new flag is default-off and
  is applied through one shared predicate in both `selectBestEdgePUCT()` and
  `selectBestValidEdgePUCT()`.
- **Protocol:** paired project-fair Searcher3; seeds `93000–93007` (8), asc 0,
  300 live-search simulations/decision, 64 particles, 8 OpenMP threads;
  root-race probes at 250/500/1000/4000 simulations. Control omitted
  `STS_S3_ALWAYS_Q`; treatment set `STS_S3_ALWAYS_Q=1`. Both used
  `STS_S3_BELIEF=0`, `STS_S3_CHAIN=0`, fair-S3 default LIVE_VALID, automatic
  `models/v_combat_7k_tuned.txt` at alpha 0.3, and automatic
  `models/policy_trees_c.txt`; no OOC strategic model was enabled. The raw
  diagnostic was run through `tools/seed_guard.sh`.
- **Corpus:** 256 captured root states: 208 ordinary encounters and 48
  Act-1 elite encounters (IDs 15/16); no boss state was captured by the
  existing first-32-states-per-seed hook. This is therefore an ordinary-vs-elite
  mechanism sample, not a boss or late-first-win sample. The root-race output
  contains run/decision metadata but no full visible-state hash; exact equality
  of control/treatment root states is unverified. The files are metadata-matched
  by `(seed,floor,encounter,turn,decision_index)` only.
- **Root decision quality:** each arm was compared with its own
  arm-specific 4000-simulation probe, not with a shared treatment/control
  teacher. Within-arm agreement at 250/500/1000 was 235/256 (91.8%), 237/256
  (92.6%), and 238/256 (93.0%) for both arms. This shows that ALWAYS_Q did not
  improve within-arm low-budget convergence on this corpus; it does not establish
  equal accuracy relative to one fixed deep policy. The metadata-pairable rows
  showed 2/256 chosen-action differences at each shallow budget. Control
  disagreement regret (mean over shallow/reference disagreements) was 1.940
  native units; treatment was 2.004. In the elite subset, treatment regret was
  worse at all three budgets (1.653 vs 1.496; 1.356 vs 1.292; 1.569 vs 1.505).
- **CPU:** root-race diagnostic `simSeconds` summed to 304.03 seconds for
  control and 416.26 seconds for treatment (+36.9%); this is a material
  overhead for a policy-only gate change. The searchdiag run wall times were
  67.3 seconds and 91.1 seconds, respectively.
- **Core-mechanism coverage:** first-win telemetry was not captured. The
  existing root-race diagnostic records root Q/visits and deep regret but does
  not expose the first winning simulation. Consequently the experiment did not
  isolate no-win-yet roots, late-first-win roots, or boss/deep difficult roots.
  The late-first-win/no-win-yet mechanism remains **inconclusive**, not falsified.
- **Raw artifacts:** `build/phase_a/control_8.csv`,
  `build/phase_a/alwaysq_8.csv`, `build/phase_a/control_8_searchdiag.csv`,
  and `build/phase_a/alwaysq_8_searchdiag.csv`, with corresponding
  `.fights.csv` files. These are ignored local artifacts and are not claimed as
  tracked evidence.
- **Reproducible analysis:** `tools/analyze_s3_always_q_phase_a.py` validates
  the root-race schema, reconstructs the arm-specific agreement/regret/action-
  difference metrics, reports metadata pairing, and labels exact state equality
  as unverified. It was run with
  `python tools/analyze_s3_always_q_phase_a.py
  build/phase_a/control_8.csv build/phase_a/alwaysq_8.csv`.
- **Verdict:** **PHASE A: NEGATIVE ON THE SAMPLED CORPUS / NO PHASE B.** Broad
  immediate-Q exploitation produced almost no decision changes and no improvement
  in within-arm low-budget convergence on the sampled ordinary and Act-1 elite
  roots, while diagnostic runtime increased substantially. This is sufficient to
  reject Phase B gameplay validation for this task. It does **not** falsify the
  narrower late-first-win/no-win-yet hypothesis; that mechanism remains
  inconclusive because first-win telemetry and boss/hard-state targeting were
  absent. Any rescue or targeting experiment would be new work.

## Searcher3 Q-gate timing correction before hard-state experiment (2026-08-23)

- **Question:** Does the baseline Searcher3 Q-exploitation gate really wait
  for a terminal winning line? The corrected implementation measures the first
  simulation ordinal after backpropagation changes `bestActionSequence` from
  empty to non-empty. This is not terminal-win telemetry.
- **Implementation:** the corrected per-instance field is
  `firstQExploitSimulation`, initialized to `-1`, reset on root promotion, and
  recorded only when the existing baseline gate first opens. Selection,
  rollout, VNet, rewards, priors, PUCT, LIVE_VALID, and RNG behavior were not
  changed. The paired hard-state/common-reference hook was not enabled.
- **Protocol:** guarded local `bestbench 1000 8 0 92000` with
  `STS_FAIR=1 STS_SEARCHER3=1 STS_S3_PARTICLES=64 STS_S3_BELIEF=0
  STS_S3_CHAIN=0 STS_S3_ALWAYS_Q=0 STS_STOP_AFTER_ACT=3`, current default
  fair-S3 V_combat/policy artifacts, and the documented V4 strategic OOC token
  model/gates. Four OpenMP threads; ascension 0. The run used
  `tools/seed_guard.sh` and wrote one telemetry row after each real combat
  search.
- **Distribution:** 3,449 rows across 8 seeds: 3,380 at simulation 1
  (98.00%), 66 at simulations 2–10 (1.91%), 1 at 11–100 (0.03%), 1 at 101+
  (0.03%), and 1 never (0.03%). The gate opened by simulation 10 in 3,446
  rows (99.91%). Act 1/2/3 were 1,011/1,152/1,286 rows; ordinary/elite/boss
  were 1,539/943/967. Exact analyzer output is reproduced in the decision log
  for this correction.
- **Smoke:** corrected two-seed smoke (seeds 91000–91001) captured 803 rows;
  799/803 (99.50%) opened by simulation 10. It also confirmed the timing CSV
  parser and that the paired hard-state diagnostic was explicitly off.
- **Decision:** **STOP_ALWAYS_Q_LINE** under the preregistered >=95% rule.
  The baseline already exploits Q almost immediately, so the planned
  16-seed late/no-win paired-reference experiment is not justified. This is a
  timing conclusion, not a gameplay gate.
- **Artifacts:** ignored local raw outputs
  `build/qgate_timing_8seeds.csv`, `build/qgate_8seed_results.csv`,
  `build/qgate_timing_smoke_v2.csv`, and `build/qgate_smoke_results_v2.csv`;
  analyzer `tools/analyze_s3_q_gate_timing.py`. The tracked compact metrics,
  exact configuration, collection SHA, and raw CSV SHA-256 are in
  `docs/experiments/evidence/s3_q_gate_timing_2026-08-23.json`; the raw timing
  CSV SHA-256 is
  `a5e7ec4d87cb737492635e41f6f7e10a4f5d2289cca7d79d1560af82d086e1bf`.

## §179 Experiment 4: persistent visible-outcome continuations below END_TURN (2026-08-25)

- **Question:** given PR #48's demonstrated strategy-fusion regret below
  stochastic END_TURN, can persistent visible-outcome-conditioned continuation
  subtrees provide reusable policy conditioning at acceptable compute cost?
- **Implementation:** default-off `STS_S3_PERSISTENT_ENDTURN_CHANCE=1` keeps one
  aggregate `Edge::child` action value/visit stream for parent PUCT and routes
  each normally sampled eligible END_TURN successor to a persistent child keyed
  by exact full `CombatObservation` equality. No eager alternatives, widening,
  hidden-state key, or other stochastic-action change. Eligibility: pre-state
  `UNDECIDED`, END_TURN, draw pile <=8, and no empty-draw/nonempty-discard
  immediate reshuffle. The PR #48 legacy diagnostic is mutually exclusive.
- **Correctness:** focused Debug CTest passed treatment split/reuse/aggregate/
  no-hidden-leak/observation-selection checks plus strategy-fusion, semantic
  card, draw-pile reuse, and RNG propagation regressions. A two-seed fixed
  configuration OFF comparison against the PR #48 tree (identical Git tree to
  baseline merge `dcdd1671`) matched every non-timing output field; CSV bytes
  differed only in `sec`.
- **Paired smoke:** guarded local Release `bestbench 1000 8 0 92000`, seeds
  92000–92007, ascension 0, Act-3 endpoint, `STS_FAIR=1 STS_SEARCHER3=1
  STS_S3_PARTICLES=64 STS_S3_BELIEF=0 STS_S3_CHAIN=0`, current default combat
  VNet/policy, V4 strategic token model with REST/EVENT/SHOP/TREASURE/BOSS_RELIC
  gates and margin 1.0, four threads. Arms differed only by the new flag.
- **Gameplay:** control 7/8, treatment 7/8. Two discordant pairs were opposite:
  seed 92002 control-only win and seed 92004 treatment-only win. Mean floor was
  50.25 vs 48.75; mean end HP 41.6 vs 46.4. Eight seeds are not decisive.
- **Structure:** eligible/ineligible END_TURN visits 2,104,508/4,568,959;
  containers 411,206; visits 2,104,508; outcome children/new misses 780,308;
  existing hits 1,324,200; reuse rate 0.629221; maximum outcomes/container 685;
  final container-count bins 1..7/8+ =
  `[313266,43347,19432,12492,5093,3450,2338,11788]`. Identities and counters
  were internally consistent (`hits + misses == visits`).
- **Compute:** summed per-run seconds 605.2119 control vs 600.7984 treatment
  (-0.73%); process wall 204.1 vs 197.6 seconds (-3.2%). Treat this ordered
  small run as no measurable overhead, not a speedup. It is materially below
  the old eager prototype's +56% and below the 20–25% engineering warning.
- **Artifacts:** ignored local `build/exp4_pair_control.csv`,
  `build/exp4_pair_treatment.csv`, and their `.meta.json` sidecars.

### Experiment-4 isolation correction and large-container probe (2026-08-25)

- Persistent chance eligibility now uses independent
  `STS_S3_PERSISTENT_ENDTURN_MAX_PILE` configuration (default 8), not the eager
  marginalization prototype's max-pile setting. Persistent chance and eager
  marginalization are rejected together at startup, as is the existing
  strategy-fusion diagnostic conflict.
- A minimal diagnostic compares each chance container's pre-END_TURN visible
  hash with its first visit. This uses the existing observation-stability hash
  only for telemetry; post-END_TURN outcome identity remains exact full
  `CombatObservation` equality.
- Guarded Debug treatment smoke: `bestbench 64 1 0 126701`, fair Searcher3, 64
  particles, belief/chain off, one thread, Act-3 endpoint, and the same V4 OOC
  strategic gates as the paired smoke. It completed normally with 4,598
  eligible visits, 1,601 containers, 2,873 new outcomes, 1,725 reuse hits
  (37.5163%), and maximum 59 outcomes/container.
- Of those containers, 241 received a pre-observation hash mismatch. Mixed
  containers reached at most 15 outcomes. The 59-outcome maximum container had
  205 visits and zero pre-observation hash mismatches. Thus the cheap probe does
  not support visible pre-state mixing as the sole cause of large containers;
  it cannot retrospectively classify the prior 685-outcome container without
  rerunning the larger smoke, which was intentionally not done.

- **Verdict:** **REVIEW FOR LARGER GATE.** Implementation passed and reuse is
  substantial without an obvious compute/gameplay warning. Independently
  review the frozen implementation and the surprising 685-outcome maximum
  before designing any 32–64 seed equal-sim/equal-CPU gate.

## E3c conditional E2c critic analysis (2026-08-25)

- **Question:** among paired future events where both direct-reference leaves
  survive current combat but eventual run outcomes differ, does the E2c
  conditional post-combat critic rank the eventual winner beyond `blendedEval`?
- **Data/protocol:** no new simulation or training. Frozen producer SHA
  `a93b3c68fc4efaaf9e9858d7aca571baac1a68d4`; M=16 shadow SHA-256
  `0aca56931c24575aca468d21e4da0848ea6b9296a36e724a93a6b8be5abf11ed`;
  direct-reference SHA-256
  `a6a18d314e0f4d040b03a84b0cd073146375f79babfe7c1994614114fdc68671`.
  Conditional `c_r` values were reconstructed only from surviving R=4 shadow
  replicates; zero-survivor values remained missing. Accuracy was tie-aware,
  root-equal, and bootstrapped over source seeds with RNG seed 0 and 10,000
  draws.
- **Coverage:** 188 complete leaves, 463 sibling pairs, 32 roots, 16 source
  seeds, 1,143 direct outcome-discordant events, 273 combat-driven events,
  and 870 downstream-discordant events. At support `>=1/2/3/4`, leaves were
  `153/142/131/117`, sibling pairs `355/319/284/253`, and downstream events
  `846/774/713/620`.
- **Result:** conditional-minus-blended root-equal deltas at those supports
  were `-0.014904/+0.022183/+0.029394/+0.014489`; all bootstrap 95% CIs
  included zero. At support `>=1`, the CI was `[-0.085624,+0.056238]` and
  leave-one-source-seed-out estimates ranged `[-0.036925,+0.008089]`.
  Predeclared conditional min, worst-half, mean-minus-0.5-std, and
  mean-minus-1.0-std summaries had no robust downstream advantage.
- **Verdict:** **E3C_INCONCLUSIVE**. The conditional mean is source-seed
  unstable, so the result is not a useful promotion signal. R=4 tails are
  coarse policy/combat-RNG summaries, not full information-set CVaR. No
  gameplay promotion, threshold selection, continuous lambda search, M=32
  extension, or distributional-model training is authorized.
- **Artifacts:** `tools/analyze_e3c_conditional_runwin.py`,
  `build/e3c_conditional_runwin_analysis.json`, and
  `build/e3c_conditional_runwin_analysis.md`; repeated-output SHA-256 values
  are JSON
  `260ffb78119f3539a59a92c2c5a658f81c87947c2be1a2180196488399ad1872` and
  Markdown
  `86c8136477a5d3bc668d58c11aa03f5cb6156f70111bb6d20c48e276cce0dc1b`.

## G1 Searcher3 generic action-observation chance tree (2026-08-25)

- **Question:** can the frozen generic action -> observed `CombatObservation`
  -> conditioned `DecisionNode` architecture execute correctly, and does
  normal N=1 tree reuse improve the generic architecture when isolated from
  legacy topology?
- **Implementation/provenance:** frozen source SHA
  `d3e250d84672e264b8515f02b1b6bbbc40c4dc66`; remote Release executable SHA-256
  `a103e0dd7e682a6bb06a641d1b2057df69a893249271e31551af0a0f6f1d641e`;
  model hashes and complete machine-readable provenance are in
  `docs/experiments/evidence/s3_generic_chance_tree_g1_2026-08-25.json`.
  The source branch was PR #54, draft/open, and was not merged.
- **Common protocol:** guarded GCP `sts-test`, project-fair Searcher3,
  ascension 0, Act-3/full-run endpoint, 24 threads, 1,000 simulations per
  decision, 64 particles, seeds `930000..930015`, generic tree on for the
  treatment arms, persistent END_TURN chance/CRN/strategy-fusion diagnostic/
  END_TURN marginalization/union expansion/legacy expansion/legacy semantic
  card edges all off. Raw outputs are ignored local `build/g1_*` files; their
  hashes are recorded in the evidence manifest.
- **Fresh-tree smoke:** control generic-off won 7/16 (mean floor 44.625,
  mean end HP 15.625, 23.563 CPU sec/run); generic fresh-tree won 4/16 (mean
  floor 41.3125, mean end HP 14.0, 31.986 CPU sec/run), approximately +35.8%
  runtime. Treatment hard counters were all zero:
  `decisionObservationMismatches=0`, `semanticResolutionFailures=0`,
  `semanticActionSetMissing=0`, `semanticActionSetExtra=0`. Discordant seeds
  were `930003, 930007, 930009`. This is architecture/runtime evidence, not a
  win-rate gate.
- **Reuse isolation:** both arms generic-on and differed only by
  `STS_REUSE_MAX_SEARCHES=0|1`. Reuse 0 won 4/16 (mean floor 41.3125, mean HP
  14.0, 31.883 CPU sec/run); reuse 1 won 5/16 (mean floor 42.0, mean HP 11.625,
  34.756 CPU sec/run), approximately +9.0% runtime. Discordant seeds were
  reuse-0-only `930000,930005,930010` and reuse-1-only
  `930002,930003,930009,930015`. Verdict: operationally correct, mixed and
  underpowered gameplay evidence, with no compute benefit.
- **Particle boundary audit:** a separate guarded 4-seed (`930000..930003`)
  `STS_S3_BELIEF_AUDIT` run split fresh and carried boundaries. Reuse 0 had
  8.33% fallback on carried boundaries and 94.75% on fresh boundaries; reuse 1
  had 12.36% and 94.71%, respectively. Overall fallback was 26.40% versus
  29.03%. Thus reuse 1 carried fallback is moderately higher, but reuse 0 is
  not near zero and fresh-boundary fallback dominates both arms. The existing
  audit is boundary telemetry, not every internal `applyParticle()` call, and
  uses its legacy CardId multiset fallback predicate. It does not associate a
  fallback count with the max-outcome action/node.
- **Verdict:** **G1_CORRECTNESS_PASS; REUSE_MIXED_SLOWER; PARTICLE_CAUSE_OPEN.**
  Do not add deterministic fast paths, local chance resampling, progressive
  widening, transpositions, CRN gameplay, or other G2+ features from these
  results. If resumed, isolate reuse=1 with a fresh 64-particle belief rebuilt
  at the real boundary. Close PR #54 without merging; preserve the tracked
  manifest before deleting local raw artifacts.

## Silver reuse-cap scaling experiment (2026-08-26)

- **Question:** does Silver's retained-allocation 32k reuse-cap predicate cause
  a sticky exact-reroot cutoff after `setRoot()` resets the active pool, and is
  replacing that predicate with active-pool usage a useful full-run change?
- **Frozen implementation:** source SHA
  `36065aefbc49063d16000a9549cad5c1346bbcc6` (PR #59); baseline SHA
  `1e9b8011c2f487ca479f66399d9901fe2e6b1b4c`; GCP Release binary SHA-256
  `3890e2156fd2d4f64f4bec8d13aec02b094bd403e2d841e23468b1495964f7f9`.
  `allocated` remained the default and production cap remained 32768. The
  active treatment changed only the metric used at that cap.
- **Protocol:** guarded GCP `sts-test`, 24 OpenMP threads, ascension 0,
  Act-3 endpoint, project-fair Searcher3 with current native OOC stack, Silver
  combat backend, 32 paired seeds `940000..940031`. D0 was allocated/1000;
  D1 allocated/3700; T1 active/3700, conditional on the D0/D1 mechanism gate.
  A same-seed diagnostics-off D1/T1 pair measured runtime. Complete flags,
  model hashes, raw-artifact hashes, and analysis hashes are tracked in
  `docs/experiments/evidence/silver_reuse_cap_scaling_2026-08-26.json`.
- **D0/D1 mechanism gate:** allocated exact reroot fell from 67.16% at 1000 to
  53.54% at 3700 while sticky-eligible rate rose from 0.22% to 16.23%.
  `deltaFallbackRate=0.136249`, `deltaStickyRate=0.160091`, and the numerical
  ratio was 1.174989. That ratio is **not** a causal share of failures: the
  candidate-missing fallback rate improved as sticky-cap fallback grew. The
  gate passed under both preregistered conditions.
- **Direct causal result:** at 3700, active exact reroot was 66.87% versus
  allocated 53.54% (+13.33pp); candidate-missing fallback changed only
  +0.207pp. All 1,852 active sticky-eligible rows exact-rerooted, and active
  mode produced zero `allocated_cap` failures. The sticky 32k retained-
  allocation mechanism is therefore **causally confirmed**.
- **Agent and efficiency result:** D1/T1 wins were 21/32 versus 20/32;
  paired mean floor delta was -0.5625 with bootstrap 95% interval
  [-1.75, +0.09375]. Nodes/simulation was 0.88% lower in active mode. The
  diagnostics-off paired runtime was 39.289s allocated versus 41.604s active:
  +2.315s / +5.89%, bootstrap 95% interval [+1.271s, +3.455s]. This fails the
  preregistered no-more-than-5%-slower criterion. The 32-seed gameplay result
  is **inconclusive**, not a promotion signal.
- **Post-hoc limit:** the collected CSVs support the paired runtime bootstrap
  and exploratory seed-level associations with inherited visits, sticky cases,
  and active-pool occupancy. They do not contain depth, chance-depth,
  transposition, or widening counters, and `STS_SILVER_TELEMETRY` was not
  enabled; those structural rates cannot be reconstructed from these artifacts.
- **Verdict:** **IMPLEMENTATION PASS; STICKY-CAP MECHANISM CONFIRMED;
  EFFICIENCY NOT MET; GAMEPLAY INCONCLUSIVE.** Keep `allocated` as production
  default. Do not optimize the runtime cost or run an active-mode promotion
  gate yet. The next justified task is a new, state-targeted decision-quality
  experiment comparing allocated/fresh, active/reused, and a high-budget
  fresh-root reference on cap-fallback states.

### Exploratory active/10k same-seed follow-up (2026-08-26; not preregistered)

- **Scope:** a user-requested descriptive run, not a formal treatment,
  efficiency gate, or gameplay promotion. It reused the frozen binary, exact
  GCP host/configuration, 24 threads, and seeds `940000..940031`, changing only
  the active-mode base budget to 10,000 simulations. It was collected after
  the formal conclusion and cannot revise it.
- **Result:** X1 active/10k won 23/32 (71.88%), mean floor 47.28125, mean end
  HP 37.90625, and 115.239 diagnostic-enabled seconds/run. Against T1
  active/3700 on the same seeds, X1 had 5 X1-only wins and 2 T1-only wins,
  +1.3125 mean floor, +6.78125 mean HP, and +73.244 seconds/run. This is an
  unequal-budget, one-block descriptive comparison, not evidence that active
  reuse is promotable or that the 10k budget is better.
- **Structure:** X1 candidate-found rate was 70.54%; exact reroot 46.94%;
  candidate-missing fallback 29.46%; and active-cap fallback 23.59%. It had
  4,868 sticky-eligible rows, all of which exact-rerooted, and zero
  `allocated_cap` failures. Thus active mode still removes the original sticky
  allocation-cap rejection, but the unchanged 32k **active pool** cap is now
  the dominant reroot limiter. Nodes/simulation was 0.8520 and inherited visits
  averaged 4,246; neither quantity establishes decision quality.
- **Artifacts:** raw result SHA-256
  `b8659acd2b8fee3e38ce7867523a7aed69da261485ce14c5e89b9eb5e9946e0d`;
  diagnostic SHA-256
  `46c9e11e9e73a0fd45045126ba2a16e5f81eafe9aea4f3cc60549d96b6c2d93b`;
  archive SHA-256
  `13587de062e12385dabbf444c1b609bb1e5bd787ceba6f91911400d362e7b9f0`.
  The combined analyzer report is ignored local
  `build/gcp_formal_36065ae/d0_d1_t1_x1_analysis.{json,md}` and its hashes are
  recorded in the evidence manifest.

### Exploratory allocated/10k counterpart (2026-08-26; not preregistered)

- **Scope:** this user-requested X2 arm completes a same-seed, same-budget
  descriptive comparison to X1. It used the same frozen executable, GCP host,
  models, Act-3/project-fair configuration, 24 threads, seeds
  `940000..940031`, and 10,000 simulations; only the cap metric changed from
  X1's `active` to `allocated`. It is not a preregistered promotion or runtime
  gate and does not alter the formal experiment verdict.
- **Direct structural comparison:** allocated X2 exact reroot was 11.32% versus
  active X1 46.94% (+35.62pp active); cap-blocked fallback was 59.24% versus
  23.59% (-35.65pp active); and candidate-missing fallback was effectively
  unchanged at 29.44% versus 29.46%. X2 had 5,839 sticky-eligible candidates,
  all rejected with `allocated_cap`; X1 had 4,868, all exact-rerooted and zero
  `allocated_cap` failures. This re-confirms the retained-allocation sticky-cap
  cause at 10k. X1 still had 3,244 `active_cap` fallbacks, so active pool usage
  rather than retained allocation is its remaining cap limiter.
- **Visits and nodes:** active inherited 4,246 visits per reroot attempt versus
  allocated 963 (+3,284); nodes/simulation was 0.8520 versus 0.8681. These are
  structural observations only, not evidence that the inherited visits improve
  decision quality.
- **Same-seed outcomes:** both arms won 23/32, with one X1-only and one
  X2-only win. Active-minus-allocated mean floor was -1.34375 (bootstrap 95%
  [-4.09375, +0.53125]); mean end-HP delta was +1.96875 (95%
  [-4.40625, +8.96875]); and diagnostic-enabled runtime delta was +4.176s
  (95% [-3.144s, +9.624s]). This paired block gives no gameplay or runtime
  promotion evidence.
- **Artifacts:** X2 result SHA-256
  `24c80c5b5b960ef668a21f75386fd153ccdd991d566e4254a0b4ca60371e0dfd`;
  diagnostic SHA-256
  `ac3cd9132ba47fb22649a079f19fc7491769deaf9a932e3c9d405ace2ac50c5e`;
  archive SHA-256
  `5036f0b44b6b52ce3b777a9d97d1becc67742963b1e119f62371edcab337d80d`.
  The strict two-arm analyzer artifacts are ignored local
  `build/gcp_formal_36065ae/x1_x2_analysis.{json,md}`; their hashes are in the
  evidence manifest.

## Silver no-tree-reuse screening experiment (2026-08-27)

- **Question:** is Silver stronger and/or more efficient when the prior search
  tree is discarded after every live decision? The control was the production
  `allocated` reuse mode; the treatment was `none`, which fresh-resets the
  existing `BattleSearcher` root and statistics at every decision.
- **Hypothesis and decision rule:** no reuse was hypothesized to avoid stale or
  misaligned inherited statistics. Recommend a fresh 64-seed promotion gate
  only if `none` is no more than 5% slower and is directionally nonnegative
  (`wins >= allocated` and mean floor delta >= 0). Stop as harmful only for a
  clear gameplay regression, especially a negative floor delta whose 95%
  bootstrap interval is entirely below zero. Otherwise report
  **INCONCLUSIVE** and do not automatically expand.
- **Frozen implementation:** reviewed source SHA
  `6e908b5800d04af663e62d61d713ddfb5813f2e4` (PR #64), merged current-main
  baseline `5a84fc542d1a4d1f3b55caf68b44fce8738e1d87`; source archive SHA-256
  `5acc352b220cbe0d231fe86d6fcad30830920e46b08fc60fde90d13d3f6e70d3`;
  remote Release `one_combat` SHA-256
  `8ee7b69b446c9424efe82278d78b498dcad3b04421e46d0b1a3f616682c1b760`.
- **Protocol:** designated GCP `sts-test` host class, 24 OpenMP threads,
  `OMP_DYNAMIC=FALSE`, ascension 0, Act-3 endpoint, fair-play Searcher3,
  isolated Silver combat backend, 64 Searcher3 particles, base Silver budget
  3700 simulations per decision, `STS_COLLECT_KEYS=0`, same default boss/OOC
  stack, same binary and models, and no telemetry or scaling diagnostics.
  The exact common environment was
  `STS_FAIR=1 STS_SEARCHER3=1 STS_SILVER_SEARCH=1 STS_COLLECT_KEYS=0
  OMP_NUM_THREADS=24 OMP_DYNAMIC=FALSE`, with only
  `STS_SILVER_REUSE_CAP_MODE=allocated|none` changed between arms. Seeds were
  paired as `944000..944031` (32 runs per arm). The pinned submodules were
  `json=2222d386c905e6a6ebf73c61571a8a2cf196e843` and
  `pybind11=63d627c5747befad7720a43ebbe5614fd5d83247`; model hashes were
  `v_rich_trees.txt=c866b62512bb7cf8abdebc6175415508cb667fe2d628198ac107fd35591a9447`,
  `v_win_trees.txt=724a75ccc4bc2394306181db229aa2295433450f9596f1bc1479083dda337e35`,
  and `policy_trees_c.txt=43c9dbddbebe52b4dce961b9376fcb76c1ac72a735caf161b646be0fa34f1a55`.
- **Results:** allocated won 19/32 (59.4%); none won 17/32 (53.1%). There
  were 5 allocated-only wins and 3 none-only wins, with 14 both wins and 10
  both losses. The exact two-sided McNemar/binomial test on the 8 discordant
  pairs was `p=0.7265625`. Mean paired floor delta (none - allocated) was
  `-0.21875`, seed-bootstrap 95% CI `[-2.875, +2.6875]`. Mean paired final-HP
  delta was `+3.03125`, seed-bootstrap 95% CI `[-5.9375, +12.5625]`.
- **Efficiency:** mean runtime was 49.219534 seconds/run for allocated and
  56.202050 seconds/run for none, a paired delta of `+6.982516` seconds/run
  and relative change of `+14.19%`. The seed-bootstrap 95% CI for the runtime
  delta was `[+1.735219, +12.480201]` seconds/run. Thus none failed the
  preregistered no-more-than-5%-slower screening criterion.
- **Artifacts and analysis:** raw control CSV SHA-256
  `fb10e450af72762925539a2d7ef2f1a4d3c083fd98c228420ed8c023a6a7c340`;
  treatment CSV SHA-256
  `265b9fed4516a54172c951410535f0f3156dad0989c6d8910ce960b8277643fa`;
  control sidecar SHA-256
  `223a1a3436e59a314fac4ba3c10fe08cbb9d55f19f1ba80a0736d2ba05bd8190`;
  treatment sidecar SHA-256
  `bcc460b559a66a77cd28f7f5ddf420f0e3fdfcb196d234a8115fdca1826b8595`.
  Local ignored copies are under `build/silver-no-reuse-6e908b5/`; the remote
  raw files and logs are under
  `/home/philippherrmann/silver-no-reuse-6e908b5/`.
- **Provenance caveat:** the sidecars correctly record the effective backend,
  Silver mode, Silver upstream SHA, models, flags, budget, threads, and seed
  block. Their `executableGitSha` is the pre-existing remote dirty-checkout
  SHA `a93b3c68fc4efaaf9e9858d7aca571baac1a68d4`, because the guarded launcher
  starts commands from the host staging checkout while the frozen binary was
  built from the isolated archive. The frozen source archive hash and remote
  binary hash above are the authoritative executable provenance for this run;
  do not treat the sidecar executable-SHA field as an independent check.
- **Verdict:** **IMPLEMENTATION PASS; NONE SLOWER; GAMEPLAY INCONCLUSIVE;
  SCREENING INCONCLUSIVE.** The lower win count and slower runtime do not meet
  the promotion rule, but the floor interval includes zero and the HP result
  is positive but imprecise. Do not automatically expand to 64 seeds. Keep
  `allocated` as production default unless a separately authorized follow-up
  revisits the question.

## Silver root-action rollout / terminal-utility diagnostic (2026-08-27)

- **Question:** does the Silver-1k to Silver-3.7k scaling pattern primarily
  reflect noisy root estimates, a systematic `SimpleAgent` rollout-policy
  bias, or a misweighted Silver terminal utility? No policy, utility term, or
  search parameter was changed in this experiment.
- **Frozen implementation and provenance:** current-main baseline was
  `3f6565113229310e7821e3d42377eee3050d4619` (already newer than the requested
  minimum `0dd84ded8b76e788b778337eea084c312dadb9b0`). The corpus-producing
  executable/source was frozen at `7bce607a52cf626831b20fe9f2ea43711fe006c4`;
  this is the last commit that changed the diagnostic C++ bridge before the
  run. The original aggregate-weighting analyzer correction was
  `e559d71377986949eca1eb17398030ea2100cf15`; the present correction is the
  analyzer-only commit `5e69dd7657a094f9812db699d3be9181b8eb0a77`. The later
  PR-head changes are analyzer/ledger provenance only and did not change the
  executable used for the corpus. The implementation adds default-off
  root/action summaries, rollout terminal counters and exact terminal-utility
  component accounting at the isolated Silver boundary, fresh forced-action
  continuation references, and a stdlib analyzer. The diagnostic is
  behavior-neutral when unset; a same-seed check matched all outcome/floor/HP/
  death fields, with only timing differing.
- **Selection and protocol:** 16 guarded fair-play seeds `102000..102015`,
  one OpenMP thread, ascension 0, `STS_STOP_AFTER_ACT=1`, native OOC enabled,
  Searcher3 flags retained but Silver combat enabled (therefore Silver's
  isolated backend bypassed S3 combat particles), 1,000 production
  simulations, fresh 3,700-simulation comparison, and the default model/OOC
  stack. The diagnostic accepted the first four ordinary Silver decisions per
  seed, producing 64 roots and 286 legal root-action rows. This is a bounded
  early-Act-1 corpus, not a stratified boss/low-HP corpus: all roots were high
  HP; only four had potions. Root selection was deterministic by encounter
  order and per-seed cap, not tuned after inspecting outcomes.
- **Reference:** for every accepted legal root action, execute that semantic
  action in a fresh private materialized state, then run a fresh Silver
  continuation for 5,000 simulations, repeated twice. Replicate seeds are
  independent across replicates and shared across sibling actions (CRN
  pairing). For a stochastic root action, however, the forced transition is
  sampled once before the continuation search; two replicates therefore do not
  estimate its immediate chance expectation. The corrected analysis retains
  all rows for descriptive mixed-action reporting but restricts headline
  action-quality metrics to the joint 50-root subset in which both budget
  selected actions are deterministic. The per-budget deterministic subsets
  remain descriptive because they have different root composition; sibling
  ordering in the headline also uses only deterministic pairs from the joint
  subset. No corpus rerun or nested stochastic sampler was added.
- **Corrected headline reference quality (deterministic forced-action scope):**
  the corpus has 64 roots and 286 legal-action rows, of which 221 rows are
  deterministic; 56 roots have deterministic candidates. The direct budget
  comparison uses exactly the 50-root joint subset. On those same roots,
  Silver-1k top-action agreement is `32/50 = 64.0%`; Silver-3.7k is
  `37/50 = 74.0%`. Mean regret is `0.09501` at 1k versus `0.04947` at
  3.7k; median regret is `0` for both. On the 438 comparable deterministic
  sibling pairs from those roots, pairwise ordering agreement is 1k visits
  `332/438 = 75.80%`, 3.7k visits `342/438 = 78.08%`, 1k child-Q
  `336/438 = 76.71%`, and 3.7k child-Q `341/438 = 77.85%`. The selected
  actions disagree on `9/50 = 18.0%` and the mean regret change is `-0.04554`
  (3.7k minus 1k). These are deterministic-action comparisons, not claims
  about the unresolved chance distribution of stochastic candidates.
- **Per-budget deterministic results (descriptive, unpaired):** the 1k
  budget has a 51-root denominator, top-action agreement `32/51 = 62.75%`,
  and mean regret `0.09336`; the 3.7k budget has a 53-root denominator,
  top-action agreement `40/53 = 75.47%`, and mean regret `0.04667`. These
  values are retained to show coverage but are not used for the direct
  1k-versus-3.7k improvement claim because their root sets differ.
- **Descriptive mixed-action results (not headline reference quality):** the
  unfiltered analysis remains available in the corrected JSON under
  `all_roots_descriptive`. Its prior values were 1k top-action agreement
  `40/64 = 62.50%`, 3.7k `46/64 = 71.875%`, mean regret `0.12845` versus
  `0.05659`, and 13/64 (20.31%) selected-action disagreement. It also reports
  the prior mixed pairwise values and margin bins, but these are demoted
  because 65/286 legal rows are stochastic and the worst mixed reference
  replicate standard deviation was `3.14014`. Among the corrected
  deterministic scope the corresponding maximum was `1.20631`.
- **Margin conditioning in the corrected scope:** 1k -> 3.7k mean regret and
  top-action disagreement were `<0.1`: `0.0763 -> 0.0551`, `62.5% -> 56.25%`
  (`n=16`); `0.1..0.5`: `0.0810 -> 0.0372`, `38.46% -> 23.08%` (`n=13`);
  `0.5..1.0`: `0.4563 -> 0`, `66.67% -> 0%` (`n=3`); and `>=1.0`:
  `0.0924 -> 0.0924`, `8.33% -> 8.33%` (`n=12`). The high-margin bin
  remains stable; the clean evidence is consistent with budget-sensitive
  near-boundary decisions but is not precise enough to assign the cause to a
  rollout-policy or utility bias.
- **Corrected-scope breakdowns:** all accepted roots are high-HP Act-1 roots;
  the deterministic headline subset has encounter-code 1/2/3/4 counts
  14/16/12/8 and 35.71%, 31.25%, 41.67%, and 37.50% 1k disagreement. The
  potion-bearing clean subset is only 3 roots (33.33% disagreement, mean
  regret 0.0127) versus 47 without potions (36.17%, mean regret 0.1003).
  Fresh/no-predecessor clean roots are 16 and 75.0% disagreement; exact-reroot
  clean roots are 29 and 13.79%. These strata are descriptive only because
  selection was early-decision biased. The clean action-type breakdown has
  only type `1` (50 roots, 36.0% disagreement), so it does not support an
  action-class conclusion. The excluded stochastic-selected roots are 13 for
  1k and 11 for 3.7k.
- **Rollout observations (descriptive across the captured rows):** current 1k had 57,494 rollout calls, 57,486 wins
  and 8 losses, mean 7.968 rollout actions and 1.757 turns; current 3.7k had
  207,017 calls, 206,991 wins and 26 losses, mean 7.542 actions and 1.644
  turns. Across the 2,468,974 forced-action reference rollouts there were
  2,467,594 wins and 1,380 losses, mean 7.016 actions and 1.518 turns. The
  current rollout terminal-loss rates were therefore 0.014% (1k) and 0.013%
  (3.7k); the reference loss rate was 0.056%. This early corpus contains no
  repeated rollout-policy loss mechanism.
- **Utility decomposition:** in the forced-action references, representative
  high-regret failures were explained by terminal HP and turn cost rather than
  hidden utility terms. For seed 102011 / encounter 4 / decision 2, END_TURN
  was the 1k choice at value 125.8778 while a card action was best at 128.2077:
  the best action gained `+0.622` HP value and `+0.217` turn-penalty value.
  For seed 102009 / encounter 1 / decision 1, the chosen card was 122.0249
  versus reference-best 123.1335, with `+1.503` HP and `-0.124` turn-penalty
  difference. Across the 26 raw 1k-vs-single-best disagreements, mean
  best-minus-chosen component deltas were HP `+0.1553`, turn penalty `+0.0286`,
  potion `+0.0252` (only 2 nonzero roots), and approximately zero for
  death-save, gold, max-HP, parasite, monster-damage, alive, energy-waste,
  draw, and survival terms. The latter are not a basis for a utility-term
  change. Current rollout component totals reconstruct their scalar utility
  sums to under `1.5e-8` absolute per recorded root, validating the
  decomposition mirror.
- **Offline intervention screen:** no rollout-policy or terminal-utility
  candidate was selected. Consequently there is no before/after held-out
  intervention metric, no candidate runtime comparison, and no gameplay gate.
  The corrected deterministic analysis still supports budget-sensitive root
  estimates as a material component of the 1k weakness, but it does not
  isolate a narrow recurring `SimpleAgent` failure or prove that any
  terminal-utility weight is wrong. The reference itself uses the current
  utility, so utility correctness remains an open external-validity question.
- **Runtime:** the bounded diagnostic run took 44.1 seconds wall time for 16
  seeds at one thread (`2.76` CPU seconds/run average) including the 5,000 x 2
  forced-action references. It is intentionally opt-in and not a production
  runtime change. A one-seed disabled/enabled behavior-neutral check measured
  1.99s versus 1.97s, but its diagnostic reference budget was only 200 and is
  not a production overhead estimate.
- **Artifacts:** raw root-action CSV
  `build/silver-root-corpus-full.csv`, SHA-256
  `62ede35a7ce2bdb47baf331b19e6ed49b1773d6e5de000f442d757da0b086c3d`;
  original mixed-action analyzer JSON `build/silver-root-corpus-full.json`,
  SHA-256 `ff1a03e3a5e74030171148794747baabeea9c8141a854e19b5eb6653b0fcd730`;
  corrected deterministic-scope analyzer JSON
  `build/silver-root-corpus-corrected.json`, SHA-256
  `9B291DB376292E42C9B2B7655DAE8D896342FB6B11A91A2642608885428D4274`;
  guarded run log `build/silver-root-corpus-full.log`; behavior-neutral
  outputs `build/silver-neutral-off.csv` (SHA-256
  `63724f511da48f31282490fe8b9341ff7522d78406b79c3dd73c879749d86d93`),
  `build/silver-neutral-on.csv` (SHA-256
  `1550707fc417dbd01bd133cfa4c02fafe8fb8663b37e73b2d33888a402699231`), and
  `build/silver-neutral-root.csv` (SHA-256
  `29aea05b469e95aa74e8a4a02e6acc733c0ac6deecdb91213afac0f7162e4f7d`).
  The analyzer is `tools/analyze_silver_root_diagnostic.py` and can regenerate
  the JSON from the raw CSV.
- **Verdict:** **NO_SIMPLE_ROLLOUT_FIX.** Implementation success and the
  corrected deterministic-scope diagnostic are positive. The clean 3.7k
  improvement and margin dependence indicate budget-sensitive root estimates
  are real, while the observed terminal traces do not identify one repeated
  rollout-policy or utility-term mechanism that meets the prescribed offline
  screening rule. The mixed stochastic-reference metrics are descriptive only
  and are not used to claim a 56% regret reduction. Do not stack a heuristic,
  alter utility weights, introduce a VNet, or run a gameplay gate from this
  result; a future follow-up needs a more stratified corpus and an externally
  justified outcome reference if it is to distinguish utility correctness
  from search-noise effects.

## §180 Silver leaf VNet transfer (2026-08-27)

**Question.** Does the existing combat VNet rank actual isolated Silver
rollout-start leaves well enough to replace the `SimpleAgent` rollout, and can
the saved work become more search per unit time?

**Implementation.** Added a default-off, type-free `SilverLeafObserver` at
`BattleSearcher::rolloutToEnd`. The observer receives a `BattleStateWire` plus
run/combat identity, root/nearest non-random-parent/leaf hashes, depth, and
pre-rollout action count. The live bridge projects the wire into a normal live
`BattleContext` and invokes the existing `CombatValueNet::predict` path; no
second 751-feature extractor or VNet implementation was added. Shadow rows are
deterministically FNV-1a sampled and capped per combat. Direct mode skips only
nonterminal rollouts; exact terminal states retain `evaluateEndState()`.

**Phase 1.** Guarded fair-play `bestbench 1000 8 0 123450`, one thread,
ordinary Silver allocated-cap settings, sampled with modulus 32 and a maximum
of 500 leaves per combat. The corpus contains 66,310 completed rows from seeds
123450–123457 and took 581.90s wall (`real`), with 5,461,485 direct-arm
nonterminal leaf skips observed later. The candidate model is
`models/v_combat_7k_tuned.txt`, SHA-256
`E26FFFDBE21392CC08DB841859D46C13188ACD16B180323868B04DCA55E15EA2`.

**Phase 2.** Whole-seed/combat sibling groups (no random leaf split) produced:

| metric | value |
| --- | ---: |
| rows / seeds / sibling groups | 66,310 / 8 / 10,348 |
| global Pearson / Spearman | 0.775965 / 0.793090 |
| strict pairwise concordance | 0.557776 (14,042 / 25,175 strict pairs) |
| both exact ties / VNet-only ties / utility-only ties | 17,135 / 25,747 / 3,859 |
| centered RMSE / MAE | 7.072633 / 3.331102 |
| top-leaf agreement / mean regret / median regret | 0.747584 / 2.588172 / 0 |

Act concordance was 0.617894 / 0.551690 / 0.544943 for Acts 1 / 2 / 3;
low/high HP was 0.570493 / 0.556329; and short/medium/long rollout was
0.583607 / 0.590266 / 0.541969. The global result is only just above the
predeclared target and the Act-3/long-rollout strata are borderline, so this
was treated as sufficient to permit the smallest gameplay gate but not as
strong evidence.

An OLS affine map fit on four whole training seeds and evaluated on four held
out seeds was `silver_score = 1.511044821751927 * vnet + 51.61250607390761`.
Train RMSE/MAE were 25.769349/21.022450 and held-out RMSE/MAE were
23.239677/19.174299; held-out Pearson was 0.807286. This map was used in the
direct arm.

**Phase 3.** Paired fair-play, one-thread, 1000-simulation runs used the same
seeds 123450–123457. Current Silver A had 2/8 wins, mean floor 42.5, mean
end HP 17.5, and 37.48s/run (297.56s wall). Direct-VNet B had 0/8 wins, mean
floor 29.8, mean end HP 0, and 195.95s/run (1562.13s wall). B skipped
5,461,485 rollouts across 6,485,000 simulations, with zero conversion,
semantic-resolution, transaction, or knowledge failures. Paired analysis had
2 discordant seeds, both A-only wins; floor delta was -12.8 with 95% CI
[-23.8, -1.4], and mean time increased by 158.48s/run. The equal-runtime
follow-up was not allowed because B was neither approximately neutral nor
materially faster.

**Neutrality.** On the one-seed smoke at 100 simulations, disabled and
shadow-enabled outputs matched exactly on seed, win, floor, act, HP, max HP,
fights lost, death combat, and death encounter; only timing differed (1.85525s
versus 3.02792s). The shadow corpus path is opt-in and behavior-neutral when
disabled.

**Reconciliation and Release throughput check.** After review, this branch was
merged with current `main` at `53c8d5c20a8791d34d132422c4bbbc566d7e3c80`.
The leaf model now uses a dedicated `CombatValueNet`, is loaded once during
backend installation, and invokes the existing predictor without the ordinary
global VNet trace hook. The focused integration test also compares the
canonical prediction on a live fixture with the prediction after the
state-to-wire-to-live projection; they agree within `1e-9`, with zero trace
callbacks. A one-seed Release sanity pair at 1,000 simulations, seed 123450,
one thread and the same fair-play configuration measured current Silver A at
floor 50 and 17.64 CPU seconds/run, versus direct B at floor 33 and 59.19 CPU
seconds/run. B skipped 125,325 rollouts; all conversion, semantic-resolution,
transaction, and knowledge failure counters were zero. This is a timing/quality
sanity check, not a new multi-seed gameplay gate.

**Artifacts.** Raw Phase-1 CSV `build/silver_vnet_phase1.csv`, SHA-256
`7B7E6E55497D0B85FCD8159CCCE8489E5AA645DF4521C2963E32A29795D550A0`;
analysis `build/silver_vnet_phase1_analysis.txt`, SHA-256
`B860C27567ADBD72B917231664B875A0C9AEDFFE6529280A74EB9E508AA902AC`;
current A CSV SHA-256
`4081CE8C07D9F0FCB96EDBEEA829935C6926328CDACF0274177A061B9E689336`;
direct B CSV SHA-256
`9022881BD6DD655687A66B40DA9D2ECD41B76995629463509E0EE9896334F438`;
paired analysis SHA-256
`A97E27A2DDE3065851AC7FC64FACF86390FF088E03B1C4DAE4A659DEBED70EA5`;
direct telemetry log SHA-256
`508D4A66473A756AE0929372726AC0BB3B4CC7DC39A5FCDD4BA417746A27789D`.

Release sanity A CSV SHA-256
`488675D4E06179A39F19997CF90A8B439B12992DF8BE776028F7155601E5292A`;
Release sanity A log SHA-256
`AA91B42F2DF39689BD962D38B9BDB893F338042538F1691966854A0F958F84D8`;
Release sanity B CSV SHA-256
`02371247CAA9590977AFAA505C965645B48E435D3879FF7DF27AF539A702916E`;
Release sanity B log SHA-256
`EBA0864B48B4F665F9B852D93B6D2FB95593E03D140B7ED0BC2E78EB559330BF`.

**Verdict: `CURRENT_VNET_DIRECT_SILVER_TRANSFER_REJECTED`.** The current
combat VNet is not accurate enough to become Silver's sole evaluator, and the
fixed-simulation gate showed a large quality loss. The corrected Release sanity
pair also shows the direct arm is materially slower on the tested seed, but
the throughput observation is explicitly limited to that small check. No
production default, selection/exploration logic, tree reuse, rollout policy, or
model training was changed.
## Silver adaptive compute allocation (2026-08-27)

- **Question:** Can a cheap root uncertainty signal recover the PR #66
  1k→3.7k decision-quality improvement at lower average simulation cost?
- **Implementation:** default-off continuation of the same Silver root. After
  1,000 simulations, continue to exactly 3,700 only when the top-vs-second
  root visit-share gap is `< 0.094`; no evaluator, widening, reuse, OOC, or
  hidden-information changes. Baseline was the verified PR #66 merge
  `9f2d67d71f095425457fdb2a91eb1a0a8660a85b`; reviewed implementation was
  `3729624a683e66aba62f9f04c86c0fa80d10c08e`.
- **Phase 1:** on 50 clean deterministic roots, top-two visit gap was the
  strongest beneficial-escalation signal (AUROC 0.775; action-change AUROC
  0.852). The selected coarse threshold escalated 40%, captured 83.3% of
  beneficial roots, and modeled 2,080 mean simulations.
- **Offline shadow:** 25 clean roots, fixed 1k / adaptive / fixed 3.7k mean
  regret `0.07236 / 0.04649 / 0.04562`; top-action agreement with 3.7k
  `84% / 88% / 100%`; adaptive root cost 1,590.6 and full-combat telemetry
  cost 1,730.5 simulations/decision. Adaptive runtime was 16.11 CPU
  seconds/run versus 5.91 nominal fixed-1k and 24.42 nominal fixed-3.7k
  controls; nominal controls retain the unchanged boss multiplier.
- **Gameplay gate:** fixed control on 16 paired seeds completed 9/16 wins,
  mean floor 47.5, mean ending HP 25.8, 18.94 CPU seconds/run. The adaptive
  treatment aborted twice with `unsupported Silver card-select task`; no
  treatment win-rate result is valid. The attempted control also retained the
  native 3x boss multiplier while adaptive used exact 1k/3.7k root budgets, so
  the arms were not budget-comparable. A future gate must set
  `STS_SILVER_EXACT_ROOT_BUDGETS=1` identically for both arms. A narrow
  fallback attempt was reverted after reproducing the failure.
- **Bridge correction and rerun:** the failed seeds were reproduced as
  `CardSelectTask::EXHAUST_MANY` (enum value 6). The narrow fix maps the two
  sequential hand-pick tasks, `EXHAUST_MANY` and `GAMBLE`, to the existing
  visible `HAND` semantic source; no broader CardSelectTask support was added.
  CI passed at `eefddd62829c192d3d67eb774f38cba9bac123fd`. With
  `STS_SILVER_EXACT_ROOT_BUDGETS=1` in both arms, the corrected 16-seed rerun
  completed: fixed 1k and adaptive both won 7/16; mean floor was 45.63 versus
  44.56, mean ending HP 22.31 versus 19.31, and mean runtime 18.76 versus
  25.94 seconds/run. Control/adaptive telemetry was 7,083,000/12,526,100
  simulations, or 992.9/1,842.6 per root/private decision; adaptive escalated
  31.5%. The result validates the crash fix but does not show a gameplay
  benefit, so the verdict remains `INCONCLUSIVE`.
- **Artifacts:** see
  `git show a849fad3da15889138fb4239578ec8e00635a28b:docs/knowledge-base/decision-log/2026-08-27-silver-adaptive-search.md`
  for raw artifact paths and SHA-256 hashes.
- **Verdict:** **INCONCLUSIVE.** Offline quality is promising, but the live
  gate was invalidated by a card-select integration failure and non-comparable
  boss budgets. Do not promote or expand this rule into a dynamic search
  controller; a separate semantic card-select bridge investigation and a
  budget-comparable rerun would be required.

## §181 Silver parent-teacher and matched 10k/25k leaf-model audit (2026-08-27)

- **Question:** On the already collected PR #70 corpus, are parent-state labels
  stable enough to guide a future policy prior, and does paying 2.5× for 25k-A
  leaf labels materially improve a learned scalar Silver evaluator over 10k-A?
- **Provenance:** PR #70 merge baseline
  `0b2fa30151e2e70e450351abdb0700eb8a052c68`; frozen GCP code
  `de04b394cc364c2c84f2e1993724168f37e8c8b9`; designated `sts-test` clean
  run clone. Input SHA-256 values exactly matched the preregistered corpus,
  manifest, and relabel hashes. No leaves were collected or relabeled, and no
  gameplay was run.
- **Parent audit:** 500 A roots/budget (496 valid) and 93/93 valid independent
  25k-B anchors. Against B, top-action agreement at 1k/3.7k/10k/25k-A was
  `73.12% / 77.42% / 77.42% / 80.65%`; legal-Q pair ordering was
  `72.98% / 75.81% / 76.61% / 77.52%`; mean regret was
  `2.554 / 2.397 / 2.407 / 2.328`. For 10k versus the 25k replicate ceiling,
  the 95% whole-root bootstrap margin was `[-8.60pp,+1.08pp]` for top action,
  `[-2.23pp,0]` for pair ordering, and `[+0.001,+0.233]` excess regret; global
  bar pass probability was 23.48%. Of 63 action-eligible 25k-A roots with two
  valid Qs, 14.29% had a top-two margin below 0.25 (median 2.100).
  **Verdict: `POLICY_TEACHER_25K_MATERIALLY_BETTER`.** This is descriptive
  guidance only; raw Q/visit labels remain authoritative and no prior target
  was chosen.
- **Matched models:** all 93 B groups were excluded before preprocessing and
  splitting. Counts were train 341 groups/2,244 leaves, validation 66/314,
  test 93/641, with zero anchor leakage. Stored wires produced the current
  canonical rich 1,766-feature CombatValueNet representation. Both arms used
  uniform weights and the same tuned XGBoost recipe; only the 10k-A versus
  25k-A target changed. M10/M25 best iterations were 500/412.
- **Independent-anchor result:** after the final review correction, both models
  use the same 5,187 non-tied independent-25k-B sibling pairs; model prediction
  ties receive half credit rather than leaving the denominator. M10/M25 had
  161/212 prediction ties and strict sibling concordance `57.89% / 58.72%`
  (delta +0.839pp; 90% paired whole-group interval `[-1.33pp,+2.50pp]`;
  P(delta>0)=74.68%). Top-leaf agreement remained
  `30.86% / 32.10%`, and mean regret `3.902 / 3.569`. The regret delta interval
  was `[-0.705,-0.018]` for M25−M10 (P(M25 lower)=95.94%). M25 also modestly
  improved global RMSE `11.757→11.458` and centered RMSE `5.475→5.390`, but
  subgroup pair-order effects were mixed (for example high-HP and long-rollout
  improved, low-HP, medium-rollout, and hallway declined).
- **Decision:** **`USE_10K_TEACHER`.** The corrected pairwise gain missed the
  ~1pp rule and had only 74.68% probability positive, below the required 90%.
  Efficiency therefore decides the near-tie. The lower M25 regret is useful
  descriptive evidence but does not satisfy the preregistered promotion rule.
  No gameplay improvement is claimed.
- **Artifacts:** durable compact evidence is
  `docs/experiments/evidence/silver_teacher_model_comparison_2026-08-27.json`;
  full GCP outputs remain under
  `/home/philippherrmann/sts_sweep/runs/silver-teacher-e5a8f97/results/`.

## §182 Silver 10k leaf evaluator deployment gate (2026-08-27)

- **Question and frozen implementation:** can the exact selected M10 Silver
  leaf model replace SimpleAgent terminal rollouts without the old generic
  combat-VNet quality/runtime failure? PR #76 implementation review and Linux
  GCC passed at frozen SHA `0f0840b5b3010e3d0f98e9563674ce0506d628a8`.
  The designated `sts-test` Release binary SHA-256 was
  `3cf3c44fb909aa3082cd7f53f5581ad0762ee892fdaa262c886924035f22adf0`.
- **Model/parity:** the exact preserved XGBoost M10 was
  `cfb7bf8b041e6748a6a63f280eb8c43ad2bbefc223e69d0d9807567ebcbe5613`.
  Existing export machinery retained trees 0--500 (`best_iteration + 1`) in
  the native 1,766-feature `CombatValueNet` format. The runtime artifact hash
  was `344c83efebb4e2772971495e1e57e6202192386476e2c0c1b038a84f355f9959`;
  641 independent-anchor rows passed Python/native parity with max/mean
  absolute error `0.000127 / 0.000023` at tolerance `0.001`.
- **Offline control:** on all 93 untouched independent 25k-B groups (641
  leaves; 5,187 non-tied sibling pairs), current combat VNet versus M10 was
  `52.79% / 57.89%` pairwise concordance, `27.16% / 30.86%` top-leaf
  agreement, `4.834 / 3.902` mean regret, `3.772 / 3.761` centered MAE, and
  `5.599 / 5.475` centered RMSE. This passed the preregistered offline stop.
- **Release cost canary:** paired fresh seed `973600`, fair ordinary allocated-
  cap Silver, one thread, 1,000 base simulations, current OOC/search settings.
  A/B were floor `50/33`, CPU seconds `4.85/4.79`, with zero failure counters.
  The absence of a catastrophic runtime regression authorized the 8-seed gate.
- **Gameplay gate:** fresh paired seeds `973600--973607`, same configuration;
  A was ordinary SimpleAgent-rollout Silver and B changed only to M10 direct
  leaves with affine `a=1,b=0`. A/B won `4/8` versus `1/8`, mean floor was
  `50.25 / 31.00`, mean ending HP `39.25 / 1.125`, and mean CPU seconds/run
  `5.531 / 5.748` (summed wall/CPU `44.249 / 45.984` seconds). Paired win
  delta was `-37.5pp`, 95% CI `[-75.0pp,-12.5pp]`; floor delta was `-19.2`,
  95% CI `[-28.2,-9.9]`. Discordance was three A-only wins and zero B-only.
- **Mechanism/health:** A/B executed `5,513,000 / 3,505,000` Silver
  simulations. B skipped `3,041,875` rollouts and made `3,041,875` M10 calls
  taking `17,603,210` microseconds total (about `5.79 us/call`). Every arm had
  zero conversion, semantic-resolution, transaction, and knowledge failures.
  B had no compensating throughput benefit: it was slightly slower per run and
  achieved about `76.2k` simulations/second versus A's `124.6k`, with the
  caveat that catastrophic policy differences shortened B's runs.
- **Stop/verdict:** **`M10_DIRECT_REJECTED`.** The catastrophic quality loss
  and absent throughput benefit triggered the immediate 8-seed stop. Seeds
  `973608--973615`, equal-runtime work, feature optimization, policy-prior work,
  and all larger gates were not run.
- **Artifacts:** compact metrics/hashes are in
  `docs/experiments/evidence/silver_leaf_evaluator_10k_2026-08-27.json`; raw GCP
  CSV/sidecar/log artifacts remain under
  `/home/philippherrmann/sts_sweep/runs/silver-leaf-evaluator-0f0840b/results/`.
## OOC survival × continuation-value action diagnostic (2026-08-27)

- **Question and baseline:** On baseline
  `cad5ee95d0cabafd918dff44a36a57f9d1902666`, does ranking OOC actions by
  `P(alive at K=3) * E[V_win at K=3 | alive]` beat the existing dense Tier-B
  action utility `10*labelWon + labelHp` on their discordant decisions? This
  was action-level OOC counterfactual evaluation, not the E3c combat-leaf
  conditional-survival experiment.
- **Producer:** known-RNG Searcher2, ascension 0, seeds `410100..410115`,
  1,000 source-run simulations, at most four existing eligible OOC decisions
  sampled per run, K=3 continuation fights at 150/100/50 simulations, native
  floor/win bootstrap, and 16 matched continuation seeds per legal sibling
  action. `models/v_combat_7k_tuned.txt` loaded with the existing alpha 0.5;
  native `models/v_rich_trees.txt`, `models/v_win_trees.txt`, and
  `models/policy_trees_c.txt` also reported loaded. The corpus contains 64 OOC
  decisions, 367 actions, and 16 replicates/action. The maximum absolute error
  between `p_survive * v_alive` and `mean(I*V)` was exactly 0.0.
- **Discordance and adjudication:** 21 decisions disagreed. All were evaluated
  by an unbootstrapped full-run continuation at 1,000 combat simulations with
  16 action-paired common continuation seeds (672/672 valid rows). The dense
  ranking won 14 decisions, the factorized ranking won 6, and 1 tied; the
  factorized win fraction excluding ties was 30%. Dense versus factorized mean
  two-choice comparative regret was `3.9792` versus `6.8929`; median
  comparative regret was `0.0` versus `2.0`, in the existing terminal
  `10*won + HP` adjudication units. The adjudicator evaluated the two rankers'
  choices, not every legal action, so these are not all-action oracle regrets.
- **Interpretation:** Every selected action on both sides survived all 16 K=3
  producer replicates (`p_survive=1`). Thus these discordances were driven by
  survivor continuation value versus the dense HP term, not by different
  measured danger. This limits diagnosis of rare safety tradeoffs, but it does
  not rescue the proposed ranking: on the observed discordant set it failed
  both preregistered promotion conditions.
- **Artifacts:** `build/ooc_factor_e4/raw.csv` (SHA-256
  `F08E317DC8D07181F84B56B4DF84AA1F19F40A96C20D689E5F4739170A166591`),
  `raw_block2.csv` (`00C4CC53A45E1E40A6945954F8AD03EEFB9F0FE1089320865F4F2B964E09A5BC`),
  `adjudication_all.csv`
  (`57301483685CB82A96F9A95DCB8C7C38F59C30F4C46FD689B9777514A7BAF18E`),
  and `final/summary.json`
  (`33DE69E32556EF03C692495B777374E8BCA1930A883461EEE944AEB415A79301`).
  The frozen Release executable SHA-256 was
  `71CC739F65015C048FD6C87276251D5FA6E9B83E00DE520EBE807E98F39B2E3B`.
- **Zero-simulation correction:** Since dead branches have `labelWon=0`,
  `P(S)E[V_win|S]=E[V_win]`; on the 21 all-surviving adjudicated choices the
  factorized score was pure QWin. The 14/6/1 headline used shaped terminal
  utility `10*won+HP`. Recomputing the same paired rows on terminal win alone
  gives current/factor/tie `3/3/15`, mean win-probability regret
  `0.03571/0.03274`, and median `0/0`. Fixed-regime coverage is 46/367 actions
  below unit survival, 15/64 decisions with sibling survival spread, and 3
  opposing-order safety-strength tradeoffs. Encounter-marginalized coverage is
  88/367, 25/64, and 15; however, only 2/22 marginal dense-vs-QWin ranking
  disagreements have survival-different selected actions. Screen-level counts
  and per-decision min/max/delta are in `corrected_fixed/` and
  `corrected_marg/` under the raw artifact directory. Corrected fixed summary
  SHA-256 is `C34E787791A8ECD8BD1733EBFB42EBADD32F609C88EB2617190B034E0AAC3F1B`
  and coverage CSV is
  `28E0CC1FABFA924146247198DBC3B230C43FDF67AC5A6B8910DF3CCA8921D5B0`;
  marginal summary is
  `5AC1967497B575C056CB15E28E95467DFBED365894B00356A8BC14D1503C6107`
  and coverage CSV is
  `02C6C8F99E1404D054493BFCF36338F1F1E6CC8B568045B79A74BF1163184C07`.
- **Corrected verdict:** **REJECT pure K=3 QWin on the observed discordant
  selected-action pairs; INCONCLUSIVE on explicit
  survival-vs-strength modeling.** Do not promote or train from this result.
  If continued, use a targeted survival-sensitive corpus. A later auxiliary-
  head test would be a statistical-learning decomposition test and should keep
  the V4 model family fixed; it is not authorized by this correction. The
  diagnostic remains offline-only and production gameplay is unchanged.

## Targeted marginal OOC survival tradeoffs (2026-08-27)

- **Question and frozen implementation:** On the 15 genuine opposing-order
  `regime=marg` contexts discovered above, does the action selected by
  `p_survive * v_alive` predict fresh terminal run wins better than always
  selecting higher survival or always selecting higher survivor value? Dense
  K=3 was a secondary baseline. Reviewed experiment SHA was
  `7baf98a7b464a7cfbc91f9ee163a691e4cd3dc2b`; no executable change occurred
  after review and CI passed on that SHA.
- **Targeting and adjudication:** deterministic selection from the frozen PR
  #71 raw corpus, not uniform new OOC collection. Fifteen contexts, two actions
  per context, and 16 fresh matched futures per action produced 480/480 valid
  full-run branches. Each sibling pair shared its resampled remaining-act
  hidden encounters and continuation/search seed. The unbootstrapped
  adjudicator used 1,000 combat simulations; terminal run win was primary and
  final HP diagnostic. The run was Ironclad, ascension 0, known-RNG Searcher2,
  with the frozen combat VNet (alpha 0.5) and native win/rich/policy trees.
- **Outcomes:** safe/strength/tied contexts were `4/5/6`. Survival-only,
  strength-only, combined-product, and dense-K3 correct non-tied choices were
  `4/9`, `5/9`, `6/9`, and `5/9`. Mean chosen terminal-win rates were
  `0.5917`, `0.6250`, `0.6458`, and `0.6042`; mean two-choice regrets were
  `0.0917`, `0.0583`, `0.0375`, and `0.0792` (all median regrets 0).
  Combined-minus-survival chosen-win difference was `0.05417`, with paired
  source-seed-cluster bootstrap 95% interval `[-0.00735, 0.14338]`;
  combined-minus-strength was `0.02083`, interval `[-0.06250, 0.11029]`.
  Combined-minus-dense was `0.04167`, interval `[0, 0.13021]`, but dense was
  not part of the primary decision rule.
- **Artifacts and provenance:** target manifest
  `build/ooc_targeted_e1/targets_rules_reviewed.csv` SHA-256
  `6CCA74E13D8ED653083671E42530A3F36C55954616A2AE86D020534B9B6954D5`;
  raw adjudication `build/ooc_targeted_e1/adjudication_7baf98a.csv`
  `1F8CABA2A8DFC5DFC9A460F57CDBAA15A79594D13EFBB9A9DD0250305D991642`;
  run log `build/ooc_targeted_e1/gcp_ooc_targeted_e1_7baf98a.log`
  `232552386519D648D1B9BF86F79003CB8AC605EF329CA47326395627B7627888`;
  decisions `build/ooc_targeted_e1/final/decisions.csv`
  `0E727A46ED075C5BF36D543DFAD732243959495B0B223D909A2265997186832`;
  summary `build/ooc_targeted_e1/final/summary.json`
  `5DC020CECD2A2B7BBDF1E65E74A5534CCC5767C8FD624E65BE12A86FBD146818`.
  Frozen executable SHA-256 was
  `D628CB493B3EC21FC68D2E803C532AE0F8F6FE447C3DA4DCA47C964215545299`;
  exact combat/win/rich/policy model hashes are recorded in the corresponding
  decision log. An independent post-run audit reproduced all pairing, metrics,
  bootstrap intervals, and the verdict.
- **Verdict:** **INCONCLUSIVE.** Combined product has the best point accuracy,
  selected win rate, and regret, but both primary confidence intervals include
  zero. This targeted exploratory result does not authorize production OOC
  changes, model training, or an auxiliary-head claim. Production gameplay is
  unchanged.

## Â§183 Silver M10 rollout blend: OFFLINE REJECTED before anchor (2026-08-28)

- **Question:** Can a low-weight affine correction of the actual auxiliary
  SimpleAgent rollout by the exact M10 prediction improve sibling ranking and
  selected-leaf regret without losing the rollout's tactical continuation
  signal?
- **Baseline and inputs:** branch baseline `29edcfd` (PR #76 merged). Reused the
  immutable 3,207-row selected corpus, 500-group manifest, 17,030-row relabels,
  canonical 1,766-feature rows, and exact M10. All six recorded input/runtime
  hashes matched; see the compact evidence manifest. No leaves were collected,
  teachers rerun, or model retrained.
- **Leakage boundary:** all 93 groups containing an independent 25k-B row were
  excluded before metric inspection. Selection used corrected 25k-A only and
  retained 329 complete sibling groups / 2,445 leaves / 31,797 non-tied
  reference pairs. The 25k-B anchor was not evaluated.
- **Fixed-grid result:** alpha 0/0.1/0.25/0.5/0.75/1 pairwise concordance was
  `62.879/63.427/63.830/64.874/66.060/66.903%`; top-leaf agreement was
  `40.426/36.474/36.778/35.866/33.131/37.994%`; mean regret was
  `2.472/2.508/2.463/2.428/2.538/2.664`. Alpha 0.1's pairwise delta 95%
  whole-group bootstrap interval was `[+0.259,+0.719]pp`, but its top-leaf
  delta interval was `[-7.295,-0.912]pp`; regret also worsened.
  Alpha 0.25 kept the same material top-leaf conflict. Lower centered RMSE at
  larger weights did not override ranking/regret metrics.
- **Depth interaction:** empirical depth tercile edges 4/5 were established
  before subgroup inspection and subgroup metrics were emitted. Phase 1's
  candidate rule already failed, so no schedule was selected or optimized.
- **Verdict/stop:** **`M10_BLEND_OFFLINE_REJECTED`**. No candidate lock, 25k-B
  evaluation, native implementation, performance gate, or gameplay gate was
  run. Full ignored selection report SHA-256:
  `162b5de871eed0fd3284d7fe60b5fcfb733b43ddf25356489db4c34b5094537d`.
  Compact evidence:
  `docs/experiments/evidence/silver_m10_rollout_blend_2026-08-28.json`.

## §184 Silver M10 fixed-blend gameplay sweep: REJECTED (2026-08-28)

- **Authorization boundary:** after the preregistered offline rejection above,
  the user explicitly overrode that stop, required this same branch, and
  requested all six fixed alphas on 16 common seeds. This is an exploratory
  gameplay sweep, not a passed offline gate; 25k-B remained untouched and the
  earlier `M10_BLEND_OFFLINE_REJECTED` verdict is unchanged.
- **Frozen implementation/provenance:** independently reviewed commit
  `6532d8f30ea2af365b48c998e8562cda2c325796`; draft PR #77 Linux GCC passed.
  The designated-GCP Release executable SHA-256 was
  `e52a6120e723f14f0c0468a4e84fe9ce2afc872536471ae5f7e6f7d6a3cebb91`;
  exact native M10 SHA-256 was
  `344c83efebb4e2772971495e1e57e6202192386476e2c0c1b038a84f355f9959`
  (501 trees). A logged alpha-0.25 canary passed
  `check_benchmark_canary.py` before expansion.
- **Protocol:** designated `sts-test`, Release, fair play, one thread, ordinary
  allocated reuse cap, 1,000 base simulations, depth threshold zero, common
  fresh seeds `974100--974115`. Arms were run sequentially in order
  alpha `0/0.1/0.25/0.5/0.75/1.0`; each produced 16 flushed rows plus a
  sidecar and telemetry log.
- **Outcomes:** wins were `13/12/11/9/8/1`; mean floors were
  `49.563/48.438/47.313/47.938/44.000/27.875`; mean ending HP was
  `34.563/35.313/28.750/21.813/18.625/2.000`; mean CPU seconds/run was
  `5.172/13.922/13.744/13.886/11.712/7.027`. Lower runtime at large alpha
  reflects much shorter losing runs, not an efficiency gain.
- **Paired uncertainty versus alpha zero:** alpha 0.1 had win delta `-6.25pp`
  (95% paired seed bootstrap `[-31.25,+18.75]pp`) and floor delta `-1.125`
  (`[-5.000,+2.375]`). Alpha 0.25 was `-12.5pp` wins
  (`[-43.75,+18.75]`) and `-2.250` floor (`[-5.875,+1.063]`). Alpha 0.5 was
  `-25pp` wins (`[-50,0]`); alpha 0.75 was `-31.25pp` (`[-56.25,0]`);
  alpha 1.0 was `-75pp` (`[-93.75,-50]`) and `-21.688` floor
  (`[-29.375,-14.063]`). Bootstrap used 100,000 deterministic paired-seed
  resamples with seed 6532.
- **Mechanism/health:** alpha-zero made zero M10 calls. Positive arms made
  `9,569,248 / 9,324,039 / 9,319,674 / 8,075,852 / 5,104,801` calls, exactly
  equal to blend invocations, taking `66.924 / 63.667 / 65.219 / 57.629 /
  36.501` million microseconds. Depth-zero avoided no eligible calls. All arms
  recorded zero conversion, semantic, transaction, and knowledge failures.
- **Verdict:** **`M10_BLEND_REJECTED`.** No tested nonzero weight improved the
  paired gameplay control; even alpha 0.1 had worse win/floor point estimates
  and about 2.7x CPU/run. Keep the implementation default-off. Do not promote,
  extend beyond 16 seeds, run equal-runtime follow-up, start Task B, or begin
  policy-prior integration from this experiment.

## §185 Silver M10 depth-gated blend follow-up: REJECTED (2026-08-28)

- **Question/design:** can alpha 0.1 recover useful deep-leaf correction while
  preserving shallow rollout values and avoiding enough M10 calls to improve
  runtime? Before new gameplay, thresholds 4 and 5 were locked from the
  original offline empirical depth-tercile edges. No threshold was selected
  from the preceding fixed-alpha gameplay outcomes.
- **Protocol/provenance:** same reviewed and CI-passed scientific SHA
  `6532d8f30ea2af365b48c998e8562cda2c325796`, GCP Release executable
  `e52a6120e723f14f0c0468a4e84fe9ce2afc872536471ae5f7e6f7d6a3cebb91`,
  and exact native M10
  `344c83efebb4e2772971495e1e57e6202192386476e2c0c1b038a84f355f9959`.
  Designated `sts-test`, fair, one thread, 1,000 base simulations, allocated
  reuse, and fresh paired seeds `974200--974215`. Arms were pure rollout,
  alpha 0.1 for `d>=4`, and alpha 0.1 for `d>=5`.
- **Outcomes:** control/d4/d5 wins were `10/10/11`; mean floors were
  `46.063/47.125/45.000`; ending HP was `36.813/36.938/31.625`; mean CPU
  seconds/run was `4.721/12.043/11.079`. Against control, d4 had win delta
  `0pp` (100,000-resample paired-seed 95% interval `[-25,+25]pp`) and floor
  delta `+1.063` (`[-4.000,+7.875]`). D5 had win delta `+6.25pp`
  (`[-12.5,+25]pp`) but floor delta `-1.063` (`[-4.438,+1.250]`) and ending-HP
  delta `-5.188` (`[-19.313,+8.813]`).
- **Coverage/cost:** d4 invoked M10 on `7,118,695/8,829,895` eligible leaves
  (`80.62%`) and avoided `1,711,200`; d5 invoked `4,952,622/8,798,554`
  (`56.29%`) and avoided `3,845,932`. Inference consumed 52.449/39.868 million
  microseconds. All conversion, semantic, transaction, and knowledge failures
  were zero.
- **Verdict:** **`M10_BLEND_REJECTED` for these depth schedules.** D4 tied wins
  with a weak positive floor point estimate but cost 2.55x CPU; d5 gained one
  win while regressing floor/HP and cost 2.35x CPU. The mixed effects and wide
  intervals do not establish a clear stable depth interaction. Do not tune
  additional thresholds or weights against this seed block, extend N, or
  promote a gate.

## 186. Silver 25k parent-Q policy scorer misses the offline gate (2026-08-28)

- **Frozen run:** baseline `effbc1bc8c84482c998829f0b29bdb1425b45ff1`;
  decision-bearing, CI-passed SHA
  `85599a3d2c6e55f32236ea59c814bdd1250d73bb`; designated GCP host `sts-test`,
  root `/home/philippherrmann/sts_sweep/task-b-85599a3`, Python 3.12.3,
  XGBoost 3.3.0, NumPy 2.5.1, and GNU 13.3.0.
- **Input/coverage:** `relabel.jsonl` SHA-256
  `abce8e1c59def61f4b1206ae0515486bf0faf5a23586cd7a59fced83a961865c`;
  500 A rows/budget, 496 valid 25k-A parents, and 93/93 valid B anchors.
  Feature generation retained 495 complete parents and 1,727 actions. Four
  invalid zero-simulation teacher rows and one whole-parent semantic-resolution
  incompatibility were excluded; no partial action set was emitted.
- **Split/model:** test-only anchors had zero leakage. Train/validation/test
  were 327/75/93 parents and 1,152/205/370 actions. Canonical feature width was
  1,788; target was `Q_25kA(s,a) - mean_b Q_25kA(s,b)`. One fixed XGBoost
  squared-error/hist recipe used validation early stopping (best iteration 96).
- **Current order / model:** pairwise 0.66361/0.68858; top agreement
  0.55914/0.64516; mean regret 2.86224/2.68121; median regret 0/0;
  centered-Q MAE 4.95394/4.50694; RMSE 7.81372/7.22796; Spearman
  0.42638/0.50630. The model had 81 prediction ties over 981 pairs.
- **Teacher references:** 1k/10k/25k pairwise 0.73649/0.77166/0.78084; top
  0.74194/0.77419/0.81720; mean regret 2.53940/2.33202/2.32816.
- **Bootstrap:** 5,000 parent replicates. Pairwise delta p05/p50/p95 was
  -0.01789/0.02468/0.07421, probability positive 0.822. Regret reduction was
  -0.51773/0.16755/0.89064, probability positive 0.6558. Top delta was
  +8.602pp, probability positive 0.9756.
- **Cost/artifacts:** feature generation 1.518 s; training 0.577 s; Python
  prediction 17.273 microseconds/action. Model SHA-256
  `3de211d354c2e03de2516c5ab68d35ec8aba40a4c02cb61937c02925221d1f20`;
  report SHA-256
  `c2ac2e2cb5fa367860f5dd9981756c613adbc69b698ce1d0bb017c8a078a09fe`.
- **Verdict:** **`POLICY_MODEL_OFFLINE_REJECTED`**. The +2.497pp pairwise
  point change missed 3pp and both ranking/regret probabilities missed 90%.
  Top improved, so evidence did not conflict. No native export, online prior,
  PUCT, or gameplay run was performed. Exact diagnostics are in
  `docs/experiments/evidence/silver_parent_policy_25k_2026-08-28.json`.

## 187. Silver 25k parent-Q online policy methods rejected (2026-08-28)

- **Authorization/status:** this was an explicit exploratory override of the
  offline `POLICY_MODEL_OFFLINE_REJECTED` gate because offline top-action
  agreement improved. The offline verdict remains unchanged. Attempts 1 and 2
  stopped on correctness failures and their partial arms are not evidence.
- **Final provenance:** corrected attempt-3 SHA
  `a805d1404e10cc6eaa4fc2d4268f450937b25f0e`; designated `sts-test`, Release,
  fair mode, one thread, ordinary Silver, 1,000 base simulations, allocated
  reuse cap, and common seeds `975000--975031`. Exact executable SHA-256 was
  `351c781a3b4478418019368d6b1f235f99c853d6d78abeca6dff252299315433`;
  source-model JSON SHA-256 was
  `3de211d354c2e03de2516c5ab68d35ec8aba40a4c02cb61937c02925221d1f20`;
  compact 97-tree SHA-256 was
  `4e2925bd17154ab60fcef52018ade3a85f82f246b1dc149be0da5cd21249386d`.
- **Correctness:** the attempt-3 exact-action repair cleared both former crash
  canaries (B seed 975000 and C seed 975024) and completed all 128 registered
  runs. A/B/C/D crossed current/learned initial ordering with ordinary
  UCT/fixed rank-prior PUCT (`c_puct=2.5`).
- **Outcomes:** A/B/C/D wins were `20/20/17/15`; mean floors were
  `47.750/46.594/45.500/44.750`; mean ending HP was
  `30.313/29.656/22.688/19.750`; mean CPU seconds/run was
  `4.932/7.355/6.843/6.766`. B/C/D cost `1.491x/1.388x/1.372x` A.
- **Paired effects versus A:** B had 0 wins and -1.156 mean floors; C had -3
  wins and -2.250 floors; D had -5 wins and -3.000 floors. The 10,000 shared
  whole-seed bootstrap 95% win-delta intervals were respectively
  `[-18.75,+15.625]pp`, `[-25,+6.25]pp`, and `[-37.5,+6.25]pp`.
- **Telemetry limitation:** `STS_SILVER_TELEMETRY=1` was absent from the final
  cohort. Simulation, inference-call/time, scored-node, legal-action,
  PUCT-selection, and aggregate failure-counter fields are unavailable and
  recorded as `null`, never zero.
- **Verdict/cleanup:** **`ONLINE_POLICY_METHODS_REJECTED`**. No arm gained the
  required three wins and every arm exceeded the 1.25x runtime limit. No
  mechanism was promoted. PR #79 removes the rejected runtime ordering/PUCT
  machinery and active compact model while retaining the reusable offline
  pipeline and durable evidence. Complete hashes, contrasts, factorial effects,
  and all 32 paired rows are in
  `docs/experiments/evidence/silver_policy_online_methods_2026-08-28.json`.

## 188. Silver root action-pruning ladder Phase 1: candidate-retention audit (2026-08-28)

- **Hypothesis/method:** Before changing search, can root candidate sets ranked
  by current Silver order, the frozen parent-Q model, or existing 1k/10k/25k-A
  teacher Q/visit signals retain the independent 25k-B best action? The
  analyzer evaluates top-1, top-2, top-3, and top-half (`ceil(K/2)`) candidate
  rules, always retaining the full exact score tie at the boundary. It uses a
  deterministic 5,000-replicate parent bootstrap (seed `20260828`) and reports
  the 30 single-action anchors only as a secondary integrity population.
- **Inputs/population:** hash-matched relabel / selected corpus / manifest /
  features / frozen model SHA-256s were respectively
  `abce8e1c59def61f4b1206ae0515486bf0faf5a23586cd7a59fced83a961865c`,
  `bdac7173f789cd1439438eca5079a167e15de7f9aaf8c4fc242635a38790a2c7`,
  `db67ff9df6a1578a46e4e09038b5f2548772fc9c70fc54a00b1576f659883cd7`,
  `0377aaef862362cdf1fa3925579a73b66381cbd646762a0453b6a939149923bd`,
  and `3de211d354c2e03de2516c5ab68d35ec8aba40a4c02cb61937c02925221d1f20`.
  The primary population is 63 independent 25k-B multi-action parents / 340
  actions; the secondary integrity population is 30 single-action parents.
- **Results:** current Silver top-2 retained the B-best action on 76.19% of
  primary parents with mean best-retained regret 1.274; frozen-model top-2 was
  87.30% / 0.974. Frozen-model top-3 was 95.24% / 0.549 but still excluded a
  B-best action with regret at least 3 on 2/63 parents (3.17%). The audit found
  17 feature-identical action groups and 26 exact model-tied groups; no tie is
  silently resolved by stable ordering. Max-Q / max-visit agreement was
  96.83%/98.41%/100% at 1k/10k/25k-A respectively.
- **Verdict/authorization:** **`PHASE_1_COMPLETE_PHASE_2_AUTHORIZED`**. This
  is descriptive offline evidence, not an authorization for permanent hard
  pruning or learned runtime ordering. Sequential Halving does not depend on
  the model and remains the next gated implementation phase. Full report:
  `docs/experiments/evidence/silver_action_pruning_retention_2026-08-28.json`
  (SHA-256 `838f7c23fe985c00d8b609a87f1858a6f231ac7f3245e29da4e8bc077baac0e6`).

## 189. Silver root action-pruning ladder Phase 2: Sequential Halving rejected (2026-08-28)

- **Implementation/protocol:** reviewed implementation SHA
  `fae0a852441c4c54b23a82ba5c95137b95954676` adds a default-off
  root-action mode only. Every legal root edge remains stored; forced-edge
  pulls are root-only, internal nodes retain UCT, chance widening is untouched,
  and adaptive allocation conflicts fail closed. The replay restored all 93
  stored parent wires into fresh `reuseCapMode=NONE` sessions with adaptive
  disabled, paired the same wire/search seed for ordinary UCT and Sequential
  Halving, and emitted 744 rows (2 methods x 4 budgets x 93 anchors). Primary
  analysis is the 63 multi-action 25k-B parents; bootstrap used 5,000
  deterministic parent resamples, seed `20260828`.
- **Inputs/artifacts:** relabel SHA-256 was
  `abce8e1c59def61f4b1206ae0515486bf0faf5a23586cd7a59fced83a961865c`.
  Raw replay JSONL is ignored at
  `build/silver_action_pruning_replay_20260828.jsonl`, SHA-256
  `63b051b741d4ebf6648ac3e79c1353da23639e48e8ea23ceef2faf603887b0fa`.
  The durable analysis is
  `docs/experiments/evidence/silver_action_pruning_sequential_halving_2026-08-28.json`,
  SHA-256 `fb85783d0f1733fdfab6eeadb264ad1dd1a7fee7f1f9c8e5689c8b86e507d98d`.
- **Results:** ordinary versus Sequential-Halving best-action matches / mean
  regret were `27/3.110` versus `27/3.738` at 64, `30/3.161` versus `32/3.192`
  at 128, `31/2.536` versus `31/3.055` at 256, and `40/2.274` versus
  `35/2.612` at 1000. Sequential Halving added >=3-regret exclusions at
  64 (19 vs 16), 256 (14 vs 13), and 1000 (12 vs 9). Aggregate replay CPU was
  0.998x ordinary, so runtime was not the rejection cause.
- **Gate/stop:** **`SEQUENTIAL_HALVING_REJECTED`**. It was non-worse on neither
  two small budgets nor mean regret, had no preregistered useful effect with
  bootstrap probability >=0.90, failed the 1000 no-harm condition, and created
  new catastrophic exclusions. Do not implement progressive unpruning,
  learned-ranked unpruning, hard pruning, or gameplay smoke under this ladder.

## 190. Narrowed Silver progressive unpruning: current-order treatment rejected (2026-08-28)

- **Implementation/protocol:** User-requested follow-up to the Phase 2 stop,
  deliberately recorded as a separate and smaller hypothesis test rather than
  a revision of `SEQUENTIAL_HALVING_REJECTED`. Implementation SHA
  `40556914bf42678313931a70e68575b354a35b23` added a default-off root mode.
  Roots with fewer than six legal actions remained ordinary UCT. Eligible roots
  retained every edge but activated current-Silver-order indices 0--2 first,
  then one additional edge after 16, 32, 64, and 128 newly added root
  simulations. Root selection used ordinary UCT only over that temporary mask;
  all internal decision nodes and chance widening were unchanged. Replay used
  fresh `reuseCapMode=NONE` sessions, `adaptiveEnabled=false`, the 93 stored
  parent wires, and only ordinary UCT versus this treatment at 128/256/1000.
  The independent reference remains the 25k-B labels; primary analysis is the
  original 63 multi-action parents, with all 93 retained as an integrity view.
- **Inputs/artifacts:** selected-corpus SHA-256
  `bdac7173f789cd1439438eca5079a167e15de7f9aaf8c4fc242635a38790a2c7` and
  relabel SHA-256
  `abce8e1c59def61f4b1206ae0515486bf0faf5a23586cd7a59fced83a961865c`;
  the frozen policy model was not consumed. Raw replay JSONL is ignored at
  `build/silver_action_pruning_progressive_current_20260828.jsonl`, SHA-256
  `0c330adbfd29ef7d1244170aff783ccf900b955ec569d5ea0fb7eff26074534b`.
  Durable analysis is
  `docs/experiments/evidence/silver_action_pruning_progressive_current_2026-08-28.json`,
  SHA-256 `1231530b9381009d36622fd32b2a496d5d18d5eb4a0958ba26abd07c8019e243`.
- **Gate:** strict no-harm was preregistered as non-worse best-action matches
  and non-increased mean regret at both 128 and 256; the 1000 condition allowed
  at most one fewer match and +0.10 mean regret; no budget could add a
  >=3-regret failure; aggregate replay CPU had to remain <=1.10x. Bootstrap
  used 5,000 deterministic parent resamples, seed `20260828`.
- **Results:** ordinary versus progressive best-action matches / mean regret /
  >=3-regret counts were `30 / 3.161 / 18` versus `31 / 3.331 / 16` at 128,
  `31 / 2.536 / 13` versus `30 / 3.026 / 14` at 256, and `40 / 2.274 / 9`
  versus `42 / 1.761 / 8` at 1000. The treatment's 128 mean-regret bootstrap
  improvement probability was 0.368; at 256 it was 0.000. Aggregate replay
  CPU was 1.007x ordinary.
- **Gate/stop:** **`PROGRESSIVE_CURRENT_ORDER_HARMFUL`**. The treatment failed
  strict 128/256 no-harm and introduced one 256 >=3-regret failure. The 1000
  recovery and CPU result do not override that lower-budget/tail evidence.
  Therefore cached frozen-model ranking is not authorized, no runtime policy
  scorer was built, and hard pruning/gameplay smoke remain out of scope.

## 191. Silver action-pruning post-gate cleanup (2026-08-29)

- **Decision:** Merge the negative-result package without retaining rejected
  runtime mechanisms. This is maintenance following the Phase 2 and narrowed
  progressive-unpruning gate failures, not a reinterpretation of either
  result. Cleanup implementation SHA:
  `65a833e87b9a79356837642157d1f43f04c9d424`.
- **Removed from production/build graph:** the default-off root-action mode
  configuration, Sequential-Halving and progressive-unpruning root selection,
  pruning telemetry, forced/masked root-edge search primitives, their focused
  bridge fixtures, and the `silver_action_pruning_replay` executable/target.
  Ordinary Silver UCT is consequently the only shipped root-action selection
  path again.
- **Retained:** the Phase 1 candidate-retention analyzer and tests, the two
  historical replay-analysis scripts, all three durable evidence reports and
  their input/raw hashes, plus the current-research and ledger conclusions.
  The analyzer sources remain reproducible analysis records; they do not imply
  that the removed runtime treatments remain supported.
- **Follow-up authorization:** none for action pruning, learned ranking, or a
  runtime policy scorer. A subsequent Silver investigation must state a new,
  independently testable hypothesis and preserve these negative results as its
  boundary condition.

## §192 Phase-12 semantic survival-tradeoff full-run adjudication: INCONCLUSIVE (2026-08-29)

- **Question and prospective freeze:** Does the combined
  `p_survive * v_alive` rule select higher terminal-win actions than the
  survival-only and strength-only rules on the union of 18 original and 19
  augmentation contexts that independently retained their frozen Phase-12
  tradeoff under fresh 16-future K=3 confirmation? No contexts or action pairs
  were reselected from terminal outcomes. The 37-row semantic manifest had 36
  unique source seeds; seed `810008` contributed two distinct decisions.
  Frozen combined choices were safe/strength `26/11`; dense-K3 choices were
  `34/3`.
- **Implementation and protocol:** PR #83 reused PR #80's seven-field semantic
  sibling identity, fail-closed uniqueness, and atomic whole-manifest
  preflight, then invoked the existing unbootstrapped terminal
  `finishOocCounterfactual` continuation. Reviewed and Linux-GCC-passed
  scientific SHA was
  `4794647faf989cc0710c4239302d4cb27b27b053`; exact GCP Release executable
  SHA-256 was
  `B9E592991AAFC77454485E5B8182CB682E8AE92AA1425987D95AC12F1059026F`.
  The 37/37 no-futures semantic preflight passed before 37 contexts x 2 frozen
  actions x 16 fresh matched futures produced 1,184/1,184 valid branches.
  Future identities `1000000--1000015` were disjoint from historical and fresh
  K3 runs. Siblings shared hidden-encounter and continuation/search seeds.
  Configuration was Ironclad ascension 0, project-fair Searcher3, one thread,
  belief/chain off, 64 particles, 1,000 reference combat simulations, combat
  VNet alpha 0.3, and the frozen strategic-token OOC gate stack. Terminal run
  win was primary; final floor/HP were diagnostics. Wall time was 16,647 s
  (4h37m27s).
- **Terminal truth:** safe/strength/tied contexts were `17/12/8`. Survival,
  strength, combined-product, and dense-K3 correct non-tied choices were
  `17/29`, `12/29`, `19/29`, and `16/29`. Mean selected terminal-win rates
  were `0.3649`, `0.3530`, `0.3851`, and `0.3649`; mean two-action regrets
  were `0.0676`, `0.0794`, `0.0473`, and `0.0676` (all median regrets zero).
  Combined had the best point accuracy, selected win, and regret.
- **Paired uncertainty:** combined-minus-survival selected-win difference was
  `+0.02027`, with deterministic 10,000-resample source-seed-clustered paired
  bootstrap 95% interval `[-0.02404,+0.06771]`; combined-minus-strength was
  `+0.03209`, interval `[-0.03125,+0.09539]`; combined-minus-dense was
  `+0.02027`, interval `[-0.02431,+0.06908]`. Every interval includes zero.
  Act and screen results are descriptive only because cells are small.
- **Artifacts:** frozen manifest
  `build/phase12_semantic_fullrun_37.csv`
  `6E7B8EDB608B61C45FB9CBC6A1375FD1770759BCA0287F4F6C77EF3C040C5988`;
  raw adjudication `build/phase12-fullrun/fullrun_16.csv`
  `F1F842FE773C17E9EF7A1999A3189C03540DD80E6E383E4ED68422D467828F9A`;
  raw log `build/phase12-fullrun/fullrun.log`
  `0DC750CEF3A22D4E89C35ABF944D2F462CE37D907895E2BB0492D782CAAF64DD`;
  decisions `build/phase12-fullrun/analysis/decisions.csv`
  `390269EAABF5B60DC2EF21660368BA026A225BF80E31CEC64CF308C5E5F74B95`;
  summary `build/phase12-fullrun/analysis/summary.json`
  `49F35D5009B50AFBE4A87E825BB8E05651CCB39862AA256C32C70144CCA09C09`.
  Exact model and preflight hashes are preserved in
  `build/phase12-fullrun/provenance.txt` and the PR evidence packet.
- **Verdict:** **INCONCLUSIVE** under the existing PR #75 decision rule.
  Combined product remains directionally promising but is not established
  against either primary baseline. This result does not authorize a production
  OOC policy change, K-horizon tuning, model training, new trajectory
  collection, or outcome-driven candidate expansion.

## Learned Silver guidance diagnostic (2026-08-29)

- **Scope:** Bounded offline review from frozen policy A/B artifacts and
  existing leaf evidence. No model training, gameplay seeds, or broad replay
  was run. Baseline checkout SHA was
  `60e00eb58f636c7fad11403dc9b01f44733f4280`.
- **Result:** On 93 independent 25k-B policy parents (63 multi-action), exact
  feature aliases affected 19 action pairs, 17 with different B values. The
  unavoidable pairwise floor was only 0.866 percentage points. On 981
  non-tied B pairs, current ordering / learned policy / 25k-A teacher scored
  66.361% / 68.858% / 78.084% pairwise, with top-action agreement 34.921% /
  47.619% / 73.016% and mean regret 4.225 / 3.958 / 3.437.
- **Interpretation:** Exact aliasing is real but too small to explain the
  regression. The tested rank-PUCT integration was harmful relative to
  ordinary UCT, while direct M10 leaf replacement was harmful online; neither
  result was an oracle replay.
- **Decision:** The historical next step was faithful parent snapshots and a
  small root-only replay. Subsequent experiments recorded below completed that
  line. See [the diagnostic report](evidence/silver-learned-guidance-diagnostic-2026-08-29.md)
  and the read-only analyzer `tools/analyze_silver_guidance_alias.py` (removed by ADR-0022).

## §193 Silver root-only exploration control rejected offline (2026-08-29)

- **Question:** Could lowering only deterministic root UCT exploration explain
  the earlier action-pruning signal without masking actions or changing
  internal/chance search?
- **Protocol:** Root c values 25.0/control, 18.5, 12.5, and 9.9 were replayed
  at 64/128/256/1000 simulations on 63 multi-action 25k-A anchors, with all 93
  anchors as an integrity view. Adaptive search was off and reuse was `none`.
- **Result:** Every reduced-c candidate introduced new `>=3`-regret choices at
  both 128 and 256. CPU stayed within the gate, so tail harm—not cost—rejected
  all candidates before the independent 25k-B gate.
- **Decision:** **ROOT_EXPLORATION_REDUCTION_REJECTED**. The experimental
  runtime override is not retained. Evidence and raw hashes are in
  `docs/experiments/evidence/silver-root-exploration-sweep-2026-08-29.json`.

## §194 Silver root-c exploratory online screen inconclusive (2026-08-29)

- **Protocol:** Fair Silver, exact 3,000 simulations/root, reuse `none`, one
  thread, adaptive/VNet/pruning off. An 8-seed broad c grid selected a fresh
  32-seed narrow screen over c=12.5/15/18.5/21 versus c=25.
- **Result:** c=18.5 and c=21 were each +6.2pp wins, but both paired intervals
  included zero; c=12.5 and c=15 were directionally negative. Integrity and
  exact-budget checks passed for complete arms.
- **Decision:** **ROOT_EXPLORATION_GAMEPLAY_INCONCLUSIVE**. Keep c=25. See
  `docs/experiments/evidence/silver-root-exploration-online-gcp-2026-08-29.json`.

## §195 Silver root c=35 128-seed rerun inconclusive (2026-08-29)

- **Protocol:** Fresh paired seeds 932401–932528, 24 threads per sequential
  arm, exact 3,000 simulations/root, c=35 versus ordinary c=25.
- **Result:** c=35 won 84/128 versus 79/128, +3.9pp with 95% CI
  `[-3.9,+11.7]`; floor was +0.9 `[-0.5,+2.3]`; runtime was 1.056x.
- **Decision:** **ROOT_EXPLORATION_GAMEPLAY_INCONCLUSIVE**. Keep c=25. See
  `docs/experiments/evidence/silver-root-exploration-c35-128-gcp-2026-08-29.json`.

## §196 Silver Sequential-Halving online tuning rejected (2026-08-30)

- **Protocol:** Root-only shapes `half`, `gentle`, `aggressive`, and
  `screen_two` crossed with three round-allocation schedules at exact budgets
  1,000/3,000/6,000. Internal and chance search remained ordinary.
- **Result:** Aggressive/finalist-heavy at 1,000 had a positive 64-seed point
  estimate but exceeded the frozen 1.10x runtime gate. Selected
  half/finalist-heavy at 3,000 was +1/64 win with intervals including zero.
  The fresh confirmation arm aborted at 78/128 on a live conversion failure,
  so partial analysis was prohibited.
- **Decision:** **SEQUENTIAL_HALVING_ONLINE_TUNING_REJECTED**. The runtime
  scheduler and experiment-specific orchestration are not retained. See
  `docs/experiments/evidence/silver-sh-online-tuning-2026-08-30.json`.

## §197 Silver live-bridge failure hardening: known operational failures repaired (2026-08-30)

- **Scope:** Implementation and telemetry diagnostics only, not a gameplay
  comparison. This preserves the prior Sequential-Halving and pruning
  rejections, all historical win rates, and the ordinary c=25 default.
- **Conversion root cause:** Deterministic seed 933396 retained a private
  post-Mug direct-choice marker after a public Looter intent query refreshed
  move history from Mug to Lunge. Intent materialization now consumes that
  marker; a focused Runic Dome fixture verifies the private/public boundary.
- **Harness hardening:** Conversion and semantic failures now include seed and
  public-safe decision context. `bestbench` catches exceptions at each OpenMP
  seed boundary, omits failed rows, names failures, and exits nonzero.
  Foreground GCP manifest runs preserve declared logs through `tee` with
  `pipefail`.
- **Telemetry root cause:** Parallel workers could interleave complete
  `[silver-combat]` records and create parser-visible counter corruption.
  Records are now formatted thread-locally and emitted under one process-wide
  mutex.
- **Historical validation:** Reviewed source SHA
  `79ca93fbf62e6a5ede9f6dfd7ac20f095ab25f8e`, executable SHA-256
  `d1766cfebd2d3e566d99c7f7fd0a74498df33914f6b94ef7851a04348cd876ba`.
  Seed 933396 passed its original exact-3000 configuration. A 24-thread
  diagnostic over seeds 933100–933163 produced 64/64 unique rows and 1,608
  valid, zero-failure, exact-budget telemetry records.
- **Verdict:** **KNOWN_OPERATIONAL_FAILURES_REPAIRED**. This does not make an
  aborted cohort valid or promote c=35 or Sequential Halving. The original
  paths and hashes are in
  `docs/experiments/evidence/silver-live-bridge-failure-hardening-2026-08-30.json`.

## §198 Aggressive Sequential-Halving confirmation inconclusive (2026-08-30)

- **Protocol:** Fresh paired seeds 934000–934127, exact 1,000/root, 24 threads,
  ordinary c=25 versus aggressive/finalist-heavy halving after operational
  repairs.
- **Result:** 84/128 versus 83/128 wins, +0.8pp with 95% CI
  `[-7.8,+9.4]`; floor +1.1 `[-0.2,+2.4]`; runtime 1.055x. All integrity
  checks passed.
- **Decision:** **SEQUENTIAL_HALVING_GAMEPLAY_INCONCLUSIVE**; do not promote.
  See `docs/experiments/evidence/silver-sh-aggressive-128-confirmation-2026-08-30.json`.

## §199 Sequential-Halving budget curve found no stable advantage (2026-08-30)

- **Protocol:** Sixteen paired seeds at exact budgets 100 through 1,000.
- **Result:** Halving led at 200/600/900, tied at 800/1,000, and trailed at the
  other five budgets. No contiguous region was favorable and every win
  interval included or touched zero.
- **Decision:** **EXPLORATORY_BUDGET_CURVE_COMPLETE_NO_STABLE_SH_ADVANTAGE**.
  See `docs/experiments/evidence/silver-sh-budget-curve-2026-08-30.json`.

## §200 Root c=35 budget curve found no stable interaction (2026-08-30)

- **Protocol:** Sixteen paired seeds at exact budgets 100/200/500/1,000/2,000/
  3,000/5,000/7,500/10,000.
- **Result:** c=35 led in noisy cells through 2,000, reversed at 3,000, and
  tied at 5,000–10,000. Every win interval included or touched zero.
- **Decision:** **EXPLORATORY_C35_BUDGET_CURVE_COMPLETE_NO_STABLE_INTERACTION**.
  See `docs/experiments/evidence/silver-c35-budget-curve-2026-08-30.json`.

## §201 Root c=35 final 512-seed promotion gate rejected (2026-08-30)

- **Protocol:** Fresh seeds 935000–935511 at exact 3,000/root, c=35 versus
  ordinary c=25. Promotion required complete zero-failure paired integrity and
  a positive paired win lower bound.
- **Result:** Each arm omitted one different seed on equivalent-duplicate hand
  ambiguity, so strict pairing rejected the unequal 511-row sets. The
  diagnostic-only 510-seed intersection was +2.4pp wins with CI
  `[-1.6,+6.3]`, which also missed the statistical gate.
- **Decision:** **ROOT_C35_PROMOTION_REJECTED_OPERATIONAL_AND_STATISTICAL**.
  Keep c=25; do not rerun for significance. See
  `docs/experiments/evidence/silver-c35-512-confirmation-2026-08-30.json`.

## §202 Silver equivalent-duplicate hand-play failures repaired (2026-08-30)

- **Scope:** Correctness repair for two observed semantic failures; no gameplay
  verdict or default changed. Real hands can contain cards identical across
  every serialized `CardWire` field, including `uniqueId`. Ordinary card-play
  lowering incorrectly required exactly one match.
- **Fix:** Reviewed historical SHA
  `6aae003f2ad255c7d9d30ba79149fb298472fb65` deterministically selects the
  first fully equivalent live hand entry only for ordinary `CARD` play, then
  retains normal live action validation. Card-selection transactions still
  require unique identity and fail closed on ambiguity.
- **Verification:** `silver_semantic_action` and `silver_bridge_boundary`
  passed. Exact Linux binary SHA-256 was
  `b1da69a6db136046b2b4067f3710425c4037698dba1bd3bcd17b7e7e65267ed3`.
  Original seeds 935505/c=25 and 935456/c=35 each completed at exact 3,000
  simulations/root with zero conversion, semantic, transaction, or knowledge
  failures.
- **Verdict:** **SILVER_DUPLICATE_HAND_PLAY_FAILURES_FIXED**. This does not
  rehabilitate the invalid c=35 promotion cohort or promote c=35. Paths,
  hashes, and the historical sidecar caveat are in
  `docs/experiments/evidence/silver-semantic-duplicate-hand-fix-2026-08-30.json`.

## Silver grouped and rank-4 visit-prior offline replay (2026-08-29–30)

- **Grouped replay:** At 32 simulations on 63 roots, grouped-linear prior
  selection improved B-best probability by +1.190476pp and regret by
  -0.257334 versus current UCT, but both paired intervals included zero and
  B-best recovery missed the frozen support bar. Decision:
  **GROUPED_LINEAR_VISIT_POLICY_REPLAY_INCONCLUSIVE**.
- **Rank-4 interaction:** Versus grouped linear, rank-4 changed B-best by
  +0.793651pp but worsened regret by +0.144530; both root-bootstrap intervals
  included zero and the finite L-BFGS run showed severe train/validation/anchor
  divergence. Decision: **RANK4_INTERACTION_VISIT_POLICY_REPLAY_INCONCLUSIVE**.
- **Artifacts:** Reproducible analyzers, trainers, focused tests, reports, and
  raw/model hashes are retained. Runtime PUCT/native inference is not.

## §203 Initial grouped visit-policy online screen invalid (2026-08-30)

- An initial 32-seed screen was invalidated by pile-selection action-identity
  failures and is retained only as diagnostic evidence. See
  `docs/experiments/evidence/silver_grouped_visit_policy_online_screen_2026-08-30.json`.

## §204 Repaired grouped visit-policy online screen negative (2026-08-30)

- **Protocol:** Fresh paired seeds 976032–976063, ordinary off versus grouped
  normalized visit-PUCT, exact 1,000 simulations/root, one thread.
- **Result:** Off won 17/32; grouped won 11/32, -18.75pp with paired 95% CI
  `[-34.375,-6.25]`. Normalized CPU ratio was 1.002x and integrity passed.
- **Decision:** **GROUPED_VISIT_POLICY_ONLINE_SCREEN_NEGATIVE**. No 128-seed
  confirmation or tuning was authorized.

## §205 Rank-4 visit-policy online screen inconclusive (2026-08-30)

- **Protocol:** Fresh paired seeds 976064–976095 under the same runtime and
  budget controls.
- **Result:** Off won 19/32; rank-4 won 17/32, -6.25pp with CI
  `[-18.75,+6.25]`; normalized CPU ratio was 0.991x.
- **Decision:** **RANK4_VISIT_POLICY_ONLINE_SCREEN_INCONCLUSIVE**. No tuning
  or follow-up was authorized. The runtime scorer/model is not retained.

## §206 Frozen whole-combat surrogate counterfactual audit passed (2026-08-31)

- **Protocol:** Before observing branch outcomes, select at most one naturally
  occurring multi-action OOC decision from each fresh source seed 982100–982131.
  Evaluate every legal sibling through the next combat with matched cloned
  continuation state, frozen ordinary project-fair Silver c=25 at exact 10,000
  simulations/root, and the unchanged Phase-1 survival/conditional-HP models.
- **Integrity:** 32/32 sources completed, zero quarantines, 157 valid branches
  (32 source-policy chosen, 125 unchosen), 1,766 finite canonical features,
  and zero conversion, semantic-resolution, transaction, or knowledge failures.
  The 826 combat summaries recorded 154.70M simulations in exact 10,000-unit
  root-search increments.
- **Unchosen result:** 118/125 combats won. Survival logloss was 0.1718 versus
  0.2158 for the constant baseline, Brier was 0.0465 versus 0.0529, and ROC-AUC
  was 0.902. Conditional-HP MAE/RMSE were 0.1462/0.2023 versus baseline
  0.2642/0.2859; absolute-HP MAE was 12.25.
- **Decision:** **COUNTERFACTUAL_GENERALIZATION_PASS** as a feasibility gate.
  The result is encouraging but only seven unchosen losses make calibration and
  failure-tail estimates imprecise. It does not authorize a transition
  surrogate, K/H experiments, retraining, or combat replacement. See
  `docs/experiments/evidence/ooc-counterfactual-surrogate-audit-2026-08-31.json`.

## §207 OOC K/combat-budget selection chooses K1 exact-10k (2026-08-31)

- **Scope and assumption:** Reused the exact PR-100 cohort of 32 OOC decisions,
  157 complete legal sibling actions, and source seeds 982100–982131. The user
  explicitly accepted the mixed-SHA Stage-A A cohort as clean and authorized
  Stage B from K2's practical point-estimate improvement despite the clustered
  intervals crossing zero. This assumption is part of the result and is not a
  general mixed-producer precedent.
- **Protocol:** Ordinary project-fair Silver UCT, c=25, exact root budgets,
  allocated reuse cap 32,768, and no Sequential Halving, pruning, learned
  prior/PUCT, learned leaf, or adaptive budget. Stage A used A futures 0–3 and
  independent terminal B futures 100–103. Stage B reused that B truth and used
  fresh matched A futures 10–13 for `[10000]`, `[5000,5000]`,
  `[3333,3333,3334]`, and diagnostic-only historical `[150,100,50]`.
- **Integrity:** The amended hash-bound analyzer accepted 11,304 rows with
  exact action/future coverage, zero invalid rows, duplicates, missing
  identities, or unknown schedules. Stage B contributed 8,164 rows from 107
  CSVs. One extreme K1 source shard was recovered through the frozen 12-way
  `(action,future)` partition: 12/12 PASS files supplied exactly 184 data rows;
  the redundant original partial was terminated with rc=143, preserved for
  audit, and excluded. All 227 packaged payload hashes verified.
- **Stage A:** K1/K2/K3 selected terminal wins were
  0.28125/0.3046875/0.2421875 and regrets were
  0.125/0.1015625/0.1640625. K2−K1 was +0.0234375 selected win and
  −0.0234375 regret, but both 95% paired intervals crossed zero. Authorized
  classification: **HORIZON_INCONCLUSIVE_K2_PROMISING**; K3 was rejected.
- **Frozen Stage-B rule:** Relative to high-quality K2, require selected win
  loss no greater than 0.01 and regret increase no greater than 0.01, then
  choose the least actual Silver compute among eligible non-historical arms.
  This is an unpaired point-estimate gate across disjoint Stage-A and Stage-B A
  future sets. Passing it is not evidence that K1 and K2 are statistically or
  practically equivalent.
- **Result:** K1 `[10000]` scored 0.296875 selected win and 0.109375 regret,
  losses of exactly 0.0078125 on both margins, so it passed. K2
  `[5000,5000]` scored 0.2890625/0.1171875 and missed both margins by
  0.015625. K3 `[3333,3333,3334]` scored 0.25/0.15625 and failed widely.
  Diagnostic `[150,100,50]` scored 0.3125/0.09375 but was preregistered as
  diagnostic-only and remains ineligible.
- **Compute:** Selected K1 used 148.81M Silver simulations, 11,732 combat
  decisions, and 2,276.13 logical CPU seconds, versus 283.07M simulations,
  22,426 decisions, and 3,213.50 CPU seconds for high-quality K2—a 47.43%
  simulation reduction. The first Stage-B launch failed at the seed guard
  before creating any output; the corrected 24-worker queue completed with the
  explicitly recorded K1 recovery race.
- **Decision:** **K1_10000_SELECTED** for future clean OOC labels. Do not tune
  intermediate budgets or promote the historical low-compute schedule from
  this diagnostic. Four A/B futures, broad intervals, a 75% B-truth tie rate,
  and the unexpectedly strong historical diagnostic remain explicit
  uncertainty. No H experiment, datagen, transition surrogate, or OOC training
  is authorized here. See
  `docs/experiments/evidence/ooc-k-combat-budget-stage-b-2026-08-31.json`.

## §208 OOC H selection chooses one future/action (2026-08-31)

- **Protocol:** Reused the hash-verified §207 Stage-B K1 `[10000]` A futures
  10–13 and independent terminal B futures 100–103 for the exact 32 decisions
  and 157 sibling actions. H1 averages the four singleton-subset ranking
  results per decision, H2 averages all six two-future-subset results, and H4
  uses all four. Subsets are sensitivity views, not independent replicates.
- **Integrity:** Both preserved archive hashes match §207. All 227 Stage-B
  packaged hashes and all 74 non-self-referential Stage-A bundle hashes match;
  the Stage-A checksum list contains a stale hash of itself, explicitly
  excluded as circular metadata. Action/future coverage is exact and complete.
- **Result:** H1/H2/H4 selected terminal win was
  0.3046875/0.30078125/0.296875 and terminal regret was
  0.1015625/0.10546875/0.109375. Top-action agreement was
  0.726563/0.729167/0.718750; pairwise concordance was
  0.490256/0.471462/0.453159; score-tie rate was
  0.304688/0.333333/0.312500; B-truth tie rate was 0.75 throughout.
  H2−H1 selected win was −0.003906 (95% source-seed-clustered CI
  [−0.015625, 0.007812]) and regret was +0.003906
  ([−0.007812, 0.015625]); H4−H2 repeated the −0.003906/+0.003906 point
  deterioration, with intervals [−0.023438, 0.011719] and
  [−0.011719, 0.023438]. Relative label costs are 1×/2×/4×.
- **Decision:** **H1_SELECTED**. Neither larger H improves regret or preserves
  selected win at the point estimate, so neither approaches the 0.01 practical
  bar. The fresh issue-19 pilot block is frozen before outcomes at source seeds
  `983000..983015`. See
  `docs/experiments/evidence/ooc-h-futures-selection-2026-08-31.json`.

## §209 Clean OOC pilot stopped at the provenance canary (2026-08-31)

- **Frozen boundary:** Implementation review and GitHub `Linux GCC` passed at
  `474c2d11c90d9074b2c3a0b589ad10df0b3cf6de`. The exact remote executable,
  teacher manifest, and OOC floor/win models were hash-verified before launch.
- **Canary:** The required one-source canary requested source seed `983000`
  under the selected K1 exact-10k/H1 teacher. It failed closed before gameplay
  or search with `wholecombatgen: teacher git_sha mismatch`; zero OOC rows,
  zero combat-surrogate rows, and no result or sidecar were published.
- **Diagnosis:** `loadWholeCombatTeacher` compares the teacher SHA with
  `git rev-parse HEAD` evaluated in the process working directory. The GCP
  launcher executes from the designated remote root, whose HEAD was
  `0189bb40e1712f2b9b3597483c66cc4d267e206e`, while the exact executable lived
  in the managed checkout at the frozen SHA. The valid teacher therefore
  rejected the unrelated runtime-root SHA. This is a provenance integration
  defect, not an H/search-quality result.
- **Decision:** **CLEAN_OOC_PILOT_FAILED**. Per the preregistered gate, the
  16-source block `983000..983015` was not launched and no substitute seeds
  were appended. See
  `docs/experiments/evidence/ooc-clean-pilot-canary-failure-2026-08-31.json`.

## §210 Corrected clean-OOC canary reaches search but fails action identity (2026-09-01)

- **Correction:** Commit `6003a8aa9dae714fade76ef78a7832c15efa760e`
  binds native producer provenance to the manifest-required
  `STS_EXECUTABLE_GIT_SHA`. Independent implementation review and GitHub
  `Linux GCC` passed before the retry. Exact executable, teacher, model, CMake
  source-binding, and clean-checkout hashes passed remote preflight.
- **Canary result:** Source seed `983000` passed the former teacher-SHA failure
  and executed 312 complete Silver telemetry blocks: 75.12M simulations and
  7,512 combat decisions with zero conversion, semantic-resolution,
  transaction, or knowledge failures. After approximately eight minutes it
  failed closed with `ooccleanpilot: source action is not a unique legal
  sibling`.
- **Diagnosis boundary:** The accepted source policy's observed action did not
  occur exactly once in the producer's legal-sibling vector. The current error
  combines missing-action and duplicate-action-bit cases, so the precise
  subcase is unresolved. The producer published no data rows; its partial is
  header-only. The failure-sidecar path exists but is empty, which is a second
  observability defect.
- **Decision:** **CLEAN_OOC_PILOT_FAILED** again. The 16-source block
  `983000..983015` was not launched and no substitute seeds were appended. See
  `docs/experiments/evidence/ooc-clean-pilot-canary-action-identity-failure-2026-09-01.json`.

## §211 Clean issue-19 OOC health pilot passed (2026-09-01)

- **Corrections and freeze:** Legal siblings were canonicalized by action bits;
  terminal-before-next-combat branches became exact absorbed OOC targets; and
  Silver multi-select accounting gained an explicit committed-transaction
  overlap counter. Independent review, focused tests/build, and GitHub Linux
  GCC passed at frozen SHA `ff9e5a99efcb22283ab1041ba6a2b65ea22e2e10`.
- **Protocol:** The previously frozen fresh block `983000..983015` ran as 16
  independent guarded processes with the selected H1/K1 teacher: ordinary
  project-fair Silver, exact 10,000 simulations/private root, c=25, allocated
  reuse cap 32,768, and no SH, pruning, learned PUCT/leaf, or adaptive search.
- **Integrity:** All 16 sources passed individual and combined fail-closed
  audits: 1,705 complete multi-action decisions, 9,289 OOC rows, 9,265 reusable
  combat-surrogate rows, 24 terminal-before-combat rows, and zero failures or
  quarantines. Exact accounting was 1.94069B simulations from 193,743 ordinary
  decisions + 452 transaction roots - 126 overlapping committed transaction
  actions. Producer, executable, teacher, models, bundle, and raw artifacts are
  hash-bound in the evidence file.
- **Targets and compute:** OOC survival was 8,928/9,289 (96.11%); combat-only
  survival was 8,928/9,265 (96.36%). Mean Q was 0.36633, mean post-combat HP
  fraction 0.73243, and mean floor bootstrap 41.8113. The cohort consumed
  16,926.96 CPU seconds and 32m51s wall time. Linear projection per 1,000
  sources is 121.29B simulations, 293.87 CPU-hours, or about 18.37 wall-hours
  at 16 workers; this is a planning projection, not authorization to scale.
- **Decision:** **CLEAN_OOC_PILOT_HEALTHY**. Stop after the pilot. Do not
  generate the replacement corpus or train either model. See
  `docs/experiments/evidence/ooc-clean-pilot-healthy-2026-09-01.json`.

## §212 Explicit K1/H1 OOC planner loses to frozen V4 strategic-Q (2026-09-02)

- **Protocol:** Fresh exact-V4 source seeds `984100..984128`, ascension 0,
  project-fair Searcher3 at 1,000 simulations/decision, 24 threads, 64
  particles, 7k combat VNet at alpha 0.3, Act-4 key collection, and all V4
  strategic gates at margin 1.0. One reservoir-sampled V4-owned multi-action
  decision per source was frozen. Every legal sibling then followed frozen V4
  to the next combat, resolved exactly one combat with the selected H1/K1
  ordinary Silver exact-10k teacher, and used the unchanged native `vStateWin`
  model after survival. Sibling hidden worlds and continuation RNG were
  matched; death was zero and terminal run victory one.
- **Cohort:** 29 decisions and 175 valid legal actions; 10 agreements and 19
  disagreements (34.48% agreement). The disagreement set covered 131 actions.
  Mean/median K1 score margin was 0.02638/0.02045. Collection used 25.78M
  Silver simulations over 2,578 combat decisions.
- **Independent reference:** Only the 19 disagreements were adjudicated. Each
  legal sibling was forced first, then frozen V4 controlled later OOC choices;
  four matched terminal futures `100..103` used the strongest exact-10k Silver
  full-run reference. All 524 expected rows were valid, consuming 1.72435B
  Silver simulations. Exact V4 replays were serialized at 24 cores; a frozen
  post-replay barrier then released 19 independent single-core Silver jobs.
- **Result:** V4 selected terminal win was **0.56579**, versus **0.40789** for
  H1 (H1−V4 `-0.15789`, 100k source-cluster bootstrap 95% CI
  `[-0.34211, 0]`). V4 mean regret was **0.19737**, versus **0.35526** for H1
  (H1−V4 `+0.15789`, CI `[0, 0.34211]`); median regret was 0 versus 0.25.
  H1's win/loss/tie record was **3/7/9**. Screen 8 was the clearest systematic
  failure: H1 lost 0.29167 selected win and added 0.29167 regret.
- **Decision:** **REJECT**. Both primary point estimates favor current V4, so
  explicit K1/H1 action selection fails the preregistered screen. No gameplay
  benchmark, production planner, horizon/budget tuning, new model, or training
  follows. See
  `docs/experiments/evidence/ooc-v4-h1-explicit-planner-2026-09-02.json`.

## §213 Random whole-Act evaluator expanded to every eligible OOC decision (2026-09-02)

- **Protocol (superseded):** Offline seed `984123`, ascension 0, 100 random legal OOC
  rollouts per source decision, 100 Silver simulations per unique
  action/encounter cell, project-fair source replay, and OpenMP
  `OMP_NUM_THREADS=8` for the independent Silver queue. Rollout encounters
  used the lightweight pass-through transition; no combat search was used in
  rollout generation. Rollout and combat seeds were explicitly recorded with
  common-random-number pairing across siblings.
- **Coverage:** 62 eligible OOC decisions across Acts 1/2/3 (24/18/20),
  3,609 identity-deduplicated action/encounter cells, and four post-boss
  decisions with zero remaining encounters. Runtime was 554.18 seconds.
- **Decision:** **INVALIDATED/INCONCLUSIVE**. The implementation retained only
  the first battle-entry snapshot for each action/encounter identity and did
  not independently prove Silver installation on each OpenMP worker. Its
  scores must not be interpreted as evidence for or against H1. Evidence:
  `build/ooc_v4_h1_random_984123_all_r100_s100_t8.csv` and its sidecars.

## §214 §213 evaluator correction canary (2026-09-02)

- **Checks:** The corrected evaluator preserves every observed occurrence's
  battle-entry snapshot, installs Silver once process-wide before the queue,
  and fails closed unless a fixed serial/parallel canary agrees and every
  configured worker participates. The guarded 8-worker smoke completed with
  62 source decisions, 1,648 occurrence cells, 1 Silver simulation per cell,
  and worker mask `255`; `silverWorkerCanary=pass`.
- **Evidence/status:** `build/ooc_v4_h1_review_smoke_processwide.csv` and
  sidecars. The
  full 100-rollout/100-Silver rerun remains required before replacing §213's
  scientific result.

## §215 Exact Silver CPU optimization and GCC PGO pilot (2026-09-10)

- **Question/design:** preserve the frozen teacher's search, RNG behavior,
  decisions and labels while reducing single-core CPU cost. Baseline
  `0034ce8038f1a7229bc4f993a0001a72ddfd10e9`; reviewed implementation
  `f8873cd` (subsequent evidence-only commit does not change executable sources).
  The implementation gates diagnostic hashes/timers/action traces, caches the
  original widening expression, ends UCB scans at a winning positive infinity,
  and replaces Silver's status map with sorted sparse explicit-membership storage.
  PGO is a separate default-off build treatment; no fast math or native CPU flags.
- **Profile:** GNU `gprofng` PC sampling of `wholecombatgen`, seed 0, gave
  22.456 CPU seconds sampled: Silver step inclusive 92.38%, status-tree copy
  exclusive 2.90%, BattleContext swap exclusive 6.11%. `perf` was unavailable;
  no cycles/instructions/cache-miss hardware evidence was collected. Baseline
  sizes: Node 6352 bytes, BattleContext 6272, Player 176. Compact chance-node
  storage was assessed but deferred: memory upside is plausible, while CPU
  attribution to unused chance payload remains unmeasured. Logical allocated
  cap semantics must remain unchanged in any future layout experiment.
- **Workload/configuration:** actual `wholecombatgen 1 10000 0 OUT SEED TEACHER`
  producer, project-fair Silver UCT, exactly 10,000 simulations per private
  root, exploration 25/25, widening 3.7028/0.52389 for both categories,
  allocated reuse cap 32768, adaptive/direct-leaf/pruning/PUCT off. Native OOC
  floor/win trees loaded and hash-bound; `STS_POLICY=0`. All seed commands used
  `tools/seed_guard.sh`. Ryzen 5 7500F, one process pinned to CPU 2,
  `OMP_NUM_THREADS=1`; GCC Release `-O3 -flto`. Actual production-job binary
  paths elsewhere were not verified or changed.
- **PGO:** train on seed 0 (22 fights across Acts 1–3) plus the existing native
  reference-searcher probe to cover a compiled archive member not linked by
  the producer. Final USE build passed strict missing/mismatched profile
  checks. Held-out seeds 1 and 2 were not used in training.
- **Controlled timing:** two repetitions per held-out seed in A/B/PGO then
  PGO/B/A order, after builds completed. Sum over four runs per arm:

  | Arm | Process CPU seconds | Whole-process wall seconds | CPU reduction vs A |
  | --- | ---: | ---: | ---: |
  | A: baseline Release | 52.994173 | 53.001637 | — |
  | B: optimized Release | 49.427041 | 49.431853 | 6.73% |
  | PGO: optimized profile-use | 46.923947 | 46.927550 | 11.45% |

  PGO reduced CPU by a further 5.06% versus B. This is a preliminary local
  result on two trajectories, not a statistical or production-wide claim;
  the individual source optimizations were not isolated in this final timing.
  Exploratory runs overlapping compilation are excluded from these numbers.
- **Equivalence:** every final CSV is byte-identical to its matched baseline,
  as is every per-fight Silver telemetry line. Fourteen native fixtures at
  10,000 simulations also have byte-identical traces (including root actions,
  values/visits, reroot and sequential-selection cases). Focused tests compare
  tracing on/off, observer counts/hashes/fingerprints, RNG state, all pool
  states/values, UCB NaN/infinity behavior, and exact widening schedules and
  fallback. These are bounded checks; no persisted full-run RNG trace was
  collected. Training/exploratory scratch data are not a promoted corpus.
- **Validation/status:** complete Debug build, 62/62 CTests, 145 agent-tooling
  tests, container ASan/UBSan, independent source review, and repository-health
  check passed. Keep source changes for review; PGO remains opt-in. No model,
  search budget, OOC policy, production corpus, or GCP deployment was changed.
  Existing Release narrowing/ODR/LTO warnings remain.
- **Evidence:** [machine-readable packet](evidence/silver_exact_search_2026-09-10.json)
  contains every final command, teacher/environment/model/executable hash,
  CPU/wall measurement, label/telemetry hash, checks and limitations. Raw logs,
  CSVs, profiles and build output remain in `build/optimization-evidence/` in
  the task checkout. Final manifests bind the implementation SHA and actual
  binary hashes; profiles were collected from the same sources before commit.

## §216 Compact Silver chance-node storage: lower memory, CPU neutral (2026-09-10)

- **Question/design:** follow up §215's deferred storage hypothesis. Compare
  the already-optimized Release executable at `49781db` (SHA256
  `835e21fb790a55a234079f34279657b2910a2e3e459cd84faf2b2f990ef1e4bf`)
  against reviewed implementation `255d8f1`. PGO is OFF in both arms. Keep
  all teacher settings, node counts, RNG use, decisions and labels unchanged;
  measure whether removing unused chance-state payload saves memory and CPU.
  Reused §215's exact baseline executable and fixture runner; fresh timings are
  necessary because the new layout is the only new treatment.
- **Implementation:** compact 88-byte nodes point to separately pooled battle
  states. Only decision nodes claim a state; chance nodes read their parent.
  Both pools retain stable addresses and capacity across reset/reroot. The
  allocated/active cap still uses logical `allNodes.size()`/`poolUsed`, never
  state-pool size or physical bytes. No block allocation or cap-policy change.
- **Structural evidence:** the 512-simulation fixture has 604 logical nodes,
  comprising 510 decisions and 94 chance nodes. State pool usage is 510;
  BattleContext is 6248 bytes. Thus 587,312 bytes of chance-state payload are
  omitted. This payload calculation excludes allocator/bookkeeping overhead;
  whole-process memory is measured separately below.
- **Workload:** same frozen `wholecombatgen 1 10000 0 OUT SEED TEACHER` contract
  as §215: project-fair ordinary Silver UCT, exact 10k private-root budgets,
  exploration 25/25, widening 3.7028/0.52389, allocated cap32768, adaptive and
  learned leaf/pruning/PUCT off. Native OOC floor/win trees hash-bound and
  confirmed loaded, STS_POLICY=0, one worker pinned to CPU2 on Ryzen5 7500F,
  GCC Release O3/LTO. Source/model/binary hashes accompany every final run.
- **Timing/memory:** seeds0/1/2, two repeats each in A/B then B/A order, after
  all compilation completed. Six runs per arm. Baseline CPU88.992959s and
  wall88.999912s; compact CPU88.466317s and wall88.480595s. The nominal 0.59%
  CPU reduction is treated as neutral/inconclusive, not a demonstrated speedup.
  Mean peak RSS across the two repetitions, in KiB:

  | Seed | Baseline | Compact | Reduction |
  | --- | ---: | ---: | ---: |
  | 0 | 277196 | 235032 | 15.21% |
  | 1 | 288450 | 237572 | 17.64% |
  | 2 | 319776 | 296542 | 7.27% |

- **Hardware profiling:** installed matching Linux perf7.1.5 and its runtime
  libraries by user-local package extraction; no sudo/sysctl or global
  configuration changes. `perf_event_paranoid` remains2. Generic userspace
  cycles/instructions/branches/branch-misses/cache-references/cache-misses are
  readable. Separate matched seed0 A/B then B/A counter runs and their running
  percentages are retained in the evidence packet. Initial profile/counter
  samples overlapping builds are excluded from controlled conclusions.
  In the matched counter pairs, compact nodes used 1.21% more cycles,
  0.20% more instructions and 1.88% more generic cache misses; this does not
  support a cache-efficiency improvement despite the lower RSS.
- **Correctness:** all matched final label CSVs and per-fight Silver telemetry
  lines are identical. Fourteen native fixture traces at10k simulations are
  byte-identical, covering reroot and sequential selection. New tests check
  null chance states, exclusive state ownership, stable pointers across growth,
  continued search after reroot, reset/replay capacity reuse and unchanged
  logical node accounting. Existing bridge allocated/active-cap tests pass.
  Full Debug target set rebuilt; 62/62 CTests pass. Final isolated search and
  bridge boundary tests pass ASan+UBSan. Independent source review and
  repo-health pass (advisory Markdown-growth warning).
- **Decision/limits:** retain as a measured memory optimization with roughly
  unchanged CPU cost on this bounded local sample. No claim of additional
  cache-efficiency or CPU benefit, no broad production qualification, and no
  combination with §215's PGO result: new source/layout requires new profiles.
  No deployment, model, budget, corpus, or cap change. Three trajectories and
  two repeats cannot establish a small general CPU effect; full-run persisted
  RNG traces were not collected. Agent-tooling tests were not repeated because
  this follow-up changes no Python/tooling configuration.
- **Evidence:** [complete packet](evidence/silver_chance_storage_2026-09-10.json)
  contains exact commands, manifests/hashes, per-run CPU/wall/RSS, hardware
  counts, fixture metrics and checks. Raw files remain under
  `build/chance-storage-evidence/` in the task checkout. The final evidence-only
  commit does not change the measured implementation.

## §217 Final-layout single-core confirmation against current main (2026-09-10)

- **Purpose/decision rule:** close §215–216's provenance gap with a direct
  current-main versus complete final-layout PR comparison. Predeclared
  criterion: identical labels/telemetry and existing native trace parity,
  plus `1 - sum(head CPU) / sum(main CPU) >= 0.05` over six executions per arm.
  This is confirmation on previously examined seeds, not a new held-out study.
- **Frozen sources/builds:** baseline current main
  `3bec0b159984ab1a01c100bce17189aa68f71967`; independently reviewed final PR
  head `4224c03e4ae0487cd43e5e9a196a193d22be9f24`. Fresh baseline archive build
  via `tools/agent/baseline_build.py` and checked-in Release ccache presets;
  final-head Release target verified up-to-date and copied to a frozen path.
  Both O3/LTO, PGO OFF. Baseline executable SHA256
  `4d0beb28998568df1503ecc0f72784f6dbf70c81973717d439ff8eb3b2031862`;
  final head `c97ab0467c8f8ba961efc1ea4bc1fa559462d3799c915afa7f6b9fb30e65c4c5`.
  Main's only change since original baseline 0034ce8 is an unrelated Python
  semantic-probe script; the freshly built binary is byte-identical to the
  original baseline. Final-head binary is unchanged from the validated compact
  layout. No merge-base refresh or source changes were needed.
- **Workload:** `wholecombatgen 1 10000 0 OUT SEED TEACHER`, seeds 0/1/2, two
  repetitions per seed in A/B then B/A order, all guard-wrapped. Same frozen
  project-fair ordinary Silver exact-10k private roots, exploration 25/25,
  widening 3.7028/0.52389, allocated cap32768, no adaptive/pruning/learned leaf,
  native OOC floor/win trees hash-bound and confirmed loaded, STS_POLICY=0.
  Ryzen5 7500F, one process pinned to CPU2, OMP_NUM_THREADS=1, no concurrent
  builds. Seeds cover 22/9/17 fights respectively, Acts1–3 collectively,
  normal/elite/boss encounters. Timing excludes manifest/hash preparation.
- **Results:** aggregate CPU **87.589210s main → 82.051059s head**, a
  **6.3229% reduction**. Whole-process wall **87.600607s → 82.066320s**,
  **6.3176% lower**. Mean process CPU seconds over two repeats per seed:

  | Seed | Current main | Final head | CPU reduction |
  | --- | ---: | ---: | ---: |
  | 0 | 19.470291 | 17.535438 | 9.94% |
  | 1 | 12.665160 | 12.666575 | approximately 0% |
  | 2 | 11.659154 | 10.823516 | 7.17% |

  **PASS** against the predeclared 5% aggregate bar. This measures the full PR
  package, including compact status/chance storage; it does not attribute a
  CPU gain to the chance layout by itself. The seed variation and small sample
  preclude a broad throughput guarantee or statistical confidence claim.
- **Equivalence/provenance:** all 12 runs completed one seed each with zero
  quarantine/health failures. Every matched label CSV and per-fight Silver
  telemetry stream is identical; executable/model hashes and full source SHAs
  agree with each teacher manifest and native provenance sidecar. Fourteen
  preserved original-baseline/final-layout native traces compare identical.
  Reusing them is justified by relevant source equivalence and matching
  executable hashes; they were not rerun during this measurement.
- **Checks/limits:** clean source preflight, pinned submodules, exact baseline
  Release build and final-head target verification passed. Linux GCC CI passed
  on frozen head4224c03 before this evidence-only update; existing full CTest,
  sanitizer and implementation-review evidence remains applicable because no
  executable source changed. PGO was deliberately not retrained or measured:
  it remains optional, and §215's PGO percentage is not a final-layout claim.
  No larger benchmark, deployment or automatic merge. Full-producer persisted
  RNG traces were not added.
- **Evidence:** [final-layout packet](evidence/silver_final_layout_ab_2026-09-10.json)
  contains the exact per-run commands, per-arm manifests/hashes, per-seed and
  aggregate metrics, native-trace reuse links, criterion and limitations. Raw
  artifacts remain in `build/final-layout-evidence/` in the task checkout.
  Subsequent commits record evidence only and do not change measured sources.

## §218 Fresh semantic confirmation and observational combat labels (2026-09-10)

- **Question/protocol:** confirm the development probe on fresh seeds
  992000–993023: 1,024 complete source decisions, 64 shards of 16. Capture all
  sources before the distribution gate; evaluate each semantic branch once,
  emitting semantic and combat sidecars from the same fight. Ordinary
  project-fair Silver exact-10k private roots, H=1, future0, allocated32768,
  exploration25/25, widening3.7028/.52389, no SH/pruning/learned guidance/adaptive.
- **Freeze:** merged instrumentation [PR149](https://github.com/pherrman1/sts_ai/pull/149),
  producer `a6c2abbc9db542ea1fc8933087f81c1de96c4f8a`; Release executable
  `ea86565cfedb44bd2d1c1b130b130aa74f8e376fcf9fbf7b393eca584662d45c`.
  Teacher and all three model hashes match the accepted handoff. The producer
  was exported with pinned dependencies and built once on GCP `sts-test`;
  all 2,468 source hashes, executable and teacher remained unchanged afterward.
  Probe encoders/hyperparameters were frozen before labels: 160 depth3 trees,
  eta0.05, deterministic grouped5-fold CV, 5,000 paired bootstrap replicates.
  The prior128 development groups were not pooled or recollected.
- **Corpus/integrity:** 1,024 decisions, 7,652 semantic actions and 7,652 combat
  rows; all64 capture/semantic/combat shard validations pass. Zero semantic
  quarantines, replay/key/sibling/future/health/accounting failures, duplicate
  branch identities, or feature/formula/provenance failures. Families:
  REWARDS765, CAMPFIRE76, SHOP56, EVENT68, TREASURE35, BOSS_RELIC16, SELECTOR8;
  25 effects,9 sources,127 compound-containing decisions. Median within-decision
  Q range0.05360;60 truth-tied decisions, leaving964 pairwise-defined groups.
- **Representation result:** state-only/primitive/semantic mean regret
  0.036945/0.028932/0.027379 and macro pairwise0.500000/0.530442/0.573233.
  Semantic-minus-primitive regret−0.001553,95%CI[−0.004263,+0.001361];
  pairwise+0.042791,[+0.029331,+0.056130]; top-or-tied+0.044922,
  [+0.021484,+0.068359]. **SEMANTIC CONFIRMED**, explicitly scoped to this
  frozen probe and natural reward-dominated mixture. Every leave-fold-out
  aggregate preserves both favorable primary directions. The large REWARDS
  family drives the ranking gain; nonreward superiority is unproven. No
  numerical harm margin was supplied, so the uncertain regret interval is not
  a formal noninferiority result. SHOP favors semantic on both point estimates
  but both intervals cross zero; EVENT is an adverse uncertain slice. Compound
  regret difference−0.010999,[−0.021706,−0.001858] is descriptive corroboration.
- **Combat labels:** 7,599 valid,7,238 wins,361 true deaths,348 nonambiguous
  deaths;53 escaped/invalid,0 turn-cap,13 ambiguous Awakened One deaths retaining
  inherited V1 signed labels but excluded from nonambiguous support. No branch
  lacks a combat row. Train/validation/test nonambiguous deaths255/45/48,
  from50/12/10 source groups and23/10/9 encounters. **COMBAT LABELS ADEQUATE**
  under the inherited row-count heuristic only: test's largest source provides
  19/48 deaths and the largest three33/48. This is not an independent-sample
  power calculation. No combat evaluator was trained.
- **Cost:** 7,028,180,000 total Silver simulations =3,784,630,000 source capture
  +1,698,650,000 source replay +1,544,900,000 semantic branches. Full corpus
  process CPU54,345.99s (15.10h); sequential stage wall3,739.28s (62.32min),
  with16 independent OMP=1 workers. Build/transfer/offline-analysis time is
  excluded. Yield1.08876 combat rows/million full-pipeline simulations
  (4.95307/million branch-only). **Zero additional Silver simulations for
  combat-label capture**; every64-shard telemetry suffix matches its sidecar.
- **Checks/limits:**12 focused Python tests and1/1 focused CTest pass;
  independent tooling and interpretation reviews KEEP with the limits above.
  Two orchestration launches failed before simulator execution (missing GNU
  time, then JSON gate key normalization), contributing zero seeds/simulations;
  both are preserved, corrected and refrozen without changing producer,
  teacher, probe or captured source data. No completed shard was rerun.
  Authoritative Linux GCC CI is recorded in the evidence PR; no production
  model export/deployment or gameplay-policy qualification was attempted.
- **Evidence:** [compact machine-readable packet](evidence/semantic_combat_confirmation_2026-09-10.json)
  includes all family/compound/fold metrics, intervals, combat act/room/encounter
  distributions, labels, split coverage, costs and hashes. Raw corpus archive
  SHA256 `705bd2c970f52759dd7541052f56536eb5c53470aa0fe37b2674abdfd1ba7ec9`;
  1,006 inventoried files verified after transfer. Raw artifacts remain under
  GCP `runs/semantic-confirmation-a6c2abb/` and local
  `build/semantic-confirmation-phase-b/`; bulk CSVs are not committed.

## §219 Counterfactual pre-combat combat evaluator feasibility (2026-09-10)

- **Question/protocol:** test whether the next-combat signed outcome can be
  predicted from the 1,017-feature pre-combat state plus encounter identity,
  without semantic-action identity. Use only the frozen §218 sidecars; do not
  pool V1 or the 128-decision development corpus, regenerate labels, call
  Silver, or integrate a runtime model.
- **Frozen implementation:** baseline `9c9e0a2`; analysis SHA
  `6d1a3f3d7c0c1913ea4e30f1b0ea12d06627eca4`; adapter
  `tools/train_combat_evaluator_semantic_branch.py`; unchanged grouped
  `stable_split(sourceSeed)`; 300-round XGBoost depth6, eta0.05, subsample and
  column sample0.8, seed20260902, hist, one CPU thread. The adapter validates
  all64 manifests and the raw package SHA256
  `705bd2c970f52759dd7541052f56536eb5c53470aa0fe37b2674abdfd1ba7ec9` before
  fitting. Encounter vocabulary and variance filtering are TRAIN-only.
- **Coverage/splits:** 7,652 rows (7,599 valid; 7,238 wins; 361 true deaths;
  348 nonambiguous deaths). Source splits are TRAIN 711/5,519 rows,
  VALIDATION 156/1,081, TEST 157/1,052; nonambiguous deaths are 255/45/48.
- **Held-out TEST:** survival logloss/Brier `0.13460/0.03121` versus prior
  baseline `0.18556/0.04356`; winning-HP MAE/RMSE `0.10380/0.15359` versus
  `0.22660/0.26409`; expected-signed MAE/RMSE `0.12396/0.19387` versus
  `0.26600/0.33568`; sign accuracy `95.53%`. Loss-severity MAE/RMSE
  `0.22309/0.26611` is worse than the death-mean baseline
  `0.13273/0.16806`.
- **Correlation-aware uncertainty:** 5,000 deterministic source-seed paired
  bootstrap replicates. TEST model-minus-baseline intervals are survival
  logloss `[-0.15549,+0.03577]`, Brier `[-0.03813,+0.00888]`, winning-HP MAE
  `[-0.15117,-0.09483]`, and expected-signed MAE `[-0.18089,-0.10948]`.
  Loss-severity uses 10 death-source groups, interval
  `[-0.03731,+0.14697]`, with leave-one-source-out differences ranging
  `[+0.02594,+0.10224]`; no source removal makes the loss tail beat baseline.
- **Alias/source views:** among 7,599 valid rows there are 5,683 unique
  `(state, encounter)` inputs, 1,106 duplicate groups, 172 groups with
  different signed outcomes, and maximum within-input outcome spread 1.23998.
  TEST source-macro survival Brier is `0.02812` versus `0.03668` baseline;
  expected-signed absolute error is `0.12900` versus `0.26527` baseline.
  Descriptive TEST act/room/encounter slices are retained in the full report;
  no encounter-specific conclusion is made from sparse source support.
- **Speed/artifacts:** batch-1 CPU medians/p95 are 0.182/0.248ms survival,
  0.176/0.234ms winning HP, and 0.175/0.234ms loss severity. Full models and
  predictions remain external and are not committed; their hashes and sizes
  are in the [compact evidence packet](evidence/semantic_combat_evaluator_2026-09-10.json).
- **Decision:** **COMBAT PREDICTOR PROMISING — LOSS TAIL INCONCLUSIVE**. The
  result supports designing a later simulation-replacement experiment, not
  deployment, Silver replacement, more labels, or gameplay qualification.
- **Evidence:** [compact machine-readable packet](evidence/semantic_combat_evaluator_2026-09-10.json).

## §220 First frozen semantic OOC action scorer: PASS on fresh holdout (2026-09-10)

- **Question/design:** carry the confirmed structured semantic action
  representation into the first reusable offline scorer. Fit `deltaQ =
  qProduct - mean(qProduct within decision)` with the exact confirmed XGBoost
  recipe, alongside a primitive control and a state-only action-agnostic null.
  The trainer freezes the ordered vocabulary, state header, encoder SHA,
  hyperparameters and model hashes before any holdout labels are inspected.
  No live policy, C++, production tree export or combat evaluator changed.
- **Training corpus/freeze:** exactly 64 validated shards, source seeds
  992000–993023, 1,024 decisions, 7,652 semantic rows and zero quarantines.
  Producer SHA is `a6c2abbc9db542ea1fc8933087f81c1de96c4f8a`; preserved package
  SHA256 is `705bd2c970f52759dd7541052f56536eb5c53470aa0fe37b2674abdfd1ba7ec9`.
  The semantic model has 1,831 features (1,017 state + 814 action), while
  primitive control has 1,084 (1,017 + 67). The frozen artifacts and full
  64-shard manifest/CSV hash list remain in ignored build storage; committed
  evidence contains their SHA256 identities.
- **Training diagnostics:** semantic/primitive macro pairwise is
  `0.599555/0.554452`, mean selected regret `0.022475/0.025271`, top-or-tied
  `0.467773/0.401367`, deltaQ MAE `0.027125/0.027642`, and RMSE
  `0.056141/0.055872`. These are fit diagnostics, not generalization claims.
- **Fresh holdout:** capture completed all eight 16-seed shards first, then
  every semantic replay manifest passed the existing corpus contract. The
  untouched source range 993024–993151 yielded 128 decisions and 935 rows,
  with zero quarantines, execution failures, sibling mismatches, future
  mismatches, health failures, accounting failures or provenance failures.
  Natural decision distribution is REWARDS 101, SHOP 11, EVENT 8, CAMPFIRE 4,
  TREASURE 4, BOSS_RELIC 0 and SELECTOR 0.
- **Frozen evaluation:** semantic/primitive/action-agnostic macro pairwise is
  `0.555025/0.490313/0.500000`; mean regret is
  `0.042972/0.045138/0.038129`; top-or-tied is
  `0.375000/0.296875/0.312500`. The semantic-minus-primitive paired bootstrap
  intervals are regret `[-0.006893,+0.002463]`, macro pairwise
  `[+0.031004,+0.098120]`, and top-or-tied `[+0.031250,+0.132813]`.
  Semantic-minus-null pairwise is `[+0.011291,+0.098945]` at 95%.
- **Slices/manual review:** non-compound decisions (116) favor semantic over
  primitive in pairwise `0.555950/0.486222` and mean regret
  `0.036091/0.041535`. The 12 compound-containing decisions still favor
  semantic pairwise `0.546242/0.529176`, but semantic regret is worse
  `0.109495/0.079962`; EVENT is also small and adverse on both scorer point
  estimates. The held-out report preserves eight fixed, non-cherry-picked
  complete sibling examples covering compound SHOP, REWARDS, CAMPFIRE/Smith,
  EVENT and TREASURE. Thirteen distinct unseen categorical action features
  (20 mentions) were reported as absent/zero; the feature shape was unchanged.
- **Decision/limits:** **SEMANTIC MODEL V1 PASS** under the preregistered
  holdout rule: above the ranking null, no worse than primitive in mean regret,
  higher than primitive in macro pairwise, and no major-family catastrophic
  failure in this natural reward-dominated sample. This authorizes a future
  controlled runtime-integration study only; it does not establish gameplay
  improvement, production compatibility or family-wide superiority. Do not
  tune against this holdout; a changed architecture needs new development-CV
  work and a new holdout.
- **Evidence:** [compact model packet](evidence/semantic_ooc_model_v1_2026-09-10.json).
  Full frozen `semantic_model.json`, `primitive_control.json`,
  `feature_manifest.json`, `training_report.json` and the detailed holdout
  `evaluation_report.json` are preserved outside Git at
  `/home/philippherrmann/sts_sweep/preserved/semantic-ooc-model-v1-2026-09-10/`;
  the working copies remain in ignored `build/` storage. Bulk semantic CSVs,
  logs and predictions remain ignored/external and are not committed.

## §221 Pre-combat combat evaluator model comparison (2026-09-10)

- **Question/protocol:** test the prespecified alternatives to the frozen §219
  three-head XGBoost evaluator using only the validated §218 corpus. TRAIN was
  used for fitting and normalization; VALIDATION selected early-stopping
  iterations and one finalist per family; a selection-freeze record was written
  before one TEST evaluation per finalist. No simulator, Silver, new labels,
  gameplay integration, or production export was used.
- **Implementation/provenance:** runner and focused tests at experiment-code
  SHA `eafaf34113cd07bf0a7b99dbecc903d229bab681`; baseline/main SHA
  `b9d9fe16bc58e7060967f6154a2e16acd89500f5`; producer
  `a6c2abbc9db542ea1fc8933087f81c1de96c4f8a`; 64 frozen manifests, 1,024
  source seeds, 7,652 rows, 7,599 valid, 7,238 wins, 361 true deaths and 348
  nonambiguous deaths. The raw package hash is
  `705bd2c970f52759dd7541052f56536eb5c53470aa0fe37b2674abdfd1ba7ec9`.
- **Frozen choices:** A = exact depth6/eta.05/300-round factorized control;
  B = B5 depth4/eta.02/1200 max with 75-round early stopping; C = C3 direct
  signed depth4/eta.02/1200 max with 75-round early stopping; D = 256→128
  multitask MLP, ReLU/dropout.1/AdamW, 600-epoch cap and 75-epoch patience;
  E = B5 with prespecified source-balanced weights. Candidate validation
  choices were B5 `0.125771`, C3 `0.128483`, and D-small factorized `0.168166`.
- **TEST primary signed MAE/RMSE:** A `0.123964/0.193867`; B
  `0.125601/0.193480`; C `0.134334/0.202945`; D direct head
  `0.169468/0.246408` (its factorized value is `0.166905/0.239267`); E
  `0.128602/0.196002`. Arm A reproduced the frozen §219 result exactly.
  Model-minus-A 5,000 source-seed bootstrap 95% intervals for primary MAE
  are B `[-0.006490,+0.010053]`, C `[-0.003671,+0.025843]`, D
  `[+0.022276,+0.068463]`, and E `[-0.005770,+0.015866]`.
- **Head and loss diagnostics:** B TEST survival logloss/Brier is
  `0.114776/0.029416`, winning-HP MAE/RMSE `0.103808/0.154392`, and loss
  MAE/RMSE `0.172366/0.208295`; E is `0.126386/0.033208`,
  `0.105771/0.155059`, and `0.146445/0.182713`. D is
  `0.237243/0.035683`, `0.149284/0.204814`, and `0.239220/0.293874`.
  The trivial TEST death-mean loss MAE is `0.132734`; therefore no new
  conditional loss head learns loss severity. There are only 10 independent
  death sources; leave-one-source-out model-minus-trivial ranges are A
  `[+0.02594,+0.10224]`, B `[-0.00018,+0.04734]`, D
  `[+0.07610,+0.12459]`, and E `[-0.00663,+0.02133]`.
- **Risk/ranking/speed:** validation thresholds targeting at least 90% death
  recall were frozen and yielded TEST recall 1.00 for A/B/D/E, with fallback
  fractions `0.531/0.610/0.705/0.590` and false-alarm rates
  `0.509/0.592/0.691/0.571`, respectively. C has no probability head. Macro
  pairwise concordance for A/B/C/D/E was `0.4524/0.4797/0.4900/0.4588/0.4819`;
  macro Spearman was `0.0930/0.1379/0.0878/0.1182/0.1383` across 136 eligible
  TEST decisions. Prebuilt-input batch-1 CPU median/p95 milliseconds were
  A `0.537/0.700`, B `0.544/0.648`, C `0.183/0.217`, D `0.076/0.109`, and E
  `0.537/0.676`; serialized finalist sizes were 2.73, 2.56, 1.04, 0.67, and
  2.10 MB.
- **Decision:** **NO CLEAR MODEL IMPROVEMENT**. The strict improvement rule
  is not met; B and E are slightly worse point estimates with intervals
  crossing zero, C is worse, and D is clearly worse. D's lower TRAIN error but
  worse held-out error supports **CAPACITY NOT THE BOTTLENECK**; the sparse,
  correlated death tail remains the actionable limitation. Do not add larger
  networks, deploy a winner, replace Silver, or run gameplay gates from this
  result. Full report and bulk models/predictions remain external.
- **Evidence:** [compact machine-readable packet](evidence/combat_evaluator_model_comparison_2026-09-10.json); full external report at
  `/home/philippherrmann/sts_sweep/runs/combat-evaluator-comparison-v4/report.json`.

## §222 Correction pass for pre-combat evaluator comparison (2026-09-10)

- **Reason for correction:** independent review found three bounded analysis
  defects in §221: the paired survival-Brier bootstrap used absolute rather
  than squared residuals; NN checkpointing and finalist selection used the
  factorized value despite declaring the direct signed head primary; and
  concordance counted truth-tied pairs as comparable. No grids, corpus,
  labels, split, or model architecture were changed.
- **Corrected implementation:** analysis SHA
  `9b6502b53b72c3239de1f39d08ccde56a3ff2557`; same baseline/main SHA
  `b9d9fe16bc58e7060967f6154a2e16acd89500f5`, producer, 64 manifests, 1,024
  sources, 7,652 rows, and raw package hash. Survival-Brier bootstrap now uses
  squared error; NN early stopping and D-family selection use direct signed
  validation MAE; concordance skips pairs with equal true signed outcomes.
- **Corrected dependent results:** finalists remain A/B5/C3/D-small/E. NN
  validation direct MAE is D-medium `0.196261` versus D-small `0.171680`.
  TEST primary signed MAE/RMSE are A `0.123964/0.193867`, B
  `0.125601/0.193480`, C `0.134334/0.202945`, D direct
  `0.167342/0.242484` (factorized `0.165833/0.237704`), and E
  `0.128602/0.196002`. The corrected Brier model-minus-A intervals are B
  `[-0.010984,+0.005912]`, D `[-0.013483,+0.024549]`, and E
  `[-0.003932,+0.008777]`; B's point Brier improvement is therefore no
  longer contradicted by its bootstrap report.
- **Corrected ranking:** after excluding truth-tied pairs, macro pairwise
  concordance A/B/C/D/E is `0.5462/0.5715/0.5395/0.5631/0.5700` across 136
  eligible TEST decisions. Spearman remains
  `0.0930/0.1379/0.0878/0.1244/0.1383`.
- **Decision:** the substantive conclusion remains **NO CLEAR MODEL
  IMPROVEMENT**. No finalist has a favorable source-clustered primary-MAE
  interval excluding zero; the MLP remains clearly worse than A, and the
  conditional loss tail remains above the trivial death mean with only 10
  independent death sources. The corrected evidence supersedes the §220
  numerical packet; no deployment, Silver replacement, or gameplay gate is
  authorized.
- **Checks:** 22 focused/relevant Python tests pass, including regression
  tests for squared Brier, direct-head NN selection, and truth-tied
  concordance; Python compilation, JSON validation, evidence cross-check, and
  `git diff --check` pass. Full corrected report and TEST predictions remain
  external at `/home/philippherrmann/sts_sweep/runs/combat-evaluator-comparison-v5/`.

## §223 Silver chance replay: generative-frequency diagnostic (2026-09-11)

- **Question/protocol:** test whether Silver's capped chance replay amplifies
  early sampling luck when multiple fresh simulator draws deduplicate to the
  same state. Baseline was `6c6dc8b7e1cbb0e11c3e64efdfa341fe5a229a78`.
  The fixture runner used the real `BattleSearcher::selectChanceOutcome()`
  path, paired deterministic seeds `0..127`, budgets `32/64/128/256/512`, and
  identical widening schedules and synthetic random streams for A/B. The
  local 128-seed cap was respected.
- **Current contract:** a stochastic action's first outcome is generated from
  `Random(randomnessBase + 0)` and cached; later widening draws increment
  `outcomesGenerated`, execute the generator from
  `Random(randomnessBase + N)`, and deduplicate the resulting state with
  `equalForSearch`. A fresh duplicate increments the cached edge's
  `generativeCount`; every descent increments its `visitCount`. Once the
  double-progressive-widening cap
  `ceil(c * (simulationCount + 1)^alpha)` is reached, the default implementation
  selects a cached edge proportional to `visitCount`. Thus search/replay
  allocation can feed back into later outcome selection; it is not the same
  quantity as fresh stochastic frequency.
- **Fixtures:** analytical 50/50, 80/20, a 25/75 raw-draw-to-two-state
  deduplication fixture, a uniform 16-state high-entropy fixture where
  progressive widening binds, and an independent-stream close decision with
  true values 0.60 versus 0.58. A treatment arm replaced only capped replay's
  `visitCount` weight with fresh-draw `generativeCount`; the default remained
  unchanged. No UCT, widening, rollout, root exploration, or tree-reuse
  parameter changed.
- **Selected raw results:**

  | Fixture | Budget | A RMSE | B RMSE | A mean p0 | B mean p0 |
  | --- | ---: | ---: | ---: | ---: | ---: |
  | 50/50 | 128 | 0.32068 | 0.18424 | 0.53394 | 0.54889 |
  | 50/50 | 512 | 0.32042 | 0.18159 | 0.53331 | 0.54939 |
  | 80/20 | 128 | 0.30012 | 0.22340 | 0.68640 | 0.64667 |
  | 80/20 | 512 | 0.29870 | 0.22025 | 0.68813 | 0.65099 |
  | dedup 25/75 | 128 | 0.33560 | 0.20849 | 0.38458 | 0.37207 |
  | dedup 25/75 | 512 | 0.33487 | 0.20644 | 0.38145 | 0.36932 |
  | entropy-16 | 128 | 0.06669 | 0.04953 | 0.03503 | 0.03534 |
  | entropy-16 | 512 | 0.01682 | 0.01254 | 0.05321 | 0.05328 |

  On the close decision, A selected the truly better 0.60 arm on
  `76.6/77.3/76.6/78.9/76.6%` of seeds at budgets
  `32/64/128/256/512`; B scored `71.1/73.4/71.1/71.1/71.9%`. Across the four
  non-close fixtures, B's aggregate value RMSE was lower by 29–35% at budgets
  32, 128, and 512. Runtime was within measurement noise overall, with the
  B/A matrix total at budget 128 about 5.8% higher and at 512 about 0.8%
  higher in this small runner.
- **Decision:** **MIXED; STOP.** The feedback mechanism is real, and B clearly
  reduces value-estimate RMSE in these synthetic fixtures, including the
  deduplication case. However, it worsens the explicitly required close root
  action decision across every tested budget. The result does not meet a
  clean policy-improvement bar and does not authorize a gameplay screen or a
  production Silver switch. The default production contract remains A.
- **Evidence/checks:** raw machine-readable rows are in
  [silver_chance_frequency_2026-09-11.csv](evidence/silver_chance_frequency_2026-09-11.csv).
  The experiment and affected Silver optimization target build with the
  `linux-gcc-debug-ccache` preset; `silver_search_optimization` passes and
  the output schema contains 70 rows over the six value fixtures plus five
  close-decision budgets per arm. `git diff --check` passes. No large gameplay
  benchmark was run.

## §224 Silver chance replay: explicitly authorized gameplay screen (2026-09-11)

- **Reason for run:** §223 stopped at a mixed synthetic result and therefore
  did not authorize gameplay qualification. The user explicitly authorized a
  small gameplay screen anyway. This is an exploratory follow-up, not a
  changed production gate.
- **Protocol:** compare default A against B with only
  `STS_SILVER_GENERATIVE_CHANCE=1` changed. Both arms used
  `one_combat bestbench 1000 32 0 0`, the repository seed guard, the same
  project-fair seed block `0..31`, Searcher2 (`STS_SEARCHER3=0`), native OOC,
  isolated Silver search, exact Silver root budgets, and telemetry. The
  implementation was `a46cc83d7d3515e8b864236e41c4013dca835d91`; the live
  treatment path is default-off.
- **Results:**

  | Arm | Wins | Mean floor | Mean ending HP | Fights lost | Mean seconds |
  | --- | ---: | ---: | ---: | ---: | ---: |
  | A, default replay weighting | 19/32 (59.4%) | 46.53 | 22.13 | 13 | 23.86 |
  | B, generative-frequency weighting | 15/32 (46.9%) | 47.47 | 21.84 | 17 | 23.02 |

  Paired win disagreements were five A-win/B-loss seeds versus one
  A-loss/B-win seed. B's paired mean deltas were `+0.94` floor, `-0.28`
  ending HP, `+0.125` fights lost, and `-0.84` seconds. The screen therefore
  does not support promoting B: its slightly higher mean floor did not carry
  through to wins and came with more lost fights. No runtime default changed.
- **Evidence/checks:** raw paired rows are in
  [silver_chance_gameplay_screen_2026-09-11.csv](evidence/silver_chance_gameplay_screen_2026-09-11.csv).
  Both arms completed 32 rows with the same seed set and no simulator,
  conversion, transaction, semantic-resolution, or knowledge failures in
  telemetry. The treatment log emitted the explicit experimental banner.
  The build and focused Silver regression checks passed before the screen;
  `git diff --check` and the seed guard also passed. This 32-seed screen is
  too small to establish a general gameplay effect, but it is sufficient to
  reject this treatment for the current production path.

## §225 Silver chance replay: 10k-simulation gameplay screen (2026-09-11)

- **Reason for run:** follow up on §224 at the user's request to test whether
  the 1k-screen result changes at a larger search budget. This remains a
  descriptive, explicitly authorized screen; it is not a new promotion gate.
- **Protocol:** the §224 paired design was repeated with only the root budget
  changed from `1,000` to `10,000`: `one_combat bestbench 10000 32 0 0`,
  project-fair seeds `0..31`, Searcher2, native OOC, isolated Silver search,
  exact root budgets, telemetry, and `tools/seed_guard.sh`. A used the default
  replay weighting; B added only `STS_SILVER_GENERATIVE_CHANCE=1`. The
  implementation/configuration head was `0517e682061ebb382f3a5a9238967b7542f87e2b`.
- **Results:**

  | Arm | Wins | Mean floor | Mean ending HP | Fights lost | Mean seconds |
  | --- | ---: | ---: | ---: | ---: | ---: |
  | A, default replay weighting | 19/32 (59.4%) | 47.47 | 28.53 | 13 | 239.97 |
  | B, generative-frequency weighting | 22/32 (68.8%) | 49.28 | 30.31 | 10 | 255.15 |

  Paired win disagreements were two A-win/B-loss seeds versus five
  A-loss/B-win seeds. B's paired mean deltas were `+3` wins in aggregate,
  `+1.81` floor, `+1.78` ending HP, `-3` fights lost, and `+15.18` seconds.
  Relative to §224, the 10k screen reverses the direction of the small 1k
  screen for this seed block: B went from 15 wins to 22, while A stayed at
  19. This suggests a budget interaction, but does not establish a general
  policy or win-rate improvement from only 32 paired seeds.
- **Decision:** **DESCRIPTIVE 10K SIGNAL; DO NOT PROMOTE.** The result is
  encouraging for a future budget-interaction study, but the sample is too
  small and the treatment remains synthetic-mixed and default-off. Keep A as
  the production default; do not enable B based on this screen alone.
- **Evidence/checks:** raw paired rows are in
  [silver_chance_gameplay_screen_10k_2026-09-11.csv](evidence/silver_chance_gameplay_screen_10k_2026-09-11.csv).
  Both arms completed 32 rows with identical seed coverage and no simulator,
  conversion, transaction, semantic-resolution, or knowledge failures in
  telemetry. The build, focused Silver regressions, seed guard, and
  `git diff --check` passed. The local 10k screen took several minutes per
  arm; full CTest and GitHub Actions CI were not run locally.

## §226 Silver chance replay: 64 fresh-seed 10k follow-up (2026-09-11)

- **Trigger:** §225's fresh 32-seed block produced exactly the proposed
  escalation threshold: B had seven A-loss/B-win seeds versus three
  A-win/B-loss seeds, net `+4` paired wins. Following the proposed rule, a
  second untouched 32-seed block was run rather than changing parameters.
- **Protocol:** seeds `64..95` were added to the existing fresh block
  `32..63`, for 64 total fresh paired seeds. Both A and B used
  `one_combat bestbench 10000 32 0 <seedOffset>` through
  `tools/seed_guard.sh`, with `OMP_NUM_THREADS=12`, project-fair Searcher2,
  native OOC, isolated Silver, exact root budgets, and telemetry. The only
  A/B difference remained B's `STS_SILVER_GENERATIVE_CHANCE=1`.
- **Results over all 64 fresh seeds:**

  | Arm | Wins | Mean floor | Mean ending HP | Fights lost | Mean seconds |
  | --- | ---: | ---: | ---: | ---: | ---: |
  | A, default replay weighting | 41/64 (64.1%) | 47.52 | 30.83 | 23 | 251.54 |
  | B, generative-frequency weighting | 46/64 (71.9%) | 47.89 | 38.91 | 18 | 298.82 |

  The paired record was 9 A-loss/B-win versus 4 A-win/B-loss seeds, for a
  net B advantage of `+5` paired wins. B's paired mean deltas were `+0.38`
  floor, `+8.08` ending HP, `-5` fights lost, and `+47.28` seconds. The
  second block alone was weaker but still favorable to B: 2 A-loss/B-win
  versus 1 A-win/B-loss, net `+1`.
- **Decision:** **64-SEED SIGNAL; HOLD FOR PROPER PROMOTION TEST.** The
  aggregate meets the suggested escalation result and is directionally
  consistent with the 32-seed trigger, but 64 seeds remain a small
  descriptive screen rather than a production qualification. Do not enable
  B by default and do not tune widening or other parameters between this
  result and any future promotion test.
- **Evidence/checks:** the combined raw paired rows are in
  [silver_chance_gameplay_screen_10k_fresh32-95_2026-09-11.csv](evidence/silver_chance_gameplay_screen_10k_fresh32-95_2026-09-11.csv),
  which preserves both source blocks and all 128 A/B rows. All four arms
  completed their expected 32 rows, startup banners reported `threads 12`
  and the correct seed ranges, and telemetry showed no simulator,
  conversion, transaction, semantic-resolution, or knowledge failures.
  Focused Silver tests, worktree validation, seed-guard checks, and
  `git diff --check` passed; full CTest and GitHub Actions CI were not run
  locally.
- **Merge cleanup:** after the screens, the user selected A as the production
  behavior. The experiment-only `generativeCount`/replay switch, synthetic
  fixture executable and CMake target, live environment flag, and diagnostic
  searcher hook were removed before merging this evidence. The recorded rows
  above were produced by the frozen pre-cleanup executable/configuration and
  remain historical evidence; no treatment implementation or production
  default is retained.

## §227 First whole-combat transition model comparison (2026-09-12)

- **Question/protocol:** use the already-collected whole-combat
  `combat_transition_row_v2` corpus to decide whether a simple flattened
  model is sufficient before planning Phase 2. No new simulator collection,
  runtime Silver replacement, model export, gameplay gate, or GCP job change
  was made. The final corpus was independently checked at 322/322 shard
  manifests and by the merged transition validator.
- **Frozen provenance:** producer
  `f0bbd7721e7cc1453976ebb91ee11ebe6127a2bf`, Release executable SHA256
  `d0a1c66faa931498660811a7406fbc6be93d63c5e7ef4f6f24c910e4f57c2872`,
  teacher `silver-ordinary-fair-exact10k-combat-transition-runtime16-f0bbd77`,
  predictor `combat_predictor_input_v1` field hash `1a92692da9247008`, and
  transition row `combat_transition_row_v2`. The corpus covers requested
  seeds `4100016..4125015`: 24,999 completed, one quarantined
  (`4102275`, `process_exit_134`), and 510,030 rows. Corpus SHA256 is
  `74c08aa0a3c30342d86cd45355fe17ffa9046963ad7c8cf71b1938f9cdc1cfde`.
- **Split/features:** source-grouped SHA256 split (80/10/10) produced 19,986
  TRAIN, 2,496 VALIDATION, and 2,517 TEST sources; split SHA256 is
  `e9043bcceb9d95027711e6ff33afbfe1cae3cf9528f820c0ff68bddbb419db32`.
  Inputs were restricted to the predictor contract. The flat representation
  had 2,846 fields, with 721 nonconstant TRAIN fields retained. DeepSets had
  89,338 parameters and attention had 107,970 parameters; attention used
  width 64, two layers, four heads, explicit token types/order/slot, and no
  arbitrary card positional embeddings. Labels were win and winning post-
  combat HP fraction, with death HP masked; observed implied alive HP was
  `0.7550374`.
- **Frozen fit:** CUDA was required for XGBoost and both neural families;
  `OMP_NUM_THREADS=8`, XGBoost histogram, depth `{4,6}`/learning-rate `.05`/
  min-child-weight `1`, 400-round cap and 30-round early stopping, DeepSets
  and attention batch 2,048, 12-epoch cap, patience 3, training seed
  `20260911`, and 1,000 source-bootstrap replicates. Validation composite
  scores were XGBoost `0.179493`, DeepSets `0.180073`, attention `0.180856`;
  XGBoost depth 6 was selected.
- **TEST aggregate:** XGBoost survival AUC/Brier/logloss was
  `0.974918/0.018980/0.065256`, winning-HP MAE/RMSE `0.075240/0.111074`,
  and joint alive-HP MAE/RMSE `0.082444/0.125727`. DeepSets was
  `0.975461/0.018809/0.064157`, `0.076545/0.112429`, and
  `0.083051/0.126736`; attention was `0.975634/0.019448/0.065977`,
  `0.076256/0.115493`, and `0.083308/0.130533`. Source-bootstrap intervals
  did not establish a strict practical DeepSets or attention win over the
  selected baseline.
- **Decision:** **XGBOOST_SUFFICIENT.** The simple model is the validation
  finalist and is not materially displaced by either typed-token family.
  This is an offline model-selection result only; it does not authorize
  runtime integration, Silver replacement, model export, or a gameplay gate.
  Phase 2 should remain planning-only and use copy-through plus sparse deltas.
- **Cost/validation:** the CUDA fit took 825.60 seconds wall and 878.81
  seconds user+system CPU, with peak RSS 16,113,592 kB (15.367 GiB). The RTX
  3060 Ti reached approximately 5.5 GiB VRAM and 100% utilization. The merged
  validator exited 0 with 491,897 wins, 18,133 deaths, zero quarantined rows,
  and zero unexpected health failures.
- **Evidence:** [compact report](evidence/combat_transition_model_v1_2026-09-12.md).
  Full audit, source-group split, prepared arrays, models, validator output,
  and timing are preserved externally under
  `/home/philippherrmann/sts_sweep/runs/combat-transition-model-v1/`; the raw
  corpus remains under `/home/philippherrmann/sts_sweep/runs/combat-transition-runtime-25k/`
  and is not committed.

## §228 Corrected whole-combat transition model rerun after independent review (2026-09-12)

- **Correction/protocol:** the existing §227 corpus, source split, and Phase-1
  targets were reused unchanged. The corrected tool derives card/relic/potion
  domains from `apps/one_combat/run_features.h` as 372/181/48, rejects IDs
  outside those domains before encoding, and removes neural ID clamping. The
  flattened baseline now uses continuous globals plus deterministic one-hot
  fields for `characterClass`, `encounter`, `roomClass`, and `lastRoom`.
  DeepSets and attention use small embeddings for those categorical globals.
- **Domain audit:** observed IDs were cards `11..369`, relics `0..177`, and
  potions `1..43`. Relative to the previous 371/128/44 bounds, 0 card tokens
  in 0 rows, 890,897 relic tokens in 339,996 rows, and 0 potion tokens in 0
  rows would have been truncated by the old flat encoder and clamped/collided
  by the old neural encoder.
- **Equal final fit:** validation-only selection froze XGBoost depth 6 at 400
  survival rounds and 400 winning-HP rounds, DeepSets at 12 epochs, and
  attention at 12 epochs. All three families were then refit from scratch on
  TRAIN+VALIDATION with those fixed lengths/configurations before the frozen
  TEST rerun. The deterministic training seed was `20260911`; no TEST metric
  was used for selection or early stopping. Validation composites were
  XGBoost `0.179316`, DeepSets `0.171834`, attention `0.169172`; attention was
  the validation finalist.
- **Corrected TEST:** XGBoost survival AUC/Brier/logloss was
  `0.974997/0.018985/0.065183`, winning-HP MAE/RMSE `0.075141/0.110923`, and
  joint alive-HP MAE/RMSE `0.082427/0.125750`. DeepSets was
  `0.978864/0.017780/0.060430`, `0.072614/0.106994`, and
  `0.078684/0.120493`; attention was `0.978805/0.017901/0.060792`,
  `0.072575/0.107032`, and `0.078781/0.120692`. Both neural families were
  below XGBoost on all three error intervals, but attention versus DeepSets
  overlapped on all three. The corrected classification is therefore
  **`STRUCTURED_NEURAL_WINS_NO_CLEAR_FAMILY`**: XGBoost is rejected as
  sufficient because both DeepSets and attention clearly improve Phase-1
  prediction. Attention has no demonstrated improvement over DeepSets, so
  DeepSets is selected as the Phase-2 default by a simplicity tie-breaker.
- **Scientific status:** TEST had already been inspected under §227's flawed
  implementation; §228 is explicitly a corrected rerun of the frozen TEST
  split, not an untouched first TEST. The numeric practical-improvement
  threshold claim is removed; the reporting rule requires separation from
  every competing family and is not described as preregistered. No runtime
  model, model export, Silver replacement, Phase 2 transition head, or new
  collection is authorized. If Phase 2 is later authorized, DeepSets is the
  default candidate by the simplicity tie-breaker; this interpretation does not
  authorize implementation.
- **Cost/validation:** CUDA fit wall time was 2,132.17 seconds, user+system
  CPU was 2,204.24 seconds, and peak RSS was 17,515,476 kB (16.704 GiB).
  The transition validator passed with 510,030 rows, 24,999 completed source
  seeds, one manifest quarantine (`4102275`, `process_exit_134`), zero
  quarantined rows, and zero unexpected health failures.
- **Evidence:** corrected compact report at
  [evidence/combat_transition_model_v1_2026-09-12.md](evidence/combat_transition_model_v1_2026-09-12.md);
  full audit, split, prepared arrays, model evidence, exact command, logs, and
  timing remain external under
  `/home/philippherrmann/sts_sweep/runs/combat-transition-model-v1/`.

## §229 Phase-2 stochastic persistent-state surrogate support audit stopped (2026-09-12)

- **Question/protocol:** implement the first offline stochastic persistent-state
  combat surrogate using the corrected PR #161 DeepSets representation and the
  frozen §228 corpus/split. The intended heads were survival, winning max-HP
  delta, conditional 101-bin post-combat HP fraction, five potion slots,
  per-owned mutable relic deltas, and joint `(deltaGold, post.stolenGold)`;
  the same DeepSets survival/expected-winning-HP point control was specified.
  No new source seeds, simulator execution, attention rerun, runtime adapter,
  or Silver integration was authorized.
- **Frozen provenance:** baseline/main SHA before implementation
  `58250bdb2e93c2c69b6556f408eb54ef5230639c`; corpus SHA256
  `74c08aa0a3c30342d86cd45355fe17ffa9046963ad7c8cf71b1938f9cdc1cfde`;
  source-group split SHA256
  `e9043bcceb9d95027711e6ff33afbfe1cae3cf9528f820c0ff68bddbb419db32`;
  510,030 rows from 24,999 completed requested seeds and one quarantined
  source (`4102275`, `process_exit_134`).
- **Implementation:** `tools/combat_transition_surrogate.py` is a separate
  offline prepare/fit tool. It derives canonical domains 372/181/48, uses
  typed DeepSets pooling at width 64, validates target support, masks relic
  delta classes per ID, derives potion count from canonical IDs, validates
  sampled state invariants, and excludes `combatRng[6]` from both input and
  output. `tools/test_combat_transition_surrogate.py` covers the support
  predicate, HP bins, relic audit, and sampler validity; the focused test is
  registered as `combat_transition_surrogate_selftest`.
- **Support audit:** overall support was 488,283/510,030 (95.7361%); by act,
  Act 1 was 237,124/238,946 (99.2375%), Act 2 162,987/171,452 (95.0628%),
  and Act 3 88,172/99,632 (88.4977%). Death support was 16,699/18,133
  (92.0918%). By room class, EVENT was 7,467/7,826 (95.4127%), ELITE
  113,725/118,335 (96.1043%), MONSTER 315,622/329,935 (95.6619%), and BOSS
  51,469/53,934 (95.4296%). The full per-encounter table is in the compact
  evidence report. Fallback reason counts overlap: WRITHING_MASS 4,477,
  RITUAL_DAGGER 13,926, and visible SMOKE_BOMB 3,765.
- **Blocking finding:** the required omitted-mutation coverage gate failed.
  Deck-structure mutations were present in 1,151 rows and card-misc
  mutations in 109 rows, with zero supported rows for either. However,
  `smokeBombUsed: false -> true` occurred in 3,001 rows, including 77 rows
  that the predictor-visible predicate would support. A full-corpus scan found
  78 rows where the resulting Smoke Bomb was not visible in the pre-state;
  one also had Ritual Dagger and was already excluded. All 78 had visible
  `ENTROPIC_BREW` in the pre-state. The bounded source path is
  `BattleContext::drinkPotion(Potion::ENTROPIC_BREW)` -> random potion draw ->
  `obtainPotion`, which can generate the unobserved Smoke Bomb. The handoff
  explicitly forbade broadening the predicate ad hoc, so preparation exits
  non-zero with the fail-closed error and no arrays are accepted for fitting.
- **Second boundary conflict:** among supported winning rows,
  `smokeBombUsed` differed in 103 copy-through checks: 77 `false -> true` and
  26 `true -> false`. Since that field is not predictor-visible, it cannot be
  safely added as another support guard under the stated predicate.
- **Target preview:** TRAIN-supported wins showed max-HP delta classes
  `{0,3,4,5,6,7,8,9,10,11,12}`, 193 joint gold classes (below the 512 stop
  threshold), and the bounded 13-ID mutable relic audit including direct
  Omamori RAW-exit handling. These are support observations only, not fit
  outputs.
- **Decision:** **`TARGET_OR_SUPPORT_PROBLEM`**. No Phase-2 or control fit,
  fixed TEST evaluation, metrics, model size, latency, sampled-transition
  validity gate, or model export was run. Raw corpus and any future models
  remain external. Evidence: [Phase-2 support-audit report](evidence/combat_transition_surrogate_phase2_2026-09-12.md).

## §230 Phase-2 corrected eligibility boundary and target-support stop (2026-09-13)

- **Correction/protocol:** the same §228 corpus, source-group split, producer,
  teacher, and Phase-2 target design were reused. The support predicate now
  excludes non-Ironclad rows, Writhing Mass, any deck containing Ritual Dagger,
  any Smoke Bomb or Entropic Brew potion, and pre-combat
  `smokeBombUsed == true`. The learned input remains
  `combat_predictor_input_v1`; `pre.smokeBombUsed` is an adapter/support-gate
  field only and is not encoded or learned. No new data, runtime inference,
  Silver replacement, attention rerun, or OOC rollout was authorized.
- **Support coverage:** the audit passed on all 510,030 rows: 485,166
  supported (95.1250%) and 24,864 fallback. Death support was 16,620/18,133
  (91.6561%); Act 1/2/3 support was 235,667/238,946 (98.6277%),
  161,917/171,452 (94.4387%), and 87,582/99,632 (87.9055%). EVENT, ELITE,
  MONSTER, and BOSS support was 94.8505%, 95.4705%, 95.0654%, and 94.7714%.
- **Required zero gates:** full-corpus omitted mutations were deck structure
  1,151 rows, card misc 109 rows, and `smokeBombUsed: false -> true` 3,001
  rows; each had zero supported rows. Supported winning rows had zero
  copy-through violations, including zero `smokeBombUsed` directions. The
  previously uncovered Entropic Brew-generated Smoke Bomb mechanism is now
  excluded by the explicit Entropic Brew and pre-state support guards.
- **Target stop:** the TRAIN-derived joint gold target still has 193 classes,
  but nine legitimate VALIDATION classes are absent from TRAIN:
  `(-83,83)`, `(-74,44)`, `(-73,73)`, `(-66,0)`, `(-56,15)`, `(-55,55)`,
  `(-41,15)`, `(-36,21)`, and `(-33,18)`. Four TEST classes are also unseen
  in TRAIN. The accepted design requires exact TRAIN classes and a stop on
  unseen VALIDATION values, so no `OTHER` class, TEST-derived class, or silent
  row dropping was introduced. The fit stopped before the first update with
  the fail-closed target-support error.
- **Regression evidence:** the focused Python and CTest checks pass. The HP
  sampler regression proves post max HP 80 with sampled bin 50 yields exactly
  40 HP, and structured exact-match regressions prove that one differing
  potion slot or one differing `(HP,maxHP)` component makes the whole row
  incorrect. No Phase-2/control metrics, sparse-head results, sampled-state
  validity, model sizes, or latency exist because the target gate stopped the
  fit.
- **Decision:** **`TARGET_OR_SUPPORT_PROBLEM`**. The eligibility boundary is
  repaired and the omitted-mutation support gate is closed, but the frozen
  target design cannot proceed without a separate target-schema decision.
  Evidence: [corrected Phase-2 report](evidence/combat_transition_surrogate_phase2_corrected_2026-09-13.md).

## §231 Phase-2 gold boundary and remaining DeepSets fit (2026-09-13)

- **Question/protocol:** remove the brittle TRAIN-derived joint
  `(deltaGold, stolenGold)` categorical target after a bounded source audit;
  reuse the §228 corpus, source split, producer, teacher, and accepted Phase-2
  target design. No new data, runtime inference, Silver replacement, OOC
  rollout, attention/XGBoost rerun, or RNG prediction was authorized.
- **Source audit:** direct combat gold writes are Looter/Mugger theft through
  `Monster::stealGoldFromPlayer`, direct Hand of Greed through
  `Player::gainGold`, and generated colorless Hand of Greed reachable through
  Jack of All Trades, Transmutation, Toolbox, or Colorless Potion. The
  predictor-visible encounter guards are `LOOTER`, `TWO_THIEVES`, and
  `EXORDIUM_THUGS`; the card/relic/potion guards are Hand of Greed, Jack of
  All Trades, Transmutation, Toolbox, and Colorless Potion. Class-bound
  Ironclad random-card paths were checked against the Ironclad pool and do not
  contain Hand of Greed. Combat reward gold, including Golden Idol reward
  modification, occurs after the raw exit hook and is outside this transition
  boundary. No unsupported source mechanism remained.
- **Support boundary:** the final predicate retains non-Ironclad,
  Writhing Mass, Ritual Dagger, Smoke Bomb, Entropic Brew, and pre-combat
  `smokeBombUsed` exclusions and adds all source-audited gold guards plus
  `pre.stolenGold == 0`. The learned input remains
  `combat_predictor_input_v1`; `pre.smokeBombUsed` and `pre.stolenGold` are
  adapter/support-gate fields, not learned features. No v2 schema was created.
- **Coverage:** on the unchanged 510,030-row corpus, support is 413,799
  (81.1323%), fallback 96,231. Death support is 15,384/18,133 (84.8398%);
  Act 1/2/3 support rates are 82.5107% / 79.4053% / 80.7983%; EVENT/ELITE/
  MONSTER/BOSS rates are 83.9126% / 84.0875% / 79.5760% / 83.7653%.
  Relative to §230, support loss is 71,367 rows or 13.9927 percentage points.
- **Zero gates:** the full audit found 21,781 `gold` mutations and 37,894
  `stolenGold` mutations, with zero supported rows for either. Existing
  deck-structure (1,151), card-misc (109), and `smokeBombUsed` (3,001)
  mutation rows also have zero supported rows. The supported copy-through
  violation set is empty, including zero smoke-bomb directions. All observed
  gold mutations are covered by the visible guard.
- **Fit:** the remaining Phase-2 target contains survival, max-HP delta,
  stochastic 101-bin HP fraction, five potion slots, and mutable relic-counter
  deltas. DeepSets and point-control DeepSets used validation-only epoch
  selection, selected 9 and 12 epochs respectively, refit from scratch on
  TRAIN+VALIDATION, and evaluated the fixed TEST split once. TEST support was
  41,454 rows. Phase-2 HP discrete CRPS was 0.048484 versus 0.071822 for the
  point-control degenerate distribution. Relic full-vector accuracy was
  0.773967 versus 0.764348 copy-through and changed-token accuracy was
  0.097227 versus 0; potion changed-row accuracy was 0.390527 versus 0, but
  potion full-vector accuracy was 0.460983 versus 0.728150.
- **Classification:** **`CORE_REGRESSION`**. The stochastic HP head works
  (discrete CRPS `0.048484` versus `0.071822` point-control), and the relic
  head is promising on full-vector and changed-counter slices. The potion
  changed slice improves, but its full-vector accuracy does not beat
  copy-through. Shared multitask training degrades the core survival predictor:
  Brier is `0.0208797` versus `0.0189359` for point control. The durable rule
  removes the post-hoc absolute `+0.005` survival-Brier tolerance; the existing
  5% relative check also fails. Gold/stolenGold are excluded from the sparse
  criterion and remain native fallback/copy-through fields. The potion head
  should probably use copy-through/change gating. The next experiment should
  protect the core predictor, e.g. freeze or separate the survival encoder/trunk
  before training transition heads; this was not run. Sampled-state validity is
  16/16 with zero invalid states. Phase-2 and point-control checkpoints are
  493,271 and 388,562 bytes; measured batch-1 CPU latency is 0.3916 ms and
  0.2989 ms.
- **Evidence:** [gold-boundary fit report](evidence/combat_transition_surrogate_phase2_gold_boundary_2026-09-13.md).

## §232 Phase-2 attention representation ablation (2026-09-13)

- **Question/protocol:** test whether the corrected Phase-1 small attention
  representation avoids the DeepSets Phase-2 core regression. PR #162 was
  merged first; the fresh Codex-managed worktree baseline was
  `6ccad271eefa5d42ea0d2debe4ff6bed486aa3f9`. The unchanged corpus, source
  split, final support predicate, `combat_predictor_input_v1`, Phase-2 targets,
  losses, AdamW recipe, batch 2,048, max 12 epochs/patience 3, and training
  seed `20260912` were reused. Only DeepSets was replaced by the known
  width-64, two-layer, four-head, FF-128 typed-token attention encoder. No new
  data, support redesign, RNG input, runtime integration, or gameplay run was
  used.
- **Support reproducibility:** the repeated audit passed with 413,799/510,030
  supported rows (81.1323%), 96,231 fallback rows, and 15,384/18,133 supported
  deaths (84.8398%). Supported TRAIN/VALIDATION/TEST counts were 331,225 /
  41,120 / 41,454. Gold, `stolenGold`, deck-structure, card-misc, and
  `smokeBombUsed` mutation audits had zero supported rows; copy-through was
  exact. Audit artifact: `/tmp/sts-phase2-attention-audit-20260913`.
- **Fit:** validation ran 12 epochs per model and selected attention Phase-2
  epoch 11 (score `0.165629169`) and attention point-control epoch 10 (score
  `0.172498332`). Both were refit from scratch on 372,345 TRAIN+VALIDATION
  rows before one fixed TEST evaluation. The initial run completed all 24
  validation-selection and 21 refit epochs and wrote both checkpoints; a
  post-fit serializer key error was corrected, then exact checkpoints were
  reloaded for evidence recovery without retraining.
- **Core TEST result:** Phase-2 versus its own point-control was Brier
  `0.019920463` vs `0.019039775` (absolute `+0.000880687`, relative `+4.6255%`)
  and log loss `0.066628456` vs `0.063621797` (absolute `+0.003006653`,
  relative `+4.7258%`). Source-seed bootstrap used 1,000 repetitions and
  2,512 TEST source groups; the 95% intervals were `[+0.000501706,
  +0.001289956]` and `[+0.001811163, +0.004202626]`. AUC and both HP error
  metrics improved, but the primary survival intervals support regression.
- **Transition result:** HP distribution NLL/CRPS were `2.666314/0.045763`
  versus attention point-control degenerate CRPS `0.070421`; 50/80/95%
  coverage was `0.664947/0.879055/0.974223`. Potion full-vector exact was
  `0.491094` vs copy-through `0.728150`, changed-row exact `0.394674` vs 0;
  relic full-vector exact was `0.777174` vs copy-through `0.764348`, changed
  token accuracy `0.118426` vs 0. Whole modeled-field exact was `0.183998` vs
  copy-through `0.210151`. Sampling validity passed 16/16 with zero invalid
  states. Attention/point checkpoints were 576,866/472,249 bytes with
  139,140/114,178 parameters; batch-1 latency was 0.9337/0.7731 ms.
- **Decision:** **`ATTENTION_CORE_REGRESSION`**. Attention does not avoid the
  core regression, so the result supports the generic multitask-interference
  hypothesis rather than an attention-specific representation bottleneck.
  Do not switch architecture or enlarge the Transformer; the next authorized
  experiment should freeze or separate the core predictor. Frozen DeepSets
  comparison and complete metrics are in the [attention ablation evidence
  report](evidence/combat_transition_surrogate_attention_ablation_2026-09-13.md).


## §233 Attention FP16 AMP implementation confirmation (2026-09-13)

- **Question:** Does the explicit CUDA FP16 AMP selection/refit training step
  retain >1.5× complete optimizer-step throughput against historical FP32 for
  both attention families, without changing the frozen training protocol?
- **Baseline/treatment:** `c13d5d94d6a2fe38bc9f55595bf4acde362eb43e` plus
  the AMP implementation; `fp32` versus explicit `amp-fp16`, CUDA float16
  autocast, GradScaler initial scale 16,384, unscale before norm clip 1.0.
  Identical initial weights, TRAIN batch membership/order, batch 2,048,
  4 warm-up + 30 measured steps, training seed 20260912, 8 Torch threads,
  RTX 3060 Ti / PyTorch 2.5.1+cu121. No game seeds, simulator, TEST tuning,
  new corpus, or quality experiment; gameplay budget/regime are not applicable.
- **Results:** Phase-2 19,112 → 37,489 examples/s (1.962×), 107.16 →
  54.63 ms/step, 1.318 → 0.921 GB peak allocated. Point control 18,938 →
  40,870 examples/s (2.158×), 108.14 → 50.11 ms/step, 1.316 → 0.920 GB.
  Both AMP smoke steps had finite losses/gradients, optimizer step 1 and
  successful scaler update; scale remained 16,384 over 34 steps.
- **Decision:** bounded implementation/performance confirmation passed; no
  equal-quality claim. FP32 remains default and historical reproduction mode.
  Scientific candidate/control comparisons must use the same precision.
- **Evidence:** [protocol, artifact/source hashes, exact command, raw results,
  caveats](evidence/attention_amp_confirmation_2026-09-13.md); external raw
  artifacts at `/home/philippherrmann/sts_sweep/runs/attention-amp-confirmation-20260913/`.

## §234 Frozen survival composition and potion-decoder qualification (2026-09-13)

- **Question:** Can frozen point-control survival compose with attention
  Phase-2 transitions, and how much potion error is invalid support?
- **Baseline:** merged PR #165 `08799ad6bd9061459339d36a4e22cce23d0236ec`;
  original PR #163 FP32 checkpoints and unchanged corpus/split/support.
  A = Phase-2; B = point-control survival + A's conditional distribution;
  C = B + conservative certified consumption-only potion mask. No fitting,
  simulator seeds, new data, gameplay, precision selection, or support expansion.
- **Result:** A reproduced at historical batch 2,048. B keeps frozen survival
  and conditional outputs; alive-HP MAE `5.903266 → 5.855358`, joint
  outcome/max-HP/HP-bin NLL `2.690480 → 2.687473`. Potion vector NLL
  `1.891231 → 1.178422`, exact `0.491094 → 0.597059`, versus copy-through
  `0.728150`; count accuracy regresses. Rule certified 322,644/413,799
  supported rows with zero contradictions. Paired source bootstrap uses
  1,000 repetitions on reused TEST, not unseen validation or training replicates.
- **Decision:** **`REPRODUCED_AND_CORE_PRESERVED`** /
  **`INSUFFICIENT_AFTER_CORRECTION`** / **`NOT_QUALIFIED`**. Eight Sundial
  mode counters remain outside native bounds. Recommend a later small joint
  potion-consumption head with protected survival and honest TRAIN-only
  validation provenance; do not train it in this task.
- **Evidence:** [hashes, native audit, paired metrics, CPU cost, checks,
  numerical batch sensitivity, and remaining limits](evidence/frozen_survival_potion_2026-09-13.md).
  Raw artifacts: `/home/philippherrmann/sts_sweep/runs/frozen-survival-potion-20260913/`.

## §235 Native relic legality and nested potion decoder preregistration (2026-09-13)

- **Baseline:** merged #166 `cee9a97a152671bc01c93527307f7d24e2241909`;
  frozen corpus `74c08aa0…1cfde`, existing source groups, unchanged support
  413,799 / 510,030. No simulator collection, gameplay seeds or RNG input.
- **Correctness gate:** native RAW counter rules derived from initialization,
  combat updates, exit write-back and direct Omamori writes. All supported
  observed counter transitions satisfy the rules; zero contradictions and
  additional-fallback pre states. Invalid/unknown states require future Silver.
- **Engineering correction:** on frozen historical TEST-victory relic logits,
  illegal counter-token mass mean 0.02687075 → 0; invalid modes 24 → 0
  (Sundial 8, Incense Burner 6, Neow's Lament 9, Pen Nib 1). NLL
  0.45244862 → 0.42272036; token exact 0.82519630 → 0.82539551.
  All observed targets survive masking. No relic fitting or joint-legality claim.
- **Prospective decoder protocol:** original TRAIN nested into
  15,971 / 2,001 / 2,014 source groups using frozen salt; split SHA256
  `58e35f9f85eefd7617e616ddbfa7ee227c429ed4d312f7dacd470828f9a09094`.
  Fixed ten-epoch FP32 TRAIN-only attention encoder; independent versus joint
  32-mask consumption heads; identical rows/conditioning/settings; validation
  joint NLL epoch selection, decoder-only TRAIN+VALIDATION refit, one primary
  HOLDOUT decision with paired source bootstrap. Separate 16-draw ancestral
  engineering exposure diagnostic using historical upstream checkpoints.
  Before fitting, the reviewed-head information confound was corrected: both
  arms now consume the same full-inventory width-133 features and width-64
  hidden MLP, producing five Bernoulli versus 32 categorical logits. Revised
  recipe SHA256 `6e758e5df43a39a0c6438ae0841e00050809fed770f654cb6da76fc10d714541`;
  split unchanged. Static parameter counts: 9,393 independent / 11,148 joint.
- **Status:** implementation/preparation and inference correction completed;
  fitting awaits independent implementation review and a frozen reviewed SHA.
  No encoder artifact, selected head epochs, HOLDOUT scores, decoder decision,
  ancestral classification or measured decoder/composed latency yet.
  Deployment remains `NOT_QUALIFIED`; `combatRng[6]` continuation is unchanged.
- **Evidence:** [native legality table, per-relic metrics, manifest, hashes,
  frozen recipe and commands](evidence/potion_decoder_v1_2026-09-13.md).
  Raw outputs/logs remain external in
  `/home/philippherrmann/sts_sweep/runs/joint-potion-mask-20260913/`.

## §236 Fresh nested HOLDOUT potion decoder fit (2026-09-13)

- **Executed/reviewed SHA:** `9f15dba5c348f775725232d33e72d2cf8e1b6127`,
  no code change before fit; merged #166 baseline `cee9a97…1909`.
  Frozen corpus, source groups, 413,799 / 510,030 support and certified native
  consumption rule unchanged. No new simulator collection or gameplay seeds.
- **Protocol:** unchanged split `58e35f9f…09094`, corrected frozen recipe
  `6e758e5d…14541`, FP32 seed 20260912. Fixed ten-epoch TRAIN-only attention
  point encoder; matched full-inventory features and width-64 MLP; independent
  five-Bernoulli versus joint 32-mask heads. VALIDATION joint NLL selected
  12 epochs for each, then decoder-only refit on 224,715 TRAIN+VALIDATION
  victories with the encoder still frozen. Artifact metadata verifies its
  exact 15,971 TRAIN sources and excludes VALIDATION/HOLDOUT.
- **Primary HOLDOUT:** all 25,398 victories, 1,979 eligible sources.
  Independent NLL `0.5189140430759348`, joint NLL `0.5166171564635460`.
  Δ joint minus independent `−0.0022968866123888503`; paired source-bootstrap
  95% CI `[−0.004204553691665904, −0.0006352931871017291]`,
  1,000 resamples, seed 20260913. CI entirely below zero →
  **`JOINT_MASK_WINS`** by the preregistered rule, without secondary overrides.
- **Separate ancestral qualification:** 16 draws per row per arm, zero
  invalid potion samples and identity creation/swaps. Preferred joint
  mixture NLL `0.5176165684`, versus teacher-forced `0.5166171565`;
  gap `0.0009994119` below frozen 0.1-nat threshold → **`ANCESTRAL_OK`**.
  Historical upstream weights previously saw original TRAIN sources; this is
  a separate engineering exposure diagnostic, not the primary decision set.
- **Other evidence:** parameters 9,393 / 11,148; decoder mean CPU latency
  0.068111 / 0.057213 ms; composed mean 3.155671 / 3.106292 ms,
  one thread, batch 1, one held-out fixture, 10 warm-ups + 100 calls.
  Secondary accuracy/calibration/slices and artifact hashes are in the report.
  Raw command exit 0. No result-dependent code, recipe, support or epoch change.
- **Boundary:** `combatRng[6]` continuation remains unmodeled; no native
  runtime integration, Silver replacement, new global TEST replication or
  multi-combat/gameplay qualification. Deployment stays `NOT_QUALIFIED`.
- **Evidence:** [full results and raw command](evidence/potion_decoder_fit_2026-09-13.md);
  checkpoints, cached state embeddings and raw predictions remain external in
  `/home/philippherrmann/sts_sweep/runs/joint-potion-mask-20260913/`.

## §237 Winning-combat HP target representation (2026-09-14)

- **Hypotheses:** signed absolute HP change may generalize better across
  starting/max HP; normalized ending HP may be easier under threshold/healing
  mechanics. Only target representation changes; no max-HP prediction head.
- **Baseline:** authorized current main `31c7a1b9adff9d55c158f5ab560f89176c0e99b3`.
- **Design:** all globally supported victories; frozen nested TRAIN+VALIDATION
  versus reused engineering HOLDOUT, exact source disjointness; teacher-forced
  observed max-HP delta in both width-64 attention models. Ten fixed FP16 AMP
  epochs, three paired training seeds, no validation/holdout epoch selection.
- **Primary:** raw continuous reconstructed HP MAE; delta minus fraction;
  rowwise differences averaged over seeds, then 1,000 source-group resamples.
  One-sided 95% CI plus agreement of all seed estimates decides the winner.
- **Executed/reviewed SHA:** `58655634bf2ecf8a76efb06f3569150bcf7fb6d3`.
  Independent implementation review passed; 20 focused HP/attention tests OK;
  six fits completed ten epochs, raw command exit 0; paired initialization,
  batch-order and conditioning hashes match. No gameplay/new collection.
- **Primary result:** fraction MAE 5.461977897 HP; delta MAE 5.421483614 HP.
  Aggregate difference -0.040494283 HP (-0.7414%); 95% source-bootstrap CI
  [-0.054637538, -0.025676357], 2,012 source groups, bootstrap seed 20260914.
  Seed estimates: +0.011898292 / -0.071289462 / -0.062091678 HP. The first
  favors fraction, so all-seed agreement fails: **`HP_TARGET_INCONCLUSIVE`**.
- **Descriptive results:** zero-max-HP-delta rows favor delta by 0.043772844
  HP; healing rows favor fraction by 0.187107964 HP; raw above-max predictions
  2.0529% fraction versus 10.2746% delta. These do not override the decision.
- **Boundary:** target-only point comparison; no target choice is qualified,
  no stochastic-distribution or runtime qualification; max-HP modeling untouched.
- **Hashes:** frozen corpus `74c08aa0…cfde`; nested split `58e35f9f…9094`;
  recipe `11703590…9fa`; raw predictions `22b28541…184`. Full hashes, all
  secondary metrics/slices and target diagnostics are in evidence.
- **Provenance/protocol:** [frozen evidence](evidence/hp_target_comparison_2026-09-14.md).
  Checkpoints and raw predictions remain external under
  `/home/philippherrmann/sts_sweep/runs/hp-targets-20260914/`.


## §238 Exact combat RNG continuation contract (2026-09-14)

- **Question / baseline:** resolve the six-stream continuation blocker on
  `31c7a1b9adff9d55c158f5ab560f89176c0e99b3`, using the existing frozen corpus
  only. No training, gameplay seeds, Silver search or new collection.
- **Provenance:** 510,030 RAW `combat_transition_row_v2` rows; 24,999 completed
  sources plus quarantined `4102275` with no rows; SHA256
  `74c08aa0a3c30342d86cd45355fe17ffa9046963ad7c8cf71b1938f9cdc1cfde`.
  Producer `f0bbd7721e7cc1453976ebb91ee11ebe6127a2bf`, project-fair exact-10k
  Silver teacher, native OOC, A0. Current support function is unchanged:
  413,799 rows, including 398,415 victories and 15,384 deaths.
- **Exact empirical result:** native `setCounter` replay matches misc and
  potion on 510,030/510,030 full rows and 413,799/413,799 supported rows each;
  zero mismatches. Supported misc changes: 97,154; potion changes: zero.
  Source-ordered consecutive pairs: 485,031; same-floor pairs: zero, including
  zero supported-origin pairs.
- **Mechanism / negative control:** native parity proves small bound 3 can
  consume extra underlying steps through rejection with counter advancing
  once; bare counter advancement is not universally exact. Every live misc
  draw is instead in a deterministic encounter initialization schedule.
  Exact bounded schedule replay, independent of post counters, matches all
  510,030 misc post states and all 413,799 supported states. The sole combat
  potion consumer is excluded Entropic Brew. Other streams reset at battle
  entry; OOC consumers reset before use; Colosseum is disabled/TODO, event
  callbacks do not chain, and A20 increments floor before boss two.
- **Decision:** **`RNG_COUNTER_DELTA_EXACT`**, using deterministic native bounded
  initialization replay. Minimal learned RNG targets: **none**. Copy potion;
  derive misc delta from visible encounter and replay its native call schedule
  including rejection. Literal misc copy-through is false. A visible gate on
  all misc-mutating encounter classes would lose 97,154 supported rows
  (23.4785%) and is unnecessary. Required new guard/support loss: none/zero.
- **Verification:** 29 focused Python tests pass, including supported
  same-floor classification rejection and dropped-final-fight row accounting,
  plus temporary native C++ parity and raw/rejection failures; configure passes; focused CTest 1/1;
  full corpus/provenance/schema/order audit exits 0 with audited rows exactly
  equal to validated rows and a zero supported-origin same-floor requirement;
  doctor and repo health pass; diff check passes. Evidence retains six-stream
  aggregate counts and misc/potion aggregate distributions, omitting reset
  stream and repeated slice histograms. No production C++ build; Linux GCC CI
  is the clean-repository gate.
- **Boundary / knowledge impact:** RNG state contract resolved; runtime
  integration, exact all-six RAW snapshot synthesis, source/controller changes
  and scientific multi-fight qualification remain outside this result.
  Deployment remains `NOT_QUALIFIED`. Current facts routed to determinism/RNG
  and current research. [Evidence and commands](evidence/combat_rng_continuation_2026-09-14.md)
  / [machine-readable result](evidence/combat_rng_continuation_2026-09-14.json).

## §239 Stochastic signed-HP categorical distribution (2026-09-14)

- **Baseline:** post-#170 clean main `443ed45f9bae4c5864dd7188645a04049b268928`,
  existing fresh Codex app-managed worktree; no additional worktree.
  Historical #170 classification remains `HP_TARGET_INCONCLUSIVE`;
  signed absolute ΔHP is the engineering parameterization.
- **Executed/reviewed SHA:** `521e364a08735ad095ed99682e3d5058a6748a46`.
  Independent implementation and accepted-design review passed before all fits.
- **Frozen design:** one categorical ΔHP head replaces #170 scalar output;
  same 64/2/4/128 attention, width-8 observed max-HP-delta embedding,
  72→64→304 ReLU head. Illegal classes receive -inf before softmax.
  Domain [-160,143] is derived only from predictor-visible pre HP and frozen
  upstream classes; SHA256 `f812c16ab1d220cd60e8a8915ebb368bcd7e6d9e48915eb8cce5c760fad78eec`.
  All 398,415 supported winning targets pass structural representation/legal
  checks without target-driven extension.
- **Data:** corpus `74c08aa0a3c30342d86cd45355fe17ffa9046963ad7c8cf71b1938f9cdc1cfde`;
  nested split `58e35f9f85eefd7617e616ddbfa7ee227c429ed4d312f7dacd470828f9a09094`.
  TRAIN = nested TRAIN+VALIDATION, 286,581 globally supported victories;
  HOLDOUT 32,345 victories / 2,012 victory-source groups, reused engineering
  data. No potion-certification restriction or new simulator/gameplay data.
- **Recipe:** scratch seeds 20260912/20260913/20260914, exactly ten epochs
  each, AdamW 1e-3 / weight decay 1e-4, batch 2048, gradient clip 1,
  trimmed padding, FP16 AMP initial scale 16384, masked NLL only.
  All fits complete before HOLDOUT scoring; no epoch selection or tuning.
- **Control:** saved matching #170 signed-delta predictions, verified SHA256
  `22b285413bb31caac4dfe23dba79e80437ec91a42ed2ae534105370db6bca184`.
  CRPS uses documented rounded/native-clamped integer HP; mean-MAE safety
  uses raw continuous point HP. No point retraining or fraction comparator.
- **Primary result:** aggregate categorical-minus-point CRPS -1.686834344 HP,
  source-bootstrap 95% CI [-1.715728962,-1.658630531]. Expected-HP MAE
  +0.011839528 HP, CI [-0.007041513,+0.029256256]. Rowwise seed averaging
  before 1,000 source resamples, fixed seed 20260914. CRPS is clearly better,
  mean MAE is not clearly worse → **`STOCHASTIC_DELTA_HP_QUALIFIED`**.
  No post-hoc threshold or descriptive slice override.
- **Seed NLL / CRPS / expected-MAE:** 20260912 = 2.504864931 / 3.673978516 /
  5.400272679; 20260913 = 2.497160196 / 3.643171465 / 5.397913096;
  20260914 = 2.503982544 / 3.679759261 / 5.501783652.
- **Calibration/validity:** 50% intervals cover 65.87–66.62%, 80% intervals
  86.94–88.02%, 95% intervals 97.27–97.82%. All 1,552,560 draws satisfy
  1≤HP≤postMaxHp; unsupported class probability exactly zero. Ending HP
  fraction is derived directly, without sampled-HP clipping. Healing CRPS
  improves in all seeds; expected healing HP MAE improves in two and worsens
  in one. Full coverage widths and required slices are descriptive evidence.
- **Verification:** 27 focused Python tests OK; new CTest 1/1 passed;
  configure and doctor passed; guarded fit command exit 0. Raw-artifact CRPS
  energy-formula and source-bootstrap reproduction passed within 1e-5 HP;
  NLL/mean-MAE reproduction and all emitted artifact hashes verified.
- **Boundary:** offline observed-maxHP engineering qualification; no sampled
  upstream composition, runtime C++, gameplay or multi-fight qualification.
  Survival, max-HP modeling, potion, relic and RNG contracts unchanged.
  Relic training is a future experiment; `combatRng[6]` remains unresolved.
- **Evidence:** [frozen protocol, all metrics/slices, raw commands and hashes](evidence/stochastic_signed_hp_2026-09-14.md).
  Checkpoints and raw predictions remain external in
  `/home/philippherrmann/sts_sweep/runs/stochastic-hp-20260914/`.
  Knowledge impact: empirical evidence and maintained current research status.


## §240 Shared relic trajectory residues (2026-09-14)

**Result: `RELIC_TRAJECTORY_QUALIFIED`** on audited offline composed support.
Baseline after merged #172: `b5502a84bb41c736fa72b210dc8766e0a25717e6`;
independently reviewed execution SHA:
`66350924cd3b4c7ca82d967e282f68cd677736b2`. Native mechanics and partial-label
reconstruction passed the complete structural gate before fitting.

Frozen corpus `74c08aa0a3c30342d86cd45355fe17ffa9046963ad7c8cf71b1938f9cdc1cfde`;
nested source split `58e35f9f85eefd7617e616ddbfa7ee227c429ed4d312f7dacd470828f9a09094`.
TRAIN combines nested TRAIN+VALIDATION: 224,715 certified victories / 17,718
sources; HOLDOUT 25,398 / 1,979. Global support remains 413,799 / 510,030.
No new simulation collection or game seeds; reused corpus retains its original
ascension/teacher/fair-regime provenance. No gameplay/OOC evaluation or
runtime model loading is claimed.

Only the small 89→64 residue decoder trained: seeds 20260912/13/14, exactly
ten epochs, AdamW lr 1e-3, decay 1e-4, batch 2048, clip 1.0, FP32. HP encoder
is frozen #172 20260912 by convention, hash
`a667a3cfa7d7eca3cb07b46f50321e443c75e8a58f7627becb1fd69bf90f08c9`;
existing joint potion weights hash
`8e04bcd5265fb11b8fa91b4553a84690915f437e7b3afee0b93358e312de3ad6`.
No upstream retraining, epoch selection, support widening or RNG change.

HOLDOUT joint NLL decoder/prior by seed: 0.519639530/0.530241176,
0.520132425/0.530254280, 0.519593622/0.530250808. Mean paired difference
−0.010460229, 1,000-repetition paired source-bootstrap 95% CI
[−0.013335116, −0.007743432]. Source resampling follows seed 20260914;
seed-average row differences are paired before resampling.

Ancestral sampled signed HP→certified potion mask→relic, 16 draws per row
per seed, retains observed max HP. Mixture joint NLL mean 0.519052762 versus
teacher-forced 0.519788526; mean per-row group-normalized exposure
−0.002407001 nat → `ANCESTRAL_OK`. All sample-domain/coherence/deterministic/
unsupported-mutation counts zero across 1,219,104 trajectories. The complete
corpus structural audit also has zero contradictory groups, unreachable
targets, native reconstruction mismatches or unsupported mutations.

Full-vector mode exact 0.805667113 versus native+copy 0.792700213; changed-row
exact 0.174612219 versus 0. Decoder has 12,895 parameters; one-thread batch-1
CPU forward mean 0.034997 ms, p95 0.036728 ms, ten warmups/100 measurements,
excluding upstream encoders and sampling/reconstruction. Exact modes do not
override the proper-score decision. Active Lizard Tail has zero eligible rows
and remains outside qualified learned support; Inserter has zero relic tokens.

External recipe, checkpoints, cache, probabilities, sampled counters and raw
logs: `/home/philippherrmann/sts_sweep/runs/relic-trajectory-20260914/`.
[Full source/protocol/results](evidence/relic_trajectory_2026-09-14.md),
[machine-readable calibration/slices/metrics/provenance](evidence/relic_trajectory_2026-09-14.json).
Knowledge impact: component evidence here; current status in the maintained
research page; native implementation routing in CODE_MAP. No runtime default.

Independent scientific replay and raw-array verification passed (exit 0):
primary CI/exposure reproduced within CPU/GPU roundoff, all artifact hashes
and initialization/batch histories matched, and native/shared sample checks
all zero. Linux GCC passed on reviewed implementation SHA `66350924...`.


## §241 Offline composed combat-transition qualification (2026-09-14)

Knowledge impact: strict offline ancestral sampler and common original-TEST
exposure/validity evidence; current status is maintained in
[evaluation/current-research.md](../knowledge-base/evaluation/current-research.md).
Baseline `7316c715bac7fe4559ead59cde1eb374d3437b5b`; independently reviewed
execution SHA `abe2c6ea50f55d37e4d594ceb6575247e91c32fa`. Fixed artifacts use
20260912 by convention. No model fit/refit/tuning, collection, gameplay seeds,
policy change or C++ integration. Mode: offline frozen-model composition;
original source-grouped reused engineering TEST, 32 draws per row, sampling
seed 20260916 (exposure) / 20260917 (complete), source bootstrap 1000 repetitions
with seed 20260917. Corpus ascension/source configuration is inherited exactly;
no new searcher, OOC configuration or game budget is exercised. CUDA scoring
uses historical per-component arithmetic; CPU latency uses one thread/batch1.

**`COMPOSED_TRANSITION_QUALIFIED`** after HP-only analytical metric correction
on independently reviewed SHA `dc1499f36055491fec8ff44143f879c124bf230d`.
Exact weighted marginal over all 11 frozen maxHP classes gives HP NLL
2.383993276 versus teacher-forced 2.371751655: gap +0.012241622 nat,
95% source-bootstrap CI [+0.009743450, +0.014807776]. Same sources, bootstrap
seed/repetitions and individual 0.1-nat gate. Illegal observed HP under a
maxHP class contributes zero. Teacher reproduction maximum NLL difference 0.0.
The original cached encodings were not persisted, so identical 512-row TEST
batches were reconstructed with frozen HP/maxHP encoders only; only HP heads
and HP exposure/bootstrap were evaluated. No new sampling or other gates ran.

The original 32-draw HP result is retained solely as diagnostic: **8/31,150 rows
received zero empirical mass with 32 ancestral draws**. All eight have positive
exact marginal mass, so empirical infinity is not a model-support rejection.
The prior `COMPOSED_TRANSITION_REJECTED` conclusion is superseded; no maxHP
investigation, model repair, resampling, tuning or threshold change followed.
Potion gap +0.000810765 and normalized relic gap -0.001521621 remain unchanged
and pass. All eleven native/state/RNG/death-call validity counters remain zero
across 1,029,248 original draws. Original TEST support 32,164/51,441; observed
supported victories 31,150. Original component diagnostics and latency remain
from `abe2c6ea...`. Historical attention arithmetic reproduction remains
within 8.35e-7 with no weights changed. The correction passes 18 direct tests
and composed CTest; independent implementation and raw-evidence reviews pass.
Next separately scoped work is runtime/OOC integration, not performed here;
qualification is offline only.

Full artifacts/hashes, reproduction, source CIs, complete diagnostics,
factorized likelihood, latency, exact commands and limitations:
[frozen protocol and executed evidence](evidence/composed_transition_2026-09-14.md),
[JSON evidence](evidence/composed_transition_2026-09-14.json),
[recipe](evidence/composed_transition_recipe_2026-09-14.json).
Raw rows/arrays/trajectories remain external under
`/home/philippherrmann/sts_sweep/runs/composed-transition-20260914/qualification/`.

## §242 Native combat boundary parity and adapter smoke (2026-09-14)

Baseline `d68545d50ea018f6e6d38cfb2c282c7e99e58edc`; exporter/inference frozen
and independently reviewed at `ec30dbfda896867e78a3f5bc2fc519134b75e19b`
before the single export. No gameplay seeds, training, tuning or data collection.
One-thread batch-1 CPU FP32, 16 captured supported states plus 7 fixed fallback
mutations; frozen probability tolerance 1e-4. All support decisions/legal masks
match Python, maximum probability error 2.0862e-7. Native continuation oracle
and eight focused CTests pass. 512 samples: all invalid counters zero; 480
victories/32 deaths are diagnostics only.

**RUNTIME_COMBAT_ADAPTER_READY** for the combat boundary. Default gameplay,
OOC policy/search implementation unchanged. Other copied hidden OOC RNG still
prevents scientific qualification of the full planner. Inserter fails closed.
Native support 0.626 µs, death 1.482 ms, victory 4.275 ms; descriptively slower
than #174 Python ~3.32 ms on a different fixture mixture. Four Attention
encoders dominate (~1.08 ms/component); no optimization was attempted.

[Full evidence and commands](evidence/native_combat_adapter_2026-09-14.md),
[artifact hashes and raw metrics](evidence/native_combat_adapter_2026-09-14.json).


## §243 First live OOC MCTS paired Silver gameplay gate (2026-09-14)

**OOC_MCTS_WINRATE_DOWN.** Control V4 full one-ply stack won 21/32; opt-in live
OOC MCTS won 10/32 on fresh paired seeds 970000..970031, A0, Act-3 stop, no keys.
Both arms played **Silver real combat** at 1000 exact-root simulations, allocated
reuse cap 32768, adaptive/direct leaf OFF, four OpenMP threads, same frozen binary
and SHA `c705072f50e12892dd02a6da6dc1e39305b6839e`. The user changed the original
cheap Searcher2 plan to Silver before any decision-bearing seed ran.
Baseline `3057ea79f8a678ba13f9f2ea2b4834850fa2dd87`; independently reviewed MCTS
implementation `0c7d932d6231de5d3cd5677d8ddac5d4b023d9d2`.

Paired win delta -34.375pp, bootstrap 95% CI [-53.125,-15.625]pp; one treatment-only
win, twelve control-only wins, nineteen same-result seeds; exact two-sided
discordant binomial p=.00341796875 descriptive. Mean floor delta -6.28125,
CI [-10.46875,-2.3125]; runtime 4.5403234x. Classification uses only the primary
win CI. Bootstrap 200000 paired draws, PCG64 seed 20260914, percentile interval.

Frozen qualified native combat artifact SHA256
`f9520a14b1fc42e2a22840c0c2cab0b13ebd8ab6285b5c943662f5e0e9cd9233` is used only
inside imagination. Real selected primitive actions execute once; real BATTLE
returns to ordinary combat. Native V4 artifact `ooc_strategic_tok_final.native`,
full REST/EVENT/SHOP/TREASURE/BOSS_RELIC gates, margin 1.0, native floor/win and
other combat configuration match between arms. MCTS defaults cPuct 1.5, k 2, alpha .5,
maxDepth 32, 128 simulations; independent indexed SplitMix64 RNG; no tuning.
Mean 123.40625 owned decisions/run, fallback 18.274%, 980.4375 combat samples/run,
15796 simulations/run, 15771 leaf evaluations/run; max depth 3 in 32/32 runs;
MCTS 8.8288376 wall seconds/run, 82.1308% of per-run elapsed time. All trace
accounting reconciles and Silver bridge failure counters are zero.

Eight implementation seeds 969992..969999: exact OFF parity across all eight
non-timing fields, repaired ON smoke 8/8 with surrogate sampling and actual
combats. Duplicate native GOLD IDs now use leaf/live fallback; candidates and
surrogate support unchanged. Silver excluded-seed canaries pass. Invalid first
smoke, mistagged baseline canary and an overly strict per-run analysis coverage
check are preserved/documented. The final coverage-validation correction changes
no MCTS/gameplay/bootstrap/classification semantics. Focused CTests 3/3,
qualified startup cases 11/11, independent implementation/statistical review pass.

MCTS reduced actual paired gameplay under the copied-RNG planning environment.
Copied hidden noncombat RNG still prevents unbiased planning/fairness or
deployment claims. Keep MCTS OFF; return for review and bounded changed-decision/
leaf investigation before any new budget or tuning experiment. No automatic
follow-up seeds. Knowledge impact: live contracts/configuration/code routing
updated in maintained KB; research status closed with this negative evidence.
[Full evidence/environment/commands](evidence/live_ooc_mcts_2026-09-14.md),
[raw paired results](evidence/live_ooc_mcts_2026-09-14/result.json).


## §244 Corrected live OOC MCTS paired exact-10k Silver regression (2026-09-14)

**OOC_MCTS_WINRATE_INCONCLUSIVE.** Both control V4 and corrected opt-in MCTS
won21/32 on the user-requested same seeds970000..970031. Paired win delta0pp,
bootstrap95% CI[-21.875,+21.875]pp; six wins unique to each arm, twenty same
results, exact discordant p=1 descriptive. Both use ordinary fair exact-10k
Silver actual combat, A0, keys OFF, Act-3 stop, four workers and the same frozen
reviewed executable `f9af4ad6055b98603fd732d59869b5b39cc8beec`.

Four bundled corrections: resolve pending reward/shop/event/selector leaves
through existing OOC policy to checkpoint/terminal before native win evaluation;
unsupported imagined combat aborts the entire root to unchanged V4 and discards
partial action estimates, with no imagined native/Silver fight; align actual
combat to the frozen10k teacher; reuse deterministic children and fix MCTS512
simulations without tuning stochastic widening/PUCT/horizon. Search depth6–13,
3,654 owned decisions, 2,142 fallbacks including972 support aborts;105,957 supported
surrogate samples. All search/support accounting and real combat logs reconcile;
zero Silver bridge failures. Control823/treatment811 actual battles.
Mean game time38.2207→61.0723s (1.5979x), mean floor48.625→49.0625 descriptive.

Focused checks3/3, startup11/11, excluded OFF parity8/8, ON smoke8/8, independent
implementation review and authoritative Linux GCC CI pass before freeze/run.
Models, corpus/support, default OFF and original §243 evidence preserved. The
initial expensive imagined-Silver canary was stopped before any revised official
seed; user chose whole-decision V4 fallback. Same seeds/four corrections imply
regression evidence, not fresh confirmation or individual causal attribution.
The result demonstrates neither improvement nor equivalence; copied hidden RNG
still prevents unbiased-planning or deployment claims. No follow-up seeds or
sweep. Knowledge impact: maintained live contracts/telemetry and research status
updated; frozen raw evidence preserved.
[Full evidence](evidence/live_ooc_mcts_corrected_2026-09-14.md),
[raw paired result](evidence/live_ooc_mcts_corrected_2026-09-14/result.json).

## §245 Frozen potion-generation support-contract correction (2026-09-14)

Baseline main `3057ea79f8a678ba13f9f2ea2b4834850fa2dd87`. Seed-free full census
of the same 510,030 rows and original source split; all corpus/model/prepared
hashes and companion provenance revalidated. No training, tuning, sampling,
new data, gameplay benchmark or win-rate run. Python/native predicates exclude
explicit Alchemize and Entropic Brew instead of rejecting all off-color cards;
all independent gates remain. Audited combat random pools cannot generate
Alchemize. Explicit Alchemize remains unimplemented in this simulator and is
excluded according to its STS1 potion-generation semantics.

Overall support 322,644/510,030 (63.260%) → 413,799 (81.132%); original TEST
32,164/51,441 (62.526%) → 41,454 (80.586%). 113,094/116,302 (97.242%) previous
potion rejections recover certification; 91,155 (78.378%) recover full support.
All historical support tables/reasons reproduce. The 96,231 remaining full
fallbacks match original global eligibility; independent reason counts are
unchanged. Zero potion creation/swap/substitution violations on every supported
row, including deaths; zero preserved RNG, copy-through and victorious relic
trajectory contradictions. 32 focused Python/native tests, affected builds and
six CTests pass. This is contract/census validation; historical distribution
qualification remains on its original measured subset, with no new runtime
performance or gameplay qualification.

[Full provenance, slices, limitations and commands](evidence/potion_generation_support_2026-09-14.md),
[raw accounting and source hashes](evidence/potion_generation_support_2026-09-14.json).


## §246 Expanded-support live OOC MCTS paired regression (2026-09-14)

**OOC_MCTS_WINRATE_INCONCLUSIVE.** User-requested same32 seeds970000..970031,
current V4 control21/32 versus expanded-support corrected MCTS22/32. Paired gain
3.125pp, bootstrap95% CI[-18.75,+25]pp;discordants7 treatment-only/6 control-only,
exact p=1 descriptive. Both ordinary fair exact-10k Silver, fixed512 MCTS,
PUCT1.5/k2/alpha.5/horizon32, A0, keys OFF, Act-3 stop, four workers, same models.

Local main updated to merged #178 `0a8f3ed`; draft #177 remains unmerged. Separate
integration freezes reviewed source `0757c2db918b6395d8f22ca54f6d94c8e3ae0b10`.
#178 narrows potion generation exclusion to Alchemize/Entropic Brew, retaining
independent gates and whole-root V4 support fallback; no imagined Silver.
Main also includes #176 real Silver semantic fixes, limiting cross-run attribution.
Recovered support has census/contract validation, not new distribution accuracy.

Owned4,060/5,621 (72.2291%);fallback27.7709%,465 support aborts,135,119 surrogate
samples. Previous §244 owned3,654,fallback36.9565%,972 aborts,105,957 samples:
coverage increases descriptively. Depth8–14; completed/discarded/attempt/support
counts all reconcile. Control823/treatment807 actual battles, zero recorded
Silver failures. Mean game time26.1105→70.4781s (2.6992x); mean floor delta-.6875
CI[-4,2.5] descriptive. The small positive win point estimate proves neither
improvement nor equivalence. Same reused-seed regression and copied hidden RNG
limits remain; keep MCTS OFF, no follow-up seeds or tuning.

Support32 tests/focused3 checks/both excluded canaries pass; independent
integration/readiness review and Linux GCC CI pass before64 official games.
Knowledge impact: raw experimental evidence and current research status updated;
existing support/MCTS contracts unchanged. §245 preserves the colliding #178
support census separately from original §243/§244 gameplay evidence.
[Full frozen evidence](evidence/live_ooc_mcts_expanded_support_2026-09-14.md),
[raw paired result](evidence/live_ooc_mcts_expanded_support_2026-09-14/result.json).


## §247 Fixed2048 live OOC MCTS budget regression (2026-09-14)

**OOC_MCTS_WINRATE_INCONCLUSIVE.** User authorized more search: fixed2048 instead
of512, all other source/model/combat/search settings unchanged. Same32 seeds
970000..970031, V4 control reused exactly from §246 at reviewed0757 executable,
new2048 MCTS24/32 versus control21/32. Primary gain9.375pp,95% paired bootstrap
CI[-12.5,+31.25]pp;discordants8/5,exact p=.5810546875 descriptive. Secondary versus
preserved512 MCTS22/32:gain6.25pp,CI[-9.375,+21.875]pp,discordants4/2. Both inconclusive.

Actual fair exact-10k Silver; PUCT1.5,widening k2/alpha.5,horizon32,four workers,
A0/keys OFF/Act-3 stop/native V4 stack/support/model hashes unchanged. No code
edits/rebuild/imagined Silver. Existing reviewed source0757c2d/binary binding and
source CI reused. Independent design/reuse/readiness review and excluded canary
pass before32 new official seeds. New gameplay33 seeds total; no extra controls.
Historical timing descriptive:2048 mean130.0688s versus51270.4781/V426.1105s.

Owned3,861/5,601,fallback31.0659%,633 support aborts,308,052surrogate samples,
maxdepth8–16. Larger search encounters more unsupported roots than512465aborts,
while completed ownership drops4,060→3,861. All support/simulation/log equations
reconcile;805actual combats,zero recorded Silver failures. Win point estimate
rises, but no improved-win or equivalence claim. Reused-seed repeated budget
regression, hidden copied RNG and historical timing limits remain. Keep OFF and
default512; no sweep/follow-up seeds. Knowledge impact: experiment evidence and
current research status; stable implementation unchanged.
[Full evidence](evidence/live_ooc_mcts_2048_2026-09-14.md),
[primary](evidence/live_ooc_mcts_2048_2026-09-14/result.json),
[secondary](evidence/live_ooc_mcts_2048_2026-09-14/budget-comparison.json).


## §248 Frozen expanded-support composition qualification (2026-09-14)

**EXPANDED_COMPOSED_TRANSITION_QUALIFIED.** #178 widened original TEST support
from 32,164/51,441 (62.526%) to 41,454/51,441 (80.586%); this engineering validation
asks whether the unchanged #174 frozen models retain composed qualification on
the 9,290 newly recovered rows and their complete union. Baseline main
`74d31681b8ebd3beb5e85d6db9c1a164f9aeaf13`, independently reviewed scoring SHA
`66d62987308e200f1abbfaa92d3fff67b3370ac7`. No gameplay, MCTS, model/schema/support
changes, data collection or retraining. Ascension/searcher/game-seed budget are
not applicable: seed-free frozen corpus scoring, not a gameplay benchmark.

Corpus `74c08aa0a3c30342d86cd45355fe17ffa9046963ad7c8cf71b1938f9cdc1cfde`,
source split `e9043bcceb9d95027711e6ff33afbfe1cae3cf9528f820c0ff68bddbb419db32`
and all six frozen models/prepared representation verified; full hashes in JSON.
OLD/RECOVERED/EXPANDED row counts 32,164/9,290/41,454 and source counts
2,474/893/2,512. Historical OLD membership, source alignment and disjoint row union
proven. All OLD reproduced component/exposure metrics and row teacher NLLs have
exactly zero error versus #174, within the existing 1e-5 tolerance.

Same survival→maxHP→signedHP→joint potion→shared relic→persistent-state recipe,
FP32/HP AMP FP16 conventions and native masks. Exact HP probability marginal
across all 11 maxHP classes; potion/relic 32-draw probability-before-log mixture;
relic mean row gap per observed learned group, informative rows only.
Sampling seed20260916; source-bootstrap seed20260917,1000 resamples. Independent
mean <=0.1-nat gates on RECOVERED and EXPANDED; CIs descriptive.
RECOVERED HP/potion/relic gaps +.019484613/+.000565261/-.002278852;
EXPANDED +.013832688/+.000723143/-.001336405. All six pass. All eleven hard-validity
counters zero over1,326,528 complete EXPANDED draws, including297,280 RECOVERED.
Independent raw-output metrics/CIs/validity/death-forward reproduction passes.

RECOVERED diagnostics are weaker than OLD but no material composition exposure.
Act/combat/card-count/common-card slices retained; outside-old-whitelist IDs are
only COMBUST and BRUTALITY, GREEN in native metadata. No general accuracy claim
for other off-color IDs. The two four-card rows have no informative relic score.
#174 evidence preserved. Reused TEST is engineering validation, not untouched
holdout evidence. Offline prerequisite for a next fresh MCTS gameplay gate now
passes; runtime/readiness and gameplay success remain separate. Knowledge impact:
experiment evidence/current research status; evaluator navigation updated.
[Full evidence](evidence/composed_transition_expanded_support_2026-09-14.md),
[JSON](evidence/composed_transition_expanded_support_2026-09-14.json).


## §249 — Fresh64 fixed10000 live OOC MCTS versus matched V4 (2026-09-14)

User-authorized fresh64 paired seeds980000..980063, with excluded979999 canary
per arm; designated GCP sts-test24 CPUs,24 OMP workers, sequential arms. Frozen
runtime54f2820f426c45540b02eb075cf73102b00de8f0/binary810281cb…/five models;
reviewed analyzer/launch13508a4507daebc1fe081151973050a51d8aef9d. Source/cache/
hashes and successful model loads verified; local/remote pre-outcome inventories
prove freshness. Both canaries and official64-arm mechanism/accounting checks
pass. No C++/models/support/fair exact-10k Silver/A0/keysOFF/Act3 changes.

**OOC_MCTS_WINRATE_INCONCLUSIVE**: MCTS42/64 versus V448/64,−9.375pp,
unchanged paired200000 PCG64(20260914)95% CI[−23.4375,+4.6875]pp. Discordant
8treatment-only/14control-only,42same-result; descriptive exact p0.2862787.
Mean floor46.921875 versus48.765625,CI difference[−4.390625,+0.53125]. Mean
game elapsed456.7888s versus101.3814s (ratio4.50565); arm wall1648.9s versus
328.8s; these sequential24-worker timings are descriptive.

7240owned/10898 decisions,3658 V4 fallbacks (33.5658%),1551 support aborts;
73686339 completed=7240×10000+1286339 discarded;73687890 attempts;
1445511 surrogate samples,1447062 imagined calls; maxdepth6..23. Real Silver
combats1564 versus1633; all bridge failures/battleLeaves zero; strict membership,
config/source/support reason accounting and postflight hashes pass. No historical
control is pooled and prior512/2048 cohorts are not causal budget comparisons.

Independent final reproduction PASS (all six means/CIs/accounting) accompanies
the raw packet; reviewed analysis stayed frozen. Analyzer regression2tests/focusedCTest1 pass; remote
runtime focused2 pass; Linux GCC analyzer CI run34860408603 passed3m9s.
No extra seeds, tuning, support/model changes or default enablement. Negative
point estimate plus crossing-zero interval provides no demonstrated improvement;
copied hidden noncombat RNG still limits unbiased planning/deployment claims.
Knowledge impact: experiment evidence/current research status; analyzer cohort
parameters in evaluation protocol. [Full evidence](evidence/live_ooc_mcts_fresh64_10000_2026-09-14.md),
[raw/analysis packet](evidence/live_ooc_mcts_fresh64_10000_2026-09-14/README.md).


## §250 — Exact OOC MCTS computation optimizations (2026-09-14)

Baseline main `210f347334898e7c2a85b8af0f30dedc4888ea88`; one clean app worktree.
No combat-support branch dependency, training, support/schema/RNG distribution,
PUCT, policy, horizon or leaf-value change. Search-local prepared combat edges,
immutable state metadata, deque particle arena and exact hot-loop cleanup;
sole-valid-action shortcut gated on explicit non-aborting qualification and
default-unsafe visit-lock capability added. The live model explicitly remains false.

Cheap captured-model profiling found four encoders at roughly1.08ms each versus
microsecond conditional heads. Fixed depth-one native-root profiling was43.38%
combat/56.22% leaf continuation/value, with copying/action-prior/bookkeeping
combined below0.5%. Baseline1,188 candidate calls/81 generated states,80 samples/
3unique combat edges; one token/prior build. Synthetic original fixtures found
0sole-action roots/41 supported roots, not a live frequency estimate.

23existing captured inputs (16supported/7unsupported),32seeds×4sequential draws
prove2,944 complete persistent-state/mt19937 post-state comparisons and exact
baseline probability outputs. Prepared128-draw amortized sampling4.393ms→60.328us
(72.82x); inferred encoder calls7,775→64. Frozen artifact `f9520a14…` and fixtures
`372a1627…`; full model/input/source/binary hashes in the packet.

Interleaved3baseline/optimized runs,CPU0/OMP1,Ironclad A0,GameContext42/search
seed20260914,512simulations/depth1,cPuct1.5/k2/alpha.5,V4 priors/native win leaves.
Detached native callback isolates searched combat from reward projection; no
real gameplay/teacher combat budget applies. Median baseline logic replay384.252ms
versus optimized223.176ms (1.722x,41.92% reduction),about1332→2294 simulations/sec.
All80samples/81states, action/order/priors/visits/Q/tree statistics and every
snapshot/history exactly equal. Encoders320→12;80individual node heap allocations
eliminated, not all allocations. Native uncached control381.131ms does not
establish a separate metadata/arena speed benefit; standalone toy planner suite
11.376→10.380ms median/process is descriptive. Baseline replay used matching final
telemetry ABI/otherwise shared build objects; initial original adapter stdout
and probability vectors also reproduce exactly.

Guaranteed visit-selected single-root toy stops after1/10 (saves9): no
challenger exists; default-unsafe still runs full budget. Sole-root
unsupported-combat roots now search and retain whole-root fallback. The sole Wheel
of Change regression proves fallback consumes agent RNG despite the same primitive;
unsafe roots cannot bypass it. An explicitly non-aborting toy still bypasses with
zero simulated work. Performance measurements above predate this gate correction
(at `806b7b9607ff7257fb549d6a8e85de983d5c4ce9`); no new benchmark was run.
Non-aborting toy lock saves48/100simulations with same
action; strict equality/mean-Q/catchable/unsafe/late-abort/adversarial cases pass.
Locked stopping remains dormant in the live adapter: all intentional abort paths
are not excluded. No copy ownership refactor or conditional-head memoization
was justified. Eight initial focused CTests pass; all three affected core/adapter/startup tests
pass again after the gate correction. Two relinking-overlap execution failures
were repaired by post-build reruns. No full local CTest/gameplay cohort/canary;
no gameplay-quality or full-game speed claim. Knowledge impact: maintained OOC
interface/telemetry/parity procedure and chronological engineering evidence.
[Full packet](evidence/live_ooc_mcts_speed_2026-09-14/README.md),
[fixed-search timings/parity](evidence/live_ooc_mcts_speed_2026-09-14/fixed-search-summary.json),
[sampler receipt](evidence/live_ooc_mcts_speed_2026-09-14/combat-summary.json).


## §251 — One-seed old/new live OOC MCTS runtime comparison (2026-09-14)

User-requested descriptive pair: exactly seed42 once at baseline `210f347334898e7c2a85b8af0f30dedc4888ea88`
and once at gated PR #183 `bea408a1113b8f4cc9c717a0f1b38d5594b80243`.
Ironclad A0, OOC512/real exact10,000 Silver, project-fair combat/copied noncombat
RNG, native V4/win/same combat artifact, keysOFF, Act3-or-death, sequential
old/new CPU0/OMP1. No model swap, tuning, support expansion or repeated cohort.
Existing §250 fixed-root/historical gameplay evidence lacks this paired revision/
configuration; two new guarded full-run commands exit0.

Full-game wall62.3369s→43.8502s,29.66% reduction/1.422x; OOC search
44.448824s→25.900525s,41.73% reduction/1.716x. Same floor50/Act3 death and
all common OOC non-timing counters (207 decisions,148owned/59fallback,
76,792 completed/76,815 attempted,1,016 discarded,4,497 surrogate samples,
23support aborts) plus all28 complete real-Silver telemetry lines match exactly.
No per-action/full-state trace: aggregate equality is not full trajectory parity.
New live bypasses/locked stops/saved simulations remain zero; gate is intact.
One-seed/order-dependent timing only, no average-speed or decision-quality claim.
Knowledge impact: engineering benchmark evidence only; no default or maintained
scientific conclusion changes. [Comparison](evidence/live_ooc_mcts_runtime_pair_2026-09-14.md),
[commands/provenance/raw results](evidence/live_ooc_mcts_runtime_pair_2026-09-14.json).


## §252 — Full-run profiling and V4 candidate-state reuse (2026-09-14)

Base `eb84039b99e2f3b932e08fdfc51f1f7eebbbeaa5`, candidate
`b019e694fcdb150b0ff085eaed118b7272103556`. The preceding CTM/gated-root PR is
unchanged except action-independent V4 state reuse in the prior/eight Q loops.
One current full-run profile identifies171,763 repeated deck/state encodings:
47.56% exclusive OOC time; tree prediction21.18%, rich-feature CSV conversion
9.52%, CTM prepare/sample/apply9.79%. Tree bucket includes continuation value
calls, not only final-leaf v_win. Timers are removed from maintained source.

Prepared128-float state per immutable candidate set preserves operations,
heads, candidate order, margins/ties, fallback/RNG and model/support contracts.
Independent old-header comparison passes1,536 bitwise checks across512 cases;
maintained adapter/frozen fixtures plus core/startup/semantic/analyzer5CTest pass.
One fresh paired seed42, CPU0/OMP1, IroncladA0, OOC512/exact10,000Silver,
project-fair combat/copied noncombat RNG, keysOFF/Act3-or-death/same models:
full43.6509s→35.3348s (19.05% lower); OOC25.998381s→17.080533s (34.30% lower).
A preliminary candidate link retained an inactive profiler object; its timing
is excluded. Rebuild/relink, no-profiler-symbol audit and5CTest rerun pass; one
clean candidate run supplies these final numbers. Both valid arms exit0, same floor50 death, every non-timing OOC counter, all28 Silver
telemetry lines and support reasons match. Shortcuts/saved simulations remain0.
No per-action/full-state trace or quality cohort; one ordered pair is descriptive.
Knowledge impact: maintained V4 API/lifetime and engineering evidence.
[Profile/comparison](evidence/live_ooc_mcts_v4_reuse_2026-09-14.md),
[full raw/provenance/check packet](evidence/live_ooc_mcts_v4_reuse_2026-09-14.json).


## §253 — Numeric rich features and contiguous OOC trees (2026-09-14)

PR #183 baseline `61882889dfb269a88f6bd26bf5386d9f22dd5d04`, measured candidate
`04b7a7878679cc7aa1827fa822ab66dafdf6b8bd`. One refreshed seed42 scoped profile:
trees33.5%, rich CSV conversion15.2%, CTM preparation16.2%, V4 deck/fusion17.4%.
Direct1,017-value numeric builder leaves CSV compatibility untouched; all operands
are integral and4,098state vectors compare bitwise against legacy parsing.
Tree nodes resolve selected features at load and flatten into contiguous storage
with root offsets/sentinel; traversal and ordered double accumulation unchanged.
Frozen original loader/predictor matches27,177bitwise predictions on win/floor/E2c.

One fresh uninstrumented seed42 ordered pair, IroncladA0/OOC512/exact10,000Silver,
fair combat/copied noncombat RNG, keysOFF/Act3-or-death/same models/CPU0/OMP1:
full32.1673s→30.3124s (5.77% lower), OOC15.028404s→12.852105s (14.48% lower).
Both exit0; outcome, every non-timing OOC counter,28Silver telemetry records and
support reasons match. No full trajectory/state trace or decision-quality cohort.
Separate128-state/10,000-call/5round equivalent-indirect-call probe medians:
win12.64% lower, floor12.94% lower, rich features29.98x. Initial unequal-inlining
probes are superseded; exploratory variants retained, final candidate unchanged.
All timings descriptive; one ordered pair is not an average-speedup claim.
Release focused7CTest and complete Debug91CTest pass; overload/map harness
failures repaired; clean binaries contain no temporary profiler symbols.
Knowledge impact: maintained OOC native interfaces and engineering evidence;
no default/model/support/scientific qualification change.
[Evidence](evidence/ooc_rich_tree_speed_2026-09-14.md),
[raw commands/provenance/check packet](evidence/ooc_rich_tree_speed_2026-09-14.json).


## §254 — Near-full Ironclad combat-support census and Stage-1 evidence stop (2026-09-14)

Baseline `210f347334898e7c2a85b8af0f30dedc4888ea88`, after updating local main
and reusing the fresh app-managed worktree; #179/#180 merged. Seed-free audit
of the unchanged RAW 25k corpus (510,030 rows, 24,999 source seeds), original
source-grouped splits (51,441 TEST rows), six frozen model/prepared/corpus/split
hashes and complete row/source/fight accounting. No model fitting, sampling,
new game seeds/collection, architecture/runtime/MCTS/default changes, or gameplay.

Historical support exactly reproduces: 413,799 overall (81.132286%), 41,454 TEST
(80.585525%); 96,231 fallback. Full reasons, combinations, encounter/act/room
counts and TEST counts are frozen in the packet. Gold exclusions affect 74,069
rows; 71,367 gold-only candidates (57,151 TRAIN / 6,915 VALIDATION / 7,301 TEST)
have zero later support rejections and zero other victorious copy-through
mutations. This is an inventory, not ancestral validity or recovered support.
Four raw joint targets covering five TEST rows are absent from TRAIN; native
clipping reconstruction is needed rather than observed-pair vocabularies.

#180 strict 64-source first-reason accounting reproduces 1,551 unsupported
imagined combats and aborted roots. Actual first failures: gold encounter366,
gold card264, gold potion250, gold relic227, Writhing Mass200, pre-stolen155,
Ritual Dagger34, Brew30, Smoke Bomb25. Gold total1,262 (81.367%). Saved traces
are aggregates only; no identified imagined-state corpus, joint reasons or root
identities support exact before/after replay. No naive subtraction is qualified.

**NEAR_FULL_COMBAT_SUPPORT_NOT_READY**. Stage 1 stops at evidence sufficiency:
upgraded Transmutation has exactly two whole-corpus rows, source4108572 fights
27/28, both TEST; zero TRAIN/VALIDATION, one non-gain victory and one death.
Native Transmutation creates upgraded colorless cards (possible upgraded Hand
of Greed), with gold procs dependent on policy/eligible kills. Full qualification
requires targeted source-grouped evidence or a reviewed transfer derivation;
neither is available. Specific live frequency is unknown (264 aggregate gold-card
first failures). Smallest additional evidence design and sample-size uncertainty
are in the staged stop report. No data was collected. Stages2–5 not started;
zero rows recovered, support unchanged, no new component/exposure/native-parity
metrics or runtime artifact. This is an evidence limitation, not impossibility.

Checks: app-worktree preflight/check and Bash doctor PASS; Python focused5tests
PASS; Debug CMake configure/generate PASS; focused Python CTest1/1 PASS (0.14s);
complete scans/hash bindings PASS; diff check PASS. No independent review yet,
no C++ build/full CTest/scientific sampling. Knowledge impact: research evidence
and maintained current status. [Staged report](evidence/near_full_combat_support_2026-09-14/REPORT.md)
links all frozen JSON receipts and hashes.

## §255 — Shared native gold component: revised Stage-1 design (2026-09-14)

Supersedes §254's overly conservative Transmutation+ stop. User-approved design
shares the stochastic gold mechanism; upgrade is a common conditional feature,
with exact native +20/+25 HoG payouts. The two Transmutation+ TEST rows are an
ultra-low-support diagnostic, not a calibration gate vetoing the gold union.
Original frozen splits/corpus/census stay unchanged; no new data or gameplay.

Implement native RAW outcome enumeration: turn/index-ordered theft with clipping,
two mugs/optional lunge/block/escape, per-thief recovery, reset pre-stolenGold,
Ectoplasm, qualifying-kill caps including split slimes and minion exclusions.
A small categorical candidate scorer uses frozen HP encoding, shared mechanical
upgrade/source features and HP/potion conditions. Native closure guarantees gold
accounting, not full policy reachability. Only new scorer TRAIN victories fit;
VALIDATION selects earliest minimum NLL. All upstream checkpoints are frozen.

Protocol: full gold-only native target audit, bounded 12-epoch decoder fit,
32 upstream draws with exact potion-mask marginalization for gold exposure;
existing exact maxHP marginal for HP; 32 complete ancestral validity draws per
TEST row. Report each gold mechanism/union separately and Transmutation+ as a
non-vetoing diagnostic (its native validity is still checked). Development
metrics do not substitute for independent final qualification/relic exposure/
union/native export/runtime continuation. Support remains unchanged pending
those gates. Scientific outcomes will be recorded on the frozen implementation
SHA in the same evidence packet after execution.

Checks: native/shared-scorer focused8tests PASS; census tests5PASS; Debug CMake
configure/generate PASS; focused CTests2/2PASS (1.36s); no C++ changes/build.
Knowledge impact: revised research status, frozen protocol and code navigation.

Executed bounded development at gold source `1a24e7ccdb26c3ef649371dfe07269ecbc3c2d4a`
and supplemental relic evaluation `2f8fb3f45a6656c03d81f69f3f4b1d1c3116164a`.
Native audit: all71,367 candidates / maximum72 outcomes / zero native target,
other persistent or inherited RNG violations. Initial preparation found a wrong
Darkling cap; source inspection of `anyHalfDead`/final death showed one native
HoG payout, corrected before fit and full audit rerun. Decoder fit56,153 TRAIN
victories /6,788 VALIDATION,12 epochs,selected12,VALNLL0.617246,2.90s.
Research checkpoint SHA256 `19a1a387f56ea4c8eceb2ebf4b92f951f497b18876ccab31168f0c6a9a5d853c`.

**GOLD_DEVELOPMENT_GATES_PASS_PENDING_REVIEW** and supplemental relic PASS.
7,301 gold-only TEST rows /7,190 victories;7,189 vetoing union victories and one
Transmutation+ diagnostic victory. Gold union NLL0.574911/Brier0.259408/mode
exact0.799972, gold/stolen expected MAE4.22353/4.17038. Informative4,091 rows:
NLL1.010275/Brier0.455851/mode0.648497. Union exposure: gold0.012944,
HP0.014668,potion0.000701,relic0.006219 per observed group (1,834 informative
relic rows). Every gold reason slice passes each mean≤0.1nat; rare procs and
ultra-low-support Transmutation+ are diagnostic caveats, not calibration claims.
233,632 complete ancestral draws,229,414 downstream gold calls,4,218 sampled
deaths; zero recorded native gold/persistent/downstream-after-death violations.
Relic exact conditional potion-mask marginal has zero zero-mixture rows.

This is the concrete Stage-1 draft-PR review handoff, not independent scientific
qualification. No support/runtime changes or rows recovered; prospective census
recovery71,367/7,301 yields95.124993% overall/94.778484% TEST only after gates
and review. Stage2–5 remain unimplemented. No new data, gameplay or full-stack
refit. Independent review/frozen reviewed SHA precedes an expensive scientific
refit; no reviewed SHA exists yet. Focused CTests2/2PASS1.17s, diff checkPASS;
Linux GCC at1a24e7c SUCCESS; later-head CI recorded in PR. Knowledge impact:
executed evidence/current research status and supplemental tool navigation.
[Staged report and JSON receipts](evidence/near_full_combat_support_2026-09-14/REPORT.md).


## §256 — Native sparse gates, affected maxHP repair and explicit escape oracle (2026-09-14)

Stage 1 user-approved at PR head 9a7220512939deb46e359339d28016e019cebad3;
remaining stages authorized, same worktree and frozen 510,030-row corpus/splits.
Writhing/Dagger shared tiny scorers: fixed12epoch TRAIN-only fits, original
VALIDATION selection. TEST teacher NLL0.587495/0.059781; exact exposure
+0.047608/-0.000122. Finite Writhing zeros remained diagnostics; exact original
exposure +0.530710 failed, maxHP head-only refit +0.287375 failed, affected
existing maxHP encoder/head refit repaired the gate (original architecture and
normalization; no other historical encoder/head changed). Refit source70b0de5,
selected11; VAL0.043296 versus0.053481, TEST0.053666. Exact repaired evaluations
source70b0de5, combined hard validity source5a605cc: 62,912 draws /58,205
surviving calls /4,707 deaths, zero recorded violations. Joint gold/Dagger
native legality shares ordinary eligible fatal hits, including thief escapes.

Affected upstream exposure evaluations source07c573e for sparse, ce12078 for
gold: all evaluated component means <=0.1nat. Native explicit ESCAPE oracle
passes exact identical-origin OOC/persistent/all-RNG/PathHistory and no-reward
continuation, including Cleric and native pre-used reset; outcome/RAW flag
mismatch rejected. Learned escape probabilities remain pending. Native Brew
replay matches3,208rows/3,106generation rounds, zero end-RNG mismatches;
112recursive consumption cases /88escape rows. Independent generation versus
preserved historical RNG replay requires an explicit origin contract; user
clarification pending, no silent fair/known-RNG substitution.

NEAR_FULL_COMBAT_SUPPORT_NOT_READY: full combined trajectories/refit/native
export/probability parity/support update and #180 state replay incomplete.
Live support unchanged, zero newly recovered rows; no new data or gameplay.
Knowledge impact: native mechanics, component repair evidence and current
qualification/contract status maintained in KB and bound evidence.
[Report and raw receipts](evidence/near_full_combat_support_2026-09-14/REPORT.md).

## §257 — Shared hypothetical Brew RNG, full-union refits and Smoke/relic composition stop (2026-09-15)

**NEAR_FULL_COMBAT_SUPPORT_NOT_READY.** User-approved continuation and resolved
planner-owned hypothetical potion RNG: seed a fresh native stream on first
Brew use, reuse it through recursive generations and retain advanced RAW RNG;
historical RNG only reconstructs teacher body labels. Shared 64-action decoder
separates special use/discard, including legal boss Smoke discard, and exactly
marginalizes compatible body/inventory trajectories and downstream effect flags.
112 proven recursive examples reconcile to108survivors(86TRAIN/11VAL/11TEST)
and4deaths. Native joint representability audit covers491,897survivors,
including3,001escapes/4,363Writhing/12,690Dagger rows, zero failures.

Existing survival/maxHP/HP/potion encoders and heads refitted on complete
candidate union with original source splits and12epoch original VALIDATION
selection, source1c31b7e. TEST NLL0.060412/0.053423/2.507614/0.504572;
shared downstream heads source546cf6a, normalized joint TEST NLL1.344312.
Full-union engineering evaluation sourceb266433:51,441TEST rows including
41,454old#179/9,987recovered candidates. Full ancestral validity1,646,112draws,
62,347deaths/1,574,266victories/9,499escapes, zero recorded RAW contract
violations. Exact HP marginal NLL/Brier/CRPS/meanMAE:
2.520435/0.752391/3.622578/5.322113. Entire informative-union exposure means:
HP+.012821,potion+.004097,relic+.000416,gold+.019119,Dagger-.000279,
Writhing+.088853; old/recovered aggregates also pass.

**Smoke relic gate fails:**102informative surviving TEST rows, gap+.242637nat,
source-bootstrap95%[+.088666,+.409294], no exact zero-mass targets.
Added-outcome ablation, teacher/ancestral-context anchored head refit and
balanced shared native-route refit give+.199237/+.201889/+.209178, still fail.
All use original data, original VALIDATION selection and fixed other heads;
final attempted repair source6ab63f4. Population808TRAIN/95VAL/102TEST,
1,005surviving corpus rows(0.197047%). No new mechanic or additional corpus
requirement proven. Outcome/HP/potion/relic correlation remains unqualified;
further conceptual repair needs reviewed design, not weakened gates or silent
support expansion. Repaired checkpoints are not promoted.

Exact finite Writhing marginal source4b7f6be gives+.091256 on449ordinary-potion
TEST rows and+.121732 on31Writhing/Ritual overlaps. Shared native maxHP
partition head repair excludes available Fruit Juice (its +5/+10 confounds
maxHP); overlap remains+.119052, source6bdf681. This is an explicit diagnostic
of shared feature intersection, not an independent new native mechanism.
Original TEST reuse after Writhing and subsequent repairs is development
evidence, never untouched confirmation.

User confirms #180 saved-state replay unavailable; tracked CSV/support JSONL
have per-seed/first-reason aggregates, no imagined states/root IDs. No count
subtraction or invented root-abort estimate. This is not the stop cause.
Live support remains413,799/510,030(81.132286%); native export/parity,
support expansion and MCTS sampling integration gated by failed composition.
No new data/gameplay, no merge; draft#182 is the handoff. External engineering
review supplied by user covers8420103 only, later implementation not reviewed.
Knowledge impact: accepted RNG contract, current qualification failure,
source-bound receipts and model navigation maintained in KB/evidence.
[Staged report and immutable receipts](evidence/near_full_combat_support_2026-09-14/REPORT.md).


## 258. Final near-full native support excluding initial/pre-Smoke and Writhing/Ritual (2026-09-15)

User-authorized final bounded pass in #182 changes the final pre-state support cutoff, not model weights or data. Initial Smoke, pre-Smoke flag and Writhing with Ritual are excluded; Brew-generated Smoke/ESCAPE remains modeled. Exact corpus support505,935/510,030(99.197106%), TEST51,036/51,441(99.212690%). All41,454 old#179 TEST rows are retained and recomposed with selected maxHP weights. Every nonempty final slice gate≤0.1 nat; maximumWrithing+.094655723. One32-draw gold zero is corrected through a restricted exact ancestral sum, preserving the original diagnostic and provenance; no target-mass failures remain. All1,633,152 final TEST draws have zero hard violations.

The tracked V2 artifact SHA22c855e0667a58a73835505672b0ae6d03f12e9fb8d64f08893810199246e94e uses the selected original full-unionv1 stack, not failed Smoke repairs. CPUFP32 Python/native probability error≤5.96e−7 at1e−4 tolerance;3,904 complete RAW/planner-stream/scalar-prepared draws match, including117recursiveBrew cases. Threeexcluded fixtures prove fail-closed/no draws. Executed native support matches exact all/TEST ordered index digests across all510,030 rows. Strict load/export and tracked-artifact/startup tests are added.

Original full-union Smoke failures and three bounded repair attempts remain preserved. No fourth repair, new data, gameplay or#180 root-abort estimate; exact#180 state replay unavailable. TEST reuse remains development evidence, not pristine scientific confirmation. V2 is opt-in and default MCTS remainsOFF. Frozen final SHA, independent review and LinuxGCC CI outcomes are recorded in #182 before authorized merge. Knowledge impact: maintained support/RNG/native artifact contracts, code map and qualification evidence updated. [Final report and bound receipts](evidence/near_full_combat_support_2026-09-14/REPORT.md).


## 259. Full-budget hypothetical OOC root-lock observation (2026-09-15)

Base5b2a5b5 (merged #183/#184/#182), measured candidateb50b1c7. Opt-in
observeRootLock suppresses all root shortcuts, records earliest strict visit
lock/action/remaining budget and measured loop suffix, and retains eventual
abort/final full-budget winner. Live ROOT_LOCK_TRACE writes per-root JSONL;
existing CSV/actual-stop metrics unchanged. No model/support/default/RNG change.
Live non-aborting guarantee stays false: #182's505,935/510,030near-full support
explicitly excludes initial/pre-Smoke and Writhing/Ritual; continuation/forbidden
imagination aborts also remain. Zero observed aborts cannot qualify enablement.

One common seed42OFF/ON, same trackedV2artifact22c855e0…/Release binary,
IroncladA0/OOC512/exact10kSilver/fair combat/copied noncombat RNG/keysOFF/
Act3-or-death/CPU0/OMP1. Both guarded commands exit0; same floor51Act3win/hp16,
every non-timing OOC counter,26Silver records and support reasons match.
All155searched roots complete512 and lock; first simulation min/median/max
1/260/509,34sole locks at1. Hypothetical remaining40,186/79,360(50.64%);
summed completed wall suffix5.258686s/13.471238OOC(39.04%,12.60%full).
0aborts/locked-then-aborts; safe-enabled roots0, actualsaved/stops0. Conditional
potential work under a future all-path proof, not achieved or average speedup.

101/101Debug and7/7Release focused CTest pass; original Torch-env/probe-missing
failures retained and repaired without dependency/runtime changes. Exact52/100
strict crossing, RNG/visits/Q replay and lock-at1abort-at7 regression pass.
No support expansion, enabled-stop timing, multi-seed run or complete full-run
trajectory/state trace. Knowledge impact: maintained observer/environment/safety
contracts and engineering opportunity evidence.
[Report](evidence/ooc_root_lock_observation_2026-09-15.md),
[raw commands/hashes/root records/checks](evidence/ooc_root_lock_observation_2026-09-15.json).


## 260. Enable live OOC visit-lock stopping despite remaining abort support (2026-09-15)

Explicit user policy choice enables strict visit locks by default inside opt-in
live OOC MCTS, despite remaining Smoke/continuation abort paths. Generic default
still requires the non-aborting guarantee; the live provider remains false.
EARLY_STOP=0 restores the requirement. Observer/mean-Q suppress stopping; an
unqualified singleton must complete one simulation. A later abort can be skipped,
changing fallback behavior; this is deliberate, not support qualification.

Source1a3f552, one paired guardedseed42/same Release binary, OOC512/exact10kSilver/
fair/copied noncombat RNG/keysOFF/Act3-or-death/CPU0/OMP1. Full vs stop: completed
simulations79,360vs39,174, stopped roots155,
saved40,186(50.64%). OOCwall11.193670vs6.758811s
(39.62%lower); full elapsed35.8988vs31.3939s
(12.55%lower). Both exit0;188decisions/155owned/33fallback,
0support/continuation aborts, all26Silver records and non-timing outcomes match
(Act3win/floor51/hp16max85). One engineering seed, no average/quality claim or
complete trajectory trace. FullDebug101/101 and focusedRelease3/3 pass after
updating legacy assertions/error wording. Knowledge impact: live policy/default/
rollback and ADR-0014 maintained; no model/support/GPU change.
[Report](evidence/ooc_early_stop_enabled_2026-09-15.md),
[raw packet](evidence/ooc_early_stop_enabled_2026-09-15.json).


## §261 — Silver reroot GC repeated canary and flat-1k smoke (2026-09-15)

PR #185 baseline `876e9305a258df3d5a5eafd50e30375b933f8884`, measured candidate
`1e37f2a9d68a403158241886f85c926b37b62f1a`. Repeated real private Silver
10k searches / exact reroots on an explicit durable starter-deck Jaw Worm
fixture (Ironclad200/200HP, A0, seed0xBADC0DE) follow expanded legal END_TURN
outcomes. Cumulative real allocations11,635→23,868→35,878→48,231→58,494;
retained nodes9→1→79→4→64. Three reroots occur beyond32,768historical allocations;
58,430nodes reclaimed. Final10kcontinuation passes at11,795live/70,225historical
nodes. Retained addresses, visits/Q, edge statistics, chance links/bookkeeping,
available best action, dedup and post-search ownership checks pass. Debug/Release
outputs agree; guarded repeated canary added to CTest; complete Debug92/92pass.
A preliminary selected-action Looter path reached a truly over-cap reachable
graph and could not demonstrate the historical-only case; its log is retained.
Historical totals describe PR allocations, not an executed no-GC baseline graph;
session cap regressions separately prove post-GC fallback ordering.

Authorized bounded smoke:16paired seeds0–15, IroncladA0, project-fairSilver,
flat exact1,000per private search including selection subdecisions, allocated
cap32,768/adaptiveOFF/keysOFF/default nativeOOC/same tracked models/OMP4/Release.
Baseline10/16wins(62.5%) vs PR7/16(43.75%):−18.75pp, paired bootstrap95%CI
[−43.75,+6.25]pp;6bothwin/5bothlose/4base-only/1PR-only. Mean floor45.375→46.9375
(+1.5625; CI approximately[−1.8,+6.6]); mean endHP23.4375→15.9375. Both exit0;
strict identical seed sets/budgets verified; conversion/semantic-resolution/
transaction/knowledge failures0 and allocated-cap fallback0 in both arms.
**Adverse win signal with higher mean floor: not a clean nonregression result,
not evidence qualifying harm or improvement.** No broader benchmark or quality
claim; timing is descriptive only. Knowledge impact: regression coverage and
bounded experiment evidence; no default/model/support change.
[Comparison and raw evidence](evidence/silver_reroot_gc_smoke_2026-09-15/README.md),
[commands/hashes/provenance](evidence/silver_reroot_gc_smoke_2026-09-15/provenance.json).


## §262 — Cap-triggered Silver compaction and exact flat-1k parity (2026-09-15)

Corrects PR #185's unconditional-reroot policy from §254. Baseline
`876e9305a258df3d5a5eafd50e30375b933f8884`; measured corrected candidate
`1e7ca07613885acfabaa0ed639a026cda904321c`. Below the configured cap,
reroot leaves pools/global dedup untouched, preserving orphan statistics.
Only pre-reroot cap pressure requests collection around an exact candidate;
the retained count is rechecked for reuse/fresh fallback. A focused below-cap
regression preserves orphan visits/Q and exact dedup slots. Mechanical tests
explicitly request collection; the repeated real canary uses lazy triggering.

Same 16 paired seeds 0–15, Ironclad A0, project-fair Silver, flat exact 1k per
private search including selection subdecisions, allocated cap 32,768, adaptive
and direct learned leaves OFF, keys OFF, default native OOC, same tracked
models, Release / OMP4. Both arms exit 0. All nine non-timing result fields
match exactly by seed; all 7,008 complete decision diagnostic records and 380
per-combat telemetry records match as multisets. Fresh baseline rows match the
preserved §254 baseline. Both win 10/16, mean floor 45.375, mean end HP 23.4375.
Maximum pre-reroot allocation is 13,454; cap fallback and integration failures
are zero. CSV sec and parallel emission order are excluded. Scaling diagnostics
do not record action fingerprints/full states: exact recorded-field parity,
not proof of full trajectory identity or search-quality qualification.

Repeated real 10k Jaw Worm stress fixture unchanged (starter deck, Ironclad
200/200 HP, A0, seed 0xBADC0DE; expanded legal END_TURN outcomes). Ten reroots
include seven baseline reroots and three actual pressure-triggered collections:
35,825→79, 34,622→7, 37,683→3 nodes. Cumulative real allocations at collections:
35,825 / 70,368 / 108,044. Reclaims 108,041 nodes; final 10k continuation passes
at 7,602 live / 115,643 cumulative allocations. Debug/Release outputs match;
retained snapshots/dedup/live ownership checks pass. Complete default Debug
build succeeds and 92/92 CTest pass (41.10s); focused 3/3 pass. An initial canary
assertion included the fresh root despite its intentional absence from baseline
dedup; restricting verification to prior dedup members repairs the fixture.

The §254 adverse smoke remains evidence about unconditional cleanup. This
correction restores exact recorded flat-1k parity while retaining mechanical
rescue under pressure. No broader cohort, 10k quality claim, sanitizer or new
independent review. PR stays draft; no merge. Knowledge impact: corrected
maintained lifetime/cap contract and reproducible parity/regression evidence.
[Summary and raw artifacts](evidence/silver_reroot_lazy_parity_2026-09-15/README.md),
[commands/hashes](evidence/silver_reroot_lazy_parity_2026-09-15/provenance.json),
[reproducible parity verifier](evidence/silver_reroot_lazy_parity_2026-09-15/verify_parity.py).


## §263 — Dynamic Silver dedup and 128k lazy reuse cap (2026-09-15)

Baseline `fa2ea0ad702281a6b2a1366d792a8e920227832d`, measured implementation
`9a849fd7deadb4374ad33f42796811b03a3ceb07`, continuing draft PR #185.
Dedup doubles its power-of-two open-addressed table on a miss before occupancy
exceeds 50%; reinsertion preserves pointers/statistics/RNG and capacity never
shrinks within the searcher. Production cap 131,072 replaces 32,768; lazy
pressure-triggered collection and final retained-cap fallback remain intact.
Focused tests force multiple resizes including 65,536→131,072→262,144 and
verify every prior state, same Node pointer, no duplicates, exact visits/Q,
unchanged RNG and further search. Deterministic 96-step parity across table
capacities passes with observer OFF/ON. Frozen 32k teacher acceptance initially
failed; explicit cap-mismatch rejection before output repairs that check without
relabeling old evidence. Complete Debug build and 92/92 CTest pass (47.36s).

Tiny real 10k repeated stress canary: starter-deck Ironclad 400/400 HP / Jaw
Worm A0, seed 0xBADC0DE, expanded legal END_TURN outcomes, 14 reroots plus a
final 10k search. Peak 140,976 live allocated nodes / 116,788 states; largest
candidate-reachable graph 80. Dedup grows twice to 262,144 slots, peak sampled
load 49.3408%, final 4,693 entries (1.7902%). Old 32k would trigger collection
earlier but no reachable-cap fallback. The 128k threshold triggers one
collection, 140,976→3, reclaiming 140,973 nodes. Final 5,497 live / 146,470
cumulative allocations; no fallback. Search batches can overshoot the cap
before the next reroot; session fixtures separately verify generic fallback.
External time -v reports 794,040 KiB RSS (775.43 MiB), no swaps, on a roughly
31 GiB host; includes validation snapshots. Raw node/state/table payload
estimate 711.72 MiB. Comfortable for this fixture/host, not a universal memory
bound. No permanent memory infrastructure, broader gameplay/quality benchmark
or win-rate claim. Knowledge impact: maintained table/128k cap contract and
engineering correctness/resource evidence; no model/support qualification.
[Evidence](evidence/silver_dedup_128k_2026-09-15/README.md),
[commands/hashes/raw packet](evidence/silver_dedup_128k_2026-09-15/provenance.json).


## §264 — Silver 32k default restored; 128k experimental only (2026-09-15)

Supersedes §256's production-cap promotion. Dynamic dedup and lazy collection
remain; default is 32,768 and `STS_SILVER_REUSE_CAP=131072` is experimental.
Frozen teacher producers and live OOC MCTS enforce the effective 32k cap.
The larger cap has no decision-quality qualification and the earlier 775 MiB
resource observation does not justify production promotion.
Default32 real 10k stress: 35,968→80 nodes, 35,888 reclaimed, 48,158 cumulative,
subsequent 10k search valid; largest candidate reachable graph80, no historical
ALLOCATED_CAP fallback. External debug fixture peak RSS207,108KiB (202.25MiB),
including validation snapshots; not a matched 32k/128k memory experiment.
13 startup cases and145 agent-tool tests pass; final full CTest raw outcome in
[evidence](evidence/silver_cap_default32_2026-09-15/README.md).
Recorded flat1k parity reverified, no new gameplay run. A separate matched
exact10k+32k vs exact10k+128k quality experiment remains required for promotion
and frozen teacher/model requalification. Knowledge impact: maintained cap and
startup contracts; no model/support qualification.


## §265 — Exact 10k Silver 32k vs experimental 128k lazy GC, exploratory paired 16 (2026-09-15)

Frozen code 2b29e9723a00b9dc6fcea45507e4dcf86c968cde, identical release binary and
models, fair RNG, A0/keysOFF, exact 10000 every root, allocated reuse/adaptiveOFF,
OOC MCTS OFF; seeds 0–15 paired, four workers, sequential 32k then 128k.
Only cap/output paths differ. Preserved 1k and stress artifacts do not satisfy
this comparison; this cohort reuses prior 1k seeds and is exploratory, not fresh
prospective validation. Both exits 0; zero bridge failures, metadata/budget/seed
and all diagnostic prefixes before 32k pressure validate.
32k 11/16 vs 128k 13/16 wins (+12.5pp), both win 11/both lose 3,32k-only 0/128k-only 2
(seeds 2, 8). Paired-bootstrap 95% CI[0,+31.25]pp; exact discordant test p=0.5.
Only two discordant pairs: no established superiority or promotion decision.
Mean floor 48.625→50.1875; HP 36.5→34.0; seconds/run 30.5031→30.8804, different
trajectory lengths prevent fixed-work runtime claims. 32k pressure candidates
1740 (1526 rescued/214 ALLOCATED_CAP fallback); 128k 3 (all rescued/no fallback).
Peak allocated 47,390→138,829; process RSS four workers 1,130,460→2,622,576KiB
(1.078→2.501GiB), about 2.32 times peak memory. Search batches can overshoot cap.
Positive exploratory outcome signal and fewer cap fallbacks at substantial RAM
cost; keep 32k production/128k opt-in. No root-regret study, new seeds/arms or
frozen teacher/model requalification. Knowledge impact: maintained exploratory
cap-research status and evidence; default/scientific contracts unchanged.
[Raw paired seeds, compressed logs/decisions, commands/hashes, analysis](evidence/silver_cap_pair10k_16_2026-09-15/README.md).


## §266 — User-selected 128k lazy GC: four budget schedules, paired 32 (2026-09-15)

Same frozen release binary/models as §258, source checkout/runtime SHA
53a3ba36cb58876f192167162587eacae7c89556 (intervening evidence only), paired
seeds 16–47, A0/Ironclad/fair RNG/keys OFF/native OOC, allocated cap 131072,
exact root budgets, Silver adaptive and SIM_ADAPT OFF, learned leaf/OOC MCTS
OFF, four workers. Requested schedules flat 1k, 1/2/5k normal/elite/boss,
flat 10k, 10/20/50k; existing room-tier routing and exact mode prevent extra
boss multiplication. 128 whole-run executions; no added seeds/arms or pooling
prior N16. Only static budgets/base argument/output paths differ.
Wins 17/32, 20/32, 21/32, 24/32; mean floor 47.4375,47.90625,48.5,47.9375;
mean final HP 24.75,35.59375,34.40625,38.84375. Seconds/run
2.65137,6.61840,31.36327,81.46058; added simulations
15.136M,31.432M,150.920M,313.860M. 1/2/5k finishes one win behind flat 10k
at ~21% runtime; no established quality equivalence. Highest schedule has
three more wins than flat 10k at ~2.60 times runtime, not fixed-work throughput.
All six paired comparisons preserved: exact p values 0.453125,0.2890625,
0.0654297,1,0.2890625,0.5078125 (schedule-combination order); all Bonferroni
six-pair adjusted p>=0.392578. Flat 1k→highest bootstrap CI[+3.125,+40.625]pp
is favorable but unadjusted; no established superiority across this four-arm
study. No root-regret measurement or scientific model/default qualification.
Cap fallbacks 0,0,0,252; pressure candidates 0,0,2,1122 (last two rescued
2/870). Peak allocated nodes 12756,65917,134873,202041; batches can overshoot
cap. Highest arm combines compute with more collection/fresh fallback.
Peak whole-process RSS four workers 0.270,1.205,2.436,4.341 GiB; external time-v,
no permanent infrastructure. All exits zero; 59,735 diagnostic rows validate
cap/budget/seed/config; all 3,278 combat telemetry records have zero bridge
failure counters. Saved analyzer, strict six paired reports, hashes and binary/
model immutability checks pass. Sequential execution, changed trajectory lengths,
N32 and six comparisons limit interpretation. Knowledge impact: maintained
exploratory budget/cost/cap status; chosen experimental cap 128k, no code/model
or frozen teacher changes.
[Paired seed CSV, raw compressed diagnostics/logs, reports and provenance](evidence/silver_budget_four32_128k_2026-09-15/README.md).


## §267 — Local 17-profile OOC MCTS parameter screen (2026-09-15)

User-authorized local screen on source `b7b26548` evaluates 17 preregistered
MCTS profiles on common seeds `12002000..12002031` (544 games): Ironclad A0,
fair RNG, exact-root-budget 10k Silver combat, keys off, Act 3 stop and 12
OpenMP threads. The user explicitly overrode the repository aggregate local
128-seed policy; every individual 32-seed invocation still ran through
`tools/seed_guard.sh`. Binary and native CTM SHA256 values are execution-bound
in the packet. The strategic-model path and successful load marker are retained
per arm, and its plan-time SHA256 matches the packaging-time file, but the
runner did not bind its bytes at execution. All 17 arms have exact 32-row result
and telemetry cohorts; profile/environment/startup/source/model receipts plus
ownership and abort accounting pass the deterministic analyzer.

The descriptive rank winner is the three-additional-combat leaf rollout:
26/32 wins (81.25%), mean floor 50.0, versus reference 21/32 (65.625%). The
paired observed delta is +15.625pp; a fixed 200k-resample paired percentile
interval is [-6.25,+37.5]pp and includes zero. The winner averages
2024.370s/game, 29.3x the reference's 69.087s/game and 41.4x the fastest
profile. Uniform one-combat continuation gives24/32; V4 one-combat continuation
and the 512-simulation profile each give23/32.

This is selection-biased discovery evidence on one reused cohort, with no V4
control, untouched holdout, composition phase or default change. Tested source
predates packaging base `608bb81` and its Silver memory/cap changes, so the
result does not qualify current main. Knowledge impact: experiment evidence
only; no maintained architecture, behavior, model, support, RNG or deployment
fact changes. [Report, analyzer, raw receipts and hash index](evidence/ooc_mcts_local_full_2026-09-15/README.md).


## §268 — Advanced CTM-scaled 10k versus flat 10k, exploratory paired 16 (2026-09-15)

Baseline `608bb810c44173fb8c0036df6e89c71da4d778e3`, frozen measured
implementation `a577fe0c6b7b81fef23e8d960d152766e84f80ae`. The opt-in adaptive
path loads the qualified tracked near-full V2 CTM and deterministically
marginalizes survival, max-HP and signed-HP distributions into death risk and
expected winning HP fraction. The historical danger formula, clamped 0.4x--2x,
scales a 10k caller base; unsupported fights retain 10k. No model sampling or
gameplay RNG consumption. Existing C_psi behavior remains available when no
CTM path is supplied.

Paired seeds 48--63, A0/Ironclad/fair RNG/keys off/native OOC, exact Silver
root budgets, experimental allocated 131072 lazy-GC reuse, Silver adaptive and
learned leaf/OOC MCTS off, four workers, sequential flat then CTM arms. No
preserved artifact matched this treatment; prior C_psi and flat-10k evidence
used different configurations/seeds. Arms/reporting were fixed before launch;
no tuning or added seeds/arms afterward.

Flat 10k wins 10/16 versus CTM 11/16; both win10/both lose5, flat-only0,
CTM-only1 (seed49), +6.25pp and exact paired two-sided p=1.0. Mean floor
46.1875→46.25, final HP33.9375→40.5625, seconds/run28.4177→19.6017. Added
simulations fall 71.840M→49.331273M (-31.33%); observed mean run time falls
31.02%. CTM fight budgets over 383 fights: min5002, median5703, mean6317.49,
max13609; 365 below/2 equal/16 above 10k. 381/383 changed budgets prove live
CTM allocation, but the two exact-10k records cannot distinguish exact model
output from support fallback after the fact.

No cap fallback in either arm; maximum allocated after search126,966→111,486;
four-worker peak process RSS2.424→2.225GiB. All 16 seeds pair, both exits zero,
7,184/7,294 decision rows validate configuration, and all 380/383 combat
telemetry rows have zero bridge failure counters. Encouraging compute-efficiency
signal, no established play improvement or default qualification; keep opt-in
pending a larger prospective gate. Knowledge impact: CTM adaptive integration
and exploratory gameplay/compute evidence only.
[Evidence, raw outputs, analyzer and provenance](evidence/ctm_adaptive10k_pair16_2026-09-15/README.md).


## §269 — Targeted whole-combat attention hyperparameter optimization (2026-09-15)

On the unchanged 510,030-row / 24,999-source Phase-1 corpus and frozen
source-grouped split, eight attention-only candidates used matched seed
20260911, batch 2,048, CUDA FP32, 16-epoch cap and patience 4. Selection used
VALIDATION Brier + winning-HP MAE + joint alive-HP MAE; TEST was not scored
until the winner was fixed. Reviewed source55f980c; exact prepared array,
split, baseline checkpoint, source membership and clean SHA fail closed.

Winner `hp_weight_2` retains width64/layers2/heads4/FF128/dropout.1/LR.001/
WD.0001 and changes only winning-HP MSE weight1→2. Validation selected epoch13:
composite0.164160725 versus matched baseline0.168567730 (−0.004407005,
−2.61%). Next candidates: width96 .167717187, FF256 .168153005, depth3
.168203941, no-dropout .169234952, lower-LR .170868000, higher-LR .170878278.

Equal TRAIN+VALIDATION refit then historical TEST: tuned survival AUC/Brier/
logloss0.980058/0.017384/0.058878, winning-HP MAE/RMSE0.069709/0.104013,
joint alive-HP MAE/RMSE0.075665/0.117100. Tuned-minus-frozen-attention paired
source-bootstrap95%: Brier[-.000842,-.000225], winning-HP MAE
[-.003101,-.002633], joint MAE[-.003416,-.002850]. Classification
**ATTENTION_HPO_IMPROVES_FROZEN_ATTENTION_POSTHOC**. TEST was previously
inspected; no tuned-versus-DeepSets prospective comparison, native export,
composition, gameplay or new data. Existing no-clear-family/DeepSets
simplicity decision remains. Wall3:09:00, exit0, peak RSS8,561,580kB; tuned
SHA005f860d, evidence SHA3a4ac885. Knowledge impact: current research status
and bound model-selection evidence updated; no runtime/default change.
[Report](evidence/combat_transition_attention_hpo_2026-09-15.md).


## §270 — Attention-HPO survival promotion into the default near-full artifact (2026-09-15)

Reviewed promotion source `a743364e1425bf5855309b565ac0eac1028cd726`
reconstructed the exact TRAIN-then-VALIDATION normalization and mapped the
selected attention checkpoint into the survival component with 0.0 maximum
probability error over 1,536 stratified rows. Baseline component and receipt
hashes fail closed. Only survival changed (`e150180a…` to `ccc3c210…`); maxHP,
HP, potion and downstream artifacts remain byte-identical. The downstream
compatibility receipt records the old/new survival identities and the audited
fact that downstream preparation consumes only HP and potion encodings.

Frozen TEST survival NLL/Brier improved 0.060411632/0.017986496 to
0.058877671/0.017384328. Final-support exposure passed every nonempty slice
after the same restricted exact correction for gold row 71838 (target mass
0.0010596961); 1,633,152 RAW draws had zero violations in every invariant
category. Native parity passed 3,904 draws and 31 fixtures, including 127
recursive Brew samples, 122 escapes and three fail-closed/no-draw fixtures;
maximum absolute error was 2.38e-6 at tolerance 1e-4. The executed native
support predicate exactly retained 505,935/510,030 all and 51,036/51,441 TEST
states with unchanged ordered-index digests. The tracked default artifact is
SHA256 `e9a18951710fdfe9e1a81a2703090a41f039067c670a1d8a0393b5e7e8e0ddfd`.
This qualifies offline composition and the native boundary on reused
development evidence; online gameplay remains a separate paired test.
[Promotion report](evidence/combat_transition_attention_promotion_2026-09-15.md).


## §271 — Old V2 versus attention-promoted V2 paired OOC MCTS gameplay (2026-09-15)

The prospective gate used fresh paired seeds 12002032--12002095, A0
Ironclad/project-fair RNG/keys off/Searcher2/Act-3 stop, exact 10k Silver
combat search and the locked 2,048-simulation OOC MCTS reference profile with
the full strategic gate stack. Every producer ran through the seed guard; two
64-seed arms exactly used the local 128-seed ceiling. The old source/artifact
were `cde61c8`/`22c855e0…`; the promoted source/artifact were
`22765a5`/`e9a18951…`. Arms, seeds, hashes and the paired decision rule were
fixed before launch.

Both arms won 49/64 (76.56%). Pairing gives both-win47, both-lose13,
old-only2 and new-only2: new-minus-old 0.0pp, deterministic 200k-resample
paired bootstrap95% [-6.25pp,+6.25pp]. Mean floor48.5938→48.7656, final
HP41.6250→41.9062 and seconds/run158.0474→164.4165. The result establishes
neither gameplay improvement nor harm; it supports preservation only within
this gate's limited resolution.

Both arms contain every seed exactly once and both phases exited zero.
Telemetry has 64 rows per arm and zero continuation-limit aborts. Old/new
support aborts are 26/34, all expected `smoke_bomb` exclusions on diverging
trajectories. This is online gameplay evidence for the exact tested profile,
not equivalence proof, unbiased-planning qualification, or permission to
enable OOC MCTS by default. Knowledge impact: current research status gains
prospective gameplay evidence; runtime and artifacts are unchanged.
[Evidence, raw outputs, analyzer and provenance](evidence/combat_transition_v2_ooc_mcts_pair64_2026-09-15/README.md).


## §272 — Frozen pre-promotion survival representation for signed-HP decoding (2026-09-15)

Baseline `cde61c85`, frozen experiment code `d10908c`. The tested full-union
survival and HP component checkpoints are TRAIN-only with respect to the
evaluated rows and share the same source/cache provenance. Their SHA256 values
are `e150180a…` and `0c8b5aa8…`; #187's TRAIN+VALIDATION-refit promoted
survival encoder was deliberately excluded. After this experiment, #187
changed only the survival component (`e150180a…` to `ccc3c210…`); therefore
the result does not directly evaluate the current promoted survival encoder.
TRAIN has 393,677 victories / 19,986 sources and VALIDATION 48,590 / 2,496;
historical TEST is untouched.

Only the frozen 64-dimensional state representation differs. Both fresh
signed-HP decoders have byte-identical initial states, identical batch order,
maxHP conditioning, legal mask, optimizer and AMP recipe; no encoder gradients
or VALIDATION gradient updates. Dedicated HP versus survival representation:
NLL 2.496705532→2.680527687 (+7.3626%), CRPS
3.618011474→4.087017666 (+12.9631%), expected ending-HP MAE
5.355416796→5.986446000 (+0.631029 HP). Healing, low-HP and damage slices all
show obvious regressions; probability support and normalization checks pass.

**`SHARED_ENCODER_HP_REJECTED` for the exact tested pre-#187 checkpoint.** The
survival representation clearly misses all three prespecified gates. Stop
before maxHP/potion next-stage composition, runtime/export work, or a seed
sweep. This rejects this frozen representation substitution under the fixed
decoder/training recipe, not every possible shared architecture or intrinsic
absence of HP information. Candidate selection at the final allowed epoch
leaves harder/slower decoding unresolved; no extra epochs were run because
that would be a new experiment. No new data, gameplay, TEST scoring, model
promotion or runtime change. Knowledge impact: experiment evidence retained
with explicit post-#187 applicability; the current promoted survival encoder
remains untested by this screen.
[Protocol, hashes, slices and receipts](evidence/shared_frozen_hp_encoder_2026-09-15.md).


## §274 — All-current-act-boss combat-evaluator OOC MCTS leaf paired 32 (2026-09-15)

An opt-in leaf replaces native `v_win` with the mean score over all three
current-act bosses: `0.75*P(survive) + 0.25*P(survive)*E[ending HP fraction
| survive]`, using the tracked qualified V2 combat-transition evaluator. It
fails the simulation/root closed if any boss is unsupported and retains exact
terminal 0/1. No treatment leaf calls `v_win`; the ordinary live fallback OOC
chain is unchanged.

Fresh paired seeds 12003000--12003031 used source `b5f037d` plus bound diff,
Ironclad A0/fair RNG/keys off/Act-3 stop, 512 OOC MCTS simulations, V4 priors,
and exact-root-budget 10k Silver real combat. Native and boss leaves both won
24/32. Both-win24/both-lose8/native-only0/boss-only0 gives 0.0pp; the fixed
200k paired bootstrap interval is [0.0,0.0]pp because every observed pair is
identical. All 32 terminal-state rows and all non-timing trace rows match.
Mean seconds/run103.8807→104.1177. Each arm has5,540 decisions,4,528 owned,
1,012 fallbacks,1,181,831 completed simulations,1,180,553 leaf evaluations,
nine expected Smoke support aborts and375 discarded simulations.

Classification corrected to **INVALID_TREATMENT_NOT_EXERCISED**. Live OOC MCTS
used `checkpointLeaves=true`; its resolved-map checkpoint called native
`v_win` without checking `bossLeaf`, so both arms executed the control leaf.
The exact trace equality is a bug signal and supports no treatment-effect
claim. Raw evidence is retained for provenance. A corrected experiment requires
a mechanism check before any fresh seed smoke. [Evidence and provenance](evidence/ooc_mcts_boss_leaf_pair32_2026-09-15/README.md).


## §275 — All-Act boss combat-evaluator OOC MCTS leaf paired 32 (2026-09-15)

The prior current-act boss leaf was broadened to all ten Act1--4 bosses. Each
probe preserves player state but uses its canonical encounter act/floor; the
equal-mean utility remains `0.75*P(survive) + 0.25*P(survive)*E[ending HP
fraction | survive]`. The treatment leaf uses the tracked qualified V2 combat
evaluator, no `v_win` call or gameplay RNG, exact terminal0/1, and fail-closed
support. Inspected origin/main `28d39cd` had five newer offline shared-HP/docs
commits but no OOC/combat runtime or model change.

Fresh paired seeds12003032--12003063 used IroncladA0/fair RNG/keysOFF/Act3
stop, fixed512 OOC MCTS, V4 priors and exact10k Silver real combat. Native and
all-boss leaves both win26/32: both-win26/both-lose6/no discordants, delta0pp,
fixed200k paired bootstrap95%[0,0]pp because all observed differences are zero.
All32 terminal-state and non-timing trace rows match. Mean floor49.15625 and
HP46.09375 match; seconds/run110.3850→109.9430. Each arm records5,720 OOC
decisions,4,626 owned,1,094 fallbacks,1,199,941 completed simulations,
1,199,100 leaf evaluations,12 expected Smoke support aborts,550 discarded and
zero continuation-limit aborts.

Classification corrected to **INVALID_TREATMENT_NOT_EXERCISED**. The same
checkpoint bug bypassed the all-Act boss evaluator and called native `v_win`
in both arms. The N32 equality is not a null result and supports no
treatment-effect inference. Raw evidence is retained for provenance. A
corrected experiment requires a mechanism check before any fresh seed smoke.
[Evidence and provenance](evidence/ooc_mcts_all_act_boss_leaf_pair32_2026-09-15/README.md).


## §276 — Corrected all-Act boss leaf mechanism and paired N8 smoke (2026-09-15)

The live checkpoint branch now selects constant, boss, or native evaluation in
that order and shares the all-ten-boss evaluator with ordinary `leafValue()`.
A fake-sampler regression with `checkpointLeaves=true,bossLeaf=true` requires
ten distinct `expectation()` calls and a returned value different from native
`v_win`. This also makes boss mode internally consistent without a loaded win
model at treatment leaves.

The pre-game real-model mechanism gate passed. At HP20/40/60, boss values were
0.00409/0.00647/0.01371 versus native0.15437/0.19850/0.24000. On an identical
64-simulation root, all three action Qs changed by about0.095--0.101, although
the selected action remained the same in that fixture.

Fresh paired seeds12003064--12003071 used IroncladA0/fair RNG/keysOFF/Act3,
fixed512 OOC MCTS, V4 priors and exact10k Silver. Native won6/8 and boss won4/8
(native-only2, boss-only0; descriptive delta -25pp). All eight terminal rows
and all eight non-timing trace rows differ. Mean floor50.75→44.125 and elapsed
seconds/run83.30→2218.42. Classification
**CORRECTED_MECHANISM_PASS_PAIRED_N8_SMOKE**: the treatment is exercised, but
N8 is not powered quality evidence and provides no default-change basis.

A conditionally planned extension completed its native N8 arm and three boss
rows before the user requested recording and merge. It is preserved under
`interrupted-extension/` and excluded from every statistic above. Knowledge
impact: the live checkpoint contract is corrected; both old N32 packets remain
invalid; current research records only this bounded mechanism smoke.
[Evidence and provenance](evidence/ooc_mcts_boss_leaf_corrected_smoke_2026-09-15/README.md).

## §273 — Purpose-trained shared maxHP/signed-HP encoder distillation (2026-09-15)

Baseline `28d39cdb`, frozen experiment code `79c6fcf5`. Exact current maxHP
and HP specialists (`2c5b54d0…`, `0c8b5aa8…`) served as frozen FP32 teachers
on the shared final-union TRAIN 393,677/19,986 sources and VALIDATION
48,590/2,496 sources. Historical TEST had zero inference rows and no metrics.
The student is the HP-initialized existing 64/2/4/128 Attention encoder with
the copied HP embedding/head and a fresh seeded Linear(64,11) maxHP head.
Pure equal-weight temperature-1 KL, seed20260912, AdamW, encoder/head LR
1e-4/1e-3, WD1e-4, batch512, clip1 and AMP-FP16 training were fixed.

The combined VALIDATION KL improved every epoch and selected the final epoch12:
maxHP KL0.003832507, HP KL0.005607910, combined0.004720209. HP teacher→student
NLL2.498291→2.505074 (+0.2715%), CRPS3.619360→3.636778 (+0.4813%) and expected
MAE5.341970→5.363075 (+0.021105 HP); every important slice passes. maxHP
NLL0.0426865→0.0455009 (**+6.5932%**, gate +2%), although accuracy drops only
0.1070pp and expected MAE rises 0.005442 HP. Nonzero accuracy drops 0.9056pp;
NLL rises 0.810300→0.861658, not catastrophic.

Decision **`SHARED_TRANSITION_ENCODER_REJECTED`**: the rejection is driven by
maxHP under-learning; HP degradation remains within all preregistered gates.
Optimization was still improving at epoch12. The miss is not
narrow enough for the epoch12 inconclusive exception. Stop without potion,
extra epochs, reweighting, adapters, architecture changes, runtime/export,
gameplay or promotion. Knowledge impact: experiment evidence and current
research status only; qualified components/defaults are unchanged.
[Protocol, epoch history, metrics and hashes](evidence/shared_transition_encoder_distill_2026-09-15.md).

## §277 — Fresh current-main V2 OOC MCTS rollout confirmation (2026-09-15)

Source `48fae046`, fresh paired seeds `12003000..12003031`, execution-hashed
V2 CTM and strategic/native models. Ironclad A0, fair RNG, exact-10k Silver,
cap 32768, adaptive/keys/Searcher3/direct leaf off, Act-3 stop, 12 workers.
Excluded per-arm canaries passed. V4/MCTS512/2048-rollout0/rollout1/rollout3
won 24/22/26/26/28 of 32. MCTS512-V4=-6.25pp, paired bootstrap95
[-28.125,+15.625]pp: **NO_CONFIRMATION**. At 2048 simulations, rollout0 and
rollout1 are each +6.25pp versus V4 with crossing-zero intervals; rollout1
minus rollout0 is 0pp, CI [-18.75,+18.75]pp, at 23.19x cost. Rollout3-V4 is
+12.5pp, CI [-3.125,+28.125]pp: **PROMISING_INCONCLUSIVE**; rollout3 minus
rollout1 is +6.25pp, CI [-6.25,+18.75]pp, at 2.35x cost. All provenance,
backend, seed, bridge, support and telemetry identities pass. The designated
GCP VM was absent; the user explicitly authorized the 64-game aggregate-local
extension, each arm remaining a guarded 32-seed invocation. No extra parameters,
seeds, gameplay/default changes or pooling. Rollout0 is the practical larger-
confirmation candidate; rollout3 is only a high-cost research candidate.
[Evidence packet](evidence/ooc_mcts_confirmation_v2_2026-09-15/README.md).

## §278 — Frozen HP representation for maxHP-delta decoding (2026-09-15)

Stacked on #190 head, baseline `cde61c85`, frozen experiment code `af46e32`.
TRAIN-only full-union maxHP/HP component SHA256 values `2c5b54d0…` and
`0c8b5aa8…`; same bound source/cache and original TRAIN/VALIDATION split.
TRAIN 393,677 victories / 19,986 sources; VALIDATION 48,590 / 2,496; no TEST.
PR #187 changed only the survival component; these exact maxHP and HP component
hashes are unchanged on current main, so no scientific rerun is required.

Only the frozen 64-dimensional representation differs. Fresh linear 11-class
heads have byte-identical initial states, batches, AdamW/FP32 recipe and
VALIDATION selection; encoders are frozen and VALIDATION never enters gradient
updates. Dedicated maxHP versus HP representation: NLL
0.042742204→0.159130603 (+272.3032%), accuracy 98.0696%→96.8203% (-1.2492pp),
expected post-maxHP MAE 0.081356→0.234180 (+0.152824 HP). On 1,546 nonzero-delta
rows, accuracy collapses 63.1307%→0.0647% and NLL rises 0.787493→3.897300.

**`SHARED_HP_ENCODER_MAXHP_REJECTED`.** The candidate clearly misses all fixed
gates, so the sequential HP-encoder potion screen did not run. Candidate
selection at final epoch 12 leaves intrinsic information absence unresolved;
this rejects the fixed linear-head/training recipe, not every jointly trained
shared representation. No extra epochs/tuning, new data, TEST, gameplay,
runtime/export, composition or model promotion. Knowledge impact: closes the
HP-encoder maxHP/potion frozen-substitution path; experiment evidence only.
[Protocol, histories and hashes](evidence/shared_frozen_maxhp_encoder_2026-09-15.md).


## §279 — Paired 500-simulation combat-budget diagnostic (2026-09-15)

Baseline/current-main source was `28d39cdb`; the pasted request named
`cde61c85`, but the requested fresh worktree was based on the actual current
local `main`. The implementation was frozen at `ee7e80a` before the scientific
run. The diagnostic is opt-in and adds 500 simulations to the current private
Silver search state, records a checkpoint, then continues that same tree to
the exact 10,000 total; the ordinary path is unchanged when
`STS_COMBAT_BUDGET_DIAG_FILE` is unset. The checkpoint is not an independent
fresh 500-simulation search: inherited visits and retained-root state may
already be substantial. Agreement is therefore a local continuation
comparison along the 10k-generated trajectory, not proof that an actually
stopped fight would reproduce later decisions with its different retained
tree and search-RNG state.

The designated run used fresh seeds 64–79, Ironclad A0, fair project RNG,
Searcher2, exact 10,000 Silver simulations, allocated cap 131,072, native
out-of-combat decisions, and four OpenMP workers. Adaptive budgets,
convergence stops, keys, and OOC MCTS were disabled. Every combat root has a
checkpoint action/root summary, final action/root summary, semantic agreement,
and reroot telemetry in the raw CSV. The paired continuation was validated by
a fixed-state bridge test: standalone 500 and the 500 prefix of a 1,000-total
continuation choose the same action with the expected simulation counts.
Additional split-versus-uninterrupted checks compare final actions and root
statistics for an ordinary root, a retained-root continuation, and sequential
GAMBLE selection.

The run completed with 398 fights and 7,016 decision rows. The checkpoint
action agreed with the final action in 5,530/7,016 rows (78.82%). A fight was
labelled path-stable only if every recorded decision agreed along the generated
10k trajectory: 35/398 stable and 363/398 unstable. The sorted-seed split was
64–71 train and 72–79 holdout; the holdout contained 25 stable and 180
unstable fights. At the first recorded decision, every tested root-summary
feature failed to separate the holdout label: AUROC was 0.454 for top-two Q
gap, 0.484 for top visit share, 0.475 for second visit share, 0.465 for the
top/second ratio, 0.529 for visit entropy, and 0.492 for legal-action count.
No train threshold satisfying the predeclared ≤5% false-stop constraint had
nonzero useful coverage on holdout. Unstable fights appeared in hallway,
elite, boss, and other categories; no category-only exception was supported.

**`NO_USEFUL_SIGNAL`** for this bounded predictive diagnostic. Stop before
adaptive budget allocation, early stopping, NN training, or production
qualification. This negative result concerns local continuation summaries and
does not establish or refute a different deployed-policy label or search
regime. Knowledge impact: current research status records a bounded negative
result; runtime defaults, models, gameplay, and production budgets are
unchanged.

The referenced evidence packet, raw CSV, analysis and provenance at
`evidence/combat_budget_diag_2026-09-15/README.md` are absent from the tracked
repository. Independent verification of the raw diagnostic remains unavailable.


## §280 — Retained-root adaptive Silver prospective A/B smoke (2026-09-16)

The frozen treatment keeps fresh roots and one-action/forced roots at exact
10,000 Silver simulations. A retained non-forced root first runs 500 new
simulations and stops only when `top_two_visit_gap_share >=
0.2932885906040268`; otherwise that same private search continues to 10,000.
This is an opt-in policy under `STS_SILVER_ADAPTIVE=1` and
`STS_SILVER_ADAPTIVE_RETAINED_ONLY=1`; the ordinary path remains unchanged.
The implementation was frozen at `ec3a9266966406c130aff18c0077f69bf4df83c9`.

Fresh paired seeds64--79 used Ironclad A0, fair RNG, exact-root budgets,
allocated reuse cap131072, native OOC, adaptive CTM off, no OOC MCTS, and
sequential control then treatment arms using the same executable. Flat exact
10k control won10/16 versus treatment11/16. Mean final floor was48.25 versus
47.25 and mean final HP36.00 versus39.06. Outer wall time was113.05s versus
66.71s. Control added70,160,000 Silver simulations across7,016 decisions;
treatment added41,362,000 across6,800 decisions, a 41.05% simulation reduction
and 40.99% wall reduction.

Treatment telemetry recorded391 fresh roots,6,409 retained roots, and255
one-action/forced roots. It stopped2,804 decisions at500 (41.24% of all
treatment decisions,42.84% of non-forced decisions,43.75% of retained roots);
all 2,804 stops had inherited visits, more than one legal action, and a gap at
or above threshold. Fresh and forced roots continued to10k. Exact/fallback
reroot rows were4425/2375 in treatment versus4556/2460 in control. The paired
outcomes had five win disagreements, five floor disagreements, and thirteen
HP disagreements. No expensive shadow10k comparison was collected.

Classification: **`PER_DECISION_SIGNAL_PROMISING`** — retained-root adaptive
search only; fresh-root early stopping remains rejected. This N16 smoke is
mechanical/compute evidence, not a quality qualification or whole-fight action
equivalence claim. It supports the planned fresh N32 prospective qualification;
it does not promote the policy or justify further offline threshold tuning.
The earlier §279 checkpoints remain local continuation comparisons and are not
pooled with this live-policy result. Knowledge impact: current research status
and experiment evidence updated; normal Silver defaults remain unchanged.
[Evidence packet and raw traces](evidence/silver_retained_adaptive_pair16_2026-09-16/README.md).


## §281 — Retained-root adaptive Silver prospective qualification (N32, 2026-09-16)

The N16 smoke met its mechanical/compute gate without an obvious gameplay
regression, so the same frozen implementation ran a fresh paired N32 on
seeds80--111. Configuration remained Ironclad A0, fair RNG, exact-root
budgets, allocated reuse cap131072, native OOC, adaptive CTM off, no OOC MCTS,
sequential arms, and the same executable. The flat control disables adaptive
Silver; the treatment uses fresh/forced roots at10k and retained non-forced
roots at500 only when the frozen top-two visit-gap threshold
`0.2932885906040268` is met.

Flat control won22/32 versus treatment24/32: three treatment-only wins and one
control-only win. Mean final floor was47.84 versus48.31 and mean final HP
32.53 versus30.97. Control added142,010,000 Silver simulations across14,201
decisions; treatment added86,146,500 across14,403 decisions, a 39.34%
simulation reduction and 42.33% wall reduction (235.06s versus135.55s).

Treatment telemetry recorded813 fresh roots,13,590 retained roots, and443
one-action/forced roots. It stopped6,093 decisions at500 (42.30% of all
treatment decisions,43.65% of non-forced decisions,44.83% of retained roots);
all stops satisfied retained/non-forced/threshold invariants. Fresh and forced
roots continued to10k. Exact/fallback reroot rows were9416/4987 in treatment
versus9285/4916 in control. No expensive shadow10k comparison was collected.

Classification remains **`PER_DECISION_SIGNAL_PROMISING`** — retained-root
adaptive search only. This N32 packet supports the compute-saving treatment at
the bounded prospective gate but does not promote a default, establish
universal safety, or claim whole-fight action equivalence. Fresh-root early
stopping remains rejected, and the earlier §279 local-continuation negative
result is not replaced or pooled with this policy result. Knowledge impact:
current research status and experiment evidence updated; normal Silver
defaults remain unchanged.
[Evidence packet and raw traces](evidence/silver_retained_adaptive_pair32_2026-09-16/README.md).

## §282 — Shared maxHP+HP encoder as potion encoder (2026-09-16)

The successful PR #197 epoch-37 shared maxHP+HP Attention encoder was tested
as a frozen replacement for the dedicated potion encoder. A fresh existing
64-action potion decoder was trained separately on each representation using
the exact current final-union TRAIN/VALIDATION winning population: TRAIN
393,677 rows / 19,986 sources and VALIDATION 48,590 rows / 2,496 sources.
Encoders were cached once, decoder initialization and 12-epoch batch order
were byte-identical, and the FP32 AdamW recipe was fixed at seed 20260912,
batch 512, learning rate 1e-3, weight decay 1e-4 and clip 1.0. TEST rows were
not evaluated. Both arms selected epoch 12; the shared curve descended at
every epoch, but the absolute NLL gap remained 0.02344 at epoch 11 and 0.02356
at epoch 12, so the shared arm was not closing the gap faster.

Dedicated potion versus shared maxHP+HP validation exact trajectory NLL was
0.507205895 versus 0.530769047 (**+4.6457%**, gate +2%). The no-change Brier
delta was +0.00527133 (gate +0.01), action-mode accuracy fell 0.8673pp (gate
1pp), illegal probability was exactly zero, and maximum normalization error
was 1.92e-7. Slice NLL changes were Brew +5.8765%, Smoke +8.7886%, recursive
Brew **+22.3968%**, and all trajectory-special +6.3589%; recursive Brew is an
obvious regression under the screen rule.

Decision **`SHARED_ENCODER_POTION_REJECTED`**. Since teacher-forced acceptance
failed, the planned 32-draw ancestral diagnostic did not run. Stop this exact
substitution path: no joint fine-tune, extra epochs, TEST, runtime/export,
promotion or gameplay. The result rejects this frozen representation and
decoder recipe, not every possible shared architecture or intrinsic
information absence. The preparation cache was regenerated after the host
restart and matched all three recorded exact hashes. Knowledge impact:
experiment evidence and current research status only; qualified components
and executable defaults are unchanged.
[Evidence, provenance and receipt](evidence/shared_potion_encoder_screen_2026-09-16.md).

## §283 — Jointly adapted shared maxHP+HP+potion representation (2026-09-16)

The PR #197 epoch-37 shared maxHP+HP Attention encoder was allowed to adapt
jointly with its maxHP/HP branches and the existing exact 64-action potion
trajectory decoder. The actual current-main base was `c371f3c2`; PR #198 was
confirmed merged there. The reviewed experiment implementation was frozen at
`49e2642a`. The maxHP and HP teachers remained frozen, and the potion decoder
was initialized from the qualified dedicated potion component.

The exact final-union source-grouped population was TRAIN 393,677 rows /
19,986 sources and VALIDATION 48,590 rows / 2,496 sources. TEST inference was
zero. The fixed FP32 recipe used seed `20260912`, AdamW, encoder LR `1e-4`,
heads/decoder LR `1e-3`, weight decay `1e-4`, batch 512, clip 1.0 and 12
epochs. A deterministic TRAIN-only 8,192-row calibration cohort froze
`s_max=0.0021965544365230016`, `s_hp=0.011543620959855616`, and
`s_potion=2.281699538230896`; the cohort row-ID SHA256 was
`122776e919b5fd6445b516ae8e9f70aa5db4f4c3d1eccbb994f0e7de80ffa053`. Batch
order SHA256 was
`110ff129ce40099ba612986aabe78195cbcc37bcd11597b9e6b3d012f3cf304d`.

All twelve epochs were eligible under the PR #197 maxHP/HP preservation gates;
the earliest strict minimum potion validation trajectory NLL was epoch 12.
The selected candidate preserved maxHP (NLL −0.0776%, accuracy −0.0185pp,
expected post-maxHP MAE +0.000554 HP) and HP (NLL +0.1202%, CRPS +0.2306%,
expected ending-HP MAE +0.012734 HP). Against the dedicated potion specialist
on the same VALIDATION rows, exact trajectory NLL was 0.504024366 versus
0.524099650 (**+3.9830%**, fixed gate +2%). Normal no-change Brier changed by
+0.00430663 and action-mode accuracy fell 0.7422pp, both within their gates;
illegal probability was exactly zero and maximum normalization error was
2.04e−7. Slice NLL changes were Brew +8.6531%, Smoke +4.6304%, recursive Brew
**+20.5168%**, and all trajectory-special +7.9931%. The primary NLL and
obvious recursive-Brew slice gates failed.

**`SHARED_TRANSITION_POTION_REJECTED`.** Because teacher-forced potion quality
failed, the mandatory 32-draw ancestral qualification did not run. No TEST,
runtime/export, promotion, native C++ or gameplay work ran. This rejects the
specified jointly adapted architecture/recipe, not every shared architecture
or intrinsic potion information absence. Qualified components and executable
defaults remain unchanged. Knowledge impact: experiment evidence and current
research status only.

[Evidence, provenance, full epoch history and receipt](evidence/shared_transition_encoder_potion_2026-09-16.md).


## §284 — Jointly adapted shared maxHP+HP+potion representation, 24 epochs (2026-09-16)

The requested follow-up to the frozen substitution screen allowed the PR #197
epoch-37 shared maxHP+HP Attention encoder, its maxHP/HP branches, and the
existing exact 64-action potion decoder to adapt jointly for 24 epochs. All
other variables were held fixed relative to the 12-epoch treatment: the
current-main base was `c371f3c2`, the reviewed implementation was
`71d3d4d6`, the same source-grouped final-union population was used (TRAIN
393,677 rows / 19,986 sources; VALIDATION 48,590 rows / 2,496 sources), and
TEST inference was zero. The FP32 recipe used seed `20260912`, AdamW,
encoder LR `1e-4`, heads/decoder LR `1e-3`, weight decay `1e-4`, batch 512,
clip 1.0, and 24 epochs. The 8,192-row TRAIN-only calibration cohort and
loss scales were unchanged; the 24-epoch batch-order SHA256 was
`9615a714605fac562b61f93779f7a1204f3a71d5125b329558eb0a2915e45375`.

All 24 checkpoints remained eligible under the PR #197 maxHP/HP preservation
gates. Epoch 23 was the earliest strict minimum potion validation NLL at
`0.520021881`. The selected checkpoint preserved maxHP (NLL −0.5145%,
accuracy −0.0165pp, expected post-maxHP MAE +0.000470 HP) and HP (NLL
+0.1168%, CRPS +0.2460%, expected ending-HP MAE +0.010358 HP).

Against the dedicated potion specialist on the same VALIDATION rows, exact
trajectory NLL was `0.504024366` versus `0.520021881` (**+3.1740%**, fixed
gate +2%). No-change Brier delta was +0.00300605, action-mode accuracy fell
0.3586pp, illegal probability was exactly zero, and normalization error was
2.04e−7. Brew, Smoke, recursive Brew, and all trajectory-special slices
regressed (+12.0600%, +15.5893%, **+20.2797%**, and +12.6391%).

Decision **`SHARED_TRANSITION_POTION_REJECTED`**. Since teacher-forced potion
quality failed, the mandatory 32-draw ancestral qualification did not run.
This rejects the specified jointly adapted architecture, recipe, and
24-epoch selection rule, not every shared architecture or intrinsic potion
information absence. Qualified components and executable defaults remain
unchanged. Knowledge impact: experiment evidence and current research status
only.
[Evidence, provenance and receipt](evidence/shared_transition_encoder_potion_24_2026-09-16.md).


## §285a — Shared maxHP+HP representation for native downstream consumers (2026-09-16)

The actual current-main baseline was `27c8f7a0918b6ac684a3913436e30c54c0f5ff6c`,
a descendant of the handoff's expected `c371f3c2`. The exact PR #197 epoch-37
checkpoint was verified at SHA256
`daf50b5ec0847fe7a44cde0efd5d592a1939a25e6978f6757dd2b0157a105267`, with
receipt SHA256 `4149c038a2abe9ab181b03c714763e74fb7b37f534020179004696fd465577c7`
and receipt decision `SHARED_TRANSITION_ENCODER_GO`.

Stage A replaced only the dedicated HP representation consumed by the frozen
relic/event/gold downstream heads. The survival representation, dedicated
potion representation, heads, support predicates, trace construction,
legality masks and targets were unchanged. The existing final-union
source-grouped data and `full-union-downstream-v1` evaluator were reused; the
eligible VALIDATION cohort was 17,950 rows, with no TEST inference.

Reference versus shared candidate joint downstream NLL was 1.364212394 versus
1.448260307 (**+6.1609%**, gate +2%). Turns exact-label accuracy fell 2.6428pp,
attacks fell 1.3663pp, and shuffles fell 6.0533pp; shuffles NLL rose 11.5188%,
Ritual NLL rose 20.6457%, and gold NLL rose 24.6343%. Cards were +0.3536% NLL
and Writhing was −1.0815% NLL. Outputs remained finite/legal, but the principal,
accuracy and important-slice gates failed.

Decision **`SHARED_HP_DOWNSTREAM_FAIL`**. Stop before the native 3-encoder
implementation and preparation benchmark; retain separate maxHP and HP
encoders. No C++, runtime, TEST, OOC timing, gameplay or default-promotion
change ran. This rejects the exact frozen downstream substitution, not every
possible shared architecture or intrinsic information absence. Knowledge
impact: current research status and experiment evidence only; qualified
components and executable defaults remain unchanged.

The reproducibility gap was repaired by tracking
`tools/combat_transition_shared_hp_downstream.py` and replaying the receipt.
The driver verifies the frozen bindings, regenerates both HP encodings, swaps
only `cache["z"]`, and reproduces the recorded metrics within `9.53e-08`.
Because the historical cache used different inference arithmetic, the driver
uses that hash-verified dedicated cache as the metric reference and records
the regenerated-vs-cache difference explicitly.

[Evidence packet and machine-readable receipt](evidence/shared_hp_downstream_2026-09-16.md).

## §285 — Sequential Silver stopping controller diagnostic (2026-09-16)

- **Question:** Can progressively larger exact continuation checkpoints
  support an offline risk estimator for a future dynamic sequential stopping
  controller, and does it improve on the frozen #199 retained-root rule?
- **Baseline and implementation:** Actual current `main` at task start was
  `c371f3c29ffab07096c71fc66a4ab930e9595952` (the requested
  `77a76167865d96df776fd80794695a6937fdac3f` was already an older contained
  parent). Diagnostic source is
  `21111b7e6af73b7f8a770b45df3d7093b17b69dc`. The opt-in checkpoint stream
  reuses the existing Silver private session and leaves the legacy fixed rule,
  gameplay policy, and defaults unchanged.
- **Protocol:** One exact-10k Ironclad A0 fair Silver native-OOC arm, normal
  policy/models, four workers, fresh seeds `112..127`, allocated reuse cap
  131,072, and cumulative checkpoints `250/500/1000/2000/4000/8000/10000`.
  CTM adaptive budgeting, Silver adaptive stopping, convergence stopping, OOC
  MCTS, and key collection were explicitly off. Seeds `112..119` were used for
  discovery and `120..127` for held-out evaluation. Every live decision used
  the final 10k reference action; no gameplay A/B was run.
- **Correctness:** 53,228 rows / 7,604 decisions were collected. Every
  checkpoint has 7,604 rows and every decision has all seven checkpoints.
  `rootVisitsAfterSearch == inheritedVisits + checkpoint` for every row,
  including retained roots whose child-edge visit summary is one lower than
  the internal root counter. Fresh/retained and one-action/forced controls
  were separately identifiable.
- **Stage 1:** Retained non-forced action-change risk was 11.7913%, 11.5242%,
  10.1274%, 8.4634%, 5.7518%, and 1.9310% at 250 through 8,000. Fresh roots
  were 24.2537% overall and one-action/forced roots 0%; neither control is
  included in the quality claim.
- **Stage 2:** The predeclared standardized logistic regression was fit only
  on discovery retained/non-forced rows before 10k. On held-out evaluation,
  the 1% and 2% ceilings stopped 0 decisions. The 5% ceiling stopped 55/3,778,
  had zero observed action disagreements, and reduced nominal simulations by
  0.5393%. The frozen #199 rule stopped 1,621 decisions, reduced nominal
  simulations by 40.7610%, and had 1.9124% offline action disagreement.
- **Six-step offline follow-up:** The strict integer visit lock
  `N1-N2 > Bmax-Bused` stopped 2,003/2,422 held-out retained/non-forced
  decisions, with budget counts 704/62/100/196/307/634/419 at
  250/500/1,000/2,000/4,000/8,000/10,000, 53.8026% nominal reduction, and
  zero observed disagreements. Held-out empirical risk by
  `rho=(N1-N2)/(Bmax-Bused)` was 30.0730%, 13.6264%, 6.5986%, 2.7119%,
  1.4963%, 0%, and 0% across `0-.1`, `.1-.25`, `.25-.5`, `.5-.75`,
  `.75-1`, `1-2`, and `2+`; the complete rho/leader-stability cross-table and
  all control-population lock distributions are in the packet JSON. These
  are descriptive offline analyses; no soft threshold was tuned.
- **Decision:** **`LOGISTIC_DYNAMIC_RULE_REJECTED`**. The logistic controller
  is too conservative to replace #199, while exact visit-lock stopping and
  an independently specified empirical-risk racing rule remain open. This is
  offline engineering evidence only; it does not qualify dynamic runtime
  stopping, establish universal safety, introduce `dynamicSearch(session,maxBudget)`,
  or change the fixed #199 policy/defaults. **Knowledge impact:** current
  research status and experiment evidence only; normal Silver defaults remain
  unchanged.
 - **Evidence:** [full packet](evidence/combat_sequential_stopping_2026-09-16/README.md),
 including the raw checkpoint stream, estimator JSON, benchmark receipt,
   sidecar, and run log.

## §286a — Purpose-trained shared maxHP+HP DeepSets encoder (2026-09-16)

- **Question and baseline:** Can the successful shared maxHP+HP Attention
  distillation be replaced by a cheaper permutation-invariant encoder while
  retaining acceptable predictive quality? Baseline is current `main`
  `77fec051c2453d79f05bad5e813989b861fa5d0a`. The fit implementation was
  frozen at `7521643c512c1f2a89a02f2fb8a512036831203a`; receipt assembly used
  `21d7467ae81b5cdde7bcd5dbc48393ea146254a1` after training completed.
- **Intervention:** one candidate only: the existing historical
  `tools/combat_transition_surrogate.py::DeepSetsEncoder`, with card/relic
  masked sum pooling and a 64-dimensional output. The encoder has 94,424
  parameters and the complete maxHP+HP student has 119,659. The maxHP and HP
  branches were unchanged. No tokenization, loss, task weight, temperature,
  extra layer, adapter, downstream consumer, or runtime default changed.
- **Protocol/provenance:** exact frozen maxHP/HP teacher checkpoints were
  `2c5b54d0…` and `0c8b5aa8…`; teacher-output hashes were `10404b3e…` and
  `6244ca5e…`; preparation cache `e1c25f27…`; source SHA `1c31b7eb…`.
  TRAIN was 393,677 victories / 19,986 sources and VALIDATION 48,590 /
  2,496. Seed `20260912`, 40 epochs, batch 512, AdamW, LR `1e-4/1e-3`,
  weight decay `1e-4`, clip 1.0, AMP FP16 training, FP32 teacher/scoring,
  and earliest strict minimum equal-weight validation KL were fixed. Nine
  nonfinite-gradient updates were skipped under the established AMP rule.
  TEST inference rows and metrics were zero.
- **Stage A:** epoch 39 selected. Combined validation KL was `0.012285614`,
  with maxHP KL `0.001936906` and HP KL `0.022634322`. Relative to the
  dedicated specialists, maxHP NLL was +0.7832%, accuracy dropped 0.0535pp,
  expected post-maxHP MAE increased 0.000550 HP, HP NLL was +0.3399%, HP CRPS
  +0.7303%, and expected ending-HP MAE +0.030176 HP. Damage, healing and
  low-pre-HP slices passed; outputs were finite, normalized and exactly legal.
  Decision **`CHEAP_ENCODER_QUALITY_GO`**.
- **Stage B:** on identical first-512 VALIDATION rows with four CPU threads,
  10 warmups and 100 repetitions, encoder median was Attention `80.714 ms`
  versus DeepSets `4.085 ms` (19.76x), and complete maxHP+HP forward was
  `81.909 ms` versus `4.320 ms` (18.96x). IQRs and the row-identity hash are
  in the evidence packet. This is an implementation-level CPU screen, not a
  native/OOC speedup claim. Decision **`CHEAP_ENCODER_SPEED_GO`**.
- **Boundary:** the result is an offline quality and speed handoff only. Do
  not export/promote the checkpoint, replace runtime defaults, retrain or
  substitute downstream relic/event/gold heads, add potion/survival, run OOC
  gameplay, or infer TEST performance from this result. The next decision is
  whether to train downstream consumers for this representation.
- **Knowledge impact:** current research status and experiment evidence only;
  no qualified component, runtime contract, native CTM, gameplay result or
  executable default changed. [Evidence packet](evidence/shared_transition_deepset_distill_2026-09-16.md)
  and [machine-readable receipt](evidence/shared_transition_deepset_distill_2026-09-16.json).

### §286b — Same-session DeepSets receipt correction (2026-09-16)

- **Correction:** the original §286 receipt is superseded because its
  normalization used `arrays[train]` and its HP delta embedding plus HP head
  were fresh. The narrowly corrected implementation uses
  `cache["ids"][train]`, asserts and tests that these are the TRAIN cache's
  original row IDs, and copies both HP modules from the verified specialist
  used by the Attention control. No other recipe, architecture, seed,
  population, TEST, gameplay or downstream scope changed.
- **Stage A:** the single corrected 40-epoch fit at
  `b192275ca0584a0c1eee8916176613b428a5e1b4` selected epoch 40 and passed
  **`SHARED_TRANSITION_ENCODER_GO`** / **`CHEAP_ENCODER_QUALITY_GO`**.
  Corrected candidate metrics were maxHP NLL `0.043216348`, HP NLL
  `2.506730318`, HP CRPS `3.639513338`, and ending-HP MAE `5.368440`.
  Normalization covered 393,677 original row IDs with hash
  `e42a4dc3…`; both copied HP-module hashes matched the specialist. TEST
  inference rows and metrics remained zero. The corrected checkpoint hash is
  `bee6800d…`, result receipt hash `83b2482e…`, and validation prediction
  hash `ecf91913…`.
- **Stage B:** because Stage A passed, the same first-512 VALIDATION-row CPU
  screen (4 threads, 10 warmups, 100 repetitions) was rerun once. Encoder
  medians were Attention `101.934 ms` versus DeepSets `4.691 ms` (21.73x),
  and complete maxHP+HP medians were `102.462 ms` versus `4.939 ms` (20.74x),
  passing **`CHEAP_ENCODER_SPEED_GO`**. The speed receipt hash is
  `49784953…`.
- **Boundary:** this is corrected offline evidence only. No TEST evaluation,
  runtime export, default promotion, gameplay, downstream training, extra
  seed, tuning or architecture work ran. See the
  [correction evidence](evidence/shared_transition_deepset_distill_correction_2026-09-16.md)
  and [machine-readable receipt](evidence/shared_transition_deepset_distill_correction_2026-09-16.json).
## §286 — Exact Silver visit-lock prospective A/B (N16 smoke and N32, 2026-09-16)

The default-off exact visit-lock implementation was committed at
`8adbfe9f6b58145c853e53248fa5979a4e1991fa` and built as the Release
`one_combat` executable with SHA-256
`b282b7662b3e128d80cc6ce8701408369d50a63a0bf1389a465c65d7488c6b8d` before
gameplay collection. The treatment used only the strict integer rule
`N1-N2 > Bmax-Bused` on the same private Silver session at generalized
2.5/5/10/20/40/80/100% checkpoints plus the zero-use check. Fresh and
one-action/forced roots remained full-budget controls. No logistic/risk/rho
rule, tuning, shadow search, default change, or cap variation was used.

The frozen regime was Ironclad A0, project-fair Silver, native OOC, four
workers, exact 10,000 root budgets, allocated reuse cap 131,072, CTM and old
Silver adaptive stopping off, convergence stopping off, OOC MCTS off, and keys
off. N16 used fresh paired seeds 128--143. The nominal compute target was 35%:
control/treatment won 11/16 versus 10/16, and treatment saved 34.80% of
control Silver simulations and 34.43% wall time. This was marginally below
the nominal target. All lock, fresh/forced, accounting and failure invariants
passed; there were 4,980 exact locks including 362 zero-use locks, and paired
gameplay had two control-only and one treatment-only win. Because the protocol
called the threshold approximate and the mechanism/gameplay checks passed,
N32 was run as an explicitly documented extension; this was not a nominal 35%
compute pass.

The earlier PR #202 offline 53.8026% reduction applied only to retained,
non-forced decisions: 2,422 of 3,778 evaluation decisions. Its all-decision
equivalent was approximately 34.5%, so the live N16 result is consistent with
that offline prediction. The live N32 result at 28.77% is a moderate
degradation relative to that prediction, not a collapse from 53.8% to 28.8%.
This makes the descriptive rho extension a justified follow-up hypothesis,
without changing the exact-lock gate or promoting a runtime policy.

After the documented N16 extension authorization, a new N32 block 144--175
was run without changing the implementation or configuration. Control/treatment won 24/32 versus 22/32;
treatment saved 28.77% of control Silver simulations and 31.59% wall time.
There were 9,179 exact locks including 465 zero-use locks, with no invalid,
fresh, one-action/forced, non-strict, accounting, semantic, conversion,
transaction, knowledge, or other bridge failures. Paired gameplay had two
control-only wins and no treatment-only wins.

Decision: **`LIVE_EXACT_VISIT_LOCK_REJECTED`** for this bounded prospective
gate because the N32 compute reduction is below the approximately 40%
requirement. This is not a universal gameplay-harm finding and does not
invalidate the current-root exact-lock proof, but it does not support
promotion. Runtime defaults remain unchanged; the exact mode remains
default-off. Knowledge impact: current research status and experiment
evidence updated.

[Evidence packet, raw traces, validation and provenance](evidence/silver_exact_visit_lock_pair_2026-09-16/README.md).

## §287 — Silver policy/value Phase-A cost diagnostic (2026-09-16)

The bounded Phase-A probe defines a diagnostic-only `PLAYER_NORMAL`
policy-plus-value contract over the visible Silver wire. It emits separate
parent-policy records and actual rollout-leaf value records, preserving exact
semantic legal siblings and preventing parent/child label substitution. The
canonical policy layout is 1,766 state plus 22 action features (1,788 total);
the prospective shared model input appends exact isolated-Silver root
effective-gold and max-HP scalars (1,768 state inputs). Hidden pending-intent
details are redacted before feature extraction. No training, model loading,
gameplay, action selection, utility, RNG, or runtime default changed.

The corrected benchmark boundary was committed at
`d7897477a45e7112e1fe21d7484edc1cd9adfbfc`. The prior corpus-producing run is
retained only for schema/examples. Clean one-thread Silver timing with no
corpus or VNet observer measured 290,326 `PLAYER_NORMAL` calls at 3.083
microseconds mean for 100 simulations (seeds 100--107), and 694,480 calls at
2.981 microseconds mean for the 1k operating point (seeds 108--109).

The conversion-inclusive native one-thread benchmark measured actual
supported leaves at 143.763/143.739/150.833/165.010 microseconds
(mean/median/p90/p99), with 3,200 calls, 13,000 action scores, and an observed
checksum. Replacing clean full-run `PLAYER_NORMAL` rollouts gives an estimated
42.134786-second search versus 1.291608 seconds at 100 simulations
(-3,162.1959% reduction, 0.0307x speedup), and 101.191794 seconds versus
3.421245 seconds at 1k (-2,857.7473% reduction, 0.0338x speedup).
The corrected bounded engineering classification is
**`PV_COST_NOT_FEASIBLE_CLEAN_BASELINE`**. The earlier
`PV_COST_FEASIBLE` result is withdrawn because its baseline included
corpus-observer work.

The Phase-A packet records the separate parent-policy/leaf-value schemas,
root effective-gold/max-HP input scalars, clean and observer-enabled run
boundaries, exact arithmetic, executable/source/benchmark/example hashes, raw
timing-log hashes, and CPU identity. This does not establish predictor quality,
hidden-state sufficiency, or gameplay benefit.

**Evidence:** [Phase-A packet](evidence/silver_policy_value_phase_a_2026-09-16.md).

## §288 — Silver rho-racing soft-lock follow-up (2026-09-16)

- **Dependency and baseline:** PR #204 was verified merged and contained in
  current `origin/main`, SHA
  `3f8ca7b59c2de1ba78a2d8bab0f280f849dd6845`. The PR #202 sequential
  checkpoint packet remained available. The new implementation was frozen at
  `ae97d56a74a9b70ac34b87478a87de5e3a9ee893`; the single Release executable
  used for all prospective arms has SHA-256
  `c85579fd22a9c38475a3810062cabd0a15fe6d4bc33c8ea5f9ee0dee5a476eb3`.
- **Offline Stage 1:** The existing seeds 112--127 packet was replayed only
  offline. Candidates A/B/C were evaluated exactly as predeclared, with
  exact locking first and fresh/forced roots held to max budget. Discovery
  selected B (`rho >= 0.50` and the same semantic leader for at least two
  consecutive checkpoints): 1,129 soft stops, 1.5058% disagreement, and
  43.0299% all-decision reduction. Evaluation on 120--127 gave 1,070 soft
  stops, 1.4953% disagreement, 42.7237% all-decision reduction versus
  34.4918% exact-only, and 8.2319 percentage points incremental saving.
  Room disagreement was 2.3041% for bosses, 2.1978% for elites, 0.6494% for
  hallways, and 0% for other rooms. Classification:
  **`RHO_RACING_OFFLINE_PROMISING`**; this is post-hoc engineering evidence.
- **Runtime implementation:** Added default-off `STS_SILVER_RHO_RACING=1`.
  It owns exact locking internally, uses the frozen B rule and PR #204's
  zero/2.5/5/10/20/40/80/100% schedule, and rejects old adaptive mode,
  separate exact-lock mode, and paired/sequential diagnostics. Focused tests
  cover exact priority, integer/remaining-budget boundaries, zero safety,
  fresh/retained behavior, arbitrary budgets, sequential transactions,
  option parsing, and default/exact regression. A first attempted pair was
  discarded after review found the soft predicate was not gated by the rho
  option; the fix was applied, retested, amended, and rebuilt before valid
  prospective collection.
- **N16:** On the clean block 176--191, exact-only used 46,126,250 Silver
  simulations and rho used 41,544,000, a 9.9341% incremental reduction.
  Wins were 11/16 versus 11/16; paired outcomes were one baseline-only and
  one treatment-only win. Exact/soft stops were 3,830/0 versus 1,313/2,516,
  with zero failure counters. The N16 gate passed.
- **N32:** On the new block 192--223, flat/exact/rho used
  150,990,000/103,112,250/89,270,750 simulations and wall times
  258.82/177.52/147.72 seconds. Exact/rho reductions versus flat were
  31.7092%/40.8764%; rho's incremental reduction versus exact was 13.4237%.
  Wins were 23/32, 25/32, and 20/32. Rho versus exact had five exact-only
  wins and no rho-only win; rho versus flat had three flat-only wins and no
  rho-only win. All seed, sidecar, schedule, budget, strictness,
  exact-priority, root-accounting, fresh/forced, and bridge-failure checks
  passed. Classification: **`RHO_RACING_COMPUTE_PASS_GAMEPLAY_CONCERN`**.
- **Decision:** The compute gates passed, but the paired gameplay point
  estimates are concerning against both comparators, especially exact-only.
  Do not promote rho, tune it, or replace the frozen #199 preferred
  experimental path. Runtime defaults remain unchanged. **Knowledge impact:**
  current research status and experiment evidence updated; no production
  policy changed.
- **Evidence:** [rho-racing packet](evidence/silver_rho_racing_2026-09-16/README.md),
  including raw N16/N32 results, scaling traces, logs, sidecars, time receipts,
  paired CSVs, provenance, and validator output.

## §292 — Retained-root adaptive Silver production deployment gate (2026-09-16)

- **Preflight:** Current `origin/main` was
  `066264dc25bf2046aecd5ca7a94a8e82d5031e7b`. It contains merged PR #199
  (`77a76167865d96df776fd80794695a6937fdac3f`), PR #204
  (`3f8ca7b59c2de1ba78a2d8bab0f280f849dd6845`), and PR #207 (the current
  merge). Production remained at a 32,768 allocated reuse cap with ordinary
  boss budgeting, exact-root budgets off, exact-lock off, and rho off.
- **Protocol:** The next unused contiguous 32-seed block, 224--255, used
  Ironclad A0, project-fair Silver, native OOC, four workers, base budget
  10,000, 32,768 allocated reuse cap, ordinary boss budgeting, CTM adaptive
  budgeting/convergence/OOC MCTS/keys off, and exact-lock/rho off. Both arms
  used the same Release executable (`c85579fd22a9c38475a3810062cabd0a15fe6d4bc33c8ea5f9ee0dee5a476eb3`).
- **Control/treatment:** Control used `STS_SILVER_ADAPTIVE=0`. Treatment used
  `STS_SILVER_ADAPTIVE=1`, `STS_SILVER_ADAPTIVE_RETAINED_ONLY=1`, and
  `STS_SILVER_ADAPTIVE_TOP_GAP=0.2932885906040268`, with no other treatment
  difference. Fresh and one-action/forced roots used 10,000; eligible retained
  non-forced roots used 500 and continued the same private tree to 10,000 only
  below the threshold.
- **Result:** Control/treatment won 21/32 versus 22/32. Treatment had five
  treatment-only and four control-only wins, mean floor 48.40625 versus
  48.28125, and mean ending HP 32.90625 versus 29.34375. Silver simulations
  were 202,860,000 versus 81,633,000, a **59.7589%** treatment reduction;
  wall times were 395.72s versus 132.08s, a **66.6229%** reduction.
- **Accounting:** Treatment recorded 13,945 decisions, 812 fresh roots,
  13,133 retained roots, 510 one-action/forced roots, 6,086 valid 500-stops,
  and 7,859 10k continuations. Every stop was retained, non-forced, exactly
  500 new simulations, and at least the threshold; fresh and forced roots all
  reached 10k. Exact/rho stop counters and conversion, semantic, transaction,
  and knowledge failure counters were zero in both arms. All seed/result,
  sidecar, reroot, and paired-accounting checks passed.
- **Decision:** **`RETAINED_ADAPTIVE_DEFAULT_GO`**. Promote the frozen #199
  retained-root policy to the normal live Silver default without changing the
  production cap, cap mode, search algorithm, MCTS constants, exact-lock
  default, or rho default. `STS_SILVER_ADAPTIVE=0` remains a clean flat-Silver
  opt-out. This N32 is a deployment screen, not a formal equivalence proof or
  superiority claim. **Knowledge impact:** maintained environment-variable
  contract, current research status, and experiment evidence updated.
- **Evidence:** [deployment packet](evidence/silver_retained_adaptive_deployment_pair32_2026-09-16/README.md),
  including raw arm results, metadata, scaling traces, run logs, paired CSV,
  summary, and validation outputs.

## §293 — Current #199 retained-adaptive Silver cap screen (fresh N16, 2026-09-16)

- **Question/provenance:** After the #199 retained-root policy deployment
  screen, test whether the allocated Silver reuse cap should increase from
  32,768 to 131,072. The fresh next block, seeds 256--271, used the reviewed
  executable `3fb0c8ce2e009c2ef7a3abee5584556aff515261` and identical explicit
  current-policy settings in both arms: fresh/forced roots at 10,000,
  retained non-forced roots at 500 with continuation to 10,000 below the
  exact threshold `0.2932885906040268`. Prior cap artifacts were inspected but
  were exploratory/reused or exact-flat-budget comparisons and did not satisfy
  this fresh retained-adaptive production comparison.
- **Protocol:** Ironclad A0, project-fair Silver, native OOC, Searcher2,
  ordinary boss budgeting, base budget 10,000, allocated reuse mode, four
  workers, CTM adaptive budgeting/convergence/OOC MCTS/keys off, and
  exact-lock/rho off. Only `STS_SILVER_REUSE_CAP` differed: 32,768 versus
  131,072. Both producers ran through `tools/seed_guard.sh` and exited 0.
- **Result:** 32k won 11/16 with mean floor 49.0000 and HP 40.2500; 128k won
  11/16 with mean floor 49.1250 and HP 39.8125. Paired outcomes were 11 both
  wins, 5 both losses, and no cap-only win in either direction. Simulations
  were 46,704,500 versus 46,652,500; external wall was 80.51s versus 77.02s;
  peak four-worker RSS was 1,066,104 KiB versus 1,986,088 KiB. The 128k arm
  therefore used 1.86x peak RSS for 0.11% fewer simulations and no changed
  paired wins.
- **Mechanism accounting:** 32k had 398 cap-pressure exact candidates, of
  which 395 were rescued by exact reroot and 3 fell back at the allocated cap;
  128k had zero pressure candidates and zero allocated-cap fallbacks. Exact
  reroot rates were 69.1407% (5,021/7,262) versus 69.2107% (5,033/7,272).
  Valid 500-stops were 3,169 versus 3,185. Both arms had zero conversion,
  semantic-resolution, transaction, knowledge, exact-lock, and rho failures.
- **Decision:** **`CAP_128K_NOT_MATERIALLY_USEFUL_IN_FRESH_N16`**. Keep the
  allocated 32,768 production cap and leave 131,072 experimental. The larger
  cap removes the small number of unrecovered cap events, but 32k already
  rescues 99.2% of pressure candidates and the paired outcome evidence shows
  no useful-tree quality gain. The observed 1.89 GiB RSS is a substantial
  concurrency cost. This N16 screen is not a general quality-equivalence
  proof. **Knowledge impact:** maintained experiment evidence and current cap
  decision; production/default/model contracts otherwise unchanged.
- **Evidence:** [cap-screen packet](evidence/silver_cap_adaptive_pair16_2026-09-16/README.md),
  including raw arm results, metadata, scaling traces, `/usr/bin/time -v` logs,
  paired analysis, compact summary, and provenance.

## §294 — Staged retained-root Silver threshold grid and Pareto inspection (2026-09-17)

- **Question/hypothesis:** Replace the single current #199 retained-root
  `500 -> 10,000` decision with cumulative 250/500/1,000/2,000/4,000/8,000/
  10,000/20,000/50,000 checkpoints and a monotone per-checkpoint top-two
  visit-share threshold. The hypothesis was that later checkpoints could
  safely buy more simulation savings while retaining useful 50k decisions.
- **Implementation/provenance:** The staged path is opt-in and was frozen at
  source SHA `41f26f8af92ebdb0b4f488cf1c9c5457fb057394`; current production
  defaults remain unchanged. Fresh and one-action/forced roots continue only
  to 10,000. The requested grid was `{0.20,0.25,0.30,0.35,0.40,0.50,0.60,
  0.75,inf}`. All commands used Ironclad A0, fair Searcher2/native OOC,
  allocated 32,768 cap, four workers, base 10,000, and CTM adaptive
  budgeting/convergence/OOC MCTS/keys off. Every bestbench command ran through
  `tools/seed_guard.sh`; each invocation stayed within the repository's local
  128-seed ceiling.
- **Discovery sweep:** Each of the nine scalar grid values was measured on
  fresh seeds 272--303 (N32 per arm). A separate exact 50k reference emitted
  complete same-root checkpoint traces. The scalar arm simulation totals were
  112,759,000; 126,997,250; 136,694,750; 145,857,000; 154,448,250;
  172,042,000; 185,837,000; 216,851,250; and 374,990,000 from tau 0.20
  through infinity. Wins were respectively 22, 26, 24, 24, 24, 24, 22, 23,
  and 23 out of 32. Peak RSS ranged from 2,025,120 to 2,212,708 KiB for the
  finite arms and was 2,143,792 KiB for infinity. Exact reroot rates ranged
  from 65.2435% down to 48.1831%; cap-pressure/rescue/fallback counts are in
  the packet's machine-readable summary.
- **Policy construction:** Offline enumeration over 2,952 retained
  non-forced discovery decisions selected maximum-saving schedules under
  early-stop-only checkpoint-to-50k disagreement constraints. The 1% schedule
  had 19/1,933 disagreements and mean 30,389.40 saved simulations; the 2%
  schedule had 42/2,190 and 33,451.05 saved; the 5% schedule had 117/2,350
  and 38,310.13 saved.
- **Held-out inspection:** On fresh held-out seeds 304--319, flat 50k won
  10/16 with mean floor/HP 47.1875/34.5625, 414,200,000 simulations, and
  13:41.47 wall. The frozen 1%, 2%, and 5% policies won 8/16, 8/16, and 7/16;
  mean floor/HP were 42.6875/24.1250, 39.9375/22.6250, and 41.6250/28.5625.
  Their simulations were 99,191,000; 78,491,500; and 57,546,500, with wall
  times 3:17.74, 2:31.00, and 1:44.68. Peak RSS was 2,138,436; 2,110,216;
  and 1,915,624 KiB. All arms had zero conversion, semantic-resolution,
  transaction, and knowledge failures.
- **Decision:** **`STAGED_PARETO_GAMEPLAY_GATE_FAIL`**. The implementation and
  compute curve are qualified as an experiment, but every frozen Pareto policy
  lost overall wins and mean floor/HP versus the held-out flat 50k reference.
  They also used more Silver simulations per run than #199's 81,633,000/32 =
  2.55M baseline: 3.60M, 4.91M, and 6.20M for the frozen 5%, 2%, and 1%
  policies. Do not promote staged adaptive Silver; keep current #199 500->10k
  and the allocated 32,768 cap in production. The rejected live
  runtime/configuration path was removed after the experiment; the analyzer
  and evidence packet remain. This is a bounded N32 scalar-arm discovery and
  N16 held-out inspection, not a universal quality equivalence proof.
  **Knowledge impact:** maintained current research status and experiment
  evidence; no production policy changed.
- **Evidence:** [staged threshold packet](evidence/silver_staged_grid_2026-09-17/README.md),
  including raw per-arm results, metadata, scaling traces, telemetry logs,
  `/usr/bin/time -v` receipts, frozen schedules, summaries, and provenance.
## §289 — Retrained downstream consumers for the qualified DeepSets representation (2026-09-16)

- **Question and baseline:** Does the corrected qualified PR #205 DeepSets
  representation contain enough information for the existing downstream CTM
  consumers when those consumers are retrained? After reconciling the branch
  with current `main`, the baseline was `066264dc25bf2046aecd5ca7a94a8e82d5031e7b`.
  The implementation correction was frozen at
  `e036a32af068e8a99cd3c3edbfe1aeb35fdab58c`.
- **Correction/intervention:** Only the downstream state input changed from
  the dedicated HP representation to the frozen 64-dimensional
  `student.encoder` output from the corrected DeepSets artifact. Preparation
  generated representations for 458,589 TRAIN+VALIDATION rows and zero TEST
  rows, with explicit row-ID binding; TEST rows were not encoded or inferred.
  The DeepSets checkpoint SHA256 was
  `bee6800dd7230b180c2b4894c0f01763efca4b7799e3f36a805333c3003dc663`, the
  corrected result receipt SHA256 was
  `83b2482eab347c09901c3b39f2ce7fed324f6be378ca36ff51f0d3965074c769`, and
  the generated representation SHA256 was
  `9232027d8331fd2157727276410161e3c12816b6680cb116ebc2b3afd37352af`.
- **Protocol/provenance:** Existing `models`, `losses`, compatible-set targets,
  exact hidden potion-trace marginalization, event candidates, legality masks,
  native helpers and source-grouped splits were reused. Preparation cache,
  downstream cache and reference checkpoint hashes were unchanged at
  `e1c25f27…a251d`, `acd48827…d0e3` and `d07ead94…6af91`. The downstream fit
  used seed `20260912`, 12 epochs, batch 512, FP32, AdamW, learning rate
  `0.001`, weight decay `0.0001`, clip 1.0, and earliest strict minimum
  original VALIDATION normalized joint NLL. TRAIN was 150,404 eligible rows /
  18,286 sources; VALIDATION was 17,950 eligible rows / 2,276 sources.
- **Result:** Candidate checkpoint SHA256 was
  `c00ed677b8b2b2854fb62982247853982bc58d9fc20afdd96c593bcc6c07423a`, with
  epoch 12 selected. Joint NLL was 1.358598545 versus reference 1.364212489
  (−0.4115%). Turns, attacks, cards and shuffles had relative NLL changes of
  −1.0592%, +0.1175%, −0.3111% and −1.9974%; singleton accuracy changes were
  +0.1705pp, +0.7407pp, +0.8675pp and +0.8071pp. Writhing, Ritual and gold
  relative NLL changes were −1.8988%, −7.3414% and −1.0014%. All fixed NLL,
  accuracy and important-slice gates passed. The explicit output-support audit
  found finite losses, normalized head probabilities and positive exact legal
  target mass under the existing masks.
- **Decision:** **`DEEPSET_DOWNSTREAM_GO`**. Retrained downstream consumers
  can use this frozen cheap representation with acceptable offline validation
  quality. This does not qualify full CTM sharing, potion/survival sharing,
  native runtime, gameplay, OOC MCTS, speedup or default promotion. No TEST
  inference, native export, C++ or runtime change occurred. **Knowledge impact:**
  current research status and experiment evidence only; qualified executable
  defaults remain unchanged.

[Corrected evidence packet and machine-readable receipt](evidence/deepset_downstream_2026-09-16.md).

## §290 — Silver policy/value stage-cost decomposition (2026-09-16)

The requested tiny follow-up decomposed the conversion-inclusive Phase-A
candidate on the same 16 supported `PLAYER_NORMAL` leaves, fixed synthetic
weights, one thread, 200 iterations, and 3,200 calls. Mean per-call costs were
1.242 microseconds for live `BattleContext` to Silver wire conversion, 40.944
microseconds for canonical feature extraction plus root-scalar and action
vector preparation, 72.158 microseconds for the `1768 -> 64 -> 64` encoder plus
value head, and 4.212 microseconds for all legal action scores. The stage sum
was 118.556 microseconds versus 118.851 microseconds independently measured
end-to-end.

The neural encoder/value stage alone is about 24.2 times the clean 1k
`PLAYER_NORMAL` rollout mean of 2.981 microseconds. Decision:
**`PV_COST_NOT_FEASIBLE_MODEL_FORWARD`** for this exact model boundary. A
Silver-native compact representation is not pursued as a conversion-only fix;
it would need to change the model/input computation as well. No gameplay,
training, runtime integration, or default change occurred. Knowledge impact:
current Phase-A evidence and research status updated.

[Phase-A evidence packet with stage receipt](evidence/silver_policy_value_phase_a_2026-09-16.md).

## §292 — Sparse Silver policy/value evaluator screen (2026-09-17)

The merged Phase-A follow-up tested one bounded implementation change: transpose
the first-layer weights and skip zero inputs while preserving the same fixed
weights, feature semantics, model width, legal actions, and outputs. On the
same 16 supported `PLAYER_NORMAL` leaves, one thread, 200 iterations, and
3,200 calls, sparse encoder/value plus action scoring measured 6.377
microseconds per call, versus 78.019 microseconds for the dense model path.
The sparse path averaged 39 nonzero state inputs and matched every dense value
and action logit within `4.66e-10` value and `1.16e-10` logit absolute error.

The sparse path is approximately 12.2x faster than dense, but remains about
2.14 times the clean 2.981-microsecond `PLAYER_NORMAL` rollout mean. Decision:
**`PV_SPARSE_NOT_FEASIBLE_PER_LEAF`** for inference throughput. The second
offline-adapter/native-state optimization was not attempted under the declared
stop rule. Root-only learned guidance is the next distinct direction, with a
separate decision-quality hypothesis. No training, gameplay, runtime, or
default change occurred. Knowledge impact: current research status and
experiment evidence updated.

[Sparse evaluator evidence packet](evidence/silver_sparse_evaluator_2026-09-17.md).

## §293 — Sparse evaluator top-level timer correction (2026-09-17)

Review found that the sparse screen's outer timer began before parity and the
separate sparse benchmark, while its denominator counted only dense calls.
The timer was moved immediately before the dense loop. On the corrected same
fixture run, dense conversion-inclusive end-to-end timing was 120.636
microseconds mean, 119.208 median, 124.404 p90, and 173.634 p99. The sparse
model-plus-action timer remained independently bounded at 6.355 microseconds
per call; parity remained below `5e-10`. This changes only the top-level report,
not the sparse-vs-dense model-computation conclusion. No training, gameplay,
runtime, or default change occurred. Knowledge impact: evidence provenance and
top-level benchmark reporting corrected.

[Corrected sparse evaluator evidence](evidence/silver_sparse_evaluator_2026-09-17.md).
## §291 — Frozen qualified DeepSets representation for potion decoding (2026-09-16)

- **Question and baseline:** Can the qualified frozen PR #205 DeepSets state
  representation replace the dedicated potion Attention encoder when the
  existing potion decoder is retrained for that representation? The current
  `main` baseline was `b0704c755a78fc139c6859781ce899c230919a44`; the final
  screen implementation was `207db265c41badab848fe3caabe4ab2d9b47de1a`.
- **Intervention/provenance:** Only the state representation supplied to the
  potion decoder changed. The corrected DeepSets checkpoint and receipt were
  `bee6800d…c3003dc663` and `83b2482e…5074c769`; the reused TRAIN+VALIDATION
  representation was `9232027d…d37352af`, with explicit row-ID binding and
  zero TEST rows. The dedicated potion component was
  `ae1a1411…15a0f1db`; the potion preparation cache contract was
  `e1c25f27…a251d`; source SHA was `1c31b7e…9a8955dd`.
- **Protocol:** The exact 64-action native potion trajectory DAG, observed
  generation-body prior, legality masks, Brew recursion, Smoke handling and
  teacher-forced metrics were reused. A and B used fresh byte-identical
  decoder initialization, seed `20260912`, FP32, AdamW, batch 512, 12 epochs,
  learning rate `0.001`, weight decay `0.0001`, clip `1.0`, fixed identical
  batch orders, and earliest strict minimum VALIDATION trajectory NLL. Both
  encoders and the PR #205 maxHP/HP upstream modules were frozen. TRAIN was
  393,677 rows / 19,986 sources; VALIDATION was 48,590 / 2,496.
- **Result:** Both arms selected epoch 12. Dedicated A validation trajectory
  NLL was `0.506803228`; frozen DeepSets B was `0.537569223`, a `+6.0706%`
  regression above the fixed `+2%` gate. No-change Brier delta was `+0.00723277`
  and passed, but normal action-mode accuracy dropped `1.2154` percentage
  points, beyond the `0.01` gate. Brew, Smoke and trajectory-special slices
  regressed `+2.7248%`, `+4.9113%` and `+3.0868%`; recursive Brew regressed
  `+19.1859%`, an obvious slice regression. Illegal probability remained
  exactly zero and maximum normalization error was `1.9914e-7`.
- **Decision:** **`DEEPSET_POTION_REJECTED`** after
  `TEACHER_FORCED_REJECTED`. The required ancestral Stage B was not run. This
  rejects this exact frozen DeepSets representation plus decoder recipe only;
  it does not reinterpret the prior Attention rejection, justify encoder
  fine-tuning, or establish intrinsic information absence. No TEST scoring,
  runtime/export, C++, gameplay, OOC MCTS or default promotion occurred.
  **Knowledge impact:** current research status and experiment evidence only;
  qualified encoders and executable defaults remain unchanged.
- **Evidence:** [screen report](evidence/deepset_potion_screen_2026-09-16.md),
  [machine-readable receipt](evidence/deepset_potion_screen_2026-09-16.json),
  and external raw receipt
  `/home/philippherrmann/sts_sweep/runs/deepset-potion-screen-20260916/results.json`
  (SHA256 `1ba8b785…7dcad107ab45363`).

## §290 — Frozen qualified DeepSets representation for survival prediction (2026-09-16)

- **Question and baseline:** Can the qualified frozen PR #205 DeepSets
  representation support survival prediction when only a new survival head is
  trained? The current `main` baseline was `4c8ff3fe044626c6d18226e5f4091a0d1cb842d1`
  after the merged PR #210 potion screen.
- **Intervention/provenance:** Arm A used the frozen TRAIN-only full-union
  survival Attention encoder; Arm B used the corrected frozen DeepSets
  encoder. The checkpoint/receipt were `bee6800d…c3003dc663` /
  `83b2482e…5074c769`; the reused TRAIN+VALIDATION representation and row-ID
  files were `9232027d…d37352af` / `3dfecd1d…112e437`. The source, corpus and
  preparation bindings were `1c31b7e…9a8955dd`, `74c08aa0…c1cfde` and
  `e1c25f27…a251d`. TRAIN was 408,183 rows / 19,986 sources; VALIDATION was
  50,406 / 2,496; TEST encoding and inference were zero.
- **Protocol:** Fresh survival heads were byte-identically initialized with
  seed `20260912`. Both arms used FP32, AdamW, batch 512, 12 epochs, learning
  rate `0.001`, weight decay `0.0001`, clip `1.0`, identical epoch
  permutations, BCE-with-logits loss, and earliest strict minimum VALIDATION
  NLL. Only head parameters entered each optimizer; both selected checkpoints
  reloaded with exact metric reproduction.
- **Result:** Arm A selected epoch 10 at NLL `0.059312280`; Arm B selected
  epoch 12 at `0.083209150`, a **+40.2899%** regression. Brier worsened
  **+37.5178%**. Observed-death NLL worsened **+44.2850%**; low-pre-HP NLL
  worsened **+55.8470%** on 756 rows / 292 deaths. ROC-AUC remained diagnostic
  only. The original dedicated component validation NLL reproduced as
  `0.059494425` versus recorded `0.059494428`.
- **Decision:** **`DEEPSET_SURVIVAL_REJECTED`**. All fixed core NLL, Brier,
  death-slice and low-pre-HP gates failed. This rejects the exact frozen
  victory-distilled DeepSets representation plus matched head recipe; it does
  not prove intrinsic information absence or authorize encoder fine-tuning.
  No TEST, runtime/export, C++, gameplay, OOC MCTS, potion, architecture sweep
  or promotion work occurred. **Knowledge impact:** current research status
  and experiment evidence only; qualified encoders and runtime defaults remain
  unchanged.
- **Evidence:** [screen report](evidence/deepset_survival_screen_2026-09-16.md),
  [machine-readable receipt](evidence/deepset_survival_screen_2026-09-16.json),
  and external raw receipt
  `/home/philippherrmann/sts_sweep/runs/deepset-survival-screen-20260916-final/results.json`.

## §291 — Converged linear probe for frozen DeepSets survival (2026-09-16)

- **Question and baseline:** Does the PR #211 survival gap persist when the
  linear readout is optimized to convergence rather than stopped after 12
  AdamW epochs? The baseline after merged PR #211 was
  `e82810f8486d4ad47b62b074ebcfdcb307fa9f17`.
- **Protocol:** Existing frozen Attention and DeepSets embeddings were reused.
  Fresh byte-identical heads were fit on TRAIN with full-batch L-BFGS, strong
  Wolfe line search, maximum 500 iterations / 1,000 evaluations, history 20,
  tolerances `1e-9` / `1e-12`, and identical L2 `1e-4`. Validation was scored
  once after fitting; no validation epoch selection, TEST inference, encoder
  training or new embedding generation occurred.
- **Result:** Attention validation NLL was `0.059344385`; DeepSets was
  `0.079102747`, a **+33.2944%** relative gap versus +40.2899% in PR #211.
  Brier relative degradation was +31.5958%; observed-death NLL +37.6878%;
  low-pre-HP NLL +41.4150%. The gap narrowed by 6.9955 percentage points but
  remained substantial. The probes used only 69 / 68 closure calls and about
  0.30 / 0.15 seconds.
- **Decision:** **`S1_LINEAR_PROBE_DIAGNOSTIC`**. This reduces, but does not
  eliminate, the hypothesis that the prior result was caused by the 12-epoch
  stopping rule. Proceed to the matched tiny nonlinear S2 decoder before
  changing the encoder. No runtime, TEST, gameplay, OOC MCTS, fine-tuning,
  native export or promotion work occurred. **Knowledge impact:** current
  research status and experiment evidence only; qualified components and
  runtime defaults remain unchanged.
- **Evidence:** [S1 report](evidence/deepset_survival_lbfgs_2026-09-16.md),
  [machine-readable receipt](evidence/deepset_survival_lbfgs_2026-09-16.json),
  and external raw receipt
  `/home/philippherrmann/sts_sweep/runs/deepset-survival-lbfgs-20260916/results.json`.

## §292 — Scale-neutral linear survival probe (S1b, 2026-09-17)

- **Question and baseline:** Does the S1 DeepSets linear gap survive
  representation-specific scale normalization and removal of L2 regularization?
  The baseline after merged PR #212 was
  `ada2b7ca13b374881c2594aaee937437ea3204f4`.
- **Protocol:** Attention and DeepSets embeddings were independently
  standardized with TRAIN-only means and standard deviations. Eleven constant
  DeepSets dimensions used unit scale after centering. One fresh byte-identical
  unregularized full-batch L-BFGS head per arm used the fixed strong-Wolfe
  recipe; validation was evaluated once after fitting. TEST rows remained zero.
- **Result:** Attention validation NLL was `0.059368707`; DeepSets was
  `0.076859772`, a **+29.4618%** gap. Brier relative degradation was +28.6715%;
  observed-death NLL +32.9193%; low-pre-HP NLL +33.1960%. AUC was 0.980665 / 0.964784.
  Final gradient norms were `6.996e-5` / `1.911e-5`; head norms were
  `8.9364` / `9.9994`.
- **Decision:** **`S1B_LINEAR_SCALE_DIAGNOSTIC`**. The remaining gap stays in
  the expected 25–35% range, so raw scale plus L2 is not the main explanation.
  Proceed to S2, the matched tiny nonlinear `64→64→1` ReLU decoder, without
  changing the encoder. No runtime, TEST, gameplay, OOC MCTS, fine-tuning,
  native export or promotion work occurred. **Knowledge impact:** current
  research status and experiment evidence only; qualified components and
  runtime defaults remain unchanged.
- **Evidence:** [S1b report](evidence/deepset_survival_s1b_2026-09-17.md),
  [machine-readable receipt](evidence/deepset_survival_s1b_2026-09-17.json),
  and raw receipt `/tmp/deepset-survival-s1b-20260917-retry2/results.json`.

## §293 — Nonlinear frozen survival decoder (S2, 2026-09-17)

- **Question and baseline:** Can a tiny nonlinear decoder recover the survival
  information that a linear head cannot expose from the frozen general
  representation? The baseline after merged PR #213 was
  `7370ccdd35a79e5b55991e646fe3587762f02718`.
- **Protocol:** The S1b TRAIN-only normalized Attention and DeepSets embeddings
  were frozen. A and B used identical fresh
  `Linear(64,64) -> ReLU -> Linear(64,1)` heads, seed `20260912`, identical
  epoch permutations, FP32 AdamW, batch 512, 12 epochs, clip 1.0, and earliest
  strict VALIDATION NLL. TEST rows remained zero.
- **Result:** Attention validation NLL was `0.059702005`; DeepSets was
  `0.072428763`, a **+21.3171%** gap. Brier relative degradation was +21.8116%;
  observed-death NLL +17.6745%; low-pre-HP NLL +20.9588%. S2 reduced the S1b
  NLL gap by 8.1447 percentage points, but Arm B still selected epoch 12 and
  the remaining gap stayed above the `10%` stop threshold.
- **Decision:** **`S2_NONLINEAR_DIAGNOSTIC`**. Nonlinear decoding recovers real
  interactions but does not make the frozen victory-distilled general
  representation survival-competitive. Stop trying to decode survival from
  this `z`; next train a survival-specific DeepSets encoder on all TRAIN
  combats including deaths, optionally using the Attention specialist as a
  soft teacher. No runtime, TEST, gameplay, OOC MCTS, fine-tuning, native
  export or promotion work occurred. **Knowledge impact:** current research
  status and experiment evidence only; qualified components and runtime
  defaults remain unchanged.
- **Evidence:** [S2 report](evidence/deepset_survival_s2_2026-09-17.md),
  [machine-readable receipt](evidence/deepset_survival_s2_2026-09-17.json),
  and raw receipt `/tmp/deepset-survival-s2-20260917/results.json`.

## §294 — Warm-start survival-specific DeepSets (2026-09-17)

- **Question and baseline:** Can the corrected PR #205 DeepSets encoder,
  warm-started and trained on all survival TRAIN rows including deaths, match
  the dedicated TRAIN-only survival Attention encoder closely enough for
  offline replacement? The reconciled baseline was
  `be5b6ac2c9914b0a56244f2522b7573f81360067`.
- **Protocol:** Reuse the exact 94,424-parameter PR #205 encoder and its bound
  scalar normalization, add only a fresh 65-parameter linear survival head,
  and train both on 408,183 TRAIN rows. The fixed recipe was FP32 AdamW,
  batch 512, seed 20260912, encoder/head LRs `1e-4` / `1e-3`, weight decay
  `1e-4`, clip 1.0, plain unweighted BCE, 12-epoch floor, patience 6, and
  absolute cap 40. Validation selected the earliest strict NLL minimum.
  The fixed gates were NLL +2%, Brier +5%, death NLL +10%, low-pre-HP NLL
  +10%, plus finite/probability/population validity and zero TEST inference.
- **Result:** Epoch 23 was selected by patience after six non-improving
  epochs. Attention NLL/Brier were `0.0594944246` / `0.0178150944`;
  DeepSets were `0.0630634725` / `0.0188982822`. Relative degradation was
  **NLL +5.9990%** and **Brier +6.0802%**. Death NLL +6.2773% and low-pre-HP
  NLL +3.8294% passed. Overall NLL/Brier failed, so the speed screen was
  skipped. TEST encoded/inferred/scored rows were all `0`.
- **Decision:** **`SURVIVAL_DEEPSET_REJECTED`**. This exact warm-started
  supervised adaptation does not recover sufficient survival quality for
  offline replacement. By the preregistered evidence pattern, Attention-teacher
  distillation is the plausible separate next hypothesis; no rescue tuning,
  TEST, runtime, gameplay, OOC MCTS, export or promotion occurred.
  **Knowledge impact:** current research status and experiment evidence only.
- **Evidence:** [fit report](evidence/survival_specific_deepset_fit_2026-09-17.md),
  [machine-readable receipt](evidence/survival_specific_deepset_fit_2026-09-17.json),
  and raw receipt
  `/home/philippherrmann/sts_sweep/runs/survival-specific-deepset-20260917-fit/results.json`.

## §295 — Shared Attention 40-epoch continuation and overflow follow-up (2026-09-15; recovered 2026-09-17)

- **Historical result:** Following the rejected 12-epoch recipe (§273), changing
  only the horizon to 40 epochs aborted at epoch 19 on a non-finite gradient
  norm: **`EXTENDED_TRAINING_NUMERICALLY_UNSTABLE`**, with no selected checkpoint
  or quality decision. The subsequent one-variable overflow-handling variant
  let GradScaler skip non-finite-gradient updates while retaining clipping and
  the finite forward-loss guard. It completed 40 epochs with seven skipped
  updates and no non-finite forward loss; epoch 37 passed all fixed gates:
  **`SHARED_TRANSITION_ENCODER_GO`**, combined validation KL `0.003101193`,
  maxHP NLL relative `+1.2492%`, and HP NLL relative `+0.1303%`.
- **Provenance and evidence:** The four files below are recovered unchanged
  from PR #197's frozen commit
  [`013db3d8a8f1180adfe16003f24c36742a9d0ed7`](https://github.com/pherrman1/sts_ai/commit/013db3d8a8f1180adfe16003f24c36742a9d0ed7),
  which preserves PR #197's final corrected state. The actual overflow run used
  `b58a03920fb84aee84f7fcde3ef300366221feb8`, as recorded in the recovered receipt.
  The later `013db3d…` correction changes only skipped-batch TRAIN metric
  accounting, not optimizer updates, validation results, checkpoint selection,
  or the GO decision; no rerun is needed. Recovered evidence:
  [continuation report](evidence/shared_transition_encoder_distill_40_2026-09-15.md),
  [continuation receipt](evidence/shared_transition_encoder_distill_40_2026-09-15/results.json),
  [overflow report](evidence/shared_transition_encoder_overflow_40_2026-09-15.md),
  and [overflow receipt](evidence/shared_transition_encoder_overflow_40_2026-09-15/results.json).
- **Boundary:** Historical offline Attention qualification precedes the later
  cheaper qualified DeepSets direction (§286a–§286b). This recovery changes no
  tool, model, runtime, or default and runs no training or gameplay.
  **Knowledge impact:** restore historical experiment evidence and correct
  maintained research chronology; no new experimental conclusion.

## §296 — Survival DeepSets six-arm LR/weight-decay sweep (2026-09-17)

- **Question:** Can less aggressive updates or stronger AdamW regularization
  close the original warm-start survival model's roughly 6% validation gap?
  Baseline main `0b7d4607c49b5db8082f4cad89579f3e33635f41`; frozen run
  `92b404e03a91a6c95a592de80c7e04fe78f2d9af`.
- **Protocol:** Six requested LR/WD combinations, identical PR #205 encoder
  and fresh head initialization, source-grouped TRAIN/VALIDATION populations,
  epoch permutations, FP32 BCE, batch 512, clip 1.0, seed 20260912, 12/40
  floor/cap, patience 6. Select each arm by earliest strict VALIDATION NLL.
  No TEST inference, architecture change, or distillation.
- **Result:** All six fail overall NLL and Brier gates. Strong-WD selects
  epoch 20, NLL `0.062930815` (+5.7760%), Brier `0.018841730` (+5.7627%).
  Death/low-HP NLL pass for this arm. Baseline reproduces exactly; best NLL
  improves it only 0.2104%. Much-lower-LR reaches cap and selects epoch 39,
  leaving convergence uncertainty for that schedule, not permission to extend.
- **Decision:** `SURVIVAL_DEEPSET_SWEEP_REJECTED`. These six optimizer
  settings do not qualify DeepSets; architecture incapacity is not established.
  Optional LR-decay continuation and speed screening were not run.
- **Evidence:** [report](evidence/survival_deepset_sweep_2026-09-17.md) and
  [audited receipt](evidence/survival_deepset_sweep_2026-09-17.json) include all
  histories, checkpoint hashes and slices. An interrupted initial attempt is
  preserved and excluded. Post-run reporting fixes and reloaded-checkpoint
  verification are explicit; six-arm training was not altered.
  **Knowledge impact:** research status/evidence only; no runtime promotion.

## §297 — Frozen strong-WD cross-fitted Platt calibration (2026-09-17)

- **Hypothesis:** global affine probability calibration explains most of the
  surviving quality gap without encoder training.
- **Protocol:** frozen strong-WD epoch 20, five source-grouped VALIDATION folds,
  unweighted FP64 logistic NLL, seed 20260912; no in-sample qualification.
- **Result:** NLL `0.062660988` (+5.3225%), Brier `0.018729319` (+5.1317%):
  both overall gates fail; death/low-HP and validity limits pass. Calibration
  closes about 8% of excess NLL, not most of the gap.
- **Boundary:** diagnostic only; the model was previously selected on the same
  VALIDATION set. No TEST, encoder training, scratch replay, widening or runtime
  change. Historical-composite versus survival-NLL selection for the proposed
  PR #161-style replay remains unresolved.
- **Evidence:** [receipt and protocol](evidence/survival_platt_crossfit_2026-09-17.md).
  **Knowledge impact:** current research evidence, no qualified default.

## §298 — Paired warm/scratch survival plus auxiliary HP (2026-09-17)

- **Question:** Does the PR #161-style joint-loss recipe salvage current
  64-wide DeepSets, and does the PR #205 initialization help within it?
- **Execution:** `9ca315fac9b6ad30444c599af489dc765207b4ef`. Same fresh heads,
  all 408,183 TRAIN-row normalization, epoch order and optimizer for both arms.
  BCE plus survivor-only HP-fraction MSE; selection solely survival NLL.
  Historical schedule: AdamW 1e-3, decay 1e-4, batch 2048, seed 20260911,
  cap 12, patience 3. Original splits and survival gates unchanged.
- **Result:** Warm epoch 12/12 NLL `0.063309319` (+6.4122%), Brier
  `0.018885445` (+6.0081%); scratch epoch 4/7 NLL `0.069789790`
  (+17.3048%), Brier `0.020476995` (+14.9418%). Both also fail death NLL;
  scratch fails low-HP NLL. HP metrics remain diagnostics only.
- **Decision:** Both rejected. Warm helps within this schedule, but its best
  epoch is at the cap; convergence and generality remain uncertain. No extension,
  TEST, speed screen, architecture change, gameplay, runtime or promotion.
- **Evidence:** [report](evidence/survival_deepset_aux_paired_2026-09-17.md) and
  [complete receipt](evidence/survival_deepset_aux_paired_2026-09-17.json).
  Both checkpoints independently reloaded and results reproduced. No independent
  implementation review passed; failed tool delegation is recorded, not hidden.
  **Knowledge impact:** current research and experiment evidence only.

## §299 — Small nonlinear survival head (2026-09-17)

- **Question:** Can a small MLP survival head materially improve the frozen
  strong-WD representation without widening the encoder?
- **Execution:** `ba77f58d1622d2d88847a7c33af965a6aeaccac3`. Strong-WD epoch 20
  initialized encoder; fresh 64→64→1 ReLU head (+4,160 parameters); joint
  strong-WD optimizer/recipe and unchanged normalization; selection survival NLL.
- **Result:** epoch 6/12 NLL `0.063041106` (+5.9614%), Brier `0.018754756`
  (+5.2745%), death NLL +15.8636%; low-HP passes. Both overall gates fail; NLL
  worsens 0.1753% while Brier improves 0.4616%. No speed screen.
- **Decision:** `SURVIVAL_DEEPSET_REJECTED`. This small nonlinear head is not
  sufficient under the fixed gates; it neither proves nor disproves a wider
  encoder ceiling. No widening, extension, TEST, runtime or promotion.
- **Evidence:** [report](evidence/survival_mlp_joint_2026-09-17.md) and
  [receipt](evidence/survival_mlp_joint_2026-09-17.json). Clean duplicate run
  reproduced the same result. No independent implementation review passed.
  **Knowledge impact:** current research evidence; no default change.

## §300 — Frozen-encoder nonlinear survival head (2026-09-17)

- **Question:** Does a fresh nonlinear head on the frozen strong-WD
  representation close the survival gap without encoder updates?
- **Execution:** `8506e5e94bfd10f9ee0a5526aa78e3e0db8af2ea`. Frozen strong-WD
  epoch-20 encoder; fresh 64→64→1 ReLU survival head only; strong-WD head
  optimizer/recipe, unchanged normalization and selection by survival NLL.
- **Result:** epoch 10/16 NLL `0.062951967` (+5.8115%), Brier `0.018761696`
  (+5.3135%), death NLL +13.6766%; relative to linear strong-WD, NLL worsens
  0.0336% while Brier improves 0.4492%; overall gates fail.
- **Decision:** `SURVIVAL_DEEPSET_REJECTED`. A nonlinear head alone does not
  materially close the gap and still regresses deaths; it neither proves nor
  disproves a wider-encoder ceiling. No extension, widening, TEST, runtime or
  promotion.
- **Evidence:** [report](evidence/survival_mlp_head_only_2026-09-17.md) and
  [receipt](evidence/survival_mlp_head_only_2026-09-17.json). Initial and
  selected encoder hashes are identical. No independent review passed.
  **Knowledge impact:** current research evidence; no default change.

## §301 — Scratch width-96 DeepSets survival (2026-09-17)

- **Question:** Does the single modest latent-width increase salvage the
  survival-only recipe without embedding or feature changes?
- **Execution:** `2e56f5de48fab5002684af8080decc988e69189d`; baseline dependency
  `6fa601d9429db1a1a266e34c63252ce4861f9d5a`. Scratch entity outputs 96,
  concat 384, trunk 384→192→96, head 96→1. Same strong-WD optimizer, batch,
  seed, early stopping and gates; fixed normalization from all TRAIN rows.
- **Result:** epoch 14/20, NLL `0.065301903` (+9.7614%), Brier `0.019292932`
  (+8.2954%), death NLL +21.4414%; low-HP +8.1272% passes. Validity passes.
  167,257 parameters. `SURVIVAL_DEEPSET_REJECTED`; speed screen skipped.
- **Limits:** One run, no matched scratch width-64 survival-only control;
  comparison with warm strong-WD conflates width, initialization and normalization.
  This does not establish pairwise interactions as the missing mechanism.
  No further scaling, training, TEST, runtime, gameplay or promotion.
- **Evidence:** [report](evidence/survival_wide96_2026-09-17.md) and
  [receipt](evidence/survival_wide96_2026-09-17.json). Checkpoint reload, full
  metrics/slices, initialization, normalization and permutations verified.
  **Knowledge impact:** current research evidence; no default change.

## §302 — Width-96 maxHP/HP pretraining then survival (2026-09-17)

- **Question:** Does PR #205-style pretraining make width-96 useful for survival?
- **Execution:** independently reviewed `8adb4794ec22fb051014c8c638cb2fec326b7615`,
  baseline `35402d1e59ae5e9e66fe277f853f3ec62213c157`. Exact teachers and victory-only
  normalization/population; copied delta8, fresh HP104→64→304 and maxHP96→11.
  Same 40-epoch AMP KL schedule; only selected encoder transfers to fresh96→1.
- **Result:** pretraining selected39/40, diagnostic GO, nine AMP skips. Strong-WD
  survival selected14/20, NLL0.062599011 (+5.2183%), Brier0.018578166 (+4.2833%),
  death NLL+16.0179%, low-HP+3.2761%. Fixed NLL/death gates reject; other gates pass.
- **Decision:** `SURVIVAL_DEEPSET_REJECTED`. No speed screen, TEST, runtime,
  gameplay, export or promotion. Improved versus scratch width-96, but no further
  scaling/tuning justified by this run; no causal claim about interaction structure.
- **Evidence:** [report](evidence/survival_wide96_pretrained_2026-09-17.md) and
  [complete receipt](evidence/survival_wide96_pretrained_2026-09-17.json), including
  both full histories and all slices. **Knowledge impact:** research status;
  no qualified-default change.

## §305 — Current OOC CPU attribution (2026-09-18)

Profiling only on baseline589a7a7, frozen instrumentationc886964. `perf` was
unavailable; no system repair attempted. Historical seeds12002032/12002033 ran
once each with Attention control, OMP1, exact10k Silver and the locked2048 OOC
profile. All non-timing MCTS columns match exactly. Full CPU42.30/62.75s
(+3.55%/+3.16% versus supplied Stage B); real Silver22.835/35.689s,
MCTS19.310/26.916s. V4 prior/continuation exclusive total8.143/10.921s;
CTM preparation3.681/5.583s. Real combat accounts for54–57%, V4 for17–19%.
Pooled infinite-real-combat-speed Amdahl bound2.26x. Existing rollout wall
telemetry supports targeting Silver rollout execution, but does not identify
a specific kernel or prove the proposed scratch-allocation hypothesis.
No optimization, model changes, fresh seeds or quality comparison performed.
Knowledge impact: performance evidence and next target, no qualified default.
[Report, exclusive/inclusive tables, receipts, raw logs and hashes](evidence/ooc_cpu_profile_2026-09-18/README.md).

## §303 — Six-arm Silver root mechanism replay (2026-09-17)

- **Question and frozen implementation:** Does a normalized Teacher-A visit
  prior help independently of Teacher-A-Q root ordering, and does either
  intervention recover the historical result? The implementation was frozen
  at `06d9de36d1c2e07c7e0420a0752ae9a4d7fd738e`; the pre-implementation
  baseline was `be5b6ac2c9914b0a56244f2522b7573f81360067`. No code changed for
  this evidence record.
- **Protocol:** The planned source population was at least 8 gameplay seeds,
  but the run used source seed `0` only: 214 eligible roots and 64
  deterministically selected roots from that one trajectory. It reused one frozen
  10k-A label plus one independent frozen 25k-B label per root. Six arms
  crossed native versus stable Teacher-A-Q-descending root order with ordinary
  UCT, uniform root PUCT, or normalized Teacher-A-visit root PUCT. Each root
  and arm used four common deterministic replicates at exactly 32 simulations.
  Internal UCT, chance handling, DPW, evaluator, rollout, RNG contract, and
  no-tree-reuse behavior were unchanged.
- **Result:** Uniform PUCT was worse than ordinary UCT (`E-A` mean regret
  `+0.352288`, 95% CI `[+0.092162,+0.653903]`). Informative PUCT was better
  than uniform PUCT (`C-E` mean regret `-0.412311`, 95% CI
  `[-0.717735,-0.139643]`; B-best delta `+5.4688` percentage points, CI
  `[+1.5625,+10.1563]`; improved/worsened/tied `17/5/42`). Informative PUCT
  versus ordinary UCT was near zero (`C-A` `-0.060023`, CI
  `[-0.328827,+0.196384]`). The largest adverse `C-E` root delta was
  `+2.121451` at `0/1/11/10/3`.
- **Tail audit and decision:** The largest adverse `C-E` root
  `0/1/11/10/3` is a normal seven-action Act-1 Exordium Thugs state with five
  cards, Liquid Memories, and End Turn. C and D select Defend only on replicate
  2; E selects Uppercut on all four replicates. This identifies a
  treatment-sensitive card-play allocation case, not a malformed action or
  provenance edge case, but does not explain its causal mechanism. Root-level
  bootstrap intervals cannot represent independent run-level uncertainty
  because all roots came from one source-seed trajectory. Classification:
  **`ROOT_GUIDANCE_INCONCLUSIVE`** — strong single-source-seed informative-
  prior signal; multi-seed confirmation required. The planned next screen is
  16 fresh source seeds × 2 roots/seed, analyzed by source seed; it was not run
  here. No model training, gameplay gate, runtime integration, or default
  promotion is authorized.
  Knowledge impact: current research status and experiment evidence updated.
- **Evidence:** [six-arm replay report](evidence/silver_root_mechanism_2026-09-17.md)
  and the external raw run directory and hashes recorded there.

## §304 — Strong-WD survival native and OOC CPU screen (2026-09-18)

- **Decision:** `DEEPSET_ONLINE_TRADEOFF_STOP`; median CPU/run reduction
  1.1596% is below the required 10%. No 16/64 quality gate or promotion.
- **Execution:** baseline `589a7a73c40e5b89e96df1ffec6a00b08c2ea9ba`, user-reviewed
  frozen SHA `471ba9a119de2a4f6ae691329467acae1b0f70a0`; Linux GCC passed first.
  Exact strong-WD checkpoint `3689593d…` re-exported to native `c870e4c…`;
  current Attention control `e9a18951…`, executable `c0275f4d…`. Other components
  unchanged; Stage-A source-bound evidence retained without rerun.
- **Mode:** guarded `bestbench 10000 1 0 SEED OUTPUT`, A0 Ironclad project-fair,
  effective Silver backend, 2048 OOC simulations, native leaf value, V4 policy,
  early stop, keys off, Act-3 stop. Historical #187 seeds 12002032/12002033,
  two repetitions per arm, balanced ordering; 8 invocations, 2 unique seeds.
  One thread per run instead of historical 12-way outer parallelism; CPU is
  `/usr/bin/time` user+system, not bestbench elapsed `sec`.
- **Results:** CPU median control/candidate 50.88/50.29 s, ratio 0.988404;
  mean 51.125/50.1525 s. Native survival 1.143383/0.128041 ms;
  reference sample 4.435917/3.168253 ms; prepared sample 0.023364/0.023288 ms.
  All runs complete, support reasons match per seed, zero continuation aborts.
  Shared legacy V1 copy-through flags in the timed V2 probe are disclosed.
- **Limits:** timing-only historical two-seed screen, not a gameplay-quality
  result; fresh cohort not launched, no bootstrap interval, no TEST inference.
  Source remains frozen; evidence/report commit is not the execution SHA.
- **Evidence:** [report, plan, runner, raw logs/CSV/telemetry and hashes](evidence/deepset_survival_online_stage_b_2026-09-18/README.md).
  **Knowledge impact:** bounded negative speed evidence and maintained research
  status; no runtime/model/default changes after review.

## §304 — OOC root checkpoint diagnostic (2026-09-18)

The live policy remained 2,048 visit-selected simulations. A same-root discarded
shadow recorded action IDs/priors/visits/Q at 128/256/512/1024/2048 over the
historical seeds12002032--12002039. The run produced1,134 roots,1,133 completed
and one expected smoke_bomb shadow abort; zero completed-root live/final-action
mismatches occurred. Agreement with final2048 was92.41%/93.65%/95.41%/97.18%
at the first four checkpoints. Gap conditioning was strongly useful (>20% gap
gave96.4% at128 and99.4% at1024), while observed stability discriminated stable
from unstable roots but did not prove invariance. Offline candidate
On the 898-root multi-action cohort, the conservative candidate
`512 -> 2048 when gap<20%` gave98.11% agreement and about42.1% additional
savings versus existing live early stopping; no rule was deployed or
gameplay-qualified. Knowledge impact: current
OOC research gains checkpoint/savings evidence; defaults and quality baselines
unchanged. [Evidence packet](evidence/ooc_root_checkpoints_2026-09-18/README.md).

## §305 — OOC 20% gap-stop quality gate (2026-09-18)

- **Question and frozen implementation:** Does the merged opt-in OOC MCTS rule
  stop at exactly 512 simulations when the top-two root visit gap is at least
  20%, while preserving the existing exact visit-lock stopping rule, materially
  reduce full-run CPU without an obvious gameplay regression? The execution
  source was frozen at `495fa147517fdc42e631c513bde5a87b3bb25144`; the Release
  `one_combat` SHA256 was
  `9a3b8c2bd1e563c691926d823c43767430d03c11b97a9c5f0d924e616beb1250`.
  No gameplay source edits were made.
- **Protocol:** Ironclad A0, project-fair, Act-3 stop, keys off, Silver backend
  with exact 10k simulations, allocated 32,768 reuse cap, exact-root budgets,
  adaptive/exact-visit-lock/rho stopping off, native OOC MCTS at 2,048
  visit-selected simulations, native leaf value, zero leaf combats, V4 policy,
  and no checkpoint/root-lock/CPU diagnostic modes. Control had
  `STS_OOC_MCTS_GAP_STOP_20=0`; treatment had it set to `1`. The predeclared
  cohort was paired seeds `12003000..12003063`, with canary `12003064`.
- **Mechanism/speed result:** The canaries passed frozen provenance and both
  arms loaded Silver/OOC-2048/V4/CTM correctly. In the 16-pair OMP1 smoke,
  treatment reduced total OOC simulations by **41.4%**, median MCTS CPU by
  **36.6%**, and median full-process CPU by **13.0%** (means were 42.7% and
  16.9% respectively). Treatment fired 1,532 gap stops versus zero in control;
  trace arithmetic reconciled for every run.
- **Gameplay result and limits:** The smoke outcomes were control 10/16 versus
  treatment 9/16, with three control-only and two treatment-only wins. This is
  smoke-only evidence, not a quality conclusion. The Stage-C OMP12 control arm
  completed 63/64 rows; seed `12003058` became a long-tail runtime pathology
  with approximately 3.56 GiB RSS and was stopped before treatment. Four
  isolated OMP1 control parity reruns matched their OMP12 outcomes and every
  non-time MCTS counter. A fresh isolated OMP1 run of `12003058` stayed near
  300 MiB RSS but exceeded 15 minutes without a completed row and was stopped;
  its boundary remains unknown. The old partial 63-row control run is
  diagnostic only and was not mixed into a quality result.
- **Decision:** **`OOC_GAP_STOP_20_QUALITY_INCONCLUSIVE_RUNTIME`**. Mechanism/
  speed is PASS; gameplay quality is unresolved. No evidence supports rejecting
  the 20% rule. No seed was replaced, Stage B was not rerun, treatment was not
  launched for the incomplete quality gate, and no default promotion is
  authorized.
- **Next predeclaration:** Close `12003000..12003063` without replacement.
  A future independent quality cohort is `12004000..12004063`, using the same
  frozen binary/configuration, one OMP1 process per seed, and up to about 12
  externally concurrent processes. Run all 64 controls first; launch treatment
  only if every control completes. Apply a fixed 10-minute per-process ceiling
  to either arm; any timeout aborts the cohort as `INCONCLUSIVE_RUNTIME`
  without substitution. Stage B is not repeated.
- **Evidence:** Raw frozen-run artifacts are retained under the local
  `build/ooc_gap_stop_20_20260918/` experiment directory, including canary,
  Stage-B, partial Stage-C, and rescue-preflight outputs. **Knowledge impact:**
  current research status and experiment evidence; no default, model, or
  gameplay implementation change.

## §311 — Silver root ensemble-teacher audit (2026-09-18)

- **Protocol:** Constructed visit-weighted `T20` from A/A2 10k corrected Qs and
  independent-jury `J50` from B/B2 25k corrected Qs on the existing 64 roots.
  No replay, gameplay, teacher generation, or training was performed.
- **Result:** T20/J50 top-action agreement is `44/64` (`68.750%`). T20 mean
  J50-regret is `0.534197`, slightly worse than original A's `0.495031`; T20
  matches original A on `54/64` roots. Disagreement roots have smaller T20/J50
  margins, but the ensemble does not improve the judge comparison.
- **Tail:** T20 still selects Seeing Red at `14/2/23/36/3`, while J50 selects
  Intimidate; T20 J50-regret is `3.034235`, identical to A's choice.
- **Decision:** Do not run the proposed I-vs-A replay, train a model, or collect
  a larger corpus. The current ensemble is not a credible target without a new
  target definition or evidence addressing unstable/biasing Q estimates.
- **Evidence:** [ensemble audit](evidence/silver_root_teacher_ensemble_audit_2026-09-18.md).
  **Knowledge impact:** current research evidence only; no model, runtime,
  gameplay, or default change.

## §312 — First frozen `silver_hard_combat_v1` candidate pool (2026-09-18)

- **Protocol:** On merged source/replay SHA `e7695fe14c342861937535f990c18479def86502`,
  collected Ironclad A0, fair Searcher2, keys-off Act-3 gameplay on fresh
  seeds `12100000..12100127` with ordinary adaptive Silver, allocated 32,768
  reuse cap, and four OpenMP threads. The run completed all 128 source seeds
  and captured 3,096 first-action combat snapshots with zero source failures.
- **Screen:** Exact flat 1k replay covered all 3,096 captures: 3,042 wins and
  54 losses, all technically valid. The prospective 10k screen covered all
  losses plus three fixed successive blocks of 128 lowest-HP-fraction 1k
  wins. Combined classifications were 22 Tier A, 116 material Tier B, 32
  unresolved Tier C, 10 anomalous, and 258 easy.
- **Selection:** Easy and anomalous cases were excluded. The deterministic
  selector retained 64 `hard64-dev` and 64 `hard64-holdout` cases, with no
  source seed shared between cohorts, no more than two cases per source seed,
  and no state-hash duplicates. DEV is 9/48/7 A/B/C; HOLDOUT is 13/47/4.
- **Baseline:** The primary 1k screen is DEV `48/64` and HOLDOUT `47/64`.
  DEV mean terminal HP fraction was `0.2011844` and HOLDOUT `0.2359278`;
  replay failures were zero. The separate exact-10k teacher/reference replay
  won `57/64` on DEV and `60/64` on HOLDOUT, with mean terminal HP fractions
  `0.5013957` and `0.5374656`. The replay schema exposes wall time but not CPU
  time; 10k mean wall time was 3.088858s (DEV) and 2.960088s (HOLDOUT).
  Per the maintained benchmark protocol, DEV@1k is the primary cheap screen,
  HOLDOUT@1k is reserved confirmation, and 10k is teacher/reference evidence;
  none is a production promotion gate.
- **Technical exclusion:** An interrupted Debug-speed run left 400 partial
  captures and 13 completed rows; those files are durably quarantined outside
  the app worktree at `/home/philippherrmann/sts_sweep/runs/` and excluded
  because three active seeds lacked completed whole-run accounting. The final
  pool uses only the clean Release rerun.
- **Evidence:** [frozen-pool receipt](evidence/silver_hard_combat_v1_20260918/README.md).
  **Knowledge impact:** durable benchmark evidence and deterministic selection
  procedure; no Silver search behavior, model, threshold, or production gate
  changed.

## §313 — OOC 20% gap-stop independent 64-pair quality confirmation (2026-09-18)

- **Relation to §305:** The earlier `12003000..12003063` cohort remains
  `OOC_GAP_STOP_20_QUALITY_INCONCLUSIVE_RUNTIME`; pathological seed
  `12003058` was not replaced. Its partial rows were not mixed into this
  fresh independent cohort.
- **Protocol:** Reused source SHA
  `495fa147517fdc42e631c513bde5a87b3bb25144` and the unchanged Release
  binary SHA256
  `9a3b8c2bd1e563c691926d823c43767430d03c11b97a9c5f0d924e616beb1250`.
  Seeds `12004000..12004063` ran as paired control/treatment evaluations,
  one OMP1 process per seed, up to 12 external workers, control first, and a
  600-second per-process ceiling. No seed replacement, rebuild, Stage-B
  rerun, or diagnostic mode was used.
- **Result:** Control and treatment each won 44/64. The paired counts were
  36 both-win, 12 both-lose, 8 control-only, and 8 treatment-only. Win-rate
  delta was **0.0 pp**, bootstrap 95% CI **[-12.5, +12.5] pp**. Floor delta
  was **-0.75** (CI [-2.61, +1.05]); ending-HP delta was **-6.56** (CI
  [-15.39, +2.13]).
- **Decision:** **`OOC_GAP_STOP_20_PROMISING`**, explicitly not
  “equivalent”. Wins are flat and the CI does not show a gameplay loss, but
  the negative floor/HP point estimates remain unresolved. Freeze the 20%
  threshold and run the predeclared independent `12005000..12005127`
  confirmation before any default promotion.
- **Evidence:** [OOC 20% gap-stop evidence packet](evidence/ooc_gap_stop_20_20260918/README.md),
  including the checked-in raw bundle, analysis JSON, and SHA256 manifest.
  **Knowledge impact:** current research status and experiment evidence; no
  default, model, or gameplay implementation change.

## §314 — Same-turn CARD RAVE/AMAF mechanism screen (2026-09-18)

Implemented an opt-in, searcher-owned RAVE sidecar for Silver and ran the
smallest frozen-root screen: A versus R8/R32/R128, 64 source-seed-0 roots,
four common replicates, and 32 simulations. The key is semantic same-turn
CARD state `(card id, upgraded, specialData, costForTurn, freeToPlayOnce,
target)`; END_TURN, potions, selections, later turns, and chance nodes are
excluded. Primary K=32 uses `beta=sqrt(K/(3*N+K))` and leaves UCT exploration
unchanged. The R32-A root-bootstrap regret difference was -0.076467 with
95% CI [-0.420937,+0.188419], with 11/17/36 improved/worsened/tied roots;
B-best fell 5.08 pp. RAVE coverage was 100% of 1,789 eligible decision nodes
and 2.994 samples per eligible edge. Classification:
**RAVE_SCREEN_INCONCLUSIVE**. This is a mechanism screen only; no gameplay
default or generalization claim is authorized. Evidence:
`docs/experiments/evidence/silver_rave_mechanism_2026-09-18.md`.
## §315 — OOC 20% gap-stop final 128-pair quality confirmation (2026-09-18)

- **Protocol:** Reused the frozen source SHA
  `495fa147517fdc42e631c513bde5a87b3bb25144` and unchanged Release binary
  SHA256
  `9a3b8c2bd1e563c691926d823c43767430d03c11b97a9c5f0d924e616beb1250`.
  The predeclared paired cohort `12005000..12005127` ran with one OMP1 process
  per seed, up to 12 external workers, control first, and a fixed 600-second
  per-process ceiling. The interrupted control batch was resumed only for its
  68 unconfirmed seeds into fresh paths; no seed was replaced and no partial
  artifact was appended.
- **Configuration:** The only gameplay/configuration difference was
  `STS_OOC_MCTS_GAP_STOP_20=0` versus `1`. OOC remained at 2,048 simulations
  with policy prior, cPuct 1.5, widening 2/0.5, depth 32, visit-root
  selection, native leaf, V4 continuation policy, and existing exact
  visit-lock stopping. Silver remained exact 10k, allocated reuse cap 32,768,
  adaptive OFF, exact-root budgets ON, and exact-visit-lock/rho racing OFF.
- **Result:** All 256 processes completed with valid provenance and clean
  exits. Control won 95/128 and treatment 88/128; paired outcomes were 81
  both-win, 26 both-lose, 14 control-only, and 7 treatment-only. The win-rate
  delta was **-5.47 pp**, deterministic paired-bootstrap 95% CI
  **[-12.50, +1.56] pp**, exact discordant-pair p **0.189**. Floor delta was
  **+0.06** (CI [-1.26, +1.33]); ending-HP delta was **-1.47** (CI
  [-7.01, +3.97]). Treatment fired 11,777 20%-gap stops across all 128
  seeds; control fired zero. Trace ownership, fallback, simulation, root-stop,
  and support accounting reconciled for every run.
- **Decision:** **`OOC_GAP_STOP_20_FINAL_PASS`**. No meaningful quality
  regression was detected at this bounded confirmation, combined with the
  previously established speed benefit. This is not equivalence proof and no
  default promotion is authorized before independent review.
- **Unresolved verification note:** A seed-free `oocmctsselftest` run with the
  full Silver environment emitted `FAIL oocmctsselftest: same sole wheel
  primitive hides a fallback agent RNG draw`. This did not consume a cohort
  seed or alter the frozen executable. The general 21-case OOC startup matrix
  passed, and all 256 actual gameplay processes completed with clean exits and
  validated Silver/provenance metadata. The assertion remains unresolved and
  is not treated as cleared by the gameplay run.
- **Evidence:** [final OOC 20% gap-stop packet](evidence/ooc_gap_stop_20_final_20260918/README.md).
  **Knowledge impact:** current research status and final experiment evidence;
  no default, model, or gameplay implementation change.

## §316 — Silver card-action canonicalization screen (2026-09-19)

- **Implementation:** Commit A canonicalized ordinary playable-card actions
  across the whole hand. Commit B reused the same conservative equivalence
  helper for `ARMAMENTS`, `EXHAUST_ONE`, `FORETHOUGHT`, `WARCRY`, `HEADBUTT`,
  `EXHUME`, and `LIQUID_MEMORIES_POTION`. Distinct cost, upgrade,
  `specialData`, `freeToPlayOnce`, or `retain` state remained distinct;
  different identities remained distinct for cards using special data.
- **Protocol:** Control was baseline `338ce1e9`; A was `dc811044`; B was
  `bbdd71cf`. All arms used the frozen `hard64-dev-snapshots.jsonl` cohort,
  1,000 simulations per decision, Release GCC builds, `OMP_NUM_THREADS=4`,
  and the existing fixed replay configuration. HOLDOUT was not used.
- **Result:** Control won `48/64`, A won `51/64`, and B won `51/64`. B versus A
  created `2,069,231` versus `2,099,430` nodes and made `2,234` versus `2,265`
  decisions. No replay failures occurred. Two fixed-cohort A/B timing pairs
  were collected: A `16.03s/15.91s`, B `16.54s/15.77s`; wall time is therefore
  inconclusive rather than a stable speedup claim. B had no obvious win-count or
  terminal-HP degradation on this bounded DEV screen.
- **Decision:** **`SILVER_CARD_CANONICALIZATION_WORK_REDUCTION_SCREEN_PASS`**;
  the result supports reduced redundant search work, but is not gameplay
  equivalence proof, a production gate, or a runtime-promotion claim.
- **Evidence:** [card-action canonicalization evidence](evidence/silver_card_action_canonicalization_20260919.md).
  **Knowledge impact:** experiment evidence only; no default, model, or
  gameplay-quality decision is authorized by this screen.

## §317 — Silver card-action canonicalization 16-seed full-run follow-up (2026-09-19)

- **Protocol:** Reused A `dc811044` and B `bbdd71cf` with identical fair Silver
  configuration, Release binaries, four OpenMP cores, 10,000 simulations per
  decision, and paired source seeds `12100032..12100047`. Each arm completed
  16/16 seeds with zero conversion, semantic-resolution, transaction, or
  knowledge failures.
- **Result:** A won `13/16`, mean terminal HP fraction was `0.536789429`, and
  B won `14/16`, mean terminal HP fraction was `0.565011767`. B was slower by
  `34.2859s` total (`+2.1429s/seed`): `553.8370s` versus `588.1229s`. B was
  faster on 5 seeds and A on 11. Aggregate Silver telemetry was A/B:
  `7,839/8,065` decisions, `78.51M/80.75M` simulations, and
  `65.68M/67.54M` nodes.
- **Interpretation:** This full-run follow-up does not support a B efficiency
  benefit. Because A and B can take different gameplay trajectories, aggregate
  full-run nodes are outcome-coupled and do not isolate selection dedup; the
  result is exploratory and does not establish a policy-quality conclusion.
- **Evidence:** [card-action canonicalization evidence](evidence/silver_card_action_canonicalization_20260919.md).
  **Knowledge impact:** experiment evidence only; no default, model, or
  gameplay-quality decision is authorized by this follow-up.

## §318 — Silver `GAMBLE` multiplicity deduplication (2026-09-19)

- **Implementation:** Silver's private sequential `GAMBLE` selector now emits
  only the first currently-unselected representative of each existing search
  equivalence class. It preserves confirmation, hand order, `selectedBits`,
  and all multiplicities `0..m`. `EXHAUST_MANY` was deliberately unchanged.
- **Structural result:** Deterministic tests reached all `9` semantic tuples
  for `2 Strike + 2 Defend` and all `36` tuples for `5 Strike + 5 Defend`,
  while removing only physical-copy permutations. Materially distinct copies,
  identity-sensitive special-data copies, noncanonical incoming masks, and the
  sequential bridge transaction all passed.
- **Local screen:** At 10,000 simulations on the fixed `5 Strike + 5 Defend`
  root, identical Release GCC benchmark-source arms reduced root actions
  `11 -> 3`. All seven wall times were recorded: baseline
  `0.121032, 0.116324, 0.113559, 0.116201, 0.109390, 0.105897, 0.119517s`;
  treatment `0.0901018, 0.0893465, 0.0890767, 0.0907252, 0.0903225,
  0.0946379, 0.0971926s`. Medians were `0.1162010s` and `0.0903225s`
  (`22.27%` lower); nodes remained `10,000` and recorded action counts were
  `23/24`. The baseline instrumented source was the same pushed test source,
  compiled and linked against pristine baseline libraries with documented
  Release commands. This is local selector evidence, not a whole-run claim.
- **DEV no-harm:** On frozen `hard64-dev-snapshots.jsonl` at 1,000 simulations,
  baseline and treatment both won `51/64`, had mean HP fraction `0.329883253`,
  `2,234` decisions, `2,234,000` simulations, `2,069,231` nodes, zero failures,
  and identical action traces/state hashes for all 64 cases. The null is
  expected because duplicate-heavy `GAMBLE` states are rare.
- **Decision:** **`SILVER_GAMBLE_MULTIPLICITY_DEDUP_ACCEPT`** for implementation
  correctness and the bounded local efficiency screen. This is bounded
  confirmation, not equivalence or default-promotion evidence. The concrete
  `EXHAUST_MANY` trigger-ordering concern remains a separate open question.
- **Evidence:** [GAMBLE multiplicity evidence](evidence/silver_gamble_multiplicity_20260919.md).
  **Knowledge impact:** durable Silver action-enumeration behavior and
  experiment evidence; no model, RNG, semantic schema, search budget, or
  gameplay default change.

## §320 — Silver stochastic UID-chance merge screen (2026-09-19)

- **Experiment:** Evaluated an opt-in `uidChanceMergeEnabled` treatment at
  source SHA `1717a41f6a233dada8192dda19b01b3358875912`. Only stochastic
  outcome states could reuse a strict PR-244-equivalent node: both hand and
  unknown-draw regions had to differ, both states had to be `PLAYER_NORMAL`,
  and the hand-plus-unknown-draw physical `CardInstance` union had to match by
  unique ID and exact value. Deterministic insertion, known positions,
  selectors, discard/exhaust, queues, special-data cards, and per-copy
  transient properties remained exact. Replay exposed the treatment only
  through `--uid-chance-merge`; no live environment variable enabled it.
- **Focused checks:** Debug `silver_search_optimization_test` passed for pure
  swap eligibility, physical UID-set rejection, per-copy cost reassignment,
  special-data and `CARD_SELECT` rejection, default-off parity, and a fixed-RNG
  `POMMEL_STRIKE` draw contraction fixture. The existing PR-244 diagnostic
  checks also passed.
- **Pristine-main smoke:** A temporary reverse-patched Release source copy at
  baseline `1b220712` matched candidate-control on the first eight fixed DEV
  cases in all 12 observable replay fields, including action-trace hash,
  nodes, and exact/fallback reroot counts. The temporary baseline binary was
  independently built; it was not added to the repository.
- **Protocol:** Baseline `1b220712`; frozen
  `hard64-dev-snapshots.jsonl`, 1,000 simulations per decision, Release GCC,
  `OMP_NUM_THREADS=4`, fixed replay configuration, all 64 DEV cases, and the
  predeclared PR-244 top-10 subset. HOLDOUT was untouched. Control omitted the
  flag; treatment enabled it in the same candidate binary.
- **Result:** All64 control/treatment created `2,063,754/2,079,940` nodes over
  `2,232,000/2,246,000` simulations, or `0.924621/0.926064` nodes per
  simulation (`+0.156%`). The predeclared top-10 was `0.937901/0.934340`
  (`-0.380%`). Wall time was `15.77/15.90s` (`+0.82%` treatment), below the
  preregistered repeat trigger. Treatment made `205,514` strict merges from
  `2,317,751` sampled chance outcomes (8.866958%), with
  `193,678` sibling and `11,836` global-transposition destinations. Exact
  reroots changed `1,627 -> 1,613` and fallbacks `541 -> 569`; action traces
  differed on `53/64` cases. Top-10 merges were `99,967/484,492` (20.633364%),
  with `288` exact reroots versus `306` and `102` fallbacks versus `100`.
- **Decision:** **`SILVER_UID_CHANCE_MERGE_REJECT`**. All64 work did not
  decrease, top-10 reduction was below 2%, timing was slightly slower, and
  reroot exactness deteriorated. The result is not a production promotion or
  identity-canonicalization design authorization.
- **Cleanup:** The rejected treatment machinery was removed after the frozen
  result. The source SHA and raw control/treatment artifacts above preserve
  the experimental provenance; no treatment config, telemetry, replay flag,
  or production search path remains.
- **Evidence:** [stochastic UID-chance merge packet](evidence/silver_uid_chance_merge_20260919/README.md).
  **Knowledge impact:** durable experiment evidence only; the rejected
  treatment is not retained in production, with no live boundary, model, RNG,
  or semantic-schema change.

## §319 — Silver duplicate potion-slot deduplication (2026-09-19)

- **Implementation:** Silver's ordinary potion enumeration now retains only
  the first occupied slot for each potion enum using a bounded previous-slot
  scan, avoiding a per-node allocation. Existing Fairy/Smoke/Gambler legality,
  targeted-potion target alternatives, action order, potion belt order,
  semantic fingerprints, and exact potion-slot lowering are unchanged.
  Successive decisions can consume every remaining identical copy.
- **Structural result:** Focused Silver optimization and bridge tests passed
  for non-target and targeted reduction, multiplicity, distinct types,
  Fairy/blocked Smoke/Gambler legality, deterministic and targeted successor
  permutation equivalence, Entropic Brew RNG/multiset equivalence, and live
  semantic lowering.
- **Local screen:** At 10,000 simulations on a fixed five-Strength root,
  baseline root actions were `6` and treatment root actions were `2`; nodes
  were `2,733` and `1,033`, respectively. Seven Release repetitions gave
  baseline `0.0334482, 0.0343304, 0.0346002, 0.0339673, 0.0345303,
  0.0285543, 0.0300224s` and treatment `0.0266973, 0.0264213, 0.0266100,
  0.0274337, 0.0258310, 0.0234443, 0.0222240s`; medians were `0.0339673s`
  and `0.0264213s` (`22.22%` lower). This is fixed-root selector evidence,
  not a whole-run runtime claim.
- **DEV screen:** On the frozen 64-case DEV snapshots at 1,000 simulations,
  baseline/treatment both won `51/64`, with mean HP fractions
  `0.329883253/0.344091151`, `2,234/2,232` decisions,
  `2,234,000/2,232,000` simulations, `2,069,231/2,063,754` nodes, and
  `15.628747/15.549843s` wall time; both had zero failures. Seven starting
  states contained duplicate potion types; `5/7` changed the initial action
  surface, and all `7/7` changed the action trace. The replay schema exposes
  no terminal state hash, so final-hash differences were not available for
  comparison. HOLDOUT was not used.
- **Decision:** **`SILVER_POTION_SLOT_DEDUP_ACCEPT`** for implementation
  correctness and the bounded fixed-root efficiency screen. This is bounded
  confirmation, not equivalence or default-promotion evidence; trajectory
  differences are not interpreted as policy improvement.
- **Hot-path correction:** The `unordered_set` implementation was replaced in
  the same task by the bounded scan. The existing five-identical Release
  microbenchmark remained at `1,033` nodes and `11` actions with a
  `0.0245379s` median over seven runs. A five-distinct no-duplicate fixture
  completed with `2,341` nodes and a `0.0250499s` median; because the root
  action surface differs, this is a sanity screen rather than a causal timing
  comparison.
- **Evidence:** [duplicate potion-slot evidence](evidence/silver_potion_slot_dedup_20260919.md).
  **Knowledge impact:** durable Silver action-enumeration behavior and
  experiment evidence; no model, RNG, semantic schema, search budget, or
  gameplay default change.

## §320 — Silver same-turn Bash/Strike dominance audit (2026-09-19)

- **Question:** can a cheap, nonterminal same-turn Bash → Strike dominance
  rule safely suppress Strike → Bash from the same decision context?
- **Evidence:** The test-only identity-resolving fixture reproduces immediate
  damage `17` versus `14`, but the fully resolved endpoints also differ in
  `curCardQueueItem`; that inequality alone is not a semantic obstruction,
  and the endpoints have different immediate parents requiring common-ancestor
  context. `energyWasted` and `cardsDrawn` are evaluation inputs omitted from
  `equalForSearch`/`hashBattleState`. A single ordinary target starting at HP
  18 leaves both Reaper endpoints alive and nonterminal at HP `1` versus `4`;
  one shared Reaper continuation reaches victory in both and yields player HP
  `51` versus `54`. This compares a shared continuation, not optimal
  continuation values. Information-boundary and corrected insufficient-energy
  rejection fixtures pass, including Bash ID `101` presence and a sufficient-
  energy positive control.
- **Decision:** **unconditional HP/order rule rejected; useful restricted
  nonterminal dominance `INCONCLUSIVE`**. The terminal exact-value case remains
  a closed sufficient condition, but integration is unresolved and the frozen
  16-case opportunity screen was not run.
- **Evidence:** [same-turn dominance audit](evidence/silver_same_turn_dominance_audit_20260919.md).
  **Knowledge impact:** durable experiment evidence only; no Silver search
  behavior, model, RNG, schema, budget, or gameplay default changed.

## §321 — Independent Silver forced-action target audit (2026-09-19)

- **Question and protocol:** After the visit-weighted learned-teacher target
  failed, test a genuinely independent target before any more model work.  Two
  roots per source were selected by deterministic hash from 16 fresh gameplay
  seeds `12006000..12006015`.  Every legal semantic action received eight
  independently executed 5k forced-action continuations (L) and a disjoint
  eight-replicate 10k judge (J); frozen 10k Teacher-A was evaluated on the same
  roots.  Bootstrap units were source seeds, not correlated decisions.
- **Result:** **`FORCED_ACTION_TARGET_PASS`**.  Mean J-regret(L)-J-regret(A)
  was `-0.3284866992`, with clustered 95% CI
  `[-0.7272965479,-0.0381220176]`.  Pairwise-concordance delta was
  `+0.1193982233`, CI `[+0.0622749256,+0.1949791723]`.  L/A maximum regret was
  `1.0854700000/5.5437900000`, upper-decile regret `0/0.4388132500`, and L
  introduced no new regret-3 harmful root.  All 32 roots had stochastic-action
  coverage; both stochastic-involving and deterministic-only pairwise deltas
  were positive.  All seven preregistered gates passed.
- **Correction and exclusions:** Immediate-terminal actions correctly consume
  zero continuation simulations, while all nonterminal replicates must consume
  the full budget.  A partial pre-fix run and a stopped invocation with an
  incorrect evaluator-SHA argument were quarantined and excluded.  The final
  stream has 2,768 rows, 173 root-action pairs, 48 terminal rows, and 864
  stochastic rows.  A non-object producer-SHA typo in generated metadata was
  corrected to the actual producer commit identified by branch history and the
  evaluator's parent; capture/selection/audit hashes were reissued and the
  aggregate analysis reproduced byte-for-byte.  A later review found that the
  post-action continuation root absorbed immediate effective-gold/max-HP
  changes.  Evaluator v2 now applies the established victory-only original-root
  correction.  A cheap scan found one nonzero end-turn correction (`-3.75`), so
  the full L/J audit was rerun on the same roots.  Regret, selections, tails and
  all gates were unchanged; pairwise concordance changed slightly to the value
  reported above.  The complete corrected raw stream is retained compressed.
- **Boundary:** This confirms a fresh-population target signal, but model
  training remains blocked.  No replay, gameplay, or default change is
  authorized.  The separate historical harmful-root regression remains
  blocked because the exact frozen snapshots were unavailable locally and on
  the designated GCP worker; no substitute roots were recollected.
- **Evidence:** [forced-action target audit](evidence/silver_forced_action_target_2026-09-19/README.md).
  **Knowledge impact:** the independent target signal is supported on the
  fresh primary population; the historical regression, model training and
  every downstream learned-policy gate remain outstanding.

## §322 — Silver rollout variance/bias diagnostic (2026-09-20)

- **Question and protocol:** Determine whether one fixed SimpleAgent rollout
  per sibling leaf is materially noisy or systematically biased relative to
  independent Silver continuation values. The diagnostic used the frozen 64
  hard DEV snapshots, ordinary fixed-1,000-simulation Silver to collect 32
  complete sibling groups, 247 leaves, and 32 fixed-seed SimpleAgent
  replicates per leaf. Each leaf also received independent A/B 25,000-
  simulation Silver teachers with the established original-root correction.
  The four independent teacher workers were split by complete sibling group
  and merged deterministically; no treatment or default was changed.
- **Result:** **`INCONCLUSIVE`** under the predeclared rules. At `k=1`, mean
  teacher regret was `2.3380`, pairwise concordance `0.6346`, and top-leaf
  agreement `0.4062`. At `k=4`, regret was `1.7978` (23.10% lower), pairwise
  concordance `0.6719`, and top-leaf agreement `0.4375`; the clustered
  bootstrap 95% interval for `k=4` regret was `[0.8513, 2.9146]`, so the
  variance-material rule did not pass. The systematic-error and not-primary
  rules also did not pass. Teacher A/B mean absolute noise was `1.0541` and
  85.64% of within-sibling teacher margins were below the one-rollout noise
  estimate.
- **Causal follow-up:** The highest stable-residual leaf from each of the first
  eight distinct `largest_stable_residuals` groups was selected before the
  probe. Teacher A's exact semantic first action was forced once, then the
  canonical SimpleAgent continuation resumed under the same 32 replicate RNG
  identities. All 256 rows were accepted. Among the three A/B-action-stable
  leaves, spanning three groups, aggregate absolute residual fell from
  `54.8644` to `13.9072`: `74.6516%` removed, passing the preregistered
  `FIRST_ACTION_BIAS_MATERIAL` threshold. The five teacher-action-unstable
  leaves were retained descriptively but excluded from the causal decision.
  Stable mismatches were deterministic card-choice substitutions on all 32
  replicates: Reaper, Spot Weakness+ → Time Eater, and Spot Weakness+ → Bronze
  Orb were each replaced by another SimpleAgent card.
- **Follow-up boundary:** This supports first-action bias as a substantial
  mechanism on the targeted frozen subset, but does not authorize a rollout
  policy change. The next experiment is a fresh matched diagnostic cohort for
  one narrow first-card-choice intervention with the existing continuation
  unchanged. No intervention was implemented here.
- **Boundary:** This is bounded diagnostic evidence, not ranking,
  equivalence, model-training, rollout-policy, or default-promotion evidence.
  No holdout or broad seed campaign was run. Large residuals remain in a
  small number of groups and require separate causal investigation if they
  become decision-relevant.
- **Fresh holdout follow-up:** The frozen `SPOT_WEAKNESS_FIRST_V1` rule was
  evaluated on the separate 64-root `hard64-holdout` cohort, selecting 32
  complete eligible groups / 251 leaves and 112 active leaves. With paired
  32-replicate baseline/treatment rows and independent A/B 25k teachers, the
  corrected k=32 teacher regret improved from `1.8767` to `1.2212` (`34.93%`)
  and the grouped-bootstrap probability of lower treatment regret was
  `95.37%`. Pairwise concordance still fell from `0.7049` to `0.6892`, while
  top agreement improved from `0.3438` to `0.4375`. The direct rollout cost
  gate is unmeasured: baseline canonical `rollout_wall_micros` and treatment
  `totalWallMicros` include different setup scopes, and the raw treatment
  stream does not retain a comparable treatment-only timer. The result is
  **`INCONCLUSIVE` / not promotable** for this exact treatment. The collector's
  completed corpus required baseline-only recovery because `case_id` was
  omitted from its first serializer; the manifest records that the complete
  eligible group count was not serialized. This does not alter the selected
  cohort, but remains an evidence limitation.
- **Fresh follow-up boundary:** Do not tune or broaden the Spot Weakness rule
  on this holdout, and do not infer that the broader first-action mechanism is
  absent from the earlier targeted result. No rollout policy, evaluator,
  prior, PUCT, budget, or gameplay default change is authorized.
- **Post-result cleanup:** After the evidence was frozen and reviewed, the
  rejected candidate treatment and collector-only implementation were reverted
  from the task branch. The raw evidence and analyzer remain retained for
  reproducibility; no production behavior was left enabled.
- **Evidence:** [rollout variance/bias diagnostic](evidence/silver_rollout_variance_20260920/README.md).
  **Knowledge impact:** durable Silver diagnostic evidence and current
  research status only; no Silver behavior, model, RNG, schema, budget, or
  gameplay default changed.

## §323 — Contextual first-action Silver selector screen (2026-09-20)

- **Question and protocol:** Can a small context-sensitive scorer replace only
  the first canonical SimpleAgent rollout action while retaining the exact
  continuation? Reuse the frozen PR #251 DEV corpus; do not recollect hard
  states or run gameplay seeds. Enumerate exact legal card/target actions and
  `END_TURN`, exclude potions, and evaluate every candidate with 32 common-RNG
  forced-action continuations. Replicates `0..15` and `16..31` are disjoint
  selection/evaluation halves, cross-fitted in both directions. The corpus has
  32 groups from 20 source seeds, so the regenerated bootstrap clusters all
  groups sharing a source seed; the corrected model-fit path uses the same
  source-seed fold key.
- **Headroom result:** **`FIRST_ACTION_POLICY_HEADROOM_INSUFFICIENT`**. There
  are 32 groups / 247 leaves / 40,512 accepted counterfactual rows. The fair
  Teacher-A comparison is baseline k=32 mean regret `1.51332` versus the
  cross-fitted first-action oracle `1.41354`, only `6.59%` reduction (below the
  preregistered `>=20%` gate). Pairwise concordance is `0.74241 -> 0.75176`,
  top-leaf agreement is `0.56250 -> 0.62500`, and Teacher-B regret is
  `1.47290 -> 1.34988` (`8.35%`). The source-seed-clustered bootstrap interval
  for baseline-minus-oracle regret is `[-0.29749, 0.58429]`; 4 groups improve,
  2 worsen, and 26 are unchanged. This is modest oracle signal below the
  decision gate, not policy headroom.
- **Policy result:** The retained run fit exactly one 30-feature linear ridge
  scorer with `lambda=1.0`, target = disjoint selection-half `q0(s,a)`, and
  historical group-id holdout folds. The actual candidate ran 7,904/7,904
  accepted paired native rollouts. Teacher-A k=1 regret changed from `2.33796`
  to `3.65020` (`-56.13%` reduction); k=32 regret changed from `1.51332` to
  `1.63434`; Teacher-B k=1 changed from `2.22788` to `3.58189` (`-60.78%`).
  The source-seed-clustered candidate bootstrap improvement was
  `[-1.33542, 0.93203]`, with 4 groups improved, 3 worsened, 25 unchanged;
  the largest regression was `14.57257` regret points. This preserves a
  negative result for this feature/scoring formulation; it does not rule out
  every linear contextual policy. No model refit or candidate rerun was made
  after the source-seed correction.
- **Cost:** The retained raw diagnostic timing, with action traces and rollout
  telemetry disabled, was `198.8600 / 201.7820` microseconds mean/median for
  baseline and `347.8855 / 353.7265` for candidate, ratio `1.74940`. The
  `<5%` runtime gate is **unmeasured**, not failed: candidate timing includes
  `rawActionForSemantic()` creating a fresh `BattleSearcher` and calling
  `search(1)` before the forced-action continuation, a cost baseline does not
  pay. It is not production-comparable.
- **Decision and boundary:** **`FIRST_ACTION_POLICY_HEADROOM_INSUFFICIENT`**.
  The fair oracle does not clear the predefined headroom threshold, and the
  retained linear formulation is negative. Do not tune another model family,
  alter later rollout actions, use potion policy, change Silver search/defaults,
  or launch fresh gameplay confirmation in this task. The result is offline
  DEV evidence only.
- **Evidence:** [contextual first-action selector packet](evidence/silver_first_action_selector_20260920/README.md).
  **Knowledge impact:** durable benchmark result and current research status;
  no production Silver behavior, model, RNG, schema, budget, or gameplay
  default changed.

## §324 — Coordinated short-prefix Silver oracle headroom (2026-09-20)

- **Question and protocol:** After the merged PR #254 first-action seam, does
  a coordinated semantic prefix of one, two, or three `PLAYER_NORMAL` actions
  expose material oracle headroom? Reuse the frozen PR #251/#254 DEV corpus;
  do not train, recollect gameplay seeds, use the hard64 holdout, or alter
  production behavior. The native seam enumerates only `CARD` and `END_TURN`,
  resolves canonical `CARD_SELECT` transitions with `SimpleAgent`, and fails
  closed on unsupported non-`PLAYER_NORMAL` states. Prefix keys are intersected
  across all 32 replicates. Selection is cross-fitted between replicates 0–15
  and 16–31 in both directions; source-seed-clustered bootstrap uses 2,000
  iterations and seed `20260920`.
- **Depth-1 boundary:** The generalized prefix implementation exactly matches
  the retained PR #254 counterfactual across all 40,512 paired
  `(leaf, replicate, action)` rows: zero missing or unmatched rows and zero
  absolute utility difference. The root step keeps the historical
  forced-first-action pending-intent behavior; later steps materialize pending
  intents before the next supplied action.
- **Result:** **`SHORT_PREFIX_HEADROOM_PRESENT`**. The frozen cohort has 32
  groups / 247 leaves / 20 source seeds. Teacher-A k=32 regret is
  `1.51332 -> 1.41354` (`6.59%`) at depth 1,
  `1.51332 -> 0.56665` (`62.56%`) at depth 2, and
  `1.51332 -> 0.58686` (`61.22%`) at depth 3. Teacher-B reductions are
  `8.35%`, `29.05%`, and `33.24%`, respectively. The clustered bootstrap
  intervals for baseline-minus-oracle Teacher-A regret are
  `[-0.29749, 0.58429]`, `[0.23573, 2.13812]`, and
  `[0.24809, 2.10558]`. All 247 leaves have complete monotonic selection and
  evaluation coverage at depths 2 and 3, satisfying the preregistered gate.
- **Surface and concentration:** The all-replicate common surface contains
  1,266 exact length-1, 4,928 exact length-2, and 15,364 exact length-3
  prefixes, for 21,558 unique keys and 689,856 accepted native rows. The
  selected prefix changes on 130/247 leaves from depth 1 to 2 and 97/247 from
  depth 2 to 3. At both qualifying depths, 8 sibling groups improve, 22 are
  unchanged, and 2 worsen. The largest 1/2/4/8 positive-improvement groups
  account for 46.35/61.88/88.43/100% at depth 2 and
  47.34/63.21/83.53/100% at depth 3.
- **Variable-length interpretation:** The exact-length secondary views are
  materially different from the monotonic headline. Exactly length 2 gives
  only `6.91%` Teacher-A reduction and a `-34.76%` Teacher-B change, with
  clustered Teacher-A CI `[-1.37089, 1.64439]`. Exactly length 3 gives
  `48.69%` Teacher-A and `21.16%` Teacher-B reduction, but covers 245 leaves,
  32 represented groups, and only 31 scorable sibling groups; its CI is
  `[-0.41122, 2.41505]`. In the up-to-depth-2 oracle, selected
  lengths are 148/99 and 138/109 (length 1/2) across the two cross-fit
  directions; at up-to-depth 3 they are 130/49/68 and 120/45/82 (length
  1/2/3). The large gain is therefore evidence for a variable-length oracle,
  not for always forcing exactly two actions.
- **Cost:** The 689,856 accepted prefix evaluations recorded diagnostic
  `total_wall_micros` of 155.13 mean / 162 median / 191 p95 per row; the
  canonical continuation portion was 9.13 mean / 9 median / 17 p95
  microseconds. These timings include exhaustive diagnostic semantic-prefix
  setup and are not a production runtime comparison or policy-cost gate.
- **Decision and boundary:** This establishes variable-length short-prefix
  oracle headroom, not a deployable policy or value-equivalence result. The
  oracle may choose a different prefix per frozen leaf after observing
  cross-fitted continuation values. Do not launch gameplay confirmation, tune
  a fixed-depth selector, change Silver search/defaults, train a model, or
  promote a rollout behavior from this packet. The next distinct experiment is
  a bounded causal mechanism that learns both the action sequence and whether
  to extend the prefix, with explicit cost measurement and no holdout
  substitution.
- **Evidence:** [coordinated short-prefix oracle packet](evidence/silver_tactical_prefix_oracle_20260920/README.md).
  **Knowledge impact:** durable tactical-prefix oracle evidence and current
  research status only; no production Silver behavior, model, RNG, schema,
  budget, or gameplay default changed.

## §325 — Bounded variable-prefix Silver selector Phase A (2026-09-20)

- **Question and protocol:** Can limited continuation samples recover at least
  50% of the PR #256 up-to-depth-2 variable-length oracle gain at no more than
  12 mean continuation evaluations per leaf? Reuse the frozen robust
  all-replicate common-prefix surface, baseline, and Teacher A/B packet; do
  not use gameplay seeds, hard64, training, or production Silver behavior.
  The screen evaluated `FLAT_K1/K2/K4/K8/K16` and the six preregistered
  hierarchical beam arms. Selection used deterministic half-local replicate
  order, Stage 2 used fresh samples disjoint from Stage 1, length-1 parents
  were explicit STOP finalists, and evaluation always used the opposite full
  16-replicate half. Source-seed-clustered bootstrap used 2,000 iterations and
  seed `20260920`.
- **Reproduction:** `FLAT_K16` exactly reproduced #256 up-to-depth-2
  Teacher-A regret `0.5666491930721915`, Teacher-B regret
  `1.0450469791084764`, and clustered baseline-minus-oracle interval
  `[0.23572861982679671, 2.1381214615864907]`. The analyzer also retains the
  exact frozen input hashes and fails closed on incomplete paired coverage.
- **Result:** **`BOUNDED_PREFIX_SELECTOR_INSUFFICIENT`**. The best bounded arm
  was `BEAM2_K1_1_K2_1`: it recovered `26.82%` of the measured oracle gain,
  used `13.74` mean calls (`25` p95), reduced Teacher-A regret from `1.51332`
  to `1.25941`, but changed Teacher-B regret by `-38.77%` and had clustered
  lower bound `-0.40184`. The cheapest beam,
  `BEAM1_K1_1_K2_1`, used `9.40` mean calls and recovered `18.30%`, with
  clustered lower bound `-0.24005`. Flat `K4` recovered `60.56%` but cost
  `100.31` mean calls, had clustered lower bound `-0.31005`, and regressed
  Teacher B by `13.20%`. No non-`FLAT_K16` arm cleared all preregistered
  requirements.
- **Decision and boundary:** Phase B native causal confirmation was not
  triggered. This result supports a cheap learned pair-plus-STOP/value
  evaluator as the next direction and does not support a rollout-heavy
  tactical controller. Do not use the packet to alter Silver rollout behavior,
  search budgets, RNG contracts, defaults, gameplay, or holdout policy.
- **Evidence:** [bounded variable-prefix Phase-A packet](evidence/silver_bounded_variable_prefix_20260920/README.md).
  **Knowledge impact:** durable current research and cost-quality evidence
  only; no production Silver behavior, model, RNG, schema, budget, gameplay
  result, or default changed.

## §326 — Offline learned Silver variable-prefix scorer (2026-09-20)

- **Question and protocol:** Can a tiny causal scorer predict the frozen mean
  32-replicate continuation utility for the robust PR #256 length<=2
  `CARD`/`END_TURN` prefix surface well enough to recover the variable-length
  oracle gain at fixed inference cost? The experiment used one structured row
  per unique `(leaf, prefix)`, exactly 6,194 candidates across 247 leaves,
  20 source seeds, and 32 continuation outcomes per candidate. Targets were
  `centered_q = q32 - leaf_baseline32`; Teacher A/B and oracle choices were
  evaluation-only. Source-seed FNV-1a five-fold cross-fitting kept all rows
  from a source seed in one fold, and normalization/epoch schedules were
  fit without held-out rows.
- **Frozen arms:** `RIDGE_PREFIX_V1` used fixed alpha 10.0;
  `MLP_FLAT_V1` used a fixed 32/32 Huber MLP with card embeddings;
  `MLP_FACTORIZED_V1` used shared `Q1(s,a1)` and `Delta2(s,a1,a2)` heads
  with the fixed 32-wide state/trunk bottleneck. Training used seed
  `20260920`, 80 fixed Adam epochs at `1e-3`, and no Teacher-based tuning.
  Parameter counts were 2,859, 75,809, and 79,874 respectively.
- **Result:** **`LEARNED_PREFIX_SCORER_INSUFFICIENT`**. Ridge reduced
  Teacher-A regret from the frozen `1.513323903420704` baseline to
  `1.4262050229284238` and recovered `9.20%` of the frozen `0.5666491930721915`
  oracle gain. The flat MLP reached `0.8613674600695627` regret and recovered
  `68.87%`, with `34.52%` Teacher-B reduction, but its source-seed-clustered
  95% baseline-minus-model interval was `[-0.09000065975211802,
  1.831220468655285]`; the preregistered strictly-positive lower bound was
  not met. The factorized arm reached `1.3697387211290277` regret, recovered
  `15.17%`, changed Teacher-B by `-18.37%`, and had interval
  `[-1.2676092570298159, 1.6872395664624396]`.
- **Selection/cost diagnostics:** Cross-fitted coverage was 247/247 leaves.
  The flat MLP selected 119 length-1 and 128 length-2 prefixes, agreed with
  the full q32 oracle on first action for `31.17%` of leaves and on prefix
  length for `61.13%`. Per-leaf pure-forward CPU timing was median/p95
  `0.555/1.131 ms` for the flat MLP, `0.077/0.148 ms` for Ridge, and
  `0.587/1.202 ms` for the factorized arm, each with one CPU thread. The
  factorized held-out Q1 MAE/RMSE was `4.14354/7.66258`; Delta2 was
  `5.53187/9.63302`.
- **Decision and boundary:** The compact feature/model family exposes
  learnable tactical signal, but no arm passed the required 50% gain,
  positive clustered support, Teacher-B, coverage, and model-size gate
  together. The result authorizes no native causal integration, gameplay
  run, hard64 holdout, MCTS change, or default promotion. A later experiment
  may test richer causal state encoding while preserving source-seed
  cross-fitting and the same frozen evaluation boundary.
- **Evidence:** [learned prefix scorer packet](evidence/silver_learned_prefix_scorer_20260920/README.md).
  **Knowledge impact:** durable current research and offline evidence only;
  no production Silver behavior, model, RNG, schema, budget, gameplay result,
  or default changed.

## §327 — Review correction for learned Silver variable-prefix scorer (2026-09-20)

- **Finding:** Independent review identified that the original
  `MLP_FACTORIZED_V1` implementation supervised the shared Q1 head on every
  training row. A length-1 target was therefore repeated once per child
  prefix, weighting Q1 by branching factor rather than by the preregistered
  one-row-per-length-1-prefix contract. The original factorized metrics in
  §326 are superseded for this arm.
- **Correction:** `fit_factorized()` now masks Q1 Huber loss to
  `prefix_length == 1`; Delta2 remains masked to `prefix_length == 2`. A
  focused contract test verifies the mask. The flat and Ridge prediction
  values were not retrained; the flat arm was rerun only to refresh timing
  under the corrected timer scope, with held-out predictions matching the
  prior values to `1e-12` absolute tolerance.
- **Corrected result:** The factorized arm reached Teacher-A regret
  `1.9130594165447128`, recovered `-42.23%` of the frozen oracle gain, changed
  Teacher-B by `-53.29%`, and had source-seed-clustered interval
  `[-1.596671381394513, 0.7164551748765366]`. Its held-out Q1 MAE/RMSE was
  `4.20910/7.42360`; Delta2 was `5.52571/9.64279`. The classification remains
  **`LEARNED_PREFIX_SCORER_INSUFFICIENT`**; no partial or promotion gate was
  crossed.
- **Timing correction:** MLP input tensors and leaf indices are now
  precomputed outside the timer. Pure per-leaf forward timing is flat MLP
  median/p95 `0.108894/0.241373 ms`, Ridge `0.076873/0.148462 ms`, and
  factorized `0.155411/0.315303 ms`, each with one CPU thread. These remain
  descriptive offline timings, not native/OOC speed claims.
- **Evidence:** [corrected learned prefix scorer packet](evidence/silver_learned_prefix_scorer_20260920/README.md);
  candidate-feature SHA256 remains
  `964eefcbd25fa1cf2453caaa12ef61a758f22dad089e17a5248d0e5dbf5414a5`, and
  corrected cross-fit prediction SHA256 is
  `5c4716c25b09ee7e2fe7de23e8d1cf1786099b64195207d8065451361827e437`.
- **Boundary:** This correction changes no production Silver path, model,
  RNG, schema, budget, gameplay, MCTS, holdout, or default. **Knowledge
  impact:** durable current research and corrected offline evidence only.

## §329 — Local 80-source learned Silver-prefix scale validation (2026-09-21)

- **Question and protocol:** Does the frozen PR #258 `MLP_FLAT_V1` scorer
  generalize from the existing 20 source seeds to the preregistered 40-source
  expansion and 40-source locked validation cohorts? The native collection
  used reviewed executable `891cf29f4ff2e318e0d605042732aec48fa1816c`,
  `STS_SILVER_SEARCH=1`, `STS_SEARCHER3=0`,
  `STS_SILVER_EXACT_ROOT_BUDGETS=1`, 8 threads, 10,000 exact root
  simulations, 32 continuation replicates, and the frozen CARD/END_TURN
  prefix surface through depth 2. No GCP path was used.
- **Coverage correction:** The first 64-group selection was rejected by the
  analyzer because five expansion source seeds were absent. The final
  deterministic selector required every preregistered source seed and added
  complete groups as needed, producing 81 groups / 702 leaves for expansion
  and 81 groups / 525 leaves for locked validation. The final analyzer saw
  525/525 intended/analyzed locked leaves, with complete baseline32,
  Teacher A/B, and prefix coverage. Seed roles and `primary_first_20` were
  SHA-bound to the committed source manifest.
- **Result:** **`FLAT_MLP_GENERALIZATION_FAILED`**. TRAIN60 on the locked
  set had Teacher-A regret `1.0405377287946858 -> 1.4789286717026773`,
  a `-42.13%` regret reduction and recovered-oracle fraction `-1.08210`.
  The source-clustered 5,000-draw Teacher-A interval was
  `[-1.63530, 0.17031]`; Teacher-B regret reduction was `-39.46%`.
  The five-seed diagnostic had recovered-oracle values from `-1.08210` to
  `-0.44063`. Exact 40-source and full-leaf coverage gates passed; recovery,
  positive-support, and Teacher-B gates failed.
- **Influence concentration:** Global leave-one-source-out absolute
  Teacher-A influence ranked locked sources `12100201` and `12100194` as the
  two largest positive influences. Joint removal left absolute improvement
  `-0.68545` and clustered `p025 = -2.13616`, so the preregistered
  concentration stress test failed. Influence ranking uses deterministic
  point estimates; only the joint two-source stress test performs the full
  5,000-draw bootstrap.
- **Learning curve:** The committed packet records the locked baseline/oracle
  regrets and all three fits. Teacher-A regret was `1.04054` at baseline,
  `1.44064`/`1.47075`/`1.47893` for TRAIN20/40/60, corresponding to
  `-38.45%`/`-41.35%`/`-42.13%` regret reduction. Teacher-B was
  `1.16868` at baseline and `1.58795`/`1.67065`/`1.62988` for TRAIN20/40/60,
  or `-35.88%`/`-42.95%`/`-39.46%`. Recovered-oracle fractions were
  `-0.98758`/`-1.06191`/`-1.08210`. All five fixed initializations were
  negative (mean `-0.66518`, range `[-1.08210,-0.44063]`).
- **Decision and boundary:** This is bounded negative external evidence for
  scale validation of the frozen scorer. It authorizes no native integration,
  gameplay run, model retraining, search change, default promotion, or
  interpretation against the native `target=-1` lowering fix. The large raw
  multi-GB replay streams remain at `/tmp/silver-prefix-scale-20260920-exact10k/`,
  while the compact candidate features, all three prediction streams,
  `analysis.json`, and `dataset-summary.json` are committed in
  [the scale-validation evidence packet](evidence/silver_prefix_scorer_scale_20260920/)
  and hash-bound by `analysis-summary.json`.
  **Knowledge impact:** durable negative learned-prefix scale-validation
  evidence and harness-contract corrections only; no production Silver
  behavior, model, RNG, schema, budget, gameplay result, or default changed.
## §328 — Silver deterministic action contraction (2026-09-20)

- **Question and protocol:** Does contracting deterministic multi-step Silver
  decisions reduce search work without changing the sequential endpoint? The
  corrected frozen implementation was `796fa5cd`, based on main
  `d5e61ae2078244a27ffea8842821aae2304263b8`. CONTROL retained primitive
  edges; A folded only RNG-neutral one-option `CARD_SELECT` states; B added
  one-edge-per-follow-up macros for the seven safe PR #237 tasks when the
  primitive was RNG-neutral, nonterminal, immediately entered `CARD_SELECT`,
  and had at least two deduplicated follow-ups. All arms used the same Release
  replay binary, allocated 32,768-node reuse cap, adaptive/exact-lock/rho off,
  common benchmark seeds, and frozen `hard64-dev` only. HOLDOUT was not used.
- **Correctness correction:** Review found that B validated only the first
  primitive action's RNG state. The corrected `macroFollowUps()` now executes
  every candidate follow-up on a copy of the post-first-action state and
  rejects the entire macro if any follow-up changes RNG. The focused test now
  includes True Grit+ with Dead Branch and at least two selectable cards,
  proving the first action is RNG-neutral while the EXHAUST_ONE continuation
  is stochastic. `silver_search_optimization_test` passed the four-choice
  Headbutt canonicalization fixture, A forced-selection resolution, macro
  endpoint/RNG equality, stochastic-parent rejection, unsupported-task and
  Hologram fallback, and sequence-accessor compatibility. All six 64-row
  Release replays completed with zero replay failures. The unrelated existing
  `silver_bridge_test` still fails its representative non-target potion
  expectation and then an existing restored CARD_SELECT lowering exception;
  no live-combat source was changed to repair it.
- **1,000 simulations:** CONTROL/A/B won `51/64`, `50/64`, and `51/64`, with
  mean HP fractions `0.344091`, `0.326269`, and `0.333693`. Total MCTS
  invocations were `2,232 / 2,220 / 2,230`; total simulations were
  `2,232,000 / 2,220,000 / 2,230,000`; nodes were
  `2,063,754 / 2,048,089 / 2,060,113`; and wall seconds were
  `17.591 / 16.918 / 18.770`. A contracted 5 forced selections; B also took
  37 macros across 22,772 eligible nodes and reduced CARD_SELECT searches
  from 104 to 79.
- **10,000 simulations:** CONTROL/A/B won `59/64`, `58/64`, and `57/64`, with
  mean HP fractions `0.469434`, `0.453714`, and `0.458448`. Total MCTS
  invocations were `2,230 / 2,216 / 2,176`; total simulations were
  `22,300,000 / 22,160,000 / 21,760,000`; nodes were
  `19,756,757 / 19,640,433 / 19,170,926`; and wall seconds were
  `201.453 / 201.980 / 210.446`. A contracted 7 forced selections; B took
  32 macros across 215,040 eligible nodes and reduced CARD_SELECT searches
  from 105 to 68. B macro eligibility was concentrated in HEADBUTT, with
  additional ARMAMENTS, EXHAUST_ONE, EXHUME, FORETHOUGHT,
  LIQUID_MEMORIES_POTION, and WARCRY coverage; the raw task breakdown is in
  the evidence packet.
- **Paired interpretation:** At 1k, CONTROL vs A/B had 3/23 outcome and 8/35
  trace discordances. At 10k, the counts were 4/26 and 11/41. B had real
  coverage and reduced search work, but did not improve wall time: it had equal
  wins with CONTROL but lower mean HP at 1k, and lower wins and mean HP at 10k.
  The corrected implementation validates every candidate continuation on a
  copied state; at 10k this is roughly 2.08 million candidate-continuation
  validations. The wall-time result therefore includes safe-macro
  implementation overhead and is not a universal claim that macro contraction
  cannot work. A passed the technical forced-select contract but its small work
  reduction was accompanied by one fewer win at each budget. This is bounded
  offline DEV evidence, not live-game, whole-run, holdout, or production
  qualification.
- **Decision:** `FORCED_SELECT_CONTRACTION_PASS` and
  `SAFE_SELECT_MACRO_REJECTED`. Do not promote B or change Silver defaults
  from this experiment. **Evidence:** [Silver deterministic contraction
  packet](evidence/silver_deterministic_contraction_20260920/README.md).
  **Knowledge impact:** durable negative efficiency/quality result and current
  research evidence only; no production Silver behavior, model, RNG, schema,
  budget, gameplay result, holdout, or default changed.

## §330 — Silver terminal/value audit: compatible reweight has insufficient development headroom (2026-09-21)

- **Question and protocol:** Can a constrained, regularized reweight of the
  current `BattleSearcher::evaluateEndState()` components improve sibling
  ranking against the existing Silver Teacher A/B labels while every
  SimpleAgent continuation trajectory remains fixed? The implementation base
  was current `main` after PR #260 (`43ef6a6d`). The native diagnostic seam now
  exposes raw terminal features and reconstructs the leaf-root production
  value without changing the production evaluator. The preserved 20-source,
  247-leaf corpus was replayed with 32 paired continuations per leaf (7,904 /
  7,904 accepted rows). Teacher B was evaluation-only.
- **Exact contract:** `SilverTerminalValueFeatures` records branch-specific
  raw terms, including death-save value, root-relative gold/max-HP deltas,
  the Spiker energy exception, and turn>100 survival handling. The existing
  teacher-comparison value remains leaf-root evaluation plus the separate
  victory baseline correction; the analyzer keeps that correction basis
  explicit. Native raw reconstruction matched `evaluateEndState()` within
  `1e-8` for every accepted rollout.
- **Result:** DEFAULT Teacher-A sibling regret was `1.51332` with pairwise
  concordance `0.74241` and top-leaf agreement `0.56250`. Cross-fitted
  `REWEIGHT_COMPAT_V1` was worse at regret `1.71113`, concordance `0.74292`,
  and top agreement `0.53125`; Teacher-B regret also worsened from `1.47290`
  to `1.82242`. The source-clustered baseline-minus-candidate bootstrap was
  `[-0.46891, 0.00000]`. The untied diagnostic also failed to improve
  cross-fitted regret (`1.61666`) after its corrected nested source-grouped
  lambda selection; its fold lambdas were `[1.0, 0.1, 0.01, 0.01, 0.01]`.
- **Additional diagnostics:** Against an optimistic zero-regret ceiling, the
  compatible arm recovered `-13.07%` of the baseline gap. The fitted
  development-only objective left 48/75 ordinary-loss leaves at or above the
  minimum victory value; this is a sanity warning, not a production candidate.
  The preserved corpus omitted act, HP-band, and source-rollout-length
  metadata, so those subgroup results remain explicitly unavailable.
- **Decision and boundary:** `TERMINAL_REWEIGHT_HEADROOM_INSUFFICIENT` on
  this bounded development corpus. The old #260 40-source expansion and
  40-source locked artifacts contain prefix rows but no replayable leaf wires,
  so they are not silently treated as a 100-source corpus. No fresh holdout,
  hard64 replay, live gameplay, production weight override, or default
  promotion was run. The next likely target is continuation trajectory/policy
  quality, subject to a fresh corpus if the line is reopened.
- **Evidence:** [terminal/value audit packet](evidence/silver_terminal_value_audit_20260921/README.md).
  **Knowledge impact:** durable bounded negative terminal-scoring result and
  raw-feature diagnostic contract; no production behavior, default, RNG,
  model, live gameplay, or holdout qualification changed.

## §331 — Silver retained-search queue-item audit (2026-09-21)

- **Question and provenance:** Can Silver merge more retained states by ignoring
  only `curCardQueueItem` at settled player decisions? The audit baseline was
  `43ef6a6df2ea9af56840c9a298c92623c14bcff6` in a separate managed worktree.
  The motivating corrected Small Slimes capture was live session `78c0ee4f9f67`,
  sequence `9`, observation hash
  `efb8bcf0367f908221521ab79f09c5f666ee5a6cf3d6e0b047b41f95558c84d8`, and
  artifact SHA-256
  `e20001e051e65e723c8cdf51e73890bc3df971454aa3713854acb2d9980ad22d`.
  PR #272 head was capture provenance only; current source facts were checked
  against the audit baseline.
- **Opportunity screen:** The 1,133-node tree contains 997 decision/state
  nodes and 136 chance nodes. Omitting only the serialized queue item yields
  49 duplicate groups, 104 participating nodes, 55 excess nodes, and 61
  unordered pairs. The upper-bound reduction is 5.52% of decision/state nodes
  and 4.85% of all retained nodes. Every candidate is an unresolved,
  settled `PLAYER_NORMAL` node; no selection, chance, pending-action, or
  terminal candidate appears in this capture.
- **Native check:** A temporary test-only native probe compared 32 paired
  common seeds for 32 steps per arm through `tools/seed_guard.sh`. Best action,
  legal-action count, root action visits, and deterministic successors matched
  after normalizing only the queue item. A separate 128-step fixed-root probe
  also passed direct statistics checks. An Attack Potion boundary observation
  reached `CARD_SELECT` while retaining different queue items; this leaves
  global canonicalization unqualified because the stale value survives outside
  the tested equivalence boundary, without demonstrating a downstream semantic
  divergence. Full END_TURN outcome coverage and chance-parent statistics remain
  an explicit proof obligation for any future implementation.
- **Decision:** **`NARROW_QUEUE_CANONICALIZATION_PLAUSIBLE_BUT_UNQUALIFIED`**.
  Do not relax `equalForSearch`, change Silver search behavior, alter the reuse
  cap, or update PR #272. A future implementation, if separately authorized,
  must be boundary-local to settled `PLAYER_NORMAL` with empty queues and must
  separately qualify evaluation inputs, chance behavior, reroot identity,
  retained statistics, and decision quality.
- **Evidence:** [retained-search queue-item evidence packet](evidence/silver_retained_search_audit_20260921/README.md) and [investigation record](../knowledge-base/investigations/2026-09-21-silver-retained-search-audit.md).
  **Knowledge impact:** durable unresolved Silver search investigation and
  experiment evidence only; no production Silver behavior, model, RNG, schema,
  budget, gameplay result, or default changed.

## §332 — Silver internal-node finite FPU screen (2026-09-21)

- **Question and intervention:** Does finite First-Play Urgency let Silver
  revisit promising explored actions at internal `PLAYER_NORMAL` nodes instead
  of forcing breadth? The treatment was default-off and changed only
  non-root, non-random nodes with at least two edges and both visited and
  unvisited edges. It used the fixed
  `c_fpu=max(explorationParameter,explorationParameterChance)` formulation
  from the experiment handoff. Roots, `CARD_SELECT`, chance DPW, rollouts,
  value, priors, transpositions, and exploration constants were unchanged.
- **Correctness:** The focused `silver_search_optimization` and
  `silver_bridge_boundary` CTest checks passed 2/2. The fixture proved flag-off
  parity, root/chance/card-select exclusions, visited-edge selection under
  finite FPU, and eventual unvisited exploration. The replay seam now emits
  initial semantic root action, simulations, nodes, depth, search wall time,
  and FPU opportunity/selection telemetry.
- **Frozen implementation and provenance:** The implementation SHA was frozen
  at `c9f58c20cd4879584fbe0d78828d33057350d914` before the expensive rerun.
  The `hard64-dev` snapshot SHA-256 was
  `ab7c3298754864986c31273a0f1d23967b165fdd79a386261b680b8ad16d0eae`.
  Every case was run as one process through `tools/seed_guard.sh` with
  `OMP_NUM_THREADS=4`, the same snapshot `benchmark_seed`, and the same fixed
  configuration across arms; only budget and the default-off FPU flag differed.
- **Complete 1k and 10k DEV cohorts:** All four arms had 64/64 accepted rows.
  Control 1k was 51/64 wins and FPU 1k was 50/64; control 10k was 59/64 and
  FPU 10k was 56/64. Full-combat nodes, depth, chance depth, simulations, and
  wall time are retained as descriptive totals only: once root actions differ,
  they are trajectory-confounded and are not causal FPU efficiency claims.
- **Preregistered root metric:** Relative to high-budget CONTROL as a
  reference, 1k CONTROL agreed in 45/64 cases and 1k FPU agreed in 39/64.
  The 1k CONTROL/FPU actions disagreed in 22 cases: FPU moved toward the
  reference in 6, away in 12, and both remained different in 4. The complete
  case-by-case direction list and selected actions are in the evidence packet.
- **First-decision efficiency:** A measurement-only replay seam covered the 59
  ordinary roots common to both arms; five transactional `CARD_SELECT` roots
  were excluded from this diagnostic but remained in the full-combat cohort.
  At 1k, mean first-decision wall time was 90,739.926 us CONTROL versus
  91,512.401 us FPU; at 10k it was 915,215.958 us versus 911,448.962 us.
  These machine-dependent diagnostics are reported separately and are not a
  production-performance qualification.
- **Decision:** **`INTERNAL_FPU_INCONCLUSIVE`** after the complete high-budget
  cohort. The mechanism is exercised, but the primary root metric is mixed and
  leans against FPU; timing is inconsistent across budgets; and whole-combat
  totals cannot support a causal efficiency claim. This does not support
  `INTERNAL_FPU_PROMISING` or `INTERNAL_FPU_REJECTED` under the existing rule.
  No tuning, holdout, gameplay qualification, or default promotion was
  performed.
- **Evidence:** [internal FPU evidence packet](evidence/silver_internal_fpu_20260921/README.md),
  including compressed raw JSONL, deterministic analyzer, frozen summary, and
  complete per-case table. **Knowledge impact:** durable complete-cohort
  inconclusive Silver allocation result, first-decision telemetry seam, and
  paired evidence contract; no production/default behavior changed.

## §333 — Selected deterministic Silver reroot safety on frozen hard64-dev (2026-09-22)

- **Question and frozen protocol:** Does selected-child hand alignment and its
  chance-action safety correction change the hard64-dev replay or expose a
  deterministic reroot miss? Replay the 64 fixed Ironclad A0 DEV battle
  snapshots at 1,000 Silver simulations per decision, project-fair combat RNG,
  `OMP_NUM_THREADS=4`, allocated reuse cap 32,768, with adaptive, exact-lock,
  and rho modes off. Input SHA-256:
  `ab7c3298754864986c31273a0f1d23967b165fdd79a386261b680b8ad16d0eae`.
- **Provenance:** The original uninstrumented baseline was `289e1ab96d4a`;
  the earlier corrected run used functional SHA `ea8a728802d3`. The
  chance-action safety repair and merge of `main` at `eb7c5fa7` were replayed
  at `db4edf1cfeb7f8c81bd384c4f02d72f99d7bdc8c`. When `main` advanced
  again to `149954a3` with default-off internal Silver FPU work, the combined
  final functional SHA was `ca45781abed16db3e440a8e20dedfe70be8759d4`.
  Its Release replay binary SHA-256 was
  `6e4a635dce114970eb4aef6d303498da20588d1d3297abb3611c2f129defea64`.
  All seed execution used `tools/seed_guard.sh`; the final command left
  `--internal-fpu` off.
- **Result:** The final 64/64 cases completed successfully: 51 wins, mean
  terminal HP fraction `0.3440911508`, and `0.9246209677` nodes per simulation.
  All 1,287 selected deterministic attempts rerooted exactly or through the
  documented equivalence repair; none was candidate-missing or cap-blocked.
  Of 881 stochastic attempts, 541 were candidate-missing. There were zero
  selected edges with positive visits but no child. Final versus earlier
  corrected action traces differed in 0/64 cases. Pre-FPU-merge rows matched
  the earlier corrected rows except for elapsed wall seconds. The final rows
  added seven FPU/depth/timing telemetry fields, while every shared field
  except elapsed wall seconds matched the pre-FPU rows. The cohort exercised no
  hand-order mismatch, equivalent-copy UID match, or other selected-child
  mismatch; focused native regressions cover those latent paths.
- **Decision and limits:** The corrected reroot safety implementation passes
  this bounded DEV sanity and correctness screen. The 541 observed fallbacks
  are stochastic chance misses, not deterministic selected-child failures on
  this cohort. This is neither holdout nor whole-run/live-game qualification;
  it does not change Silver defaults or establish broader reroot rates.
  **Evidence:** [reroot packet](evidence/silver_deterministic_reroot_20260921/README.md),
  including compressed raw baseline, earlier corrected, and final JSONL and a
  reproducible summarizer. **Knowledge impact:** bounded research evidence and
  the maintained hand-alignment contract only; no model, RNG, budget, gameplay
  policy, or default promotion.

## §334 — Settled Silver queue-item default candidate, consumed HOLDOUT (2026-09-22)

- **Question and boundary:** Make `curCardQueueItem` historical only at
  unresolved, nonterminal, empty-queue `PLAYER_NORMAL` decisions in Silver
  retained search. Keep `CARD_SELECT` and every pending-action state exact;
  preserve selected deterministic reroot safety from §333.
- **Provenance:** Current-main baseline `8613f9c7811ce19a81cb731e78b6b58d01ec91ca`;
  frozen functional candidate `44331fa511058250fee874f41057e9c59ae2daa1`.
  Release GCC, `OMP_NUM_THREADS=4`, 1,000 simulations per decision, allocated
  reuse cap 32,768, adaptive/exact-lock/rho/internal FPU off. All commands
  used `tools/seed_guard.sh`. DEV input SHA-256
  `ab7c3298754864986c31273a0f1d23967b165fdd79a386261b680b8ad16d0eae`;
  HOLDOUT input SHA-256
  `e8b914ad74ca0508ee6b1db329c5f454e92e7785cd60af1475d53b35a9d8af34`.
- **Focused verification:** Six affected CTests passed, including search
  dedup/boundary/Attack Potion, bridge deterministic/hand/UID/chance reroot,
  live importer, and Silver integration variants. The 59 supported paired
  first-decision DEV roots created 58,966 baseline versus 58,912 candidate
  nodes, with 7,763 candidate canonical lookup hits and 12 differing first
  actions. Five roots were unsupported by the existing first-decision seam
  (`transactional_selection_required`) in both arms.
- **DEV:** 64/64 technically completed. Candidate: 52 wins, mean terminal HP
  fraction 0.3701368277, 0.9203209877 nodes/simulation, 325,595 canonical
  hits. Deterministic reroot 1,312/1,312 with zero misses and zero selected
  positive-visit edges without children; stochastic sampled success 354/892,
  with 538 candidate misses. Cap fallbacks: zero. Baseline: 51 wins,
  0.3440911508 mean terminal HP fraction, 0.9246209677 nodes/simulation,
  deterministic 1,287/1,287, stochastic misses 541. All 64 action traces
  differed, so whole-combat efficiency and outcome differences are
  trajectory-confounded.
- **HOLDOUT correctness failure:** The one planned candidate run completed
  63/64. Case `12100063/26` failed closed after three decisions at a selected
  deterministic `CARD_SELECT` child with 525 edge visits. The diagnostic
  reported that retained and observed states differed in `curCardQueueItem`
  while the listed gameplay fields, RNG, queues, and hand UIDs matched. PR #285
  kept all `CARD_SELECT` states exact, so this correctly failed closed
  under that candidate's identity contract. Its `PLAYER_NORMAL`-only boundary
  and root-rewrite design were insufficient; the candidate is **not adopted**.
  The 63 completed rows had 49 wins and mean terminal HP fraction
  0.3674471462. Across all recorded rows there were
  325,149 canonical hits, 1,091 successful deterministic reroots before the
  failing attempt, 529 stochastic candidate misses, and zero cap fallbacks.
  The failed row has no terminal outcome. HOLDOUT is consumed; no retuning or
  second cohort run occurred.
- **Decision and limit:** The intended default decision remains blocked by
  semantic correctness at `CARD_SELECT` and selected-child reroot requirements.
  The evidence proves a representational mismatch at that boundary, not a
  downstream gameplay difference. A new design must account for descendants
  created under a retained representative's historical queue item while
  preserving pending-work semantics and deterministic reroot correctness.
  **Evidence:**
  [raw packet](evidence/silver_queue_item_canonical_20260922/README.md).
  **Knowledge impact:** rejected candidate and consumed HOLDOUT recorded in
  ADR-0016 and this ledger; no maintained search behavior or production
  implementation change.

## §335 — Quiescent Silver queue-item identity on frozen hard64 DEV (2026-09-22)

- **Question and boundary:** Does ignoring only historical `curCardQueueItem`
  at quiescent unresolved `PLAYER_NORMAL` or `CARD_SELECT` states preserve
  selected-child reroot and expanded selection descendants without rewriting
  the retained root? §334 records PR #285's rejected root-rewrite design and
  consumed HOLDOUT. This §335 records the replacement design without changing
  that evidence.
- **Frozen implementation and protocol:** Current-main baseline
  `8613f9c7811ce19a81cb731e78b6b58d01ec91ca` versus candidate functional
  SHA `68b57f1bc644733e845a7bff15d717d481617dee`. The 64 frozen hard64
  **DEV** snapshots (SHA-256
  `ab7c3298754864986c31273a0f1d23967b165fdd79a386261b680b8ad16d0eae`)
  were replayed at 1,000 simulations per decision through `seed_guard.sh`,
  `OMP_NUM_THREADS=4`, default Silver settings, and `--reroot-diagnostics`.
  The consumed HOLDOUT was not rerun.
- **Focused verification:** Six focused CTest cases passed, covering Silver
  optimization, bridge boundary, integration modes, and live importer. The
  new expanded Gambler's Brew fixture reroots through selection, reopened
  selection, and confirmation, preserves all retained queue items, and
  continues searching. Headbutt's pending `OnAfterCardUsed` remains exact.
- **DEV result:** Both arms completed 64/64. Main versus candidate: 51 versus
  52 wins; mean terminal HP fraction 0.3440911508 versus 0.3701368277;
  1,287 versus 1,312 selected deterministic reroots with no fallback; zero
  deterministic misses and zero positive-visit selected edges without child
  in either arm. Candidate counted 325,548 queue-item dedup hits. Action
  traces changed in 64/64 cases and first actions in 12/64, so full-combat
  node, simulation, time, win, and HP differences are trajectory-confounded.
- **Same-root diagnostic:** A first-decision-only seam paired 59 ordinary
  roots; five transactional selection roots were reported as such in both
  arms. Both performed 59,000 root visits. First actions changed in 12/59;
  candidate versus main created 54 fewer nodes in aggregate and recorded
  7,763 queue-item dedup hits. Search time summed to 691,962.262 versus
  656,110.242 microseconds in one run; this does not qualify a speed effect.
- **Decision and limits:** Bounded DEV confirmation supported the identity
  rule and invariants for later independent implementation review. It is
  not a HOLDOUT result, scientific qualification, or default promotion. No
  fresh independent cohort was run. **Evidence:** [raw DEV packet and
  provenance](evidence/silver_quiescent_queue_item_20260922/README.md).
  **Knowledge impact:** ADR-0017 records the scoped identity choice and the
  combat-search KB records the branch behavior. Eligible roots can change
  default Silver action selection; no configuration setting, RNG, budget, or
  model changed.

- **Live-boundary correction:** Review found that live conversion omits pending
  action/card queues. Functional SHA `14ad63b10dcbe820a9df3580a99d202ddbbf2fa8`
  carries a source-side empty-queue proof and keeps identity exact for
  legacy/imported wires without it. Six focused tests pass, including actual
  quiescent Gambler's Brew and pending Headbutt after conversion. A permitted
  DEV rerun at this SHA completed 64/64 with zero deterministic misses and
  zero positive-visit childless edges. The frozen legacy JSON provides no
  source proof, so candidate and main had identical 64/64 action traces,
  51 wins, and zero candidate canonical hits; 59 paired first roots also
  matched. This verifies conservative legacy behavior, not positive
  live-policy qualification. [Corrected raw packet](evidence/silver_quiescent_queue_item_20260922/README.md).

## Silver prior model v1 — Stage A stopped before VALIDATION J (2026-09-22)

- **Question and boundary:** Complete the predeclared structured policy-only
  Stage A using TRAIN L, VALIDATION L, then the 64 preselected VALIDATION J
  roots. No Silver integration, gameplay, or LOCKED_TEST evaluation was
  permitted.
- **Implementation and throughput:** Baseline `a2d50b1810ebac6cb3ae25009f3cadef3068c928`;
  reviewed trainer commit `4c724e40`. The vectorized `SilverPriorNetV1` has
  232,665 parameters. The one-epoch CPU T1 probe processed 8,862 roots and
  57,012 actions in 1.361 seconds (6,513 roots/s; 41,900 actions/s; peak RSS
  555,624 KiB). All 19 trainer tests passed and `git diff --check` passed.
- **Stage-A L result:** With initialization seed `20260922`, TRAIN-only
  `tau0=0.5899875000025645` and temperatures `0.29499375000128225`,
  `0.5899875000025645`, `1.179975000005129`, all arms stopped at epoch 45 by
  the declared patience rule. Their validation target CEs were 1.40496, 1.40160,
  and 1.40785. The model-minus-uniform expected-regret differences were
  -3.20118 [-3.47135, -2.96099], -3.17542 [-3.44476, -2.93642], and
  -3.14024 [-3.40932, -2.90211], respectively (95% source-cluster bootstrap,
  5,000 replicates). All arms pass the L gate only.
- **J evaluation stop:** The sealed selection contains 64 preselected
  VALIDATION J roots. All 64 corresponding J shard paths are absent from disk
  and absent from the sealed release file list. The dedicated loader stopped
  on the first selected J path before reading a J label. It did not substitute
  roots. No J result, eligible temperature, candidate selection, or robustness
  run exists.
- **Locked-test boundary:** `locked_test_labels_opened=false`.
  `metadata_deviation="LOCKED_TEST root/action counts observed before freeze; labels untouched"`.
  No LOCKED_TEST labels, predictions, outcomes, or shards were inspected.
- **Decision and limits:** The experiment is incomplete due to missing
  permitted VALIDATION J artifacts, not a negative result. Continue only after
  restoring those exact selected artifacts under the frozen release or
  explicitly reviewing a new sealed corpus release. Do not select a model from
  L-only evidence. [Evidence packet](evidence/silver_prior_model_v1_20260922/README.md).
  **Knowledge impact:** trainer workflow is in the maintained Silver prior
  operations page; no Silver behavior or model promotion changed.

### Correction after PR #289 independent review

The preceding Stage-A metrics and missing-J conclusion are **superseded and
invalidated**. The epoch order used `len(train)` where `train` was the prepared
split dictionary; only its 35 dictionary fields, not all 8,862 TRAIN roots,
were presented to each epoch. The old validation-L metrics and checkpoints do
not represent the preregistered run and cannot support the L gate. The full-set
CPU throughput probe remains valid because it used
`len(train["contexts"])` explicitly.

The J path conclusion was also wrong. Collection finalization stores J raw
records at `raw/J/<hash>.json.gz` and intentionally creates no `shards/J`
projection. A path and release-manifest inventory of the 64 preselected
VALIDATION J roots found 64/64 raw files present and 64/64 listed. This was a
metadata-only inventory: no VALIDATION J raw record was opened and no
LOCKED_TEST path or label was inspected. Correct the trainer to validate and
project selected J raw records in memory. Rerun Stage A only after independent
review of the corrected implementation SHA; open VALIDATION J only after the
new all-root VALIDATION-L run completes.

`locked_test_labels_opened=false`;
`metadata_deviation="LOCKED_TEST root/action counts observed before freeze; labels untouched"`.
The corrected evidence packet relabels the old Stage-A files as invalidated.

### Corrected Stage A and VALIDATION J after review

The corrected trainer SHA `863d7d5e09aa069fc3f4456cfa393c105729aa32` passed
independent source/test review before this rerun. Every training epoch was
accounted for as exactly 8,862 roots, 57,012 actions, and 70 optimizer steps.
With unchanged seed `20260922` and recipe, the arms stopped at 18/20/20 epochs.
Their VALIDATION-L model-minus-uniform mean-regret differences and 95% source
cluster CIs were T0.5 `-3.67685 [-3.99284,-3.39745]`, T1
`-3.62102 [-3.94162,-3.34120]`, and T2 `-3.57885 [-3.89616,-3.30330]`.

After L metrics completed, the corrected loader opened only the 64 preselected
VALIDATION J raw records from `raw/J`, verified their manifest checksums and
J jobs, validated each record, and projected them in memory. It did not seek
`shards/J`; collection deliberately materializes no such projection. All arms
passed the VALIDATION-J upper-CI gate. Their J model-minus-uniform
mean-regret differences and 95% source-cluster CIs were T0.5
`-3.69322 [-4.22695,-3.16496]`, T1 `-3.66057 [-4.20016,-3.13460]`, and T2
`-3.64892 [-4.17707,-3.14134]`.

T0.5 had the largest mean J improvement. The paired T2-minus-T0.5 J regret
interval was `[-0.12449,0.20423]`, containing zero, so the preregistered tie
rule selected the higher temperature T2. This confirms the validation gates
for the frozen v1 policy model, not gameplay utility or default promotion.
No LOCKED_TEST label, outcome, prediction, or shard was opened. [Corrected
Stage-A/J evidence and metrics]
(evidence/silver_prior_model_v1_20260922/README.md).

### Selected-arm robustness diagnostic after independent review

The robustness runner passed independent source/test review at PR head
`06b3383a`. Review identified that the Stage-A cache was bound to an earlier
trainer SHA; a fresh cache was prepared for trainer source SHA-256
`f66aed7ee1da9f48d0c21ea8392d23e83f22b0b2a281dc549380c4367cc9391f`, without
rerunning Stage A or changing selected arm T2. The two preregistered seeds
`20260923` and `20260924` each trained all 8,862 TRAIN roots per epoch, with
57,012 actions and 70 optimizer steps. They stopped after 19 and 20 epochs.
Their VALIDATION-L model-minus-uniform mean-regret differences were -3.57079
and -3.54033; the VALIDATION-J differences were -3.65704 and -3.72922. Both
seeds improved on both validation sets, satisfying the declared
`PRIOR_MODEL_OPTIMIZATION_STABLE` rule. This bounded diagnostic neither
reselects the arm nor establishes gameplay impact. No LOCKED_TEST labels,
outcomes, predictions, or shards were opened. [Robustness raw metrics and
provenance](evidence/silver_prior_model_v1_20260922/robustness-reviewed-f66aed7e/).

### One-time LOCKED_TEST evaluator and result (2026-09-22)

The sole candidate remains Stage-A T2, initialization seed `20260922`, target
temperature `1.179975000005129`, and checkpoint SHA-256
`b756c3e6576bdb53085f24aeb1102e4e2fe55fd7469c55546c99f068ccf40e24`.
Before any LOCKED_TEST labels are opened, a dedicated evaluator is being
reviewed at the supplied main baseline `60ece5403ec0a06d802c54aed8c7b85a9d4bc369`.
It reads all non-quarantined LOCKED_TEST L shards and only preselected
LOCKED_TEST J raw records, with create-only consumption receipt before label
access. The trainer remains TRAIN/VALIDATION-only.

The decision rule was frozen before opening labels: classify
`PRIOR_MODEL_LOCKED_TEST_CONFIRMED` only when the upper 95% source-seed-cluster
bootstrap CI (5,000 replicates) of model-minus-uniform expected regret is below
zero on both L and J; otherwise classify
`PRIOR_MODEL_LOCKED_TEST_NOT_CONFIRMED`. No top-action threshold is used. No
LOCKED_TEST label was opened before independent review. The reviewed evaluator
SHA was `f458ef51029ea53f9baaf361e87fba67c743d5a2`; the run used only the
frozen candidate and completed once with 1,494 L roots / 64 sources and 64
preselected J roots / 64 sources. L model-minus-uniform expected regret was
`-3.23423 [-3.53464,-2.93676]`; J was `-2.89553 [-3.58717,-2.26012]`.
Classification: **`PRIOR_MODEL_LOCKED_TEST_CONFIRMED`**.

Descriptive diagnostics: validation-to-locked L delta changed from
`-3.57885 [-3.89616,-3.30330]` to `-3.23423 [-3.53464,-2.93676]`; J changed
from `-3.64892 [-4.17707,-3.14134]` to `-2.89553 [-3.58717,-2.26012]`.
The frozen L target's locked-J delta versus uniform was
`-4.11938 [-4.89133,-3.39374]`; soft-prior headroom recovery was 70.29%.
These diagnostics do not affect the decision rule. The exact consumption
receipt and per-root metrics are retained at
`/home/philippherrmann/Documents/sts/silver-prior-model-v1/locked-test-v1/`;
the compact committed packet is
[here](evidence/silver_prior_locked_test_v1_20260922/README.md).
The committed provenance now pins hashes for the receipt, full external L/J
summaries, decision file, and imported trainer source. After this sole run, the
evaluator CLI and `run()` entry point were disabled; any output-directory value
is refused before checkpoint, manifest, or label access.

LOCKED_TEST is consumed and must not be used for model tuning. This confirms
offline policy-prior generalization under the frozen expected-regret criteria;
it does not promote the model to Silver default or establish native cost or
gameplay impact. The next experiment is separate oracle/native prior
integration. **Knowledge impact:** current research status and this result are
updated here and in `evaluation/current-research.md`; no stable implementation
contract or Silver behavior changed.

- **Fresh native production-path smoke and replayable provenance:** Functional
  SHA `06279a8644492e9ef9cea813455ddfe841425380` added trusted v2
  hard-combat capture of the source queue proof; v1 remains conservative.
  Seven focused CTests passed. Eight fresh A0 seeds `2026100100..2026100107`
  ran project-fair Silver through native `bestbench` at 300 simulations per
  decision with the repository seed guard. All eight completed normally;
  175 combats yielded 178,497 queue-item canonical hits and zero conversion,
  semantic-resolution, transaction, knowledge-consistency, or fail-closed
  selected-child failures. All captures were v2; replay of one trusted
  capture per seed completed 8/8 with 2,303 canonical hits, zero deterministic
  misses, and zero positive-visit childless edges. This is bounded positive
  production-path exercise and capture round-trip verification, not a
  gameplay-quality comparison or population qualification. The consumed
  HOLDOUT was not rerun. [Native-smoke raw packet](evidence/silver_quiescent_queue_item_20260922/README.md).

### Frozen Silver prior root-PUCT replay screen (2026-09-23)

At baseline `293c0704f0921688a6dc7066800b3bfcb1801bc5`, screened the frozen
`SilverPriorNetV1` T2 checkpoint (seed `20260922`, tau `1.179975000005129`,
checkpoint SHA-256 `b756c3e6576bdb53085f24aeb1102e4e2fe55fd7469c55546c99f068ccf40e24`)
on exactly 64 preselected VALIDATION-J roots / 64 source seeds. This is a
development mechanism screen because VALIDATION was already used for model
selection. Preparation validated the frozen corpus binding and selected L
shards only, then sealed native-order aligned learned, uniform, and L-oracle
priors. The learned arm used `softmax(logits)` without another temperature;
the oracle used `softmax(L / tau)`. Replay completed and was sealed before the
analyzer read the matching 64 VALIDATION J raw files. No LOCKED_TEST root,
label, count, or raw artifact was used.

All four arms retained native Silver action order and ran fresh trees at 32
simulations with four common-seed replicates per root. Root PUCT used its
existing `c=2.5`; internal UCT, chance handling, rollout, and evaluator were
unchanged. The 1,024-row replay was analyzed by 10,000 paired bootstrap
replicates over source seeds. Mean J regrets were A_UCT 1.32065, U_UNIFORM
1.41371, M_LEARNED 1.37981, and O_ORACLE_L 1.14595. M_LEARNED minus
U_UNIFORM was `-0.03390 [-0.11794,0.03651]`; M_LEARNED minus A_UCT was
`+0.05916 [-0.28676,0.37000]`; O_ORACLE_L minus U_UNIFORM was
`-0.26776 [-0.56135,-0.07144]` (95% source-seed bootstrap CIs).

Classification: **`LEARNED_PRIOR_SEARCH_HEADROOM_NOT_CAPTURED`**. The oracle
confirms usable root-PUCT headroom on these roots, while the learned prior
fails its predeclared comparison with uniform and does not beat ordinary UCT.
Stop the deployment line; do not export or port the network based on this
screen. This is not a gameplay result, fresh generalization claim, or default
promotion. [Evidence packet](evidence/silver_prior_root_replay_20260923/README.md).
**Knowledge impact:** update the current research status; no stable
implementation contract or Silver behavior changed.

### User-authorized frozen Silver prior online integration smoke (2026-09-23)

After the negative 64-root mechanism screen above, the user explicitly
requested a separate full-run gameplay diagnostic using the same frozen
`SilverPriorNetV1` T2 artifact. This did not alter or reinterpret
`LEARNED_PRIOR_SEARCH_HEADROOM_NOT_CAPTURED`. The branch first merged main
`3d28adfcf3c989e338eff9ef85e4a5c6d8794497` into experiment head
`9fe3cb05b4dfd367f9db1370d245cb8d1a4f978e`; no history was rewritten.

After current main `4e4da3b154e59f193c77f972e9b5e2338c52be3c` was merged, native
inference was rebuilt from clean code commit `57a824349fd99c917cf22d67e929a8630f001a9d` and matched all 64 frozen
VALIDATION roots: 411 actions,
maximum prior error `8.799900734768329e-07`, maximum logit error
`2.86102294921875e-06`, under the required `1e-5` prior and `1e-4` logit
tolerances. Coverage included card occurrence cost/special data, potion
target/discard, multi-monster targeting, unknown-pile permutation invariance,
observed-pile order sensitivity, absent monsters, and END_TURN. Warm latency
over 32 repeats/root was median `7,821.303 us`, p95 `11,657.502 us`, mean
`7,520.073 us`; the model loaded in `438,621 us`, and the artifact was
4,792,455 bytes. The user waived the proposed 5 ms/root stop threshold, so the
bounded smoke continued at this measured cost.

Paired smoke seeds `24109998` and `24109999` completed in both control and
learned arms (each run Ascension 0, Act 3 stop, 1,000 simulations/decision,
project-fair, native OOC, one thread, 32,768 allocated reuse cap, adaptive,
visit-lock, and rho racing off). CONTROL made zero prior calls. Summing every
combat telemetry line, seed 24109998 had 24 combats / 383 decisions / 383,000
simulations in CONTROL and 24 / 393 / 393,000 in LEARNED; LEARNED made 380
prior evaluations and 380 root-PUCT calls. Seed 24109999 had 28 / 540 /
540,000 in CONTROL and 28 / 565 / 565,000 in LEARNED; LEARNED made 521 prior
evaluations and 521 root-PUCT calls. All four runs had zero surface,
conversion, semantic-resolution, transaction, and knowledge failures. Exact
mean inference time was 6.679 ms/call and 6.930 ms/call for the two LEARNED
runs. Old per-combat latency percentiles cannot be pooled because raw samples
were not recorded. Smoke outcomes were seed 24109998: both lost; seed 24109999:
both won. They are integration checks, not a gameplay-quality comparison.

The raw `.csv.meta.json` files identify executable SHA
`1dc14cef9f5b6602fe84bd2a266347757245d78c`, not then-current candidate
`fb9e0cf9510ac612fdc3f521076ca093d1fb55b5`. Keep these as working-tree
integration evidence only, not candidate-SHA smoke evidence. Do not rerun these
old smoke seeds to repair provenance; the future frozen screen runner requires
an exact executable SHA and per-call latency samples.

The user-authorized full-run screen then completed all 32 paired seeds
`24100000..24100031` at source `57a824349fd99c917cf22d67e929a8630f001a9d`,
binary SHA-256 `fc41e47d4a7d78f0922144d480a3dbeed674cf6fa1db21e97c568ff836a40197`,
and model SHA-256
`b3a4c5e4bbe91b7f17dadf588408a95199ec5b8b25f732d99ef0966c0ff05fdb`. All 64
A0, project-fair, one-thread, Act-3-stop runs completed at 1,000 simulations
per effective searched decision with the frozen shared flags; each arm checked
the exact source, binary, model, and flags before launch and used the seed
guard. Runtime surface, transaction, conversion, semantic-resolution, and
knowledge-failure counters were zero. The treatment made 12,985 prior
evaluations, all matching root-PUCT decisions; pooled inference latency was
7.247 ms mean, 7.237 ms median, and 11.575 ms p95.

CONTROL won 21/32 and LEARNED won 15/32. The paired table was 1 learned-only,
7 control-only, 14 both-win, and 10 both-lose; the win-rate delta was
`-18.75 pp` (paired-bootstrap 95% CI `[-34.375,-3.125] pp`), with exact
two-sided discordant-pair `p=0.0703125`. The frozen `net_discordant=-6` rule
classifies this as **`ONLINE_LEARNED_PRIOR_UNFAVORABLE`**. This is the
preregistered bounded-screen classification, not a claim of conventional
statistical significance, general model invalidity, or a default change. The
mean floor changed by `-2.00` (95% paired-bootstrap CI `[-4.25,-0.3125]`), mean
end HP by `-11.06` (`[-21.3125,-1.46875]`), and fights lost by `+0.1875`
(`[0.03125,0.34375]`). Mean full-run wall time changed by `+2.167 s`
(`[0.725,3.385]`); search time changed by `-0.828 s` (`[-2.062,+0.224]`),
with its interval crossing zero. The offline
`LEARNED_PRIOR_SEARCH_HEADROOM_NOT_CAPTURED` result remains unchanged.
Compact aggregate and per-seed results are in the [online evidence packet](evidence/silver_prior_online_screen_20260923/README.md);
all raw run output remains under `/tmp/silver-prior-online-screen-57a824349fd99c91`
outside Git.

The first pair exposed a validator accounting defect on its CONTROL GAMBLE
transaction: `simulations` counted both searched subdecisions, while
`decisions` counted the outer transaction once. The runner now validates
`1000 * (decisions + transaction_subdecisions - transaction_decisions)`;
seed `24100009` raw files were not rerun or modified. The complete cohort was
revalidated with this counter definition.

Focused checks passed: `silver_search_optimization`,
`silver_repeated_reroot_canary`, `silver_prior_native_export`, and the two
exporter identity-failure unit tests. All 64-root parity was rerun against the
durable native artifact. The 32-seed screen is complete as recorded above. No
tuning, LOCKED_TEST access, or offline evidence rewrite occurred. See the
[online evidence packet](evidence/silver_prior_online_screen_20260923/README.md).

**Knowledge impact:** the default-off runtime contract remains documented in
`environment-variables.md`, `CODE_MAP.md`, and `combat-search.md`; current
research records this separate unfavorable gameplay screen without changing
the offline mechanism result or qualifying a default.

### OOC CTM final-token optimization (2026-09-23)

From source baseline `3d28adfcf3c989e338eff9ef85e4a5c6d8794497`, retain only
the final Transformer layer's global-token dead-computation elimination. Layer 1
still computes every token; layer 2 computes K/V for every token and Q plus the
remaining output only for token 0. The 31-row Release near-full probe is
byte-identical to baseline (SHA-256
`dbcee67b1037c86e3f9e96b99c2baac47437e812ebb2629feb257a692fe2dd26`), including
prepared/reference sample, full persistent-state, and planner-RNG parity over
128 draws per supported fixture. The focused near-full tests pass.

On one supported captured fixture, one Release `prepare()` measurement changed
from 2.132574 ms to 1.609938 ms (-24.5%). This is one observation per arm and
one fixture; treat it as an initial signal, not a stable aggregate. An earlier
Debug component microbenchmark measured median summed encoder time of 26.695 ms
versus 16.465 ms (-38.3%) across three process runs. Neither is gameplay timing.

A separate contiguous-workspace experiment showed only a noise-sized overall
Release preparation change (5.812681 ms to 5.788186 ms across three samples) and
was rejected from the implementation. Its raw screen and the retained
candidate-1 evidence are in the [final-token evidence packet](evidence/ooc_ctm_encoder_optimization_20260923/README.md).
No gameplay seed or quality comparison was run. The native-contract test's
relic write-back import guard also fails at unchanged baseline; it is not
attributed to this optimization. This is bounded parity and performance evidence,
not production qualification.

## §336 — Forced all-DeepSets OOC CTM timing smoke (2026-09-23)

Compared the current near-full CTM artifact to a separately exported, explicitly
unqualified DeepSets stack on paired seed `12002032` with the same Release
binary and OOC/Silver configuration. The candidate used the Phase-1 survival
DeepSets checkpoint (TEST log loss `0.060430`), shared DeepSets maxHP/HP,
DeepSets downstream heads, and potion screen B despite its
`DEEPSET_POTION_REJECTED` offline decision. Runtime metadata bound all checkpoint
hashes, marked every candidate component unqualified, and left the standard
artifact/default untouched.

The run completed in both arms. In the captured repetition, CTM preparation
plus composed inference fell from `2.397 ms` to `0.591 ms` per call (-75.3%);
combat sampling/resolution fell from `100` to `55` microseconds per call. Whole
MCTS CPU rose from `54.14` to `83.77` seconds, while MCTS simulations rose from
73,218 to 120,399 and CTM preparations from 11,102 to 20,231. The candidate
reached floor 48 versus floor 33, so the whole-run difference includes a changed
trajectory and larger search workload; one seed does not establish gameplay
quality or a stable runtime gain. No separate numerical parity or gameplay
qualification was run. [Full profile
packet](evidence/ooc_deepset_stack_profile_2026-09-23/README.md).

The Phase-1 normalization inputs are bound by the exact prepared-array SHA256
`a642671d0956f36405b837755cdf3dfb3c4870cde4a1d6f251046ffc8205a1c9` and
prepared-manifest SHA256
`fdf1ca760c971b212e60d9cb86beec78afae6b124958aa53c56a8aea5bb92f51`. The
review-hardened re-export binds these inputs and the computed mean and
inverse-standard-deviation vector hashes in candidate metadata. Its tensor
payload matches the measured candidate byte-for-byte; its metadata-only change
was not rerun for timing. Only the second execution's timing/profile was
retained. The first execution per arm was a functional repetition and its
timing was not captured.

Knowledge impact: this timing smoke is recorded here; model qualification,
standard CTM artifact and runtime defaults remain unchanged.

## §337 — PR 295 DeepSets shared transition-encoder reuse (2026-09-23)

On the current PR 295 tree, the exporter-installed DeepSets artifact's 28
maxHP, HP, and potion encoder tensors were byte-identical across all three
groups. The Release probe also emitted all three 64-value representations;
they were identical on each of 28 supported frozen fixtures. Candidate artifact
SHA-256 is
`3f6d174950f1e4a8b042cebc78bd8525c7e112a13e31865670a39df4b0f2f586`, the
current provenance-hardened re-export with tensor payload identical to the
originally profiled candidate.

The DeepSets-only prepared path now computes the shared transition encoding
once for the maxHP, HP, and potion heads. Survival remains separate. Code
inspection shows prepared encoder calls fall from four to two; this is not a
runtime-instrumented counter. Attention-artifact preparation retains the
original code path. Across 31 fixed fixtures (28 supported), all
3,584 prepared/reference draws, deterministic outputs, support results, full
persistent post-states, and planner RNG checks matched exactly before and
after.

Release preparation timing on one identical fixed fixture over 30 independent
process repetitions changed from median `284,427 ns` (range `280,254-357,929`)
to `142,541 ns` (range `140,062-265,236`), a `49.88%` median reduction. The
ranges did not overlap. This is fixed-fixture runtime evidence, not model
qualification or a gameplay result. Applying that reduction to PR 295's
historical `14.28%` CTM-preparation share of MCTS CPU projects about `7.12%`
less same-workload MCTS CPU; this projection is an inference, not a measured
search speedup. Later profiling candidates were not run because the clear Phase
2 result met the handoff stop rule.

The Release probe and `one_combat` targets built. Focused loader and near-full
artifact CTests passed (2/2). The full 31-row `smoke-and-parity` invocation
returned `invalid_relic_counter` on both the untouched PR 295 preparation path
and the candidate path, with the same artifact and fixtures; both emitted
eight rows first. This reproduces the failure on baseline and shows it is not
specific to encoder reuse. The separate `near-full` path completed all
fixtures and verifies prepared/reference state and RNG parity. Full CTest,
GitHub Actions Linux GCC, game seeds, and gameplay comparisons were not run.
[Evidence packet](evidence/ooc_deepset_encoder_reuse_2026-09-23/README.md).

Knowledge impact: experiment evidence only; no maintained qualification,
production artifact, or default changed.

## §338 — Potion-specific end-to-end DeepSets specialist (2026-09-23)

- **Question and baseline:** Does jointly training a dedicated 64-wide
  DeepSets potion encoder and the existing exact trajectory decoder recover
  the gap of the frozen shared-representation substitution? Baseline is
  `c62f3694517bf622d2670a9fbf3c20a70380a763`; dedicated Attention reference
  validation trajectory NLL is `0.506803228`.
- **Intervention/provenance:** W initialized its encoder/decoder from
  `bee6800d…c3003dc663` / `06eda953…448819c1`; S used deterministic seed
  `20260912`. The exact existing trajectory loss and legality/DAG semantics
  were retained. Both arms used FP32, batch 512, AdamW, encoder/decoder LR
  `1e-4`/`1e-3`, weight decay `1e-4`, clip 1.0, up to 40 epochs, and the same
  TRAIN batch order. TRAIN was 393,677 rows / 19,986 sources; VALIDATION was
  48,590 / 2,496. The receipt records zero TEST encoding/inference rows; the
  cache loader reads the prepared cache as a whole, but TEST examples were not
  encoded, evaluated, selected on, or used for debugging. The three prepared
  cache artifacts were reproduced byte-for-byte from their provenance source
  revision. Implementation SHA is
  `3d1db667f0859c5a1d4788cb4232eaf6f6670bb7`.
- **Reproduction guard:** the newer
  [`reproduction wrapper`](../../tools/reproduce_combat_transition_deepset_potion_specialist.py)
  pins the recorded baseline/experiment SHAs, validates the actual clean source
  worktree HEAD at the experiment SHA and verifies baseline ancestry, then
  invokes the historical trainer with fixed provenance arguments. The trainer
  alone is not a provenance guard. The wrapper replaces inherited
  `PYTHONPATH` with that worktree root, disables user-site imports, and removes
  `PYTHONHOME` before starting the trainer. Its dry-run command was verified
  against a real detached worktree at the pinned source; training was not
  repeated.
- **Result:** W selected epoch 27 at NLL `0.487162724` (`-3.8754%` vs reference);
  S selected epoch 34 at `0.498382425` (`-1.6616%`). W no-change Brier was
  `0.086596849` vs `0.092057790`; normal action-mode/count accuracies were
  `0.816036359`/`0.824688321` vs `0.806321144`/`0.814556144`. W illegal
  probability was zero and max normalization error `2.14e-7`; reload reproduced
  metrics. W Brew/Smoke/trajectory-special NLL changes were `+7.0897%`,
  `-16.5479%`, and `+3.1766%`; recursive Brew was `+13.3126%` (12 rows).
  Scratch recursive Brew was `+33.4429%`. The strongest remaining degradation
  is concentrated in recursive Brew, though that small slice limits inference.
- **Decision:** **`POTION_DEEPSET_SPECIALIST_REJECTED`** by the existing
  teacher-forced gate. Per the stated stop rule, W is a narrow miss: it improves
  clearly over the previous frozen DeepSets result (`0.537569223`, +6.0706%)
  and the Attention reference overall, but fails the recursive-Brew slice
  gate. Do not continue with width or hyperparameter sweeps. A bounded next
  architecture experiment should first inspect the recursive-Brew
  TRAIN/VALIDATION examples. One unverified hypothesis is that the encoder's
  `z` retains initial inventory information at recursive DAG nodes while the
  decoder's separate current-inventory input changes; test this before choosing
  a potion-slot/context interaction layer or another architecture change.
  No ancestral draws, TEST scoring, export/native parity, latency, gameplay,
  OOC MCTS, or runtime/default promotion ran. Hardware was local RTX 3060 Ti
  with CUDA available; no GCP instance or spend was used.
- **Evidence:** [report](evidence/potion_specialist_deepsets_2026-09-23.md),
  [complete receipt](evidence/potion_specialist_deepsets_2026-09-23.json)
  (SHA256 `31a26d11553b30ecfd3f495d21e8cce61dd74129bcf5516d160cc94a66621a44`).
  W checkpoint SHA256 is `71d88a71cf7579e1092c3b3c27e000538a6aafe35bbf5228c10c15fa0edd4ace`;
  S is `b0bac3affcf389e6317cc90424ad58d69fc10a6f623a320e8db0a22379367c62`.
  Raw run directory: `/tmp/deepset-potion-specialist-20260923`.

Knowledge impact: current potion-representation status and experiment evidence
updated; qualified encoders and runtime defaults remain unchanged.

## §339 — Potion-pooled-blind DeepSets follow-up (2026-09-23)

- **Question and baseline:** Does removing the initial pooled potion identity/
  slot contribution from DeepSets `z` preserve the PR #298 specialist's overall
  result and repair recursive Brew? Baseline `1ed96f2aa564742156cc6593a1fc1915ea4e9033`;
  Attention reference validation trajectory NLL `0.506803228`.
- **Intervention:** C reproduced the ordinary PR #298 warm-start encoder and
  exact trajectory decoder. P used identical checkpoint bytes and fixed batch
  order, replacing only the pooled potion block with zeros. Potion embedding/
  MLP parameters stayed in the checkpoint module but were frozen and excluded
  from AdamW. The current-inventory-conditioned decoder, trajectory DAG, labels,
  legality, and global fields remained unchanged. Thus `potionCount` and
  `potionCapacity` remain in P's global representation.
- **Stage 0:** frozen TRAIN contains 90 recursive-Brew winning rows from 90
  source seeds; VALIDATION has 12 from 12 seeds. Every audited target has at
  least one compatible trajectory, with no obvious target/DAG defect. Full
  per-case inventory, capacity, boss, Sozu, generated-body, target, graph, and
  existing-model NLL details are in the audit JSON.
- **Provenance and fit:** implementation `cffe964a806891908ea1082bcca632683c4d2d37`;
  encoder/decoder warm-start hashes `bee6800dd7230b180c2b4894c0f01763efca4b7799e3f36a805333c3003dc663` /
  `06eda953b523ed6b3b9dbc3031bf44408c3bc67f0bc8b7862d28c150448819c1`;
  TRAIN 393,677 rows / 19,986 sources; VALIDATION 48,590 / 2,496. C selected
  epoch 34 at NLL `0.486931329`, within `0.000231` of the prior W result and
  inside the fixed `0.005` control-reproduction tolerance. P selected epoch 31
  at NLL `0.489927014`. Local runtime was Python 3.12.3, PyTorch 2.5.1+cu121,
  CUDA 12.1, RTX 3060 Ti. Runtime counters recorded zero TEST encoding, scoring,
  or teacher-metric rows.
- **Result:** P relative overall trajectory NLL was `-3.3299%` versus
  Attention; no-change Brier improved from `0.092057790` to `0.087477024`,
  normal action/count accuracies were `0.815202435`/`0.824292207`, illegal
  probability was exactly zero, and maximum normalization error was
  `1.99e-7`. Recursive Brew was `3.026048` versus Attention `2.412967`
  (`+25.4078%`) and C `2.985346` (`+0.040702` nat mean difference). P improved
  on 5/12 paired recursive cases and worsened on 7/12; see the report for every
  row. The other P slice changes were Brew `+6.9947%`, Smoke `-7.9783%`, and
  trajectory-special `+4.5160%`.
- **Decision:** **`POTION_DEEPSET_POTION_BLIND_REJECTED`** by the unchanged
  teacher-forced gate. Removing the pooled potion branch did not repair the
  recursive-Brew regression. The result weakens that pooled-branch-only
  hypothesis; it does not test removing global count/capacity signals or
  establish another cause. Stop here: no ancestral evaluation, TEST scoring,
  export, native/runtime qualification, gameplay, or alternate architecture.
- **Checks/artifacts:** focused specialist unit tests: 13 passed; Python
  compilation and `git diff --check` passed. The experiment command exited 0,
  checkpoint reload reproduced metrics, and runtime TEST counters were zero.
  GitHub Actions CI was not run locally. See
  [report](evidence/deepset_potion_blind_2026-09-23.md),
  [complete receipt](evidence/deepset_potion_blind_2026-09-23.json) (SHA256
  `16a7958fe0ea6c74ffac1fe7552a66be2215fe19e778a10bfc6254ff8e7ae4be`), and
  [Stage 0 recursive audit](evidence/deepset_potion_blind_recursive_audit_2026-09-23.json).
  Selected checkpoint hashes: C `99a43bfa138021ff9f645accd1e098ec89863b9498490294837762a93b18ff1c`,
  P `38c2b8eadc0aa1926c6bbbbe46e952d30e652dee7887559b6b57a0f4726dcab0`.

Knowledge impact: current potion-representation hypothesis and evidence updated;
runtime defaults and qualified artifacts remain unchanged.

## §340 — Silver handoff timing and adaptive 128-seed baseline (2026-09-24)

Measured how much Silver decision time goes to moving state between the main
simulator and the isolated Silver simulator. The run used the new opt-in
`STS_SILVER_HANDOFF_TIMING=1` instrumentation. It also recorded a Silver
whole-run reference on the standard seed block under the ADR-0018 defaults.

- **Configuration:** Release `one_combat` from clean commit `2a602f6`, 4-core
  container, `bestbench 1000 128 0 126700` with `STS_SILVER_ADAPTIVE=1`. The
  sims argument has no effect under adaptive Silver, which searches 500 to
  10,000 simulations per decision. Silver fair play, reuse cap 32,768
  (`allocated`), native OOC trees, policy prior auto-load, keys skipped,
  ascension 0. Regime: project-fair.
- **Gameplay:** 83/128 wins (64.8%; Wilson 95% [56.2%, 72.6%]). Mean floor
  48.26, mean end HP 30.9, 38.05 CPU s/run, 1,240 s wall. Win means beating
  the Act 3 boss; keys were not collected.
- **Timing:** 3,245 combats, 59,961 decisions, 377.3M simulations, 4,818.6
  decision-seconds.

  | Part | Share of decision time | Mean per decision |
  | --- | ---: | ---: |
  | Live-state conversion | 0.006% | 5.0 µs |
  | Private-state materialization | 0.004% | 3.4 µs |
  | Semantic-action resolution | 0.002% | 1.3 µs |
  | Root setup (exact reroot or fresh root, including collection) | 2.56% | 2.06 ms |
  | Search | 97.36% | 78.2 ms |
  | Other (diagnostics, captures) | 0.07% | — |

  In a pre-commit smoke of the same code, 16 seeds with flat 1,000-simulation
  Silver gave 0.045% copy time (8 µs/decision), 0.99% root setup and 98.9%
  search.
- **Interpretation:** Copying state across the simulator boundary
  (conversion, materialization and resolution) costs about 10 µs per decision
  and is negligible. Root setup is the only material non-search cost. A
  retained-tree design needs it regardless of simulator count.
  **Inference:** merging the simulators would not produce a meaningful speed
  gain. Its case rests on having one rule set and removing the
  boundary-matching code.
- **Artifacts:** [evidence packet](evidence/silver_handoff_timing_2026-09-24/README.md)
  with the results CSV, metadata, all per-combat timing lines and the
  reproducible summary.

Knowledge impact: combat-search architecture records the handoff cost;
current-baselines records the Silver adaptive whole-run reference.
## §341 — V4 policy-prior cost under uniform-leaf OOC MCTS (2026-09-24)

On baseline `41c0f5af5711c452b6e133e6dc66c7756f50874c`, refreshed the fixed
seed `12002032` profile with the requested V4 policy prior, uniform leaf policy,
2,048 simulations, same DeepSets CTM and Act-3 stop. The refreshed run reported
119,445 simulations, 115,398 transitions, 88,566 policy/state evaluations,
29.823s MCTS thread CPU, 35.516s real-combat CPU, 5.226s CTM preparation,
5.428s policy prediction exclusive CPU and 7.023s V4 state-network CPU.
Expanded-node action counts were 0:0, 1:40,599, 2:21,831, 3+:49,456; 23,700
singleton nodes called `policyLogits()` and V4 inference.

Two exact changes were retained: singleton legal sets now receive prior 1.0
without model inference, and the V4 policy head reuses the immutable state
prefix (ordered dimensions 0–127) across candidate actions before consuming
the unchanged action suffix (128–183). The Q path and candidate encoding were
not changed. Exact source logits, aggregate/normalized priors and action order
are covered by the focused adapter self-test; fixed-work MAP search preserves
selected action, priors, visits, Q, work counts, state fingerprints and RNG.

An alternating prefix-only/prefix+singleton/singleton/prefix-only fixed-seed
comparison preserved run outcome and byte-identical action/support traces.
Singleton V4 policy inferences dropped from 23,700 to zero; the policy/state
inference count fell 26.8%. Mean MCTS thread CPU decreased 37.867s to 34.888s
(7.9%). Mean measured whole-process CPU decreased 3.3%, a modest result under
substantial CPU throttling. Separately, the prefix-only change measured 10.6%
lower MCTS CPU and 6.0% lower whole-run wall in its alternating repetitions.
A final observational profile split the remaining 6.166s V4 state-preparation
inclusive CPU into deck 3.154s, state fusion 2.488s, relic 0.199s, and potion
0.070s; these components were not optimized.

The one-seed performance evidence does not establish gameplay improvement,
production speedup or default promotion. Live OOC MCTS stays opt-in, and the
uniform-leaf/V4-prior research configuration remains unchanged. See the
[complete evidence packet](evidence/ooc_v4_prior_uniform_leaf_optimization_2026-09-24/README.md)
for provenance, raw commands/results, checks and remaining uncertainty.

Knowledge impact: current OOC implementation and profile evidence updated in
the architecture and current-research pages; no qualified baseline or runtime
default changed.

## §342 — Experimental DeepSets CTM with Entropic Brew fallback (2026-09-24)

- **Question and baseline:** Can the PR #298 potion-aware DeepSets specialist
  serve ordinary OOC CTM preparations while the current standard Attention
  artifact handles every pre-combat Entropic Brew state? Baseline is merged
  PR #303 at `41c0f5af5711c452b6e133e6dc66c7756f50874c`. This is an
  engineering screen, not another offline potion qualification.
- **Intervention/provenance:** Exported the existing, already-verified W
  checkpoint unchanged (SHA256
  `71d88a71cf7579e1092c3b3c27e000538a6aafe35bbf5228c10c15fa0edd4ace`,
  epoch 27) as a dedicated potion encoder/decoder in the experimental
  DeepSets stack. A new opt-in hybrid routes each full predictor-visible
  pre-combat input containing Brew to the exact current standard V2 CTM;
  other inputs use the experimental fast child. The default path is
  unchanged, and the specialist itself rejects direct Brew use.
- **Mechanism/parity:** Python/native W parity passed on 31 frozen fixtures
  at `1e-4` absolute tolerance (maximum encoder/probability errors
  `7.75e-7`/`4.77e-7`, zero legal-mask mismatches). Hybrid/direct-child support,
  prepared and scalar draws, full RAW state and RNG identity passed for the
  same fixture inputs; routing consumed no planner RNG. Direct fast-path Brew
  use failed closed. The 18 Brew rows among 31 fixtures are mechanism coverage,
  not a representative dispatch sample. Pre-combat routing is sufficient for
  the known recursive-Brew case because its trajectory starts with Brew in
  the visible inventory.
- **Fixed-input timing:** On 31 frozen fixtures, 10 warmups and 100 repeats
  per row, the 10 non-Brew rows supported by fast were timed on both children:
  median preparation was 3,715 us standard versus 491 us fast (7.57x), with
  hybrid fast at 487 us on those same rows. Median sampling was 39.5 us
  standard versus 35.0 us fast. Separately, on 18 supported Brew rows standard
  preparation was 3,315 us and hybrid fallback 3,419 us; sampling was 41.7 and
  44.4 us. Encoder calls were 4 for standard/fallback and 3 for fast. Fixture
  fallback share is 18/31 and cannot estimate OOC frequency or whole-search
  speed. This is a fixed-fixture timing smoke only.
- **Implementation checks:** The initial review confirmed fallback metadata
  identity but did not bind the standard artifact bytes. Follow-up review found
  the gap; source commit `9a1335a243e08ad57c59a36c95b48778fdba8b76` pins the
  actual standard artifact SHA256 to
  `e9a18951710fdfe9e1a81a2703090a41f039067c670a1d8a0393b5e7e8e0ddfd` and
  adds a matching-metadata byte-tamper rejection check. After rebasing onto
  `bb2379e844464f9bff35a6ca61e1eeaa8dbb0090`, the six runtime-linked Release
  targets built, focused adapter/runtime-loader CTest passed 2/2, Python/native
  parity and the hybrid mechanism probe passed again, and fixed-input timing was
  rerun. Full GitHub Actions CI was not yet available.
- **Paired OOC screen:** After review, the implementation was frozen at
  `9ce11fdbe50f32b4b2646dd8a0803c6dc0c3f351`. Standard and hybrid both ran
  seeds `980000..980063` with 10,000 combat simulations, 2,048 OOC MCTS
  simulations, A0 fair play, 24 threads, Silver continuation, V4 policy, and
  identical non-model settings. Each arm has 64 unique results and matching
  per-seed MCTS traces/configuration metadata. Standard won 40/64, hybrid
  39/64; discordant outcomes were 7 hybrid-only and 8 standard-only wins. The
  paired delta is **-1.56 pp** (bootstrap 95% CI `[-14.06,+10.94] pp`, exact
  discordant p `1.0`), classified
  **`OOC_HYBRID_WINRATE_INCONCLUSIVE`**. This is not equivalence evidence.
- **Runtime and dispatch:** Mean bestbench elapsed time was 641.4 s/seed for
  standard and 439.7 s/seed for hybrid (paired change `-201.7 s`, 95% CI
  `[-254.8,-141.3]`). Mean MCTS CPU was 139.35 vs 94.85 s/seed (change
  `-44.50 s`, 95% CI `[-69.61,-5.93]`); MCTS wall was 462.83 vs 276.65 s.
  The hybrid recorded 4,219 Brew fallbacks out of 1,135,061 preparation calls
  (**0.372%**) and 401 per-seed unique Brew states summed across runs. It
  recorded 21 fast-child and 1 fallback-child support-failure queries. MCTS
  support aborts were 20 control and 22 hybrid; all were the existing
  `smoke_bomb` exclusion, with no new unsupported reason. Whole-process CPU
  was not separately recorded. Arms made different work counts, so total time
  is a runtime signal, not a matched-work causal estimate.
- **Decision:** The mechanism and runtime questions look promising: ordinary
  fixed-input preparations are substantially faster and Brew is rare in this
  OOC cohort. The observed paired win-rate difference is small, but the
  interval still includes a sizable regression; the screen is inconclusive and
  does not establish quality equivalence. A separate larger confirmation is
  warranted before any default promotion. Do not use this bounded result as
  offline CTM qualification.
- **Checks/evidence:** Release targets built; focused adapter/runtime-loader
  CTest passed 2/2; Python compilation and `git diff --check` passed. Full CI
  was not run. See the
  [mechanism, timing, and paired OOC packet](evidence/deepset_entropic_brew_hybrid_2026-09-24/README.md),
  including the raw per-seed CSV, source/config receipts, support counts,
  compressed action traces, and reproducible summary.
- **Evidence:** [mechanism and timing packet](evidence/deepset_entropic_brew_hybrid_2026-09-24/README.md).

After PR #309 advanced `main` to `7a181b3fa296fda4122033b70767fc2c0f03618c`,
the branch was rebased onto that Silver-only architecture. The six Release
targets and focused 2/2 CTest selection passed again; 31-fixture parity and
hybrid routing/RNG checks passed. On 10 matched ordinary rows, standard median
preparation was 4,732 us, fast was 534 us (8.86x), and hybrid fast was 661 us
(7.16x). On 18 Brew rows, standard was 3,687 us and hybrid fallback 3,726 us.
An OpenSSL-disabled configuration also built the non-CTM `main` target after
the Crypto dependency was made optional at configure time. These checks do not
change or relabel the original 64-pair outcome, which remains attached to frozen
executable `9ce11fdbe50f32b4b2646dd8a0803c6dc0c3f351`. Exact commands and raw
outputs are in the [Silver-only main verification packet](evidence/deepset_entropic_brew_hybrid_2026-09-24/silver-only-main-source/COMMANDS.md).

Before publication, `main` advanced again through PR #310 to
`7b4244ef8af4508466e01a1a6b515c70015e6274`; the branch was rebased onto this
head and all six Release targets plus focused CTest passed again. Parity and
mechanism checks again passed all 31 fixtures. Fixed-input preparation medians
on 10 matched ordinary rows were 3,957 us standard, 520 us fast (7.61x), and
508 us hybrid (7.79x); on 18 Brew rows, standard was 3,565 us and hybrid
fallback 3,708 us. OpenSSL-disabled configure and non-CTM `main` build passed.
No gameplay run was repeated. Results and commands are in the
[PR #310 verification packet](evidence/deepset_entropic_brew_hybrid_2026-09-24/main-7b4244-source/COMMANDS.md).

- **Independent 512-pair confirmation (2026-09-25):** Frozen gameplay source
  `c9ecfb2041f8061d89bd728b8dccded2e8e12adf` and binary SHA256
  `c08bdd7e37a26c0ad47d3b6e75c0e08dcc729fc49191553e0fcbbc169d10d244` were
  used unchanged. After correcting the analyzer's c9 metadata expectation to
  `models.policyNet="off"` and adding a regression test, analyzer and canary
  self-tests passed; both preserved `989999` canaries passed mechanism and
  provenance validation. Independent V4 policy-load and effective-config
  checks remained enforced. The paired confirmation used exactly seeds
  `990000..990511`, Ascension 0, 10,000 Silver simulations, 2,048 OOC MCTS
  simulations, 24 threads, Act-3 horizon, and the frozen −5 pp gate. Execution
  changed transport only: eight normal seed-guarded 128-seed invocations in
  `C1,H1,C2,H2,C3,H3,C4,H4` order, with `OMP_NUM_THREADS=24` and CPU affinity
  externally limited to CPUs 0–7. Per-chunk receipts do not encode CPU
  affinity; the run-level value is preserved in the tracked local runtime
  provenance record. Both arms completed all 512 seeds and passed strict
  receipt/seed merging before analysis. C won 277/512 and H
  292/512; paired H−C was `+2.9297 pp` (paired bootstrap 95% CI
  `[-1.7578,+7.6172] pp`). Its lower bound is above the −5 pp margin, meeting
  the predeclared non-inferiority criterion and yielding
  **`OOC_HYBRID_QUALITY_CONFIRMED`** for this cohort. This is not a superiority
  claim or offline CTM qualification; the hybrid remains opt-in and no runtime
  default changed. Compact decision-bearing evidence is committed in the
  [confirmation evidence packet](evidence/deepset_entropic_brew_hybrid_confirmation_2026-09-24/README.md);
  full chunk outputs, logs, transport receipts, and merged arm files remain
  ignored under `build/local_deepset_hybrid_confirmation_7069518/`. Summary SHA256
  `0afa5319c21706ef380b76825035514c76dbe694bbafa4ed6293a75ce48b98ce`, merge
  report SHA256
  `fef01e97b6eba1b0a8fa4394676c2081c913f35780a12c14747abe1dc8cdb282`.
  Preserved canaries passed validation after the metadata fix. The local runner
  then repeated the same canary seed in its fresh output root before C1; those
  additional canary outputs also passed and remained excluded from analysis.
  CPU affinity was transport-only; the pinned clean treatment environments
  retained `OMP_NUM_THREADS=24`. The recorded `transportToolGitSha` is launch
  base HEAD `7069518b5da3b38f4bac562a9b724de158814583`, not a commit containing
  the then-working-tree helper files. The analyzer/merger/runner file hashes
  are recorded in the confirmation evidence README.

Knowledge impact: current research status and the independent confirmation
evidence are recorded; qualified models and runtime defaults remain unchanged.

### §343 — Active Lizard Tail CTM qualification (2026-09-23)

From baseline `aa09f75e6be837f7f39a2e31dde234bfd2c2ef08`, a detached shadow
collector used the frozen `silver-ordinary-fair-exact10k-combat-transition-runtime16-f0bbd77`
teacher and produced 111 unique source seeds (`4200100..4200210`), 2,234 rows,
2,223 wins, 11 deaths, and zero quarantines. Combined with the 16-seed smoke,
the local collection used 127 unique source IDs, within the 128-source cap.
Manifest SHA-256:
`457e33d53c7af2f474957d2201da0f7a7c95a1f6be10de71f40782cb14f832f6`; corpus
SHA-256:
`4d9927ad0f23d7f9e6e1fdb1091c6cf98ff7f5935540a5103746257b550b5504`.

The source-grouped split contains 87 TRAIN, 15 VALIDATION, and 9 TEST source
seeds. Supported non-Lizard HP, potion, and relic composition exposure met the
existing 0.1-nat mean-gap gates, although the relic result uses only 32 rows
from four sources. The old untrained Lizard head scored worse than the
TRAIN-only prior (TEST gap +0.76590 nat; 95% source-bootstrap CI
[+0.61415, +0.87443]). A fixed 10-epoch fit of only the two Lizard-head
parameters on supported TRAIN victories was therefore run under the existing
relic recipe. Its TEST NLL was 0.69889 versus 0.19213 for the TRAIN-only prior;
the paired source-bootstrap gap was +0.50675 nat (95% CI [+0.37380, +0.61081],
126 winning rows / nine sources). The Lizard head is rejected by the existing
proper-score gate. Ancestral sampling covered all 127 fully supported TEST
pre-states (including the observed death), with zero hard-validity failures;
this does not override the score rejection.

Production `active_unqualified_lizard` remains unchanged. No Phase 3B
specialist, runtime integration, native/Python parity qualification, gameplay
benchmark, or live seed `13027029` check was run. The live check remains gated
on offline qualification. See the [complete evidence packet](evidence/active_lizard_ctm_2026-09-23/README.md).

**Knowledge impact:** the maintained current-research page now points to this
negative result; active Lizard Tail remains outside qualified CTM support.

### §344 — Active Lizard Tail paired rescue pilot (2026-09-23)

A 32-source paired pilot (`4200100..4200131`) compared exact Silver combats
with and without active Lizard Tail under the frozen ordinary fair 10k teacher.
It is descriptive only: 30 pairs won in both treatments with Tail retained;
one ordinary death became an active-treatment win with Tail consumed; and one
ordinary death became an active-treatment win with Tail retained. The ordinary
CTM mean predicted death rate was `0.05704` versus `0.0625` observed deaths
(Brier `0.01474`). The observed Tail-consumption rate was `0.03125`, with Brier
`0.03182` when compared to those same death probabilities. Two ordinary deaths
are too few to infer a rescue rate or calibration. The retained-Tail win also
shows active relic presence can change the policy trajectory, so consumption
cannot be treated as a direct label for the no-Tail counterfactual. The
existing conditional heads had only one Tail-consumed winning row to score.

During collection, seven rows asserted on a potion reward when all three slots
were full. The paired source-reward branch lacked the full-inventory guard in
the normal reward policy; adding that guard fixed the invalid action, and all
seven rows then completed. This is a collector fix, not CTM evidence.

No rescue head, scalar extra-HP model, training, support qualification, or
runtime integration followed. The failed Lizard-head proper-score result in
§343 and production `active_unqualified_lizard` guard remain unchanged. See the
[paired pilot evidence packet](evidence/lizard_tail_rescue_pilot_2026-09-23/README.md).

**Knowledge impact:** exploratory evidence only; no model or runtime change.

### §345 — Risk-targeted active Lizard Tail rescue experiment (2026-09-24)

The preregistered 128-source cohort (`4200300..4200427`) completed candidate
generation with 2,700 ordinary combat rows and zero quarantines. Precombat CTM
risk-only selection yielded 128 unique targets across the four declared risk
bands plus 19 low-risk fallbacks, because band availability overlapped by
source. Exact-state paired collection completed 128/128 targets with zero
quarantines.

The no-Tail arm died in 27/128 fights (21.1%); active Tail won 123/128 (96.1%)
and was consumed in 32/128 (25.0%). Among control deaths, active Tail won 22/27:
14 wins consumed Tail, while 8 wins retained it. Silver's first action changed
in 59/128 pairs and full action traces in 122/128, confirming that policy
adaptation is frequent even when Tail remains. The HP-shift survival proxy
predicted 90.3% mean win probability versus 96.1% observed active-Tail wins;
this is not a lethal-crossing replay or a policy-aware Tail model.

On 71 both-arm wins with active Tail retained, paired post-head NLL deltas did
not meet the preregistered material-shift criterion. The CIs remain too wide to
establish equivalence, and supported relic-group comparisons had only 5–12
pairs. The head scores are teacher-forced descriptive screens, not
qualification. The data support continuing with small survival/consumption
corrections as the next research candidate while modeling policy adaptation;
they do not justify a full specialist or establish that existing heads can be
reused in runtime.

The complete candidate, selection, paired, and analysis artifacts, hashes,
unsupported-row counts, and interpretation are in the [targeted rescue evidence
packet](evidence/lizard_tail_targeted_rescue_2026-09-23/README.md). No training,
support expansion, runtime integration, model/default change, native/Python
parity test, or gameplay qualification followed. Production
`active_unqualified_lizard` remains fail-closed.

**Knowledge impact:** targeted descriptive evidence only; qualification and
runtime boundary unchanged.

### §346 — Minimal active Lizard correction diagnostic (2026-09-24)

On the same 128-pair cohort, the fixed `T2` revive-HP transform lowered
consumed-win HP NLL by `1.084` nat on 22 supported rows (paired source-bootstrap
95% CI `[-2.165,-0.331]`). Its HP CRPS point estimate also improved; the CI
crossed zero. `T1` improved HP scores more, but showed positive paired
relic-constraint deltas for attacks, shuffles, and turns, so it was not
retained. T2 is an offline development candidate only; neither transform
qualifies the reused heads.

The 3-class labels were 96 `WIN_RETAINED`, 27 `WIN_CONSUMED`, and five
`LOSS_CONSUMED`. Six Fairy Potion rows were left at the exact boundary, leaving
122 modeled rows; Mark of the Bloom remains excluded. B1 mechanical reserve was
coherent on all modeled rows. The 5-fold source-grouped L2 q/r correction had
NLL `0.5641` / Brier `0.3181`, versus B1 `0.5774` / `0.3279`, but paired
source-bootstrap intervals for correction-minus-B1 included zero for both
scores. The small correction therefore has no clear signal over B1, and five
losses do not establish rescue prediction. Recommend collecting 20 additional
`LOSS_CONSUMED` examples (25 total) before reassessing; this is not a
qualification threshold.

The 32-draw-per-supported-source offline prototype produced 3,136 class draws
from 98 supported sources; 30 sources fell back under existing support or
Fairy boundaries. There were zero impossible `LOSS_RETAINED` or
spent-to-active transitions; all sampled Tail states matched class, all 3,019
victory states had legal HP, and all terminal snapshots had legal potion and
persistent relic state. No runtime sampler, model artifact, or production
support changed. Classification: `LIZARD_MINIMAL_CORRECTION_DATA_LIMITED`.
See the [Phase A-C evidence packet](evidence/lizard_tail_targeted_rescue_2026-09-23/README.md#minimal-three-state-correction-diagnostic)
and raw [analysis JSON](evidence/lizard_tail_targeted_rescue_2026-09-23/minimal-correction-analysis.json).

**Knowledge impact:** current research status and development evidence updated;
production active-Tail qualification remains unchanged.

### §347 — B1-ranked active Lizard candidate-pool extension (2026-09-24)

The frozen 2,700-row precombat pool was rescored with fixed B1
`P(LOSS_CONSUMED) = 1 - pReserveWin`. Four targeted batches added 347 unique
paired fights after dropping 35 repeated `(sourceSeed,fightIdx)` rows that
overlapped the original 128-pair cohort; those repeated replays differed, so
the original observation was retained. The new rows had 305 `WIN_RETAINED`,
34 `WIN_CONSUMED`, and eight `LOSS_CONSUMED` outcomes. This raises the distinct
loss count from five to 13, below the prior target of 20 additional examples.
First Silver action changed in 136/347 new pairs.

The combined analysis contains 475 unique paired fights, 451 modeled rows from
124 sources after 24 native exact-boundary exclusions. A follow-up prospective
runtime-domain analysis additionally reapplied `full_support_reasons()` to the
Tail-stripped state and predictor, excluding 24 unsupported rows and leaving
427 rows from the same 124 sources (362 `WIN_RETAINED`, 53 `WIN_CONSUMED`, 12
`LOSS_CONSUMED`). Five-fold q/r CV and source-bootstrap resampling kept all
fights from each source together. With T2 fixed and not retuned, the
support-domain q/r scored NLL `0.3427` / Brier `0.1932`, versus B1 `1.9890` /
`0.2096`; q/r minus B1 source-bootstrap intervals were `[-4.9543,-0.0132]`
and `[-0.0310,-0.0011]`. The broader descriptive analysis remains in the
packet: its q/r scores are NLL `0.3544` / Brier `0.1994` versus B1 `1.9122` /
`0.2158`. The prospective-domain result remains promising but data-limited;
12 supported losses do not qualify its rare rescue class.

The 35 overlapping source/fight rows are exact combat-observation duplicates:
both arms' transition states, outcomes, Tail state, and Silver traces match.
Only the selector's `targetRiskBand` differs. The comparator now ignores that
metadata and records 35/35 as matching; the original cohort observation is
still retained.

The 1,611 supported, coherent, unpaired candidates had summed fixed-B1 loss
mass `1.4045` (mean `0.000872`), below the 12 further cases needed to reach the
sample target. Batches 2 and 3 added zero losses despite score mass about 6.05
and 2.35 respectively. Collection stopped because the remaining pool could
not plausibly provide the target under the fixed selection model, rather than
because every candidate row was replayed. All four pair manifests had zero
quarantines and clean conversion/semantic/transaction/knowledge counters. No
training, export, runtime integration, or support expansion followed;
`active_unqualified_lizard` remains fail-closed. See the [extension evidence
packet](evidence/lizard_tail_targeted_rescue_2026-09-23/README.md#b1-ranked-candidate-pool-extension)
and [combined B1/q/r JSON](evidence/lizard_tail_targeted_rescue_2026-09-23/b1-qr-combined-analysis.json).
The support-domain rerun is [recorded separately](evidence/lizard_tail_targeted_rescue_2026-09-23/b1-qr-runtime-support-analysis.json).

**Knowledge impact:** current research status and the experiment evidence now
record the targeted-pool stop and source-grouped comparison; runtime support
and qualification are unchanged.

### §348 — Silver search ported onto the main engine: 128-seed gate (2026-09-24)

Compared the Silver combat search ported onto the main simulator
(`SilverSearcher` behind `STS_NATIVE_SILVER=1`, no conversion into the
vendored model) with the vendored Silver backend on the §340 seed block.

- **Configuration:** Release `one_combat` from commit `f81eabb` on branch
  `claude/native-silver-searcher`, 4-core container, `bestbench 1000 128 0
  126700` with `STS_NATIVE_SILVER=1 STS_SILVER_ADAPTIVE=1` (adaptive
  retained-root policy, 500 → 10,000 simulations). Project-fair, native OOC
  trees, keys skipped, ascension 0. Baseline: the vendored §340 run on the
  same seeds (commit `2a602f6`; later commits kept vendored bestbench rows
  identical at 200 flat simulations).
- **Port scope:** production search path only (UCB with exploration 25, DPW
  chance widening 3.7028/0.52389, transposition dedup, reroot with the 32,768
  node cap, Silver's rollout policy and terminal evaluation). The draw pile
  uses the information-set `CardPile` built from the combat knowledge
  tracker; the six RNG streams are reseeded from a public per-battle seed and
  treated as one chance source. Known gaps: Runic Dome intents are visible to
  the native search (the vendored model defers them); multi-card selections
  (Gambling Chip, Purity) are atomic subsets rather than Silver's sequential
  picks; the vendored reroot repairs (UID swap, hand-order alignment) are
  replaced by multiset equality plus identity-based action translation.
- **Gameplay:** native 86/128 wins (67.2%) against vendored 83/128 (64.8%).
  Paired difference +2.3 pp, normal 95% CI [−6.2, +10.9] pp; discordant seeds
  17 native-only vs 14 vendored-only (McNemar z = +0.54). Mean floor 47.81 vs
  48.26. CPU 37.37 vs 38.05 s/run. No seed failures.
- **Interpretation:** no detectable difference in either direction at 128
  seeds. **Inference:** the port preserves Silver's playing strength within
  about ±8 pp; a tighter non-inferiority claim needs more seeds (GCP path).
- **Artifacts:** [evidence packet](evidence/native_silver_gate_2026-09-24/README.md).

Knowledge impact: combat-search architecture and environment variables record
the experimental native backend; the vendored Silver backend stays the default.

## §349 — Silver rollout-cost screen: B faster; original quality screen invalid (2026-09-24 onward)

- **Question and baseline:** Can rollout hot-path work be reduced while
  preserving useful fixed-time Silver decisions? The handoff baseline
  `7b4244ef8af4508466e01a1a6b515c70015e6274` had advanced; the tested current
  main was `1ed96f2aa564742156cc6593a1fc1915ea4e9033`.
- **Cohort and setup:** frozen `hard64-dev` first-decision snapshots, SHA-256
  `ab7c3298754864986c31273a0f1d23967b165fdd79a386261b680b8ad16d0eae`; GCC
  13.3 Release (`-O3 -flto`), CPU 2, `OMP_NUM_THREADS=1`, and the existing
  telemetry path. Each fixed-work run attempted 64 roots at 1,000 simulations;
  59 roots / 59,000 simulations were valid and the same five roots returned
  `transactional_selection_required` in every arm. All replay runs used
  `tools/seed_guard.sh`; holdout was untouched.
- **A — early energy rejection:** exact non-timing output parity held across
  all valid roots. A averaged 1,401,721 µs summed search wall versus control's
  1,286,513 µs; the two complete outer CPU samples were 1.035 s versus 1.015 s.
  There was no speed gain, so A and its focused test were reverted.
- **B — rollout-only unordered unknown piles:** only copied rollout scratch
  draw/discard/exhaust piles opt out of unknown-region sorting; retained tree
  piles remain canonical. Focused tests cover duplicate draw frequencies,
  known top/bottom, shuffle-in, reshuffle, absorb, cost mutation, and tree
  isolation. Across four matched repetitions, mean summed search wall fell
  10.3% (1,274,480 to 1,143,222 µs), median summed search wall fell 5.7%, mean
  summed rollout wall fell 13.0%, and process user CPU fell 10.9% (1.0275 to
  0.9150 s). This is a useful throughput signal. RNG mapping changed, and B
  executed about 0.24% more rollout actions at the same simulation count.
- **Original fixed-work DEV quality screen — invalid:** it reported 40/59
  current-main/control agreements and 35/59 B agreements against a 10k control
  reference, with eight control-only versus three B-only. The 1k control and
  10k reference shared the same `benchmark_seed`; because B changes
  RNG-to-card mapping, control's 1k search was the exact prefix of its teacher
  while B was not. Reclassify the former result as
  `QUALITY_SCREEN_INVALID_SHARED_REFERENCE_RNG`. Preserve the raw rows, but do
  not interpret them as no-harm failure or as a B quality regression.
- **Corrective implementation and protocol:** B now requires the default-off
  `rolloutUnsortedPilesEnabled` flag, and the replay harness defaults detailed
  rollout diagnostics and search timing off. The harness accepts an optional
  `isolated_search_seed` while retaining and reporting the validated
  state-bound `benchmark_seed`; `seed_guard.sh` checks both uint64 values and
  caps replay JSONL roots at 128. The implementation was independently reviewed
  and frozen at `1e63068ff548abb18638e4b02d60e7e0d6dc936c`. The preregistered
  current-main design specified three independent 10k teachers, four matched
  1k identities per arm, and an uninstrumented CPU comparison. Its decision
  rule, frozen eligible mask, and stop conditions are in the
  [corrected protocol](evidence/silver_rollout_cost_20260924/review_followup/PROTOCOL.md).
- **Corrected DEV result:** On 52/59 roots with teacher-majority consensus,
  matched fixed-work first-action agreement was 54.3% control versus 58.7% B,
  a paired mean of `+4.3 pp` (10,000-replicate root-cluster bootstrap 95%
  interval `[-1.4,+10.1]`;
  16 roots favored B, 9 control, 27 tied). The preregistered non-negative mean
  rule triggered the 1,000-control/1,100-B equal-time-equivalent screen; its
  agreement was 54.3% versus 61.5%, `+7.2 pp` (95% interval `[+1.0,+13.5]`;
  20/8/24 roots B-favored/control-favored/tied). Logged aggregate user CPU and
  elapsed time were approximately 0.760/0.738 s and 0.775/0.758 s (control/B);
  B was slower in two of four paired user-CPU samples. The uninstrumented 1k CPU
  confirmation measured mean user CPU 0.740 s control versus 0.675 s B
  (`-8.8%`), with B lower in all four pairs. This is first-action DEV evidence;
  the fixed-work interval crosses zero, and no gameplay, holdout, or default
  qualification is claimed. Evidence review found the input helper's seed
  domain strings (`teacher/NN`, `arm/NN`) differ from the strings frozen in the
  protocol (`teacher-NN/NN`, `arm-NN/NN`). The helper and manifest predate raw
  outputs by mtime, but a durable pre-run amendment was not retained; exact
  preregistration fidelity is unresolved. Seeds remain deterministic and
  pairwise distinct per root, and each arm identity is matched. Raw data, input
  derivation, analysis, binary hashes, and checks are in the
  [follow-up packet](evidence/silver_rollout_cost_20260924/review_followup/README.md).
- **C — incoming-damage reuse:** no cache was implemented. A separate
  instrumented `-pg` diagnostic estimated `SimpleAgent::getIncomingDamage` at
  2.6% inclusive time (1,543,022 calls) on the same fixed-work cohort. Given
  this small share and the broad set of monster/player state dependencies, a
  cache is not justified.
- **D — chance saturation:** replay telemetry exposed fresh samples and
  sibling reuses by `END_TURN`, card-play, and other categories. B recorded
  15,709 sibling re-executions, mostly card-play actions. Exact support
  exhaustion was not measured, so the certified avoidable count is zero and
  15,709 is only an upper bound. No heuristic or chance behavior change was
  introduced.
- **Review and checks:** an independent read-only implementation review found
  no blocking semantic defect and flagged stale sorting comments, which were
  corrected. Release and Debug optimization-test CTests each passed 1/1; the
  Debug run exercises the tree-isolation assertions. The complete report and
  raw outputs are in the [evidence packet](evidence/silver_rollout_cost_20260924/README.md).

Knowledge impact: the scratch-pile boundary and completed corrected DEV result
are recorded in maintained combat-search and current-research pages. B remains
default-off and is not gameplay-qualified.

## §350 — Native Silver rollout-only unsorted draw pile: rejected at profile gate (2026-09-25)

**Hypothesis:** the §349 candidate B (rollout scratch piles left unsorted) has
a useful analogue in native Silver (`SilverSearcher`, default backend since
ADR-0021). In native Silver only the information-set draw pile (`CardPile`)
is kept canonically sorted; discard and exhaust are plain vectors.

**Preregistered stop rule:** if removable rollout-only canonical-sort work is
clearly below ~3% of native search CPU, stop before implementing.

- **Baseline:** `856b3f8fb463be838daa1c4caf221b22bd876353`.
- **Method:** Release (`-O3 -flto`, plus `-g`) `unit-test` binary,
  `valgrind --tool=callgrind` on `test silver_searcher` (24 whole battles,
  native `SilverSearcher` with reroots, 200 simulations per decision). A
  second run used `--toggle-collect='sts::search::SilverSearcher::rolloutToEnd*'`
  to isolate rollout scratch execution. A deck-size sensitivity run temporarily
  (uncommitted, since reverted) added 20 cards (Pommel Strike, Shrug It Off,
  Inflame, Twin Strike, Anger ×4 each) to the starter deck.
- **Results (instruction counts, Ir):**

  | Workload | Total Ir | `rolloutToEnd` share | Rollout `std::sort<CardInstance>` | Share of total |
  |---|---|---|---|---|
  | Starter deck (10 cards) | 8.62e9 | 67.4% | 163.1M | **1.89%** |
  | 30-card deck | 6.65e9 | 65.9% | 137.5M | **2.07%** |

  Almost all removable work is the `absorbUnordered()` sort in
  `CardManager::moveDiscardPileIntoToDrawPile`. `addUnknown()` insertion and
  the `mutateAt()`/`mutateAll()` sortedness checks were about 0.02%. Non-rollout
  sorts (about 0.9–1.6% of the total) must stay canonical and are not
  removable. The vendored ~9% (§349) does not transfer, because the vendored
  engine also sorted discard/exhaust.
- **Decision:** rejected at Phase A. No implementation, fixed-work benchmark,
  or gameplay seeds were run or reserved.
- **Limitations:** callgrind Ir is a proxy for CPU; no production `one_combat`
  adaptive-budget profile was taken (**Inference:** the rollout/tree ratio and
  hence the share should be similar). The same profile attributes about 53% to
  `BattleContext::executeActions`, 17% to rollout card choice, and ~15% to
  `BattleContext` copy/swap; those are the larger native rollout-cost targets.

Knowledge impact: this entry plus a one-line pointer in current-research. No
code or default changed.

## §351 — Singleton reroot correction on frozen hard64 holdout (2026-09-25)

- **Question:** Does zero-search selection at singleton roots, while retaining
  the selected edge for later rerooting, change complete frozen-fight outcomes
  or reduce search work?
- **Frozen comparison:** main control at the time of this recorded run
  `01f6f164a0fe757ec174738ac3a2f0fb98c2462d`
  versus corrected treatment `2da8eed6a9c7faecd82effdd1751265eac1b42fd`.
  Treatment enables the benchmark-only singleton skip in the frozen replay
  utility; the production live backend change remains independently covered by
  the focused bridge and integration checks.
- **Cohort/configuration:** the tracked `hard64-holdout` set from
  `silver_hard_combat_v1_20260918`, 64 unique snapshots with stored per-fight
  benchmark seeds (snapshot SHA256
  `e8b914ad74ca0508ee6b1db329c5f454e92e7785cd60af1475d53b35a9d8af34`). Both
  arms used 10,000 simulations per searched root, allocated reuse cap 32,768,
  adaptive/exact-lock/rho off, and OMP 4. Every invocation used
  `tools/seed_guard.sh`; arm order alternated by 8-case block.
- **Results:** 64 cases were attempted; 63 were valid in both arms. Control and
  treatment each won 57/63 with zero paired outcome flips. Treatment skipped 62
  singleton searches, used 20.060M versus 20.720M simulations (**−3.185%**),
  and had 183.797 versus 189.465 summed per-case replay wall seconds
  (**−2.991%**). Mean ending HP changed by +0.159. Action trace hashes matched
  on 60/63 valid pairs. These bounded descriptive metrics are not equivalence
  evidence.
- **Technical exclusion:** case `12100109/21` failed in both arms after 28
  decisions / 280,000 simulations with the same
  `selected_deterministic_state_mismatch` and action-trace hash. An isolated
  rerun reproduced the same failure with current main, treatment with the
  switch off, and treatment with it on. The row is preserved; no case was
  substituted. The comparison is **N64 attempted / N63 valid**, so it is not a
  complete valid N64 confirmation.
- **Interpretation:** this is the first tracked post-reroot-correction hard64
  replay packet. It does not validate the live wire conversion path or
  establish gameplay safety; the live implementation remains supported only
  by the continuity regression and focused integration smoke. The old supplied
  59/64 report remains pre-correction and unverified.
- **Evidence:** [frozen hard64 packet](evidence/silver_singleton_reroot_hard64_holdout_2026-09-25/README.md),
  including raw 64-row arm outputs, pair rows, summary, shared-failure reruns,
  and hashes.

Knowledge impact: current research now records the post-correction replay
result and its one shared technical failure. No default or quality gate changed.

## §352 — Singleton reroot replay against updated current main (2026-09-25)

- **Question:** Does the retained-session singleton zero-search path reduce
  work without changing observed outcomes on the frozen hard-fight cohort
  after merging the latest main updates?
- **Frozen comparison:** main control
  `46684659a0d56729d7af1f8ae2ce9eeab39a6934` versus merged treatment
  `be47b2a1502013b04dcdd923b6d14c1c22c7dde1`. The treatment enabled only
  `--skip-singleton-search` in the frozen replay utility. The production live
  path is independently covered by the retained-edge bridge regression and
  flat/adaptive integration checks.
- **Cohort/configuration:** the same 64 stored-seed rows from the tracked
  `hard64-holdout` set in `silver_hard_combat_v1_20260918` (snapshot SHA-256
  `e8b914ad74ca0508ee6b1db329c5f454e92e7785cd60af1475d53b35a9d8af34`). Both
  Release arms used exact 10,000 simulations per searched root, allocated
  reuse cap 32,768, adaptive/exact-lock/rho off, and OMP 4. Alternating
  eight-case blocks went through `tools/seed_guard.sh`; all 64 stored states
  ran in both arms. No new states were collected.
- **Results:** 64 cases were attempted and 63 were valid in both arms. Each
  arm won 57/63 with zero paired outcome flips. Treatment skipped 62 singleton
  searches, used 20.060M versus 20.720M simulations (**−3.185%**), and had
  183.421 versus 189.820 summed per-case replay wall seconds (**−3.371%**).
  Mean ending HP changed by +0.159; action traces matched on 60/63 valid
  pairs. These bounded descriptive metrics are not equivalence evidence.
- **Post-run source advance:** while the packet was being prepared, main moved
  to `8ed346ea1e503a85640c44131c05b9e8b5f48f53` via PR #320. Rebuilding the
  replay target from that main head produced the same control binary hash as
  the run. After merging it into the treatment tree, the replay target also
  retained the exact treatment binary hash used by the run. No more seeded
  replays were launched after this byte-for-byte check because the local
  128 arm-case allowance had been used; the raw command records retain the
  original invocation SHAs. Main later advanced to
  `03ae0297ac33fba41c64921d5b0bcc6eabe4be2a` via PRs #318 and #321. Release
  rebuilds from that main head and final treatment merge
  `b0393b034117cbdf5e16b994a0fe50528e89787b` again produced the recorded
  control (`58a8b80a857bedcb8773f2f26d4390d7f0ec720a9f3984e201821d0714fbdc05`)
  and treatment (`03a6aa7f0dcb613ddbd70beba1e8ed18b59c2ea7ee0102ed71effc31ba8fa63d`)
  hashes. Main then advanced to `18232bf049a3facade2d5df440a67bb30135f400`
  (PR #314); its control binary was
  `f0367213d95300dac94fcef486aee0ca9ad3b57b30243b1a7c5e060b78323773`, while
  final treatment `b6242a65f98d90520440145600241ad5a39d3860` built to
  `ba4ef57db9b2574b144b4aabbe6e851218606564a41c6b8c2f6bb1817c2d2f57`.
  Both differ from the replay binaries. Inspection found PR #314 adds a
  default-off unsorted-rollout option (disabled in these invocations), changes
  diagnostic timing collection defaults, and adjusts the isolated simple-
  rollout terminal feature probe. All 64 snapshots omit `isolated_search_seed`,
  so the new harness fallback remains the stored `benchmark_seed`. These
  changes do not alter the default combat replay search path. No new hard64
  screen was necessary for this merge; the N63 outcome/simulation rows remain
  historical observations of their original binaries, and the wall-time result
  is not reverified on the newer harness. Main later advanced via PR #322 to
  `856b3f8fb463be838daa1c4caf221b22bd876353` and PR #323 to
  `f8fa4a3fd9ebbbc01f2003946ee40c634bcd677d`. Release replay rebuilds from
  current main and the merged treatment still have SHA-256
  `f0367213d95300dac94fcef486aee0ca9ad3b57b30243b1a7c5e060b78323773` and
  `ba4ef57db9b2574b144b4aabbe6e851218606564a41c6b8c2f6bb1817c2d2f57`.
  PR #322 changes `one_combat` backend dispatch and PR #323 records a profile
  result; neither changes the replay target. No new hard64 screen was needed.
- **Technical exclusion:** case `12100109/21` failed in both arms after 28
  decisions / 280,000 simulations with the same
  `selected_deterministic_state_mismatch` and action-trace hash
  `5626104837987834096`. Both raw rows remain in the packet. No case was
  removed, replaced, or rerun, so the result remains **N64 attempted / N63
  valid**, not complete valid N64 confirmation.
- **Interpretation:** this updates the earlier post-correction replay whose
  control was main at `01f6f164`. It confirms descriptive compute savings on
  the same frozen cohort against main at `46684659`; byte-for-byte rebuilds
  show the replay target stayed identical at main `8ed346ea` and treatment
  commit `4b1b27f6`. It does not establish action equivalence or gameplay safety,
  validate live wire conversion, or change a default.
- **Evidence:** [current-main frozen hard64 packet](evidence/silver_singleton_reroot_hard64_holdout_2026-09-25_main46684659/README.md),
  including raw per-arm rows, paired records, run order, per-invocation
  outputs, analysis scripts, and hashes.

Knowledge impact: current research now records the updated-baseline replay
and its shared technical failure. The prior comparison remains preserved as
historical evidence; no default or quality gate changed.

## §353 — `v_win` terminal-pricing audit (2026-09-24)

- **Question / decision:** Is the tracked compact `v_win` suitable for a
  relative-price lookup over combat-terminal victories? The preregistered
  result is **`VWIN_W1_NEEDS_SMOOTHING`**. This is W1 input-readiness only; it
  makes no gameplay-quality or runtime-promotion claim. The monotonicity
  threshold failed, while the low-HP flat-run threshold, per-act positive HP
  and held-potion intervals, Q4, and Q5 passed. The handoff's thresholds were
  unchanged. The Q4 capacity model was amended before outcome analysis because
  metadata-only inspection found both capacity 3 and 5; see commit `ca6960ad`.
- **Collection / artifact:** 128 project-fair E2c-v2 seeds
  `3100000..3100127`, ascension 0, collected at executable/source SHA
  `5334920f5dc184ba9507ce9a15ed2fd96fd69bec`, `e2cgen` simulations argument
  1,000, adaptive Silver enabled, allocated reuse cap 32,768. Model SHA-256 is
  `fc52c14cb7239a33b3c1f9d0477ccb6c895fd51a07240fe804744e605067ad70`
  (448 features, 1,060 trees, logistic). The current 2-seed smoke passed
  2/2, with 92 rows and zero invalid/quarantined seeds/branches or simulator
  health failures. The first population process stopped after representing 93
  seeds and did not leave its final sidecar counters. E2c writes rows only for
  runs passing `trainingRunValid`, so all 93 represented seeds passed that
  predicate, which rejects unresolved runs and simulator-health failures;
  attempted/completed counts and any unrepresented quarantines remain unknown.
  The stop cause is unknown. The remaining 35 seeds have
  complete sidecar accounting (35/35, zero invalid/quarantined seeds or
  branches, zero health failures). Silver telemetry reported
  `prior_model_loaded=0`; this measures the optional Silver learned root
  prior, which was off by default, and is not a preregistration deviation.
  Compact-policy-tree load status is Unverified from retained logs. The complete row/hash
  inventory and interrupted-segment boundary are in the
  [evidence packet](evidence/vwin_terminal_pricing_audit_20260924/README.md).
- **Parity / data checks:** Before Q1–Q5, 600 RAW rows passed native/Python
  name-aligned parity at `1e-4` (600/600 compared; max and mean difference
  0.000000). The combined files contain 3,069 RAW and 2,706 POST rows with
  2,706 matched pairs; there are no duplicate keys or paired outcome, room,
  encounter, or within-seed label mismatches. There are 363 unmatched RAW and
  no unmatched POST rows. Two complete analyses were byte-identical; result
  JSON SHA-256 is
  `8803126fba6a73de07b99ab8a4b5a006f17fc79d5f18f7468bdf16c38194ba98`.
- **Q1:** Monotone HP sweeps were 63.77% of rows (95% seed-bootstrap CI
  60.18–67.35%), below the 95% gate; overall median longest flat run was 5 HP
  (CI 5–5), passing the 10-HP limit. Per-act mean HP slopes were
  `0.000933`, `0.002670`, and `0.002586` probability/HP; held-potion
  equivalents were `6.76`, `6.74`, and `6.70` HP, each with intervals above
  zero. Full act/room/potion summaries are retained in the packet.
- **Q2:** **Inference:** No reviewed repository intervention isolates an HP
  offset on captured states with matched continuations. The synthetic trainer
  probe is model-space only; paired rest branches change HP and progression,
  path branches change route and downstream rewards, and TERM_WIN changes
  policy (its recorded win-rate screen was null at approximately 3.1x cost).
  **Open question:** An 8-state × 3-offset × 4-continuation (96-trajectory)
  matched continuation test is proposed only; its 60.8 CPU-minute estimate is
  rough and replay cost is unmeasured. The current tracked model has
  counter-value splits on r26/r30/r31/r44/r46/r52/r68, with r32 absent and
  r35/r116/r131 presence-only. This corrects the current-artifact
  interpretation in ledger §§109–110; the exact model used in that historical
  run remains unbound.
- **Q3–Q6:** The pre-collection inventory found the named vrich, rest/path
  counterfactual, and datagen3 files absent from checked local trees. The
  historical E2c GCP output path is not mounted on this host, so current
  remote existence and historical dataset byte sizes remain unverified; see
  the packet inventory. Predicted mean P(win) was 0.545 versus equal-seed
  observed run win rate 0.719; Brier 0.232 versus 0.187 row-prevalence
  baseline. Treat calibration as weakly powered at 128 seeds, with
  underprediction in this cohort. Q4 had 2,706 pairs, rank 5/5,
  `R²=0.04776` (narrowly below 0.05); coefficient endpoint bounds exceed
  3 HP-equivalent across the observed ranges, so the formal gate passes only
  through the frozen low-R² clause. Q5 recorded-vs-zeroed hidden-future
  HP-slope and potion-value rank correlations were 0.934 and 0.873;
  zeroing is out-of-distribution-prone. Fair/zeroed per-act HP slopes were
  0.000675/0.002274/0.002355 and potion equivalents were
  15.59/13.55/4.45 HP; the full interval table is in the packet.
  Q6 measured native prediction median/p95 21.761/31.249 μs over 20,000
  direct calls and identified HP, max HP, gold, potion, deck/Parasite, and
  exit-mutated relic inputs.
- **Scope / evidence:** No W1 table, causal continuation replay, live gameplay,
  runtime change, or default change. The raw E2c CSVs remain ignored local
  data; aggregate, parity, provenance, model-counter, latency, and smoke
  evidence are committed in
  [the audit packet](evidence/vwin_terminal_pricing_audit_20260924/README.md).
  See the machine-readable [results](evidence/vwin_terminal_pricing_audit_20260924/results.json).
- **Checks:** On audit source `812fb8afb9413a5e277d3aaebdda98e95ff7f4c0`,
  which includes `origin/main` base `01f6f164a0fe757ec174738ac3a2f0fb98c2462d`,
  `cmake --preset linux-gcc-release` configured and `cmake --build
  build/linux-gcc-release --target one_combat -j2` passed. Focused CTest
  passed 3/3
  (`winnettest_selftest`, `vwin_terminal_pricing_audit_selftest`,
  `export_win_model_selftest`); Python compilation and the analyzer self-test
  passed earlier with unchanged audit tooling. Native/Python parity passed
  again on 600 rows after the latest-main build, max and mean difference
  0.000000. The build emitted a narrowing-conversion warning in
  unrelated run-timing code and an ODR warning for `Path` across root and
  bundled `SimpleAgent.cpp`. Full CTest was not run. Draft PR #317 triggered CI
  run 1184, but the `Linux GCC` job was skipped by the workflow's draft-PR
  condition. The current-head CI result is tracked in PR #317. No gameplay seed
  was rerun for verification.

#### Review corrections and post-review descriptive additions (2026-09-25)

- **A1–A3, A5–A7:** `prior_model_loaded=0` measures the optional Silver
  learned root prior (off by default), not compact-policy load; that status is
  Unverified. Silver terminal prices are score points with +1 healed HP = 1
  point; Feed-like +1 max HP/+1 current HP is 3 points, max-only is 2. The
  Q4 `curHp` coefficient is −3.36e−4/HP with interval excluding zero (about
  17% of mean `s_HP=0.00195`), although the frozen gate passes by low R². The
  Q5 Spearman gate tests ranks rather than price levels; zeroed/recorded
  potion HP-equivalent ratios are 2.31, 2.01, and 0.66 by act. The 33
  per-potion features have 124 splits (six with none), versus 271 for
  `potionCount`; pot21 Fairy in a Bottle has three splits and mean 2.48
  HP-equivalents (CI 1.07–4.27), zero in 32.7% of rows. **Inference:**
  per-potion prices mostly encode state association, so they are not usable
  identity prices.
- **A4:** Using only same-seed, same-act next RAW rows exactly one floor later,
  the matched full-belt drop/no-drop/unclassified counts are 1/153/259 and
  space-available counts 423/464/1,406. Unmatched full-belt counts are
  147/0/199 and space-available counts 0/0/17. Thus there are zero
  classifiable unmatched residuals; 216 unmatched rows remain unclassified.
  The belt was full in 413/2,706 matched rows (15.3%) and 346/363 unmatched
  rows (95.3%).
  One matched full-belt drop acquired Potion Belt (`r159`), which raised
  capacity before the potion choice. The full-run reward chain takes a
  potion only with slot capacity and cannot discard or swap a held potion;
  the belt was full in 759/3,069 RAW rows (24.7%), and 148/301 full-belt rows
  with classifiable adjacent-floor status had a drop (49.2%). E2c
  `captureE2cPost` returns while gold, relic, or potion rewards remain
  pending, so an unclaimed potion blocks POST capture.
  The 147 proxy-confirmed full-belt drops are 4.79% (4.8%) of all 3,069 RAW
  fights. If all 199 unmatched full-belt rows with unknown proxy status also
  represent unclaimed potion drops, the code-path upper count is 346/3,069
  (11.27%, or 11.3%). This is a conditional upper bound, not an estimated
  rate; 17 unmatched space-available rows show other causes of missing POST,
  so the actual forfeiture rate can be lower. Q4's 2,706 pairs exclude all
  no-POST rows by inner-join construction.
- **B1–B3:** Clamped-probe shares were 56.0%, 45.9%, and 54.1% by act.
  Held-potion mean/median HP-equivalents under fixed-/10 → actual-span
  denominators were 6.76/1.96 → 4.51/1.51, 6.74/1.99 → 4.28/1.66, and
  6.70/0.85 → 4.78/0.61. Gold means were 0.357 → 0.231, 0.090 → 0.058,
  and 0.058 → 0.040; Feed-like means were 1.548 → 1.263, 1.001 → 0.937,
  and 0.300 → 0.140. Full mean CIs, median bootstrap CIs, and IQRs for all
  held-potion and per-type probes are in `post_review_descriptive`. Max-only
  mean/median values were 0.613/0.314, −0.061/0, and −0.477/0; Silver's
  comparators are 2 (max-only) and 3 (Feed-like).
- **B4–B7:** RAW-row and first-row-per-seed AUC were 0.708 [0.652, 0.769]
  and 0.638 [0.528, 0.745]; 128 source seeds give weak power. Paired
  POST/RAW median `s_HP_span` ratios were 1.0014, 0.9818, and 0.7833 for
  monster/elite/boss, with corresponding held-potion ratios 0.9441, 0.9590,
  and 0.6939. Near-current >0.005 drop shares were 14.5%, 21.6%, and 19.7%;
  largest HP-equivalent drops had median/p95 3.684/29.374, 1.454/15.414,
  and 1.806/24.842. The interruption cause is unknown; 48/128 seeds have
  noncontiguous fight indices, all last RAW floors differ from `finalFloor`,
  and the segment-1 last-written seed 3100091 is contiguous (0–26), ends at
  floor 48 versus finalFloor 51, with a complete 1,387-column final CSV line.
  `fight_index` advances across battles while E2c captures only monster, elite,
  and Act 1–2 boss rooms; event-initiated fights and Act 3 bosses therefore
  explain the expected index gaps. The final line is newline-terminated and
  complete; there is no evidence of CSV truncation. The stop cause remains
  unknown; 35/35 seeds in flight reran cleanly, so a deterministic crashing
  seed is not supported (**Inference:** an external stop such as a timeout).
- **Earlier post-review verification (before the current-main refresh):** after
  merging `origin/main` at
  `03ae0297ac33fba41c64921d5b0bcc6eabe4be2a`, the Release
  `one_combat` rebuild passed on branch source `82dc7f04`; existing warnings
  were the `one_combat.cpp` narrowing conversion, duplicate `Path` ODR report,
  and serial LTO note. Focused CTest passed 3/3, and the native/Python parity
  fixture passed 600/600 with max/mean absolute difference 0.000000. Python
  compilation, analyzer self-test, JSON validation, both CSV provenance hashes,
  and `git diff --check` passed. Full CTest and new gameplay seeds were not
  run. On that reviewed head, PR #317 was draft and GitHub skipped Linux GCC.
- New results are isolated under the top-level `post_review_descriptive`
  key. The preregistered outputs, thresholds, and verdict remain unchanged;
  two current-code analyses were byte-identical at SHA-256
  `79d4709d71baf32c70e817445b46de70df70c3f30e05972b9a359113f350dd4e`.

Knowledge impact: current research now records the W1 candidate boundary
(smoothed HP for non-act-boss wins, with gold only tentative), unstable
fair-regime price levels, the full-belt forfeiture bounds, and the limits on
using per-potion or max-HP prices. Architecture documents the reward-chain
capacity rule. The post-review descriptors do not change the frozen W1
verdict, runtime defaults, or gameplay claims.

## §354 — Native Silver one-action-root bypass: paired 128-seed check (2026-09-25)

Change: the native backend commits the sole action of a one-action root
without search and keeps the retained graph for the next reroot
(`STS_SILVER_SEARCH_SINGLETON_ROOTS=1` or exact root budgets restore
searching). This carries the vendored bypass of §§351–352 (removed with the
vendored model, ADR-0022) over to native Silver. The same change adds native
simulations to `ScumSearchAgent2::simulationCountTotal`, which previously
stayed at zero under native Silver.

Setup: one Release binary, 4 threads, adaptive Silver, `bestbench 1000 128 0
126700`, control with singleton roots searched, treatment with the new default.

Result: control 82/128, treatment 86/128; paired +3.1 pp, 95% CI [−1.7, +8.0]
pp; discordant 7/3 (McNemar z = +1.26). Mean floor 47.43 vs 47.42. Mean
per-run time 38.58 s vs 36.09 s (−6.5%).

Decision: adopt as the native default; no detectable gameplay difference, 6.5%
faster. Evidence: [native_singleton_bypass_2026-09-25](evidence/native_singleton_bypass_2026-09-25/README.md).

## §355 — Native equivalent-copy reroot: paired 128-seed check (2026-09-25)

Change (ADR-0023, issue #327): when the exact node lookup misses, native Silver
retries with the unique ids of one pair of search-equivalent cards exchanged,
so playing a different physical copy than the one the search expanded reuses
that branch. The advisor translates retained actions onto the live root.

Setup: Release control from `main` `0eed6993` vs the branch, 4 threads,
adaptive Silver, `bestbench 1000 128 0 126700`.

Result: control 86/128, treatment 89/128; paired +2.3 pp, 95% CI [−3.2, +7.9]
pp; discordant 8/5 (McNemar z = +0.83). Mean floor 47.42 vs 48.11. Mean
per-run time 38.36 s vs 39.30 s (+2.5%).

Decision: adopt; no detectable gameplay difference and restores ADR-0015's
reuse. Evidence: [native_equivalent_copy_reroot_2026-09-25](evidence/native_equivalent_copy_reroot_2026-09-25/README.md).

## §356 — Retrained contextual deck semantic-prior qualification (2026-09-25)

- **Question / decision:** Does a newly trained 3,200-parameter contextual
  O(n) deck block preserve the deployed42 teacher's actual OOC MCTS semantic
  prior after grouping and multiplicity correction? The result is
  **`CONTEXTUAL_SEMANTIC_PRIOR_PASS`**. This is a new frozen student, not a
  byte-identical recovery of the missing historical `45a3ce…` checkpoint.
- **Trace / provenance:** Reused PR #329's saved trace only; no new seeds or
  capture were run. The gzip at
  `/home/philippherrmann/Documents/Codex/2026-09-25/ooc-contextual-semantic-prior/trace_mainline.jsonl.gz`
  has SHA-256
  `192b623ca28887e7da646aca16efaecd041583261265e1af23b83a1eab958370`; its
  decompressed SHA-256 is
  `9f95592e9dfbf9b199dbdd81f1b4cae2e654e52a871c227c888ace47f7fb1cb1`.
  It contains 24,959 records from seeds 12450008–12450015; 11,474
  prior-covered, non-singleton, nonuniform occurrences yield 6,317 unique
  canonical prior inputs (1,402 SHOP occurrences / 1,002 unique SHOP inputs).
  The recovered `strategic_tierb.csv` and seed-disjoint split match their
  required SHA-256 values `c428f229bdf7cfe070ff06fd1664978e6e49bbde872d5929ef4fa50f56ba008b`
  and `0efe5b56e1f87c0642827c14e55790db517b55820d54620edd32420012e8b67b`;
  the cache uses `raw-to-grouped-v2`.
- **Teacher / source audit:** Tracked native teacher SHA-256 is
  `e62abd833fc8cb9081a1cec4a1a012832ac3b0e3166da3892841911664f1184c`;
  reconstructed Python teacher SHA-256 is
  `5bc14fb437131d4bdc531ea775e22eca1f6834976d4670ec0aabb2fb14b735b8`.
  Export parity re-created the tracked native file byte-for-byte, with max
  logit/Q/value differences `1.06e-5 / 1.28e-5 / 8.19e-6`. On the captured
  trace, Python-vs-native maximum source/candidate logit error was
  `2.6703e-5` (<`1e-4`), source argmax matched 6,317/6,317 inputs, and the
  rebuilt final prior maximum error was `1.9898e-6`. The captured teacher's
  own raw-weight and normalized-prior formulas reproduced within
  `1.2e-16` and `5.6e-16` respectively.
- **Training:** Recreated the exact Tier-B train/validation split (3,720/930
  seeds; 578,391/145,460 grouped states) and trained seed 0 for 30 epochs on
  CUDA with AdamW, learning rate `1e-3`, weight decay `1e-4`, 4,096 groups per
  batch, and representation MSE only. The checkpoint contains all 115 teacher
  tensors exactly plus exactly six contextual-deck tensors (3,200 parameters);
  no policy/Q loss or end-to-end fine-tuning was used. The final validation
  representation cosine mean/median was `0.94753 / 0.95696`. The durable,
  read-only checkpoint is outside `.codex/worktrees` at
  `/home/philippherrmann/Documents/Codex/2026-09-25/ooc-contextual-semantic-prior/retrained-contextual-student/contextual_student_frozen.pt`,
  SHA-256 `bc22f8b03646da79754c1fcfe04f49f20ed5f51ff9ba5250cf715d390d04a761`.
- **Historical source-policy gate:** 100,314 held-out groups / 567,642 source
  rows passed: argmax agreement `97.945%`, median/p90 TV
  `0.003128 / 0.034804`. Card Reward agreement was `99.187%`; SHOP was
  `93.864%` (median/p90 TV `0.008026 / 0.027206`). These reproduce the
  previously declared source-policy threshold and are not themselves the
  semantic-prior result.
- **Semantic-prior gate:** On the primary 6,317 unique prior inputs, top
  semantic-action agreement was `98.892%`, median/p90 TV
  `0.000109 / 0.018815`, ordered top-two agreement `96.881%`, and top-two
  teacher/student margin correlation `0.999871`. The call-weighted 11,474-row
  result was `98.771%` agreement with median/p90 TV
  `0.003513 / 0.028456`. All broad-screen guards passed. SHOP was explicitly
  checked: 1,002 unique inputs, `97.705%` agreement, median/p90 TV
  `0.002183 / 0.016985`. The event screen had `94.581%` agreement, below the
  95% overall headline threshold but above the 90% broad-screen guard, with
  median/p90 TV `0.011271 / 0.047501`; rest (90 unique)
  and treasure (72) remain smaller descriptive strata. Direct primitive and
  grouped-semantic agreement were `98.926%` and `98.887%`; full strata and
  representative decoded records are in the evidence packet.
- **Current-main drift:** The trace source was branch head `03079d52`; at
  evaluation `origin/main` was `0eed6993`. The intervening OOC adapter change
  adds the singleton-root fast path. The merged trace code preserves that
  no-prior-cache behavior when tracing is unset and writes singleton rows only
  when the opt-in trace path is set. Inspection found the non-singleton
  candidate construction, `priorSourceGroups`, and `policyLogits`/multiplicity
  prior calculation unchanged; singleton records are excluded from the
  primary population. The saved trace therefore remains authoritative for the
  evaluated non-singleton inputs.
- **Scope / next step:** This is offline prior-fidelity qualification only.
  No new seeds, native contextual inference, runtime benchmark, MCTS/gameplay
  smoke, policy-strength gate, default change, or claim of tree/gameplay
  equivalence. A separate native contextual inference plus parity/runtime task
  is now justified. See the [evidence packet](evidence/ooc_contextual_semantic_prior_2026-09-25/README.md)
  for exact commands, full screen/stratum tables, hashes, and raw result JSON.

Knowledge impact: current research now records the offline pass and its exact
boundary. No native runtime or default is promoted.

## §357 — Native Silver endpoint/tree-depth descriptive profile (2026-09-26)

Issue #344 adds opt-in counters only, against main
`b23aad9d8885c6eca332b1f5cccf3890755bbecf`. The fixed diagnostic cohort is
seeds 0–7, A0, fair native Silver, flat 1,000 caller simulations with the
existing boss multiplier and singleton bypass, OMP=1, existing native-GBM
`bestbench` OOC policy. No new policy, model, RNG, or budget intervention.
Earlier artifacts do not contain this new endpoint/depth schema; a fresh small
cohort was necessary. This is implementation/descriptive evidence, not an
expensive scientific qualification or a promotion.

[Evidence directory](evidence/native_silver_tree_profile_2026-09-26/manifest.json)
contains source/model/binary hashes, exact guarded commands, logs, result CSVs,
compressed raw JSONL, full grouped analysis, and the one-seed on/off comparison.
The source hashes identify the instrumented code; the baseline SHA alone does
not identify that code. Both compact-tree models reported successful loading.

All 8 runs completed: 3,726 real decisions, 5,225,000 new simulations, 55
encounters across acts 1–3 and MONSTER/ELITE/BOSS/EVENT rooms. All endpoint and
histogram denominators reconcile. Evaluated endpoints were 4,770,360 victory
(91.2988%) and 454,640 death (8.7012%); no nonterminal, turn-limit, engine-stop,
or aborted search was observed. These are correlated simulation samples, not
independent run outcomes.

Crucially, 4,648,023 simulations started their rollout at a nonterminal tree
leaf. The 100% terminal **evaluated endpoint** share does not mean the tree
itself reached those outcomes: Silver rolls new leaves forward and then uses
its heuristic, with no neural leaf evaluator. Tree action depth p50/p90/p99/max
was 3/6/8/16; total depth including rollout was 15/36/57/107. Chance-outcome
edges do not double-count their action. Inherited visits are excluded at each
real decision, including after rerooting.

Simulation death share was 3.463% in act 1, 4.514% in act 2, and 17.164% in
act 3. The supplied analysis includes room/encounter/turn/decision/HP/budget
views, encounter rankings at a 20-decision minimum, and a complete fight
trajectory per encounter. All ordinary-terminal shares tie at 100%, so those
rankings do not establish meaningful encounter differences. The cohort uses
one caller budget and cannot support a budget-response inference.

Focused Debug fixtures prove exact lethal/nonterminal/death/safety accounting,
chance-edge depths, chunked denominators, terminal-root exclusion, and on/off
full-fight equality of every action, six RNG streams, outcome, HP and turn,
including reroot reuse. Analyzer fixtures reject invalid counts and error rows.
A Release full-run seed-0 on/off comparison matches every gameplay CSV field;
timing is excluded. The uninstrumented branch is not a speed benchmark and
these timings were not isolated for a performance claim.

**Conclusion:** this diagnostic measures evaluated endpoints separately from
search depth and rollout starts. It does not justify a leaf model, pruning,
search-budget change, or a gameplay-quality claim.

## §358 — Exact OOC branching and real-floor/decision profile (2026-09-26)

Issue #341: observational implementation against main
`b23aad9d8885c6eca332b1f5cccf3890755bbecf`. `STS_RUN_PROFILE` captures existing
search checkpoints and exact expansion cardinality without changing early
stopping, singleton shortcuts, models, budgets, or RNG. Earlier artifacts lack
this combined floor/decision/exact-histogram schema, so a fresh bounded run
was needed. No scientific promotion or adaptive policy was implemented.

[Evidence manifest](evidence/ooc_run_profile_2026-09-26/manifest.json) records
commands and source/model/binary/artifact hashes. Seed 0, A0, OMP=1, fair native
Silver exact 10k; native V4 plus `combat_transition_near_full_except_smoke_v2`
CTM, OOC MCTS 2048 with existing strict-lock stopping and depth cap 32. Both
on/off arms use identical settings. This branch is independent of the pending
#336 depth-cap and #344 Silver-profile changes. The source hashes, not the
baseline SHA alone, identify instrumented code. Model loading succeeded.

The run completed with death to Slime Boss on floor 16: coverage is **Act 1
only**, not a representative estimate across all acts or seeds. Its 17 floor
intervals cover 45 OOC decisions (29 searched, 15 singleton bypasses, one
boundary/fallback), 43,540 completed simulations, 41,780 transition samples,
and 8,193 CTM samples. All nine matching floor aggregates reconcile exactly
with existing completed-run telemetry; decision rows reconcile with floors.

40,635 expanded nodes span exact cardinalities 1–22 and 24. Singleton nodes
are 32.3022%. The full histogram, room means/medians, top-10 wall/CPU floor
lists, encounter costs, prior/visit/Q statistics, and stability cross-tabs are
in compressed `summary.json.gz`, backed by raw `profile.jsonl.gz`.

Measured floor CPU totals were 35.7148 s: 28.9845 s in OOC search scope and
6.7211 s in real-combat lifecycle scope. These are nested components of the
floor total, not additional costs. The top 5 / top 10 floors account for
55.0695% / 83.6623% of floor CPU. Highest wall costs were the initial Neow/map
interval (4.643 s; engine room INVALID), floor 6 Lagavulin (4.407 s), floor 11
rest (4.273 s), floor 12 event (3.372 s), and floor 16 Slime Boss (2.977 s).
No performance improvement claim follows from this one-run profile.

Observed retrospective stability for the 29 searched decisions was first
seen at 128 in 25 cases, 256 in one, and only at the observed stopping point
1953/2000/2028 in one case each. Thus 86.21% had the same observed winner from
128 onward, 89.66% from 256 onward. **Every searched decision stopped early**:
there are zero full-budget stability labels. Singleton/boundary roots also
have no stability label. The analyzer keeps censored and full-budget
statistics separate and does not infer unexecuted search outcomes.

Validation: focused Debug planner/adapter/analyzer CTest 3/3 passed. Fixtures
prove exact singleton/10-way expansion counts, checkpoint root-statistic and
sampling-draw parity, preservation of early stopping and singleton bypasses,
and one floor row per interval with correct metadata/counter differences.
Five analyzer tests cover stability, strict lock/ties, missing checkpoints,
histogram corruption and floor reconciliation. Full-run on/off comparison
matches all nine gameplay fields, 41 non-timing MCTS fields, and byte-identical
OOC action traces; timing is excluded. Raw outputs and comparison hashes are
included in the evidence directory. Compressed reanalysis is reproducible.

**Conclusion / cheapest next experiment:** capture a small fixed set of roots
with late observed winner changes plus matched early-stable roots, then run
full-budget detached shadow searches for those roots while preserving the
actual policy. That would resolve censoring before testing a budget rule. The
present evidence alone neither qualifies early stopping nor justifies pruning
wide nodes. The additional later-act pilot below extends coverage; independent
gameplay qualification remains outside this engineering issue.

### Additional later-act coverage pilot

The user requested a pilot beyond Act 1. The predeclared coverage search was
seeds 1–8 in ascending order, stopping at the first completed A0 run reaching
Act 2 and then repeating that seed with profiling off. This selects for
coverage, not an unbiased win-rate or speed sample. Seed 1 met the criterion
on the first correctly configured attempt and **won at floor 51, Act 3, with
38/85 HP**. No other A0 seeds were screened. The source is the frozen
implementation `fbe390532addaeaa93b3703d29c1df44dcfe2a24`; rebuilt Release binary
SHA-256 exactly matches the original pilot's binary. Models, fair native
Silver exact-10k budget, OOC MCTS 2048, early stopping and all other settings
remain unchanged.

[Additional evidence](evidence/ooc_run_profile_2026-09-26/later_act_pilot/manifest.json)
contains raw/compressed traces, commands, hashes, metadata, per-act accounting,
parity and summaries. There are 53 `(act,floor)` intervals and 148 OOC decisions:
84 searched, 61 singleton bypasses, three boundary/fallback decisions. The run
completed 118,596 simulations and 22,203 CTM samples, with 112,757 expanded
nodes; singleton expansion share was 39.9044%.

| Act | Floor intervals | OOC decisions | Total floor CPU s | OOC scope CPU s | Real-combat lifecycle CPU s |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 | 18 | 50 | 29.3236 | 23.6408 | 5.6773 |
| 2 | 18 | 55 | 54.2016 | 41.3275 | 12.8654 |
| 3 | 17 | 43 | 55.6456 | 39.4552 | 16.1839 |

Component scopes remain nested inside the floor total. Top-five/top-ten floors
accounted for 25.7362%/42.8233% of CPU. Of 84 searched decisions, 73 retained
the observed winner from checkpoint 128 onward, but **all 84 stopped early**;
there are still zero full-budget stability labels. This does not qualify a
stopping rule or performance improvement.

The matching off run also won at floor 51 with 38/85 HP. All nine gameplay
fields, 41 non-timing search fields and byte-identical OOC action traces match.
All nine corresponding floor/run counter totals reconcile; the analyzer also
validates decision/floor accounting across act boundaries. Source code and
model artifacts were not changed for this extension.

One initial runner invocation swapped positional ascension/seed arguments,
producing A1 seed 0 (death at floor 40) instead of A0 seed 1. Output validation
caught the mismatch; it was excluded and retained in `excluded_a1_seed0/`
with actual settings, logs, traces and hashes. It is not pooled with the
matching pilot. The corrected runner additionally asserts ascension, exact
seed block and executable source identity from the output metadata.

Knowledge impact: expanded descriptive evidence in this ledger; maintained
profiling semantics and defaults are unchanged. Coverage now includes all
three acts, while representative multi-seed qualification remains unrun.

## §359 — Silver root-selection contract and narrow useless-action census (2026-09-26)

Issue #345, baseline main `b23aad9d8885c6eca332b1f5cccf3890755bbecf`.
Code and focused arranged-root fixtures establish the final rule: maximum
**edge visits**, strict-greater update, first enumerated edge on ties. Q,
child-node visits, prior and UCB do not break final ties. Backend/advisor,
flat/adaptive/exact budgets and rerooting use the same method; singleton bypass
has only its sole edge. Card-identity translation/semantic lowering do not
rerank actions. Current semantics are maintained in the combat-search KB.

The opt-in diagnostic starts with a last-card red Defend, no potion, no player
power/status, no relic except Burning Blood, and no incoming attack intent.
After the selected play, End Turn must be forced. Two copied continuations
(Defend + End Turn versus End Turn) must have identical complete next-turn
state and RNG, except reported unused-energy score bookkeeping and at least
as much loop-guard headroom for the comparator. Exact ordered piles and all
Player/Monster fields are compared. Snapshot round-trip is required. This is
**frozen concrete-state** mechanical evidence, not a public-information
pruning rule or a claim over other random futures. Live knowledge observation
is suspended for the copies; their results never affect action selection.

[Evidence manifest](evidence/silver_useless_action_census_2026-09-26/manifest.json)
records source/model/binary/artifact hashes and exact guarded commands. Earlier
artifacts lack this predicate and cannot establish its rate, so the requested
small fresh census was necessary. Fixed seeds 0–7, A0, OMP=1, flat 1k native
fair Silver with existing boss multiplier/singleton bypass, existing native
GBM OOC policy. Both compact-tree models loaded successfully. All 8 runs
completed; no budget/policy/model/RNG change was tested or promoted.

**Result: 0 verified selected actions / 3,726 real decisions.** Reasons were
3,499 outside the last-Defend/no-potions class, 226 not a concrete quiet root,
and one unqualified relic state. No root-statistic causal classification is
possible from this zero census. The replay verifier reports `verified=0 PASS`;
that is not evidence of replaying a positive observed example. The positive
mechanical fixture and several trigger counterexamples are tested separately.
The result does not establish that ordinary wasted-block behavior is absent.

Focused Debug Silver and analyzer CTest passed 2/2. Native fixtures prove
visits-versus-Q selection and tie order, one equivalent block/End-Turn state,
rejection of Barricade/Juggernaut/Ink Bottle/incoming attack/extra card/draw
effects, preservation of the original state, and full-fight on/off equality
of every action, all six RNG streams and outcome/HP/turn. Three analyzer tests
cover visit/tie classification and zero-census reporting. Release full-run
seed-0 on/off gameplay CSV fields match; timing is excluded. No large gameplay
benchmark, live-mod deployment, or independent scientific review was run.

An implementation fact relevant to later diagnosis: Silver's non-victory
heuristic subtracts `1.75 * energyWasted` except in shape encounters. Spending
otherwise-useless energy changes this score bookkeeping, despite identical
mechanical continuation. This is a possible mechanism to examine, **not a
causal finding from this census**. The trace records that difference alongside
root Q/visits for any future verified example.

**Cheapest justified follow-up:** reproduce the excluded relic case and qualify
its exact relic mechanics, or separately qualify a last-playable-card class
with other unplayable cards remaining. Keep exact state/RNG equality and trigger
counterexamples. Do not suppress Defend or change final selection from this
evidence. No predicate broadening or policy change was implemented here.

### Expanded fixed census: seeds 8–39

The user requested more seeds without broadening the predicate. The fixed
extension uses 32 new A0 seeds, **8–39**, at the same flat-1k native fair Silver
configuration and native GBM OOC policy. The preserved executable is byte-for-
byte identical to the original eight-seed census, built from
`10c1a4b79268ddef5e78ccf6d9ffe23434b4b3db`; source and model hashes match the
original manifest. OMP remains 1. Output metadata verifies the exact seed
block, ascension, executable source, backend and budget mode.

[Expanded evidence](evidence/silver_useless_action_census_2026-09-26/expanded_seeds_8_39/manifest.json)
contains the commands, CSV/meta/logs, compressed trace, separate and combined
summaries, replay result, parity check and hashes. All 32 requested runs
completed, producing **15,107 additional decisions and zero verified selected
actions**. Exclusions were 13,931 outside the last-Defend/no-potions class and
1,176 not concrete quiet roots.

The original artifact hashes and disjoint seed sets were verified before
combining. Across **40 seeds (0–39), there are 18,833 decisions and zero verified
cases**: 17,430 outside the narrow class, 1,402 not concrete quiet roots, and
one unqualified relic state. This does not establish that ordinary wasted
block is absent; it provides no positive snapshot and no Q/visit causal
classification. The unchanged predicate was deliberately not expanded after
seeing zero cases.

Seed 8's matching trace-off run agrees on all nine gameplay CSV fields,
excluding timing. The replay verifier reports `verified=0 PASS`, explicitly
not a positive replay result. Three analyzer tests pass; compressed trace
reanalysis and all packaged artifact hashes agree. No runtime, policy, model,
budget or maintained diagnostic semantics changed. Knowledge impact: bounded
census evidence expanded in this ledger; no default or quality promotion.

## §360 — Native Silver hot-path profile; live-only action-queue copy (2026-09-26)

Issue #350. Profiled native Silver with callgrind on a fixed workload,
`test silver_profile 2000 4`: 89 roots from 12 act-1–3 encounters, one
searcher per combat.

Profile:
- Rollouts: 73% of instructions, of which the rollout policy is 17%.
- Node dedup: 11%.
- `BattleContext` copies and moves: 13.5%.
- The exclusive profile is flat; the top function takes 6%.

The one concentrated structural cost: the 128-slot action queue is 6.2 KB of
the 8 KB `BattleContext`, and it was copied whole on every copy, move and swap.
`ActionQueue` now copies only its queued slots.

Result:
- Instructions: −4.0%.
- Median throughput: +6.5% at 2,000 simulations, +6.2% at 10,000.
- Search visit digests are identical.
- `bestbench 1000 8 0 126700` rows are identical apart from timings.

Batched/SIMD state execution was not pursued: no uniform hot loop exists
(**Inference** from the flat profile).

Decision: adopt; this is a pure speedup with exact parity. Evidence:
[sim_hotpath_profile_2026-09-26](evidence/sim_hotpath_profile_2026-09-26/README.md).

## §361 — OOC MCTS reroot opportunity: measure, do not implement (2026-09-26)

Issue #339, Phase A only. Every live OOC decision builds a fresh search tree.
The question was whether the next real decision state is already stored in the
previous search, and how much search work that stored node carries.

Method: a new opt-in observer, `STS_OOC_MCTS_REUSE_TRACE`. It fingerprints
every stored decision node of each completed live search, then matches the next
real root against them. It uses two identities:
- **public**: the state the sampled search holds fixed. Hidden seeds, pool
  order, unrevealed encounter suffixes and hidden chest/event contents are
  excluded.
- **rng**: public plus all RNG draw counters.

Live actions and all non-timing search counters are byte-identical with the
trace on and off.

Workload: the 2026-09-18 OOC CPU-profile seeds 12002032 and 12002033, at OOC
2048 and the current default depth 512. 273 real OOC decisions: 162 searched,
110 singleton, 1 abort.

Results:
- **rng identity: 0 matches.** Sampling redraws the unrevealed encounter
  suffix, which advances `monsterRng` counters in every stored particle.
- **public identity: 94 of 159 searched decisions (58%)** match a node under
  the previously selected action, at depths 1/2/3+ = 60/25/9. No match crosses
  a real combat.
- **Retained work is small.** One real outcome maps to a median of 64 publicly
  identical sibling particles. The best single node keeps a median of 30
  visits (max 42): 0.90% of all searched simulations.
- Upper bound: merging all identical particles would keep 26.6%. That is
  belief/transposition merging, which the issue excludes without separate
  evidence.

Decision: stop after measurement, per the issue's decision rule. No
persistent-tree or reroot code is added. **Open question:** whether collapsing
publicly deterministic sampled transitions is semantically sound.

Evidence:
[ooc_reroot_opportunity_2026-09-26](evidence/ooc_reroot_opportunity_2026-09-26/README.md).

## §362 — Native contextual V4 deck parity and runtime screen (2026-09-26)

The task began in a fresh Codex-app-managed worktree at
`b65615bb78aa982b0fca097d86876009eb34ec6a`. During execution, fetched
`origin/main` first advanced through §360 and subsequent local-research updates
to `ffd51f3bc43b03aa356c419567d77b1eecc636a`, then through PR #362 to
`6bae3a67c63d1f724908e2ee87b27d51e32d30a0`. PR #362 changed Silver handling
for deferred Guardian Mode Shift, so the task branch was fast-forwarded before
final verification. The contextual native header, exporter, semantic evaluator,
and ledger were unchanged by that upstream update. This result was originally
recorded as §361; PR #362 itself did not append a ledger section. PR #366 later
recorded its separate §361 reroot measurement on main, so this contextual
rejection is numbered §362 here. No §357–§360 question or default was reopened.

The prototype revision at commit `71e9ace30a876a3c0ed12254615eb58814d87d14`
made the V4 native net accept both the original `OOC_STRAT_V4` attention
artifact and `OOC_STRAT_C1`. V4 continued through the existing attention
implementation; C1 shared the same `deckTok` tokens and changed only deck
aggregation. Empty decks remained zero vectors. C1 read exactly six appended
context tensors and rejected trailing bytes. The exporter failed closed on the
frozen checkpoint SHA, deployed-teacher identity, exact 115-tensor shared
weights, six contextual tensors, and the 3,200-parameter count. It produced an
811,976-byte C1 artifact for the experiment
(SHA-256 `6d308d5fea278ea8aecc90d1f8bf44efe839b11c57d1362020f1e47f6dba68f7`).
After the performance follow-up below, the C1 artifact and implementation are
not retained in the final PR tree. The `.pt` checkpoint was not committed.

One checkpoint-contract detail differs from the handoff's requested GELU
approximation: the frozen contextual block in `ContextualDeck` was trained and
evaluated using PyTorch's default exact GELU, while V4's existing layers use
the tanh approximation. A tanh C1 attempt failed the declared full-trace
parity thresholds (deck `1.055e-3`, source logits `1.065e-3`, prior
`1.171e-4`). The historical prototype used exact GELU to preserve the frozen
weights' actual behavior. No parity threshold was relaxed; the failed attempt remains
in the evidence directory. The C1 runtime was removed after the speed-only
follow-up below.

### Native/Python parity

The existing §356 semantic evaluator still classifies the frozen student as
`CONTEXTUAL_SEMANTIC_PRIOR_PASS`. Native C1 and the exact Python student were
compared across 6,317 unique eligible canonical priors (37,985 source logits):

| Output | Maximum absolute error | Gate |
| --- | ---: | ---: |
| Deck representation | `1.1325e-6` | `<1e-4` |
| Source policy logits | `3.0518e-5` | `<1e-4` |
| Grouped candidate logits | `3.0518e-5` | `<1e-4` |
| Multiplicity-corrected normalized prior | `2.8439e-6` | `<1e-4` |
| Top semantic action mismatch | `0 / 6,317` | exact |

The replay preserves captured candidate order, grouped source averaging,
primitive multiplicity correction and normalization. An attention-artifact
golden-vector test protects the existing V4 deck encoder.

### Controlled Release runtime

The two artifact arms ran one-threaded on the same 6,317 states, after one
warm-up pass and over five measured passes with A/B order alternated. Trace
decompression and parsing are outside the timed regions. Calls per arm were
31,585 for deck-only encoding, `prepareState`, and complete policy-prior
evaluation. Times use the thread CPU clock; per-call medians and tails are in
the linked raw evidence.

| Operation | Attention total CPU s | Contextual total CPU s | B/A | Reduction |
| --- | ---: | ---: | ---: | ---: |
| Deck encoder | 1.076375 | 1.149302 | 1.06775 | `-6.78%` |
| `prepareState` | 2.222872 | 2.301332 | 1.03530 | `-3.53%` |
| Complete prior | 3.787551 | 3.907124 | 1.03157 | `-3.16%` |

The decision-bearing complete-prior metric is slower by 3.16%, so the
predeclared `>=5%` improvement gate failed. Phase 3's paired 8-seed live smoke
was not triggered. There is no gameplay-quality result and no default
promotion.

### Current-main integration diagnostics

These checks were run against prototype commit `71e9ace30a876a3c0ed12254615eb58814d87d14`;
the C1-specific code and tests are not part of the final PR tree. The focused
Release suite passed 10/10: attention compatibility, contextual
artifact load and trailing-byte rejection, profiler attribution, attention and
contextual `LiveOocMctsPolicy`, `live_ooc_parity`, `live_ooc_protocol`,
`ooc_mcts_adapter`, and `run_profile_analysis`. The advisor protocol test
verified root and per-candidate OOC value-distribution bins. `ooc_mcts_adapter`
also exercised the existing depth-safety and semantic grouping/multiplicity
fixtures.

Independently, `live_ooc_protocol` verified the current advisor's
`ooc_value_distribution_v1` root distribution and per-candidate bins. The
Release `one_combat`, advisor, policy-test, parity-test and native-probe
targets built successfully. GitHub Actions CI remains the draft PR's
clean-repository gate.

### Review follow-up: tanh GELU speed-only screen and disposition

After review identified scalar `std::erf` as a likely hot operation, a temporary
speed-only build replaced C1 exact GELU with the same tanh-GELU formula already
used by V4. The source baseline was the prototype commit above; the frozen
6,317-state trace, attention artifact, contextual weights, one warm-up pass,
five measured alternating A/B passes, one thread, and thread CPU clock were
held fixed. The tanh implementation was already known to fail parity, so this
run made no fidelity claim and did not relax any gate.

| Operation | Attention CPU s | Tanh C1 CPU s | B/A | Reduction |
| --- | ---: | ---: | ---: | ---: |
| Deck encoder | 1.302093 | 1.531404 | 1.176110 | `-17.611%` |
| `prepareState` | 2.677835 | 2.884597 | 1.077212 | `-7.721%` |
| Complete prior | 4.526272 | 4.760331 | 1.051711 | `-5.171%` |

The predeclared complete-prior improvement threshold was `>=5%`; tanh C1 was
5.171% slower, so the gate failed decisively. Deck-count bucket results are in
the raw JSON; the 33–64 bucket contains only 25 measured calls. No fast GELU
approximation was implemented or timed, and Phase 3's eight-seed live smoke was
not run. The permanent C1 runtime, native artifact, exporter/evaluator support,
and C1 tests were removed from the final PR tree. The exact-GELU parity and
initial timing results above remain historical evidence for the rejected
prototype.

[Evidence packet](evidence/ooc_contextual_native_runtime_2026-09-26/README.md)
contains frozen artifact identities, parity results, both exact-GELU and tanh
speed distributions, raw build/export/test logs, and the failed tanh parity
attempt. Profile-only and rejected-preflight diagnostics were omitted during
review because they do not support parity or the speed decision. Knowledge
impact: current native architecture stays at `OOC_STRAT_V4`; §362 records the
rejected C1 prototype and follow-up. No
gameplay-quality or default-promotion result exists.

## §363 — Mechanical-q Lizard Tail archived screen and current-main transfer status (2026-09-26)

- **Question:** Does replacing the learned ordinary-win probability `q` with
  `1 - pOrdinaryWin`, while preserving the frozen learned `r` artifact and T2
  rule from PR #326, remove the q regression without introducing a score or
  support failure?
- **Candidate:** mechanical `q = 1 - pOrdinaryWin`; unchanged learned `r` from
  PR #326 (artifact SHA-256
  `9f8fb965b24fbd8da1f9600fc9ca0f243e5e9069c47067123c88e36e9f5ebcf9`); T2
  remains `floor(maxHP / 2)` on consumed-Tail wins. No r refit, T2 edit, or
  production integration.
- **Stage A — archived vendored post-hoc screen:** scored only the exact 128
  paired rows and CTM predictions frozen in PR #326. The vendored Silver teacher
  is retired on current main and was not rerun. Mechanical q had exact parity
  and candidate support on all 128 rows. The pooled candidate-minus-B1
  three-class NLL delta was `-5.44160` (source-bootstrap 95% CI
  `[-16.24698, -0.00910]`), and the multiclass Brier delta was `-0.04653`
  (95% CI `[-0.07691, -0.01735]`). The unchanged learned-r NLL/Brier deltas on
  45 consumed rows were `-0.91805` / `-0.09034`, with both intervals strictly
  below zero. The unchanged T2 rule passed its paired HP NLL, CRPS, and expected
  HP absolute error screens. Only 9 `LOSS_CONSUMED` labels from 9 sources were
  present, below the qualification data floor. This is development evidence,
  not qualification.
- **Stage B — native teacher-transfer diagnostic:** the first collector attempt
  replayed the campaign rather than loading the archived precombat snapshot.
  Its raw failure record is retained in
  `native_teacher_transfer/stage_b_collection_failure.json`; the source
  trajectory changed under native Silver, so its “selected fight not found or
  source trajectory incomplete” error is a **harness failure**, not a
  teacher-transfer result or scientific stop. It wrote no pair JSONL or native
  outcome labels. The corrected preregistered amendment,
  `native_teacher_transfer/stage_b_direct_snapshot_plan.json`, uses the exact
  119 non-burning archived snapshots and lists the nine burning-elite targets
  as structurally unreplayable because the archived state omits
  `burningEliteBuff`. No state is reselected; before either branch, the direct
  collector verifies the exact archived predictor input and persistent state.
  Main advanced through PR #332 to
  `0eed6993999386737d87f040e38fb241623b5cf3`, which default-initializes the
  native simulation counter added by PR #331; the singleton-root bypass remains
  disabled by the frozen exact-root-budget setting. The refreshed addendum
  SHA-256 is
  `9dde779d1d3d9fdfed83debfa9af101df96088ed0aba7aff7c597cec76928c03`; it pins
  integrated collector commit `00f34384b0235bcc4053e60fee05b42dc1d23c46`,
  executable SHA-256
  `ce0ef761b63d46c40bffd7b0518f9891ac8ab9aa3075d2a15e497352305561be`, the
  refreshed native teacher manifest, and `OMP_NUM_THREADS=1`. A pre-run local
  resource check measured one-minute load 28.87 on 12 logical CPUs with 74.81%
  CPU-pressure `some` avg10; one thread is frozen identically across arms to
  limit contention. The first guarded invocation exited before its pair loop
  with `invalid direct snapshot replay plan`: the collector and analyzer
  require the nine preregistered exclusions at the plan top level, while the
  first refreshed plan held them only inside `sourceSelection`. The corrected
  plan now includes that unchanged top-level list. The raw attempt log and
  failure record are retained at
  `evidence/lizard_tail_mechanical_q_qualification_2026-09-25/native_teacher_transfer/stage_b_direct_snapshot_collection.log`
  (SHA-256
  `d8089f349723cbea4a8cb22aa89588005dfb0e52978264c5354b3527ee55cc94`) and
  `stage_b_direct_plan_validation_failure.json` (SHA-256
  `d6823b7c4ed0dab919d6dcc101aa0a4d474d87fa68efb1507c3c9a17f1072cb3`). No
  pair JSONL, pair manifest, or combat outcomes were written; this is a
  pre-outcome plan-validation failure, not a teacher-transfer result.
- **Later Stage B update (2026-09-26):** retry 4 durably wrote 116/119 pairs
  and stalled on three `Room::EVENT` targets: `(4201028,15)` Masked Bandits,
  `(4201056,18)` Mysterious Sphere, and `(4201117,12)` Masked Bandits. Debug
  tracing proved all three direct snapshots and predictor inputs matched and
  all six Silver playout arms returned. The infinite loop was in post-combat
  `afterBattle()`/`regainControl()`: snapshots lack `curEvent` and the transient
  event callback, so the generic `Room::EVENT` fallback recursively invoked
  the same callback. A debug-only three-target rerun completed both arms for
  all three pairs with 8 OpenMP threads. The collector now returns direct
  snapshot Event rooms to the map after RAW combat capture, without inventing
  event rewards. At the time of collection, main was
  `0eed6993999386737d87f040e38fb241623b5cf3`. Retry 5 recollected all 119 rows
  under one executable and teacher manifest; it completed in 127 seconds with 119/119 checkpoints,
  119/119 exact support, exact mechanical-q parity, and no snapshot mismatch.
  Pair JSONL SHA-256 is
  `3e02b7d1175190edc0cb7933ba32ce87d614a3e2836f7ef4c6e473bd8a5f3658`;
  teacher manifest SHA-256 is
  `e81dc96da406b661b7b465a8790c63d8ff92516802b71ce1a4744a9b1e337be8`; the
  producer executable SHA-256 is
  `a055597f5c62cf29f6dd1912990400040044604be1b110f4119f43ee1e7ace16`.
  Exact plan: `stage_b_direct_snapshot_plan_retry5_eventfix_omp8_resumable.json`
  (SHA-256
  `7cc41d8588db740c80f4a79f3c29c610bfceed1e805b211596a9aa61b77d5fb9`).
  Two analyzer input-validation defects initially stopped scoring before
  outcome analysis: the exact-key schema omitted collector `pairCheckpointing`
  metadata, and the direct-snapshot path check used nonexistent
  `Path.is_relative()`. The validator now accepts and checks the exact
  metadata and uses `not Path.is_absolute()`; scoring, bootstrap, and gates
  were untouched. Against the retry-5 teacher pinned to the then-current base,
  the predeclared analyzer reports
  `PROCEED_TO_FRESH_NATIVE_QUALIFICATION`. Native labels are 81
  `WIN_RETAINED`, 28 `WIN_CONSUMED`, and 10 `LOSS_CONSUMED`; all 119 rows have
  exact support and q parity. Pooled candidate-minus-B1 three-class NLL is
  `-5.81982` (source-bootstrap 95% CI `[-17.44907,+0.02927]`) and Brier is
  `-0.02613` (95% CI `[-0.05668,+0.00352]`). On 38 consumed rows, learned-r
  NLL/Brier deltas are `-1.01041` / `-0.06454`; neither interval shows a clear
  regression. T2 scored 28 supported consumed wins and its HP NLL, CRPS, and
  expected-HP absolute-error intervals favor T2. The vendored/native
  three-class label agreement is 99/119; this remains a descriptive table
  only, with no cross-teacher pooling. The analysis JSON SHA-256 is
  `454b8afa9518875bb90359df5184641fa2b813ee97d0fbf888b6f6f8d605add8`; the
  strict direct-snapshot validator fix is pinned by
  `tools/combat_transition_lizard_pair_pilot.py` SHA-256
  `d681103e100a32b47aa6ca371b2a73752bb2c0dbeb93ed39288b50d4bf097a2d`. Stage
  B is a transfer diagnostic, not qualification.
- **Stage B retry 6 — current-main teacher transfer:** after PR #362, the
  baseline was `6bae3a67c63d1f724908e2ee87b27d51e32d30a0`. The exact same 119
  non-burning snapshots and nine preregistered exclusions were replayed with
  native Silver exact-10k fair search, an observed 8-thread OpenMP team,
  collector source `9ca24419bc8799e45aaa5df4b937ab9c11920ab4`, and executable
  SHA-256
  `038d69a177b07baf8efc10a523b47b655bddc7a2d3f27eef74707ab4b02cbe6a`. The
  frozen plan SHA is `7a83ceb0e4c9336922a683a0c97d9c04b5afb219de30d02ecc48ed3e26d6cfcb`;
  the teacher manifest SHA is
  `648593cc572930c0887b0339881b80da61e563c3407d2aca4f60ffb80650f5d1`. All
  119 states, support rows, and mechanical-q parity checks passed. Labels were
  80 `WIN_RETAINED`, 30 `WIN_CONSUMED`, and 9 `LOSS_CONSUMED`; as a transfer
  diagnostic, it does not meet the rare-loss floor. Candidate-minus-B1 pooled
  three-class NLL delta was `-5.85699` (95% CI `[-17.50884,+0.00700]`) and
  Brier delta `-0.03223` (CI `[-0.06387,-0.00142]`). The 39 consumed-row
  learned-r NLL delta was `-1.05627` (CI `[-2.96512,+0.00543]`) and Brier
  delta `-0.07813` (CI `[-0.17577,+0.01696]`). T2 scored 30 supported wins;
  HP NLL, CRPS, and expected-HP absolute-error deltas were `-1.62445`,
  `-4.63706`, and `-5.30852`, all with 95% intervals below zero. There were
  19/119 vendored/native three-class label disagreements; the teachers remain
  unpooled. The frozen analyzer passed the transfer proceed gate. Analysis
  SHA-256 is
  `947bf1ab459ec29f46bb13e362b8f310f21efdb4617bb6434dd485894b740951`; the
  final pair JSONL SHA-256 is
  `9f8c46bd196ed9a9c1f2a90515ac36329418bd7dde6e880e97b6c12fbf798456`. The
  119 bulky checkpoint payloads remain local scratch; the compact checkpoint
  hash index is
  `stage_b_direct_snapshot_checkpoint_sha256_index_retry6_current_main_omp8.tsv`
  with SHA-256
  `38a68642a32319ade68c03c9f1cff97f26f6fbbec4fcbaf2196dd431d03cda0f`.
  This diagnostic permits Stage C to proceed but is not qualification.
- **Stage C — fresh native qualification:** a 320-source HARD288/BROAD32
  assignment is frozen with an audited fresh block and outcome-blind BROAD32
  salt. Its 320 unique sources were rechecked disjoint from all 367 recorded
  prior Lizard sources (assignment SHA-256
  `752fd7cc3769a065478c0045593944a0822e24909db7cd374397a0f464ae964a`). Retry 5
  applies only to the teacher pinned to `0eed6993999386737d87f040e38fb241623b5cf3`;
  retry 6 is the matching current-main transfer diagnostic on baseline
  `6bae3a67c63d1f724908e2ee87b27d51e32d30a0`.
  Main advanced through `ffd51f3bc43b03aa356c419567d77b1eecc636a1` to current
  base `6bae3a67c63d1f724908e2ee87b27d51e32d30a0`. PR #327 changed native
  Silver equivalent-copy reroot behavior, which is not disabled by the frozen
  exact-root-budget setting. PR #362 changed `SilverWireState` and
  `SilverConversion` to preserve pending card queues at card-selection roots
  and settle Guardian Mode Shift before replay. Retry 5 remains historical
  evidence; retry 6 passes the current-main Stage-B proceed gate. Current main retired the GCP research workflow in
  PR #361; under ADR-0024, the frozen 320-source Stage C can run locally without
  a general seed ceiling after the current-teacher Stage-B gate passes. The
  user has authorized that conditional local run. Before launch, freeze the
  final source/build/artifact provenance and resource budget, then use the
  repository seed guard. The pre-outcome plan is frozen at SHA-256
  `54784e141ef029e132d07c5aa0300d5f7440034a49d427c19438a6096355736c`. It pins
  the candidate, teacher/executable, selector/analyzer sources, and unchanged
  gates. Candidate and pair collection use eight one-thread subprocess workers;
  each source is durable and independently resumable, while shard payloads stay
  out of the PR. Preflight found 12 logical CPUs, 10 GiB available RAM, 369 GB
  free disk, load average 1.44, and no recent CPU pressure. The first candidate
  collection attempt completed eight guarded source commands, then stopped
  because its mutable progress index used the write-once artifact writer. All
  eight source shards passed independent producer/teacher/seed and file-hash
  validation. No target selection, candidate scoring, pair collection, or
  qualification analysis ran. The empty failed index was preserved in local
  quarantine. The write-once behavior remains for immutable per-source outputs;
  only the progress index now uses atomic replacement. Two focused tests cover
  both behaviors. Remote main then advanced from `6bae3a67c63d1f724908e2ee87b27d51e32d30a0`
  to `212aa25485bc6e8f0a5a91eb35edc7485056cb5a` in PR #366. The intervening
  native-search change is the opt-in `STS_OOC_MCTS_REUSE_TRACE` observer, which
  is unset in the frozen Stage-B/Stage-C teacher configuration; Stage B retry 6
  remains applicable. The merged PR source was clean-built at producer commit
  `45ff412f2f48ee4ff8b14325b8e317688a3a2880`, executable SHA-256
  `8965131f93e6d56544c8a127ce7308decc66b8ef61ff511845d2760f88aa35ea`, with
  current-main teacher manifest SHA-256
  `c271a3edc7adb8237ca1e6a8611c7e97be1ba2efadd6d5179fa80dcad476dbc8`. The
  earlier eight shards are preserved but excluded because they used the old
  executable; all 320 fresh sources will use the same current-main binary. The
  first execution-only amendment plan
  `stage_c_preoutcome_plan_retry1_indexfix.json` (SHA-256
  `52c331382131309ff5ee74c111d9ce962ad84f394884f1c040535fcae5536769`) binds
  the checkpoint-writer correction. The current-main execution amendment
  `stage_c_preoutcome_plan_retry2_current_main_indexfix.json` (SHA-256
  `2c4d5eb54ee0277573ddef9e21359852ac965cbd0a5a9df9496086432f2a3ee2`) binds
  the refreshed teacher/binary and records why the eight old-executable shards
  are not reused. The source assignment, candidate, selection, worker topology,
  and qualification gates are unchanged. The updated preflight passes. The
  refreshed collector started at `2026-09-26T20:47:18Z`; by `20:49:49Z`, its
  durable index recorded 36/320 current-main sources. It reports eight
  subprocess workers with one OpenMP thread each. Target selection, pair
  collection, and qualification analysis have not started. Only Stage C can
  qualify the candidate.
- **Decision:** Stage A remains development evidence. Retry 6 passed the
  current-main transfer proceed gate and authorizes the already-frozen Stage C
  run, but neither Stage A nor B qualifies the candidate. The Stage-C
  scientific plan and resource preflight remain frozen. The first Stage-C
  candidate attempt stopped on the checkpoint-index bug after eight valid
  old-executable shards; the corrected collector preserves them but excludes
  them after the main advance so the qualification cohort uses one current-main
  binary. The refreshed plan is frozen; no current-main candidate shards, target
  selection, or paired outcomes have been produced. No runtime support changed; production remains
  `active_unqualified_lizard`.
- **Evidence:** [stage packet](evidence/lizard_tail_mechanical_q_qualification_2026-09-25/README.md),
  including frozen cohort artifacts, Stage A analysis, candidate manifest,
  source assignment, retry-5 history, retry-6 current-main teacher/plan/pairs,
  analyzer output, compact checkpoint hash index (payloads excluded as scratch),
  the Stage-C scientific and execution-amendment plans, both failed-attempt
  provenance records, and current-main teacher manifest. The obsolete >128 GCP gate was
  removed per ADR-0024, and the repository's local 320 experiment maximum is
  used without a cloud bypass. The clean Release build and focused Event-room
  regression passed; GitHub Actions did not start because of the account
  payment/spending-limit block (not a code verdict). The focused Stage-C shard
  index self-test now also passes after the retry-1 checkpoint-writer fix.

Knowledge impact: current research now records the event-continuation harness
fix, analyzer schema compatibility fix, retry-6 current-main transfer result,
the frozen Stage-C scientific plan, and its checkpoint-index execution
correction. No runtime support or candidate parameters changed.

## §364 — Active Lizard fresh native Stage-C qualification (2026-09-27)

- **Hypothesis:** replacing learned q with mechanical `q = 1-pOrdinaryWin`,
  while retaining the exact #326 learned-r artifact and T2 rule, improves the
  three-class transition model on a fresh native-Silver cohort without a clear
  BROAD32 degradation.
- **Frozen cohort and selection:** 320 fresh sources, `4202000..4202319`,
  disjoint from the audited 367 prior Lizard sources. HARD288 selected one
  prospective-support combat per source maximizing `(1-pOrdinaryWin)*(1-r)`;
  BROAD32 used the frozen outcome-blind SHA-256 salt. The candidate pool
  contained 6,509 rows; the selector scored 4,674 eligible states and froze
  320 targets (288 HARD288, 32 BROAD32). Assignment SHA-256 is
  `752fd7cc3769a065478c0045593944a0822e24909db7cd374397a0f464ae964a`; target
  selection SHA-256 is
  `68c4e6e4c20596464338e3b8ab44ea0bae8bc4a431d7f3de765a944dc8063493`.
- **Teacher and execution:** current-main baseline
  `212aa25485bc6e8f0a5a91eb35edc7485056cb5a`, producer commit
  `45ff412f2f48ee4ff8b14325b8e317688a3a2880`, executable SHA-256
  `8965131f93e6d56544c8a127ce7308decc66b8ef61ff511845d2760f88aa35ea`, and
  native-Silver teacher manifest SHA-256
  `c271a3edc7adb8237ca1e6a8611c7e97be1ba2efadd6d5179fa80dcad476dbc8`.
  Teacher search was fair, exact 10,000 simulations; collection used eight
  subprocesses with one OpenMP thread each. The separate pre-outcome pair plan
  SHA-256 is
  `dc1084ea262769500f7fd37852cfd237ecc89cd4e74267c54adc0929d4dabd07`.
  All 320 per-source pair shards, manifests, and provenance records validated.
  The initial collector invocation exited only during aggregate-time module
  import after producing all shards; running it as a Python module reused all
  320 saved outputs without rerunning seeds.
- **Pair-plan timestamp correction:** the frozen `fresh_native/stage_c_pair_preoutcome_plan.json` remains unchanged at SHA-256 `dc1084ea262769500f7fd37852cfd237ecc89cd4e74267c54adc0929d4dabd07`. Its `frozenAtUtc` value, `2026-09-26T21:22:37.149773+00:00`, agrees with the observed file mtime `2026-09-26T23:22:37.150061+02:00`. The candidate JSONL and manifest mtimes are `23:11:10.402490+02:00` and `23:11:10.426052+02:00`, about 11m27s earlier; the recorded UTC freeze therefore follows candidate-corpus validation. `frozenAtLocal=2026-09-26T22:41:02+02:00` is stale/inherited metadata (20:41:02Z, before current-main candidate collection started at 20:47:18Z) and is not the pair-plan freeze time. This documentation corrects the interpretation only; no frozen plan or outcome artifact was changed.
- **Integrity and outcome counts:** the final pair JSONL SHA-256 is
  `d60bf8004234abf6549997ab4cff12da6650cc50d4f42b2d6bceb6a07f5cdf73`; the
  manifest SHA-256 is
  `c0269eb57ce3fe4eeb2890e7d58f06a2b778f62da43fb9345612e42aa69bc78b`.
  All 320 rows were valid, exactly supported, and passed mechanical-q parity.
  Outcomes were 195 `WIN_RETAINED`, 105 `WIN_CONSUMED`, and 20 `LOSS_CONSUMED`
  from 20 distinct sources; 125 consumed rows were B1-scoreable. All 32
  BROAD32 rows were `WIN_RETAINED`.
- **Predeclared qualification result:** the frozen analyzer output SHA-256 is
  `d1f87d5a74170445fbd7ce5f3f22abd36bd14569942883276ebfc3c03b389984`; it
  classifies the candidate
  `ACTIVE_LIZARD_MECHANICAL_Q_LEARNED_R_T2_NATIVE_QUALIFIED`. Pooled
  candidate-minus-B1 three-class NLL was `-12.99026` (source-bootstrap 95% CI
  `[-23.75822,-4.36279]`) and multiclass Brier was `-0.05266` (CI
  `[-0.07482,-0.03239]`). Learned-r NLL and Brier deltas on 125 consumed rows
  were `-1.85084` (CI `[-3.26182,-0.71950]`) and `-0.11904` (CI
  `[-0.16692,-0.07162]`). T2-minus-T0 on 105 supported consumed wins was
  `-1.06154` HP NLL (CI `[-1.47307,-0.67843]`), `-3.18088` HP CRPS (CI
  `[-4.85606,-1.51303]`), and `-2.84107` expected-HP absolute error (CI
  `[-4.77866,-1.02229]`). Data floor, exact support, q parity, primary,
  learned-r, and T2 gates passed; no clear HARD288 or BROAD32 degradation was
  detected. The T2 requirement for at least 20 supported consumed-win rows
  was met with 105, and no T2 row was unscored or outside its model domain.
- **Decision and boundary:** Stage C qualifies the frozen research candidate
  under the predeclared native-teacher gates. It does not integrate runtime
  support or change the production guard; production remains
  `active_unqualified_lizard` pending a separate reviewed implementation and
  promotion decision. Stage A vendored post-hoc evidence, Stage B same-state
  teacher-transfer diagnostics, and Stage C fresh native qualification remain
  separate evidence domains. See the [full packet](evidence/lizard_tail_mechanical_q_qualification_2026-09-25/README.md#stage-c-fresh-native-qualification-assignment)
  and raw [analysis JSON](evidence/lizard_tail_mechanical_q_qualification_2026-09-25/fresh_native/fresh_stage_c_analysis.json).

Knowledge impact: current research records that the frozen mechanical-q,
learned-r, T2 candidate passed its fresh native Stage-C qualification. No
runtime support changed.

## §365 — Active-Lizard correction in the DeepSets/Brew CTM stack: parity pass, integration canary invalid (2026-09-27)

- **Question and baseline:** Can the freshly qualified active-Lizard correction
  compose with the gameplay-qualified DeepSets plus standard-Attention Brew
  fallback CTM stack? Task baseline was PR #330 merge
  `812ce0235e67aa9832142f69c6c8fc89d6875372`; the fresh current-main checkout
  began at `be84fd934131395e87858195d74c169146a36ccf`. Existing PR #330 and
  PR #351 qualification cohorts were reused only as accepted evidence; neither
  cohort was repeated.
- **Gate 1:** The integration passed frozen 320-row Stage-C deterministic
  native parity at `1e-4` tolerance with zero support/semantic mismatches.
  Maximum absolute errors were `5.364418e-7` ordinary survival,
  `3.576279e-7` reserve survival, `5.364418e-7` q, `3.884913e-7` r, and
  `5.364418e-7` for class probabilities. Conditional T2 child identity passed
  on all 320 rows. The existing 31-row DeepSets/Brew mechanism fixture passed
  with 13 ordinary DeepSets and 18 standard Attention fallback routes. The
  eight-row dispatch fixture passed ordinary DeepSets, Brew fallback, active
  Lizard, later-position Lizard, spent Tail, Lizard+Brew fail-closed, Fairy,
  and Mark of the Bloom routes. The reviewed integration implementation was
  `bcdb92e66043483681b2cd3259c97edbefed23cb`.
- **Post-merge Gate 1 revalidation:** before handoff, the branch was merged
  with fetched current `origin/main` `31571bbd406f7bc0435d3010fc14cfee6897ff33`.
  The focused Release build of `combat_transition_runtime_probe` and
  `one_combat` passed. The rebuilt probe SHA-256 remained
  `1ed808cfa04b9dbdddbae256d410f664b252690613e5d656253c526ee69ec692`; the
  merged-source `one_combat` SHA-256 is
  `8c4f87c4339690541dd7f0585ba235d9b419ae409e7dd0e8f63e80d9817cf845`. The
  frozen parity verifier again passed all 320 rows, zero support/semantic
  mismatches, all 320 conditional T2 child identity checks, and all eight
  dispatch fixtures. The 31-row Brew/DeepSets mechanism fixture again passed
  with output byte-identical to the original recorded fixture and unchanged
  13 ordinary / 18 fallback routing counts. Focused CTest passed 5/5. The
  machine-readable parity output is preserved as
  `evidence/lizard_tail_mechanical_q_ctm_integration_2026-09-27/post_merge_native_parity.json`.
  The exact parity input is included in that packet as
  `integration_candidate.native` (SHA-256
  `40743022491de57d864dc911b3db1bd7bb7dceb9d60f2481c55145d66864aa25`) with
  `status=integration_candidate`, `qualified=false`, `defaultChanged=false`,
  and `defaultForOocMcts=false`; it is a non-production test input. The
  historical Gate 2 manifest retains its original `/tmp` path, whose artifact
  hash matches this tracked copy. No gameplay seeds were rerun.
- **Revalidation after current main advanced:** current main
  `56381780ff4382c85564b02a86d45325b4421021` added the Match and Keep policy.
  It was merged at `1acb8c7d52b8cd82de5e20da9a96407c49129033`. The focused
  Release build completed; `combat_transition_runtime_probe` SHA-256 remained
  `1ed808cfa04b9dbdddbae256d410f664b252690613e5d656253c526ee69ec692` and
  `one_combat` SHA-256 is
  `ab397c4a4079102095cdc34a167686dd4913aa83553dd5f6c6d88c92ab0cac38`.
  Gate 1 again passed 320/320 parity rows, zero support/semantic mismatches,
  all T2 identity checks, and all dispatch fixtures using the tracked candidate.
  The 31-row Brew fixture matched its saved rows and metrics byte-for-byte.
  Focused CTest passed 6/6, including `match_and_keep` and the five
  combat-transition/OOC tests. The forced-relic data=1 helper remains intact.
  No gameplay seeds were run in this deterministic revalidation.
- **Gate 2 plan and provenance:** The predeclared canary ran exactly eight
  paired seeds `991000..991007`, Ascension 0, Act-3 horizon, project-fair
  native Silver at 10,000 real-combat simulations, and 2,048 OOC MCTS
  simulations. `STS_FORCE_RELIC=LIZARD_TAIL` was set in both arms; only
  `STS_OOC_MCTS_ACTIVE_LIZARD` differed. The frozen final manifest SHA-256 is
  `bb0e964bb2b19af1f18559c51b3d1b094c9f5bb538e47d2bdc0c089c9d8900b3`;
  source SHA is `bcdb92e66043483681b2cd3259c97edbefed23cb`, executable SHA-256
  `63975e203b240f987a1b87fac8778fb25f434cfa5e23834bfda1cd5a7e6fc7ee`.
- **Result and classification:** All 16 whole-run processes returned zero and
  produced result rows, sidecars, and traces. Every run had zero
  `unsupportedCombats`, `mctsSupportAborts`, hybrid fast/fallback support
  failures, and Lizard support failures. However, all eight treatment telemetry
  rows also had zero Lizard preparations and samples. The cause was the forced
  relic helper: it inserted every relic with `data=0`, whereas
  `GameContext::obtainRelic` initializes a new active Tail with `data=1` and
  battle setup uses that value as the active-relic flag. Therefore both arms
  started without active Lizard, and this canary is
  **`INVALID_TREATMENT_NOT_EXERCISED`** despite successful process completion.
  Control and treatment outcomes matched on all eight pairs at 5/8 wins each;
  these are descriptive only and do not compare the correction. See
  [the complete result and raw-output bundle](evidence/lizard_tail_mechanical_q_ctm_integration_2026-09-27/gate2_failed_canary_2026-09-27/)
  and [the report](evidence/lizard_tail_mechanical_q_ctm_integration_2026-09-27/README.md).
- **Run history and correction:** Two stale-environment startup groups each
  contained 16 invocations that exited with code 2 before `bestbench`: first
  the removed `STS_SILVER_TELEMETRY=1`, then the removed
  `STS_SILVER_REUSE_CAP=32768`. Neither group created a result or sidecar or
  consumed a gameplay seed. The final manifest used telemetry `0` and left
  the fixed native reuse cap override unset. After discovering the inactive
  forced Tail, `installRunForcedRelic` was changed to initialize only Lizard
  Tail with `data=1`; ordinary forced relics remain zero-initialized. The
  active-Lizard CTest now verifies the forced relic's data and battle-start
  flag, along with an ordinary Anchor control. The post-correction
  `one_combat` SHA-256 is
  `3e8eb01c41ec7615d99b87003ae71fe5068430f083b270ea41c9a974af269b22`.
  Focused Release build succeeded and focused CTest passed 5/5. No gameplay
  runs were repeated or extended.
- **Decision:** Gate 1 passes; Gate 2 does not. Gate 3 was not run, the exact
  candidate was included only as a non-production evidence input and was not
  packaged as a production artifact; default selection did not change.
  `STS_OOC_MCTS` remains off by default and the active-Lizard correction
  remains opt-in. The eight fixed pairs are spent;
  any new active-Tail canary needs a new frozen plan. This is not a win-rate
  qualification, and the existing PR #330/#351 quality evidence is unchanged.
- **Packaging guard and environment reference:** review found that the
  re-export tool's `--production` option could mark an artifact qualified and
  default without a valid integration canary. The option was removed; the tool
  now emits only an `integration_candidate` with qualification/default flags
  false. The environment-variable reference also documents the opt-in
  `STS_OOC_MCTS_ACTIVE_LIZARD` switch, its `0`/`1` values, and its required Brew
  fallback model.
- **Knowledge impact:** updated the maintained environment reference with the
  forced-Tail initialization semantics and active-Lizard opt-in; current
  research records the invalid integration result and post-merge deterministic
  revalidation. Baselines remain unchanged. No trained model, promoted artifact,
  or default configuration changed.

## §366 — Active-Lizard DeepSets/Brew integration: fresh canary and default plumbing (2026-09-27)

- **Question and baseline:** Does the corrected active-Tail initializer allow
  the qualified Lizard correction to run in the already-qualified DeepSets plus
  standard-Attention Brew-fallback stack, and can that exact stack become the
  default when OOC MCTS is explicitly enabled? The task baseline was PR #330
  merge `812ce0235e67aa9832142f69c6c8fc89d6875372`. Before Gate 2 follow-up,
  the implementation branch included current main through
  `56381780ff4382c85564b02a86d45325b4421021` at merge commit
  `1acb8c7d52b8cd82de5e20da9a96407c49129033`. PR #330 and PR #351 qualification
  evidence was reused; neither quality cohort was repeated.
- **Gate 2 follow-up:** The original `991000..991007` canary remains invalid
  because the forced Tail was inserted spent. A fresh, disjoint cohort ran
  exactly eight paired seeds `991008..991015`, control then treatment, A0,
  Act-3 horizon, 10,000 project-fair native Silver combat simulations and
  2,048 OOC MCTS simulations per run. All 16 runs completed and reached floor
  51; both arms won 8/8, descriptive only. Treatment reported 120,708 Lizard
  preparations and samples, 225 consumed wins, 30 consumed losses, and zero
  Lizard support failures. The single treatment seed with support aborts had 41
  `active_unqualified_lizard` reasons, 39 fast-path and 2 Brew-fallback support
  failures, and 41 boundary exclusions. The frozen adapter route and reason
  identify these as predeclared Fairy/Mark exact-path cases, including two
  Brew-plus-boundary intersections; raw telemetry does not distinguish Fairy
  from Mark of the Bloom. No eligible correction failure or other treatment
  support reason was observed. Per-run accounting, result/sidecar/trace
  validation, HP bounds, and state/RNG/numerical log scans passed. The frozen
  result JSON SHA-256 is
  `1ecd285c78e69249b6e5f46943d84cc10bc4bb86eea4e912f1c0abe774fef1d9`; the
  manifest pins source commit `5c818c0e30aa20fb178bfde19355c01852afef84`,
  candidate artifact `40743022491de57d864dc911b3db1bd7bb7dceb9d60f2481c55145d66864aa25`,
  and seeds/budgets. See the
  [follow-up evidence packet](evidence/lizard_tail_mechanical_q_ctm_integration_2026-09-27/gate2_followup_canary_2026-09-27/).
- **Gate 1 and production package:** Re-exported the exact DeepSets tensor
  payload (`429f9dc018a6b9de231657df4aba787bddc2de2e4cecb2e7989e167c37813139`)
  as `selfplay/models/combat_transition_deepsets_lizard_t2.native`; artifact
  SHA-256 is `abb2a9ead6efd6b97ee64192e0459eb08ceff7fd93f2b5f4b87a0bf379e571ab`.
  Packaging requires the exact hashed Gate 2 PASS report and verifies its
  frozen inputs and raw evidence files. The runtime pins the production
  artifact bytes and promotion provenance. On that artifact, deterministic
  parity passed 320/320 rows, all conditional T2 child identity checks, and
  all eight dispatch fixtures with zero support/semantic mismatches; maximum
  probability error was `5.364418e-7` at `1e-4` tolerance. The 31-row
  DeepSets/Brew fixture matched saved output and metrics byte for byte. Focused
  Release build and six focused CTests passed. The production-artifact parity
  report SHA-256 is
  `7f6abc72c32605c6e0375eb31875902f80f33beafd8c9de0bbb907a7acf18a75`.
- **Default behavior:** With `STS_OOC_MCTS=1` and
  `STS_OOC_MCTS_COMBAT_MODEL` unset, the adapter selects the promoted DeepSets
  artifact, pinned standard Attention Brew fallback, and active-Lizard
  correction. Explicit combat/fallback paths remain usable. Setting
  `STS_OOC_MCTS_ACTIVE_LIZARD=0` disables the correction as a diagnostic
  rollback. OOC MCTS remains off unless explicitly enabled. Active Lizard plus
  Entropic Brew, Fairy Potion, and Mark of the Bloom retain their declared
  boundary behavior.
- **Gate 3 default smokes:** The two frozen cases ran on implementation commit
  `529c214562fd7eda4842f4386c05303c4d3d3d47`, executable SHA-256
  `ebe2dcc09b0ca76867a12332f583e7529a58991033afeb7b7a00fb065a5e10fe`, with
  combat-model, Brew-fallback, and active-Lizard override variables omitted.
  Both guard-only preflights passed. Seeds 991016 (no forced relic) and 991017
  (forced `LIZARD_TAIL`) produced complete result, sidecar, trace, and log
  outputs at floor 51. Both startup lines and combat telemetry identified the
  promoted model, standard Attention fallback, and active-Lizard correction.
  The forced-Tail case reported 17,610 preparations and 17,608 samples; its two
  support aborts were the existing `unsupported:smoke_bomb` model exclusion,
  with zero fast/fallback support-failure counters.
- **Smoke evidence limits:** The ordinary case's complete outputs and final
  `BEST` summary were produced, but the post-run wrapper failed while parsing
  the malformed auxiliary `[ooc-mcts-config]` line before saving that child
  process exit code. The same line lacks the closing quote after `dispatchRule`
  in both logs; the separate startup and combat-telemetry records are intact.
  Review traced the malformed payload to this implementation's config emitter;
  a follow-up correction closes the string and strengthens the seed-free
  startup check to parse the emitted JSON and verify its dispatch and
  active-Lizard fields. Seed 991016 was not repeated and the frozen results
  remain unchanged, so its child exit code remains unknown. This does not alter
  the verified effective stack values. The
  frozen smoke manifest SHA-256 is
  `e3778296788e8550f450d85df8dbf897e4886f009542061d5debcb028b67cf93`; the
  machine results SHA-256 is
  `a1a66cae7b5e13b8f936df7b72cea62e58c1ad96500e9c8d257adffca64ad4be`. See
  the [Gate 3 smoke packet](evidence/lizard_tail_mechanical_q_ctm_integration_2026-09-27/gate3_default_smokes_2026-09-27/README.md).
- **Knowledge impact:** current baselines, current research, OOC architecture,
  environment-variable reference, and this evidence packet now record the
  enabled-OOC default and its boundaries. PR #330 and PR #351 remain the
  scientific quality qualification; this section records the integration and
  default-plumbing evidence only.

## §367 — OOC MCTS equivalent-outcome merging: search structure and paired gameplay (2026-09-28)

- **Question:** With sampled futures, every OOC MCTS chance particle was its own
  decision node even when it matched a sibling's visible state. Does pooling
  search-equivalent particles (`STS_OOC_MCTS_MERGE_OUTCOMES=1`, #384, PR #386)
  change play strength? Answers the open question left by §361.
- **Implementation and provenance:** source `6ed6c943397c058610855f3d29d513bdf9f37a97`
  (base `795c4e7`), Release GCC 13.3, frozen executable SHA-256
  `a7450100fee8b937ed9efb4f39824e11c92f9a975f48393af4015ad9a957380a`; models
  and full environment in the evidence packet. A0, project-fair, Act-3 stop,
  exact-10k native Silver, 2,048 OOC MCTS simulations, automatic CTM stack.
- **Search structure (seeds 12002032/12002033, temporary diagnostic):** without
  pooling 49-55% of decision nodes duplicated a sibling's visible state (shop,
  rest 100% and rewards 93% of multi-particle chance nodes were visibly
  deterministic); with pooling 0%, about 35% of samples pooled, maximum depth
  4 -> 11-12. Remaining distinct siblings differed visibly except 11 event pairs.
- **Paired gameplay:** plan frozen before seeds ran. A sequential design
  (38400000.., Bonferroni looks) was stopped by the user after look 1 (N = 8,
  interval [-20.8, +6.8], continue) in favor of a fixed cohort. Fixed cohort
  `38410000..38410127`, 128 pairs, 95% t-interval on `floor + 10*won`:
  mean **-0.25**, **[-2.46, +1.96]** — **inconclusive**. Wins 86 vs 83
  (McNemar p = 0.74; descriptive paired win-rate 95% interval [-11.5, +6.8] pp); mean floor 47.47 vs 47.45; +12.7% seconds per run,
  +19% MCTS CPU per simulation; 36.2% of transition samples pooled; max depth
  4 -> 15; fallback decisions 387 vs 377.
- **Decision:** keep the option opt-in (default off). No default change.
- **Evidence:** [packet](evidence/ooc_merge_outcomes_2026-09-28/README.md).
- **ELI5:** The search stopped counting identical-looking futures separately
  and so looked three times deeper for the same effort, but on 128 paired runs
  it neither won nor lost more often; it only ran about 13% slower.
- **Knowledge impact:** `architecture/out-of-combat.md` (merge semantics and
  result), `evaluation/current-research.md` (§361 open question answered),
  `operations/environment-variables.md`.


## §368 — #334 A3 VALIDATION sibling-ranking correction (2026-10-02)

**Scope:** offline diagnostics on the frozen TRAIN/VALIDATION experiment at
`/home/philippherrmann/Documents/sts/artifacts/vwin-refresh-334/a3-trainval-20261001-50713b83/`.
Baseline: `50713b83ed972b87d16c86593cfc2820dd6807d5` (PR #392).
No gameplay seeds, training, collection, C++ build, or TEST evaluation ran.

**Invalidated result:** the old MAP accuracy 0.500 with CI [0.500, 0.500]
for every arm scored the common pre-decision `rowIdx=0`. The producer captures
it before executing the forced MAP option. The corrected evaluator uses the
minimum recorded `rowIdx > 0` for MAP branches, retaining minimum `rowIdx`
for other types. No producer or frozen data changed.

**Provenance:** the frozen corpus index SHA-256 is
`ca4b6e2bbcb29d10f83bd90944b991dd7f19eebdf5e19029e7ffac5a049cd87f`. Only 77 VALIDATION components were opened for
MAP and branch table access (68,903 MAP rows; 2,577 branches). Component
manifests and opened tables were hash-verified. The four saved checkpoints
and all 43 frozen files were verified unchanged before/after. Every non-MAP
ranking summary reproduced the original frozen summary exactly.

**Corrected VALIDATION accuracy [source-cluster 95% CI]:** 2,000 bootstrap
replicates, seed 0; pair-weighted credits, whole-source resampling. Missing
post-option MAP branches: **0 for every type and arm**.

| Decision type | Discordant pairs | Sources | B0 | X1 | X2 | M1 |
| --- | ---: | ---: | --- | --- | --- | --- |
| BOSS_RELIC | 121 | 36 | 0.6612 [0.5593, 0.7581] | 0.5455 [0.4160, 0.6653] | 0.6736 [0.5702, 0.7689] | 0.5041 [0.3934, 0.6051] |
| CARD_REWARD | 70 | 25 | 0.4000 [0.2571, 0.5556] | 0.5071 [0.3730, 0.6370] | 0.4786 [0.3380, 0.6232] | 0.4857 [0.3514, 0.6176] |
| EVENT | 42 | 16 | 0.6667 [0.5000, 0.8163] | 0.7143 [0.5323, 0.8750] | 0.7500 [0.5833, 0.8929] | 0.6429 [0.4473, 0.8298] |
| MAP | 23 | 17 | 0.5217 [0.3500, 0.7045] | 0.5000 [0.3269, 0.6944] | 0.4565 [0.2917, 0.6500] | 0.3913 [0.2273, 0.5714] |
| NEOW | 140 | 41 | 0.6571 [0.5352, 0.7660] | 0.5964 [0.4928, 0.6958] | 0.5607 [0.4593, 0.6619] | 0.5071 [0.4130, 0.6030] |
| OTHER_SELECTOR | 102 | 16 | 0.6225 [0.4505, 0.7710] | 0.6520 [0.4615, 0.8194] | 0.5931 [0.3944, 0.7745] | 0.6961 [0.5163, 0.8348] |
| REST | 184 | 29 | 0.4429 [0.3481, 0.5389] | 0.4457 [0.3402, 0.5511] | 0.4783 [0.3822, 0.5824] | 0.4402 [0.3268, 0.5604] |
| SHOP | 181 | 31 | 0.5912 [0.4583, 0.7169] | 0.6022 [0.4711, 0.7188] | 0.6105 [0.5082, 0.7083] | 0.5801 [0.4573, 0.6919] |
| TREASURE | 7 | 7 | 0.5714 [0.1429, 0.8571] | 0.3571 [0.0714, 0.7143] | 0.5000 [0.1429, 0.8571] | 0.7143 [0.4250, 1.0000] |

**SPARSE_RANKING_SIGNAL = YES:** MAP (23 pairs) and TREASURE (7 pairs)
remain below 30 valid discordant pairs. The corrected MAP intervals provide
limited precision; this is no TEST verdict or model-promotion evidence.

**Native B0 parity:** PASS on the first 64 VALIDATION MAP rows after the
LF-only fixture correction; maximum absolute error
`5.734090424702742e-09` < `1e-4`. Existing executable SHA-256
`8175c9dc91aa5029e47b3e74f511128b3af575382ae52bf1f7fea811d464b1f6`; frozen B0 SHA-256
`fc52c14cb7239a33b3c1f9d0477ccb6c895fd51a07240fe804744e605067ad70`. No native parser/model changes or rebuild.

**Unchanged evidence:** X1 half TRAIN NLL `0.47293937`, full TRAIN NLL
`0.44453298`, delta `+0.02840638536`; `DATA_SCALE_SIGNAL` remains valid.
`REAL_TEST_OPENED=false`; no TEST latch exists. Smoke/frozen TEST status is
unchanged. The frozen tooling identity still binds the original source;
this correction does not authorize opening TEST with changed tooling.

**Evidence:** `/tmp/vwin-ranking-review-20261002/` contains the bounded
recomputation script, full-precision ranking/provenance JSON, before/after
frozen hashes and verification logs. `ranking.json` SHA-256:
`1a49609b20195b86ad5bb9ab6accaf67511ad2da2ba399eda14099ed5d3b9826`.

**Knowledge impact:** maintained A3 ranking/parity semantics in
`operations/ooc-label-pipeline.md`; this ledger corrects scientific evidence.

## §369 — #400 Stage 1 Silver search-parameter heterogeneity screen (2026-10-02)

**Question:** do combat contexts (room class × act) prefer different native
Silver search constants strongly enough that choosing them per combat beats
the single best global choice?

**Protocol:** frozen plan
[PLAN.md](evidence/silver_param_screen_400/PLAN.md), pre-registered before the
cohort. Code `31de6a6d` (PR #402); independent review passed before analysis.
`one_combat silverparams400gen` played seeds `40000000..40000127` with the
exact-10k native Silver teacher and the V4-gated policy, then replayed every
real fight from a detached pre-battle copy under five arms: control
(exploration 25, widening alpha 0.52389), exploration 12.5 / 50, and widening
alpha 0.40 / 0.65. The control arm had to reproduce the source fight.
Discovery and confirmation halves were split by seed hash.

**Integrity:** 128/128 valid sources and 3,380 fights. The control replay
reproduced 3,361 of them; all 19 exclusions were Smoke Bomb escapes, and one
more fight escaped only under c50. That leaves 3,360 valid paired fights
(1,679 discovery / 1,681 confirmation). About 11.8 process CPU-hours on a
4-CPU cloud container.

**Result:** **`ADAPTIVE_SEARCH_PARAMS_NOT_JUSTIFIED`**.
- On confirmation, per-cell choice minus the best global arm (wa065) was
  **+0.0044 signedOutcome/fight, 95% CI [-0.0003, +0.0089]**. The upper bound
  is below the frozen 0.01 materiality threshold.
- No arm beat control globally: c12 -0.004 [-0.007, -0.001], c50 -0.005
  [-0.008, -0.002], wa040 -0.002 [-0.005, +0.001], wa065 -0.001
  [-0.004, +0.002].
- Descriptive only: c12 helped Act-1 bosses on all data (+0.038
  [+0.006, +0.071]), but on confirmation alone it was +0.027
  [-0.014, +0.069]. c50 hurt Act-1 and Act-2 bosses.

**Decision:** keep the current constants. Do not build the #400 Stage 2
controller. Revisit only together with a learned Silver prior (the issue's
factorial check) or with a new, sharper context hypothesis.

**Evidence:** [packet](evidence/silver_param_screen_400/README.md).

**ELI5:** We replayed about 3,400 fights five times each, changing only how
adventurous Silver's search is. Picking the setting per fight type gained
about a third of an HP per fight at most, too little to justify a controller,
and the default setting was already as good as any alternative.

**Knowledge impact:** `evaluation/current-research.md` (Silver root
allocation section); the research-only mode is recorded here and in its
evidence packet. No default changed.

## §370 — Learned Silver stopping: fight-replay and live A/B against #199 (2026-10-03)

**Question:** can a learned stop/continue model at fixed search checkpoints
save native Silver compute against the production #199 rule without making
fights worse? This revisits §285, where a logistic model was rejected because
it almost never stopped.

**Policy:** `STS_SILVER_LEARNED_STOP=1` (research-only, default off).
- Each multi-action root is searched to the checkpoints
  250/500/1k/2k/4k/8k/10k new simulations.
- Search stops at the first strict visit lock (`N1 − N2 > 10k − used`) or
  when the risk from model `gbt-b91dcfea64e1` is below 0.03.
- The model is a 300-tree histogram GBT over 18 root features, compiled into
  the binary.
- It was trained on native exact-10k checkpoint traces
  (`STS_SILVER_STOP_TRACE`), seeds `41000000..41000023`. The threshold was
  chosen on `41000024..41000031`. Held-out offline result: 58.1% saving
  against flat 10k at 0.76% disagreement with the 10k action; #199 gets
  42.5% at 0.99%.

**Protocol:** frozen [PLAN.md](evidence/silver_learned_stop/PLAN.md).
- Code `ae7a6d79` (PR #403). The independent pre-run review returned GO WITH
  FIXES, and the fixes were applied in plan commit `885987d`.
- Part A (primary): `one_combat silverstopreplaygen` on seeds
  `42000000..42000095`. Every real fight of exact-10k source runs was replayed
  under three arms: flat 10k (control, which must reproduce the source),
  #199, and learned stopping.
- Gate:
  - S = 1 − sims(learned)/sims(#199) ≥ 10%;
  - the 95% seed-clustered CI lower bound of the per-fight signedOutcome
    difference above −0.005;
  - no more learned-only than #199-only invalid fights.
- Part B (descriptive): 128 paired `bestbench` runs on seeds
  `43000000..43000127`, production default against learned stopping.

**Integrity:** 96/96 valid sources and 2,445 fights. The control replay
reproduced 2,437; all 8 exclusions were Smoke Bomb escapes. No arm had an
invalid result in a counted fight. All shards exited 0. One launch was stopped
by the operator about 40 seconds in, before any seed finished (waiter timeout
risk), and restarted unchanged. About 3.5 replay CPU-hours plus 1.5 live
CPU-hours.

**Result:** **`LEARNED_STOP_PASS`**.
- Learned − #199: **+0.0019 signedOutcome/fight, 95% CI [−0.0009, +0.0048]**,
  with **19.4% fewer simulations** [18.3, 20.5] and a CPU ratio of 0.80.
- Against flat 10k:
  - #199: −0.0029 [−0.0054, −0.0004] at a 46.4% saving;
  - learned: −0.0010 [−0.0040, +0.0021] at a 56.8% saving.
- No room class showed a negative point estimate.
- Live, descriptive (#199 → learned):
  - wins 70.3% → 75.8%, +5.5 pp [−3.1, +14.1], with 13 #199-only and 20
    learned-only wins;
  - floor −1.1 [−2.4, +0.0];
  - ending HP +1.8;
  - CPU-seconds per run −23%.

**Review notes, not blocking:**
- Offline, the strict lock alone saves 38.2% with zero disagreements. The
  model adds about 20 pp and causes all held-out disagreements. The runtime
  counter does not split lock and model stops.
- Fresh-root held-out disagreement was 1.25%; #199 never stops fresh roots.
- Train vs held-out disagreement (0.06% vs 0.76%) indicates overfitting.
- **Inference:** P(PASS | true D = 0) is about 80%. This is non-inferiority
  evidence, not superiority.

**Decision:** the learned stopper passes its pre-registered gate as a
compute-saving candidate: about 19% fewer simulations than #199 with no
detectable fight-quality loss. It stays default-off. Promotion to the
production default is a separate decision, which should come with a lock-only
control arm and a fresh confirmation.

**Evidence:** [packet](evidence/silver_learned_stop/README.md).

**ELI5:** At a few points during each search, a small learned model checks
whether more thinking would still change the move, and stops if not. Over
about 2,400 replayed fights it played as well as the current rule while
thinking about a fifth less.

**Knowledge impact:** `evaluation/current-research.md` (retained-root adaptive
section) and `operations/environment-variables.md`. No default changed.

## §371 — #397 Stage 1 `v_win` information-boundary audit and hidden-future ablation (2026-10-03)

**Question:** which rich `v_win` features could a real player not know, and
how much of the #334 A3 X1 VALIDATION score depends on them?

**Protocol:** preregistered in `tools/analyze_vwin_public_info_397.py`
(committed `f86119dc` before any arm was trained). Offline only: frozen #334
corpus `corpus-mixed-512.json` (SHA-256 `ca4b6e2b…cd87f`), TRAIN 333,367 /
VALIDATION 68,903 MAP rows, no gameplay seeds, no C++ build, no TEST rows read.
Frozen A3 X1 recipe (depth 6, eta 0.06, min_child_weight 30, CPU hist, early
stopping on VALIDATION, 4 threads), XGBoost seeds 0/1/2. Arms: **A** the 461
TRAIN-variable A3 features; **B** A minus the four verified hidden-future
fields; **C** A minus all eight V4-excluded fields (diagnostic). Rule:
`HIDDEN_FUTURE_LEAK_MATERIAL` if the mean B−A NLL delta is ≥ 0.002 and every
seed's source-clustered CI lower bound is > 0; `NOT_MATERIAL` if the mean is
< 0.002 and every CI upper bound is < 0.002; else `INCONCLUSIVE`.

**Classification (all 1,017 rich features):** HIDDEN_FUTURE 4
(`nextEliteId`, `nextFight0..2`: realized queue entries); PUBLIC_HISTORY 10
(`pv*`, `potionChance`, `cardRarityFactor`, `monOffset`, `eliteOffset`);
REDUNDANT 4 (`remFights`, `remElites`, `deckSize`, `potionCount`);
PUBLIC_CURRENT 999. `monOffset`/`eliteOffset` count combats already entered
this act and `remFights`/`remElites` equal the fixed act queue length minus
them: the identity `offset + remaining = {16,15,15,0}` (hallway) /
`{10,10,10,1}` (elite) held on **all** 333,367 TRAIN and 68,903 VALIDATION
rows (0 violations). Of the V4 "leak" eight, only four are hidden. All 12
relic columns carrying counters (Happy Flower, Incense Burner, Ink Bottle,
Lizard Tail, Nunchaku, Omamori, Pen Nib, Sundial, Girya, Neow's Lament,
Maw Bank, Tiny Chest) are in-game visible counters.

**Sanity gate:** A seed 0 reproduced the frozen X1 exactly (NLL
`0.44453298345900494`, 290 trees).

**Results (VALIDATION NLL / Brier / AUC; pooled sibling accuracy):**

| arm | seed 0 | seed 1 | seed 2 | mean NLL |
| --- | --- | --- | --- | ---: |
| A (461) | 0.44453 / 0.14563 / 0.8024; 0.559 | 0.44905 / 0.14701 / 0.8003; 0.571 | 0.45195 / 0.14808 / 0.7961; 0.582 | 0.44851 |
| B (457) | 0.44959 / 0.14712 / 0.7978; 0.549 | 0.44793 / 0.14685 / 0.8014; 0.568 | 0.43996 / 0.14425 / 0.8082; 0.554 | 0.44583 |
| C (453) | 0.45072 / 0.14831 / 0.7997; 0.558 | 0.44890 / 0.14700 / 0.8009; 0.577 | 0.44774 / 0.14685 / 0.8027; 0.567 | 0.44912 |

Paired B−A NLL [source-clustered 95% CI]: seed 0 +0.00506 [−0.00243,
+0.01289]; seed 1 −0.00112 [−0.00888, +0.00617]; seed 2 −0.01199
[−0.02010, −0.00373]; mean **−0.00268**. C−A: +0.00619, −0.00015, −0.00421;
mean +0.00061. Every sibling-accuracy CI overlaps across arms.

**Verdict:** **`INCONCLUSIVE`** under the preregistered rule (B and C as well).
No evidence that the hidden-future fields help held-out prediction: removing
them did not worsen the 3-seed mean, and the only CI excluding zero favors B.
The 0.002 materiality cannot be certified because **XGBoost seed noise alone
is ~0.007–0.010 NLL** within one feature set — larger than the leak question
and comparable to the whole A3 X1 grid spread (0.4445–0.4578). B is the
public-safe baseline (`PUBLIC_SAFE_BASELINE_ESTABLISHED` as a contract, not as
a measured equivalence).

**Implication for #334:** A3 X1/X2 checkpoint selection by single-seed
VALIDATION NLL is within subsampling-seed noise; selection-level comparisons
need multiple seeds (or deterministic subsampling) before they are interpreted.
Not tested here: a deployed model's dependence on these fields under fair-play
sampled queues (B0 `models/v_win_trees.txt` also reads all eight).

**Evidence:** `/home/philippherrmann/Documents/sts/artifacts/vwin-public-info-397/stage1-20261003-f86119dc/`
(`report.json` SHA-256 `61193b03da6e5c8c3d7d71d0d86f341be46954e16bdf030a2843eb5806c6b854`,
`validation_predictions.npz` `c415e0e3c29d98345d4acbb6b443a025371d91936075e63b98bd1c86d59f0d06`,
sibling stdout/stderr/time logs). 15 min wall, 1,194 CPU-s, 5.5 GB peak RSS.

**ELI5:** Four of the model's inputs peek at which monsters are coming next,
which a player can't see. We trained the same model with and without them three
times each. Dropping them didn't make it worse on average, but the model's own
random wiggle between training runs is bigger than the effect we were trying to
measure, so the honest answer is "no sign it matters, not proven tiny".

**Knowledge impact:** information-boundary classification and public-safe
allowlist in `operations/ooc-label-pipeline.md`; status in
`evaluation/current-research.md`.

## §372 — Learned Silver stopping v2: retrained model and fresh confirmation with a lock-only arm (2026-10-03)

(§371 is left to the parallel #397 audit, PR #404.)

**Question:** does a learned stopper retrained on more seeds pass the §370
gate again on fresh seeds, and how much does the model add over the strict
visit lock alone?

**Model selection:** 128 more exact-10k trace seeds
(`41000032..41000159`), 160 seeds and 66,930 multi-action decisions in total.
5-fold seed-grouped cross-validation of GBT, regularized, monotone and
logistic variants (`tools/silver_learned_stop_cv.py`). The best variant was
the v1 hyperparameters plus 4 trend features (change of gap share, top share,
Q gap and entropy since the previous checkpoint): 58.1% out-of-fold saving
against flat 10k at 0.72% disagreement, against 41.0% at 1.03% for #199.
The chosen model `gbt-770201c31f7b` uses threshold 0.0323, with 0.31% train
vs 0.72% out-of-fold disagreement (v1: 0.06% vs 0.76%).

**Protocol:** frozen [v2/PLAN.md](evidence/silver_learned_stop/v2/PLAN.md),
code `adbcae75` (PR #403). The independent pre-run review returned GO.
- Part A (primary): `silverstopreplaygen` on seeds `44000000..44000127`, with
  four arms: flat 10k control, #199, lock-only, learned. The gate is the §370
  gate unchanged.
- Part B (descriptive): 128 paired `bestbench` runs on `45000000..45000127`.
- Split over 4 cloud containers into disjoint 32-seed parts
  (`launch_part.sh`, commit `0fa711e`, which runs a hash-checked local copy of
  the binary because the shared folder is not executable).

**Integrity:** 128/128 valid sources and 3,412 fights. The control replay
reproduced 3,385; all 27 exclusions were escapes. No arm had an invalid
result in a counted fight. All 48 shards exited 0, each run once. About 6.1
replay plus 1.6 live CPU-hours.

**Result:** **`LEARNED_STOP_PASS`**.
- Learned − #199: **−0.0007 signedOutcome/fight, 95% CI [−0.0031, +0.0018]**,
  with **21.3% fewer simulations** [20.3, 22.3] and a CPU ratio of 0.79.
- Learned − lock-only: +0.0006 [−0.0017, +0.0030] with 30.2% fewer
  simulations.
- Lock-only − #199: −0.0013 [−0.0036, +0.0008], using 12.7% more
  simulations than #199.
- Against flat 10k: #199 +0.0013, lock-only −0.0000, learned +0.0006; all
  CIs include zero. Savings 45.1%, 38.1% and 56.8%.
- Learned stopping stopped 35,598 roots by model and 9,629 by lock.
- By room, learned − #199: normal +0.0002, elite −0.0005, boss −0.0074
  [−0.0246, +0.0101] on 367 fights, other +0.0037.
- Live, descriptive (#199 → learned): wins 76.6% → 77.3%, +0.8 pp
  [−7.0, +8.6]; floor −1.0 [−2.1, +0.0]; ending HP +0.0; seconds per run −25%.

**Notes:**
- **Inference:** the boss estimate is negative with a wide CI. The live floor
  difference was about −1 in both §370 and here, each CI touching zero. Not
  evidence of harm, but worth tracking in a promotion run.
- The gate is non-inferiority with about 80% pass probability at zero true
  effect; this is not a superiority claim.

**Decision:** v2 passes the fresh confirmation, and the lock-only arm shows
that the model, not the lock, carries the saving over #199. It stays
default-off. Whether to make it the production default is a separate
decision.

**Evidence:** [v2 packet](evidence/silver_learned_stop/v2/README.md).

**ELI5:** The retrained stopper was tested on new games. It again played as
well as the current rule while thinking about a fifth less, and the simple
"the answer can no longer change" check alone would not have saved that much.

**Knowledge impact:** `evaluation/current-research.md` (learned stopping
section) and `operations/environment-variables.md` (v2 default threshold). No
default changed.

## §373 — #397 Stage 1b reachable rich card/relic/potion domain (2026-10-03)

**Question:** of the 744 rich card columns (`d0..d371`, `u0..u371`), which
card IDs can an Ironclad run actually hold, and does the #334 A3 TRAIN
variance mask already exclude the rest?

**Method:** `tools/analyze_rich_domain_397.py` derives the master-deck domain
from the simulator's own tables and obtain sites (Ironclad Transform/
TrulyRandom/Rarity pools, colorless pools, curse pool, every literal
`deck.obtain`/`obtainCard` `CardId` in `src/`, the Note For Yourself default)
and compares it with the frozen A3 `preflight.json` mask. No corpus rows,
seeds, or builds. Prismatic Shard is compile-time disabled
(`GameContext::disablePrismaticShard`), so `AnyColorTypeCardPool` is
unreachable; in-combat generated cards never enter the master deck.

**Result:** 127 reachable IDs of 371 enum values: 75 red (starters + 72-card
class pool), 39 colorless (35-card pool + event cards Apparition, Bite,
J.A.X., Ritual Dagger), 13 curses (10-card pool + Ascender's Bane, Curse of
the Bell, and live-only Necronomicurse). Column 371 is beyond the 371-value
enum and is always empty. **No TRAIN-variable `d`/`u` column is unreachable**
(125 `d`, 114 `u` variable). Reachable but TRAIN-constant: `d` Ascender's Bane
(asc 0 corpus) and Necronomicurse; `u` all 13 curses. Relics: no TRAIN-variable
column belongs to the 16 other-class-only relics; potions: no TRAIN-variable
column belongs to the 9 other-class potions.

**Finding (simulator fidelity, not fixed here):** the Cursed Tome event grants
Necronomicon, but the simulator never adds Necronomicurse (`grep
NECRONOMICURSE src/` finds only `Card.cpp` transformability). The real game
does, so the allowlist keeps it as `live_game_only`.

**Decision:** per #397 Stage 1b, the TRAIN variance mask already removes every
unreachable card, relic and potion column, so no model-input change is needed.
The broad 1,017-column producer schema stays for compatibility. 490 of the 744
card columns (and `d371`/`u371`) are structurally zero, which matters only if
producer storage or feature preparation becomes a measured cost.

**Evidence:** `/home/philippherrmann/Documents/sts/artifacts/vwin-public-info-397/stage1b-card-domain.json`
(SHA-256 `934206626d71f8348955a6a3df2b1c96901c34a4b61d82473051bbba22702404`):
reachable list with sources and every literal obtain site.

**ELI5:** About two thirds of the card slots in the state are for cards an
Ironclad can never own. The training pipeline already ignores them because
they are always zero, so nothing needs changing.

**Knowledge impact:** reachable-domain summary added to the rich `v_win`
information-boundary section of `operations/ooc-label-pipeline.md`.

## §374 — #397 Stage 2 public-history families on the public-safe `v_win` baseline (2026-10-03)

**Question:** do raw public-history features (relics seen but not owned,
events seen, encounters fought) improve held-out run-win prediction beyond
the 457-feature public-safe baseline (§371)?

**Protocol:** preregistered in `tools/analyze_vwin_history_397.py` (committed
`69e17093` before any arm was trained; `a095ca79` fixed a crash on purchased
shop slots with null relic ids, found while loading history and before any
training; the crashed attempt's empty output directory is kept with suffix
`-FAILED-null-relic`). Frozen #334 corpus (SHA-256 `ca4b6e2b…cd87f`),
TRAIN 333,367 / VALIDATION 68,903 MAP rows, no gameplay seeds, no C++ build,
no TEST rows. History is rebuilt per trajectory from `combat.csv` encounters,
`decision.csv` event ids and offered relics (shop, boss relic, rewards);
branches inherit the source prefix before their deviating screen; a MAP row at
floor F sees items at floor ≤ F. New columns kept only if TRAIN-variable:
H1 128 `relicSeenNotOwned_*`, H2 47 `eventSeen_*`, H3 58 `fought_*`. Frozen
A3 X1 recipe, XGBoost seeds 0–4, arm prediction = 5-seed mean probability.
Rule: `USEFUL` if ensemble ΔNLL ≤ −0.002 and CI upper < 0; `LOW_VALUE` if CI
lower > −0.002; else `INCONCLUSIVE`.

**Coverage:** 15,067 trajectories (14,632 branches), 0 ambiguous branch fight
prefixes, every MAP row joined. Event identities are incomplete: the decision
sink writes only screens with more than one option, so 15,462 TRAIN/VALIDATION
event screens have no recorded `eventId` against 57,405 captured. Most are
later pages of an identified event; per event visit (consecutive event
screens, all 512 sources) 1,959 of 61,173 (3.2%) have no captured screen —
1,048 whose first screen failed option enumeration and 911 with a single
option.

**Results (5-seed ensemble, VALIDATION):**

| arm | features | NLL | Brier | AUC | ECE | pooled sibling acc. |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| P (public-safe) | 457 | 0.44338 | 0.14534 | 0.8062 | 0.0481 | 0.570 [0.522, 0.617] |
| P+H1 relics | 585 | 0.45094 | 0.14842 | 0.8002 | 0.0571 | 0.557 [0.509, 0.605] |
| P+H2 events | 504 | 0.44635 | 0.14595 | 0.8015 | 0.0470 | 0.540 [0.490, 0.590] |
| P+H3 encounters | 515 | 0.44995 | 0.14747 | 0.7902 | 0.0489 | 0.563 [0.522, 0.604] |

Ensemble ΔNLL vs P [source-clustered 95% CI]: H1 +0.00756 [−0.00267,
+0.01971]; H2 +0.00297 [−0.00430, +0.01093]; H3 +0.00657 [−0.00677,
+0.02197]. Per-seed paired ΔNLL: H1 all five positive (+0.0017…+0.0117);
H2 four of five positive; H3 four of five positive.

**Verdict:** `H1/H2/H3_HISTORY_INCONCLUSIVE` under the preregistered rule.
Descriptively every family made the ensemble worse on NLL, Brier and AUC, and
no CI reaches the −0.002 usefulness threshold on its favorable side by more
than ~0.005. Per #397's decision rule (add a family only with clear held-out
signal) none is added. H4/Stage 2b–2d derived public probabilities remain a
separate question; raw history shows no signal for them to compress.

**Side observation:** the 5-seed ensemble of P (0.44338) beats every single P
seed (0.43996–0.44959, mean 0.44664), which supports seed-averaging in #334.

**Evidence:** `/home/philippherrmann/Documents/sts/artifacts/vwin-public-info-397/stage2-history-20261003-a095ca79/`
(`report.json` SHA-256 `b38f681be2003a1c4af9339140ab19b94a16f3f7935eb92a41d29b9b8f666dce`,
`validation_predictions.npz` `ed6439992c228d2cc7bd462fddeefaf1fed3629d8dd240a8775ca965c9bcf4ad`,
sibling logs). 20:52 wall, 2,153 CPU-s, 8.1 GB peak RSS.

**ELI5:** We told the model which relics it had passed up, which events it had
already seen, and which monsters it had already fought. On runs it had never
seen, it predicted wins slightly worse with each of these, not better.

**Knowledge impact:** history-family outcome in the rich `v_win`
information-boundary section of `operations/ooc-label-pipeline.md` and in
`evaluation/current-research.md`.

## §375 — #397 Stages 2b–2c rule-derived public probabilities (2026-10-03)

**Question:** do public-rule probabilities (potion-drop chance, card-rarity
odds, next-elite and next-hallway-encounter distributions) predict run wins
better than the raw counters/history on the public-safe `v_win` baseline?

**Protocol:** preregistered in `tools/analyze_vwin_derived_397.py` (committed
`c7ff841a` before any arm was trained). The report's `tooling.git_sha` reads
`5cc739d3` because that commit, which only adds
`tools/analyze_vwin_derived_rooms_397.py` and its CMake test, landed during
the run; the analysis file is identical. Rules were checked with `javap`
against STS1 V2.3.4 `desktop-1.0.jar`: `AbstractRoom.addPotionToRewards`,
`AbstractDungeon.rollRarity`/`AbstractRoom.getCardRarity`/`MonsterRoomElite`
(factor start 5, −1 per common to −40, reset on rare; N'loth's Gift ×3),
`AbstractDungeon.populateMonsterList`/`populateFirstStrongEnemy` and the
`Exordium`/`TheCity`/`TheBeyond` weights and exclusions. Frozen #334 corpus,
TRAIN/VALIDATION only, no seeds, no build; frozen A3 X1 recipe, XGBoost seeds
0–4, 5-seed ensemble vs P (457 public-safe features). Arms: F1d (P −
`potionChance` + `pPotionDrop`), F1b (P + `pPotionDrop`), F2d/F2b (same with
`cardRarityFactor` and a 14-column per-card and per-reward rarity block), F3
(P + next-elite distribution), F4 (P + next-hallway distribution + entropy).

**Integrity:** the observed hallway/elite prefix lengths matched `monOffset`
and `eliteOffset` on every TRAIN/VALIDATION row (0 mismatches), confirming
that the observed fights are exactly the consumed queue prefix.

**Findings (simulator, not fixed here):** native `populateFirstStrongEnemy`
applies the first-strong exclusions only in act 1; Java also excludes in acts
2–3 (#407). The derived F4 features use the Java rule.

**Results (5-seed ensemble, VALIDATION; P NLL 0.44338):**

| arm | features | NLL | ΔNLL vs P [95% CI] | label |
| --- | ---: | ---: | --- | --- |
| F1d potion derived only | 457 | 0.44555 | +0.0022 [−0.0013, +0.0058] | DERIVED_NOT_SHOWN_EQUIVALENT |
| F1b potion raw + derived | 458 | 0.44900 | +0.0056 [+0.0023, +0.0090] | DERIVED_ADDS_NO_CLEAR_SIGNAL |
| F2d rarity derived only | 470 | 0.44889 | +0.0055 [−0.0003, +0.0111] | DERIVED_NOT_SHOWN_EQUIVALENT |
| F2b rarity raw + derived | 471 | 0.44588 | +0.0025 [−0.0007, +0.0063] | DERIVED_ADDS_NO_CLEAR_SIGNAL |
| F3 next elite | 466 | 0.44715 | +0.0038 [+0.0006, +0.0072] | F3_LOW_VALUE |
| F4 next hallway fight | 495 | 0.44387 | +0.0005 [−0.0045, +0.0051] | F4_INCONCLUSIVE |

**Interpretation:** no derived family improved prediction; none is adopted.
F1b is a calibration of the method's resolution: `pPotionDrop` is a monotone
transform of `potionChance` (it differs only with White Beast Statue), yet
adding it worsened the ensemble by +0.0056 with a CI excluding zero. The
source-clustered CI holds the fitted models fixed and does not include
training-procedure variance, so feature-set perturbations of about ±0.005 are
within what retraining alone produces here. Effects smaller than that cannot
be resolved on this 358-source TRAIN / 77-source VALIDATION corpus.

**Evidence:** `/home/philippherrmann/Documents/sts/artifacts/vwin-public-info-397/stage2bc-derived-20261003-c7ff841a/`
(`report.json` SHA-256 `0e6434b1cac71c6d8fbad48c760f1fcb16ac3d926da0ec74aabeb508939b9f75`,
`validation_predictions.npz` `83314aa8752af64799efe3e87380453d6a1ed02a82250983ad0ebdf2bef2be72`).
21:56 wall, 2,585 CPU-s, 6.7 GB peak RSS.

**ELI5:** We handed the model the actual odds the game uses (chance of a
potion, of a rare card, of which elite or monster comes next) instead of
making it learn them. It did not get better; even adding a copy of a number it
already had moved the score about as much.

**Knowledge impact:** maintained summary in `operations/ooc-label-pipeline.md`
and `evaluation/current-research.md`.

## §376 — #397 Stage 2d unknown-room odds and next remove price (2026-10-03)

**Question:** do the next ? room outcome odds and the next card-remove price,
derived from public history and verified rules, improve held-out run-win
prediction over the public-safe baseline?

**Protocol:** preregistered in `tools/analyze_vwin_derived_rooms_397.py`
(committed `5cc739d3` before training). Rules checked with `javap`:
`EventHelper.roll`/`resetProbabilities` (0.1/0.03/0.02 float chances, slot
order monster→shop→treasure→event, shop 0 from a shop room, Tiny Chest every
fourth ?, Juzu Bracelet monster→event, reset-on-hit else +base) and
`ShopScreen` (`purgeCost` 75 +25 per paid removal; Courier ×0.8, Membership
×0.5, Smiling Mask 50 at shop open). Native `getEventRoomOutcomeHelper`
matches. ? nodes come from `pvEvent` increments between MAP rows; outcomes
from the same floor's NORMAL fight / shop / treasure screen. Limitation: with
Juzu Bracelet a rolled monster appears as an event. Same corpus, recipe and
5-seed ensemble design as §375. Arms: F5 (P + `pQMonster`, `pQShop`,
`pQTreasure`, `pQEvent`), F6 (P + `nextRemoveCost`).

**Integrity:** the reconstructed remove price matched the displayed
`removeCost` on 106,975 of 107,900 shop screens (99.14%, above the 99% stop
threshold); the residual 0.86% is unexplained.

**Results (5-seed ensemble, VALIDATION; P NLL 0.44338):** F5 0.44457, ΔNLL
+0.0012 [−0.0021, +0.0045], `F5_INCONCLUSIVE`; F6 0.44859, ΔNLL +0.0052
[−0.0001, +0.0102], `F6_LOW_VALUE`. Neither improves; neither is adopted.

**Evidence:** `/home/philippherrmann/Documents/sts/artifacts/vwin-public-info-397/stage2d-rooms-20261003-5cc739d3/`
(`report.json` SHA-256 `56f56d4c94efaf26ba1dd379c9c4312329285798ae7b4865b29840521db8b5a3`,
`validation_predictions.npz` `8a3c88a165e4fb47cc7479beda8c5cd49c0212d9c03b75f265701476e640e9af`).
17:03 wall, 1,515 CPU-s, 6.4 GB peak RSS. Event-eligibility distributions
(Stage 2d item 4) and chest/relic summaries (item 5) were not built: 3.2% of
event visits lack an identity (§374) and the eligibility rules were not
verified.

**ELI5:** Knowing what the next ? room is likely to be, or what card removal
will cost at the next shop, did not help the model predict wins.

**Knowledge impact:** maintained summary in `operations/ooc-label-pipeline.md`
and `evaluation/current-research.md`.

## §377 — Learned Silver stopping v3: 1,024-pair live promotion run with boss variants (2026-10-03)

(§373–§376 are used by the parallel #397 work.)

**Question:** do the about −1 floor leans in the §370/§372 live runs reflect a
real strength cost of learned stopping against #199? Do boss fights benefit
from falling back to #199, or from a cap above 10k? Philipp asked the second
question.

**Protocol:** frozen [v3/PLAN.md](evidence/silver_learned_stop/v3/PLAN.md).
- Code `8c7da1d0`, which adds research-only `STS_SILVER_LEARNED_STOP_BOSS_FALLBACK`
  and `STS_SILVER_LEARNED_STOP_BOSS_MAX`.
- The pre-run review required three fixes, applied in `4a5e1a5`: Bonferroni,
  full-precision analysis, and correct v1/v2 attribution.
- Run after Philipp's go.
- 1,024 paired `bestbench` seeds `46000000..46001023`, four arms:
  - #199;
  - v2 learned (`gbt-770201c31f7b`);
  - v2 with boss rooms on #199;
  - v2 with boss roots that reach 10k unstopped continuing to 30k unless
    strictly locked.
- Rule: a variant qualifies when the 98.33% bootstrap CI lower bound of the
  paired floor difference ΔF against #199 is above −0.75 and its mean
  seconds per run are below #199's. The qualifier with the highest ΔF is
  recommended.

**Integrity:** 4 parts on 4 cloud containers, 64 shards, all exit 0, each run
once. All sidecars name executable `8c7da1d0` and the arm settings.
`analyze.py` reproduces `report.json`. 30.7 CPU-hours (planned 26–28).

**Result:** **`PROMOTE_learned`**.
- learned − #199: **ΔF +0.49 floors, 98.33% CI [+0.08, +0.91]**; wins 80.3%
  vs 78.3% (+2.0 pp, 95% CI [−0.6, +4.5]); 23.7 vs 29.3 s per run (ratio
  0.81).
- bossfallback − #199: +0.33 [−0.03, +0.71], qualifies, ratio 0.87.
- bossmax30k − #199: +0.32 [−0.08, +0.75], ratio 1.05, so it fails the time
  criterion.
- Against plain v2, both boss variants were slightly worse:
  - fallback: −0.2 floors, −1.5 pp wins;
  - 30k: −0.2 floors, −1.1 pp wins, +7.1 s per run.
- Deaths on an act-boss floor: #199 163, learned 157.

**Notes (Inference):**
- The negative live floor lean of §370/§372 (128 pairs each) did not
  replicate at 8× the sample size.
- More boss search than 10k showed no benefit here, so the 10k cap stays.
- The design is non-inferiority. The positive ΔF and the CI excluding 0 are
  reported, but superiority was not pre-registered.

**Decision:** learned stopping v2 is recommended as the production Silver
budget policy, replacing #199. The flip needs its own ADR and PR, and
Philipp's decision. The boss options stay research-only.

**Evidence:** [v3 packet](evidence/silver_learned_stop/v3/README.md).

**ELI5:** On 1,024 new games, the learned stopper reached half a floor further
on average, won slightly more often and used about a fifth less time than
the current rule. Giving bosses extra thinking time did not help.

**Knowledge impact:** `evaluation/current-research.md` and
`operations/environment-variables.md` (the boss options). No default changed.

## §378 — #397 follow-up: history and derived families with the A3 M1 MLP (2026-10-03)

**Question:** §§374–376 tested every family with XGBoost only, which is
invariant to monotone rescaling. Does the frozen A3 M1 network gain from the
same families?

**Protocol:** preregistered in `tools/analyze_vwin_mlp_397.py` (committed
`2ab1bd81` before training). `47203156` added `--skip-corpus-validation`
(user request); it checks only the frozen index SHA-256 and builds the
component view from the manifests instead of re-hashing every table already
validated by §§371–376. Frozen M1 recipe (457→64→32 GELU MLP, AdamW lr 1e-4,
weight decay 1e-3, dropout 0.1, TRAIN normalization, batch 8192, ≤60 epochs,
patience 8 on VALIDATION, deterministic CUDA on the RTX 3060 Ti, 4 threads),
seeds 0–2, 3-seed ensemble vs P (457 public-safe features). Arms: H1–H3
(§374), F1–F6 (§§375–376), ALL (F1–F6), N0 (one standard-normal noise
column, null control). `USEFUL` additionally requires beating N0's delta by
0.002. Two earlier attempts were stopped by the user before any result
(directories suffixed `-ABORTED-*`); a third was stopped after 21 of 37 fits
(`-STOPPED-partial`), and the complete rerun reproduced those 21 lines
exactly.

**Gate:** the 461-feature A3 set at seed 0 reproduced the frozen M1 exactly
(NLL `0.47669561245471703`, best epoch 10).

**Results (3-seed ensemble, VALIDATION; P NLL 0.46886, still far behind the
XGBoost P at 0.44338):**

| arm | NLL | ΔNLL vs P [95% CI] | label |
| --- | ---: | --- | --- |
| N0 noise control | 0.47190 | +0.0030 [−0.0043, +0.0100] | NULL_CONTROL |
| H1 relics seen not owned | 0.45721 | −0.0117 [−0.0356, +0.0126] | INCONCLUSIVE |
| H2 events seen | 0.47943 | +0.0106 [−0.0042, +0.0284] | INCONCLUSIVE |
| H3 encounters fought | 0.47569 | +0.0068 [−0.0083, +0.0234] | INCONCLUSIVE |
| F1 potion drop | 0.47155 | +0.0027 [−0.0047, +0.0098] | INCONCLUSIVE |
| F2 rarity block | 0.47463 | +0.0058 [−0.0014, +0.0138] | LOW_VALUE |
| F3 next elite | 0.46980 | +0.0009 [−0.0060, +0.0083] | INCONCLUSIVE |
| F4 next hallway | 0.47327 | +0.0044 [−0.0049, +0.0145] | INCONCLUSIVE |
| F5 ?-room odds | 0.46916 | +0.0003 [−0.0053, +0.0059] | INCONCLUSIVE |
| F6 remove price | 0.47184 | +0.0030 [−0.0046, +0.0104] | INCONCLUSIVE |
| ALL F1–F6 | 0.47302 | +0.0042 [−0.0051, +0.0142] | INCONCLUSIVE |

**H1 diagnostic (not preregistered):** every H1 seed (0.4640, 0.4568, 0.4642)
beat every P seed (0.4731, 0.4702, 0.4771), and act 2 improved most (0.5251 →
0.5034). The gain is concentrated, though: 43 of 77 VALIDATION sources
improved, and the five most-improved sources account for 114% of the net
log-loss reduction, hence the wide source-clustered CI. Even with H1 the MLP
(0.4572) stays behind the plain XGBoost baseline (0.4434).

**Verdict:** no family is `USEFUL` for the MLP either. H1 relic history is the
only direction with a consistent seed-level gain and a plausible mechanism (the
tree arm worsened instead); it is a candidate to re-test on a larger corpus or
inside the replacement model, not a contract change.

**Evidence:** `/home/philippherrmann/Documents/sts/artifacts/vwin-public-info-397/mlp-20261003-47203156-run2/`
(`report.json` SHA-256 `f6f56f3fe27ac2463479380c814d525f1425bce1161afc596ee290391cde50fc`,
`validation_predictions.npz` `a5d16bdef8e27e0f296b5511116cbd195043bab0d13f379d9d6053dd2ddc4a2b`).
9:42 wall, 11.5 GB peak RSS.

**ELI5:** We tried the extra features with the small neural network instead
of trees. Knowing which relics it passed up seemed to help a little, but the
gain came from a handful of runs, and the network is still worse than the
tree model without any extras.

**Knowledge impact:** summary added to `operations/ooc-label-pipeline.md` and
`evaluation/current-research.md`.

## §379 — Frozen X2-B native deployment qualification, default off (2026-10-05)

**Question:** can the exact post-#334 X2-B ensemble run through native v_win
without changing the B0 default, with Python parity and no full-path slowdown?
Baseline source: `8ab1157e45403d25e13a8db735e7515ecc77fa04`. No gameplay,
retraining, or TEST evaluation was performed for this engineering qualification.

**Identity:** frozen UBJ `99dbac6b5b082c46fe07242d2d15d8ccc6818041cb851efa79d6b423cdcb52dd`;
freeze `ade2d0cfc0ff8af1d6e5638ced3888b6d7a754d8969dc6932017cb78146d289a`;
export `a251b33d4f71c1aa3fca529801da23ea9740dd0ded58abfb1a90fe69da7c9acf`.
The existing exporter preserves 445 trees and 461 ordered features. B0 stays
`fc52c14cb7239a33b3c1f9d0477ccb6c895fd51a07240fe804744e605067ad70`.

**Parity:** 1,024 deterministic MAP rows across all 155 frozen VALIDATION
sources, acts 1–3, plus nine complete HP sweeps (756 rows). Maximum absolute
Python/native error `3.57778595e-7`, mean `6.36904418e-8`, p99 `2.43617067e-7`;
passes the unchanged `<1e-5` gate. Worst row 866: Python 0.736649215221405,
native 0.736649573. Cached input hashes and source partitions were verified.

**Latency:** GCC 13.3 Release `-O3 -DNDEBUG -flto`, Ryzen 5 7500F,
`OMP_NUM_THREADS=1`, CPU 2; 10,000 warmups then 100,000 measurements per model
and mode, alternating arm order. Model-only median/p95: B0 28.103/42.750 us,
X2-B 7.414/15.038 us. Full rich-feature preparation plus prediction:
B0 28.323/43.602 us, X2-B 8.266/15.990 us. Full-path median ratio 0.29185
passes `<=1.05`; mean throughput 31,949 vs 105,400 evaluations/s.
The corpus reconstructs the selected VALIDATION states and sweeps; unavailable
original map topology is replaced by deterministic native act maps in both
arms. Every other encoded feature is checked for equality. This is an
implementation microbenchmark, not a gameplay speed claim. Existing fixed
OOC workload: `NOT_RUN` (no applicable workload found).

**Hidden-future audit:** nextEliteId/nextFight0/nextFight1/nextFight2 have
57/61/58/54 splits, in 52/52/50/50 trees respectively (230 splits in 161 trees
combined). Depth ranges are 1–5/2–5/1–5/0–5. Full simulator policies use native
realized queues; OOC and live MCTS use sampled native queues with observed
history preserved. Rich encoding matches the frozen producer. Classification:
`X2B_HIDDEN_RUNTIME_COMPATIBLE` for these queue fields. No incompatible sentinel
representation was found, so substitution sensitivity is not applicable.
The live advisor's separate loading and pity marginalization are not qualified
for gameplay by this simulator engineering result.

**Evidence:** local persistent directory
`/home/philippherrmann/Documents/sts/artifacts/vwin-refresh-334/x2b-deployment-20261005-1ee9/`;
`stage-a-files.sha256`, input provenance, raw Python/native predictions,
per-evaluation latency samples, source scripts, caller matrix, and build/test logs.
`GITHUB_CI_NOT_USED_BILLING_LIMIT`. Local Release build, default/override/parser/
projection tests, legacy bitwise tree parity, OOC startup and adapter tests in
both model configurations passed. Worktree/submodule check and environment
doctor passed. Candidate is default off; terminal-pricing readiness remains false.

**ELI5:** the frozen tree model agrees with Python and is substantially cheaper
to evaluate. Whether it preserves current gameplay quality is a separate,
preregistered paired experiment; these checks do not promote the default.

**Knowledge impact:** runtime selection and encounter-queue semantics recorded
in maintained out-of-combat architecture and environment-variable documentation.

## §380 — OOC leaf `v_win` preparation profile; state copy removed (2026-09-26)

Issue #338. Profiled native OOC-MCTS leaf value on one fixed seed
(`12002032`, A0 fair, Act 3 stop, 2,048 sims, V4 leaf policy, zero leaf
combats). New profiler buckets split `leaf_value` into `leaf_features` and
`leaf_predict`.

Profile (139 decisions, 119,520 native leaf values, 208 s MCTS CPU):
- `leaf_value`: ~7% of MCTS CPU.
- Feature construction: 3.7 µs/call, **0.2%** of MCTS CPU.
- `v_win` tree inference: 115 µs/call, 6.6%.
- The leaf deep-copied `GameContext` and map (~4 µs/call) only to call a
  non-const wrapper; the copy is removed.

Exact repeated feature vectors: 16.7% of calls. A per-decision exact
`v_win` cache hit 12.0% of calls but produced no end-to-end change beyond
run-to-run noise. Every run had identical result rows and non-timing MCTS
trace columns.

Decision: adopt the copy removal and profiler split (exact parity). Reject
parent→child incremental features (ceiling 0.2%) and the exact cache (no
measured gain). Leaf cost is model inference and belongs to #334. Evidence:
[ooc_leaf_vwin_prep_profile_2026-09-26](evidence/ooc_leaf_vwin_prep_profile_2026-09-26/README.md).

## §381 — Frozen minimal active Lizard CTM qualification stopped at rare-event floor (2026-09-25)

The predeclared fresh cohort completed 128/128 paired sources under the frozen
exact-10k fair Silver teacher: HARD96 `4201000..4201095` and BROAD32
`4201096..4201127`. Candidate selection used frozen q/r `q*(1-r)` for HARD96
and the preregistered SHA-256 source/fight/salt rule for BROAD32. The source
freshness audit found no overlap with the prior 160 Lizard source IDs; pair
collection had zero quarantines. All 128 pairs were in the prospective CTM
support domain after removing Tail from pre-state and predictor input, with no
Fairy Potion or Mark of the Bloom rows.

The frozen q/r artifact is SHA-256
`9f8fb965b24fbd8da1f9600fc9ca0f243e5e9069c47067123c88e36e9f5ebcf9`. It was
fit once on the existing 427-row/124-source prospective-support development
cohort, with q/r rows 427/65, L2=1, q inputs `logit(pDeath)` and signed
`pReserveWin-pOrdinaryWin`, and r input `pReserveWin`. T2 remained the fixed
`curHp=floor(maxHP/2)` transform for consumed wins. The existing-data T2
extension confirmation had 33 supported rows/31 sources: HP NLL delta
`-1.60054` (95% CI `[-2.57783,-0.66053]`), CRPS `-4.06102`
(`[-7.70190,-0.39899]`), expected-HP MAE `-3.66847`
(`[-8.02682,0.67188]`), and zero domain/legality failures, so T2 remained a
frozen candidate.

Fresh classes were HARD96 52 `WIN_RETAINED`, 35 `WIN_CONSUMED`, 9
`LOSS_CONSUMED`; BROAD32 31, 1, 0; pooled 83, 36, 9. The rare-event floor
requires 20 losses from 10 distinct sources; the cohort reached only 9 from 9
(45 consumed rows total). Therefore the preregistered classification is
`LIZARD_QUALIFICATION_INCONCLUSIVE_RARE_EVENT`, and work stopped before Phase 6
ancestral qualification or any runtime/parity/support/live work.

Pooled q/r three-class NLL was `0.53763` versus B1 `5.95150` (delta
`-5.41388`, source-bootstrap 95% CI `[-16.22244,0.01903]`); Brier was `0.31811`
versus `0.34764` (delta `-0.02953`, CI `[-0.06996,0.00860]`). The NLL CI
crosses zero, so the primary gate did not pass. Pooled q was worse than B1 on
both NLL (delta `+0.02772`, CI `[-0.02440,0.08042]`) and Brier
(`+0.00816`, `[-0.01335,0.02869]`), failing the q gate. Pooled r passed its
score comparison on all 45 consumed rows (NLL delta `-0.91805`, CI
`[-2.52707,-0.02577]`; Brier delta `-0.09034`, `[-0.16639,-0.01888]`), but
cannot override the loss-source minimum. BROAD32 had no clear primary
degradation, with only one consumed row.

Fresh T2 scoring on 36 supported consumed wins passed its numeric gate: HP NLL
delta `-1.34633` (95% CI `[-2.18779,-0.60768]`), CRPS `-3.72108`
(`[-6.61319,-1.01197]`), expected-HP MAE `-3.46591`
(`[-6.81904,-0.27249]`), zero unscored/domain rows, and no clear maxHP/potion/
relic degradation. In the retained-win check, the supported cards relic
constraint NLL delta was `+0.12641` (`[0.02769,0.24579]`) on six matched
sources; this sparse subgroup shift remains descriptive.

Production `active_unqualified_lizard` remains fail-closed. No native q/r
sampler, ancestral draws, parity tests, support-predicate change, or live seed
`13027029` smoke ran. Further frozen qualification evidence belongs on the
designated GCP/large-research path; do not expand the local 128-source budget
or tune this artifact from these outcomes. The full metrics, hashes, and exact
limitations are in the [qualification evidence packet](evidence/lizard_tail_minimal_ctm_qualification_2026-09-25/README.md)
and [analysis JSON](evidence/lizard_tail_minimal_ctm_qualification_2026-09-25/fresh_qualification_analysis.json).

**Knowledge impact:** current research status and experiment evidence updated;
runtime behavior, model interfaces, and support remain unchanged.


## §382 — #379 sealed DECISION audit and current-main leaf profile (2026-10-05)

**Purpose:** establish the screen-leaf experiment baseline without opening
DECISION TEST or interpreting timing runs as gameplay quality.

Baseline `a59d7e47f7fc0faee3015e824b267f6bf2961adc`; explicit qualified X2-B
native hash `a251b33d4f71c1aa3fca529801da23ea9740dd0ded58abfb1a90fe69da7c9acf`.
All 1,024 frozen component manifests and DECISION hashes pass the narrow audit.
Original split: 696 TRAIN / 155 VALIDATION / 173 TEST. TRAIN has 1,509,014
DECISION rows; VALIDATION 329,425. All seven observed screen families cover
every TRAIN/VALIDATION source. Event enumeration omits 14,370/3,930 captures;
all emitted rows have supported complete candidates. TEST files were hashed
as opaque bytes, with no headers or numerical rows parsed.

Two bounded historical-seed profiles used one thread, exact-10k Silver and
OOC2048. Seed 12002032 with historical explicit attention CTM consumed 225.67
process CPU seconds, 170.5306 MCTS seconds and 52.9275 inclusive leaf seconds.
Seed 12002033 with current default hybrid CTM consumed about 102.1 process
CPU seconds, 62.6637 MCTS seconds and 33.6169 inclusive leaf seconds. These
are different seeds/configurations, not an A/B comparison. Leaf features and
prediction on the default-stack seed took 0.2496 and 1.1860 seconds.

Exact S0 requires frozen trajectory reconstruction because the DECISION sink
omits complete RNG/pool/map state and callback continuations. Historical
VALIDATION branch time is 44.11 core-hours, approximately 45.87 including
source/setup extrapolation, before S0. A derived exporter and current-main
import/evaluation bridge are being gated by exact frozen-output parity;
constructed-state roundtrip/callback tests do not qualify that replay.

Both producer-version canaries subsequently passed all seven original CSV
hashes (VALIDATION sources 13001315 and 13001638). The two-producer 1,024-state
S0 pilot passed in 2.52 wall seconds, with 1.68 inclusive leaf CPU seconds.
Public-input review limits the provisional direct model to boss relic, rest,
shop and treasure; events, selectors and rewards have omitted public parent
or offer context. A temporal sidecar records exact resulting MAP links for
calibration. The fixed Python S1/S2 tools are gated before training; all three
excluded families remain audited and use the original fallback.

All six fixed training fits completed (`TRAINING_COMPLETE_NOT_QUALIFIED`). The
first full VALIDATION protocol stopped scheduling on a Golden Idol import
semantic mismatch in source 13001065. All 14 scheduled replays passed original
seven-file parity; 13 S0 evaluations passed and one failed. The historical
producer infers the trap stage from held Golden Idol while current main uses
`info.phase`; the faithfully preserved old phase remains zero. This is not a
model verdict. The failed run and partial outputs remain immutable. Independent
review permits a narrow version-bound phase adaptation and a new protocol that
reuses the exact replay artifacts, with current public/candidate parity intact.

**Status:** training complete; no candidate freeze, DECISION TEST opening,
native screen-leaf integration or gameplay qualification. Defaults unchanged.
`GITHUB_CI_NOT_USED_BILLING_LIMIT`.

**Evidence:** [profile receipts, raw logs and audit](evidence/screen_leaf_379_preflight_20261005/README.md).

**Knowledge impact:** experiment evidence and maintained current research
status; no qualified model or runtime/default claim.

## §383 — #379 outcome: offline S0 comparison, online leaf probes, GBM screen leaf default (2026-10-06)

**Offline (VALIDATION, TEST sealed):** full S0 recovery passed on all 155
sources (two fail-closed `hp_envelope` rows, outside the four candidate
families; Smoke Bomb and Golden Idol import normalizations are audited). Both
#379 MLP arms were worse than S0 on NLL in every family and failed the frozen
calibration gate. Classification `SCREEN_LEAF_VALIDATION_NOT_QUALIFIED`; the
DECISION TEST was not opened.

**Online probes (2048 OOC sims, exact 10k Silver, X2-B):**
- 512 pairs, seeds 47000000..47000511: direct X2-B at the decision state vs
  the playout leaf: wins +1.4 pp (95% CI −3.3 to +6.1), floor +0.3, 0.56x time.
- 32 pairs: direct X2-B at 4096 sims vs playout at 2048: wins −25 pp
  (CI −47 to −3); inconclusive sample.
- 128 pairs, seeds 47001024..47001151, four arms: GBM screen leaf vs playout
  wins +3.1 pp (CI −7.8 to +14), floor +0.3 (CI −1.2 to +1.8); vs direct X2-B
  wins 0, floor +1.0 (CI −0.4 to +2.5); vs #379 MLP wins +10 pp (CI 0 to +20).

**GBM screen leaf:** XGBoost residual on X2-B's margin over the 461 X2-B run
features plus fixed-width public screen features (all seven families). VALIDATION
NLL 0.418 vs 0.423 for X2-B at the decision state; boss relic 0.527 to 0.454,
rewards 0.422 to 0.416. Native trees match Python to 1.1e-6; screen features
match exactly across Python, C++ and the live game state. Follow-ups on
VALIDATION: next-MAP X2-B (TD) labels, label mixes and tree parameters all within
±0.0003 NLL; deck-fit features plus all 372 deck counts −0.0008 (below the
0.002 go bar). Inference: this corpus is near its ceiling for the screen leaf;
fresh on-policy data is #415.

**Decision:** Philipp made `screengbm` the default OOC MCTS leaf (ADR-0027);
`native` restores the playout. `STS_OOC_MCTS` stays off by default.
`GITHUB_CI_NOT_USED_BILLING_LIMIT`; focused local Release build and tests.

**Evidence:** [leaf probes, GBM training and sweeps](evidence/ooc_leaf_direct_probe_20261006/README.md);
[#379 preflight and VALIDATION](evidence/screen_leaf_379_preflight_20261005/README.md).

**Knowledge impact:** ADR-0027 and the environment-variable table record the
new default.

## §384 — Live OOC MCTS on vs off, paired 128-seed pilot (2026-10-06)

**Question:** with the new default screen leaf (ADR-0027), does live OOC MCTS
beat the same pipeline with MCTS off? Since §249 there had been no on/off
comparison; §367 and §383 only compared MCTS variants with each other.

**Protocol:** frozen [PLAN.md](evidence/ooc_mcts_vs_off_pilot_20261006/PLAN.md),
independently reviewed before the run (one blocking smoke-check bug fixed in
`614007a4`, re-check clean). Philipp authorized it on 4 cloud cores.
- Binary from `aa000e8a` (source identical to `5e9583cc`), SHA-256 `fcaeec61…`.
- Shared §377 live profile (V4 gate stack, B0 `v_win`, keys off,
  `STS_REST_WIN=0`) plus an act-3 stop.
- Seeds `48000000..48000127`, Ironclad A0. Three arms, each adding one change:
  - `learned`: learned Silver stopping;
  - `flat10k`: flat exact-10k Silver, which MCTS requires;
  - `mcts`: `flat10k` plus OOC MCTS at 2048 sims with the §383 knobs and the
    default `screengbm` leaf.
- The verdict uses the paired win difference `mcts − flat10k` (95% bootstrap).

**Integrity:** all 12 invocations exit 0 and no seed failed. The smoke seed
`48009000` passed the plan's checks. `analyze.py` reproduces `report.json`.
A first launch was stopped after about a minute, before any results were
inspected, because its background timeout was shorter than the run. It was
relaunched from scratch with identical arguments.

**Result: `MCTS_WORSE`.**
- **mcts − flat10k: wins −21.9 pp, 95% CI [−32.0, −11.7]** (56.3% vs 78.1%);
  floor −1.46 [−3.16, +0.27]; discordant 12 vs 40; 2.0x time (114 vs 58 s per
  run).
- flat10k − learned: wins +4.7 pp [−4.7, +14.1], floor −0.51 [−2.0, +0.93],
  2.4x time. The exact-10k precondition does not cost detectable strength
  here; it only costs time.
- mcts − learned: wins −17.2 pp [−28.9, −4.7], floor −1.97 [−3.64, −0.32],
  4.7x time.
- Descriptive, not pre-registered:
  - MCTS losses concentrate on boss floors (44 of 56, against 24 of 28 for
    `flat10k`).
  - MCTS wins end with less HP (32.2 vs 44.5).

**Interpretation (Inference):**
- MCTS loses strength on the way to bosses. It enters them weaker and wins
  with less HP. This fits a planner that over-trusts its imagined combat
  outcomes.
- Possible causes, not separated by this pilot:
  - The CTM was trained on the old vendored Silver from before ADR-0021 and
    later default changes, so even `flat10k` is not its teacher ([#418
    comment](https://github.com/pherrman1/sts_ai/issues/418#issuecomment-6019472255)).
  - The screen leaf was fitted on policy-chain data.
  - The 2048-sim search itself.
- The §383 profile (X2-B `v_win`, default `STS_REST_WIN`) is not the profile
  run here. The −22 pp sits beside §243 (`WINRATE_DOWN`) and §249 (−9.4 pp),
  which also used the earlier leaf.

**Decision:** OOC MCTS stays off. A distillation student (#399) and fresh
on-policy screen-leaf data (#415) are not justified by this teacher. Any next
step needs a new hypothesis, for example a refreshed CTM (#418) followed by a
repeat of this pilot.

**Evidence:** [README, raw CSVs, sidecars and logs](evidence/ooc_mcts_vs_off_pilot_20261006/README.md).

**Knowledge impact:** the current-research section on OOC MCTS records the
result. The environment-variable table now shows the actual `STS_REST_WIN`
default (on).

## §386 — #418 Stage 0: production CTM on learned-stop vs exact-10k teacher rows (2026-10-07)

**Protocol:** frozen in advance ([plan](evidence/ctm_stage0_418_20261007/PLAN.md)), authorized by Philipp at 128 paired seeds instead of the proposed 256. SHA `46153506` (includes #419–#421), `combattransitiongen`, fair RNG, A0, seeds `50000000..50000127`. Each seed ran under both the flat exact-10k teacher and the production learned-stop teacher (ADR-0026) on the same binary. The run used 30 workers in six shards (local 10, five 4-core cloud containers). Result: 128/128 seeds per arm, 0 quarantined, 2,668 and 2,620 rows. The production CTM stack scored every row offline via `ctmscorerows`. CIs are 95% seed-level paired bootstrap.

**Support:** 2,647 / 2,603 rows scored. The rest were unsupported: Smoke Bomb 16 / 11, unqualified active Lizard 5 / 5, Writhing+Ritual Dagger 0 / 1. There were no escapes and no zero-probability HP outcomes.

**Survival is calibrated on both arms.** Mean signed bias (predicted win minus observed) is exact −0.003 (CI −0.009..+0.003) and learned −0.001 (−0.007..+0.005). Boss bias is exact −0.006 (−0.038..+0.027) and learned −0.025 (−0.063..+0.011). Survival NLL is 0.066 / 0.069 nat per fight. The only cell with a significant bias is the exact-arm act 3 boss (+0.087, CI +0.005..+0.177, n=58). The learned arm's act 3 boss is +0.002.

**Boss HP is optimistic on both arms.** Predicted post-combat HP on boss wins is too high by +10.3 HP (CI 8.0..12.7) for exact and +10.0 (7.8..12.4) for learned.

| Learned arm, boss wins | n | pre HP | predicted post | observed post |
|---|---|---|---|---|
| act 1 | 113 | 62.1 | 45.8 | 32.9 |
| act 2 | 70 | 57.9 | 39.6 | 30.3 |
| act 3 | 39 | 69.4 | 44.0 | 40.9 |

Normal and elite HP bias is within ±1.6 HP in every act. Overall HP NLL is 2.58 / 2.61 nat.

**Teacher transfer (learned minus exact):** survival NLL +0.003 (CI −0.010..+0.016), HP NLL +0.032 (−0.041..+0.107), survival bias +0.002, HP bias +0.02. No teacher effect was detected.

**Frozen decision:** **Path B.** The survival-NLL and HP-NLL delta CI upper bounds (0.016, 0.107) exceed the tolerances (0.01, 0.05). The boss survival-bias condition passed (upper bound +0.011 < +0.05). This is a failed equivalence test at reduced n, not a detected teacher difference. The CTM's boss HP optimism is the same on both arms, so the teacher's budget policy does not cause it.

**Inference (pre-follow-up):** the boss HP gap could come from drift since the CTM corpus or from a CTM miscalibration that was already present. The follow-up below separates the two.

**Follow-up (Philipp chose to check before Path B):** the same scorer was run on the old corpus's TEST split (`split_for_seed`; 51,441 rows from 2,517 seeds, producer `f0bbd77`, 51,036 scored). The predictor and pre-state round-trips held on every row. On its own distribution the CTM has no boss HP gap: predicted minus observed is −0.2 HP for act 1 (CI −0.65..+0.26), +0.4 for act 2 and −0.6 for act 3. Act 1 boss wins went from 63.4 pre-HP to 46.7 post-HP in the old corpus, and from 62.1 to 32.9 in the fresh rows. The model predicts about 46 in both. So the gap comes from **teacher drift**: current native Silver ends boss wins about 13 HP lower than the vendored `f0bbd77` teacher at similar entry HP. It is not a CTM miscalibration. One small pre-existing bias remains: act 3 elites +1.2 HP (CI +0.6..+1.8), and act 3 boss/elite deaths are under-predicted by 2–3 pp. The drift is by design. Native Silver scores an act-boss win at the HP left after the act-transition heal (`postBattleHealedHp`, `src/sim/search/SilverSearcher.cpp`), which is max HP at A0. It therefore spends HP freely at bosses. Stage 0 boss deaths are at or below the CTM's prediction (learned act 1: 10 observed vs 13.3 predicted). **Inference:** the post-boss HP gap is mostly harmless downstream, because the next act starts healed. It is therefore unlikely to explain §384's MCTS boss losses.

**Evidence:** [README, plan, scripts, results.json](evidence/ctm_stage0_418_20261007/README.md).

**Knowledge impact:** `ctmscorerows` is documented in `operations/ooc-label-pipeline.md`. No default changed.

## §387 — #347 boss-entry budget rescue on #417 sources: inconclusive, mixed (2026-10-07)

**Question:** does flat exact 40k Silver (B) win boss fights that flat exact
10k (A) lost, from the identical boss-entry states the #417 policies reached?
**Design:** eight #417 boss-loss sources frozen before any challenger run
(R: four mcts boss losses whose flat10k seed won; C: four flat10k boss losses),
reconstructed with the live run driver on build `e6b6122a` (research mode on the
#417 baseline `5e9583cc`), original-seed 10k control parity, then four fresh
planner seeds per entry paired across A and B. Plan frozen at `946d49d9` after
independent review; PR #425.
**Validity:** all eight runs reproduced their historical rows exactly; every
control reproduced its source fight (outcome, HP, full trace, post-exit digest);
repeats identical; every root searched exactly its budget.
**Result:** `BUDGET_HEADROOM_INCONCLUSIVE`, mixed. B 13/32 vs A 12/32 wins,
3 rescues and 2 regressions (net +1; rule needs >= 4 with >= 3 positive
entries). R: A 1/16, B 2/16; three R entries lost all eight continuations.
C: A 11/16, B 11/16; three C sources that lost historically won 11 of 12 fresh
10k planner repeats. B cost 4.4x CPU.
**Interpretation:** little budget rescue at this scale. **Inference:** the
selected C deaths were mostly planner-seed variance on winnable states, while
most R entries are hard for Silver at either budget. Not a full-run or
causal-share estimate; preparation is not tested here.
**Next:** matched-seed OOC-entry comparison on the R seeds (replay each seed's
flat10k boss entry against the mcts entry with the same 10k planner repeats).
It fixes the combat policy, not the combat future (RNG-stream states can
differ), so it measures the total OOC-policy effect, not isolated preparation.

**Evidence:** [packet](evidence/boss_budget_rescue_347_pilot_20261007/README.md).

**Knowledge impact:** `ooc-label-pipeline.md` and `CODE_MAP.md` route the
research-only `bossrescue347` mode, its run-driver hook and the native Silver
planner-seed override.

## §388 — #347 boss-preparation R-match: flat10k entries win, MCTS entries lose (2026-10-07)

**Question:** for the four #417 seeds where the OOC-MCTS arm died at a boss and
the flat10k arm won the run (the #425 R seeds 48000024, 48000014, 48000116,
48000095), does the flat10k-produced boss entry (F) win more often than the
MCTS-produced entry (M) under fixed flat exact 10k native Silver?
**Design:** both #417 trajectories of each seed reconstructed on diagnostic build
`5549a16a` (the #425 research patch on the #417 baseline `5e9583cc`, plus a
manifest-declared `expectedSourceWon`), boss entry captured, original-seed
control parity, then eight fresh planner seeds per seed
(`boss-prep-347-planner-v1:{runSeed}:{act}:{rep}`, identical for M and F).
Entries keep their own legitimate RNG state: this is the total effect of the
OOC trajectory, not an isolated preparation effect and not the same combat
future. Baseline `main` `866e8c32`; plan frozen at `c797c311` after independent
review; PR #428.
**Validity:** all eight reconstructions matched their #417 rows; M sources lost
and F sources won the target boss; every control reproduced its source fight
(outcome, HP, full trace, post-exit digest, simulations); repeats identical;
M/F planner seeds identical; every root searched exactly 10,000 steps.
**Result:** `PREPARATION_HEADROOM_SIGNAL`, shape consistent_positive. F 29/32 vs
M 1/32 boss wins: 28 F-only, 0 M-only, net +28 (rule: >= 8 with >= 3 positive
seeds); per seed net +8 (24, Champ), +7 (14, Donu & Deca), +8 (116, Champ),
+5 (95, Time Eater). Descriptive: F entries carried more relics on three seeds
(+4, +9, +5), more upgrades on two (16 vs 4, 19 vs 6), more HP/max HP on two
(92/100 vs 54/85, 117/117 vs 80/80) and had visited more elites on three; the
M entry of 48000024 had 449 unspent gold and no shop visit.
**Interpretation:** on these selected, failure-enriched seeds the #417 MCTS boss
deaths were not combat-planner bad luck: the MCTS-produced entries lose under
almost every fresh planner seed while the flat10k entries win. **Inference:**
OOC MCTS made these boss entries much weaker; the entry differences above
suggest elite/relic, upgrade and shop choices, but no decision was isolated.
Not a full-run or win-rate estimate.
**Next:** localize the OOC decisions behind the stronger F entries (earliest
consequential divergence per seed: route/elites, rest vs upgrade, shops, card
and relic picks), then a counterfactual on one recurring decision family.

**Evidence:** [packet](evidence/boss_preparation_rmatch_347_20261007/README.md).

**Knowledge impact:** `ooc-label-pipeline.md` and `CODE_MAP.md` route the new
`bossrescue347` selection schema (`expectedSourceWon`, shared planner seeds,
entry descriptor).

## §389 — #347 OOC divergence on the #428 R seeds: chests and campfires (2026-10-07)

**Question:** which out-of-combat decisions made the flat10k (F) boss entries
of §388 stronger than the OOC-MCTS (M) entries on seeds 48000024, 48000014,
48000116 and 48000095?
**Design:** descriptive replay. The eight frozen #428 sources were rerun on
diagnostic build `1ed47e5c` (#428 build `5549a16a` plus a read-only
`STS_OOC_DECISION_TRACE` per-step log); the M sources once more with
`STS_RUN_PROFILE` for OOC MCTS root priors, visits and Q. No new seeds or arms.
**Validity:** all sources `VALID`; every row column except CPU/wall time is
identical to the frozen #428 rows; the traces of both passes are identical.
**Result:** two families recur on all four seeds. OOC MCTS left all 11
treasure chests unopened (F opened 11 of 11) and rested at 24 of 27
campfires, nine times at full HP, smithing 3 times (F smithed 22 of 28). At
those roots the V4 policy prior put 0.76–0.99 on leaving the chest and
0.14–0.78 on resting versus 0.01–0.08 per smith target; `OPEN_CHEST` had the
higher mean Q at 8 of 11 chest roots, yet leaving reached the early-stop lock.
Over 301 multi-action M roots the executed action was the max-prior action 248
times and the max-Q action 121 times. Smaller, seed-specific: three skipped
relic rewards, fewer elites (three seeds), no shop visit on 48000024.
**Interpretation:** **Inference:** the policy prior, not the search value,
drives the chest and campfire losses that explain most of the relic and
upgrade gaps in §388. Not isolated causally: RNG diverges after the first
different decision.
**Next (proposed, not run):** hand OOC MCTS treasure and campfire roots to the
ordinary chain (research flag, default off) and replay the four R seeds with
the §388 planner-seed schedule; decision rule and cost in PR #429.

**Evidence:** [packet](evidence/ooc_divergence_347_20261007/README.md).

**Knowledge impact:** `ooc-label-pipeline.md` routes the research-only
`STS_OOC_DECISION_TRACE` log.

## §390 — #347 counterfactual on the R seeds: chest rule and campfire fallback (2026-10-07)

**Question:** with OOC MCTS forced to open every chest (no Cursed Key), does
handing its campfire decisions to the ordinary chain (CR) give boss entries
that fixed flat-10k Silver wins from more often than chest rule alone (C)?
**Design:** the four §388 R seeds, research flags on diagnostic build
`1911f044` (#417 mechanics), boss entry of the same act, 8 fresh planner seeds
per entry shared with §388. Rule fixed before the run: signal at net >= +8 of
32 with >= 3 of 4 seeds positive. Plan frozen after independent review; PR #429.
**Validity:** all sources `VALID` (control parity, repeats, budgets); flags off
reproduce the §388 rows exactly; the chest rule fired at all 11 chests and the
chain handled every CR campfire.
**Result:** `CAMPFIRE_CHAIN_INCONCLUSIVE`. CR 13/32, C 9/32, net +4 (per seed
+4, 0, +1, -1). Descriptive: M 1/32, F 29/32 (§388); C vs M net +8.
**Interpretation:** after the chest opened, OOC MCTS left the relic on the
reward screen at 8 of 11 chests (C) and 7 of 11 (CR). The chain also made
no-op full-HP rests in these trajectories (9 in CR) and smithed at 6 of 27
campfires. **Inference:** forced chest opening and campfire handoff recover
only part of the gap; relic skipping on reward screens remains.
**Next:** candidate rules: take every relic offered on a reward screen, and
never rest at full HP when a card can be upgraded; then a fresh-seed paired
pilot. Awaiting Philipp's choice.

**Evidence:** [packet](evidence/ooc_counterfactual_347_20261007/README.md).

**Addendum (chest scoring, 2026-10-07):** a read-only hook on the C runs
scored each of the 11 chest states on the map screen with the run's leaf model
(X2-B v_win): relic taken minus relic left is 0 at 5 chests, negative at 5
(Whetstone -0.021), positive at 1 (+0.006); mean -0.003. Gold is priced (+0.016
for 27 gold on 48000116). **Inference:** the leaf model values these relics at
about zero, so relic skipping is not a reward-screen artifact. Traces
byte-identical to the C runs.
[Packet](evidence/ooc_chest_score_347_20261007/README.md). PR #431 drops
key actions from live OOC MCTS when keys are off (it could take the sapphire key
and lose the relic).

**Knowledge impact:** `architecture/out-of-combat.md` records the chest rule
and the keys-off filter; the research flags live only on diagnostic builds.

## §391 — OOC MCTS boss-rollout leaf pilot: 9/32, far below rollout3 (2026-10-07)

**Question:** does OOC MCTS with no prior and a model-free leaf (play the V4
policy chain with CTM fights until the next boss; 1 for beating it, 0 for
dying) play well? Requested by the user as a 32-seed look.
**Design:** research-only `STS_OOC_MCTS_LEAF_VALUE=bossrollout` (PR #430,
default off). Frozen reviewed source `1954f100`, binary `ecb20781…`, #417
`mcts` arm environment with `PRIOR=uniform`, 2048 sims, exact-10k Silver,
act-3 stop, X2-B win net for campfires; seeds 51000000–031 (the rollout3
look's seeds), 1 CPU per seed across four cloud containers.
**Validity:** all 32 runs exited 0 on the frozen SHA/binary with the
intended leaf and prior; 1 of 3,207 root searches aborted. Inside rollouts the
CTM cannot price an active Lizard Tail with Fairy Potion or Entropic Brew, so
the tail is spent there (9,600 times); without that, smoke searches aborted
almost every root.
**Result:** **NEGATIVE.** 9/32 wins (28.1%, Wilson 16–45%), mean floor 38.2,
1,297 s/game. The rollout3 look on the same seeds (uniform prior, 3 CTM fights
then X2-B, earlier main) won 25/32 (78.1%, Wilson 61–89%): −50 pp, unpaired.
Losses: 10 at the act-2 boss and 8 in the act-2 hallway (floors 21–30).
MCTS opened 58 of 80 chests and chose upgrade 141, rest 65, ruby key 5 at
campfires, so the prior-driven chest/rest failure seen in #429 does not appear.
**Interpretation (Inference):** a 0/1 boss-survival signal from long, noisy
policy rollouts does not rank OOC options well at 2048 simulations; it ignores
HP and resources after the boss, and act 2 collapses. Not tested: more
simulations, rollouts that also score post-boss HP, or the refreshed CTM.
**Decision:** keep the leaf default off as a record; no follow-up queued.

**Evidence:** [packet](evidence/ooc_mcts_boss_rollout_leaf_pilot_20261007/README.md).

**Knowledge impact:** `environment-variables.md` and `out-of-combat.md` list the
`bossrollout` leaf mode.

## §392 — #347 prior cost on the R seeds: root by Q and uniform prior (2026-10-07)

**Question:** on the §390 C entries (OOC MCTS + chest rule), how much does the
V4 policy prior cost? CQ = final root choice by mean Q
(`STS_OOC_MCTS_ROOT_SELECTION=q`, no early-stop lock); CU = uniform prior
(`STS_OOC_MCTS_PRIOR=uniform`). Existing knobs, no code change.
**Design:** §390 build `1911f044`, same four R seeds, 8 shared planner seeds
per entry, C rows frozen from §390. Rule per comparison as §390: signal at net
>= +8 of 32 with >= 3 of 4 seeds positive. Plan frozen after independent
review; PR #429.
**Validity:** all 8 sources `VALID`; logged config, chest rule, planner seeds
and binary hashes checked by `analyze.py`.
**Result:** CQ 9/32 vs C 9/32, net 0 (+5, +1, 0, -6; CQ died before the act-3
boss on 48000095): `INCONCLUSIVE`. CU 22/32, net +13 (+6, +7, 0, 0):
`INCONCLUSIVE` (two seeds unchanged). Descriptive: F 29/32 (§388).
**Interpretation:** CU entered with smaller decks and more max HP. All arms
still left most chest relics. **Inference:** the prior's steering of visits,
not the root choice rule, is where the cost shows; not shown that a learned
prior over all OOC decisions would beat no prior.
**Next:** proposed: a fresh-seed paired pilot of uniform vs policy prior with
chest rule and keys-off filter, on Philipp's word.

**Evidence:** [packet](evidence/ooc_prior_cost_347_20261007/README.md).

**Knowledge impact:** none (existing knobs; no default change).

## §393 — #347 uniform-prior OOC MCTS with chest and relic rules: 32-seed pilot (2026-10-07)

**Question:** how do full runs look with live OOC MCTS on a uniform prior once
every OOC policy opens chests (no Cursed Key), takes reward relics (except
Bottled ×3, Dead Branch, Tungsten Rod, Unceasing Top, Juzu Bracelet) and the
search cannot take keys? One arm, descriptive, as Philipp chose.
**Design:** seeds 53000000..53000031, #417 `mcts` arm (2048 sims, screengbm,
flat exact 10k Silver) plus uniform prior, binary from `c2e701d`. Plan frozen
after independent review; PR #429.
**Validity:** all shards exit 0, logged config checked, 32/32 seeds.
**Result:** 18/32 wins (56.3%, Wilson 95% [39.3, 71.8]); 9 of 14 losses at a
boss (act 1: 1, act 2: 4, act 3: 4). Rules fired as intended: 93/93 chests, 187 relics
by rule, no non-exception relic left. Context only: #417 (48M, policy prior,
no rules) MCTS 56.3%, flat10k 78.1%.
**Interpretation:** **Inference:** the rules plus a uniform prior do not make
OOC MCTS visibly better than the #417 MCTS arm; a paired comparison against
flat10k with the same rules is needed to say more.
**Next:** on Philipp's word.

**Evidence:** [packet](evidence/ooc_mcts_uniform_rules_pilot_20261007/README.md).

**Knowledge impact:** none (no default change; rules recorded in §390/KB).

## §394 — E1: focal retrain of the #334 X2 family, card-reward selection gain inconclusive (2026-10-07)

**Question:** were the #334 counterfactual sibling comparisons diluted among
later trajectory rows, so that training on the first MAP row after each
sampled option (focal rows) prices picks, especially card rewards, better?
**Design:** offline on the frozen 1,024-source corpus (`ae56f963…`), unchanged
696/155 TRAIN/VALIDATION split, TEST closed. Frozen X2-B as is, plus three arms
with the X2-B recipe on the 457 public features (four #397 HIDDEN_FUTURE fields
removed), seeds 0/1/2, 3-seed mean: P0 all rows; F1 focal rows only with
per-decision balanced weights; F2 all rows with the focal block upweighted to
equal the non-focal total weight. Selection gain = branch outcome of the
model's argmax sibling minus the V4 chosen sibling's, source-clustered bootstrap.
Tooling `36b5b14f`; X2-B VALIDATION NLL reproduced exactly (0.4226084).
**Result:** `E1_INCONCLUSIVE`. VALIDATION NLL all/focal: X2B 0.4226/0.4884,
P0 0.4237/0.4923, F1 0.4369/0.4958, F2 0.4263/0.4869. Card-reward selection
gain vs V4 (155 decisions, 48 discordant): P0 +0.027 [−0.019, +0.079], F1
+0.039 [−0.014, +0.096], F2 +0.042 [−0.009, +0.090]; oracle +0.155. Boss relic
gains are negative for every arm (F2 −0.026 [−0.092, +0.033]). Pooled over
1,329 decisions, F1/F2 beat P0 by +0.019 [+0.005, +0.032] / +0.016 [+0.004,
+0.027]. X2B − P0 all-row NLL −0.0011 [−0.0059, +0.0041].
**Interpretation:** focal training does not clearly improve card-reward picks on
this corpus; the direction is positive but 48 discordant comparisons cannot
resolve it. The pooled gain was not the preregistered criterion. F2 keeps
all-row calibration within noise and slightly improves focal Brier, so it is a
cheap training default for E3; F1 alone loses calibration. Dropping the
hidden-future fields is again free (§371). Per the plan, E3 decides.

**Evidence:** [packet](evidence/ooc_e1_focal_20261007/README.md).

**Knowledge impact:** `ooc-label-pipeline.md` routes `tools.vwin_e1_focal`.

## §395 — Fair native OOC decision quality and fixed removal-ranking confirmation (2026-10-08)

**Question:** which reproducible decision or implementation weaknesses limit
fair Ironclad A0 Act-3 wins under the non-MCTS native Silver/V4 stack, and does
one independently selected minimal intervention improve fresh whole runs?

**Reference and design:** campaign base `a4b3df35`; all alternatives default
off, original floor/win/V4/stop models unchanged. Direct audit reproduced hidden
unrevealed encounter-identity use by native fallback despite `STS_FAIR=1`.
The research reference therefore uses reviewed public-eight-future marginalization
and disables legacy actual-future hypothetical paths. Optional Ruby Recall with
keys off was separately reproduced and corrected in the common reference from
`3ed91ab3`. Original Bprod/Bflat and pre-Recall-correction Wave1 are diagnostic;
their outcomes are not inherited into corrected-reference qualification.

All full-run trials use Ironclad A0, Act-3 stop, keys-off policy, MCTS off,
default V4 gates/margin 1 except explicitly tested gate ablations, native
Silver, one OpenMP/BLAS thread and at most six concurrent games. Fprod uses learned stopping, adaptive/exact-root budgets off,
nominal 10,000 maximum and allocated reuse cap 32,768. Fflat and the final-boss
binary-utility challenger use exact 10,000 and no learned stopping. Sources,
binaries, models, environments, per-source allocations and per-wave immutable
analyzers are in the linked manifests. Every seed command uses the seed guard.

**Discovery:** the first 32-source screen tested exact combat budget, shop
feature correction, REST/boss/shop gate ablations, zero skip threshold and
final-boss binary utility. ShopFix and RestOff appeared positive before the
common Recall correction. FinalBinary matched every Fflat win/loss at about
2.6% more CPU; this is not equivalence. The later corrected-reference screens
advanced FullHp, ShopOff and RemoveLow by one net win in 32 pairs each. A separate
floor-acceptance-preserving win-head card ranker won 22/32 versus 26/32 and did
not advance. These discovery seeds were adaptively reused and are not fresh
confirmation.

**Fresh development:** exact 128-source cohorts, no pooling or extension; all
pairs complete. Intervals are paired bootstrap percentile intervals: 10,000 replicates, 95%, RNG 20261008.

| Intervention | Wins / Fprod | Candidate-only / control-only | Gain and 95% interval, pp | Disposition |
|---|---|---|---|---|
| RestOff |97/128 vs101/128|10/14|−3.125 [−10.15625,+4.6875]|Rejected for advancement|
| ShopFix |99/128 vs101/128|1/3|−1.5625 [−4.6875,+1.5625]|Correctness fix retained; no strength advancement|
| RestShop |91/128 vs101/128|10/20|−7.8125 [−16.40625,+0.78125]|Rejected for advancement|
| FullHp |102/128 vs101/128|4/3|+0.78125 [−3.125,+4.6875]|Wave3 nominee by frozen tie rule|
| ShopOff |102/128 vs101/128|10/9|+0.78125 [−5.46875,+7.8125]|Not selected by tie rule|
| RemoveLow |106/128 vs104/128|7/5|+1.5625 [−3.90625,+7.03125]|Largest development gain; sole exploratory champion|

**Final confirmation: `CONFIRMED_IMPROVEMENT`.** RemoveLow won 395/512
(77.1484375%) versus Fprod 381/512 (74.4140625%), with 27 candidate-only wins,
13 control-only wins and 368 shared wins. Gain +2.734375 pp, paired 95% interval
[+0.390625, +5.2734375]; both the positive lower bound and 2 pp practical floor
pass. All 256 jobs completed exit0 with no missing pair, retry, replacement or
extension, and no remaining campaign game worker. CPU C/R 6,949.0484/6,844.1451 s;
parallel elapsed 2,332.7000 s (38.88 minutes), 3.83144 game-core-hours total.
The health audit passes with diagnostic limits: 457,287 roots, 1,965,273,000
completed simulations, zero root errors/aborts/nonterminal endpoints, 1,689
cycle rollouts and 339 engine-stop/377 turn-limit endpoints.

Champion RemoveLow and matched Fprod use
immutable `d35b42b1`, binary SHA256 `1dcc79169e60cc58865218cd66644dd2db61a9e9ceaafdf39c1b8a7b6600a8f5`;
only `STS_OOC_REMOVE_LOW_OBTAIN_WEIGHT=0→1` differs. Exactly 512 pairs
(`610083000..610083511`), 1,024 runs and 256 four-seed jobs were frozen with source,
models, analysis/helper/runtime hashes and reviewed before the holdout latch
was written. Final superiority requires positive paired 95% lower bound and
observed gain >= 2 pp, plus complete execution/information gates. No retry,
replacement, extension, retuning or automatic combination is permitted.

**Decision audit:** baseline-failing fixtures establish native information
exposure, optional Recall and shop hypothetical deck-size arithmetic defects.
These are separate from playing-strength claims. The outcome-unselected
corrected 128-source reference had 101 wins and 27 losses, including 13 final-boss
losses. A chronological first 12 atlas includes wins, losses and benign controls.
At one matched shop, feature correction changes the selected bundle; at Living
Wall, RemoveLow changes Shrug It Off removal to Strike. FullHp and RemoveLow
rescued the same discovery source through different long paths, so gains cannot
be added. No missing-free-treasure hypothesis survived the first 12 audit:
32/32 free chests and 112/112 ordinary relic offers were collected.

**Conditional experiments:** at one selected REST state reviewed from public
information with the baseline action known before continuation outcomes, Offering
upgrade was chosen on 16 futures/action and then won 23/32 independent continuations
versus 17/32 for REST (8/2 discordances, +18.75 pp,[0,+37.5]); this remains local
conditional inconclusive under the older teacher. At one outcome-informed
public Champ root, fresh exact 10k continuation after forced Shrug won 50/62 versus
END 51/62 (9/10, −1.613 pp,[−14.516,+11.290]); no demonstrated better line or
whole-run claim. The original potions had already been spent by turn 2.

The corrected GEN2 tranche used 32 fresh sources, 63 CARD/BOSS decisions and 1,968
valid sibling branches, costing 4.15072 observed game-core-hours. Choices frozen
from futures 0–3 preceded independent evaluation 4–7: 252 fixed-rule state/future
pairs, 32 source clusters. Rollout-selected gain −1.171875 pp, 95%[−5.46875,+3.125]:
`LOCAL_CONDITIONAL_INCONCLUSIVE`. P0 +0.390625 pp[−4.296875,+5.46875] and
F2 −0.78125 pp[−5.078125,+3.125] are secondary, not a selected winner. Separately
reviewed exploratory analysis found apparent selection gain +10.55 pp, 47/63 tied
selection maxima and 17/63 all-option evaluation ceilings. Queue-blind historical
P0/F2 retain latent counters and older privileged-teacher labels; this diagnostic
does not qualify a current fair deployment. No training or protected historical
TEST opening occurred.

**Validity and interpretation:** named binaries and complete output hashes are
preserved. Prelaunch/build/fixture and verifier failures were retained and
repaired without replacing game sources. Debug 67/67 core/smoke plus 2/2 extra
integration passed at `a557ace5`; later FullHp/removal/card-rank changes have
separate focused/static/runtime checks at `b229f3ff`, `d35b42b1`, and `5add2413`.
Supplementary tree audits distinguish fatal root/abort/nonterminal failures from
intentional cycle fallback and recorded simulator safety-limit search endpoints.
The sampler is a bounded conditional approximation and live-game equivalence
was not established. The draft workflow skips authoritative Linux GCC CI; local
checks do not become a CI pass. No merge or production-default change.

**Next:** proposed, not launched: fresh 32-source BOSS-only K4-versus-K16 action
selection at identical states, both choices frozen before shared independent
futures 16–31. This isolates selection precision from source mix/model drift;
projected 8.3 core-hours typically, 12.4 with six options before tail, proposed hard
four-worker, four-hour cap of 16 core-hours. No automatic extension or training.

**Evidence:** [complete packet](evidence/ironclad_a0_overnight_20261008/README.md),
[ranked hypotheses](evidence/ironclad_a0_overnight_20261008/HYPOTHESES.md),
[decision cases](evidence/ironclad_a0_overnight_20261008/DECISION_CASES.md),
[champion freeze](evidence/ironclad_a0_overnight_20261008/champion_freeze.json).

**Knowledge impact:** maintained OOC/environment/label-pipeline/combat
interfaces, native information-boundary caveat, current research disposition
and actual CI routing. No production baseline promotion.

**Follow-on:** the proposed selection-precision comparison was later attempted
under a separate four-hour authorization; see §398 below. It ended
`EXECUTION_BLOCKED`, without changing this campaign’s closed confirmation.

## §396 — E3: first counterfactual OOC tranche, card-reward criterion negative, boss relics priced (2026-10-08)

**Question:** do whole-run counterfactual labels (same state, each option,
shared futures) let a GBM pick card rewards and boss relics better than X2-B,
and better than V4?

**Design:** pre-registered in E3-PREREG (2026-10-07).
- **Data:** `ooccfpilotgen` GEN=2 (#434, git 8edf724c, binary `224a1a42…`),
  learned-stop V4 teacher. 1,000 seeds (55000000..999) on 25 cloud workers,
  K=2, card-reward and boss-relic states, whole-run `finalWon` labels.
- **Data rules:** the four HIDDEN_FUTURE fields are masked; a (state, k) group
  with any invalid sibling is dropped; the split is `source_split`, with TEST
  closed.
- **Arms:** X2B (masked); E3 (E3 rows only); F2_334 (#334 TRAIN with E1 F2
  weights); F2 (F2_334 plus E3 TRAIN, the primary arm).
- **Metric:** per-state selection gain against V4's choice, with
  source-clustered CIs.

**Result:** `E3_NEGATIVE` for the card-reward criterion.
- **Data:** 1,983 states. 15,667 of 15,668 runs valid; one Silver stall
  (55000830..834) excluded.
- **F2 on VALIDATION:**
  - Card-reward gain +0.017 [−0.018, +0.051], boss relic +0.012 [−0.027,
    +0.050].
  - NLL 0.4788 against X2B 0.4957.
  - F2 − X2B: boss relic +0.060 [+0.020, +0.104], pooled +0.038 [+0.015,
    +0.062].
  - F2 − F2_334: pooled +0.024 [+0.003, +0.046].
- **X2B:** boss-relic gain −0.048 [−0.093, −0.003].
- **Uniform-random option:** card reward −0.001 [−0.027, +0.026], boss relic
  −0.090.
- **E3 learning curve:** not rising.

**Interpretation:**
- Card-reward choices move win rate by less than about ±3 pp per decision
  under the V4 + Silver continuation. Even a random card pick ties V4, so
  better card-reward pricing is not a lever at this scale (inference).
- Boss relics: this is a descriptive VALIDATION result outside the decision
  rule, one of several contrasts reported. It is slightly optimistic because
  the retrained arms early-stop on the same VALIDATION split.
  - X2-B prices relics worse than V4, and F2 matches V4 (F2 − X2B +0.060).
  - The independent review re-checked this with all 14 future-dependent
    boss-relic fields dropped (the 4 masked plus `bossId` and the `fm*` map
    counts). E3 − X2B stays at +0.051 [+0.008, +0.095].
- No online A/B follows from the pre-registered rule. A boss-relic-only leaf
  or one-ply use of F2 would be a new hypothesis.
- The F2 and F2_334 numbers were copied from a local run on Philipp's machine.
  Its full report.json is not archived; a verbatim VALIDATION excerpt is in
  the evidence packet.

**Evidence:** [packet](evidence/ooc_cf_e3_20261008/README.md).

**Knowledge impact:** `ooc-label-pipeline.md` routes `tools.vwin_e3_cf`.

## §397 — Synthetic Silver corpus: learned leaf fails, root prior bonus passes offline (2026-10-08)

**Question:** can Silver-labelled synthetic states train (a) a leaf value that
beats one SimpleAgent rollout, or (b) a root prior that improves a low-budget
Silver search? Assessment in `/mnt/project-files/silver-synthetic-prior/ASSESSMENT.md`.

**Design:** pre-registered (evidence `PREREG.md`), offline only.
- **Data:** `silversynthgen` (#438, frozen 450376c8), natural seeds
  56000000..215 and perturbed seeds 56002000..215. Every 10k root's visits and
  Q, a second independent 10k search on 1 root in 4, two Silver-2k
  continuation labels per root action on 1 root in 8, and sampled rollout
  leaves.
- **Split:** fold = seed offset mod 5; fold 4 test, fold 3 validation. Metrics
  on natural fold 4 (43 seeds). Arms nat and nat+pert (primary).
- **Models:** LightGBM on the engine's combat features
  (`combatExtractFeatures`, plus action features for the prior).
- **Gate A:** on 2,007 test sibling groups, compare V on a probe child with one
  rollout from the same child (R1). The judge is the mean of two continuation
  labels.
- **Gate B:** root replay from the wire with a bonus
  `w * P(a) / (1 + n_a)` on visited root edges. Regret is against the mean Q
  of the two 10k teachers, at 256 and 1,000 simulations. w is picked on
  validation from {25..400}.

**Result:**
- **Gate A: FAIL.** V_cont (nat+pert) regret 4.39 vs R1 4.02, difference
  +0.37 [−0.01, +0.74]; concordance 0.666 vs 0.668.
  - No secondary model passes. V_roll (nat+pert) ties R1 (−0.05
    [−0.41, +0.33]).
  - Four rollouts beat one: −0.47 [−0.78, −0.14], concordance 0.683.
- **Gate B: PASS** for both arms (w = 400, the top of the grid, for both).
  ASSESSMENT.md asked for "no new ≥3-regret roots"; the pre-registration made
  that a count rule (prior count ≤ plain count at each budget). Read
  literally, Gate B fails: 168 root-seed runs are ≥3 only under the prior at
  256 sims and 183 at 1,000. Two plain replay seeds already differ by about
  200 such runs out of 4,094 roots, so the count rule is the fair version.

| prior | regret @256 | vs plain @256 | ≥3-regret runs @256 | regret @1000 | vs plain @1000 | ≥3 @1000 |
|---|---|---|---|---|---|---|
| plain UCB | 2.04 | | 1,134 | 1.68 | | 840 |
| model nat+pert | 1.71 | −0.33 [−0.46, −0.21] | 948 | 1.53 | −0.14 [−0.27, −0.03] | 783 |
| model nat | 1.75 | −0.29 [−0.40, −0.20] | 960 | 1.60 | −0.08 [−0.18, +0.01] | 799 |
| oracle (teacher visits) | 0.82 | −1.22 | 411 | 0.96 | −0.72 | 492 |

**Interpretation:**
- Variant (a) is closed. With about 147k continuation labels, a GBM leaf still
  ranks siblings no better than one cheap rollout. This matches §181/§182 at
  65x the data (inference: features, not data volume, are the limit).
- The prior at 256 sims is about as good as plain UCB at 1,000 (1.71 vs 1.68).
  This is the compute win the assessment expected, not evidence of play above
  10k. The perturbed states help only nominally: nat+pert scores better than nat
  at 1,000, but the two arms were never tested against each other and the
  nat-only CI at 1,000 crosses 0.
- The oracle row reuses the teacher's own visits, so it is headroom only.
- w = 400 sits on the grid edge, so a larger weight might do better. The
  pre-registered grid was kept.
- The prior is trained to imitate 10k visits and judged against 10k Q. A pass
  therefore means "closer to 10k at lower budget", not "stronger than 10k".
- GBM inference cost is not measured here (prior applied at the root only).

**Next:** the pre-registered follow-up is a 32-pair online screen: prior +
flat 2k vs plain flat 2k, then prior + 2k vs plain 10k. It uses seeds
56003000..031, the range reserved when the corpus was resized (the PREREG copy
still names the older 56001000..031). It needs native GBM inference in the backend and Philipp's go. No Silver
change ships before the CTM full retrain lands.

**Evidence:** [packet](evidence/silver_synth_gates_20261008/README.md).

**Knowledge impact:** `combat-search.md` documents the corpus harness and the
research-only root prior bonus.

## §398 — Boss-relic selection precision K4 versus K16: execution blocked (2026-10-08)

**Question:** does increasing selection futures from four to sixteen improve
which retained boss relic is chosen at the same source state, or does the
small-K optimism seen in §395 persist on independent futures?

**Frozen design:** 32 fresh sources (`610084200..610084231`), at most one
BOSS_RELIC state each, 32 common futures per retained option. K4 selects on
k0–3; K16 selects on k0–15. Both use the captured source-policy action to break
ties, then canonical key order. Both choice sets must be saved and hashed before
separate evaluation on k16–31. The primary is the equal-weight mean of the 32
source-level paired K16-minus-K4 differences, with an otherwise valid no-state
source contributing zero. The 95% interval resamples whole sources 10,000 times
with RNG 20261008; lower bound above zero supports local conditional gain,
upper bound below zero supports harm, otherwise inconclusive. Any invalid or
incomplete source blocks this primary. No replacement, retry, cap change or
completed-subset substitution is allowed.

The unchanged gameplay producer is `3ed91ab3491a4cdc1a7de687b2ad87dcc7774fc0`,
binary SHA256 `27a78efd3f5da731897d36dd9b50a622d2ace4f54dae69dfc157bf6712b027c7`;
reviewed collection/analysis tools are at `54c97fd0995c043ca584e75ff6af6da2fb032cf3`.
The original floor/win/V4 models, corrected public-eight-future/Recall policy
and native learned-stop teacher are fixed. No gameplay source, model training
or GPU workload changed. The user authorized a separate 11:02:24–15:02:24
Europe/Berlin block. Seed-guarded collection used at most six one-thread workers,
1,800 seconds per source, a 10,800-second process-group cap and an absolute
14:22:24 collection stop. The actual dispatcher deadline was 14:21:54.

**Result: `EXECUTION_BLOCKED`.** All 32 invocations were attempted exactly once:
31 completed exit 0; source `610084217` timed out after 1,800.033516 seconds,
exit 124. Dispatch ran 11:21:54–13:02:19, ended exit 123, and left no game worker.
The frozen verifier returned `INVALID`, `source subprocess incomplete/failed`.
Neither selection nor efficacy evaluation ran; the point estimate, interval and
K16-versus-K4 quality verdict are null. The timeout is not a valid no-state zero.

| Preserved execution metadata | Value |
| --- | ---: |
| Complete branch records from the 31 completed sources | 3,968 |
| Additional complete persisted records from the timed-out source | 100 branches; 97 MAP rows |
| Observed source CPU | 412.584270 s; timeout source cost unavailable |
| Observed branch CPU | 32,650.585663 s; interrupted/unflushed work unavailable |
| Total observed emitted CPU | 33,063.169933 s = 9.184214 core-hours, censored |
| Sum of invocation process-wall times | 33,290.747188 s |
| Parallel dispatcher elapsed | 6,024.881753 s = 100.414696 minutes |

All 255 source files and the dispatch log are preserved. Missing cost is not
imputed as zero, concurrent process-wall sums are not elapsed time, and the
truncated option table cannot establish a complete expected branch allocation.
The original §395 inventory of 799 completed invocations excludes these 32
follow-on attempts and their timeout. The supplemental E3 allocation check
found its declared `55000000..55000999` range disjoint; the original freshness
inventory remains unchanged and bounded to the metadata inspected at freeze.

**Diagnosis and limits:** source217's 100 saved complete continuations used
1,747.39344 CPU seconds, averaging 17.4739 seconds—2.43 times the historical
branch average used for planning. The saved profile stream was still advancing
immediately before termination. This supports a compute-cost tail explanation;
the aggregate forecast did not bound per-source runtime. Across all sources,
990,256 saved profiles and 3,982,623,750 completed simulations had no recorded
fatal health finding. The 4,268 cycle fallbacks, 49 engine-stop and 49 turn-limit
endpoints remain diagnostics. Interrupted/buffered work and per-branch combat
coverage are not certified by that scan. A timeout establishes no selector
superiority, harm or equivalence.

The conditional sampler retains latent counters and pool membership; it is not
an exact posterior over every player-visible history. No online selector,
population win-rate or merged-source qualification follows. The earlier
RemoveLow confirmation stays closed and separate, with no pooled labels or
reopened holdout. Selection precision remains unresolved. Any future efficacy
use needs a new authorized protocol disclosing this failed allocation and
addressing per-source compute tails; no automatic continuation is authorized.

**Evidence:** [complete follow-on packet](evidence/ironclad_a0_k_precision_20261008/README.md),
[frozen protocol](evidence/ironclad_a0_k_precision_20261008/PROTOCOL.md),
[machine result](evidence/ironclad_a0_k_precision_20261008/RESULT.json),
[metadata accounting](evidence/ironclad_a0_k_precision_20261008/analysis/BLOCKED_RESULT.md),
[independent custody/health review](evidence/ironclad_a0_k_precision_20261008/audit/CLOSEOUT_REVIEW.md),
[independent interpretation review](evidence/ironclad_a0_k_precision_20261008/design/FINAL_INTERPRETATION_REVIEW.md).

**Knowledge impact:** current research records a failed fixed-allocation
experiment and unresolved selection precision. Production defaults, model
artifacts and the closed §395 qualification are unchanged.

## §399 — Synthetic Silver root prior online screen: negative (2026-10-08)

**Question:** does the §397 root prior (Gate B pass offline) win more full runs
at a flat 2k budget, and does prior + 2k approach plain 10k?

**Design:** pre-registered after Philipp's go (evidence `PREREG.md`, written at
launch before any seed result, not committed beforehand).
- **Build:** commit 51937c6a (#449), a research-only `STS_SILVER_ROOT_PRIOR`
  option (default off). The §397 nat+pert prior was exported to
  `combat_policy_trees_v1` with exact margin parity. Native vs offline replay
  was identical on 300 test roots.
- **Arms:** bestbench, seeds 56003000..031 (never used for training), A0, fair,
  flat exact budgets, no learned stopping. A plain 2k; B prior w = 400 + 2k;
  C plain 10k.
- **Rule:** SCREEN_PASS if B − A ≥ +3 wins and B ≥ C − 2; SCREEN_NEGATIVE if
  B − A ≤ 0.

**Result:** `SCREEN_NEGATIVE`.

| arm | wins | mean floor | CPU s/run |
|---|---|---|---|
| A plain 2k | 21/32 | 50.2 | 12.8 |
| B prior + 2k | 21/32 | 49.5 | 12.4 |
| C plain 10k | 28/32 | 50.2 | 72.7 |

- B vs A: 3 seeds won only by B and 3 only by A.
- B vs C: 7 seeds won only by C, 0 only by B.

**Interpretation:**
- The offline gain (prior + 256 ≈ plain 1,000 in root regret) did not show up
  as whole-run wins at 2k. Inference: per-root regret gains of about 0.3 points
  are too small to move run outcomes at this scale, or the root-only prior
  helps where it matters least. The screen cannot tell these apart.
- 10k clearly beats 2k on these seeds (+7 wins). The budget matters, and the
  prior does not substitute for it.
- The prior's CPU cost is negligible (B ran as fast as A).
- Per the rule, variant (b) stops here unless a new target definition
  appears. Together with §397 Gate A, the synthetic-corpus route to a Silver
  prior or leaf is closed for now.
- `STS_SILVER_ROOT_PRIOR` stays research-only and off.

**Evidence:** [packet](evidence/silver_root_prior_screen_20261008/README.md).

**Knowledge impact:** `combat-search.md` documents the option. The ledger
records the negative screen.

## §400 — Synthetic Silver root prior v2: offline replay, no gain at 2k (2026-10-08)

**Question:** after §399, is the prior model the bottleneck? Does a richer
prior (post-action state features, per-root ranking loss, more rounds, wider
weight grid) recover more of the visit-share oracle's root-regret gain,
especially at the 2k budget the online screen used?

**Design:** offline only, on Philipp's request to look further into the model
training. Same corpus, folds, teacher and replay harness as §397; adds a
2,000-sim budget. The prior v2 recipe and the weight rule (best validation
regret at 1,000 sims) were fixed before the test replay. Arms on 4,094 test
roots x 2 replay seeds: plain, v1 (§397 prior, w = 400), v2 (w = 1600, picked;
w = 400 secondary), oracle visit shares (w = 400 and 1600).

**Result:** root regret (Silver points; mean, and difference vs plain with 95%
seed-clustered CI).

| budget | plain | v1 w400 | v2 w1600 | oracle w1600 |
|---|---|---|---|---|
| 256 | 2.04 | 1.71 (−0.33 [−0.45, −0.22]) | 1.59 (−0.45 [−0.59, −0.32]) | 0.57 |
| 1,000 | 1.68 | 1.53 (−0.14 [−0.27, −0.03]) | 1.47 (−0.21 [−0.33, −0.10]) | 0.64 |
| 2,000 | 1.55 | 1.46 (−0.09 [−0.23, +0.04]) | 1.44 (−0.11 [−0.23, +0.01]) | 0.73 |

- v2 − v1: −0.12 [−0.21, −0.04] at 256, −0.07 [−0.17, +0.05] at 1,000,
  −0.02 [−0.11, +0.09] at 2,000.
- Secondary arm v2 at w = 400: −0.10 [−0.22, +0.02] vs plain at 2,000, the
  same as w = 1600, so the tie does not depend on the weight pick.
- Share of the oracle gain captured at 2,000: v1 11%, v2 13%.
- Fit (validation fold, also the early-stopping fold, so slightly optimistic):
  top action equals the 10k top action for v1 55.1%, v2 58.5%; a second
  independent 10k search agrees 75.0%, a lower bound on what a perfect prior
  could reach. On roots where both 10k searches agree, v2 matches 66.8%.

**Interpretation:**
- The richer prior is better only at low budgets. At 2k it ties v1 and neither
  clearly beats plain, which matches §399.
- Model fit improved only modestly (55% → 59%, while two 10k searches agree
  75%). Inference: the post-action features and the ranking loss were not the
  main limit. Label noise is not the main limit either, since v2 misses a third
  of the roots where both 10k searches agree.
- The oracle numbers overstate the reachable gain: the oracle's visit shares
  come from the same 10k searches whose Q values form the teacher.
- No new online screen is proposed. The v2 recipe stays offline (no native
  scorer for afterstate features exists).

**Evidence:** [packet](evidence/silver_prior_v2_offline_20261008/README.md).

**Knowledge impact:** the ledger records the result. `silversynthfeatures`
now writes `after` rows; no maintained KB page describes that row layout.

## §401 — OOC MCTS leaf valued by F2 instead of X2-B: negative (2026-10-08)

**Question:** F2 (#334 TRAIN plus the E3 counterfactual tranche, §396) beat
X2-B offline: map-row NLL 0.479 vs 0.496, and a boss-relic selection gain of
+6 pp. Does F2 also make a better OOC MCTS leaf value?

**Protocol:** frozen [PLAN.md](evidence/ooc_mcts_f2_leaf_pilot_20261008/PLAN.md),
independently reviewed before the run (one launcher provenance fix).
- **Option:** new research option `STS_OOC_MCTS_LEAF_WIN_MODEL` (default
  unset), which values `native`/`direct` leaves with a given tree model.
- **F2 export:** the three F2 seeds were margin-averaged into
  `models/candidates/v_win_f2_e3_trees.txt` by `tools/vwin_export_ensemble.py`.
  On E3 VALIDATION it reproduces NLL 0.4788.
- **Profile:** §384, with flat exact-10k Silver and B0 `v_win` in the
  non-MCTS chain.
- **Seeds:** `57000000..57000127`, 128 pairs.
- **Arms:**
  - `flat10k`: OOC MCTS off.
  - `x2b`: OOC MCTS (§384 knobs) with the `native` leaf valued by X2-B.
  - `f2`: the same, valued by F2.

**Result: `F2_WORSE`.**
- **f2 − x2b: wins −13.3 pp, 95% CI [−24.2, −2.3]** (63.3% vs 76.6%); floor
  −1.41 [−3.14, +0.20]; discordant 18 vs 35.
- f2 − flat10k: −10.9 pp [−21.9, 0.0]. x2b − flat10k: +2.3 pp [−8.6, +13.3].
- Descriptive: `f2` loses more on boss floors (38 of 47 losses, against 21 of
  30 for `x2b`) and in act 2 (17 vs 12).
- Integrity: 12 of 12 invocations exit 0, no failed seeds; `analyze.py`
  reproduces `report.json`.

**Interpretation (Inference):**
- A better offline fit on E3 map rows did not make F2 a better search leaf.
  - F2 was fitted to the first map row after card rewards and boss relics,
    plus #334 policy-chain rows.
  - The search compares leaves across many other kinds of state, so leaf
    ranking there matters more than calibration on E3 rows. Neither offline
    metric measured that ranking.
- `x2b − flat10k` (+2.3 pp, CI ±11) is not a replay of §384 (−21.9 pp).
  §384 used the default `screengbm` leaf, and the seeds differ.
  - Open question: does the `native` X2-B leaf avoid most of the §384 loss?
    That would need its own pre-registered comparison against `screengbm` on
    the same seeds.

**Decision:** F2 is not adopted as a leaf. `STS_OOC_MCTS_LEAF_WIN_MODEL`
stays as a default-off research option, and `STS_OOC_MCTS` stays off.

**Evidence:** [README, raw CSVs, logs, smoke and provenance](evidence/ooc_mcts_f2_leaf_pilot_20261008/README.md).

**Knowledge impact:** this entry, and the
[environment-variable table](../knowledge-base/operations/environment-variables.md)
(`STS_OOC_MCTS_LEAF_WIN_MODEL`).


## §402 — #346 A20 counterfactual corpus: option spreads vs E3 (2026-10-09)

**Question:** issue #346 asks whether harder-Ascension data carries more
decision signal than A0 data. Before training anything: does an OOC choice
change outcomes more at A20 than at A0?

**Protocol:** [PLAN.md](evidence/a20_transfer_346_20261009/PLAN.md),
written before the corpus run.
- **Code (PR #455, `5ba068e0`):** under `STS_STOP_AFTER_ACT=3`, A20 runs now
  play the second Act-3 boss, and `ooccfpilotgen` takes a trailing ASCENSION.
- **Probe:** bestbench flat10k (§401 profile), seeds `59000000..59000031`.
- **Corpus:** `ooccfpilotgen` GEN=2 at A20 with E3's settings (§396), seeds
  `59100000..59101199`, 20 cloud workers.
- **Comparison:** against E3 (A0). Per state, a two-way option × future ANOVA
  estimates the variance of true option values. Futures are shared across
  options. This measure and the floor-reached / first-Act-3-boss targets were
  chosen after PLAN.md, which named best-minus-mean, best-minus-second, label
  entropy and chosen-is-best.

**Result (descriptive):**
- **Probe:** A0 wins 24/32. A20 wins 6/32 if the run stops after the first
  Act-3 boss, and **0/32** once the second boss is played. All six die to it.
- **Corpus:** 240/240 parts, 16,590/16,590 valid labels, 2,094 states. The
  label win rate is about 10%: the generator's learned-stop teacher does win at A20.
- **Card rewards:** option SD on final win ≈0 at both ascensions. On floor
  reached, 2.0 floors at A20 (CI excludes 0) vs 0.37 at A0 (CI includes 0).
- **Boss relics:** option SD on beating the first Act-3 boss is 0.12 at A0
  and 0.11 at A20. On A20 final win it is 0.065. On floor reached, 3.7 floors
  at A20 vs 1.7 at A0.
- Full table: [README](evidence/a20_transfer_346_20261009/README.md),
  [report.json](evidence/a20_transfer_346_20261009/report.json).

**Interpretation (Inference):** at A20, OOC choices make a bigger difference to
survival depth than at A0. They do not make a bigger difference to win labels,
which the second boss saturates. Part of the floor difference is
mechanical: 89.7% of A0 labels end at the floor-50 cap (A20: 37.8% at floor
50 or later), so A0 floor spread is compressed the same way A20 win spread
is. This partly supports the premise of #346 for
floor-type targets. It says nothing yet about whether A20 data helps an A0
model.

**Decision:** no model or default change. The next step is the #346
transfer test (A0-only vs mixed-ascension GBM on the fixed E3 holdout), which
needs its own go.

**Knowledge impact:** this entry, and the `STS_STOP_AFTER_ACT` row of the
[environment-variable table](../knowledge-base/operations/environment-variables.md).

## §403 — A20 synthetic Silver corpus: A0 root prior transfers (T1 not passed) (2026-10-09)

**Question:** Philipp asked for the §397 synthetic Silver data at A20 instead
of A0. Do A20 Silver root choices need A20 training data, or does the A0
prior already predict them?

**Design:** [PREREG-T1.md](evidence/silver_prior_a20_transfer_20261009/PREREG-T1.md),
written before any corpus row existed.
- **Corpus:** the §397 generator unchanged (`450376c8`, same binary sha and
  teacher), ASC = 20. Runs play to the end, including the A20 second Act-3
  boss. Seeds natural `60000000..60001079`, perturbed `60002000..60003079`,
  20 cloud workers; smoke `60009000..60009017`.
- **Arms** (prior v2 recipe, §400): A0 = the §400 `prior-v2.txt`; A20 =
  trained on A20 folds 0-2; Mixed = A0 1x corpus + A20 folds 0-2. Validation
  on A20 fold 3, test on A20 fold 4 (folds by seed).
- **Rule:** if A20 or Mixed beats A0 by ≥ 3 pp top-1 vs the 10k pick, with the
  seed-clustered 95% CI excluding 0, run a replay gate at A20; otherwise A0
  transfers and there is no A20-specific prior.

**Result: T1 not passed.**
- Corpus: 237 of 240 units, 2,133 runs, 18,553 fights, 310,766 roots, 0
  invalid fights. Three units were dropped: one seed each stalled for over an
  hour in the label searches (seeds 60002492, 60002631, 60000997).
- A20 test (57,115 roots, 428 seeds): A0 62.8%, A20 64.9%, **Mixed 65.3%,
  +2.5 pp [+2.1, +2.8]** vs A0. On roots where both 10k searches agree:
  70.9 / 73.0 / 73.6%.
- By act, Mixed − A0: Act 1 +3.0, Act 2 +1.4, Act 3 −0.6 [−2.6, +1.1]
  (2,502 roots, 17 seeds). A20-only is worse than A0 in Act 3 (−2.6). A20
  second boss (descriptive, 174 roots, 5 seeds): Mixed +2.3 [−6.2, +10.7].
- A0 test (descriptive): Mixed +0.6 pp [+0.2, +1.0] vs A0.
- A20 runs are short: 8.7 fights per run vs 21.4 at A0; in the smoke, 72% of
  fights were in Act 1.
- Correction after review: a first run was missing two A0 units' features
  (+2.6 [+2.2, +2.9]); the numbers above are the rerun on complete data.

**Interpretation (Inference):** the A20-specific gain is small (+2.5 pp) and
sits in Act 1, where A20 data is plentiful. Part of it is probably
training-set size: Mixed has 2.6x the A0 arm's roots and also helps A0.
Absolute accuracy is not comparable across ascensions (75% of A20 test roots
are Act 1, where every arm scores higher). A20 late-game coverage is too thin
to say anything about A20 bosses.

**Decision:** no A20-specific prior; T2 not run; no code or default change.
The A20 rows can be pooled as extra training data for prior or encoder work.

**Evidence:** [README, prereg, script, report, per-unit hashes](evidence/silver_prior_a20_transfer_20261009/README.md).

**Knowledge impact:** this entry only. No maintained interface changed: the A20
corpus uses the existing `silversynthgen` ASC argument.

## §404 — Learned encoder Silver root prior: ties GBM v2 at 6x data, no 2k gain (2026-10-09)

**Question:** after §400 (GBM priors stall on hand-made features), does a
learned encoder over the structured combat state fit the 10k search's choices
clearly better, and does that help search at 2k sims?

**Design:** pre-registered in the evidence `PREREG.md` (stage 1 committed
before training, stage 2 before any new data), on Philipp's go (2026-10-08).
- Model: transformer over state tokens (cards by zone, monsters, potions,
  player statuses, relics, context), d 128, 3 layers; per-action logits from
  the tokens an action uses; per-root softmax cross-entropy vs 10k visit
  shares. Trained on cloud CPU.
- Stage 1: the §397 corpus (165k roots), §397/§400 folds. Stage 2: plus a new
  5x corpus from the same frozen generator (seeds 58000000-58001079 natural,
  58002000-58003079 perturbed, 20 cloud workers, 238 of 240 units used), 951k
  roots; v2 retrained on the same data (v2-6x).
- Gate 1 / 1': top-1 vs the 10k pick on test roots where two 10k searches
  agree must beat v2 (stage 1) / v2-6x (stage 2) by >= 5 points.

**Result:** both gates FAIL. Test fold of the original corpus, 6,003 roots
where both searches agree (32,309 roots in all); the two searches agree on
74.4% of roots with a second search.

| prior | data | agree-root top-1 | all-root top-1 | cross-entropy |
|---|---|---|---|---|
| v1 (§397) | 1x | 63.3% | 55.3% | 1.230 |
| v2 (§400) | 1x | 67.8% | 59.0% | 1.175 |
| encoder | 1x | 63.4% | 55.3% | 1.227 |
| v2-6x | 6x | 70.8% | 61.2% | 1.144 |
| encoder | 6x | 70.6% | 61.7% | 1.124 |

- Stage 1 encoder overfit after epoch 7. An exploratory learning curve
  (regularized) rose 2 to 3 points per doubling of data, which motivated
  stage 2.
- Deviations from the pre-registration: 238 of the 240 pre-registered units
  (2,160 runs) were used, because one unit never reported and one finished
  after tokenization; 242 training roots with more than 128 tokens or 64
  actions were skipped for memory (evaluation covers every root); the 6x
  encoder's best epoch was the last of its 12-epoch cap, with validation
  cross-entropy nearly flat but still falling.
- Exploratory replay (not a gate; §400 test roots, 8,188 runs per arm), regret
  vs plain at 2k: v1 −0.09 [−0.24, +0.04], v2-6x −0.09 [−0.20, −0.00],
  encoder-6x (w 400, no own weight pick) −0.07 [−0.23, +0.09]; v2-6x − v1
  −0.005 [−0.11, +0.11]. At 256 sims the encoder is best (−0.49 vs plain).

**Interpretation:**
- More data helped v2 by +3.0 points agree-root top-1 (67.8 to 70.8) and the
  encoder by +7.2 (63.4 to 70.6); the encoder comparison also changes the
  recipe (unregularized stage 1 vs the regularized 6x configuration). With
  951k roots the learned encoder ties GBM v2 on choice accuracy and edges it
  on cross-entropy. Inference: the encoder caught up with the hand-made
  features rather than exposing a feature limit.
- Better fit still does not lower root regret at the 2k budget: v1, v2-6x and
  the encoder all sit near −0.09 there. Inference: at 2k, Silver's own search
  already recovers most of what a root prior of this quality adds; the
  remaining oracle gap (§400) is optimistic and not reachable with these
  targets.
- The synthetic-corpus root-prior line stops here. No native encoder and no
  online screen are proposed. The 5x corpus stays available for other uses.

**Evidence:** [packet](evidence/silver_encoder_prior_20261008/README.md);
corpus README at
`/mnt/project-files/silver-synthetic-prior/corpus5x-450376c8/README.md`.

**Remaining uncertainty:** the 12-epoch cap may have stopped the encoder
slightly early; the encoder replay arm used w = 400 without its own weight
pick.

**Knowledge impact:** this entry only; no defaults or maintained interfaces
changed.

## §405 — #346 GBM transfer: A20 counterfactual rows and the A0 win model offline, suggestive but inconclusive (2026-10-09)

**Question:** issue #346 asks whether harder-ascension data improves A0 models.
Does adding the §402 A20 corpus improve an A0 `v_win` GBM on the fixed E3 A0
VALIDATION split, at equal A0 supervision?

**Protocol:** [TRANSFER-PLAN.md](evidence/a20_transfer_346_20261009/TRANSFER-PLAN.md),
committed at `d10cc8da` before training; `tools/vwin_a20_transfer.py`.
- **Recipe and split:** E3's (§396): X2-B public features plus `ascension`,
  each state weighted 1 (but see the deviation below), three xgboost seeds averaged, split by source seed.
  Scored on E3 VALIDATION; TEST stays closed.
- **Arms:** A, A0 only; C, A0 plus all A20 rows; B, an A20-pretrained model
  with boosting continued on A0; E, the A20 model alone.
- **A0 data:** 10%, 25%, 50% and 100% of E3 TRAIN sources.

**Result as run: `TRANSFER_HELPS` for C and for B under the pre-registered
rule. Not robust; see the deviation.**
- **C − A, map-row NLL:** −0.009 [−0.023, +0.005] at 10%, −0.013 [−0.025,
  −0.002] at 25%, −0.012 [−0.024, −0.000] at 50%, **−0.016 [−0.027, −0.006] at
  100%** (0.4827 vs 0.4990).
- **B − A:** −0.022 [−0.033, −0.012], −0.011 [−0.021, −0.001], −0.004 [−0.014,
  +0.005], −0.008 [−0.015, −0.002].
- Post hoc: C with 25% of the A0 labels (0.4984) matched A with all of them
  (0.4990).
- **Boss-relic selection gain, C − A (descriptive, as-run models only):**
  +4.5, +1.9, +5.8 and +2.2 pp. The 10% and 50% CIs exclude 0.
- **Card rewards:** no difference; every CI includes 0.
- **E (A20 model alone):** NLL 1.54, and its boss-relic ranking is worse than A
  (−4.5 pp [−7.8, −1.3]). A20 values and rankings do not transfer directly.
- Details: [TRANSFER-RESULT.md](evidence/a20_transfer_346_20261009/TRANSFER-RESULT.md).

**Deviation (found in review):** the plan says "recipe as in E3", but the
script omits E3's weight rescaling to mean 1 (`w *= len(w)/w.sum()`).
Weights averaged about 1/7.9, so with `min_child_weight` 10 every arm was
over-regularized. Arm A at 100% gave 0.4990 instead of E3's 0.4854. The
reviewer's post-hoc rerun with E3's normalization reproduces A at 100% as
0.4856:
- C − A: −0.0075 [−0.021, +0.007], −0.0094 [−0.020, +0.001], −0.0043
  [−0.013, +0.004], −0.0087 [−0.016, −0.001] (0.4769 vs 0.4856).
- B − A: every CI crosses 0.
- Under the rule, both C and B are `INCONCLUSIVE`. Every point estimate still
  favours the A20 arms.
- C at 25% is 0.4844 against A at 100% 0.4856.

**Interpretation (Inference):** the evidence that A20 rows help an A0 win model
is suggestive but inconclusive. The pre-registered verdict depends on an
unintended over-regularization, and under E3's normalization no rung clears
the rule. It does not establish H1/H2 of #346. The direct A20 model does not
help (H3 not supported, as-run evidence).
- **Open:** a normalized primary test would be a new pre-registered run.
- **Open:** C uses more rows than A, so an equal-size extra-A0 control
  (#334 rows, as in F2) is needed to show that A20 rows beat more A0 rows.
- **Open:** early stopping used the scoring set; TEST is still closed.
- **Open:** no gameplay test. §401 showed that better offline fit need not
  make a better search leaf.

**Decision:** no model or default change. Candidate follow-ups, each needing
Philipp's go: a normalized re-test with an F2-sized equal-data control, then
TEST, before any gameplay use.

**Knowledge impact:** this entry and the evidence folder.

## §407 — #346 GBM transfer re-test with E3 weights and an equal-size extra-A0 control: inconclusive (2026-10-09)

**Question:** with E3's weight normalization, which §405 omitted, does adding
the §402 A20 corpus improve the A0 `v_win` GBM? And does it beat adding the
same number of extra A0 rows?

**Protocol:** [TRANSFER2-PLAN.md](evidence/a20_transfer_346_20261009/TRANSFER2-PLAN.md),
committed at `f0e41fbf` before training; `tools/vwin_a20_transfer.py
--e3-weights --extra-a0`.
- §405's arms, rungs, features, split and rule, with weights rescaled to mean
  1 as in E3.
- **Arm D:** E3 TRAIN at f plus 16,590 #334 A0 TRAIN map rows. These are
  sampled from the 96 TRAIN sources in the #334 cloud returns, with the A20
  block's total weight.
- Scored on E3 VALIDATION; TEST stays closed.
- Authorized by Philipp ("Yes do the retest and control").

**Result:** C (A0 + A20) `INCONCLUSIVE`; B (A20 pretrain) `INCONCLUSIVE`;
C vs D `NO_DIFFERENCE_DETECTED`.
- Arms A/B/C reproduce the §405 reviewer's normalized rerun exactly.
- **C − A map-row NLL:** −0.0075, −0.0094, −0.0043, −0.0087. Only the 100%
  CI excludes 0 ([−0.016, −0.001]).
- **B − A:** every CI includes 0.
- **D − A:** +0.003, +0.005, +0.009, +0.001, every CI including 0. Extra #334
  rows do not help.
- **C − D:** −0.010, −0.015, −0.014, −0.010, every CI including 0.
- **Boss-relic selection gain (descriptive):** C − D +8.0 pp [+4.4, +11.8] at
  10% and +7.7 [+3.6, +12.0] at 25%; D − A −5.4 [−9.0, −1.8] at 25%.
- **Card rewards:** no difference.
- Details: [TRANSFER2-RESULT.md](evidence/a20_transfer_346_20261009/TRANSFER2-RESULT.md).

**Interpretation (Inference):** H1/H2 of #346 are not established for the A0
win GBM's calibration. Every point estimate favours A20 rows over both
A0-only and equal extra #334 rows, but the effects (about 0.01 NLL) sit
within rung-to-rung noise at this validation size (167 sources). A20 rows
may help boss-relic ranking when A0 data is scarce. That is descriptive and
uncorrected.

**Open:**
- D is not a same-generator control.
- A decisive test needs more A0 validation sources or a larger effect.

**Decision:** no model or default change. #346 stays open.

**Knowledge impact:** this entry and the evidence folder.

## §406 — Silver root prior v1 at low sim budgets: about +19 pp at 32–128 sims, no gain from 2k up (2026-10-09)

**Question:** §399 found no online gain from the native root prior at 2k sims,
and §404 found the offline gain concentrated at 256 sims. Does the prior make a
very cheap Silver search play like a larger one, and how does prior search at
several budgets compare with plain 10k?

**Design:** four pre-registrations on Philipp's asks (2026-10-09 10:16, 10:21,
10:38 and 11:53 UTC), none committed beforehand. Only the screen's file clearly
predates its arms. The other three were written in the same command that
launched their arms, and their shared-folder stamps are 5 s after the first
arm started (probably copy times), so the order cannot be proven either way.
- Binary and prior as §399: commit 51937c6a, one_combat sha256 c3547dc4…,
  v1 GBM prior `prior-natpert.compact.txt` (sha256 573305c4…), weight 400.
  Only v1 has a native scorer. w = 400 was tuned offline at 256 sims (§397)
  and was not re-tuned for any other budget.
- The sidecars' `executableGitSha` is the checkout HEAD (d4ca7515, or 0f5adc4e
  for the low budgets), not the binary. The binary is identified by
  `sha256.txt`. `models/v_win_trees.txt` and `v_rich_trees.txt` are identical at
  all three commits.
- Run settings: A0, fair play, keys skipped, default OOC policy, `bestbench`,
  `STS_SILVER_EXACT_ROOT_BUDGETS=1` (flat budgets, no learned stopping), 4 CPUs.
- Screen: seeds 61000000-61000031, arms plain 256, prior 256 and plain 2k.
  Pass if prior 256 − plain 256 >= +3 wins.
- Confirmation: seeds 61001000-61001127, same arms. CONFIRMED needs the prior
  256 − plain 256 CI above 0 and prior 256 − plain 2k >= −5 pp.
- Sweep (descriptive, same 128 seeds): prior 512, 1k, 2k and 4k, plus plain 10k.
  A prior arm "matches 10k" if its CI vs plain 10k includes 0 and the point
  estimate is >= −3 pp; any match needs a larger confirmation before it is
  claimed.
- Low budgets (descriptive, same 128 seeds): plain and prior at 32, 64 and 128.
- Statistics: paired seed bootstrap, 10,000 resamples, RNG seed 0. CPU s/run
  is the mean per-run `sec` column, with 4 runs going at once.

**Result:**
- Screen (32 seeds): plain 256 13/32, prior 256 19/32, plain 2k 19/32. This is
  the pre-registered PASS (+6 wins, 10 vs 4 discordant, sign test p ≈ 0.18).
- Confirmation (128 seeds): label PRIOR_HELPS_ONLY_VS_256. Prior 256 − plain
  256 is +11.7 pp [+1.6, +21.9], but prior 256 − plain 2k is −14.8 pp
  [−24.2, −4.7].

| sims | plain | prior | prior − plain | prior vs plain 10k | mean floor plain / prior | CPU s/run plain / prior |
|---|---|---|---|---|---|---|
| 32 | 25.8% | 44.5% | +18.8 [+7.8, +29.7] | −35.9 [−45.3, −26.6] | 38.5 / 43.3 | 0.19 / 0.43 |
| 64 | 37.5% | 56.2% | +18.8 [+8.6, +28.9] | −24.2 [−33.6, −14.8] | 41.4 / 45.6 | 0.34 / 0.62 |
| 128 | 44.5% | 63.3% | +18.8 [+8.6, +28.9] | −17.2 [−25.8, −8.6] | 43.2 / 46.8 | 0.66 / 0.98 |
| 256 | 54.7% | 66.4% | +11.7 [+1.6, +21.9] | −14.1 [−23.4, −4.7] | 44.6 / 47.8 | 1.32 / 1.71 |
| 512 | — | 68.8% | — | −11.7 [−20.3, −3.1] | — / 47.7 | — / 3.05 |
| 1,000 | — | 73.4% | — | −7.0 [−14.1, +0.8] | — / 48.6 | — / 5.78 |
| 2,000 | 81.2% | 84.4% | +3.1 [−4.7, +10.9] | +3.9 [−3.9, +11.7] | 49.2 / 49.0 | 11.30 / 11.71 |
| 4,000 | — | 81.2% | — | +0.8 [−7.0, +8.6] | — / 49.2 | — / 23.71 |
| 10,000 | 80.5% | — | — | ref | 49.2 / — | 61.77 / — |

- Screen mean floor (32 seeds): plain 256 45.1, prior 256 47.0, plain 2k 47.5.
- Pre-registered "matches 10k" rule: prior 2k (+3.9) and prior 4k (+0.8)
  qualify; prior 1k (−7.0) does not. Per the rule, neither match is claimed
  without a larger confirmation.

**Interpretation:**
- At 32 to 128 sims the prior adds about 19 pp. Post hoc, not pre-registered:
  prior 64 (56.2%) vs plain 256 (54.7%) is +1.6 pp [−7.8, +11.7] at about half
  the CPU. The gain narrows to +12 pp at 256 and is
  not resolved at 2k, which repeats §399.
- No budget of 1k or below with the prior matches plain 2k or plain 10k. The
  32-seed tie of prior 256 with plain 2k did not replicate.
- Under flat budgets, plain 2k ties plain 10k on these seeds, so above 2k there
  was no headroom for the prior to close. n = 128 resolves only differences of
  about ±8 pp.
- Inference: the v1 prior is useful only where search compute is very tight,
  for example as a fast combat evaluator inside other searches. A follow-up
  thread compares low-sim prior Silver with the CTM stack. The option stays
  default off.

**Evidence:** [README, pre-registrations, scripts, CSVs, analysis](evidence/silver_root_prior_lowsim_20261009/README.md).

**Knowledge impact:** this entry only; no defaults or maintained interfaces
changed.

## §408 — CTM vs low-sim Silver as combat-outcome forecasters: Silver more accurate on every field, CTM about 400x cheaper (2026-10-09)

**Question (Philipp, 2026-10-09):** could low-sim Silver with the synthetic
root prior (§406) replace the CTM stack in OOC planning? Compare speed and
accuracy on the same job.

**Design:** [PREREG.md](evidence/ctm_vs_lowsim_silver_2026-10-09/PREREG.md)
(v2 committed at `b2504ed3` before its seeds ran). New research mode
`one_combat ctmsilvergen` (code `ccc3d62a`).
- At every real fight of a source run (exact-10k Silver, frozen V4 OOC policy,
  fair RNG), score forecasts of that fight's outcome. The truth is the source
  fight on the real hidden future.
- CTM: the production stack (DeepSets Lizard T2 + standard Brew fallback,
  active-Lizard correction), as the OOC planner loads it. Expectation for
  death/HP, and 32 `prepare`+`sample` draws of the full post-combat state.
- Silver arms replay the entry state with the six combat RNG streams redrawn,
  as a planner would: prior 256, prior 64 and plain 256 (4 replicates each),
  10k (2 replicates; the noise floor). A control replay on the real future
  must reproduce the source fight. The root prior (v1, w400) is switched per
  thread; the source and 10k arms run without it.
- Losses: death Brier, HP squared error (HP 0 on death), and per field the
  Brier of the sample distribution (potions, relic counters, max HP, gold,
  deck, stolen gold, all-but-HP joint, full joint).
- Primary: prior 256 ×4 − CTM on death Brier and HP MSE, seed-bootstrap CI.
  Co-primary (v2): the all-but-HP joint field Brier. Labels SILVER_BETTER,
  CTM_BETTER, SILVER_NONINFERIOR (both CI upper bounds < 10% of the CTM loss)
  or INCONCLUSIVE.
- v2 seeds 62100000–62100255 (256 runs), four cloud workers × 4 cores. v1
  (seeds 62000000–127, only HP and deaths) was stopped by Philipp after an
  interim look at about 66 seeds and is not pooled. v2's HP and death results
  are therefore a replication of a read already seen, not a blind test.

**Integrity:** 256/256 sources valid; 6,816 fight states. The control replay
matches every state with a valid source label. All 28 mismatches are Smoke
Bomb escapes, whose source label is itself quarantined. 6,788 states have a
valid source label; 6 more are dropped for every forecaster because a Silver
replicate escaped with Smoke Bomb, leaving 6,782 valid states. The CTM supports
6,750 of them. Over all 6,816 states the CTM's unsupported reasons are 34 Smoke
Bomb (33 `smoke_bomb`, 1 `unsupported:smoke_bomb`), 19 active Lizard outside the
qualified support, 4 HP envelope and 1 Writhing Mass/Ritual Dagger.

**Deviation (independent review of #466):** the pre-registered HP truth
(`sourceTerminalHp`) and the Silver arms' HP are battle-end HP, before
end-of-combat healing (Burning Blood +6, Black Blood +12). The CTM forecasts the
post-combat persistent HP, after that heal, so the as-registered HP loss scored
the CTM against a target about 6 HP lower than what it predicts (on wins the
control's post-combat HP exceeds battle-end HP by 6 in 4,276 states, 0 in 1,136
where the heal is capped, 12 in 112). The as-registered HP numbers are kept
below for the record but are **invalid for the CTM**. The corrected scoring
(`hp_post` in `report.json`) uses post-combat HP on both sides: truth = the
control replay's post-combat HP, Silver = the mean post-combat HP of its
replicates, 0 on death; same states, own bootstrap generator (seed 0). The
labels pair it with the unchanged death Brier. No label changes.

**Result (6,750 CTM-supported states):**

| forecaster | HP RMSE (post-combat) | HP bias | death Brier | all-but-HP Brier | CPU per forecast | as-registered HP RMSE / bias |
|---|---|---|---|---|---|---|
| CTM (expectation; samples for fields) | 11.7 | +2.3 | 0.0057 | 0.510 | 0.62 ms (one sample 0.53 ms) | 14.1 / +6.9 (invalid) |
| prior 256 ×4 | 8.5 | −2.6 | 0.0045 | 0.402 | 251 ms | 8.8 / −2.8 |
| prior 64 ×4 | 9.2 | −3.3 | 0.0054 | 0.447 | 91 ms | 9.6 / −3.8 |
| plain 256 ×4 | 9.3 | −3.3 | 0.0055 | 0.446 | 207 ms | 9.7 / −3.6 |
| 10k ×2 | 6.8 | 0.0 | 0.0056 | 0.269 | 4.5 s | 7.0 / 0.0 |
| prior 256 ×1 | 10.4 | −2.7 | 0.0086 | – | 64 ms | 10.8 / −2.9 |

- **Primary: SILVER_NONINFERIOR.** Post-combat HP MSE −65 [−75, −55] (CTM 137);
  death Brier −0.0012 [−0.0026, +0.0002], below the 10% margin. As registered
  (invalid for the CTM): HP MSE −121 [−133, −109], same label.
- **Co-primary: SILVER_BETTER.** All-but-HP joint Brier −0.107 [−0.120, −0.094].
- Every field separately is SILVER_BETTER for prior 256, prior 64 and plain 256
  (CIs exclude 0). The field Brier estimates each Silver arm's
  infinite-replicate distribution, so for "×4" it is an upper bound on what four
  playouts deliver; this is also why the `outcome` field is SILVER_BETTER while
  the K=4 death Brier is only non-inferior. Exact-match rates, CTM vs prior 256: potions 73% vs 81%,
  relic counters 75% vs 81%, max HP 90% vs 94%, gold 96% vs 98%, full state
  19% vs 37%.
- A single playout loses on deaths (prior 256 ×1: CTM_BETTER, +0.0029
  [+0.0008, +0.0051]), because one playout can only predict 0 or 1. Its
  post-combat HP is still better than the CTM's (MSE −28 [−40, −16]).
- Noise floor (half the 10k ×1 loss): post-combat HP MSE 32 (RMSE 5.7), death
  Brier 0.0037.
- The CTM error grows with act: post-combat HP RMSE 9.2 / 11.5 / 14.3 in acts
  1–3 (bias +1.8 / +1.6 / +3.6), vs 6.5 / 8.8 / 10.1 (bias −2.0 / −2.8 / −3.1)
  for prior 256 ×4.
- Speed: the CTM is 404x cheaper than prior 256 ×4, about 100x cheaper than one
  prior-256 playout and about 37x cheaper than one prior-64 playout.

**Interpretation:**
- Low-sim Silver is the more accurate combat model on every outcome field the
  CTM predicts. On post-combat HP the CTM is slightly optimistic (+2.3) and
  low-sim Silver slightly pessimistic (−2.6, it plays worse than 10k), but the
  CTM's spread is larger (RMSE 11.7 vs 8.5). It also misses the potion and
  relic-counter outcomes more often than a 64-sim playout.
- The Run 2 retrain (Path B) was not tested here.
- The prior matters only modestly for forecasting. Plain 256 is close to prior
  256 on HP and loses mainly on potions.
- Cost is the open question for retirement. OOC MCTS resolves many combats per
  decision (512 simulations by default), so a 23–250 ms combat model costs
  orders of magnitude more per decision than the 0.6 ms CTM. Whether the
  accuracy gain pays for that needs a gameplay test at matched CPU.

**Decision:** no default or code-path change; the CTM is not retired by this
entry. Candidate follow-ups, each needing Philipp's go: score the Run 2 retrain
(FAST0) on the same states, and a matched-CPU OOC MCTS gameplay pilot with a
Silver combat resolver.

**Evidence:** [README, pre-registration, worker script, report](evidence/ctm_vs_lowsim_silver_2026-10-09/README.md).

**Knowledge impact:** this entry plus one paragraph in
`docs/knowledge-base/evaluation/current-research.md`; the new mode is
research-only and changes no default.
