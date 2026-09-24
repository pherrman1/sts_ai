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
After synchronization with current `origin/main`, `one_combat` was rebuilt in
Release and the same parity gate passed again on all 600 rows.

Every confidence interval below uses a 2,000-replicate percentile bootstrap
over source seeds with RNG seed `20260924`. Two complete runs of the audit
script produced byte-identical JSON results (SHA-256
`8803126fba6a73de07b99ab8a4b5a006f17fc79d5f18f7468bdf16c38194ba98`).
Machine-readable results and tables are retained in this directory.

## Q1 — local terminal prices

The model's HP curve is monotone for 63.77% of RAW rows (95% CI
60.18–67.35%); the required share is at least 95%. The overall median longest
flat run is 5 HP (bootstrap CI 5–5), within the 10-HP limit. Per-act summaries
follow; intervals are seed-clustered 95% CIs.

| Act | RAW rows | Monotone share | Median flat run | Zero HP-slope share | Mean HP slope, probability/HP | Held-potion value, HP-equivalent | Gold, HP-equivalent/gold | +1 max HP, HP-equivalent |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 1,232 | 65.9% [61.4, 70.4] | 5 [5, 5] | 0.81% [0.08, 1.85] | 0.000933 [0.000837, 0.001025] | 6.76 [4.99, 8.85] | 0.357 [0.303, 0.418] | 1.55 [0.03, 3.52] |
| 2 | 1,005 | 62.1% [55.9, 67.7] | 4 [4, 5] | 0.80% [0.20, 1.68] | 0.002670 [0.002412, 0.002936] | 6.74 [4.65, 9.22] | 0.090 [0.069, 0.114] | 1.00 [-1.08, 2.20] |
| 3 | 832 | 62.6% [56.6, 68.6] | 4 [4, 4] | 0.84% [0.00, 1.97] | 0.002586 [0.002198, 0.002987] | 6.70 [3.52, 12.58] | 0.058 [0.014, 0.117] | 0.30 [-3.13, 2.39] |

Silver reference prices were 11 probability points per potion, 0.25
probability points per gold, and 2 probability points per max-HP unit. The
positive HP-slope and held-potion criteria pass in every act. The max-HP probe
is descriptive and is not one of those sign gates.

The tracked compact model has 2,127 splits on curHp, 3,257 on maxHp, 2,210 on
gold, 271 on potionCount, and 153 on potionCapacity. The most-split potion
features are pot7 (18), pot26 (16), and pot29 (11). The compact export stores
split indices and thresholds but no gain values, so total gain is unavailable;
the complete split counts are in q1_split_counts.csv. Per-potion deltas,
HP-equivalents, and zero-value shares for ids with n >= 30 are in q1_potions.csv.

## Q2 — intervention review and relic counters

**Inference:** The reviewed repository interventions do not identify a causal
derivative of the tracked terminal classifier with respect to HP. The synthetic
trainer probe measures the model response, not an outcome effect. Paired
rest counterfactuals change HP and progression together, path branches change
route and downstream rewards, and TERM_WIN changes the search policy (its
historical win-rate screen was null at about 3.1x cost for the recorded setup).

**Open question:** No reviewed experiment holds the rest of a captured state
fixed while applying an HP offset and matched continuation. The bounded
proposed follow-up is 8 captured states × 3 offsets (-10, 0, +10) × 4 common
continuation seeds = 96 trajectories. Its rough 60.8 CPU-minute estimate uses
an existing 38-CPU-second/run reference; replay cost is unmeasured. It was not
run.

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

### Pre-collection artifact inventory (2026-09-24)

I checked the task worktree, the canonical checkout, and the existing Codex
worktrees for the named data paths before collecting the new cohort. The historical training/counterfactual CSVs and associated retained
data/model artifacts listed below were not present in those local locations.
The current tracked v_win model was present, as noted in the table. The ledger-referenced E2c GCP path is also
not mounted on this host; that does not establish whether the remote files
still exist. No remote job or data transfer was started.

| Candidate | Availability and recorded size | Verified generation/provenance | Use for this audit |
| --- | --- | --- | --- |
| Current models/v_win_trees.txt | Present locally; 3,224,915 bytes; SHA-256 fc52c14c…067ad70; 448 features, 1,060 trees. | The tracked bytes match the original exported build/v_win_trees.txt blob introduced by 746e50fc. train_winrate.py is the binary-logistic XGBoost trainer and defaults to build/vrich.csv, but the exact training manifest for this model hash is not recorded, and the agent generation tied to this model hash is unverified. | Used for this audit; exact training-data lineage remains unverified. |
| Ignored build/vrich.csv (E2) | Absent from checked local trees. Historical ledger records 1,444,372 rows, 67,655 seeds, and 1,009 columns; CSV byte size and source hash are not reproduced in the maintained ledger. Its referenced build/e2_postcombat_runwin/ hash bundle is also absent locally. No remote copy is identified in the ledger. | Verified from the ledger: generated by tools/run/datagen2_loop.sh on 2026-07-15, Ironclad A0, 10,000 simulations, epsilon 0.05; v_server.py V-marginal card continuation (softmax temperature 3 plus 5% uniform floor), heuristic map/shop/rest. Native datagen2 collection; XGBoost training recipe recorded separately. | Not available for reanalysis. The historical corpus configuration is not proof that it trained the currently tracked model. |
| E2c-v2 production output (da692d59…a89e2) | Absent from the task/canonical/managed worktrees. Historical ledger points to /home/philippherrmann/sts_sweep/build/e2c_raw_terminal_2000/; that path is absent on this host. Historical dataset accounting: 83,045 rows, 1,980 represented seeds; artifact byte sizes were not recorded. | Historical record says GCP-hosted one_combat e2cgen, source SHA e029dffb4c72449e8fc5b874391c49a27b2f6a81; 1,000 sims, A0, fair Searcher3/live-valid, 64 particles, accepted VNet/OOC models. Ledger retains the dataset SHA and artifact hashes. Current remote existence and full backend manifest were not verified. | Not available locally for reanalysis. No GCP job was launched. |
| Paired rest counterfactual (build/rest_cf.csv) | CSV, model, and build/rest_cf output directory absent from checked local trees; no remote location or byte size/hash is recorded. | Historical §54 describes same-pre-action rest-vs-smith branches with detached map and common future agent seed; a 50-run smoke emitted 104 decisions from 37 runs. train_rest_cf.py defaults to this CSV and learns paired gate-score differences. The historical record does not bind an exact data file, generator build, simulator backend/configuration, byte size, or source hash. | Not a controlled HP intervention: action changes HP and progression together. |
| Paired route/card counterfactual outputs (pathcfgen, datagen3) | selfplay/path_buffer/path_cf.csv, path_maps_5k.csv, selfplay/models/path_cf_5k*, build/card_cf.csv, selfplay/card_buffer/card_cf_maps.csv, and the historical card model paths are absent from checked local trees. No remote location or current byte size/hash is recorded. | Historical §§60–63 record datagen3 card branches from identical pre-choice states, common RNG futures, 100 simulations and two futures (21,863 decisions / 87,452 action rows; the map export was 9.7 MB, while the source CSV size was not recorded); §63 records pathcfgen with common future seeds (5,000 decisions / 11,784 branches), and model initialization from meta_graph_full21k.pt. Historical CSV/model paths are ledger references, not verified current files. | These action/route contrasts change more than HP and cannot identify the tracked model's HP derivative. |

**Verified:** the local absence checks and the historical ledger facts stated
above. **Unverified:** current remote E2c file existence, omitted byte sizes
for historical datasets, and the exact v_win training corpus/configuration.
The table separates those unknowns from the fresh 128-seed Silver collection.

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

Act-level exchange rates are shown below for both regimes. “Fair” means the
specified zero-hidden-future sensitivity; its prices are OOD-prone and should
not be read as ordinary observed terminal prices.

| Act | Regime | Mean HP slope, probability/HP (n rows) | Held-potion value, HP-equivalent (n rows) |
| --- | --- | ---: | ---: |
| 1 | Recorded | 0.000933 [0.000837, 0.001025] (1,232) | 6.76 [4.99, 8.85] (727) |
| 1 | Fair, hidden fields zeroed | 0.000675 [0.000576, 0.000767] (1,232) | 15.59 [8.35, 26.47] (629) |
| 2 | Recorded | 0.002670 [0.002412, 0.002936] (1,005) | 6.74 [4.65, 9.22] (833) |
| 2 | Fair, hidden fields zeroed | 0.002274 [0.002038, 0.002524] (1,005) | 13.55 [4.86, 29.76] (824) |
| 3 | Recorded | 0.002586 [0.002198, 0.002987] (832) | 6.70 [3.52, 12.58] (696) |
| 3 | Fair, hidden fields zeroed | 0.002355 [0.001977, 0.002740] (832) | 4.45 [3.19, 5.97] (695) |

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

Code references for the changing features: curHp transfer and exit healing
are in third_party/silver_lightspeed/src/combat/BattleContext.cpp:494 and
:598-613; Feed max HP is in third_party/silver_lightspeed/src/combat/Actions.cpp:979-995
and copied at BattleContext.cpp:495; Hand of Greed gold is in Actions.cpp:1008-1026
and copied at :496; potion inventory is transferred at :488-489 and encoded in
apps/one_combat/run_features.cpp:95-100; Writhing Mass/Parasite deck changes are
in BattleContext.cpp:479-484 and run_features.cpp:77-80; exit-mutated relics are
updated at BattleContext.cpp:550-596 and encoded in run_features.cpp:90-94.

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
- **Checks on the merged current-main source:** `cmake --preset
  linux-gcc-release` configured successfully; `cmake --build
  build/linux-gcc-release --target one_combat -j2` passed. The Release build
  emitted a narrowing-conversion warning in the run-time aggregate and an ODR
  warning for `Path` in the root and bundled `SimpleAgent.cpp`, plus the LTO
  serial-compilation note; these are outside the audit changes.
- Focused CTest passed **3/3**:
  `winnettest_selftest`, `vwin_terminal_pricing_audit_selftest`, and
  `export_win_model_selftest`. Python compilation and the analyzer
  self-test passed. Native/Python parity passed again after the merged build
  on 600 rows with max/mean difference 0.000000.
- Full CTest and GitHub Actions CI have not been run at this point; the draft
  PR will provide the authoritative CI status. No additional gameplay seeds
  were run for these checks.

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
  hashes, row/key integrity, exact interrupted-segment limitation, pre-collection source inventory, and
  reproducibility hash.
- [`remainder_35_provenance.json`](remainder_35_provenance.json) and
  [`remainder_35_schema.json`](remainder_35_schema.json) — wrapper-generated
  metadata for the completed final 35 seeds.
- [`parity_summary.txt`](parity_summary.txt),
  [`native_latency_20000.json`](native_latency_20000.json), and the four
  smoke diagnostic files — parity, cost, and pre-collection gate evidence.
