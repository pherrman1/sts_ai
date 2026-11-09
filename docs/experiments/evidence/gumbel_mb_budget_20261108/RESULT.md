# Max backup at 32k and 64k simulations under the Gumbel root (result)

Pre-registration: [PREREG.md](PREREG.md). Analysis: `analyze.py` as frozen, output `results/analysis.json`. Follow-up
to §772 ([Gumbel budget check](../gumbel_budget_20261108/RESULT.md)).

## Run

- Run commit 1a296818 (code 5a233efd, binary c28d71b7), queue schedule, 4 lanes per worker.
- Philipp's go was for 40 workers, but only 14 ran (W1-W12, W39, W40). W13-W38 failed at start (21:48 CET) with the
  session limit ("too many threads and Claude Code sessions are running at once") and never claimed a unit.
- The first unit started at 21:47 CET on 2026-11-08, the first tar was uploaded at 22:14 CET, and the last at 04:53
  CET on 2026-11-09. Unit wall time sums to 304 lane-hours (projected 332). The median unit took 8.7 min, the longest
  2.7 h (`1655315178 3 g64mb 50:1`, one copy of an act-3 boss at 64k).
- 1,187 units were claimed on a first attempt and 8 on a second. The 8 first attempts were lost when the containers
  of W6 and W12 restarted; none of them uploaded a tar.
- `verify_campaign.py`: 1,187 of 1,187 units OK, 0 extra tars, all from run 1a296818.
- Unit tally by rc (the PREREG selection): 1,187 rc 0, 0 rc != 0, 0 missing. §772's 1,728 units and §770's 329 units
  are all rc 0 as well. Nothing was excluded.
- `analyze.py`: 1,878 act-1-3 elite and boss fights from 309 runs, **0 dropped** (no `missing_side`). Copies seen in
  more than one unit agree: 0 conflicts for production and for the arms, in this campaign and in §772's and §770's.

## Reproduction (gate for the pairing)

Production here equals §770's production in all 4 copies of **1,878 of 1,878 fights (100%)** (7,512 copies; won, exit
HP, exit max HP, turns, decisions, simulations and potions). The gate is ≥ 99%, so all contrasts are paired.

## HP lost per fight

Production loses 11.60 HP per fight on these states, Baalorlord 8.74.

| arm | source | HP lost | deaths | potions | sims / decision | CPU ratio |
|---|---|---|---|---|---|---|
| production | here | 11.60 | 5.5% | 0.555 | 4,547 | 1.00 |
| g16 = gsh16+flat16000 | §770 | 10.71 | 5.2% | 0.546 | 14,733 | 3.46 |
| g16mb = gsh16+flat16000+mb4 | §772 | 10.43 | 4.8% | 0.520 | 14,810 | 3.33 |
| g32 = gsh16+flat32000 | §772 | 10.47 | 4.9% | 0.549 | 29,447 | 6.73 |
| g64 = gsh16+flat64000 | §772 | 10.35 | 4.7% | 0.541 | 59,003 | 13.54 |
| **g32mb = gsh16+flat32000+mb4** | here | **10.18** | 4.6% | 0.514 | 29,655 | 6.53 |
| **g64mb = gsh16+flat64000+mb4** | here | **9.97** | 4.6% | 0.513 | 59,339 | 12.80 |

CPU ratios are against this campaign's production. The arms from §770 and §772 ran on other machines, so their ratios
mix machines (PREREG caveat).

## Primary A: max backup at high budget (97.5% run-clustered bootstrap CI)

| contrast | mean | 97.5% CI | deaths (95%) |
|---|---|---|---|
| g32mb − g32 | **−0.29** | **[−0.57, −0.01]** | −0.29 pp [−0.7, +0.1] |
| g64mb − g64 | **−0.38** | **[−0.62, −0.13]** | −0.08 pp [−0.4, +0.3] |

Both have hi < 0. g64mb − g64 has the lower mean → **MB_HELPS_AT_HIGH_BUDGET (gsh16+flat64000+mb4 vs
gsh16+flat64000)**.

## Primary B: budget on top of max backup (97.5%)

| contrast | mean | 97.5% CI | deaths (95%) |
|---|---|---|---|
| g32mb − g16mb | **−0.25** | **[−0.46, −0.03]** | −0.24 pp [−0.6, +0.1] |
| g64mb − g16mb | **−0.46** | **[−0.70, −0.21]** | −0.20 pp [−0.6, +0.2] |

Both have hi < 0. g64mb − g16mb has the lower mean → **MORE_SIMS_HELP_WITH_MB (gsh16+flat64000+mb4 vs
gsh16+flat16000+mb4)**.

A and B are separate families (PREREG). No default change on either.

## Secondary (95% CIs, descriptive)

- g64mb − g32mb: −0.21 [−0.44, +0.02]. The step from 32k to 64k is again not resolved (§772 without max backup:
  −0.12 [−0.33, +0.08]).
- Against g16 (§770): g32mb −0.53 [−0.75, −0.32], g64mb −0.74 [−0.96, −0.52].
- Against production: g32mb −1.42 [−1.70, −1.13], g64mb −1.62 [−1.92, −1.34].
- Share of the production − Baalorlord gap (2.86 HP) closed, as point estimates: g16 31%, g16mb 41%, g64 44%, g32mb
  50%, g64mb 57%.

## Co-reported by cut (95% CIs)

| cut | n | prod HP lost | g32mb − g32 | g64mb − g64 | g64mb − g16mb | CPU g64mb |
|---|---|---|---|---|---|---|
| act 1 | 998 | 12.11 | +0.03 [−0.23, +0.29] | −0.10 [−0.34, +0.15] | −0.27 [−0.48, −0.06] | 15.1 |
| act 2 | 536 | 12.44 | **−0.97 [−1.41, −0.51]** | **−0.75 [−1.23, −0.27]** | −0.57 [−1.02, −0.13] | 13.6 |
| act 3 | 344 | 8.79 | −0.17 [−0.90, +0.58] | −0.60 [−1.30, +0.12] | −0.83 [−1.63, −0.02] | 11.6 |
| elites | 1,350 | 10.19 | **−0.45 [−0.70, −0.20]** | −0.27 [−0.50, −0.03] | −0.19 [−0.40, +0.01] | 16.7 |
| bosses | 528 | 15.19 | +0.11 [−0.43, +0.66] | **−0.66 [−1.18, −0.14]** | **−1.13 [−1.66, −0.60]** | 12.3 |
| 1E / 1B | 744 / 254 | 11.24 / 14.65 | +0.03 / +0.03 | +0.06 / −0.56 | −0.09 / −0.78 | |
| 2E / 2B | 397 / 139 | 10.40 / 18.24 | −0.98 / −0.91 | −0.76 / −0.72 | −0.35 / −1.19 | |
| 3E / 3B | 209 / 135 | 6.02 / 13.07 | −1.13 / +1.33 | −0.49 / −0.77 | −0.27 / −1.71 | |

- Max backup's gain sits in acts 2 and 3, not in act 1, at both budgets. At 32k it is again an elite gain (bosses
  +0.11, as at 16k in §772); at 64k it reaches the bosses too (−0.66 [−1.18, −0.14]). Elite − boss differences are
  not tested.
- With max backup, the budget gain from 16k to 64k sits in the bosses (−1.13 [−1.66, −0.60]); in elites it is −0.19
  [−0.40, +0.01].

By encounter (n ≥ 20; about 60 contrasts, so a few resolve by chance; all have wide CIs):
- g64mb − g64: Slavers −1.31 [−1.98, −0.67] (n 129), Hexaghost −1.15 [−2.09, −0.20] (n 93), Awakened One −2.37 [−5.01,
  +0.21], Automaton −1.64, Champ −1.43, Reptomancer −1.10. Positive: Collector +0.52, Donu and Deca +0.19, Lagavulin
  +0.17.
- g32mb − g32: Automaton −2.28 [−4.28, −0.24], Giant Head −1.39 [−2.63, −0.13], Gremlin Leader −1.34 [−2.12, −0.59].
  Positive: Time Eater +3.53 [+1.07, +5.98] (n 47), The Guardian +0.67.
- g64mb − g16mb: Collector −1.80 [−3.45, −0.12], Awakened One −2.26, Time Eater −1.86, Champ −1.31. Positive: Nemesis
  +0.43, 3 Sentries +0.23.

All cuts are in `results/analysis.json`.

## Interpretation (Inference)

- The two gains of §772 add up. Max backup helps at every budget tested (16k −0.29, 32k −0.29, 64k −0.38), and more
  budget helps with max backup as much as without it (32k −0.25 vs −0.24, 64k −0.46 vs −0.37). g64mb is the best arm
  measured on these states: 0.74 HP per fight below g16 and 1.62 below production, closing 57% of production's gap to
  Baalorlord.
- Max backup costs nothing extra: the max-backup arms ran at 0.97× (32k) and 0.95× (64k) of the CPU of their budget
  arms (ratios across campaigns and machines).
- Per CPU the returns still diminish: g16mb gets −0.29 below g16 at about g16's cost, g32mb −0.53 at 1.9× g16's CPU,
  g64mb −0.74 at 3.7×. The step from 32k to 64k with max backup (−0.21) is not resolved.
- Exploratory: these states were used before (§711/§716/§718/§770/§772/§773), the main line is production's, and
  one Gumbel setting (k 16, c_visit 50, c_scale 1) and one max-backup setting (min 4 visits) were used at every
  budget, not re-tuned. These fights are the combat plan's stage-3 test set. No training data was recorded.

## Decision

- **MB_HELPS_AT_HIGH_BUDGET (gsh16+flat64000+mb4)** and **MORE_SIMS_HELP_WITH_MB (gsh16+flat64000+mb4)**.
- No default change. Which arm becomes the combat net's teacher target is Philipp's call (PREREG). The candidates are
  g16mb (3.3× production's CPU), g32mb (6.5×) and g64mb (12.8×). The Gumbel tuning experiment (separate plan) uses
  g16mb as its control.
- Seeds: none new (§694's external run seeds, §770's copy seeds).
- Cost: 304 lane-hours on 14 workers.
