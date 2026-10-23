# Result: endgame exact study (2026-10-22)

Campaign endgame-exact, run commit f8831b48, solver c449ca96 (sha256 e16d59d1...), 8 workers x 4 lanes,
13:37-14:36Z. `verify_campaign.py`: units OK 133, MISSING 0, BAD 0, duplicates 0, one run commit; unit tar hashes in
`tars.sha256`. `collect.py`: every unit rc 0 and one row per position; every config covers its input once.
Write-up: section 9 of /mnt/project-files/exact-combat-research/REPORT.md.

Extra numbers (not printed by study.py):
- Attack-vs-block Q gap, clustered by fight (mean over each fight's attack/block pairs of exactly solved actions with
  at least 50 visits): last turn +0.439 ± 0.085 (133 fights; positive in 79% of 208 positions), second-to-last turn
  +0.711 ± 0.434 (33 fights).
- Lost fights, first decision of each turn (S0): death turn 50 turn starts, 33 solved, no surviving play in 26, best
  P(survive) mean 0.076, Silver's first action 0.075; one and two turns before the death all 31 and 30 solved turn
  starts survive with certainty.
- 120 s check (local, the 32 positions of unit C1 0 32): 11 solved against 10 at 30 s, identical values on the 10.

## study.py output

Runs: 68 (won 12); elite/boss fights recorded: 549 (elite won 354, elite lost 15, boss won 144, boss lost 36)

| config | roots | solved | over time limit | unsupported | median s | p90 s | max states |
|---|---|---|---|---|---|---|---|
| C0 elite | 1061 | 593 (56%) | 171 | 297 | 0.06 | 30.0 | 1,414,583 |
| C0 boss | 603 | 344 (57%) | 93 | 166 | 0.05 | 30.0 | 509,136 |
| C0 all | 1664 | 937 (56%) | 264 | 463 | 0.05 | 30.0 | 1,414,583 |
| C2 elite | 1712 | 609 (36%) | 406 | 697 | 1.54 | 30.1 | 2,153,132 |
| C2 boss | 786 | 244 (31%) | 240 | 302 | 4.62 | 30.1 | 1,711,092 |
| C2 all | 2498 | 853 (34%) | 646 | 999 | 1.76 | 30.1 | 2,153,132 |
| C1 elite | 1712 | 464 (27%) | 552 | 696 | 3.74 | 30.1 | 1,807,927 |
| C1 boss | 786 | 183 (23%) | 294 | 309 | 8.81 | 30.1 | 924,781 |
| C1 all | 2498 | 647 (26%) | 846 | 1005 | 5.29 | 30.1 | 1,807,927 |
| S0 elite | 175 | 134 (77%) | 5 | 36 | 0.03 | 0.4 | 123,953 |
| S0 boss | 541 | 286 (53%) | 72 | 183 | 0.03 | 30.0 | 675,505 |
| S0 all | 716 | 420 (59%) | 77 | 219 | 0.03 | 30.0 | 675,505 |
| S1 elite | 67 | 21 (31%) | 18 | 28 | 1.65 | 30.0 | 862,467 |
| S1 boss | 184 | 19 (10%) | 79 | 86 | 10.54 | 30.1 | 1,692,669 |
| S1 all | 251 | 40 (16%) | 97 | 114 | 8.60 | 30.1 | 1,692,669 |

### Won fights

**Last turn (C0)** (796 solved roots of won fights, 364 fights): proven optimal 433 (54%), certified mistakes 6 (sum 7.92 points; 1 of them under 0.5), undetermined 357 (regret upper bound median 35.8, p90 72.6); certified loss per fight 0.022 points

| seed | fight | turn | HP | Silver | best | certified regret | Silver visits share |
|---|---|---|---|---|---|---|---|
| 111149703 | GREMLIN_LEADER | 4 | 1/109 | attack: use card (3) (Twin Strike,16,1,1) -> (3) GREML | other: use card (1) (Spot Weakness,17,1,1) -> (2) FAT | 3.27 (≤ 23.60) | 65% |
| 111149757 | TIME_EATER | 8 | 120/130 | attack: use card (3) (Bash+,1,2,2) -> (0) TIME_EATER } | block: use card (2) (Slimed,44,1,1) } | 1.20 (≤ 15.60) | 32% |
| 111149718 | SLAVERS | 2 | 74/82 | other: use card (2) (Second Wind+,19,1,1) } | attack: use card (0) (Bash+,9,2,2) -> (1) TASKMASTER } | 1.13 (≤ 51.40) | 63% |
| 111149734 | REPTOMANCER | 2 | 78/78 | attack: use card (1) (Immolate+,4,1,1) } | block: use card (3) (Shrug It Off,16,2,2) } | 1.12 (≤ 11.60) | 36% |
| 111149730 | NEMESIS | 4 | 95/96 | attack: use card (2) (Anger,48,0,0) -> (0) NEMESIS } | attack+block: use card (0) (Shrug It Off,16,0,0) } | 1.04 (≤ 41.85) | 92% |

Certified mistakes by kind (Silver -> best): other -> attack: 2, attack -> block: 2, attack -> attack+block: 1, attack -> other: 1

**Second-to-last turn (C1 with C2 bounds where tighter)** (854 solved roots of won fights, 274 fights): proven optimal 175 (20%), certified mistakes 24 (sum 11.47 points; 16 of them under 0.5), undetermined 655 (regret upper bound median 31.2, p90 100.2); certified loss per fight 0.042 points

| seed | fight | turn | HP | Silver | best | certified regret | Silver visits share |
|---|---|---|---|---|---|---|---|
| 111149746 | GREMLIN_NOB | 4 | 47/75 | block: use card (0) (Defend,6,1,1) } | block: use card (4) (Flame Barrier+,11,2,2) } | 2.00 (≤ 2.00) | 80% |
| 111149753 | GREMLIN_NOB | 2 | 56/75 | attack: use card (1) (Pummel,11,1,1) -> (0) GREMLIN_NO | attack: use card (2) (Uppercut,13,2,2) -> (0) GREMLIN_ | 1.60 (≤ 1.93) | 82% |
| 111149762 | THREE_SENTRIES | 1 | 65/75 | block: use card (2) (Defend,8,1,1) } | attack: use card (0) (Pommel Strike,16,1,1) -> (2) SEN | 1.43 (≤ 1.43) | 56% |
| 111149705 | GREMLIN_NOB | 2 | 18/75 | block: use card (4) (Shrug It Off,13,1,1) } | potion: drink potion (0) Gamblers Brew } | 1.05 (≤ 1.05) | 86% |
| 111149764 | GREMLIN_NOB | 2 | 49/75 | attack: use card (1) (Strike,3,1,1) -> (0) GREMLIN_NOB | block: use card (0) (Defend,9,1,1) } | 1.00 (≤ 1.00) | 86% |
| 111149748 | GREMLIN_NOB | 3 | 41/75 | attack: use card (1) (Perfected Strike,16,2,2) -> (0)  | block: use card (0) (Defend,8,1,1) } | 0.86 (≤ 1.13) | 77% |
| 111149762 | THREE_SENTRIES | 1 | 65/75 | block: use card (1) (Defend,7,1,1) } | attack: use card (0) (Pommel Strike,16,1,1) -> (2) SEN | 0.86 (≤ 0.86) | 69% |
| 111149764 | GREMLIN_NOB | 2 | 49/75 | attack: use card (5) (Strike+,5,1,1) -> (0) GREMLIN_NO | attack: use card (2) (Havoc,17,1,1) } | 0.57 (≤ 0.57) | 61% |

Certified mistakes by kind (Silver -> best): attack -> attack: 7, attack -> block: 4, block -> attack: 4, attack -> other: 3, block -> block: 2, other -> attack: 1, attack+block -> attack+block: 1, block -> potion: 1, other -> other: 1

**Second-to-last turn, C1 alone** (647 solved roots of won fights, 220 fights): proven optimal 166 (26%), certified mistakes 24 (sum 11.47 points; 16 of them under 0.5), undetermined 457 (regret upper bound median 19.0, p90 73.3); certified loss per fight 0.052 points

| seed | fight | turn | HP | Silver | best | certified regret | Silver visits share |
|---|---|---|---|---|---|---|---|
| 111149746 | GREMLIN_NOB | 4 | 47/75 | block: use card (0) (Defend,6,1,1) } | block: use card (4) (Flame Barrier+,11,2,2) } | 2.00 (≤ 2.00) | 80% |
| 111149753 | GREMLIN_NOB | 2 | 56/75 | attack: use card (1) (Pummel,11,1,1) -> (0) GREMLIN_NO | attack: use card (2) (Uppercut,13,2,2) -> (0) GREMLIN_ | 1.60 (≤ 1.93) | 82% |
| 111149762 | THREE_SENTRIES | 1 | 65/75 | block: use card (2) (Defend,8,1,1) } | attack: use card (0) (Pommel Strike,16,1,1) -> (2) SEN | 1.43 (≤ 1.43) | 56% |
| 111149705 | GREMLIN_NOB | 2 | 18/75 | block: use card (4) (Shrug It Off,13,1,1) } | potion: drink potion (0) Gamblers Brew } | 1.05 (≤ 1.05) | 86% |
| 111149764 | GREMLIN_NOB | 2 | 49/75 | attack: use card (1) (Strike,3,1,1) -> (0) GREMLIN_NOB | block: use card (0) (Defend,9,1,1) } | 1.00 (≤ 1.00) | 86% |
| 111149748 | GREMLIN_NOB | 3 | 41/75 | attack: use card (1) (Perfected Strike,16,2,2) -> (0)  | block: use card (0) (Defend,8,1,1) } | 0.86 (≤ 1.13) | 77% |
| 111149762 | THREE_SENTRIES | 1 | 65/75 | block: use card (1) (Defend,7,1,1) } | attack: use card (0) (Pommel Strike,16,1,1) -> (2) SEN | 0.86 (≤ 0.86) | 69% |
| 111149764 | GREMLIN_NOB | 2 | 49/75 | attack: use card (5) (Strike+,5,1,1) -> (0) GREMLIN_NO | attack: use card (2) (Havoc,17,1,1) } | 0.57 (≤ 0.57) | 61% |

Certified mistakes by kind (Silver -> best): attack -> attack: 7, attack -> block: 4, block -> attack: 4, attack -> other: 3, block -> block: 2, block -> potion: 1, other -> other: 1, other -> attack: 1, attack+block -> attack+block: 1

**Second-to-last turn, C2 alone** (853 solved roots of won fights, 274 fights): proven optimal 122 (14%), certified mistakes 9 (sum 1.62 points; 8 of them under 0.5), undetermined 722 (regret upper bound median 35.6, p90 102.0); certified loss per fight 0.006 points

| seed | fight | turn | HP | Silver | best | certified regret | Silver visits share |
|---|---|---|---|---|---|---|---|
| 111149748 | GREMLIN_NOB | 3 | 41/75 | attack: use card (1) (Perfected Strike,16,2,2) -> (0)  | block: use card (0) (Defend,8,1,1) } | 0.86 (≤ 1.14) | 77% |

Certified mistakes by kind (Silver -> best): attack -> attack: 2, attack -> other: 2, block -> attack: 2, attack -> block: 2, block -> block: 1

Last turn: Silver edge Q minus exact value (actions solved exactly, >= 50 visits)

| action kind | n | mean | median |
|---|---|---|---|
| attack | 1127 | -0.90 | -0.08 |
| block | 217 | -1.21 | -0.68 |
| other | 120 | -1.67 | -0.96 |
| attack+block | 83 | -0.84 | -0.32 |
| end turn | 30 | -0.00 | +0.00 |
| potion | 16 | -2.47 | -0.79 |

Attack vs block in the same root: Silver Q gap minus exact gap +0.47 ± 0.06 (n 697 pairs; positive = Silver favours the attack more than it should)

Second-to-last turn: Silver edge Q minus exact value (actions solved exactly, >= 50 visits)

| action kind | n | mean | median |
|---|---|---|---|
| attack | 245 | -3.63 | -2.94 |
| block | 85 | -5.08 | -3.79 |
| end turn | 74 | -2.28 | -2.11 |
| potion | 52 | -2.12 | -1.51 |
| other | 28 | -3.98 | -4.01 |
| attack+block | 27 | -0.22 | -0.64 |

Attack vs block in the same root: Silver Q gap minus exact gap +0.47 ± 0.28 (n 142 pairs; positive = Silver favours the attack more than it should)

### Lost fights

**S0: lost fights, P(survive the next enemy turn)** (420 solved roots, 44 fights): Silver's choice lowers the survival probability at 3 roots (in 3 fights; mean drop 0.077)

| seed | fight | turn (to end) | HP | Silver | P(survive) | best | P(survive) |
|---|---|---|---|---|---|---|---|
| 111149712 | DONU_AND_DECA | 12 (2) | 5/114 | other: use card (4) (Battle Trance,16,0,0) } | 0.47 | attack: use card (5) (Anger+,41,0,0) -> (0) DECA } | 0.63 |
| 111149764 | AUTOMATON | 5 (0) | 38/42 | attack: use card (2) (Havoc,31,1,1) } | 0.71 | attack: use card (3) (Pommel Strike,21,1,1) -> (1) | 0.73 |
| 111149767 | TIME_EATER | 16 (0) | 10/85 | attack: use card (3) (Clothesline,12,2,2) -> (0) T | 0.00 | attack+block: use card (1) (Shrug It Off,19,1,1) } | 0.06 |

By kind (Silver -> best): attack -> attack+block: 1, other -> attack: 1, attack -> attack: 1

**S1: lost fights, P(survive the next 2 enemy turns)** (40 solved roots, 18 fights): Silver's choice lowers the survival probability at 3 roots (in 3 fights; mean drop 0.218)

| seed | fight | turn (to end) | HP | Silver | P(survive) | best | P(survive) |
|---|---|---|---|---|---|---|---|
| 111149700 | LAGAVULIN | 4 (1) | 21/75 | attack: use card (1) (Strike,4,1,1) -> (0) LAGAVUL | 0.00 | block: use card (0) (Defend,7,1,1) } | 0.54 |
| 111149702 | HEXAGHOST | 5 (1) | 15/75 | attack: use card (1) (Strike,5,1,1) -> (0) HEXAGHO | 0.36 | block: use card (0) (Armaments,17,1,1) } | 0.41 |
| 111149717 | SLIME_BOSS | 7 (1) | 8/81 | attack: use card (3) (Strike,1,1,1) -> (0) SPIKE_S | 0.06 | attack: use card (3) (Strike,1,1,1) -> (2) ACID_SL | 0.12 |

By kind (Silver -> best): attack -> block: 2, attack -> attack: 1
