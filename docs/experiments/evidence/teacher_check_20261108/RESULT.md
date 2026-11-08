# Teacher check on Baalorlord's elite and boss states: result

Pre-registration: [PREREG.md](PREREG.md). Analysis: `analyze.py` as frozen, output `results/analysis.json`.
Combat plan stage 1 ([plan](https://claude.ai/artifact/HvTqKL592wjb21Zgb3Sho4)).

## Run

- Run commit 75604d31 (code a51a2ed2, binary 44d6d0c9). 14 workers × 4 lanes, 2026-11-08 01:49-08:20 CET (first and
  last upload). Unit wall time sums to 132 lane-hours (median 7.9 min, longest unit 4.9 h).
- Container reset waves at about 03:25 and 05:25 CET killed some lanes. Their claims were re-claimed after the lease
  and run again from scratch: one unit needed three attempts. No unit was dropped.
- `verify_campaign.py`: 329 of 329 units OK, 0 missing, 0 bad, 0 duplicates, all tars from run 75604d31. 13 of 14
  worker DONE.json files were present at analysis time (W7 ran the last unit).
- Unit tally by rc (the PREREG selection): 329 rc 0, 0 rc 124, 0 rc 9x, 0 missing. Nothing was excluded, so
  `analyze.py` ran on all 329 units.
- `analyze.py`: 1,878 act-1-3 elite and boss fights from 309 runs, 0 dropped (the other 20 units have no elite or boss
  fight inside the exact-replay prefix).

## Primary (HP lost per fight, arm − production, 98.75% run-clustered bootstrap CI)

Production loses 11.60 HP per fight on these states. Baalorlord lost 8.74, so production − expert is +2.86 [2.17,
3.56] (95%).

| arm | HP lost | arm − prod | 98.75% CI | sims / decision | CPU ratio |
|---|---|---|---|---|---|
| production | 11.60 | | | 4,547 | 1.00 |
| rpl4 | 11.53 | −0.07 | [−0.31, +0.17] | 4,559 | 3.36 |
| flat4000 | 11.81 | +0.22 | [−0.05, +0.48] | 4,000 | 0.84 |
| gsh16+flat4000 | 11.44 | −0.15 | [−0.45, +0.14] | 3,678 | 0.78 |
| **gsh16+flat16000** | **10.71** | **−0.88** | **[−1.20, −0.57]** | 14,733 | 3.15 |

Deaths per fight 5.5% for production; no arm differs (largest: gsh16+flat16000 −0.32 pp, 98.75% CI [−0.9, +0.2]). Potions per
fight 0.555 for production, 0.546 for gsh16+flat16000.

**Decision rule:** gsh16+flat16000 has hi = −0.57 < 0 → **TEACHER_FOUND**. It is also the arm with the lowest mean,
so it is the stage-2 teacher candidate. No default change (PREREG).

## Secondary (95% CIs)

- Gumbel root at equal budget, gsh16+flat4000 − flat4000: **−0.37 [−0.59, −0.15]**. The Gumbel root beats a flat
  root at 4,000 simulations, but flat4000 is itself 0.22 HP worse than production's learned stop, so at about equal
  CPU the Gumbel root is only −0.15 against production (not resolved).
- 4× budget under the Gumbel root, gsh16+flat16000 − gsh16+flat4000: **−0.73 [−0.93, −0.52]**.

## Co-reported (gsh16+flat16000 − production, 95%)

| cut | n | prod HP lost | Δ | 95% CI |
|---|---|---|---|---|
| act 1 | 998 | 12.11 | −0.43 | [−0.68, −0.18] |
| act 2 | 536 | 12.44 | −1.23 | [−1.68, −0.77] |
| act 3 | 344 | 8.79 | −1.65 | [−2.52, −0.85] |
| elites | 1,350 | 10.19 | −0.62 | [−0.86, −0.38] |
| bosses | 528 | 15.19 | −1.54 | [−2.14, −0.99] |
| 1E / 1B | 744 / 254 | 11.24 / 14.65 | −0.28 / −0.87 | [−0.52, −0.05] / [−1.56, −0.18] |
| 2E / 2B | 397 / 139 | 10.40 / 18.24 | −0.77 / −2.53 | [−1.23, −0.31] / [−3.63, −1.41] |
| 3E / 3B | 209 / 135 | 6.02 / 13.07 | −1.56 / −1.80 | [−2.46, −0.67] / [−3.31, −0.40] |

Every encounter with n ≥ 20 has a negative point estimate. The largest are Automaton −3.73 [−5.71, −1.83] (n 44),
Champ −2.56, Awakened One −2.55, Donu and Deca −1.90, Reptomancer −1.86 and Nemesis −1.66; the smallest are Lagavulin
−0.09 and Gremlin Nob −0.34. All cuts are in `results/analysis.json`.

The other arms: rpl4 is null everywhere at 3.4× CPU (as §479). flat4000 is worse than production on bosses, +0.76
[+0.23, +1.30]: the learned stop spends more than 4,000 simulations where it matters. gsh16+flat4000 is −0.94 [−1.71,
−0.23] in act 3 and null in acts 1-2.

## Interpretation

- A better teacher than production exists on these states: a Gumbel root (Gumbel-top-16 over the g7f_E prior,
  sequential halving) with 16,000 simulations. It gains 0.88 HP per elite or boss fight, 1.5 HP per boss fight, at
  3.15× production's CPU. That closes about 31% of the 2.86-HP gap to Baalorlord.
- Budget alone did not do this before. §718 found flat 40k on Baalorlord's 499 boss states −0.25 [−1.10, +0.61] at
  7.7× CPU, and §716 found act-2 elites not budget-limited (flat 10k / 100k +0.0 / +0.1). Here a 4× budget is
  −0.73 under the Gumbel root, against −0.37 for the Gumbel root itself at equal budget. So the Gumbel root seems to
  be what turns extra simulations into better play (Inference: flat 16k without the Gumbel root was not run, so the
  split between root rule and budget is not measured directly).
- For stage 2 this means the combat net can learn more than a copy of production: targets from gsh16+flat16000 are
  better than production's own. Its root policy target (visit counts after sequential halving, or the completed-Q
  policy of Danihelka et al.) needs a choice before stage-2 data generation.
- Caveats: exploratory on states used before (§711/§716/§718); the main line is production's, so later fights follow
  production's earlier fights; one fixed setting (k 16, c_visit 50, c_scale 1, min-max q) was tested, not tuned. A
  whole-run A/B of a Gumbel-root combat needs its own pre-registration and Philipp's go (about 3× combat CPU).
