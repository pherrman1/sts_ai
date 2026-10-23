# The A20 CTM is pessimistic about today's Silver; a per-fight calibration fixes most of it (2026-10-23)

Stage 4 of the value-head research plan ([doc](https://claude.ai/artifact/MoLmbWb4QXdLTEsDVYgt4a)). Stages 1–2 found
the rollouts too pessimistic, and their Act-4 decomposition traced most of the Heart gap to the CTM's Heart model
(§663, [`../value_leaf_compare_20261023/RESULT.md`](../value_leaf_compare_20261023/RESULT.md)). On 2026-10-23 at 17:50Z
Philipp chose "Check the CTM first". The option said: compare the CTM's predictions with the real outcomes of the
stage-3 A/B's 4,096 games, by act and fight; if it over-predicts deaths, fit a per-act fix like M0 and propose an A/B.
This directory holds that check, the fix and its play check. The fix was first a research flag (§670). Philipp then
judged the CTM by its precision and made the fix the A20 default (ADR-TBD, 2026-10-23); a 512-seed guard against the
raw CTM ([`PREREG.md`](PREREG.md)) turns it off only if it comes out WORSE.

## The check
- **Rows.** The A/B recorded every real combat as a `combat_transition_row_v2` row (`STS_HEART_OUTCOME_CTM_ROWS=1`):
  97,561 fights from the 1,024 tars in `/mnt/project-files/value-level-ab/units/` (arms A, M, S and MS of §661, all
  rows supported). The 6,022 fights of the 256 stage 1–2 games (§663, `/mnt/project-files/value-leaf-compare/units/`)
  are a held-out set that no fit saw. Row counts and hashes: [`offline/rows.txt`](offline/rows.txt);
  [`offline/extract.sh`](offline/extract.sh) rebuilds them from the tars (re-run: all five hashes match).
- **Scores.** `one_combat ctmscorerows ROWS OUT.csv` with the deployed A20 stack: `pathb_a20_lizard` (`ae785ec2…`) with
  the Brew fallback `near_full_escape_pathb_a20` (`e338506d…`), the Lizard correction, the manifest's boss shift
  (§470) and the Act-4 survival model (`05279b3c…`, ADR-0048). Script: [`offline/score.sh`](offline/score.sh). The
  score CSVs (`off`, `zero`, `cal`; hashes in [`offline/scores.sha256`](offline/scores.sha256)) are on the share,
  gzipped, in `/mnt/project-files/ctm-calibration/scores/`.
- **Finding.** The CTM predicts too many deaths at most bosses and too much HP loss in Acts 2–4. It is the same in all
  four arms. Over the 48,674 fights of the odd seeds:

| fights | rows | deaths: observed | deaths: CTM | won fights: CTM's mean HP after − real |
|---|---|---|---|---|
| all | 48,674 | 0.032 | 0.038 | −1.9 |
| Act-1 boss | 1,959 | 0.050 | 0.093 | −3.9 |
| Act-2 boss | 1,578 | 0.150 | 0.166 | −8.6 |
| Act-3 elite | 3,034 | 0.044 | 0.050 | −8.1 |
| Act-3 boss | 2,131 | 0.148 | 0.189 | −19.0 |
| Shield and Spear | 808 | 0.051 | 0.080 | −3.1 |
| the Heart | 767 | 0.370 | 0.486 | (the run ends) |

  - Not everything is too pessimistic. The CTM under-predicts deaths at the Awakened One, Reptomancer, Gremlin Leader,
    Slavers and Act-2/3 event fights, and Act-1 hallway fights cost more HP than it predicts.
- **Likely cause (not tested).** The CTM was trained on combats of an older, weaker combat player. Today's Silver
  (g7f_E prior, learned stop, boss-only prior playouts) loses much less HP late in the run. The Act-4 model was
  trained on student C play (10-17, Heart won 32% of the time); here the Heart is won 63% of the time.

## The calibration (`STS_CTM_CALIBRATION`; the A20 default since ADR-TBD, `=0` restores the raw CTM)
- **Groups.** A fight's group is `<act>:<ENCOUNTER>` in an elite or boss room, else `<act>:<ROOM>` with ROOM one of
  NORMAL (hallway), ELITE, BOSS and OTHER (event fights and the rest), from the predictor input's room class. An
  encounter group needs 400 rows, a room group 100; a fight without either keeps the CTM's prediction.
- **Death.** Each group gets a shift on the logit of the death probability, applied after §470 and the Act-4 model.
  It is an L2-penalized logistic fit (Newton; λ = 2 Fisher units, towards 0 for room groups and towards the room
  group's shift for encounter groups). In two-fold seed CV the encounter groups' λ is flat between 0.5 and 5 (CV log
  loss 0.06848 at λ = 2, kept), against 0.07085 with room groups only and 0.07239 uncalibrated
  ([`offline/cv_lambda_fine.txt`](offline/cv_lambda_fine.txt)).
- **HP.** Each group gets a scale s on the HP losses of a won fight. The runtime multiplies every loss class of the HP
  head's distribution by s, splits the mass between the two nearest classes (so the mean loss scales exactly), keeps
  gains, and keeps the result in [1, max HP]. s is the least-squares fit of the real loss on s·A − B (A and B the
  predicted loss and gain parts, from a second scoring with every loss removed).
- **Table.** [`../../../../models/candidates/ctm_calibration_pathb_a20_v1.json`](../../../../models/candidates/ctm_calibration_pathb_a20_v1.json)
  (`359619f7…`), fitted on all 97,561 A/B fights by
  [`tools/ctm_calibration.py`](../../../../tools/ctm_calibration.py) `fit`. Examples (shift on the death logit,
  scale on HP loss): Hexaghost −0.84 / 0.87, The Guardian −0.91 / 0.78, Time Eater −1.43 / 0.35, Giant Head
  −1.16 / 0.31, Awakened One +0.65 / 0.71, Reptomancer +0.89 / 0.85, Act-3 hallway −0.15 / 0.54, Shield and Spear
  −0.56 / 0.84, the Heart −0.74 (its HP scale has no effect: the run ends).
- **Runtime.** `CombatTransitionRuntime::survival` (every survival, including the Lizard composition's two terms) and
  `calibrateHpLoss` (in `sampleNearFull`, so every sampled transition, and in the forecast expectation). The table
  applies to the runtimes of the stack it names (`pathb-a20`, fast and Brew fallback) and nowhere else. The live
  advisor refuses the flag.

## Validation
Out of sample, the calibration predicts real outcomes better in both folds and on the held-out games:

| test set (fit on) | fights | death log loss: CTM → calibrated | Δ [95% seed bootstrap] | won-fight HP error (MAE): CTM → calibrated | Δ [95%] |
|---|---|---|---|---|---|
| A/B odd seeds (even seeds) | 48,674 | 0.0731 → 0.0685 | −0.0045 [−0.0055, −0.0035] | 8.46 → 7.66 | −0.80 [−0.89, −0.71] |
| A/B even seeds (odd seeds) | 48,887 | 0.0717 → 0.0684 | [−0.0044, −0.0019] | 8.48 → 7.67 | [−0.89, −0.72] |
| stage 1–2 games (all A/B rows) | 6,022 | 0.0733 → 0.0698 | [−0.0059, −0.0009] | 8.23 → 7.60 | [−0.78, −0.47] |

By group, odd seeds, fit on even seeds ([`offline/eval_fit_even_on_odd.json`](offline/eval_fit_even_on_odd.json)):

| fights | rows | deaths: observed | predicted, CTM → calibrated | log loss | won-fight HP error (MAE) | HP bias (predicted − real) |
|---|---|---|---|---|---|---|
| all | 48,674 | 0.032 | 0.038 → 0.032 | 0.0731 → 0.0685 | 8.5 → 7.7 | −1.9 → +0.3 |
| 1:NORMAL | 12,215 | 0.002 | 0.002 → 0.002 | 0.0026 → 0.0026 | 3.6 → 3.6 | +0.6 → +0.3 |
| 1:ELITE | 4,965 | 0.013 | 0.017 → 0.011 | 0.0362 → 0.0363 | 7.6 → 7.6 | +0.3 → +0.2 |
| 1:BOSS | 1,959 | 0.050 | 0.093 → 0.068 | 0.1551 → 0.1389 | 10.8 → 10.2 | −3.9 → −1.0 |
| 1:OTHER | 204 | 0.020 | 0.003 → 0.003 | 0.1130 → 0.1157 | 7.3 → 7.3 | +2.0 → +0.7 |
| 2:NORMAL | 9,319 | 0.010 | 0.012 → 0.011 | 0.0263 → 0.0261 | 6.6 → 6.5 | −0.3 → +0.4 |
| 2:ELITE | 3,623 | 0.047 | 0.034 → 0.036 | 0.1231 → 0.1189 | 10.7 → 10.5 | −0.5 → +0.6 |
| 2:BOSS | 1,578 | 0.150 | 0.166 → 0.158 | 0.3077 → 0.3053 | 17.8 → 16.1 | −8.6 → +0.2 |
| 2:OTHER | 406 | 0.039 | 0.027 → 0.029 | 0.1132 → 0.1117 | 7.6 → 7.9 | −0.1 → −1.2 |
| 3:NORMAL | 6,997 | 0.009 | 0.010 → 0.008 | 0.0264 → 0.0265 | 7.6 → 6.7 | −2.2 → +0.5 |
| 3:ELITE | 3,034 | 0.044 | 0.050 → 0.040 | 0.1458 → 0.1308 | 15.2 → 11.6 | −8.1 → −0.0 |
| 3:BOSS | 2,131 | 0.148 | 0.189 → 0.148 | 0.2839 → 0.2444 | 24.9 → 16.5 | −19.0 → +0.5 |
| 3:OTHER | 668 | 0.027 | 0.011 → 0.012 | 0.1248 → 0.1235 | 9.1 → 8.7 | −2.7 → −0.6 |
| Shield and Spear | 808 | 0.051 | 0.080 → 0.052 | 0.1698 → 0.1619 | 18.6 → 18.0 | −3.1 → +0.8 |
| the Heart | 767 | 0.370 | 0.486 → 0.391 | 0.4514 → 0.4058 | 18.6 → 17.9 | +6.0 → +1.8 |

- The gains are at the bosses, Act-3 elites and Act 4. Low-death groups (Act-1 hallways and elites, events) stay
  about where they were.
- Per fight type and per elite and boss, over both halves: [`offline/errors_by_fight.md`](offline/errors_by_fight.md)
  (death-rate and HP-loss errors, predicted − real; [`offline/group_errors.py`](offline/group_errors.py)). Out of
  sample, every act × room group is within about ±2 pp and ±2 HP. Single encounters are within their noise; the
  largest is Hexaghost at ±4.6 pp, whose real death rate differs by 5 pp between the two halves.
- Held out ([`offline/compare_heldout_stage12_cpp.json`](offline/compare_heldout_stage12_cpp.json), scored by the C++
  runtime with the table): Act-3 bosses 0.3305 → 0.2639 log loss and 23.1 → 15.4 HP error; the Heart 0.458 → 0.358
  predicted deaths against 0.337 observed. One group got worse: Act-1 bosses, 0.2016 → 0.2107 log loss, where the
  held-out games died more often (21 of 249, 0.084) than the A/B (0.063).
- **By pre-fight HP** ([`offline/hp_bands_fit_even_on_odd.txt`](offline/hp_bands_fit_even_on_odd.txt),
  [`offline/hp_bands_fit_odd_on_even.txt`](offline/hp_bands_fit_odd_on_even.txt)), the CTM's pessimism sits at higher
  HP. Below 20 HP its death rate is about right in Acts 2–3 and too low in Act 1. The calibration lowers it further in
  Acts 1 and 3, most in Act 3, so Act-3 fights at low HP look safer than they are:

  | Act 3, below 20 HP | fights | observed | CTM | calibrated |
  |---|---|---|---|---|
  | odd seeds | 179 | 0.475 | 0.488 | 0.431 |
  | even seeds | 143 | 0.434 | 0.429 | 0.382 |

  - It also flattens the death gap between low and high HP. At Act-3 bosses, 20–39 HP against 60+ HP, the gap is
    0.43 observed, 0.46 for the CTM and 0.38 calibrated (odd seeds).
  - An HP-fraction term in the shift improved the overall out-of-sample log loss by at most 0.0002 in either fold, and a
    slope on the logit (Platt) made it worse ([`offline/death_variants.txt`](offline/death_variants.txt)). The table
    keeps the plain shift.
  - The search might use this optimism, for example by entering Act-3 fights at low HP more readily. The A/B's
    descriptive endpoints count fights entered below 20 HP.

## Implementation checks
- **Off is unchanged.** Unset and `=0`, `ctmscorerows` of all five row sets is byte-identical to the scores before the
  change ([`offline/parity.txt`](offline/parity.txt)). ctests `ctm_calibration_unset` and `ctm_calibration_off`.
- **C++ = the fit.** With the table, the runtime's scores match the tool's prediction on all 99,764 fights without an
  active Lizard Tail: death within 1.2e-7, mean won-fight HP within 2e-6 HP. The clamp at 1 HP, which a scale above 1
  can hit, only raises the mean, by at most (s − 1)·(pre HP − 1). Under an active Lizard Tail (3,819 fights) the
  shift acts on the composition's two survivals, so those rows differ from the tool's formula by design; the
  held-out comparison above uses the C++ scores, Lizard rows included. ctest `ctm_calibration_parity` checks 27
  fixture fights (one per group, one with Entropic Brew for the fallback runtime).
- Binary: x86-64-v3 release `one_combat` at `ea859598`, sha256 `2e65eff7…`. Score hashes:
  [`offline/scores.sha256`](offline/scores.sha256) (`off`, `zero` = every loss removed, `cal` = the table).

## Commands (as run)
```
python3 -I tools/ctm_calibration.py zero zero.json
bash offline/score.sh BIN ROWS off  off            # and: off0 ; table zero.json -> zero ; table TABLE -> cal
python3 -I tools/ctm_calibration.py fit TABLE --note "…" off/A.csv,zero/A.csv off/M.csv,zero/M.csv off/S.csv,zero/S.csv off/MS.csv,zero/MS.csv
python3 -I tools/ctm_calibration.py fit offline/table_fit_even.json --seeds even SPECS   # and --seeds odd: table_fit_odd.json
python3 -I tools/ctm_calibration.py eval offline/table_fit_even.json --seeds odd SPECS --json offline/eval_fit_even_on_odd.json
python3 -I tools/ctm_calibration.py eval TABLE off/LC.csv,zero/LC.csv --json offline/eval_heldout_stage12.json
python3 -I tools/ctm_calibration.py compare off/LC.csv cal/LC.csv --json offline/compare_heldout_stage12_cpp.json
python3 -I tools/ctm_calibration.py parity TABLE off/X.csv,zero/X.csv cal/X.csv ROWS/X.jsonl
python3 -I tools/ctm_calibration.py fixture TABLE ROWS/A.jsonl off/A.csv,zero/A.csv tests/fixtures/ctm_calibration_parity.jsonl
python3 -I offline/cv_lambda.py tools SPECS
bash offline/extract.sh OUT                         # rebuilds the five row sets of offline/rows.txt from the tars
python3 -I offline/hp_bands.py tools/ctm_calibration.py offline/table_fit_even.json odd SPECS > offline/hp_bands_fit_even_on_odd.txt
python3 -I offline/death_variants.py tools/ctm_calibration.py even odd 0.5 SPECS   # and odd even: death_variants.txt
python3 -I offline/group_errors.py tools/ctm_calibration.py offline/table_fit_even.json offline/table_fit_odd.json SPECS > offline/errors_by_fight.md
```

## What this does not show
Better predictions of real fights do not by themselves make the search play better: the A/B's 4,096 games were
played with the uncalibrated CTM, and the search's rollouts reach states the real runs do not. The last CTM
calibration A/B (Act-4 survival model, §534) was NOT_SHOWN, 75 vs 82 Heart kills of 512. Whether this one helps is
not tested: the guard ([`PREREG.md`](PREREG.md)) only checks that it does not clearly lose.
