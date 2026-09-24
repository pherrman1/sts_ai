# `v_win` terminal-pricing audit

## Preregistration and status

This first commit freezes the analysis plan and the handoff's proposed
decision thresholds before any Q1–Q5 metric is computed on a main population.
The Silver E2c smoke was run as the required collection gate; its outcome and
the resulting stop condition are recorded in the follow-up results commit.
No main cohort or fallback dataset is currently available to analyze.

**Question.** Is the tracked `models/v_win_trees.txt` a usable source of
relative prices among combat-terminal victories, measured in HP-equivalent
units, for a future W1 lookup table? This audit makes no gameplay or runtime
promotion claim.

**Current baseline.** `origin/main` at `7a181b3fa296fda4122033b70767fc2c0f03618c`
(2026-09-24). The model SHA-256 is
`fc52c14cb7239a33b3c1f9d0477ccb6c895fd51a07240fe804744e605067ad70`.
The accepted handoff named older baseline `bb2379e8`; the first local
preflight used `c0937d8a`. Before main-population analysis, the shared
`origin/main` advanced to `7a181b3f`, and its removal of Searcher2 materially
changed `apps/one_combat/run_driver.cpp`: current Silver now enters the common
E2c start/exit capture path. The model, feature producer, and E2c capture
implementation are unchanged. This baseline refresh is frozen in a second
pre-analysis commit. The earlier 2-seed smoke on `c0937d8a` wrote zero rows
because of the old branch; it is retained as a baseline-refresh diagnostic,
not part of the current Silver population. The current-baseline smoke must
pass before the main cohort is launched.

**Primary population.** Fresh project-fair Silver E2c-v2 RAW/POST states,
ascending from seed offset `3100000`, with up to 128 seeds, ascension 0, an
adaptive 500–10,000 Silver budget, reuse cap 32,768 (`allocated`), native OOC
trees, and the tracked policy prior wherever `e2cgen` supports those settings.
Run a 2-seed smoke with the same settings first. The main cohort is admissible
only if the smoke proves Silver was active, has nonzero RAW/POST pairs, and has
zero quarantines and simulator health failures. Do not inspect Q1–Q5 metrics
on smoke data.

**Population and analysis rules.** On at least 500 RAW rows, align model
features by name and pass the Python/native parity gate at max absolute error
`1e-4` before analysis. Use seed-clustered percentile bootstrap intervals
(2,000 replicates, fixed RNG seed `20260924`) for every reported uncertainty
interval. Compute Q1 HP sweeps, potion removals, ±25-gold probes, +1
maxHP/+1 curHP probes, act/HP-band/room strata, and tree split counts using
the compact-tree model exactly as serialized. Preserve canonical derived
features when perturbing `curHp`, `maxHp`, potion counts, or gold.

For Q4, pair RAW and POST by `(seed, fight_index)`, then fit `DeltaV` against
RAW `curHp`, `potionCount`, potion-slot slack, and `gold`. Report any
rank-deficient terms explicitly; at ascension 0, fixed `potionCapacity` makes
`potionCount` and slack exact complements, so only their joint observed-range
effect is identifiable. Compare potion value between slack 0 and slack ≥1.

For Q5, use the existing E2c T-fair classification in
`tools/analyze_postcombat_raw_terminal.py`: zero the eight
`HIDDEN_FUTURE` fields when an offline resampling equivalent is unavailable,
and label that regime out-of-distribution. Keep `bossId` because that
classifier marks it observable/trackable. Report per-row Spearman agreement
for local HP slope and potion HP-equivalent, plus act-level exchange rates.

For Q2, review existing interventional evidence only and propose a smallest
follow-up; do not run it. For Q3, document training provenance and estimate
calibration-in-the-large plus Brier score on the primary RAW population, with
seed-clustered intervals and an explicit warning about weak power at 128 runs.
For Q6, identify within-combat-varying model inputs from the exit/update code
and measure Release native `WinNet::predict` median latency over at least
10,000 calls. No runtime integration is in scope.

## Frozen decision thresholds

These thresholds are copied unchanged from the accepted handoff:

- **`VWIN_W1_READY`** requires at least 95% of RAW rows to have no HP-sweep
  step drop greater than 0.005; median longest flat HP run through
  `ceil(0.6 * maxHp)` no greater than 10 HP; positive mean HP slope and potion
  value in every act with seed-bootstrap 95% intervals excluding zero; Q4
  `R² < 0.05` or no coefficient interval implying more than a 3-HP-equivalent
  shift across the observed range; and Q5 per-row HP-slope Spearman correlation
  at least 0.8.
- **`VWIN_W1_NEEDS_SMOOTHING`** applies when all signs are correct in every act
  but the monotonicity or resolution criterion fails.
- **`VWIN_W1_NOT_READY`** applies when any act has zero or wrong-sign HP or
  potion value, or Q4/Q5 fail materially.

Q2, Q3, and Q6 constrain interpretation and cost but do not gate the verdict.
No threshold has been changed. The three scientific verdicts apply only after
the collection and parity gates pass; a failed collection gate is reported as
blocked, not converted into a scientific verdict.
