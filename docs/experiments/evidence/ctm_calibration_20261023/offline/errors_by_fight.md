# CTM errors by fight type

The 97,561 real fights of the stage-3 A/B (2026-10-23). Errors are predicted minus real.

- A positive death error means too many predicted deaths. A positive HP error means too much predicted HP loss.
- HP loss is the mean over won fights, net of Burning Blood and other healing (hence near 0 in hallways). The Heart ends the run, so it has no HP loss.
- The CTM columns cover all fights: nothing was fitted to them.
- The adjusted columns are out of sample. The odd seeds are scored with the adjustment fitted on the even seeds, and the even seeds with the one fitted on the odd seeds.
- Single encounters are noisy. The real death rate of one encounter differs between the two halves by up to 5 pp (Hexaghost 6.9% against 12.0%), so an adjusted error of a few pp at one encounter is noise level.

## By act and room

| fights | n | real death rate | CTM error (pp) | adjusted error (pp), odd / even seeds | real HP loss | CTM error (HP) | adjusted error (HP), odd / even seeds |
|---|---|---|---|---|---|---|---|
| all fights | 97,561 | 3.2% | +0.6 | -0.0 / +0.0 | 6.1 | +1.9 | -0.3 / +0.1 |
| Act 1 hallway | 24,509 | 0.2% | -0.0 | +0.0 / -0.0 | 0.4 | -0.6 | -0.3 / -0.2 |
| Act 1 elites | 9,999 | 1.2% | +0.5 | -0.2 / +0.3 | 12.6 | -0.5 | -0.2 / -0.8 |
| Act 1 bosses | 3,926 | 6.3% | +3.5 | +1.8 / -2.0 | 18.7 | +3.6 | +1.0 / -0.5 |
| Act 1 event fights | 451 | 2.0% | -0.5 | -1.7 / +3.2 | 7.4 | -2.5 | -0.7 / -0.9 |
| Act 2 hallway | 18,426 | 1.0% | +0.1 | +0.1 / -0.0 | 2.7 | +0.5 | -0.4 / +0.1 |
| Act 2 elites | 7,250 | 4.3% | -0.8 | -1.1 / +1.2 | 11.5 | +0.8 | -0.6 / +0.8 |
| Act 2 bosses | 3,154 | 15.3% | +1.2 | +0.8 / -0.9 | 23.9 | +8.9 | -0.2 / +1.2 |
| Act 2 event fights | 840 | 3.3% | -0.8 | -1.0 / +0.7 | 4.0 | -0.8 | +1.2 / -1.8 |
| Act 3 hallway | 13,948 | 0.8% | +0.1 | -0.1 / +0.1 | 0.3 | +2.3 | -0.5 / +0.2 |
| Act 3 elites | 6,119 | 4.2% | +0.8 | -0.4 / +0.5 | 7.2 | +8.2 | +0.0 / +1.0 |
| Act 3 bosses | 4,321 | 14.2% | +3.9 | -0.0 / -0.0 | 13.8 | +19.3 | -0.5 / +1.3 |
| Act 3 event fights | 1,365 | 1.8% | -0.8 | -1.5 / +1.0 | 4.0 | +2.6 | +0.6 / +1.7 |
| Act 4 elites | 1,668 | 5.0% | +2.8 | +0.1 / -0.1 | 22.4 | +2.7 | -0.8 / -1.6 |
| Act 4 bosses | 1,585 | 38.9% | +10.6 | +2.1 / -2.1 | – | – | – |

## Elites and bosses with their own correction

| fights | n | real death rate | CTM error (pp) | adjusted error (pp), odd / even seeds | real HP loss | CTM error (HP) | adjusted error (HP), odd / even seeds |
|---|---|---|---|---|---|---|---|
| Gremlin Nob (A1) | 3,314 | 1.3% | +0.5 | -0.5 / +0.5 | 11.7 | -1.6 | -0.2 / -1.2 |
| Hexaghost (A1) | 1,399 | 9.4% | +5.8 | +4.4 / -4.6 | 23.5 | +4.2 | +1.6 / -0.1 |
| Lagavulin (A1) | 3,329 | 1.2% | +0.5 | -0.4 / +0.5 | 13.2 | +0.4 | -0.0 / -0.3 |
| Slime Boss (A1) | 1,194 | 5.4% | +1.0 | +0.2 / -0.7 | 12.9 | +0.5 | +1.4 / -2.1 |
| The Guardian (A1) | 1,333 | 3.9% | +3.3 | +0.5 / -0.4 | 18.9 | +5.7 | -0.0 / +0.8 |
| Three Sentries (A1) | 3,356 | 1.1% | +0.5 | +0.2 / -0.2 | 12.9 | -0.4 | -0.4 / -0.7 |
| Automaton (A2) | 1,009 | 16.4% | -0.5 | -0.6 / +0.4 | 26.5 | +9.5 | -1.4 / +2.2 |
| Book of Stabbing (A2) | 2,369 | 3.7% | +0.8 | +0.1 / +0.1 | 12.1 | +3.5 | -1.1 / +1.3 |
| Champ (A2) | 1,032 | 11.0% | +2.9 | +1.3 / -1.1 | 20.1 | +12.3 | -1.5 / +2.2 |
| Collector (A2) | 1,113 | 18.3% | +1.3 | +1.7 / -1.8 | 25.2 | +4.8 | +2.2 / -0.9 |
| Gremlin Leader (A2) | 2,415 | 4.6% | -1.8 | -2.2 / +1.9 | 9.0 | +0.1 | -0.9 / +0.8 |
| Slavers (A2) | 2,466 | 4.7% | -1.2 | -1.3 / +1.4 | 13.3 | -1.0 | +0.1 / +0.3 |
| Awakened One (A3) | 1,446 | 22.4% | -6.1 | +0.5 / -1.2 | 19.7 | +9.3 | +0.1 / +1.3 |
| Donu and Deca (A3) | 1,386 | 9.9% | +6.5 | -2.3 / +2.2 | 10.3 | +22.6 | -2.3 / +2.2 |
| Giant Head (A3) | 1,981 | 3.5% | +4.6 | -0.3 / +0.7 | 3.9 | +13.6 | +0.7 / +0.9 |
| Nemesis (A3) | 2,008 | 1.9% | +1.4 | +0.1 / +0.1 | 6.9 | +8.8 | -0.1 / +1.1 |
| Reptomancer (A3) | 2,130 | 6.9% | -3.3 | -1.1 / +0.6 | 10.6 | +2.4 | -0.5 / +1.0 |
| Time Eater (A3) | 1,489 | 10.3% | +11.3 | +1.5 / -1.1 | 12.0 | +24.5 | +0.6 / +0.4 |
| Shield and Spear (A4) | 1,668 | 5.0% | +2.8 | +0.1 / -0.1 | 22.4 | +2.7 | -0.8 / -1.6 |
| The Heart (A4) | 1,585 | 38.9% | +10.6 | +2.1 / -2.1 | – | – | – |

Per-fight precision, the mean absolute error of the HP after a won fight over all fights: CTM 8.46 HP, adjusted 7.66 HP (odd seeds); 8.48 → 7.67 (even seeds).

Source: `docs/experiments/evidence/ctm_calibration_20261023/offline/eval_fit_even_on_odd.json` and `eval_fit_odd_on_even.json`.
