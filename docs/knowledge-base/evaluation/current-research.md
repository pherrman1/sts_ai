# Current research status

Last verified: 2026-08-29 against the current working tree.

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
The rejected runtime root-action modes and their replay executable were removed
from the merge package on 2026-08-29; the tie-safe offline analyzers, tests,
durable reports, input hashes, and ledger evidence remain available for future
independent hypotheses.

Evidence: `docs/experiments/evidence/silver_action_pruning_retention_2026-08-28.json`
(SHA-256 `838f7c23fe985c00d8b609a87f1858a6f231ac7f3245e29da4e8bc077baac0e6`)
and `docs/experiments/evidence/silver_action_pruning_progressive_current_2026-08-28.json`
(SHA-256 `1231530b9381009d36622fd32b2a496d5d18d5eb4a0958ba26abd07c8019e243`).
See [ledger-06 §188–191](../../../docs/experiments/ledger-06.md).

### Silver root-only exploration control

The preregistered control for the pruning result was implemented on the fresh
`exp/silver-root-exploration-sweep` branch from baseline
`034830df6510f1ab37ad4f053c07333fca0970c7`. It changes only deterministic UCT
selection at the current root through the default-off
`STS_SILVER_ROOT_EXPLORATION` setting; internal deterministic c, chance c,
widening, reuse, final action selection, and legal root-edge storage remain
unchanged. The four declared candidates were 25.0 (unset control), 18.5,
12.5, and 9.9. The retained 93-anchor wires were replayed at 64/128/256/1000
simulations, with 63 multi-action anchors as primary and all 93 as secondary.

The 25k-A selection rule rejected every lower-root candidate: each candidate
introduced a new >=3-regret selection at both 128 and 256 simulations. The
CPU ratios were within the 1.05 limit, but that does not waive the catastrophe
criterion. Therefore the independent 25k-B offline gate was not run, no
candidate was frozen, and the preregistered result is
`ROOT_EXPLORATION_REDUCTION_REJECTED`. No gameplay cohort was authorized, and
the prior Sequential-Halving rejection is unchanged; the historical 931000–
931063 smoke is not confirmation evidence.

Evidence: [root-only exploration sweep report](../../../docs/experiments/evidence/silver-root-exploration-sweep-2026-08-29.json).
The ignored raw replay files and their hashes are recorded in that report.

At the user's direction, an exploratory online follow-up was subsequently run
on GCP rather than treating the offline rejection as evidence about gameplay.
A broad fresh 8-seed-per-arm screen over c={0, 5, 9.9, 12.5, 18.5, 25, 35,
50} selected a narrow online screen around the only promising lower-c region.
The fresh 32-seed-per-arm narrow block 932100–932131 produced point win
deltas of -6.2pp (c=12.5), -6.2pp (c=15), +6.2pp (c=18.5), and +6.2pp
(c=21) against unset c=25; every paired 95% win interval included zero.
All complete arms passed the recorded operational integrity checks, but this
is **ROOT_EXPLORATION_GAMEPLAY_INCONCLUSIVE**, not a promotion or a reversal
of the offline `ROOT_EXPLORATION_REDUCTION_REJECTED` decision. The default
remains ordinary c=25, and Sequential Halving/root pruning remains unrestored.
See the [online GCP evidence packet](../../../docs/experiments/evidence/silver-root-exploration-online-gcp-2026-08-29.json)
and [ledger-06 §194](../../../docs/experiments/ledger-06.md).

The broad screen's c=35 arm was then rerun at the user's direction using all
24 GCP cores rather than one core. On fresh paired seeds 932401-932528,
c=35 scored 84/128 wins versus 79/128 for unset c=25: +3.9pp paired win
delta (95% CI [-3.9,+11.7]) and +0.9 paired floor delta ([-0.5,+2.3]), at
1.056x runtime. Both arms passed exact seed, budget, Silver telemetry, and
zero-failure checks. This remains
`ROOT_EXPLORATION_GAMEPLAY_INCONCLUSIVE`; the default remains c=25 and no
Sequential Halving machinery is restored. See the [24-thread c=35 evidence
packet](../../../docs/experiments/evidence/silver-root-exploration-c35-128-gcp-2026-08-29.json)
and ledger-06 section 195.

A subsequent fully online Sequential-Halving tuner varied four root reduction
shapes, three round-allocation schedules, and exact budgets 1000/3000/6000.
The 16-seed broad screen promoted three schedules to a fresh 64-seed narrow
screen. Its frozen gate selected half/finalist-heavy at budget 3000, but the
fresh 128-seed confirmation aborted after 78 rows on a Silver live-backend
hidden-information conversion error. Partial analysis was prohibited, so this
line is **SEQUENTIAL_HALVING_ONLINE_TUNING_REJECTED** for promotion. The same
confirmation's valid c=35 arm scored 90/128 versus c=25's 84/128 (+4.7pp,
95% CI [-3.9,+13.3]), floor +0.5 ([-0.8,+1.7]), at 0.975x runtime. It remains
`ROOT_EXPLORATION_GAMEPLAY_INCONCLUSIVE`: it missed the frozen +5pp bar and
the interval includes zero. Do not combine c=35 with this halving path:
Sequential Halving forces root pulls and does not consult root UCT c while
active, so that label would be behaviorally inert rather than an interaction
test. The earlier pruning and offline Sequential-Halving rejections remain
unchanged. See the [online tuning evidence packet](../../../docs/experiments/evidence/silver-sh-online-tuning-2026-08-30.json)
and ledger-06 section 196.

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
