# `v_win` terminal-pricing audit

## Decision

**`VWIN_W1_NEEDS_SMOOTHING`** under the frozen handoff thresholds. HP slope and
held-potion value are positive with seed-bootstrap intervals above zero in all
three acts. The median longest low-HP flat run is 5 HP, within the 10-HP limit.
Only 63.8% of RAW rows satisfy the monotonicity rule, below the required 95%.
This is an input-readiness result for a future W1 lookup table; it is not a
gameplay-quality result or permission to promote a runtime change.

## W1 review interpretation

Only a monotonically smoothed HP curve remains a candidate `v_win` input, and
then only for non-act-boss victories. In A0, Silver's native terminal evaluator
sets post-battle HP to max after an act-boss win; the audit's boss `s_HP_span`
median POST/RAW ratio is 0.7833, so the win tree also changes slope by about
22% across the reward boundary. Near realized HP, 14.5–21.6% of rows by room
type have a probability drop above 0.005 within ±20 HP; the 95th-percentile
largest drops are 15–29 HP-equivalents. Smoothing must therefore enforce
monotonicity.

Gold is a possible secondary input, but its act-dependent signal is small and
thinly supported. Span-denominator mean/median HP-equivalents are 0.231/0.097,
0.058/0.025, and 0.040/0.000 per gold across Acts 1–3. Held-potion values are
4.51/1.51, 4.28/1.66, and 4.78/0.61; max-HP-only values are 0.613/0.314,
−0.061/0.000, and −0.477/0.000. Potion-type prices and max-HP prices are not
usable terminal prices. RAW-row AUC is 0.708 and first-row-per-seed AUC is
0.638; with 128 seeds discrimination is weak, and the model underpredicts the
cohort run-win rate. None of these descriptions changes the frozen verdict or
supports a gameplay-quality claim.

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
- **Silver root prior:** telemetry reported `prior_model_loaded=0`. This
  gauge reads the optional learned Silver root prior
  (`g_silverPriorModel` / `STS_SILVER_ROOT_PRIOR_MODEL`), which is off by
  default; it is not a preregistration deviation. The retained logs show the
  compact `v_win` and `v_rich` trees, but do not show whether the separate
  compact policy trees (`models/policy_trees_c.txt` / `STS_POLICY`) loaded.
  Compact-policy load status is **Unverified**; `prior_model_loaded` does not
  measure it.
- **Collection interruption:** the initial process stopped after its CSV
  represented 93 seeds (`3100000..3100092`). The resulting CSV is retained and
  its bytes/hash/rows are recorded below, but the interrupted process did not
  leave a seed-guard provenance sidecar or final aggregate invalid/quarantine
  and simulator-health counters. `finishE2cRun` emits rows only when the run
  passes `trainingRunValid`, which rejects unresolved runs and simulator
  health failures; all 93 represented seeds therefore passed it. The absent sidecar still leaves attempted/completed totals and any
  unrepresented quarantines unknown.
  The exact process stop cause is also unknown. The remaining 35 seeds were
  collected separately and have a complete
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
The parity gate was repeated after synchronization with `origin/main`; the
latest-main build and result are recorded below and in
[`parity_summary.txt`](parity_summary.txt).

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

| Act | RAW rows | Monotone share | Median flat run | Zero HP-slope share | Mean HP slope, probability/HP | Held-potion value, HP-equivalent | Gold, HP-equivalent/gold | +1 max HP and +1 current HP (Feed-like), HP-equivalent |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 1,232 | 65.9% [61.4, 70.4] | 5 [5, 5] | 0.81% [0.08, 1.85] | 0.000933 [0.000837, 0.001025] | 6.76 [4.99, 8.85] | 0.357 [0.303, 0.418] | 1.55 [0.03, 3.52] |
| 2 | 1,005 | 62.1% [55.9, 67.7] | 4 [4, 5] | 0.80% [0.20, 1.68] | 0.002670 [0.002412, 0.002936] | 6.74 [4.65, 9.22] | 0.090 [0.069, 0.114] | 1.00 [-1.08, 2.20] |
| 3 | 832 | 62.6% [56.6, 68.6] | 4 [4, 4] | 0.84% [0.00, 1.97] | 0.002586 [0.002198, 0.002987] | 6.70 [3.52, 12.58] | 0.058 [0.014, 0.117] | 0.30 [-3.13, 2.39] |

Silver's win-branch prices are score points, where +1 post-battle HP = 1 point:
11 per potion, 0.25 per gold, and 2 per max-HP point. The existing probe adds
both +1 max HP and +1 current HP, so its comparable Silver price is 3 points
(1 through healed HP plus 2 from max HP). A max-HP-only probe has a Silver
reference of 2 points and is reported separately under the post-review
additions. The positive HP-slope and held-potion criteria pass in every act;
the max-HP probes are descriptive and are not sign gates.

The tracked compact model has 2,127 splits on curHp, 3,257 on maxHp, 2,210 on
gold, 271 on potionCount, and 153 on potionCapacity. The most-split potion
features are pot7 (18), pot26 (16), and pot29 (11). The compact export stores
split indices and thresholds but no gain values, so total gain is unavailable;
the complete split counts are in q1_split_counts.csv. Per-potion deltas,
HP-equivalents, and zero-value shares for ids with n >= 30 are in q1_potions.csv.
Across the 33 potion-type features there are 124 splits, and six potion types
have no splits; potionCount alone has 271. Fairy in a Bottle (pot21) has 3
splits and a mean value of 2.48 HP-equivalents (95% CI 1.07–4.27), with zero
value in 32.7% of rows. Silver prices any held potion at 11 score points and
adds a 0.3 × max-HP death save for Fairy in a Bottle, about 35 points at
80 max HP. **Inference:** per-type `v_win` prices mostly reflect which states
hold each potion, not potion identity; `v_win` is not a usable source of
per-potion prices.

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

### Review correction A4 — unmatched RAW rows and potion drops

The 363 unmatched RAW rows are not explained by full belts alone. For the
drop proxy, I used only the next RAW row from the same seed and act when its
floor is exactly one higher: `potionChance` falling by 10 means a drop, and
rising by 10 means no drop. Event potion generation can also change this
counter, so non-adjacent or otherwise ambiguous transitions remain
unclassified. The implementation changes `potionChance` in combat/event
potion generation and resets it at act transitions; the adjacent-floor,
same-act restriction avoids crossing an intervening event or act reset.

| Pair status | RAW belt state | Drop | No drop | Unclassified |
| --- | --- | ---: | ---: | ---: |
| Matched to POST | Full | 1 | 153 | 259 |
| Matched to POST | Space available | 423 | 464 | 1,406 |
| No POST row | Full | 147 | 0 | 199 |
| No POST row | Space available | 0 | 0 | 17 |

There are no classified unmatched residuals: all 147 classifiable unmatched
rows are full-belt drops. A single matched full-belt drop is explained by a
new `r159` Potion Belt feature between RAW and POST; Potion Belt adds two
slots before the potion is claimed. The remaining 216 unmatched rows have no
classifiable drop status. Thus the data supports the potion-drop explanation
for classified unmatched rows, with an explicit capacity-increase exception
and an unclassified residual; it does not establish a universal rule for all
363 rows. The belt was full in 759/3,069 RAW rows (24.7%). Among the 301
full-belt rows with classifiable adjacent-floor status, 148 (49.2%) had a
potion drop. The run policy takes a potion only when a slot is available and
has no discard/swap path.
The belt was full in 413/2,706 matched rows (15.3%) and 346/363 unmatched
rows (95.3%).

Code inspection of the full-run `REWARDS` chain confirms that its free-reward
handler takes a potion only when a slot is available. The later handlers do
not discard or swap a carried potion to make room. A reward relic that
increases capacity, such as Potion Belt, can be collected before the potion
decision and create space. `captureE2cPost` in
`apps/one_combat/e2c_capture.cpp` also returns while gold, relic, or potion
rewards are pending, so an unclaimed potion blocks POST capture. Q4's
matched-pair analysis excludes all no-POST fights by construction.

The 147 proxy-confirmed full-belt drops are 4.79% (4.8%) of all 3,069 RAW
fights. If every one of the 199 unmatched full-belt rows with unknown proxy
status also represents an unclaimed potion drop, the code-path upper count is
346/3,069 (11.27%, or 11.3%). This is a conditional upper bound, not an
estimated rate. The 17 unmatched space-available rows show that missing POST
capture also has other causes; the exact full-belt forfeiture rate is unknown
and can be lower.

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
The `curHp` coefficient is `−3.36e−4` per HP with a seed-bootstrap interval
excluding zero; relative to mean `s_HP=0.00195`, this is about a 17% shift.
Thus the formal low-R² gate passes while RAW-to-POST HP pricing still differs
across states. The 2,706 Q4 pairs are an inner join on `(seed,fight_index)`;
unmatched RAW fights do not enter this regression.

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
sensitivity check, not an alternate production price table. The Spearman gate
measures rank agreement, not price levels: recorded-to-zeroed act-level
potion HP-equivalents change by factors 2.31, 2.01, and 0.66 in Acts 1–3.
The fair-regime exchange rates are therefore unstable even though the frozen
rank-correlation gate passed.

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

## Post-review descriptive additions (not preregistered)

The following B1–B7 summaries are descriptive additions. They do not change
the preregistered metrics, thresholds, or verdict.

### B1 — actual-span HP slope and prices

`s_HP_span=(V(hi)-V(lo))/(hi-lo)`, where `lo=max(1,curHp-5)` and
`hi=min(maxHp,curHp+5)`. Rows at `curHp <= 5` or `curHp > maxHp-5` have a
clamped probe. The preregistered fixed-10 results above remain primary. The
verdict's HP sign gate divides by the positive constant 10, while monotonicity
and flat-run use the complete sweep; none depends on the B1 denominator or
slope magnitude.

| Act | Clamped rows (95% seed-bootstrap CI) | Potion mean / median, /10 → span | Gold mean / median, /10 → span | Feed-like max HP mean / median, /10 → span |
| --- | ---: | ---: | ---: | ---: |
| 1 | 56.0% [52.6, 59.4] | 6.76 / 1.96 → 4.51 / 1.51 | 0.357 / 0.125 → 0.231 / 0.097 | 1.548 / 0.976 → 1.263 / 0.688 |
| 2 | 45.9% [40.9, 50.9] | 6.74 / 1.99 → 4.28 / 1.66 | 0.090 / 0.032 → 0.058 / 0.025 | 1.001 / 0.645 → 0.937 / 0.492 |
| 3 | 54.1% [48.4, 59.8] | 6.70 / 0.85 → 4.78 / 0.61 | 0.058 / 0.000 → 0.040 / 0.000 | 0.300 / 0.721 → 0.140 / 0.586 |

### B2 — robust HP-equivalent summaries

Span-denominator summary below: mean, median with 95% seed-bootstrap interval,
and row-level IQR. `results.json` also records these fields for every
per-potion-id HP-equivalent, plus counts and the fixed-10 summaries.

| Act | Price | Mean | Median [95% CI] | IQR |
| --- | --- | ---: | ---: | ---: |
| 1 | Held potion | 4.510 | 1.508 [1.101, 2.052] | [0.000, 4.945] |
| 1 | Gold per gold | 0.231 | 0.097 [0.087, 0.110] | [0.042, 0.215] |
| 1 | Feed-like max HP | 1.263 | 0.688 [0.529, 0.818] | [0.114, 1.422] |
| 1 | Max HP only | 0.613 | 0.314 [0.255, 0.352] | [0.000, 0.818] |
| 2 | Held potion | 4.284 | 1.664 [1.163, 2.047] | [0.000, 4.172] |
| 2 | Gold per gold | 0.058 | 0.025 [0.021, 0.031] | [0.002, 0.068] |
| 2 | Feed-like max HP | 0.937 | 0.492 [0.312, 0.715] | [0.000, 2.035] |
| 2 | Max HP only | −0.061 | 0.000 [0.000, 0.063] | [0.000, 0.445] |
| 3 | Held potion | 4.780 | 0.614 [0.162, 1.352] | [0.000, 3.705] |
| 3 | Gold per gold | 0.040 | 0.000 [0.000, 0.003] | [−0.011, 0.025] |
| 3 | Feed-like max HP | 0.140 | 0.586 [0.300, 0.828] | [0.000, 2.039] |
| 3 | Max HP only | −0.477 | 0.000 [0.000, 0.000] | [0.000, 0.624] |

### B3 — max-HP-only probe

The +1 max-HP probe holds current HP fixed. Act-level mean / median
HP-equivalents were 0.613 / 0.314, −0.061 / 0.000, and −0.477 / 0.000 for
Acts 1–3. The Feed-like probe, which adds both +1 max HP and +1 current HP,
was 1.263 / 0.688, 0.937 / 0.492, and 0.140 / 0.586. Silver's comparable
score prices are 2 for max HP only and 3 for the Feed-like change.

### B4 — outcome discrimination

RAW-row ROC-AUC was 0.708 [0.652, 0.769] (`n=3,069`, 128 seeds). Using only
the first RAW row per seed, AUC was 0.638 [0.528, 0.745] (`n=128`). Both CIs
use seed bootstrap; 128 source seeds provide weak power.

### B5 — paired RAW-to-POST prices

This is the decision-relevant descriptive version of Q4; it does not replace
the frozen gate. Ratios use positive finite RAW denominators; paired
differences use all pairs with finite prices.

| Room | Price | Median POST/RAW ratio [95% CI] | Median POST−RAW difference [95% CI] |
| --- | --- | ---: | ---: |
| Monster | `s_HP_span` | 1.0014 [1.0009, 1.0019] | +1.08e−6 [6.27e−7, 1.57e−6] |
| Monster | Held-potion HP-eq | 0.9441 [0.8919, 0.9780] | −1.51e−5 [−8.66e−5, 0] |
| Elite | `s_HP_span` | 0.9818 [0.9700, 0.9910] | −2.28e−5 [−4.85e−5, −7.79e−6] |
| Elite | Held-potion HP-eq | 0.9590 [0.8729, 0.9970] | −0.000423 [−0.00629, 0] |
| Boss | `s_HP_span` | 0.7833 [0.7307, 0.8274] | −0.000372 [−0.000507, −0.000273] |
| Boss | Held-potion HP-eq | 0.6939 [0.4281, 0.7802] | −0.525 [−1.205, −0.308] |

### B6 — location and size of HP-sweep drops

Largest-drop median and p95 are reported in probability points and in HP
equivalents (`drop / abs(s_HP_span)`). “Near current HP” means a drop above
0.005 within the defined ±20 HP interval.

| Act | Near-current share [95% CI] | Largest probability drop: median / p95 | Largest HP-eq drop: median / p95 |
| --- | ---: | ---: | ---: |
| 1 | 14.5% [11.3, 17.9] | 0.00309 / 0.01139 | 3.684 / 29.374 |
| 2 | 21.6% [17.0, 26.5] | 0.00366 / 0.01378 | 1.454 / 15.414 |
| 3 | 19.7% [14.7, 25.1] | 0.00369 / 0.01384 | 1.806 / 24.842 |

### B7 — retained segment completeness

The exact interruption cause is unknown; the process left no seed-guard
sidecar or final aggregate counters. The 35 seeds in flight at the interruption
reran cleanly (35/35), so a seed that deterministically crashes is not
supported; an external stop such as a command timeout remains an inference.
Across all 128 seeds, 48 have noncontiguous captured `fight_index` values, and
the last captured RAW floor differs from `finalFloor` in every seed. E2c
increments the fight index across battles but captures only monster, elite, and
Act 1–2 boss rooms; event-initiated battles and Act 3 bosses therefore leave
expected gaps. The final-minus-last-RAW floor deltas are 1: 5, 2: 22, 3: 71,
4: 15, 5: 10, and 6: 5. The last seed block in segment 1 by file order is seed
`3100091`: its fight indices are contiguous 0–26, last RAW floor 48, and
`finalFloor` 51. Segment 1 has 4,227 data rows, ends with a complete
newline-terminated line, and its final row has all 1,387 columns; there is no
evidence of a truncated CSV.

The two current-code full runs were byte-identical. Their `results.json`
SHA-256 is `79d4709d71baf32c70e817445b46de70df70c3f30e05972b9a359113f350dd4e`.

## Scope, deviations, and checks

- No W1 table, runtime integration, default change, gameplay claim, or Q2
  continuation experiment is included.
- `prior_model_loaded=0` reports the optional Silver learned root prior, which
  was off by default; it is not a preregistration deviation and does not
  report compact-policy-tree load status. Compact-policy load status is
  Unverified from the retained logs. Rows from all 93 represented first-segment
  seeds passed `trainingRunValid`; exact attempted/completed and any
  unrepresented quarantine totals remain unavailable without the sidecar.
  The interruption cause is unknown.
- The local raw E2c CSVs are not committed. This packet preserves result JSON,
  aggregate tables, segment provenance/schema for the completed remainder,
  integrity accounting, parity outcome, smoke summaries, and native latency.
- **Earlier merged-main validation (before the current-main refresh):** branch
  source `82dc7f04` merged `origin/main` at
  `03ae0297ac33fba41c64921d5b0bcc6eabe4be2a`. The Release
  `one_combat` rebuild passed. CMake reconfigured for added source files; the
  build emitted the existing `one_combat.cpp` narrowing-conversion warning,
  duplicate `Path` ODR warning across the root and bundled `SimpleAgent.cpp`,
  and serial LTO note.
- Focused CTest after rebuild passed **3/3**:
  `winnettest_selftest`, `vwin_terminal_pricing_audit_selftest`, and
  `export_win_model_selftest`. Native/Python parity on the retained 600-row
  fixture compared 600/600 rows and passed at `1e-4`; max and mean absolute
  difference were both `0.000000`.
- In the post-review working tree, Python compilation, analyzer self-test,
  JSON validation of `results.json` and `collection_provenance.json`, and
  `git -c core.whitespace=cr-at-eol diff --check` passed. Both full analyzer
  runs were byte-identical at the SHA-256 above. The local segment hashes
  matched provenance. No C++ file changed in the review corrections.
- **Current-main revalidation:** merged refreshed `origin/main`
  `f8fa4a3fd9ebbbc01f2003946ee40c634bcd677d` into the task branch; the ledger
  audit is §351 after main's §§349–350. `cmake --build
  build/linux-gcc-release --target one_combat -j2` passed. The build reported
  return-path warnings in `Actions.cpp` and vendored `SimpleAgent.cpp`, a
  `one_combat.cpp` narrowing warning, the existing duplicate-`Path` ODR
  warning, and serial LTO. Focused CTest passed **3/3**:
  `winnettest_selftest`, `vwin_terminal_pricing_audit_selftest`, and
  `export_win_model_selftest`. Python compilation and analyzer self-test passed;
  both local E2c hashes matched provenance; JSON validation, worktree/submodule
  validation, and staged/unstaged diff checks passed.
- Full CTest has not been run locally. GitHub Actions run #1184 is a historical
  prior-head run that skipped `Linux GCC` under the draft-PR condition. The
  authoritative status for the current reviewed head is available in PR #317.
  No new gameplay seeds or GCP jobs were run.

## Evidence files

- [`results.json`](results.json) — complete machine-readable Q1–Q6 results,
  unchanged verdict checks, intervention review, counter splits, source-group
  list, and the separately keyed post-review descriptive additions.
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
