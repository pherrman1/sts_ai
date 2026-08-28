# Current research status

Last verified: 2026-08-28 against the current working tree.

## Purpose

This page is the single routing source for active, parked, and closed research
lines. It does not replace the current benchmark configuration in
[current-baselines.md](current-baselines.md), chronological evidence in
`EXPERIMENTS.md`, or implementation contracts in the architecture pages.

## Active line

### Encounter-marginalized strategic labels

The 2,000-source-seed matched M0 (fixed-world) vs M1 (encounter-marginalized)
experiment completed (2026-08-15). On the preregistered 64-seed paired gameplay
gate (seeds 900000–900063, frozen S3 + 7k-VNet Act-3 stack, all strategic
screens ON, margin 1.0), M1 did not separate from M0:

- M0 17/64 = 26.6%; M1 16/64 = 25.0%; paired Δ (M1−M0) = **−1.6pp**, 95% CI [−14.1, +10.9]pp.
- Offline best-CE: M0 `val_pol_ce` 0.50897 vs M1 0.51181 (both trained 40 epochs).

Per the preregistered decision rule this is a **null / approximately-equal**
result: encounter marginalization does not separate from the fixed-world control
at 2,000 source seeds. It does not support promotion or immediate scaling to
5,000 seeds. A corrective same-seed/same-config Act-3 calibration (§169) placed
deployed V4 at 37.5% vs M0 26.6% / M1 25.0% — so the Phase-12 models remain
below V4, but by a smaller same-block margin (the historical 48.4% V4 figure was
a different Act-3-only seed block, not a direct comparator). A separate
bottleneck (H4) remains plausible; do not infer that fixed-world leakage is
beneficial. See [ledger-06 §168–169](../../../docs/experiments/ledger-06.md) and
the
[Phase 12 decision log](../decision-log/2026-08-14-phase12-encounter-marginalization-next-step.md).

Evidence:

- [Encounter-marginalization final report](../encounter-marg-final-summary-2026-08-10.md) (500-seed pilot, +3.1pp M1)
- `docs/experiments/ledger-06.md` §168 (2,000-seed null result) and §169 (corrective Act-3 gate + V4 calibration)
- `apps/one_combat.cpp::strategicMargGen`
- `tools/convert_marg_to_trainer.py`, `tools/reconstruct_marg_csv.py`

### Silver root action-pruning ladder

Phase 1 is complete: a frozen, tie-safe candidate-retention audit evaluated
current Silver order, frozen parent-Q scores, and 1k/10k/25k-A teacher Q and
visit rankings against all 93 independent 25k-B anchors. Its primary population
was the 63 multi-action parents; the 30 single-action parents were reported
separately and do not inflate retention claims. Frozen-model top-3-plus-ties
retained 95.24% of the B-best actions, but still had two `>=3` regret
exclusions, so it provides no hard-pruning permission. The Phase 2 decision is
`SEQUENTIAL_HALVING_REJECTED`: the fresh-session 63-parent gate regressed mean
regret at 64/128/256/1000, lost five best-action matches at 1000, and introduced
new >=3-regret exclusions despite a 0.998x replay CPU ratio. A subsequent user-
requested, narrower progressive-unpruning experiment was evaluated separately:
only roots with at least six actions began with the current-Silver-order top 3,
then recovered one stored edge after 16/32/64/128 new simulations. It is
`PROGRESSIVE_CURRENT_ORDER_HARMFUL`: its 128 and 256 results increased mean
regret (the latter also added a >=3-regret failure), even though its 1000 result
improved and replay CPU was 1.007x ordinary. The cached frozen-model ordering,
runtime scorer, hard pruning, and gameplay smoke remain unauthorized. The
previous rejection of learned ordinary ordering/PUCT remains unchanged.

Evidence: `docs/experiments/evidence/silver_action_pruning_retention_2026-08-28.json`
(SHA-256 `838f7c23fe985c00d8b609a87f1858a6f231ac7f3245e29da4e8bc077baac0e6`)
and `docs/experiments/evidence/silver_action_pruning_progressive_current_2026-08-28.json`
(SHA-256 `1231530b9381009d36622fd32b2a496d5d18d5eb4a0958ba26abd07c8019e243`).
See [ledger-06 §188–190](../../../docs/experiments/ledger-06.md).

## Current baseline

Use [current-baselines.md](current-baselines.md) for the recommended executable
configuration and qualified benchmark numbers. Do not infer the current
baseline from a dated plan, session report, model filename, or ignored build
artifact.

## Parked lines

- Silver reuse-cap scaling (PR #59, frozen source SHA
  `36065aefbc49063d16000a9549cad5c1346bbcc6`): a paired 32-seed GCP experiment
  causally confirmed the 32k retained-allocation sticky-cap mechanism. At 3700
  simulations, switching only the cap metric from allocated nodes to active
  pool usage restored exact reroot from 53.54% to 66.87%; every one of 1,852
  sticky-eligible active cases exact-rerooted and none failed the allocated cap.
  It did **not** establish agent value: active was 5.89% slower in the
  diagnostics-off paired runtime comparison (above the 5% limit), wins were
  20/32 versus allocated 21/32, and floor was directionally lower. Allocated
  remains the production default. Do not run an active-mode 64-seed promotion
  gate or optimize its runtime yet. The next narrow question is decision
  quality on cap-fallback states against a high-budget fresh-root reference. A
  default-off implementation now records deterministically sampled ordinary
  sticky states and isolated fresh 3,700/25,000/50,000-search comparisons; it
  awaits independent review before the specified 16-seed collection.
  See [the experiment evidence](../../experiments/evidence/silver_reuse_cap_scaling_2026-08-26.json)
  and [ledger-06](../../experiments/ledger-06.md).
- Infinite-combo-aware search steering: investigation completed, but no active
  implementation or gate is scheduled.
- Self-play strategic relabeling: the 2026-08-07 handoff predates later
  controller, model, and encounter-marginalization work. It requires a new
  pre-registered contract before execution.
- Rollout leaf variants: prior K-rollout, one-turn bootstrap, policy-filtered,
  and related variants were null or negative. Reopen only with a new premise.
- Policy-head search distillation: the old Phase F handoff is not current
  execution guidance and must be revalidated against current labels and code.
- Searcher3 real-observation belief filtering
  ([decision log](../decision-log/2026-08-10-s3-real-belief-filter.md),
  [ledger-01.md](../../../docs/experiments/ledger-01.md)): the
  exact-transition posterior filter (`STS_S3_REAL_BELIEF_FILTER`) is
  implemented opt-in. The 32-seed diagnostic shows compatible fraction 72%
  (was ~10%), affordable CPU, and semantic correctness, but collapse is
  ~14%. A confirmation gate is the next justified step; rejuvenation is
  parked behind it. No gameplay default changed.
  A 2026-08-15 lifecycle diagnostic found that useful filters are usually
  discarded before the next search. A paired collapse-fallback correction showed
  the prior 79.1% temporary-transfer collapse was primarily stale pre-transition
  particle restoration: post-state fresh recovery reduced collapse to 19.7%.
  Transfer remains experimental and absent from the executable; only telemetry
  remains pending a separate action/quality experiment. A new opt-in live causal
  rejuvenation implementation is now present on the experiment branch. Its
  completed 32-seed gate on seeds 910000–910031 was **mixed/inconclusive**:
  `STS_S3_AI_REJUV_LIVE=off|placebo|ai` defaults to `off`; live runs
  require persistent filtered belief and use one first eligible attempt per
  combat, with `STS_S3_REJUV_TRIGGER` and `STS_S3_REJUV_PROPOSALS` supplied
  explicitly. Treatment children are particle-lineage anchored, replay the
  complete history, replace only AI_RNG, and inherit the source lineage ID.
  Collapse-fresh invalidates battle-start ancestry for the remainder of combat.
  AI−PLACEBO was +3/32 wins and +1.25 mean floor, but the exact paired-win
  McNemar p-value was 0.5078125 and the bootstrap floor CI included zero.
  Both live arms were below OFF in aggregate; exposure was 32/32 seeds for
  both. The raw-data audit is
  `build/s3live32_causal_gate_910000_910031/s3live32_causal_gate_audit.md`.
  The result does not establish H1 or the proposed novelty-versus-duplication
  mechanism, and no 64-seed extension is currently authorized.
- Single-child follow-up on fresh seeds 920000–920015: OFF won 10/16 with mean
  floor 47.3125, PLACEBO1 won 8/16 with mean floor 47.8125, and AI1 won 11/16
  with mean floor 45.25. AI1−PLACEBO1 was +3 wins but −2.5625 floor; AI1−OFF
  was +1 win but −2.0625 floor. Both live arms exposed all 16 seeds, injected
  at most one child per combat, and had zero telemetry integrity failures.
  This is mixed mechanism evidence, directionally promising on wins but with a
  possible depth/downside cost; no promotion or automatic extension is
  authorized. See [ledger-06 single-child follow-up](../../../docs/experiments/ledger-06.md).
- Fresh 64-seed confirmation on `920016–920079` retained the direction: OFF
  40/64 (mean floor 45.3281), PLACEBO1 38/64 (45.5625), AI1 41/64 (45.4688).
  AI1−PLACEBO1 was +3 wins, discordance 4–1, floor delta −0.0938 with bootstrap
  CI [−1.4531,+1.1094]; AI1−OFF was +1 win, discordance 4–3, floor delta
  +0.1406 with CI [−1.3281,+1.4688]. Both live arms exposed 64/64 seeds,
  maximum one child/combat, and zero telemetry integrity failures. Two severe
  AI1 floor regressions (−17 and −28 floors) occurred against both comparators;
  classify as promising win-rate direction with a possible downside tail, not
  clean promotion evidence. No automatic extension beyond 64 seeds.
- Searcher3 particle-count default
  ([decision log](../decision-log/2026-08-10-s3-particle-count-sweep.md),
  [ledger-01.md](../../../docs/experiments/ledger-01.md)): 128 particles
  is directionally promising (monotonic collapse reduction, positive win
  direction) but not confirmed for promotion. 64 particles remains the
  gameplay default; a confirmation gate on a full seed block is the next
  justified step.

## Closed lines

- Silver 25k parent-Q action scoring is closed after the preregistered offline
  gate rejected it (`POLICY_MODEL_OFFLINE_REJECTED`, ledger §186). The model
  improved exact-order top-action agreement but achieved only +2.497pp
  pairwise concordance with 82.2% bootstrap probability positive and 65.58%
  probability of lower mean regret, missing the registered bars. An explicitly
  authorized exploratory online override also rejected every method
  (`ONLINE_POLICY_METHODS_REJECTED`, ledger §187): A/B/C/D won 20/20/17/15 of
  32 and every learned arm cost at least 1.372x baseline CPU. The rejected
  runtime mechanisms and compact model were removed; the reusable offline
  pipeline and durable evidence remain. Do not restart learned ordering or
  PUCT from this artifact.
- Raw deep-search utility as the combat leaf target, repeated DAgger, residual
  correction, and the sampled terminal-endHP relabeling did not improve the
  recorded online gate (`EXPERIMENTS.md` §166).
- The initial DeepSets combat VNet failed under MCTS distribution shift
  (`EXPERIMENTS.md` §157-§158).
- Completed and superseded plans, handoffs, and intermediate reports are under
  `docs/archive/research/`. They are historical evidence, never current
  instructions.

## Invariants and assumptions

- Code and executable behavior remain authoritative.
- Policy-quality claims require paired common seeds and an explicitly labelled
  fair or known-RNG regime.
- Agent-run seed counts remain subject to `tools/seed_guard.sh`.
- An artifact path in a historical report does not prove that artifact still
  exists or loaded successfully.

## Relevant code

- `apps/one_combat.cpp::strategicMargGen`
- `apps/one_combat.cpp::stepFrozenV4Ooc`
- `tools/convert_marg_to_trainer.py`
- `train_strategic_tok.py`
- `export_strategic_tok.py`

## Known limitations

- The active M0/M1 direction is supported by a small, underpowered matched
  gate; it is not a promotion claim.
- Historical reports sometimes omit hashes, exact seed ranges, or complete
  environment provenance. Those omissions must not be filled by inference.

## Open questions

- Does scaled encounter-marginalized supervision improve M1 relative to a
  matched M0 control?
- If so, does the matched winner become competitive with deployed V4?
