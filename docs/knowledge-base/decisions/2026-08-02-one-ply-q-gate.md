# Margin-gated one-ply Q gate for run-level overrides

Status: Adopted (deployed architecture; shop/TREASURE/boss-relic extension in progress)
Date: 2026-08-02
Last verified: 2026-08-02 against the current working tree.

## Decision

Learned overrides of run-level decisions are executed by a single margin-gated
one-ply Q gate. For the current screen, every legal action is scored directly
with the Q(s,a) head of the deployed strategic net on the pre-decision state
(`OocStrategicNet::predictActionValue`; input resolution identical to the
training rows via `strategicCands` — no successor clones, no RNG sampling at
deployment). The argmax action is executed only when its score margin over the
runner-up reaches `STS_OOC_STRATEGIC_MARGIN` (default 1.0); otherwise the
heuristic/default layer runs (floor value for card/shop, win-rate rest and
upgrade targets, heuristic events).

Screens covered: card rewards (round 3, EXPERIMENTS.md §73,
`apps/one_combat.cpp::oocOnePlyCardRewardPolicy`); campfires — rest options
plus smith upgrade targets — and events incl. Neow (round 4, §74,
`oocOnePlyRestPolicy`, `oocOnePlyUpgradeSelectPolicy`,
`oocOnePlyEventPolicy`, opt-in via `STS_OOC_STRATEGIC_REST=1` /
`STS_OOC_STRATEGIC_EVENT=1`, default **off** so the §73 card-only
configuration stays bit-reproducible). Shop/TREASURE/boss-relic gating is the
remaining plan scope (plan 5.5.1/5.5.4; round-6 work, in progress).

Direct successor-value scoring (the V2 path, reachable with
`STS_OOC_STRATEGIC_Q=0`) and greedy un-gated execution are **rejected** for
deployment: recorded regressions (§70 pooled-head gate −10.9pp at margin 1.0;
§73 greedy margin 0 → −3.9pp wins, 14 A-only / 9 B-only).

## Label contract (durable)

The Q head is trained on Tier-B one-ply counterfactual labels collected by
`strategicgen2` (`apps/one_combat.cpp::runStrategicGenSeed2`):

- **Schema:** the `strategicgen` columns unchanged, then
  `won,endFloor,endHp,labelWon,labelHp,labelFloor,labelBootstrap`
  (EXPERIMENTS.md §73).
- **Branches:** each legal action applied to a detached pre-decision copy,
  continued with the deployed-default OOC policy through the next K=3 battles
  (`STRATEGIC_BRANCH_FIGHTS=3`, `STRATEGIC_BRANCH_SIMS=150,100,50`,
  `STRATEGIC_BRANCH_FUTURES=1`), then bootstrapped to expected floor/P(win)
  from the native trees (`finishOocCounterfactual(..., maxFights=3,
  bootstrap=true)`, `STS_VNET=build/v_combat_fair_trees.txt`,
  `STS_VNET_ALPHA=0.3` — the §67b cheap-sims pattern, scaled up).
- **Common random numbers:** all branches of one decision share the branch
  seed, so action-vs-action label noise is largely common-mode and cancels in
  the pairwise comparisons the gate uses.
- **Sampling:** all decisions (`STRATEGIC_SAMPLE_ALL=1`; uniform screen
  coverage, per-screen Q metrics meaningful); the reservoir knob
  (`STRATEGIC_SAMPLES_PER_RUN`) is kept for cheap runs.
- **Target:** Q target `10·labelWon + labelHp` on every labeled row (same
  scale as the value head's `10·won + endHp`), so margin values stay
  comparable across rounds.

## Rationale

- **Inference (gate):** un-gated greedy NN overrides of heuristic OOC
  decisions are a recorded failure mode (§66m, §70, §73 margin 0 — the Q
  model too), so the margin gate is a deployment invariant, not a tuning knob;
  it bounds any per-decision damage while the Q head's ranking improves.
- **Inference (one-ply, no clones):** direct Q scoring on the pre-decision
  state removes successor-state approximation and the head-interleave hazard
  that corrupted the deployed V2 artifact (§73 correction); the Q input
  resolution is input-identical to the training rows.
- **Inference (labels supersede plan 5.5.3):** each Tier-B label is the
  concrete branch outcome under CRN (K=3 battles + bootstrap), so the label
  already averages the stochastic continuation — no RNG-clone sampling is
  needed at deployment. Documented deviation, not a loss of mechanism.
- **Inference (event upside):** events were the default heuristic's weakest
  screen (§71 EVENT value MAE 5.21), and the card gate showed Q works where
  the state-value head did not — the event gate is the round-4 main
  contributor (+5.5pp wins alone, §74), roughly additive with the other
  layers.
- **Inference (default-off flags):** new gates ship behind default-off knobs
  so the prior configuration stays bit-reproducible and layer-wise ablations
  are possible.

## Alternatives considered

- Greedy un-gated execution — rejected: §70 pooled-head gate (−10.9pp at
  margin 1.0), §73 margin 0 (−3.9pp wins), the §66m lesson.
- Direct successor-value scoring of cloned successors (V2 path,
  `predictValue(state, screen)`) — rejected as the deployed path: the §70
  gate regression; the V2 gate never fires at margin ≥ 0.5 (§73); the round-2
  exporter wrote the 8 value heads per-head-interleaved while
  `OocStrategicNet::load` reads block-major, so deployed heads 1–7 read
  garbage (§73 correction; V3 exporter writes block-major, verified by a C++
  harness). Kept reachable behind `STS_OOC_STRATEGIC_Q=0` as a fallback, not
  the deployed path.
- RNG-clone outcome sampling at deployment (plan 5.5.3) — superseded: the
  Tier-B labels already average the stochastic continuation per action.
- Per-screen margin knobs — rejected: one shared margin plus margin probes
  keeps gate semantics uniform; §74's combined stack peaks at margin 1.0
  anyway.
- Always-on rest/event gates when the net loads — rejected: would conflate
  layers and break the §73 comparison.
- V4 token net as the deployed default — rejected (§75): better held-out
  ranking (policy top-1 0.793 vs 0.784) but the deployed gate (+3.1pp @ m5)
  did not beat V3's +7.0pp @ m1 on the same block; V3 stays deployed, V4 is
  opt-in behind `STS_OOC_STRATEGIC_TOK_NN`.
- Next-battle-only and whole-run branch horizons for the labels — rejected at
  round-3 datagen (see `docs/knowledge-base/decision-log/2026-08-02-phase5-round3-tierb-q-labels.md`).

## Evidence

- EXPERIMENTS.md §73 (round 3): Tier-B dataset 3,057,708 rows / 4,650 seeds /
  723,851 decisions; held-out policy top-1 0.784, **Q top-1 0.284, Q MAE
  14.32 / RMSE 20.07**, per-screen Q MAE 13.3–16.9; export parity logit
  9.9e-06 / value 1.0e-04 / Q 5.1e-05. Q-head card gate (fair, 1,000 sims,
  seeds 126700–126827, bit-identical baseline 21.1% / 37.5 / 8.6): margin 0
  → 22 (−3.9pp), 0.25 → 26 (−0.8pp), 0.5 → 33 (+4.7pp), 1.0 → 29 (+2.2pp),
  5.0 → 26 (−0.8pp); all 95% CIs span zero. First strategic gate to fire at
  margin 1.0 (20/128 discordant); the margin curve is non-monotone with a
  peak at 0.5.
- EXPERIMENTS.md §74 (round 4): cards+rest+event at margin 1.0 → **36 wins
  (28.1%, +7.0pp)**, floor +1.38, score +2.09, win CI [−1.2, +15.2]pp; margin
  0.5 → +3.1pp; margin 5.0 → +2.3pp. Ablations at m1: event-only +5.5pp
  (main contributor), rest-only +1.6pp, cards-only +2.2pp — roughly additive.
- EXPERIMENTS.md §75 (round 5): V4 token net (opt-in) +3.1pp wins at margin
  5.0, floor/HP gains at every margin, CIs span zero — does not beat the V3
  reference (+7.0pp @ m1); **V3 remains the deployed default**.
- Deployed artifacts (hashes of the current tree): `selfplay/models/ooc_strategic.native`
  (V3, sha256 `9d1f870b…fef8`), `selfplay/models/ooc_strategic_tok_final.native`
  (V4 opt-in, sha256 `05178ec8…9e1ea`); dataset `build/strategic_tierb.csv`;
  baseline `build/tierb_gate_base.csv`; gate outputs `build/tierb_gate_{base,m0,m025,m05,m1,m5}.csv`,
  `build/tierb_re_gate_{m1,m05,m5}.csv`, `build/tierb_{rest,ev}_only_m1.csv`,
  `build/tok_gate_{m1,m05,m5}.csv`.
- Gate functions: `apps/one_combat.cpp::oocOnePlyCardRewardPolicy` (line
  3081), `oocOnePlyRestPolicy` (3149), `oocOnePlyUpgradeSelectPolicy` (3193),
  `oocOnePlyEventPolicy` (3240), wired into `runFullRunOOC` and
  `runTraceRun`; margin/knobs parsed in `main`.

## Consequences (observed)

- The pipeline (collect → train → export → native one-ply → paired gate)
  works end-to-end; no strategic model is deployed by default — all one-ply
  layers are opt-in (`STS_OOC_STRATEGIC_NN`, `STS_OOC_STRATEGIC_Q`,
  `STS_OOC_STRATEGIC_REST`, `STS_OOC_STRATEGIC_EVENT`,
  `STS_OOC_STRATEGIC_TOK_NN`).
- The margin curve is non-monotone (card-only peak at 0.5; combined stack
  peaks at 1.0), so gate rounds sweep margins rather than assuming a
  monotone trade-off.
- The V3 exporter writes value heads block-major, fixing the V2
  head-interleave corruption; native loads validate header/dims and every
  payload read.
- The Tier-B label contract supersedes plan 5.5.3's deployment-time RNG-clone
  sampling; the one-ply Q gate replaces the successor-value V2 path.
- The round-3 verdict pre-registered a neutral-with-Q-labels result as
  acceptable; observed results are directionally positive but none are
  statistically established on the 128-seed block.

## Superseding or invalidating evidence

- §70 and §73 (margin 0) invalidate greedy un-gated deployment for both the
  pooled-head and the Q-head models.
- §73's V2 head-interleave correction invalidates §71's per-seed-neutral
  verdict as measured against the deployed V2 artifact (the trainer-side
  per-screen MAE table is unaffected).
- §75 keeps V3 as the deployed default and the V4 token net opt-in.
- §72 invalidated the recorded PVNet 66.4% combat headline — combat-side
  evidence; it does not change this gate decision.

## Relevant code

- `apps/one_combat.cpp` — `oocOnePlyCardRewardPolicy`,
  `oocOnePlyRestPolicy`, `oocOnePlyUpgradeSelectPolicy`,
  `oocOnePlyEventPolicy`, `runFullRunOOC`, `runTraceRun`,
  `runStrategicGenSeed2`, `strategicGen2`, `main` (env parsing)
- `apps/ooc_strategic_net.h` — `OocStrategicNet` (`predictActionValue`,
  `load`)
- `apps/ooc_strategic_tok_net.h` — `OocStrategicTokNet` (V4, opt-in)
- `train_strategic.py`, `export_strategic.py`; `train_strategic_tok.py`,
  `export_strategic_tok.py`, `strategic_tok_net.py` (V4)
- `docs/knowledge-base/architecture/out-of-combat.md`,
  `docs/knowledge-base/architecture/ooc-strategic-v4.md`
- `docs/archive/ooc-action-plan-2026-08.md` — historical plan (former spec of record,
  5.5.1–5.5.4)
- Decision log: `docs/knowledge-base/decision-log/2026-08-02-phase5-round3-tierb-q-labels.md`,
  `2026-08-02-phase5-round4-campfire-event-gates.md`,
  `2026-08-02-phase5-round5-token-state-v4.md`
