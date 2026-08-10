# OOC Strategic Model — Investigation and Experiment Handoff

Date: 2026-08-09
Status: **ARCHIVED**. Superseded by completed experiments and
`docs/knowledge-base/evaluation/current-research.md`.

## Objective

Improve the honest Slay the Spire out-of-combat strategic model while keeping
strict player-observable information. First characterize the corrected honest
V4 token model on the current combat stack; do not redesign supervision until
its deployment behavior is understood.

## Established correctness facts

The following eight features are forbidden in honest strategic models and
labels:

- `nextEliteId`, `nextFight0`, `nextFight1`, `nextFight2`
- `remElites`, `remFights`, `monOffset`, `eliteOffset`

`bossId` is legitimate and player-visible. The former V4 trainer bug built
some global slots from the wrong CSV columns while C++ inference used the
intended layout. The corrected honest V4 model is therefore a meaningful new
baseline. Its reported S2 fair 64-seed result was 39.1% vs 23.4% baseline,
+15.6pp (approximate CI [+3.1,+28.1]). Offline CE/top-1/Q metrics did not
explain this result and must not be treated as validated gameplay proxies.

Strategic datagen probes must detach `GameContext::map` before candidate
execution because map regeneration mutates shared `Map` objects. Audit every
remaining shallow-copy probe, especially `regretGateChoose`.

## Frozen benchmark contracts

Every experiment must explicitly record:

- git SHA and model SHA256/path;
- dataset/datagen version;
- combat VNet hash/path;
- Searcher version and Searcher3 particle/belief/chain/live-valid settings;
- combat sims, ascension, seed range, thread count;
- `STS_COLLECT_KEYS=0/1` and victory meaning;
- `STS_STOP_AFTER_ACT`;
- enabled OOC screens and margin/gate mode;
- VNet alpha and other relevant flags.

`STS_COLLECT_KEYS=0` is the Act-3 objective. `STS_COLLECT_KEYS=1` is the
Heart objective. Never mix those results. Historical pre-key results are
Act-3-objective results. Freeze the current 7k combat VNet for the immediate
OOC investigation; do not simultaneously swap combat architecture or model.

## Wave 0A — OOC correctness and feature contract

Create a permanent Python↔C++ feature-contract/parity test using several real
strategic decision rows. Compare before neural inference:

- all 42 honest V4 globals, including derived values;
- counted deck token IDs/upgrades/counts;
- relic tokens;
- potion tokens;
- candidate/action representation and derived features.

The native check must fail on mismatch, not merely print a diagnostic. Python
training/export and C++ inference must use identical semantics. Audit and fix
all shallow-copy counterfactual probes, especially regret-gate action matching.

## Wave 0B — seed-disjoint validation

Both `train_strategic.py` and `train_strategic_tok.py` must:

1. collect unique seeds;
2. deterministically shuffle them;
3. assign complete seeds to train or validation;
4. assert train/validation seed intersection is empty;
5. compute normalization using train seeds only;
6. retain `(seed,decIdx)` as the decision-group batching unit;
7. print train seeds, validation seeds, train/validation decisions and rows;
8. invalidate/rebuild any affected caches.

Prefer a permanent frozen test-seed set never used for training, checkpoint
selection, threshold tuning, or architecture selection.

## Wave 0C — benchmark provenance

Every OOC benchmark needs a machine-readable configuration record containing
at least the fields above. A `bestbench` results file should have a provenance
sidecar recording objective, argv, seed block, key objective, searcher/S3
settings, OOC flags, model paths/load status, and timestamp. The human BEST
banner is not complete provenance.

## Wave 0D — deployment-aligned offline metrics

Implement shared metrics, usable by both strategic trainers and a standalone
analyzer on existing checkpoint/dataset pairs. The actual C++ gate rule must be
reproduced exactly. Report globally and by screen:

1. **Gate-fire curves:** thresholds 0, 0.25, 0.5, 1, 2, 5; opportunities,
fires, and fire rate.
2. **Override quality:** label agreement and beneficial/harmful/neutral
override rates for decisions the model actually overrides.
3. **Fallback-relative advantage:**
`A_label = labelQ(model choice) - labelQ(fallback choice)` and
`A_pred = Q_pred(model choice) - Q_pred(fallback choice)`; report distributions,
sign accuracy, rank correlation, margin bins, and harmful probability by
confidence.
4. **Regret:**
`labelQ(best)-labelQ(model choice)` and `labelQ(best)-labelQ(fallback)`;
report all rows, fired rows, and per screen.

Do not select models only by policy top-1, policy CE, Q top-1, Q error, or
value error.

## Wave 0E — corrected V4 on current stack

Freeze corrected honest V4, current 7k VNet, current S3 settings, combat
budget, and identical paired seeds. Run V4 gates OFF vs ON separately for:

- Act-3 objective: `STS_COLLECT_KEYS=0`;
- Heart objective, if relevant: `STS_COLLECT_KEYS=1`.

Start with 64 paired seeds. If positive or ambiguous, confirm with at most 128
routine automated seeds. Report paired delta and confidence interval. Do not
run 256/1000 automatically.

## Wave 0F — override tracing

For every V4 opportunity record seed, floor, act, screen, candidate set,
fallback action, NN action, predicted Q values, best/second margin,
NN-vs-fallback margin, threshold, gate-fired status, and final run outcome.
The trace must include explicit `STS_COLLECT_KEYS` and `STS_STOP_AFTER_ACT`.

## Wave 0G — per-screen causal ablations

First inspect override frequencies and prioritize screens with most overrides.
Use simple controlled ablations, not combinatorial subsets:

- full corrected V4;
- full minus CARD REWARD;
- full minus EVENT;
- full minus REST;
- full minus SHOP;
- full minus TREASURE;
- full minus BOSS RELIC;
- MAP where applicable.

Use 64 paired seeds per useful screen test and confirm interesting results to
128. Goal: identify whether one or two screens explain the S2→S3 interaction.

## Wave 0H — margin sweep

After screen behavior is understood, test only margins 0.5, 1.0, 2.0, 5.0.
Measure fire count, harmful override rate, and paired gameplay outcome. The
purpose is to characterize conservative high-confidence overrides, not run a
large hyperparameter search.

## Wave 0I — checkpoint selection

Compare identical training recipes using at minimum best `val_pol_ce` versus
best `q_top1`. Optionally test a deployment-aligned metric if it tracks online
behavior. Use a 64-seed screen first and no more than 128 for confirmation.

## Wave 1 — fallback-relative advantage labels

Only after Wave 0. Train targets:

`A(o,a) = U(force a) - U(force fallback)`

using paired/common-random-number futures for candidate and fallback. Deploy
fallback unless predicted advantage is sufficiently positive.

## Wave 2 — hidden-future marginalization

Use a small diagnostic corpus of 100–200 diverse decisions and 16 hidden
realizations initially (32 only when uncertain). Keep public state fixed and
resample only unobservable information. Measure changes to action argmax,
candidate-vs-fallback sign, and action ranking before scaling.

## Wave 3 — prototype advantage model

Train a small model on fallback-relative advantage only if Wave 1/2 supports
it. Evaluate advantage sign accuracy, beneficial-override precision,
harmful-override rate, fired-only regret, and per-screen results. Policy CE is
not the main criterion.

## Wave 4 — screen-specific modeling

Only if Wave 0G shows heterogeneity: test shared encoder/separate screen heads
or separate small models for genuinely different decisions. SHOP is a special
sequential/combinatorial case. Require evidence before splitting.

## Wave 5 — candidate/deck interaction

Only after labels and screen behavior are controlled, test
`STRAT_TOK_CROSS=1`, especially for card rewards, shop cards, upgrades, and
removals. Do not use architecture to compensate for broken supervision or
evaluation.

## Wave 6 — ascension curriculum

After the base pipeline is trustworthy, compare existing A0 training with a
controlled mixed A0/A5/A10 dataset. Do not jump to A20-only. Measure coverage,
screen frequency, target variance, and performance across ascensions.

## Wave 7 — Heart-aware OOC strategy

If Heart completion is the true objective, eventually learn key acquisition
tradeoffs: sapphire key, burning elite, recall, and present-strength versus
Act-4 eligibility. Do this only after regular OOC is stable.

## Permanent rules

- Honest information only; never restore the eight hidden features.
- One causal variable per gate; do not simultaneously change OOC, combat,
  Searcher, target, margin, ascension, and horizon.
- Paired seeds; report paired deltas, not only independent percentages.
- 64 first, 128 maximum for routine automated confirmation.
- Explicit `STS_COLLECT_KEYS=0/1` for every benchmark.
- Log SHA256 artifacts, configs, commands, offline metrics, and gates.
- When offline/online behavior disagrees, audit feature order/semantics,
  normalization/cache invalidation, Python↔C++ parity, action encoding, and
  gate semantics before inventing an ML explanation.

## Current implementation status in this session

Implemented or present in the working tree:

- `strategic_split.py` and seed-disjoint trainer wiring;
- `strategic_tok_contract.py` and V4 contract self-test;
- map-detach fixes in OOC probes;
- `STS_OOC_STRATEGIC_TRACE` and `tools/analyze_strategic_trace.py`;
- benchmark provenance sidecar;
- `tools/vnet_distribution_shift.py` query-log analyzer;
- `tools/analyze_screen_ablation.py` and updated `run_screen_ablate.sh`;
- `strategic_metrics.py` and `tools/analyze_strategic_metrics.py` for
  deployment-aligned prediction CSVs without retraining.

Wave 0E was requalified after isolating per-fight `g_potionKeepValue` as
thread-local. The repaired frozen Act-3 S3+7k-VNet stack gives V4 ON 31/64
(48.4%) versus OFF 24/64 (37.5%), +10.9pp, CI [−1.6,+23.4]. Wave 0F tracing,
Wave 0G screen ablations, and Wave 0H margin tests are now complete at the
64-seed exploratory point; see `EXPERIMENTS.md` §§159–161. A 128-seed
confirmation remains appropriate because the 64-seed CI crosses zero.

Wave 0I checkpoint selection is implemented for both trainers, including the
CSV group-contiguity fix and `STRAT_SELECT_METRIC` switch. A short
`val_pol_ce` CUDA run completed, but the paired `q_top1` run was stopped before
training after the first run's ~2.9 GB state allocation; do not claim a
checkpoint-selection result yet. Avoid another full GPU run until resources are
explicitly available.

Focused self-tests, Python compilation, `bash -n`, `git diff --check`,
`one_combat` build, 2-seed sidecar smoke, 1-seed trace/analyzer smoke, and the
existing CTest suite must pass before the next experiment. Full 64/128-seed
Wave 0E/0G gameplay gates remain explicit experiments and must use the frozen
stack/objective above.
