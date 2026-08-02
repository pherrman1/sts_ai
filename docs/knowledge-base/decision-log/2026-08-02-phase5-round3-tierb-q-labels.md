# 2026-08-02 — Phase 5 round 3: Tier-B one-ply counterfactual labels + Q-head gate

Date: 2026-08-02
Session/task: Collect Tier-B one-ply labels (strategicgen2), train a Q(s,a) head, export OOC_STRAT_V3, and gate card rewards on direct Q scoring.

## Decision

Added `strategicgen2` (Tier-B one-ply labels), a Q(s,a) head to
`train_strategic.py`, `OOC_STRAT_V3` export with `predictActionValue`, and
switched `oocOnePlyCardRewardPolicy` to direct Q scoring of legal card-reward
actions (V2 successor-`predictValue` path kept behind `STS_OOC_STRATEGIC_Q=0`).

Label design:

- **Horizon: K=3 battles + bootstrap** (`STRATEGIC_BRANCH_FIGHTS=3`,
  `STRATEGIC_BRANCH_SIMS=150,100,50`, `STS_VNET` combat value net leaf,
  `STS_VNET_ALPHA=0.3` — the §67b cheap-sims pattern, scaled up). Each branch
  continues with the deployed-default OOC policy through the next 3 battles
  and bootstraps expected floor/P(win) from the native trees. Label target
  scale: `10·labelWon + labelHp`, matching the value head's `10·won+endHp`.
- **Sampling: all decisions** (`STRATEGIC_SAMPLE_ALL=1`; ~5,600 seeds,
  ≈2.7–3.0M rows, ≈6h of datagen). Uniform screen coverage, no sampling bias;
  the reservoir knob (`STRATEGIC_SAMPLES_PER_RUN`, uniform over decisions) is
  kept for sparse/cheap runs.
- **Common random numbers**: all branches of one decision share the branch
  seed (per future), so action-vs-action label noise is largely common-mode
  and cancels in the pairwise comparisons the gate uses.
- **Q head**: `Linear(168,96)→GELU→Linear(96,1)` on the same
  (state, action-bits, action-cat, screen) concat as the policy head, sharing
  the state/action encoders. Loss `CE + 0.5·value_MSE + STRAT_QLAMBDA·Q_MSE`
  (λ default 1.0); Q loss on every labeled row.
- **Trainer memory**: for multi-GB CSVs the state block is chunk-read,
  standardized on train rows only, and written once to a group-ordered float16
  file (`OUT + "_state.bin"`); training reads contiguous mmap slices, so
  ~15M-row datasets fit a 31GB machine.
- **Gate**: direct Q scoring (no successor clones) inside
  `oocOnePlyCardRewardPolicy`, margin gate `STS_OOC_STRATEGIC_MARGIN`
  retained (greedy un-gated deployment is a recorded failure mode, §66m).

## Rationale

- **Inference:** §66l showed next-battle labels transfer to 3-checkpoint
  utility at Spearman 0.64; the Q head's deployment target is whole-run
  utility, so a 3-battle horizon with bootstrap should transfer better than
  the spec's next-battle+50-sim labels. User chose K=3/150-100-50 over both
  the spec-strict next-battle config and whole-run cheap-sims (which compounds
  battle variance).
- **Inference:** CRN makes per-decision action comparisons far less noisy than
  absolute labels, so extra per-battle sims have diminishing returns for the
  ranking metric; the horizon is where the bias sits.
- **Inference:** all-decision sampling gives the Q head uniform coverage
  across screens and decisions at equal total cost to sparse sampling, and
  makes per-screen Q metrics meaningful.
- **Inference:** Q target `10·labelWon+labelHp` keeps the gate margin knob on
  the same scale as §70/§71, so margin values stay comparable across rounds.
- **Unverified:** fair-trained `v_combat_fair_trees.txt` (the only tracked
  combat VNet) is used as the leaf inside known-RNG branch battles; regime
  mixing is recorded in provenance and could bias branch battle strengths.

## Alternatives considered

- Next-battle-only horizon with 50/25/10 sims (the task's written default) —
  rejected by user choice: weaker labels, direct §66l comparison was the only
  upside.
- Whole-run branches at cheap sims (no bootstrap) — rejected: battle search
  noise compounds across ~40 fights; §67b shows bootstrap-to-horizon at cheap
  sims is near-full-strength and cheaper.
- Sampling N decisions per run via reservoir (the written spec) — kept as a
  knob (`STRATEGIC_SAMPLES_PER_RUN`), but the run uses `STRATEGIC_SAMPLE_ALL=1`
  for uniform coverage; reservoir branch work is wasted when a slot is
  replaced, acceptable only for cheap runs.
- A few-hour datagen without trainer restructure — rejected: the pandas
  trainer needs ~8–10× CSV size in RAM; 5k+ seeds would exceed 31GB. The
  float16 group-ordered mmap restructure removes the ceiling.
- Q head trained on a subset (chosen rows only) — rejected: the point of
  Tier-B is per-action labels; all rows are labeled under sample-all.

## Evidence

- Datagen: `strategicgen2 5600 1000 0 build/strategic_tierb.csv 128000` with
  `STRATEGIC_SAMPLE_ALL=1 STRATEGIC_BRANCH_FIGHTS=3
  STRATEGIC_BRANCH_SIMS=150,100,50 STRATEGIC_BRANCH_FUTURES=1
  STS_VNET=build/v_combat_fair_trees.txt STS_VNET_ALPHA=0.3` (≈6h, 12
  threads). Smoke (5 seeds): 2,669 rows, all labeled, chosen-row
  `labelWon~won` Pearson 0.818, `labelHp~endHp` 0.567; bootstrap rate 74%.
- Trainer (`train_strategic.py`) smoke on 5 seeds: policy top-1 0.547, Q top-1
  0.156, Q MAE 16.4 (3 epochs, tiny data); full metrics incl.
  `q_top1/q_mae/q_mae_screen` in `_metrics.json`.
- Export parity (real checkpoint): logit 5.9e-06, value 6.5e-05, Q 1.3e-04
  (< 1e-4/2e-4/2e-4); C++ harness cross-check value 1.6e-08, Q 3.8e-07.
- **Correction (V2 native value heads misaligned):** the round-2 exporter
  wrote the 8 value heads per-head-interleaved while `OocStrategicNet::load`
  reads block-major; in the deployed `OOC_STRAT_V2` artifact only head 0
  (TREASURE) was aligned, heads 1–7 read garbage in C++. §71's per-seed-neutral
  gate and the §73 V2-path margin diagnostics (0.5, 0.25) therefore measure
  that misaligned deployment; the trainer-side per-screen MAE table (§71) is
  unaffected. The V3 exporter writes block-major (verified by a C++ harness
  against the numpy reference).
- V2-path gate diagnostics (patched V2 artifact loaded as V3 with
  `STS_OOC_STRATEGIC_Q=0`): margin 0.5 → per-seed identical to baseline
  (21.1%/37.5/8.6); margin 0.25 → 24.2%/38.0/9.3, +3.1pp wins, floor +0.55,
  score +0.86, CIs span zero, discordant 2 A-only / 6 B-only. The V2 card gate
  never fires at ≥0.5 and is directionally positive (not significant) at 0.25.
- Round results (EXPERIMENTS.md §73): dataset 3,057,708 rows / 4,650 seeds /
  723,851 decisions (seed 128087 excluded — pre-existing
  `BattleContext::executeActions` loop-guard assertion); held-out policy
  top-1 0.784, Q top-1 0.284, Q MAE 14.32; export parity logit 9.9e-06 /
  value 1.0e-04 / Q 5.1e-05. Q-head gate (fair, 1,000 sims, seeds
  126700–126827, baseline bit-identical re-measure): margin 5.0 → −0.8pp
  (3 discordant), margin 1.0 → +2.2pp wins / floor −1.27 (20 discordant),
  margin 0.5 → +4.7pp wins / floor +0.06 (30 discordant); all deltas' CIs span
  zero. Greedy margin 0 → −3.9pp wins (14 A-only / 9 B-only) and margin 0.25
  → −0.8pp: the margin curve is non-monotone with a peak at 0.5, and the
  un-gated regression confirms the gate does essential work (§66m lesson).
  The Q gate is the first to fire at margin 1.0 and is directionally
  win-positive at 0.5 — the opposite shape of §70's damage curve — but not a
  statistically established improvement.

## Status and follow-up

Implemented; gate verdict recorded in EXPERIMENTS.md §73 (mixed: fires at
margin 1.0, win-positive only at margin 0.5, CIs span zero; greedy margin 0
regresses). Follow-ups: (1) extend the one-ply Q gate to events/maps/other
screens as a SEPARATE round — the benchmark only ever touches card rewards,
everything else stays heuristic (user decision); (2) A/B the label horizon
(K=1 vs K=3) with multi-truncation labels; (3) A/B `STRATEGIC_BRANCH_FUTURES`
for encounter averaging; (4) rest/shop/TREASURE gated one-ply where
per-screen value MAE is strongest; (5) fix or isolate the
`BattleContext::executeActions` loop-guard assertion (seed 128087 crashes);
(6) consider a `decisions/` record for the Tier-B label contract once §73
stabilizes it.
