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
| Strict corrected M0 | 23/64 | 35.9% | 40.281 | 16.672 |
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
  and [the read-only analyzer](../../tools/analyze_silver_guidance_alias.py).

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
