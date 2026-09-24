# `v_win` terminal-pricing audit

## Decision

**`VWIN_W1_NEEDS_SMOOTHING`** under the frozen handoff thresholds. HP slope and
held-potion value are positive with seed-bootstrap intervals above zero in all
three acts. The median longest low-HP flat run is 5 HP, within the 10-HP limit.
Only 63.8% of RAW rows satisfy the monotonicity rule, below the required 95%.
This is an input-readiness result for a future W1 lookup table; it is not a
gameplay-quality result or permission to promote a runtime change.

The preregistered thresholds are unchanged. The only pre-analysis amendment
was to Q4: the first 93 row-bearing seeds showed potion capacities 3 and 5, so
the descriptive regression includes `potionCount` and slot slack together and
reports the actual design rank. The amendment was committed as
`ca6960ad` before the main-population Q1–Q5 calculations.

## Frozen setup and collection

- **Collection executable/source SHA:**
  `5334920f5dc184ba9507ce9a15ed2fd96fd69bec` (Silver-only refreshed baseline).
- **Model:** `models/v_win_trees.txt`, SHA-256
  `fc52c14cb7239a33b3c1f9d0477ccb6c895fd51a07240fe804744e605067ad70`;
  448 model features, 1,060 trees, logistic output, base score 0.33217296.
- **Population:** project-fair E2c-v2, ascension 0, seed range
  `3100000..3100127`, `e2cgen` simulation argument 1,000, adaptive Silver
  enabled, allocated reuse cap 32,768.
- **Policy-prior deviation:** Silver telemetry reported
  `prior_model_loaded=0`; the policy prior was not loaded for this cohort.
- **Collection interruption:** the initial process stopped after its CSV
  represented 93 seeds (`3100000..3100092`). The resulting CSV is retained and
  its bytes/hash/rows are recorded below, but the interrupted process did not
  leave a seed-guard provenance sidecar or final aggregate invalid/quarantine
  and simulator-health counters. Those counters are unknown for that segment.
  The remaining 35 seeds were collected separately and have a complete
  sidecar: 35/35 completed, zero invalid/quarantined seeds or branches, zero
  simulator-health hard failures, and 1,548 rows.

The two files were combined without altering their rows. They contain 5,775
data rows (3,069 RAW and 2,706 POST), 128 unique consecutive seeds, and 2,706
matched `(seed, fight_index)` pairs. There are 363 unmatched RAW rows and no
unmatched POST rows. There are no duplicate keys, paired outcome/room/encounter
mismatches, or within-seed label inconsistencies. The outcome count is 92 wins
and 36 losses. The unmatched RAW rows were retained and were not treated as
quarantines.

Exact segment commands, hashes, sidecar values, integrity checks, and the
missing interrupted-segment counters are in
[`collection_provenance.json`](collection_provenance.json). The raw E2c CSVs
remain local under ignored `build/vwin_pricing/`; they are not committed.

The required two-seed current-baseline smoke passed before the cohort: 2/2
completed, 92 E2c rows (48 RAW, 44 POST, 44 matched pairs), zero invalid or
quarantined seeds/branches, and zero simulator-health hard failures. A stale
`c0937d8a` diagnostic that produced zero rows is retained separately and was
not included in the population. Smoke data were not used for Q1–Q5.

## Parity and deterministic analysis

Before Q1–Q5, 600 RAW records were projected with the full 1,017-column
canonical rich-state block and the 448 model features aligned by feature name.
Native `winnettest` and Python predictions agreed on all 600 rows: maximum and
mean absolute probability difference were both 0.000000, below the frozen
`1e-4` tolerance. See [`parity_summary.txt`](parity_summary.txt).

Every confidence interval below uses a 2,000-replicate percentile bootstrap
over source seeds with RNG seed `20260924`. Two complete runs of the audit
script produced byte-identical JSON results (SHA-256
`c8dc74656f9671c8ac1b1ee4b9880e67e6e53684e1bf5049d519acb7853195f4`).
Machine-readable results and tables are retained in this directory.

## Q1 — local terminal prices

The model's HP curve is monotone for 63.77% of RAW rows (95% CI
60.18–67.35%); the required share is at least 95%. The overall median longest
flat run is 5 HP (bootstrap CI 5–5), within the 10-HP limit. Per-act summaries
follow; intervals are seed-clustered 95% CIs.

| Act | RAW rows | Monotone share | Median flat run | Mean HP slope, probability/HP | Held-potion value, HP-equivalent | Gold, HP-equivalent/gold | +1 max HP, HP-equivalent |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 1,232 | 65.9% [61.4, 70.4] | 5 [5, 5] | 0.000933 [0.000837, 0.001025] | 6.76 [4.99, 8.85] | 0.357 [0.303, 0.418] | 1.55 [0.03, 3.52] |
| 2 | 1,005 | 62.1% [55.9, 67.7] | 4 [4, 5] | 0.002670 [0.002412, 0.002936] | 6.74 [4.65, 9.22] | 0.090 [0.069, 0.114] | 1.00 [-1.08, 2.20] |
| 3 | 832 | 62.6% [56.6, 68.6] | 4 [4, 4] | 0.002586 [0.002198, 0.002987] | 6.70 [3.52, 12.58] | 0.058 [0.014, 0.117] | 0.30 [-3.13, 2.39] |

Silver reference prices were 11 probability points per potion, 0.25
probability points per gold, and 2 probability points per max-HP unit. The
positive HP-slope and held-potion criteria pass in every act. The max-HP probe
is descriptive and is not one of those sign gates.

## Q2 — intervention review and relic counters

The reviewed repository interventions do not identify a causal derivative of
the tracked terminal classifier with respect to HP. `train_winrate.py` includes
a synthetic +30%-of-maxHP feature-space probe; it measures the model response,
not an outcome effect. Paired `rest_cf` changes HP and progression together,
`pathcfgen` changes route and downstream rewards, and TERM_WIN's terminal
bonus changes the search policy (historical run: null win-rate result and about
3.1x cost at its recorded setup). None holds the rest of a captured state fixed
while applying an HP offset and matched continuation. The bounded proposed
follow-up is 8 states × 3 offsets (`-10, 0, +10`) × 4 common continuation seeds
= 96 trajectories. Its rough 60.8 CPU-minute estimate uses an existing
38-CPU-second/run reference; replay cost is unmeasured. It was not run.

This audit also corrects an interpretation attached to historical ledger
§§109–110. The **current tracked 1,060-tree artifact** has splits above the
presence threshold on several counter features. `run_features.cpp` encodes a
present relic as `1 + counter`; thresholds above 1 therefore distinguish
counter values. Current counts of such splits are: Happy Flower (`r26`) 8,
Incense Burner (`r30`) 26, Ink Bottle (`r31`) 39, Nunchaku (`r44`) 60, Omamori
(`r46`) 100, Pen Nib (`r52`) 27, and Sundial (`r68`) 11. Inserter (`r32`) is
not a model feature. Lizard Tail (`r35`), Neow's Lament (`r116`), and Thread
and Needle (`r131`) have presence-only splits in this artifact. In the current
enum, `r116` is Neow's Lament and `r131` is Thread and Needle; the old ledger
labels `r131` as Neow's Lament. The full threshold table is
[`q2_counter_relic_splits.csv`](q2_counter_relic_splits.csv).

The model file matches the original exported `build/v_win_trees.txt` blob
introduced by `746e50fc`, but the exact artifact used by the historical
§109–110 run is not bound in that entry. This audit therefore corrects the
claim about the currently tracked artifact and enum mapping; it does not
rewrite the historical run's measured result. See
[`q2_model_history.txt`](q2_model_history.txt).

## Q3 — calibration and provenance

Mean predicted P(win) over RAW rows was 0.545 (95% CI 0.517–0.571), compared
with an equal-seed observed run win rate of 0.719 (0.641–0.797) and observed
row win rate of 0.752 (0.676–0.822). RAW-row Brier score was 0.232 (0.213–
0.254), above the row-prevalence baseline 0.187. This cohort indicates
underprediction against its observed win rate, but 128 run seeds give weak
calibration power and rows within a seed are correlated.

The repository ledger describes a historical `vrich` training corpus, but
that data file is absent locally and no saved training manifest ties the
historical rows/configuration to this exact model hash. Treat that lineage as
incomplete rather than asserting exact training provenance.

## Q4 — RAW-to-POST effects

There are 2,706 matched pairs. Mean `Pwin(POST)-Pwin(RAW)` was 0.00229
(0.00177–0.00284) for monsters, 0.02149 (0.01818–0.02492) for elites, and
0.04077 (0.03590–0.04590) for bosses.

The preregistered regression has rank 5/5 and `R²=0.04776`, just below 0.05.
The frozen Q4 gate therefore passes via its `R² < 0.05` branch. The maximum
absolute HP-equivalent endpoint bound across each coefficient's observed
range is above 3 HP for `curHp` (26.65), `potionCount` (8.81), potion-slot
slack (11.66), and `gold` (15.54); the `potionCount` and slack intervals also
include zero. Coefficients are descriptive for the observed capacity mix
(3 and 5), not causal effects.

Using Q1's per-row held-potion HP-equivalent, rows with a full inventory had
mean 0.61 HP-equivalent (0.21–1.11; 711 rows); rows with at least one free
slot had mean 9.56 (7.39–12.44; 1,545 rows). The common-seed paired
available-minus-full contrast was 9.34 HP-equivalent (6.71–12.99; 102 seeds).
This is descriptive and can reflect which runs/states occupy each stratum.

## Q5 — hidden-future sensitivity

The specified E2c T-fair fallback zeroed the eight `HIDDEN_FUTURE` fields and
retained `bossId`, which the current classifier treats as observable/trackable.
Per-row Spearman agreement between recorded and zeroed-feature HP slopes was
0.934 (`n=3,069`); potion HP-equivalent agreement was 0.873 (`n=2,122`). Both
pass the frozen 0.8 correlation threshold. Zeroing is not the historical
resampling substitute and may place the inputs out of distribution; this is a
sensitivity check, not an alternate production price table.

## Q6 — within-combat inputs and prediction cost

Code inspection identified model inputs that can change between the combat
entry state and a victorious exit: `curHp`, `maxHp` (Feed), `gold` (Hand of
Greed), potion count/held potion IDs, Parasite/deck-size fields from Writhing
Mass, and the tracked exit-mutated relic features listed in `results.json`.
Potion capacity varied between runs (3 and 5) but is copied into the combat
context and is not changed by exit transfer, so it is not a within-combat
input. The Release direct native prediction benchmark made 20,000 calls:
median 21.761 μs, p95 31.249 μs. This is a predictor microbenchmark, not
end-to-end combat latency.

## Scope, deviations, and checks

- No W1 table, runtime integration, default change, gameplay claim, or Q2
  continuation experiment is included.
- The tracked prior was not loaded during collection; the first segment's
  final health/quarantine counters were lost at interruption. These
  limitations do not alter the measured 128-seed rows, but limit claims about
  exact collection completeness and preregistration adherence.
- The local raw E2c CSVs are not committed. This packet preserves result JSON,
  aggregate tables, segment provenance/schema for the completed remainder,
  integrity accounting, parity outcome, smoke summaries, and native latency.
- The deterministic analysis self-test passed. Native/Python parity passed
  on 600 rows with max difference 0.000000. Broader repository verification
  and authoritative GitHub Actions CI are recorded in the pull request once
  the final review SHA is frozen.

## Evidence files

- [`results.json`](results.json) — complete machine-readable Q1–Q6 results,
  verdict checks, intervention review, counter splits, and source-group list.
- [`q1_strata.csv`](q1_strata.csv), [`q1_potions.csv`](q1_potions.csv), and
  [`q1_split_counts.csv`](q1_split_counts.csv) — Q1 strata, prices, and model
  split counts.
- [`q2_counter_relic_splits.csv`](q2_counter_relic_splits.csv) and
  [`q2_model_history.txt`](q2_model_history.txt) — current counter thresholds
  and artifact/enum audit.
- [`q4_regression.csv`](q4_regression.csv) — regression estimates and
  seed-bootstrap confidence limits.
- [`collection_provenance.json`](collection_provenance.json) — commands,
  hashes, row/key integrity, exact interrupted-segment limitation, and
  reproducibility hash.
- [`remainder_35_provenance.json`](remainder_35_provenance.json) and
  [`remainder_35_schema.json`](remainder_35_schema.json) — wrapper-generated
  metadata for the completed final 35 seeds.
- [`parity_summary.txt`](parity_summary.txt),
  [`native_latency_20000.json`](native_latency_20000.json), and the four
  smoke diagnostic files — parity, cost, and pre-collection gate evidence.
