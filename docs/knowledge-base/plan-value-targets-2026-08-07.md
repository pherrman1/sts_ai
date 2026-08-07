# Combat-value targets plan — frontier-leaf data, particle relabeling, utility-distribution target (2026-08-07)

Status: **ACTIVE companion plan** to `plan-winrate-ideas-2026-08-07.md`. Phases are
numbered 1-7 in the order proposed by the user on 2026-08-07. Phase 1 is
**owned by another agent** and not duplicated here. Phase 6 (PVNet deployment
speed) is **implemented 2026-08-07** (gate pending); phase 5 (value-only
utility-target model) was skipped this session by user instruction (a phase-5
trainer draft was reverted). Frontier-leaf labels from phases 2-4 slot in when
they land. Every policy-affecting item gets its own paired gate per the repo
protocol.

## 1. Relationship to the winrate plan (no conflict — one amendment)

| Winrate plan item | Interaction |
|---|---|
| §2 baseline B1–B4 | Untouched. Still the prerequisite for every paired gate; this line reuses the §124 reference. |
| §3 Wave 1 (S3 diag, ablation, cPUCT, prior v2, multi-select) | No overlap — prior/policy side. |
| §4.1 / §4.2 (expand, TERM_WIN cpsi) | No overlap. |
| §4.3 boss-conditioned NN leaf | **Amendment:** §4.3 step 1 ("train a fresh combat value net on post-§113 honest trajectories via fairgen") is superseded by the phase-2/3 labels here (frontier leaves + particle-multisample + high-budget + utility distribution). §4.3's *conditional application* survives and becomes the deployment vehicle for phase 6 (merged with continuation-length gating). |
| Closed lines §97/§102 (unconditional combat VNet), §102/§103 (PVNet policy/value) | Not reopened. This line is a new angle: conditional application + different data + different target, each with its own gate per the protocol. |
| §5.1 self-play relabeling (deferred) | Stays deferred; this is combat-leaf value, orthogonal to strategic relabeling. Shares the premise (teacher = deployed full stack). |
| Compute | S3 gates keep priority; phases 2/3 run local + GCP idle; phase 5 training local (RTX 3060 Ti). |

## 2. Verified current state (2026-08-07, HEAD 7b1a8d2 + uncommitted §123)

- Value dataset = one row per combat decision, each stamped with the **single
  realized** `(won, endHp)` of the teacher's own play (`apps/one_combat.cpp`
  `runCombatGenSeed`, fairgen path). Confirms the noise/distribution critique.
- **HP-fraction mismatch confirmed:** quantile head trained on `endHp/maxHp`
  fractions (`train_combat_pvnet.py:268`) but `CombatPVNet::leafValue` uses them
  raw with winBonus 50 (`src/sim/search/CombatPVNet.cpp:354`); opt-in
  `STS_PVNET_HP_SCALE` fix exists (§123), default OFF. `CombatDistValueNet.cpp:53`
  `riskAdjustedValue` ignores its maxHp argument entirely (latent bug, only under
  `STS_DIST_VNET`). → owned by the phase-1 agent.
- **No mid-combat state serialization exists.** `BattleContext` is copyable and
  self-contained (RNG streams, player, monsters, cards, potions;
  `include/combat/BattleContext.h`), `CombatObservation::visibleHash()` exists —
  a leaf serializer is straightforward new code (phase 2).
- S3 frontier sites to instrument: unexpanded leaf
  (`BattleScumSearcher3.cpp:267-346`), illegal-fallback rollout (`:418-422`),
  depth cap (`:438-439`); leaf blend at `:327-343`; `evaluateLeaf` `:597-613`.
- PVNet leaf = 1 forward/sim, no batching (`policyScores` batch helper is dead
  code), 14-18× rollout cost at 3k (§102). The 1766-feature state block is
  **card-id counts only** — per-card cost/upgraded exist only in the 14-feature
  action block (`CombatValueNet.cpp:136-140`).
- Checkpoint selection = combined value+policy val loss
  (`train_combat_pvnet.py:530-532`). Export = native text `combat_pvnet_v1`.

## 3. Phases

### Phase 1 — HP-fraction scale fix — OWNED BY ANOTHER AGENT
Not duplicated. Note for the other agent: fix `CombatDistValueNet.cpp:53` mH bug
only if `STS_DIST_VNET` is used in an active line.

### Phase 2 — frontier-leaf diagnostic corpus (`frontiergen` mode)
New `one_combat` mode, S3 fair only (decision). Runs the deployed full stack
(`STS_FAIR=1 STS_SEARCHER3=1 STS_S3_BELIEF=0 STS_S3_CHAIN=0`, live-valid ON, V4
gates, **explicit `STS_LIVE_VALID=1`** — datagen is not covered by the default,
§123) over fresh seeds (400000+). At each S3 frontier site, save:

- full `BattleContext` binary snapshot (new serializer; restore resamples hidden
  RNG/draw per particle anyway, so visible-state integrity is all that matters)
  + 1766 features (`combatFeatureRow`) + `visibleHash` + metadata:
  seed/fightIdx/decIdx, turn, floor/act/room/encounter, budget, frontier-type
  (unexpanded|illegal-fallback|depth-cap), rollout length, tree depth, root
  policy entropy, curHp/maxHp, isBoss.
- Round-trip test: save→load→`combatExtractFeatures` identical (new unit test).
- Oversample strata: boss rooms, turn ≤ 3, deep unresolved leaves,
  illegal-fallback leaves, entropy ≥ threshold, curHp ≤ 30% maxHp. Dedup by
  `visibleHash` (keep first + count). Target **10-50k leaves**.

Verify: serializer round-trip test; `ctest`; smoke 8 seeds local, corpus stats table.

### Phase 3 — relabeling (`leafrelabel` mode)
Per saved leaf: restore snapshot, run S3 with `STS_S3_PARTICLES=16` (8-32 knob)
at high budget (10k, optionally 30k for a ~100-leaf subsample), instrument to
record **per-sim terminal outcomes** (rollout ends + terminal-in-tree):
`(won, endHp)` → empirical distribution P(win), HP|win histogram, mean,
quantiles; per-particle breakdown.

- **Sibling mode:** store parent-action context in phase 2; per leaf, evaluate
  siblings with the **same particle set** (CRN — construct one Belief from the
  parent visible state, apply to each sibling; small searcher API addition).
  Sibling evals at 3-5k sims.
- Output: `leaf.csv` (absolute labels) + `sibling.csv` (pairwise A>B). Sanity
  check: tree's own PUCT root value vs rollout distribution (investigate if
  they diverge).
- Budget (decision): relabel **500-1000 leaves** (≈3-8 h single-process at
  30 s/leaf; parallelize on GCP), siblings cheap; grow to 1-2k only if phase 4
  demands.
- Verify: 5-leaf smoke (label stability across 2 runs with same seeds), CSV
  schema pinned before batch.

### Phase 4 — sibling-ranking evaluation of the current PVNet (offline gate, no training)
Extend `eval_combat_pvnet.py`: on the phase-2/3 corpus compute **pairwise
ranking accuracy, top-1 leaf accuracy, Spearman,
regret = teacherV(bestTeacher) − teacherV(modelBest)**, broken down by
room/boss, turn, depth, rollout length, frontier-type, entropy, HP level.
Recompute Brier/ECE on the frontier corpus (vs the 0.107/0.002 on-policy numbers).

Pre-registered decision: if the current PVNet already ranks frontier siblings
well (top-1 ≥ 80%, Spearman ≥ 0.7), the value-quality hypothesis is weakened —
deprioritize 5/6, keep the conditional-application work. If poor, proceed.

### Phase 5 — value-only model, terminal-utility distribution target (EXECUTED 2026-08-07, §128)
- **Done (this session):** `train_combat_utility.py` (value-only 14-token
  encoder + single 51-bin head over R = 0 | 50+endHp, CE loss) trained on the
  §127 datagen rows (`build/fair34_v.csv`, 225k, vnet-era controller) →
  `build/v_combat_utility.txt` (native `combat_utility_v1`; encoder section
  identical to v1, one `util` head). Eval `eval_combat_utility.py` + utility
  parsing in `combat_pvnet_parity.py`. **Offline result (30k identical
  held-out rows): win Brier 0.0647 / ECE 0.0688 / death BCE 0.2287 vs the
  tracked PVNet's 0.2505 / 0.3298 / 2.2076** — and the tracked PVNet itself
  miscalibrates on the new distribution (0.107 Brier recorded on its own
  data), confirming the phases-2-4 distribution-gap premise.
- Nothing deployed: no C++ integration (vnet owns the leaf, §126).
- **Deferred:** clean target-only ablation (same rows, win/quantile heads vs
  51-bin), shared-encoder variant (dual-CSV policy pass), folding the
  fresh-data + direct-target recipe into the vnet GBM retrain line, C++
  loader for `combat_utility_v1` (only with a deployment gate).
- Next: sibling-ranking eval (phase 4) once phase-2/3 leaf data exists.

### Phase 6 — conditional deployment + inference speed (IMPLEMENTED 2026-08-07, gate pending)
Implemented in this session (user request; phase 5 value-only model was
skipped/its changes reverted):
- `STS_PVNET_COND_{TURN,DEPTH,BOSS}`: gate the per-expansion PVNet leaf in
  `BattleScumSearcher3` (`pvnetCondAllowed`) — cheap/easy continuations
  (early turn, shallow tree, non-boss) use the ordinary rollout only; the NN
  fires for long/unresolved continuations. Direct-eval and post-rollout
  `evaluateLeaf` calls stay ungated. Defaults preserve pre-phase-6 behavior.
- `STS_PVNET_CACHE` (default ON): visibleHash (`node.obsHash`) leaf-value cache
  at the direct-eval sites — verified behavior-preserving (identical per-seed
  outcomes cache-on vs off, 8 seeds @300 sims local).
- **Not implemented (recorded reasons):** batched NN leaf calls — the S3 leaf
  eval is on effectively unique states (new child per expansion), so a
  deferred/queued batch would require restructuring `step()`/`backpropagate`
  for ~BLAS-efficiency-only gain; deferred pending a real gate signal.
  GBM/MLP distillation — phase-5 training line, not this session.
  Rollout-skip at α=1.0 — observed that `playoutRandom` still runs and its
  terminal value is discarded by the α=1.0 blend (wasted compute), but
  removing it changes `bestActionSequence` semantics; candidate knob for a
  later session, not implemented.
- Local smoke (8 seeds @300 sims, PVNet α=1.0, fair S3−belief−chain/64p):
  cache-on == cache-off per-seed outcomes; all three cond knobs change
  behavior and print in the banner; `ctest` 5/5.
- **Gate — RE-EVALUATED 2026-08-07 after §124-§126 landed (commit 3f04e82):
  NOT run; deferred to a phase-5-model revisit.** Reasons, verified against
  HEAD: (1) the §126 vnet promotion makes the VNet the fair-S3 default leaf
  (α=0.3, +12.5/+12.1/+12.5pp, three significant gates) and the S3 blend site
  is `if VNet … else if PVNet …` — the PVNet leaf (and therefore these knobs)
  is shadowed in the default stack, so a gate now would measure an off-default
  config; (2) §126's own conditioning test (vnet cond-boss at both α: flat,
  ~13-15% discordance — "the value is spread across all rollout-heavy
  contexts, not just bosses") directly weakens the conditioning premise of
  the COND_* knobs; (3) the pre-registered §4.3 rule (null at both budgets
  closes the leaf line) is effectively consumed by §126's answer to the leaf
  question: the GBM leaf wins, the NN leaf line stays closed (§102). The
  coherent next gate is phase-5's value-only utility model (when it lands) +
  these speed knobs, paired vs the §126 vnet default
  (`build/vnet_all_a03_1k.csv`, 50.4% @1k/64p). The knobs remain committed;
  `STS_PVNET_CACHE` is behavior-preserving and defaults ON. Decision log:
  `2026-08-07-pvnet-gate-recheck.md`.

### Phase 7 — larger model
Only if phase 6 shows per-card token value and cpu budget permits:
D=192-256, 3-4 layers sweep, same gate. (Per-card-instance tokens were
originally step 6 of the user's ordering; they are folded into phase 6's
model-side work if phase 5's value-only result is positive.)

## 4. Recording

EXPERIMENTS.md entry per phase (config/flags/models/seeds/artifacts); decision
log entry on session close (plan adoption + §4.3 amendment); KB:
`combat-search.md` (leaf-eval section), `training-and-inference.md`,
`current-baselines.md` only on headline change. Traps from AGENTS.md apply
(load-message verification, bestbench append-no-dedup, clean rebuild on header
changes, no fair/known-RNG mixing).
