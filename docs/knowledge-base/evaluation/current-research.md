# Current research status

Last verified: 2026-09-10 at `9b6502b53b72c3239de1f39d08ccde56a3ff2557`.
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
not qualify the treatment; the default remains A. See [ledger-06 §§223–224](../../experiments/ledger-06.md),
the [synthetic raw matrix](../../experiments/evidence/silver_chance_frequency_2026-09-11.csv),
and the [paired gameplay rows](../../experiments/evidence/silver_chance_gameplay_screen_2026-09-11.csv).

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
