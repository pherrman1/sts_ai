# Matched expert-entry fight replay: result (§TBD)

Campaign `expert-fight-replay`, frozen per `PREREG.md` and `campaign.manifest` (run commit `11b496b3`, code
`748eb3eb`, binary `d7af0395…`), 4 cloud workers, 2026-10-28 16:15-17:55Z. `verify_campaign.py`: 329/329 units OK,
none missing, bad or duplicated, one run commit; every unit rc 0. Analysis: `analyze.py` → `result.json`.

## Primary (acts 1-2 elites and bosses)

| | n fights (runs) | bot HP lost | expert HP lost | bot − expert, 95% CI |
|---|---|---|---|---|
| all 4 copies | 1,492 (308) | 12.38 | 9.75 | **+2.63 [+1.99, +3.29]** |
| copy 0 (expert's deal) | 1,492 | | | +2.39 [+1.64, +3.13] |

Pre-registered rule (lower bound > +2 → COMBAT_GAP; upper < +2 → NO_COMBAT_GAP): **INCONCLUSIVE**. The lower bound
misses the +2 margin by 0.01 HP; the CI excludes 0, so the bot does lose more HP than Baalorlord on his own states,
by about 2-3 HP per fight. Co-reported potions: bot 0.62 vs expert 0.54 per fight, +0.08 [+0.04, +0.11]. Death per
fight 0.059 vs 0.031, +0.03 [+0.02, +0.04]. No fight was dropped.

## By act and room (bot − expert HP lost, 95% CI; potions per fight bot vs expert)

| | n | bot | expert | diff | potions | deaths |
|---|---|---|---|---|---|---|
| act-1 hallway | 1,400 | 1.37 | 1.14 | +0.22 [−0.07, +0.51] | 0.12 / 0.08 | 0.005 / 0.004 |
| act-1 elite | 739 | 11.23 | 10.04 | +1.20 [+0.43, +1.96] | 0.62 / 0.59 | 0.031 / 0.015 |
| act-1 boss | 250 | 14.59 | 12.89 | +1.70 [+0.30, +3.13] | 0.89 / 0.47 | 0.125 / 0.064 |
| act-2 hallway | 958 | 3.82 | 1.81 | +2.01 [+1.48, +2.55] | 0.19 / 0.24 | 0.011 / 0.005 |
| act-2 elite | 375 | 11.00 | 5.56 | **+5.44 [+4.08, +6.83]** | 0.41 / 0.53 | 0.055 / 0.027 |
| act-2 boss | 128 | 18.67 | 14.21 | +4.46 [+1.56, +7.43] | 0.66 / 0.44 | 0.107 / 0.070 |
| act-3 hallway | 393 | 0.49 | −1.63 | +2.12 [+1.31, +2.96] | 0.10 / 0.12 | 0 / 0 |
| act-3 elite | 190 | 6.26 | 2.75 | +3.51 [+1.39, +5.60] | 0.23 / 0.28 | 0.016 / 0.005 |
| act-3 boss* | 121 | 13.07 | 7.90 | +5.17 [+2.07, +8.29] | 0.33 / 0.06 | 0.070 / 0.008 |

By encounter (elites/bosses, n ≥ 36): Slavers +7.0, Automaton +9.8, Awakened One +10.7, Book of Stabbing +4.8,
Gremlin Leader +4.6, Champ +4.9, Nemesis +4.3, The Guardian +4.3 (CIs exclude 0); Lagavulin +1.3, Nob +1.2,
Sentries +1.0, Hexaghost +1.1, Slime Boss −0.2, Collector −0.1 (near 0). Full table in `result.json`.

**Against §701 (observational, won fights):** act-1 elites +3.5 → +1.2 matched; act-1 boss +8.0 → +1.7; act-2 elites
+4.5 → +5.4; act-2 boss +12.4 → +4.5. In act 1 most of the observed gap goes away on the expert's own states (it
comes from upstream: deck, HP, path); act-2 elites keep their whole gap, act-2 bosses about a third.

## Potions and prefix

- The bot holds fewer potions at entry (acts 1-2 elites/bosses 1.25 vs 1.65): it keeps its own and drinks more in
  bosses (act-1 0.89 vs 0.47, act-2 0.66 vs 0.44), though less than him in act-2 elites (0.41 vs 0.53).
- Subset whose entry potions equal the expert's (n 323, 147 runs, mostly early): +0.29 [−0.83, +1.39] HP, but the bot
  drinks +0.18 [+0.11, +0.24] more per fight there. Selected subset; descriptive.
- Prefix: end floor median 24 (IQR 16-39); end act 1/2/3/4: 108/129/34/58 runs. Stops: Act 4 58, card offer differs
  44, main-line death 31 (all 4 copies lost a fight he won; 28 fights), boss relic offer differs 29, boss relic not
  logged 20, others ≤ 12. 79 fights continued from copy 1-3 (68 runs); logged reward potions not offered afterwards:
  145 in those runs vs 92 in the others; 252 potions left for a full belt (bot holding its own).

## Post-hoc correction (descriptive rows only)

\* The final act-3 boss (floor 51 at A20): the engine's exit from that fight runs on into the Act-4 transition,
which heals 75% of missing HP (`GameContext::transitionToAct`); the expert's floor-51 HP is before that heal. Before
the correction Time Eater and Donu and Deca showed the bot *gaining* HP (−3.4 and −2.7 lost). `analyze.py` now
inverts the heal for those bot exits (largest h with h + round(0.75·(max − h)) = exit). Acts 1-2 and the primary are
unaffected (identical before and after).

## Interpretation

On identical deck, relics, path and HP, today's A20 Silver loses ~2.6 more HP per acts-1-2 elite/boss fight than
Baalorlord, dies about twice as often per fight (6% vs 3%), and drinks slightly more. The gap is small in act 1 and
large in act-2 elites (+5.4, all three) and act-2/3 bosses (Automaton, Awakened One). So §701's act-1 gap is mostly
upstream, while from act 2 on combat play itself is a real bottleneck. Caveats from PREREG apply: one expert sample
per fight vs a 4-copy mean, engine fidelity not testable, potions only partly matched.

Seeds: none (external Baalorlord run seeds, §694's 329).
