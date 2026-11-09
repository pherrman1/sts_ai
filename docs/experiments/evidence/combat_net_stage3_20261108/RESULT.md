# Combat net stage 3a: the net's policy as Silver's root prior (result)

Pre-registration: [PREREG.md](PREREG.md) with Amendment 1. Analysis: `analyze.py` as frozen, output
`results/analysis.json`. Combat plan stage 3 ([plan](https://claude.ai/artifact/HvTqKL592wjb21Zgb3Sho4)).

## Run

- Run commit f104e139 (code 4d2a7f80, binary 4000eb83). 35 workers × 4 lanes on Philipp's count (PREREG, Amendment
  1), 2026-11-08 18:24-22:14 CET (first unit start and last unit end). Unit wall time sums to 74 lane-hours (median
  4.9 min, longest unit 2.7 h), below the 85-90 estimated.
- The project share hit its 50,000-entry limit as the campaign started, so workers W20-W35 could not claim units at
  first. After the share was cleaned up (claims of finished campaigns deleted from verified backups; three finished
  campaigns' unit dirs packed into verified `ARCHIVE-units-20261108.tar.xz`), they joined late. Units run before the
  cleanup were uploaded normally; the verification below finds every unit complete.
- `verify_campaign.py`: 329 of 329 units OK, 0 missing, 0 bad, 11 duplicates (re-claimed units; the first tar of each
  is used), 0 tars for unknown units, all tars from run f104e139. 1 of 35 worker DONE.json files was present at
  analysis time (workers were released after the verification).
- Unit tally by rc (the PREREG selection): 329 rc 0, 0 rc 124, 0 rc 9x, 0 missing. Nothing was excluded, so
  `analyze.py` ran on all 329 units.
- `analyze.py`: 1,878 act-1-3 elite and boss fights from 309 runs, 0 dropped (as §770).

## Validity

- **Production reproduces §770:** on all 1,878 fights, production's 4 copies equal §770's on won, exit HP, exit max
  HP, turns, decisions and simulations. `flat4000` also equals §770's `flat4000` arm on all 1,878 fights.
- **The net arms used the net:** 0 of 30,048 net-arm copies lack a net prior (limit 1 %). Net priors per decision:
  0.918 (cnp100), 0.919 (cnp55), 0.918 and 0.918 (flat net arms). The other decisions have one action left after
  pruning and get no root prior.
- **No leak:** production and `flat4000` have 0 net priors.
- **CPU:** cnp100 1.02 and cnp55 0.98 to production; both flat net arms 1.01 to `flat4000`. All are below 1.25, so
  every arm is judged.

## Primary (HP lost per fight, arm − production, 97.5% run-clustered bootstrap CI)

Production loses 11.60 HP per fight on these states; Baalorlord lost 8.74 (production − expert +2.86 [2.17, 3.56],
95%).

| arm | HP lost | arm − prod | 97.5% CI | sims / decision | CPU ratio |
|---|---|---|---|---|---|
| production | 11.60 | | | 4,547 | 1.00 |
| cnp100 (T = 1) | 11.53 | −0.06 | [−0.29, +0.17] | 4,585 | 1.02 |
| cnp55 (T = 0.55) | 11.49 | −0.10 | [−0.32, +0.11] | 4,562 | 0.98 |

Deaths per fight 5.5% for production and cnp100, 5.7% for cnp55 (cnp55 − prod +0.15 pp, 97.5% CI [−0.3, +0.6]).
Potions per fight 0.555, 0.563 and 0.556.

**Decision rule:** neither arm has hi < 0, both have lo > −0.5 → **NO_GAIN.** Neither arm has lo > 0, so neither is
WORSE. No default change (PREREG).

## Secondary (Amendment 1; flat net arm − `flat4000`, 97.5% CI)

| arm | HP lost | arm − flat4000 | 97.5% CI | sims / decision | CPU ratio |
|---|---|---|---|---|---|
| flat4000 | 11.81 | | | 4,000 | 1.00 |
| flat4000+cnp100 | 11.65 | −0.17 | [−0.39, +0.05] | 4,000 | 1.01 |
| flat4000+cnp55 | 11.88 | +0.07 | [−0.15, +0.30] | 4,000 | 1.01 |

**Decision rule:** neither arm has hi < 0, both have lo > −0.5 → **FLAT_NO_GAIN.** Neither is FLAT_WORSE. With both
NO_GAIN, the fixed reading applies: the net's root prior does not help on these states, with or without the learned
stop.

## Co-reported (95%, descriptive)

- `flat4000` − production: **+0.22 [+0.02, +0.42]**, as in §770 (same copies). The learned stop beats a flat 4,000
  simulations at about the same mean budget; on bosses +0.76 [+0.23, +1.30].
- cnp55 − cnp100: −0.04 [−0.23, +0.15]. `flat4000+cnp55` − `flat4000+cnp100`: +0.24 [+0.03, +0.44]: at a fixed
  budget the flatter T = 1 prior did better than T = 0.55, under the learned stop the two do not differ.

| cut | n | prod HP lost | cnp100 − prod | cnp55 − prod | flat+cnp100 − flat | flat+cnp55 − flat |
|---|---|---|---|---|---|---|
| act 1 | 998 | 12.11 | −0.03 [−0.24, +0.17] | −0.11 [−0.31, +0.09] | −0.13 [−0.34, +0.07] | +0.02 [−0.19, +0.23] |
| act 2 | 536 | 12.44 | −0.04 [−0.41, +0.34] | −0.08 [−0.43, +0.28] | −0.12 [−0.52, +0.29] | +0.28 [−0.17, +0.73] |
| act 3 | 344 | 8.79 | −0.18 [−0.91, +0.55] | −0.11 [−0.77, +0.52] | −0.33 [−1.02, +0.39] | −0.10 [−0.80, +0.60] |
| elites | 1,350 | 10.19 | −0.03 [−0.22, +0.17] | −0.08 [−0.27, +0.11] | −0.03 [−0.22, +0.15] | +0.16 [−0.04, +0.36] |
| bosses | 528 | 15.19 | −0.15 [−0.67, +0.38] | −0.15 [−0.65, +0.35] | −0.50 [−1.10, +0.09] | −0.16 [−0.71, +0.40] |

No act, room or act × room cut has a CI below 0 for any net arm. Of the 18 encounters with n ≥ 20 × 4 contrasts, two
are resolved, one each way: Book of Stabbing, cnp100 − prod −0.62 [−1.16, −0.08] (n 139), and Slavers,
`flat4000+cnp55` − `flat4000` +0.61 [+0.03, +1.23] (n 129). Of 72 CIs at 95%, about 3.6 would exclude 0 by chance.
All cuts are in `results/analysis.json`.

Context only, not paired with this run: §770's Gumbel root at 16,000 simulations gained −0.88 HP per fight at 3.15×
CPU on the same states.

## Interpretation

- The combat net's policy, as Silver's root prior at weight 400, does not change how well production plays these
  states. The point estimates are −0.06 and −0.10 HP per fight at the same simulations and CPU, and gains above
  0.29 (T = 1) and 0.32 HP (T = 0.55) are excluded at 97.5%.
- The learned stop is not what hides a gain. At a flat 4,000 simulations the net prior is also null (−0.17 [−0.39,
  +0.05] at T = 1). So the stop check that Amendment 1 named for FLAT_PRIOR_BETTER is not needed.
- The net's +1.77 pp top-1 agreement with the Gumbel teacher on the D1 holdout (§771) did not become play strength
  here. The PREREG's caveats give the candidate reasons, none tested here:
  - Only the root prior changed. With about 4,500 simulations per decision and weight 400, the prior steers early
    visits; the final choice follows the visits and Q values, which the rollouts below the root (still g7f_E) set.
  - The net learned from self-play decks and paths; Baalorlord's decks differ.
  - §770's teacher searched with the g7f_E prior too. Its gain came from the Gumbel root and the 4× budget, and a
    prior that imitates its visit shares does not bring that search along.
- The flat-budget pair also repeats §770: the learned stop is worth about 0.2 HP per fight over a flat budget of the
  same mean size, mostly on bosses.
- Caveats: exploratory on states used before (§711/§716/§718/§765/§770); the main line is production's; two
  temperatures, not tuned on these states; one net (polonly_d1).

## Decision

- No default change. `STS_SILVER_COMBATNET_PRIOR` stays default off.
- The native inference (`CombatTokNet`) and the hook stay in the code for stage 3b (leaf) and for a possible test of
  the net prior under the Gumbel root, where the prior selects the top-k candidates. Neither is pre-registered.
