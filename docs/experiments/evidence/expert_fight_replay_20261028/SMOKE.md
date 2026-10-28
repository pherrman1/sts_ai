# Smoke (2026-10-28, this container, 4 lanes)

Two smokes with `run_unit.sh` on run ids from `units.txt`; raw outputs were kept in the session scratchpad, the
aggregate of the second is `smoke_analysis.json` (not evidence, n = 8 runs).

1. Four runs (1665608474, 1693933695, 1651781965, 1660344805), potions set to the expert's at every fight: all rc 0;
   repeated runs gave identical files. Found the potion-refill bias: in 1660344805 the bot drank a free Blood Potion in
   every act-3 fight (the expert held one and never drank it) and exited fights 15-20 HP above entry
   (act-3 hallway HP lost −7.0 vs −2.0 for the expert). Fixed by `STS_EXPERT_FIGHTS_POTIONS=own` (the default).
2. Eight runs (the four above + 1632511943, 1648247344, 1666898585, 1686952006), `own` potions, binary sha256
   `edc27322…f16e93` (working tree before commit): all rc 0, 148 measured fights, 49 acts-1-2 elite/boss fights
   (6.1 per run). Prefix ends: act 4 2, boss relic offer differs 2, shop item not offered 1, logged upgrade card not
   in deck 1, expert log ends 1, main-line death 1 (1693933695: all four copies died to The Guardian at 21 HP; the
   expert won with 13 HP after two potions). No anomaly in act 3 any more (act-3 hallways 2.4 vs 0.1).
   Primary (not a result, n = 8): bot 12.4 vs expert 10.9 HP lost, +1.5 [−1.8, +5.1]; potions 0.60 vs 0.61 per fight;
   bot death per fight 0.071 vs 0.

## Cost

| run | end floor | measured fights | wall s |
|---|---|---|---|
| 1693933695 | 16 | 7 | 37 |
| 1686952006 | 32 | 16 | 86 |
| 1666898585 | 34 | 18 | 94 |
| 1651781965 | 25 | 12 | 98 |
| 1665608474 | 39 | 18 | 101 |
| 1632511943 | 34 | 19 | 150 |
| 1648247344 | 52 | 29 | 194 |
| 1660344805 | 52 | 29 | 653 |

Mean 177 s per run (one process, one core); act-3 bosses dominate (50-100 s CPU per copy in 1660344805). 329 runs
≈ 16 CPU-hours: ≈ 4-5 h wall at 4 lanes in one container, or < 1 h on 16 cloud workers. Expected primary n ≈ 2,000
acts-1-2 elite/boss fights. Peak RSS was not measured (no Act 4 is played inside the measurement).
