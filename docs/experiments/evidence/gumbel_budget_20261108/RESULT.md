# Gumbel budget check: 32k and 64k simulations under the Gumbel root (result)

Pre-registration: [PREREG.md](PREREG.md). Analysis: `analyze.py` as frozen, output `results/analysis.json`. Follow-up
to §770 ([teacher check](../teacher_check_20261108/RESULT.md)).

## Run

- Run commit 695624d8 (code d430d406, binary 3e801097). 40 workers × 4 lanes. The first unit started at 13:43 CET, the
  first tar was uploaded at 14:09 CET, and the last at 19:58 CET on 2026-11-08. Unit wall time sums to 425 lane-hours
  (projected 450). The median unit took 7.3 min and the longest 6.3 h (an act-3 g64 unit).
- Every unit finished on its first attempt (1,728 claims, all `.a1`). No container reset killed a unit and nothing
  was re-claimed, so the last-wins rule for re-attempt tars (review note N2) never applied.
- Idle workers were released while the 8 longest units were still running. Only W1-W4 wrote a `DONE.json`; the other
  36 were released idle after their last upload.
- One upload of `1680728310_3_g64` (W2) was not visible on the share for about 40 minutes, although the worker's cmp
  had passed. The share was at its file limit at the time. W2 copied its local tar again, unchanged and not rerun
  (sha256 37aa0871…), and it then appeared.
- `verify_campaign.py`: 1,728 of 1,728 units OK, 0 extra tars, all from run 695624d8.
- Unit tally by rc (the PREREG selection): 1,728 rc 0, 0 rc != 0, 0 missing. §770's 329 units are all rc 0 as well.
  Nothing was excluded.
- `analyze.py`: 1,878 act-1-3 elite and boss fights from 309 runs, **0 dropped** (no `missing_side` in any arm set;
  review note N4). Production played the main line in all three arm sets with 0 conflicts between them (N1).

## Reproduction (gate for the pairing with g16)

Production here equals §770's production in all 4 copies of **1,878 of 1,878 fights (100%)**. That covers won, exit
HP, exit max HP, turns, decisions, simulations and potions. The gate is ≥ 99%, so the g16 contrasts are paired.

## Primary (HP lost per fight, arm − g16, 97.5% run-clustered bootstrap CI)

Production loses 11.60 HP per fight on these states, g16 (gsh16+flat16000, from §770) 10.71, Baalorlord 8.74.

| arm | HP lost | arm − g16 | 97.5% CI | arm − prod (95%) | sims / decision | CPU ratio |
|---|---|---|---|---|---|---|
| production | 11.60 | | | | 4,547 | 1.00 |
| flat16000 | 11.50 | +0.79 | (95%) [+0.57, +1.02] | −0.09 [−0.27, +0.09] | 16,000 | 3.52 |
| g16 = gsh16+flat16000 | 10.71 | | | −0.88 [−1.13, −0.64] | 14,733 | 3.15 |
| **gsh16+flat32000** | **10.47** | **−0.24** | **[−0.46, −0.02]** | −1.13 [−1.39, −0.86] | 29,447 | 6.71 |
| **gsh16+flat64000** | **10.35** | **−0.37** | **[−0.57, −0.16]** | −1.25 [−1.50, −1.01] | 59,003 | 13.51 |

The CPU ratio of g16 is against §770's production. Those units ran on other machines, so ratios across the two
campaigns mix machines (PREREG caveat).

Deaths per fight: production 5.5%, g16 5.2%, g32 4.9%, g64 4.7%. g64 − g16 is −0.49 pp, 95% CI [−0.9, −0.1].
g32 − g16 is −0.32 pp [−0.7, 0.0]. Potions per fight are 0.541-0.556 in every budget arm.

**Decision rule:** both arms have hi < 0. g64 has the lower mean → **MORE_SIMS_HELP (gsh16+flat64000)**. Whether the
gain is worth its CPU is Philipp's call (PREREG). No default change.

## Max backup (separate contrast, 95%)

| arm | HP lost | arm − g16 | 95% CI | deaths | potions | CPU ratio |
|---|---|---|---|---|---|---|
| gsh16+flat16000+mb4 | 10.43 | **−0.29** | **[−0.49, −0.09]** | 4.8% (−0.37 pp [−0.8, 0.0]) | 0.520 | 3.32 |

hi < 0 → **MAX_BACKUP_HELPS**. Max backup with min 4 visits under the Gumbel root at 16k gains as much as doubling the
budget to 32k (−0.24). It costs only 5% more CPU than g16, against 2.1× for 32k. It also uses fewer potions (0.520 vs
0.546).

## Secondary (95% CIs)

- Gumbel root at equal budget, flat16000 − g16: **+0.79 [+0.57, +1.02]**. The flat root at 16k is not better than
  production (−0.09 [−0.27, +0.09]). Production's learned stop already spends its budget where it matters, so
  §770's 16k gain comes from the Gumbel root rule together with the budget. Budget alone does not give it.
- gsh16+flat64000 − gsh16+flat32000: −0.12 [−0.33, +0.08]. The step from 32k to 64k is not resolved.
- Share of the production − Baalorlord gap (2.86 HP, 95% CI [2.17, 3.56]) closed, as point estimates: g16 31%, g32
  39%, mb4 41%, g64 44%.

## Co-reported by cut (95% CIs)

| cut | n | prod HP lost | g32 − g16 | g64 − g16 | mb4 − g16 | flat16k − prod |
|---|---|---|---|---|---|---|
| act 1 | 998 | 12.11 | −0.37 [−0.60, −0.14] | −0.39 [−0.63, −0.15] | −0.21 [−0.46, +0.04] | −0.21 [−0.41, −0.01] |
| act 2 | 536 | 12.44 | +0.06 [−0.33, +0.44] | −0.11 [−0.49, +0.27] | −0.30 [−0.72, +0.15] | +0.07 [−0.30, +0.44] |
| act 3 | 344 | 8.79 | −0.34 [−0.97, +0.29] | −0.70 [−1.26, −0.15] | −0.47 [−1.14, +0.18] | −0.01 [−0.54, +0.53] |
| elites | 1,350 | 10.19 | −0.27 [−0.48, −0.07] | −0.37 [−0.58, −0.17] | **−0.44 [−0.65, −0.23]** | −0.04 [−0.23, +0.15] |
| bosses | 528 | 15.19 | −0.17 [−0.68, +0.33] | −0.36 [−0.83, +0.12] | +0.11 [−0.42, +0.66] | −0.22 [−0.72, +0.29] |
| 1E / 1B | 744 / 254 | 11.24 / 14.65 | −0.37 / −0.39 | −0.35 / −0.49 | −0.20 / −0.27 | −0.10 / −0.52 |
| 2E / 2B | 397 / 139 | 10.40 / 18.24 | −0.08 / +0.46 | −0.09 / −0.17 | −0.51 / +0.30 | +0.22 / −0.34 |
| 3E / 3B | 209 / 135 | 6.02 / 13.07 | −0.30 / −0.41 | −0.96 / −0.31 | −1.18 / +0.63 | −0.31 / +0.46 |

- Max backup's gain is in elite fights (−0.44 [−0.65, −0.23]). On bosses it is +0.11 [−0.42, +0.66], not resolved.
  Elite − boss difference: not tested.
- More budget helps elites and bosses alike as point estimates, but only the elite cut resolves.
- CPU ratios of g64 run from 12.1× (act 3) to 16.2× (act 1). mb4 runs from 3.1× to 3.8×.

By encounter (n ≥ 20; all have wide CIs), g64 − g16:
- Largest gains: Collector −1.81 [−3.65, +0.04], Giant Head −1.31 [−2.38, −0.19], Reptomancer −1.20, Time Eater −1.11,
  Lagavulin −0.47 [−0.90, −0.04].
- Positive: Automaton +1.22 [−0.49, +2.96], Champ +0.57, Awakened One +0.34, Gremlin Leader +0.10.

mb4 − g16 by encounter:
- Largest gains: Giant Head −1.41 [−2.59, −0.20], Reptomancer −1.17, Nemesis −0.96, Slavers −0.82 [−1.47, −0.18],
  3 Sentries −0.54 [−0.95, −0.11].
- Positive: Donu and Deca +1.09, Time Eater +0.58, Collector +0.50.

All cuts are in `results/analysis.json`.

## Interpretation (Inference)

- The Gumbel root keeps gaining past 16k, with diminishing returns per CPU:
  - 32k gains −0.24 for 2.1× g16's CPU.
  - 64k gains −0.37 for 4.3×.
  - The step from 32k to 64k (−0.12) is not resolved.
- Max backup at 16k gets the 32k gain at about g16's cost. It is the cheapest improvement found here.
- Max backup combined with 32k or 64k was not run, so whether the two gains add up is unknown.
- §762 found max backup NOT_SHOWN in whole runs at about 1,000 simulations with the plain root. This is a different
  regime: a high budget, the Gumbel root, and elite and boss fights only. Its gain sits in elites, not bosses.
- The flat-16k control settles §770's open question: the budget alone does not help. With a flat root, 16k
  simulations are no better than production's learned stop at 4.5k.
- Exploratory: these states were used before (§711/§716/§718/§770), the main line is production's, and one Gumbel
  setting (k 16, c_visit 50, c_scale 1) was used at every budget, not re-tuned.
- These fights are the combat plan's stage-3 test set. No training data was recorded.

## Decision

- **MORE_SIMS_HELP (gsh16+flat64000)** and **MAX_BACKUP_HELPS**.
- No default change.
- Candidates for a better stage-2/3 teacher target are gsh16+flat16000+mb4 (same cost as g16) and
  gsh16+flat32000/64000. Choosing one, or testing mb4 combined with a larger budget, is Philipp's call.
- Seeds: none new (§694's external run seeds, §770's copy seeds).
- Cost: 425 lane-hours.
