# Traced replay of the §775 whole-run Gumbel test, arms D and G16: result

Descriptive, no gate, no default change ([PREREG](PREREG.md), frozen with `analyze.py` at b5464a79). The follow-ups in
part B (`explore.py`) were written after the data were seen, and they are labeled that way.

## Run

- 271 units on 40 cloud workers, 2026-11-10 05:40-07:55 CET. All 271 claims were first attempts. `verify_campaign.py`
  reports 271/271 units OK, 0 missing, 0 bad, 0 duplicates, run b5464a79, and 40/40 `DONE.json` files
  (`results/verify.txt`, `results/claims.txt`).
- Binary 0eabb014 (code 5665d5ae), net-0420, §775's environment plus `STS_OOC_DECISION_TRACE`.
- 224.9 lane-hours: D 74.2, G16 150.7 (§775: 72 + 146).
- **Validity:** 2,048/2,048 games reproduce §775 (rc 0, BEST line, `[heart1_ppo]` line, and G16's Gumbel roots/sims
  line), so the verdict is **REPRO_OK**. 0 games fail to reproduce, 0 seeds are missing and 0 combat aborts occurred.
  The traces therefore describe exactly §775's games: Heart kills D 324/1,024 = 31.64%, G16 422/1,024 = 41.21%.

## A. Pre-registered tables (`analyze.py`, `results/result.json`)

Seed-cluster bootstrap with 10,000 resamples, 95% intervals. "HP saved" = D minus G16 in HP lost per won fight. Post
HP includes the heals that follow a fight (see the caveats).

| Fight class | Fights D / G16 | Deaths % D / G16 | G16 − D deaths, pp | HP lost per won fight, D / G16 | HP saved by G16 | Potions saved per fight |
|---|---|---|---|---|---|---|
| A1 normal | 5,964 / 5,977 | 0.54 / 0.37 | −0.17 [−0.35, +0.02] | 0.36 / 0.05 | +0.31 [+0.21, +0.41] | +0.012 [+0.006, +0.018] |
| A2 normal | 4,021 / 4,267 | 1.29 / 1.15 | −0.14 [−0.50, +0.22] | 2.09 / 1.65 | +0.44 [+0.14, +0.76] | +0.024 [+0.009, +0.039] |
| A3 normal | 2,872 / 3,424 | 0.56 / 0.32 | −0.24 [−0.55, +0.07] | −0.43 / −1.06 | +0.63 [+0.17, +1.08] | +0.011 [−0.006, +0.028] |
| A1 elite | 2,648 / 2,706 | 3.36 / 2.62 | **−0.74 [−1.44, −0.01]** | 13.80 / 13.08 | +0.72 [+0.34, +1.09] | +0.009 [−0.008, +0.026] |
| A2 elite | 1,756 / 1,897 | 5.52 / 4.01 | **−1.52 [−2.72, −0.33]** | 11.10 / 9.64 | +1.46 [+0.66, +2.27] | −0.028 [−0.060, +0.004] |
| A3 elite | 1,417 / 1,696 | 2.96 / 2.42 | −0.55 [−1.62, +0.50] | 3.74 / 3.66 | +0.08 [−0.87, +1.02] | +0.008 [−0.029, +0.044] |
| A1 boss | 898 / 928 | 11.25 / 9.59 | −1.66 [−3.73, +0.40] | 18.12 / 18.71 | −0.59 [−1.69, +0.49] | +0.089 [+0.044, +0.135] |
| A2 boss | 642 / 710 | 13.55 / 8.87 | **−4.68 [−7.45, −1.96]** | 16.80 / 16.68 | +0.11 [−1.74, +1.98] | −0.048 [−0.110, +0.013] |
| A3 bosses (both) | 950 / 1,131 | 7.16 / 7.34 | +0.18 [−1.85, +2.22] | 0.54 / 0.86 | −0.32 [−1.14, +0.51] | +0.015 [−0.028, +0.058] |
| Shield and Spear | 416 / 497 | 1.92 / 0.40 | **−1.52 [−3.01, −0.18]** | 11.39 / 10.88 | +0.51 [−1.68, +2.73] | +0.024 [−0.064, +0.113] |
| Heart | 408 / 495 | 20.59 / 14.75 | **−5.84 [−10.31, −1.32]** | 41.10 / 49.63 | −8.52 [−12.21, −4.87] | −0.047 [−0.139, +0.046] |

There were no Smoke Bomb escapes in either arm. Turns per fight are equal within ±0.1, except at the Heart, where
G16 takes +0.84 turns [+0.60, +1.09].

**State at boss entry** (runs that reach the fight): G16 enters every boss with more HP. The difference is +1.53
[+0.76, +2.31] at the Act 1 boss, +1.83 [+0.53, +3.16] at the Act 2 boss, +2.25 [+0.20, +4.30] and +2.25
[−0.23, +4.75] at the two Act 3 bosses, +2.05 [+0.36, +3.82] at Shield and Spear, and +2.31 [−0.46, +5.03] at the
Heart. That is 0.2 to 1.9 points of HP fraction. Potions held differ by −0.004 to +0.064 and deck size by −0.3 to
+0.04 cards, so both are about equal.

**First divergence** (paired, from identical states): 1,017 seeds diverge, almost all in Act 1. At a normal fight
(n 735), G16 ends with +1.20 HP [+0.86, +1.54] and the same deaths. At an elite (n 272), it ends with +1.35 HP
[+0.24, +2.48] and −0.74 pp deaths. The other classes have n ≤ 4.

**Where the losing arm died on discordant seeds.** On 171 seeds only G16 killed the Heart, and on 73 only D did.
The net column below sums to G16's +98 kills.

| Fight that ended the run | D lost, G16 won | G16 lost, D won | Net |
|---|---|---|---|
| Act 1 normal / elite / boss / other | 6 / 16 / 13 / 1 | 1 / 6 / 9 / 0 | +5 / +10 / +4 / +1 |
| Act 2 normal / elite / boss | 8 / 27 / 19 | 3 / 6 / 7 | +5 / +21 / +12 |
| Act 3 normal / elite / bosses / other | 2 / 13 / 24 / 4 | 0 / 6 / 11 / 1 | +2 / +7 / +13 / +3 |
| Shield and Spear / Heart | 2 / 35 | 0 / 22 | +2 / +13 |
| Ended alive without a death fight | 1 | 1 | 0 |

By room type, the net is elites +38, Act 1-3 bosses +29, Act 4 +15, normal fights +12 and other fights +4. By act,
it is Act 1 +20, Act 2 +38, Act 3 +25 and Act 4 +15.

**Most frequent death causes:** D: Heart 84, Hexaghost 44, Slavers 42, Awakened One 41, Gremlin Nob 38. G16: Heart
73, Awakened One 56, Hexaghost 44, Gremlin Leader 30, Gremlin Nob 28.

## B. Exploratory follow-ups (`explore.py`, `results/explore.json`, written after the data)

**Funnel** (runs that reach / win each stage):

| Stage | D | G16 |
|---|---|---|
| Act 1 boss | 898 / 797 | 928 / 839 |
| Act 2 boss | 642 / 555 | 710 / 647 |
| Act 3 boss 1 | 489 / 461 | 587 / 544 |
| Act 3 boss 2 | 461 / 421 | 544 / 504 |
| Shield and Spear | 416 / 408 | 497 / 495 |
| Heart | 408 / 324 (79.4%) | 495 / 422 (85.3%) |

**Split of the +98 Heart kills:** 69.1 come from reaching the Heart more often (495 vs 408 arrivals, counted at D's
79.4%), and 28.9 come from winning more of the Heart fights (85.3% vs 79.4%).

**Entry HP explains little of the boss gains.** Within D, the least-squares slope of death on entry HP at each
stage, times G16's entry-HP shift, gives the predicted change. The bootstrap uses 5,000 resamples.

| Stage | Slope in D, pp per HP | Predicted from entry HP, pp | Observed G16 − D, pp |
|---|---|---|---|
| Act 1 boss | −0.35 | −0.54 [−0.95, −0.22] | −1.66 [−3.70, +0.40] |
| Act 2 boss | −0.51 | −0.93 [−1.78, −0.24] | −4.68 [−7.41, −2.03] |
| Act 3 boss 1 | −0.24 | −0.54 [−1.27, −0.04] | +1.60 [−1.22, +4.31] |
| Act 3 boss 2 | −0.38 | −0.85 [−2.05, +0.08] | −1.32 [−4.43, +1.63] |
| Shield and Spear | −0.04 | −0.09 [−0.29, +0.01] | −1.52 [−3.02, −0.13] |
| Heart | −0.45 | −1.04 [−2.50, +0.18] | −5.84 [−10.45, −1.35] |

**Boss deaths per encounter, D vs G16:**

| Encounter | D | G16 |
|---|---|---|
| Automaton | 14.3% (30/210) | 8.2% (19/231) |
| Collector | 15.1% (31/205) | 9.3% (21/225) |
| Slime Boss | 10.9% (32/293) | 7.2% (22/305) |
| Heart | 20.6% (84/408) | 14.7% (73/495) |
| Champ | 11.5% | 9.1% |
| Guardian | 7.8% | 7.0% |
| Hexaghost | 15.4% (44/285) | 15.0% (44/294) |
| Time Eater | 4.0% | 3.3% |
| Donu and Deca | 4.7% | 4.0% |
| Awakened One | 12.4% (41/330) | 14.2% (56/393) |

**Per run, Acts 1-3, at D's fight counts** (per-fight saving times D's fights per run):

| Fight type | Fights per run | HP saved per run | Potions saved per run |
|---|---|---|---|
| Normal | 12.6 | 5.24 | 0.195 |
| Elite | 5.7 | 4.27 | −0.013 |
| Boss | 2.4 | −0.67 | 0.062 |

The boss figure is mostly selection: G16 wins harder boss fights, and those cost more HP.

`results/battles.csv.gz` holds one row per traced fight: 46,932 fights over both arms and all seeds, with pre and post
HP, max HP, potions, deck size and gold. It serves later analyses without the share tars.

## Readings

- **Is G16's advantage per fight larger in normal fights?** No. Per fight it is small in normal fights: +0.3 to +0.6
  HP, and −0.1 to −0.2 pp deaths with intervals that include 0. It is larger in Act 1-2 elites (+0.7 / +1.5 HP,
  −0.7 / −1.5 pp deaths), at the Act 2 boss (−4.7 pp) and at the Heart (−5.8 pp).
  - Over a run, though, the 12.6 normal fights add up to about 5.2 HP and 0.2 potions. That is as much HP as the 5.7
    elites (4.3 HP).
  - An HP proxy measured only on elite and boss fights (§770, §772, §774) therefore misses about half of G16's HP
    saving per run.
  - Normal fights end few runs, though: they are the last fight on only 12 of the 98 net seeds.
- **Does the Heart gain come from search or from a better entry state?** Mostly from search inside the fights.
  - G16 enters each boss with about 2 HP more, with the same potions and deck size. D's own HP-death slope turns
    that into about −0.5 to −1.0 pp per boss.
  - The observed drops are −4.7 pp at the Act 2 boss and −5.8 pp at the Heart.
  - About 70% of the +98 Heart kills come from reaching the Heart more often. Elites (+38 net) and Act 1-3 bosses
    (+29) are the main places where D's runs end and G16's continue. The remaining 30% comes from winning more Heart
    fights.
- **Where G16 does not help:** Awakened One (14.2% deaths vs 12.4%; Act 3 boss 1 overall +1.6 pp [−1.2, +4.3]) and
  Hexaghost (15.0% vs 15.4%). Both are now the largest single death causes after the Heart.

## Caveats

- **Per-class rates compare different state distributions.** G16's later fights include runs that D had already
  lost. Only the first-divergence rows are paired.
- **HP lost per won fight is conditional on winning.** G16 wins more of the hard Heart fights and loses more HP in
  them (49.6 vs 41.1 per won Heart).
- **Post HP includes the heals that follow a fight.** One example is Burning Blood. At the Act 3 bosses it evidently
  also includes the heals between and after the two bosses: floor 51 averages −8.2 HP "lost", and 33-43% of Act 3
  boss wins end at full HP. The Act 3 boss HP rows are therefore not in-fight HP. Death rates are not affected.
- **The slope prediction is rough.** It is a linear, within-arm slope on observational data. It is a scale check,
  not a causal estimate.
- Part B was written after the data were seen.

Data: on the share, `/mnt/project-files/gumbel-wholerun-trace/units/` holds 271 tars (29 MB) with the full traces.
In the repo, `results/` holds `result.json`, `explore.json`, `battles.csv.gz`, `claims.txt` and `verify.txt`.
