# Gold2 (A20, 397 decisions, 16-future floor labels): heuristic vs V4, per decision type

Built 2026-10-12 from /mnt/project-files/v4-a20-retrain/gold2-w*.tar.gz; Q from tsq.py (gold2-scoring) at 0 epochs; script analyze: gold_breakdown.py. gain = label(V4 pick) - label(heuristic pick), floors; + = V4 better. Labels are heuristic-continuation floor reached, A20.

---
```
model v4final: 397 decisions; regret heur 2.26 V4 1.98; V4-minus-heur floors/decision +0.28 [-0.09,+0.67]; agree 0.42

## By screen (gain = V4 label minus heuristic label, floors; + means V4 better)
screen         n agree  regH  regV               gain/dec    sum V4 better V4 worse
BOSS_RELIC     4  0.75  2.52  1.84    +0.67 [+0.00,+2.02]    2.7         1        0
EVENT         36  0.36  5.63  3.03    +2.60 [+0.35,+5.32]   93.6        14        6
MAP           70  0.39  2.92  3.16    -0.24 [-1.50,+1.31]  -16.6        14       25
REST          23  0.74  1.15  0.53    +0.62 [+0.11,+1.28]   14.2         5        1
REWARDS      214  0.42  1.53  1.52    +0.01 [-0.26,+0.27]    1.4        35       32
SHOP          21  0.10  4.30  3.13    +1.17 [+0.12,+2.16]   24.6        15        4
TREASURE      13  0.92  0.03  0.09    -0.06 [-0.17,+0.00]   -0.8         0        1
UPGRADE       16  0.12  2.23  2.77    -0.54 [-1.22,+0.06]   -8.6         3        7

## By act
act 1: n 282 gain/dec +0.45 [-0.02,+1.00] sum 127.6
act 2: n 96 gain/dec -0.20 [-0.68,+0.21] sum -18.9
act 3: n 19 gain/dec +0.10 [-0.31,+0.58] sum 1.9

## Disagreements (232): heuristic choice -> V4 choice (coarse), sorted by total gain
  REWARDS    take card                    -> skip card                    n=  4 mean -4.69 sum -18.8
  MAP        REST                         -> MONSTER                      n=  4 mean -4.64 sum -18.6
  MAP        EVENT                        -> MONSTER                      n= 11 mean -1.06 sum -11.7
  UPGRADE    pick                         -> pick                         n= 14 mean -0.62 sum -8.6
  REWARDS    relic                        -> take card                    n=  8 mean -0.72 sum -5.8
  REWARDS    relic                        -> key                          n=  5 mean -1.07 sum -5.4
  REWARDS    skip card                    -> take card                    n=  4 mean -1.00 sum -4.0
  REWARDS    gold                         -> relic                        n=  8 mean +0.00 sum +0.0
  REWARDS    gold                         -> potion                       n=  9 mean +0.00 sum +0.0
  SHOP       buy relic                    -> buy potion                   n=  7 mean +0.42 sum +2.9
  REWARDS    potion                       -> take card                    n= 12 mean +0.46 sum +5.6
  REST       SMITH                        -> REST                         n=  5 mean +2.29 sum +11.4
  REWARDS    take card                    -> take card                    n= 29 mean +0.41 sum +11.8
  SHOP       buy relic                    -> buy card                     n=  4 mean +3.25 sum +13.0
  REWARDS    gold                         -> take card                    n= 33 mean +0.45 sum +14.8
  MAP        MONSTER                      -> MONSTER                      n= 13 mean +1.15 sum +15.0
  EVENT      NEOW                         -> NEOW                         n=  6 mean +14.40 sum +86.4

## Does V4 confidence (its own Q margin over the heuristic pick) predict a real gain? (disagreements only)
  V4 Q(best)-Q(heur) in (0.0, 0.25]: n  19 gain/dec -0.17 [-1.25,+0.95]
  V4 Q(best)-Q(heur) in (0.25, 0.5]: n  21 gain/dec -0.43 [-1.93,+0.99]
  V4 Q(best)-Q(heur) in (0.5, 1.0]: n  37 gain/dec +0.39 [-1.54,+3.12]
  V4 Q(best)-Q(heur) in (1.0, 2.0]: n  61 gain/dec -0.43 [-1.08,+0.20]
  V4 Q(best)-Q(heur) in (2.0, 4.0]: n  52 gain/dec +0.93 [+0.43,+1.47]
  V4 Q(best)-Q(heur) in (4.0, 1000000000.0]: n  42 gain/dec +2.05 [-0.28,+4.80]

## Worst 12 V4 overrides
  69118006 f 6 MAP       heur 'REST' -> V4 'MONSTER'  -14.06 (best 'REST')
  69120007 f19 MAP       heur 'EVENT' -> V4 'MONSTER'  -13.62 (best 'EVENT')
  69123008 f 3 REWARDS   heur 'take CLEAVE' -> V4 'skip card'  -11.94 (best 'take CLEAVE')
  69124009 f17 MAP       heur 'MONSTER' -> V4 'MONSTER'  -10.88 (best 'MONSTER')
  69111007 f13 REWARDS   heur 'gold' -> V4 'take HEADBUTT'  -8.50 (best 'gold')
  69113004 f 4 MAP       heur 'EVENT' -> V4 'MONSTER'  -8.44 (best 'SHOP')
  69104008 f 9 REWARDS   heur 'relic' -> V4 'key'  -6.44 (best 'relic')
  69112000 f 3 REWARDS   heur 'take CARNAGE' -> V4 'skip card'  -6.12 (best 'take CARNAGE')
  69107001 f 1 MAP       heur 'EVENT' -> V4 'MONSTER'  -5.94 (best 'EVENT')
  69120014 f 0 MAP       heur 'MONSTER' -> V4 'MONSTER'  -5.81 (best 'MONSTER')
  69100003 f11 REWARDS   heur 'relic' -> V4 'take PUMMEL'  -5.75 (best 'take ANGER')
  69112011 f13 MAP       heur 'ELITE' -> V4 'SHOP'  -5.44 (best 'ELITE')

## Best 12 V4 overrides
  69122004 f 0 MAP       heur 'MONSTER' -> V4 'MONSTER'  +37.88 (best 'MONSTER')
  69116004 f 0 EVENT     heur 'NEOW opt3' -> V4 'NEOW opt1'  +30.19 (best 'NEOW opt2')
  69124003 f 0 EVENT     heur 'NEOW opt3' -> V4 'NEOW opt1'  +25.75 (best 'NEOW opt1')
  69105010 f 0 EVENT     heur 'NEOW opt3' -> V4 'NEOW opt1'  +24.25 (best 'NEOW opt2')
  69121004 f 2 MAP       heur 'EVENT' -> V4 'MONSTER'  +17.25 (best 'MONSTER')
  69116009 f 0 EVENT     heur 'NEOW opt3' -> V4 'NEOW opt1'  +9.81 (best 'NEOW opt2')
  69113004 f 2 REWARDS   heur 'potion' -> V4 'take POMMEL_STRIKE'  +8.62 (best 'take POMMEL_STRIKE')
  69118002 f11 REWARDS   heur 'gold' -> V4 'take CLEAVE'  +8.31 (best 'take DUAL_WIELD')
  69115002 f 5 MAP       heur 'ELITE' -> V4 'REST'  +7.19 (best 'REST')
  69108007 f 4 REWARDS   heur 'gold' -> V4 'take WILD_STRIKE'  +7.06 (best 'take WILD_STRIKE')
  69111005 f 7 REST      heur 'SMITH' -> V4 'REST'  +6.25 (best 'REST')
  69124008 f19 EVENT     heur 'Vampires opt1' -> V4 'Vampires opt2'  +5.81 (best 'Vampires opt2')

## Live-style gate on gold decisions: play V4 when its best-vs-second Q margin >= m, else heuristic
  m=0    V4 overrides 232  gain vs heuristic +0.28 [-0.09,+0.67] floors/decision
  m=0.25 V4 overrides 187  gain vs heuristic +0.35 [-0.01,+0.75] floors/decision
  m=0.5  V4 overrides 152  gain vs heuristic +0.40 [+0.06,+0.78] floors/decision
  m=1    V4 overrides 100  gain vs heuristic +0.36 [+0.09,+0.66] floors/decision
  m=2    V4 overrides  50  gain vs heuristic +0.08 [-0.08,+0.24] floors/decision
  m=4    V4 overrides  19  gain vs heuristic -0.03 [-0.17,+0.12] floors/decision
  m=8    V4 overrides   4  gain vs heuristic -0.01 [-0.06,+0.02] floors/decision
```

---
```
model W30_best_qtop1: 397 decisions; regret heur 2.26 V4 1.84; V4-minus-heur floors/decision +0.42 [+0.05,+0.81]; agree 0.43

## By screen (gain = V4 label minus heuristic label, floors; + means V4 better)
screen         n agree  regH  regV               gain/dec    sum V4 better V4 worse
BOSS_RELIC     4  0.75  2.52  1.84    +0.67 [+0.00,+2.02]    2.7         1        0
EVENT         36  0.47  5.63  3.29    +2.34 [+0.32,+4.77]   84.2        13        5
MAP           70  0.63  2.92  2.02    +0.90 [-0.22,+2.35]   63.1        10       13
REST          23  0.61  1.15  0.61    +0.54 [-0.05,+1.24]   12.3         5        4
REWARDS      214  0.37  1.53  1.47    +0.06 [-0.22,+0.33]   12.5        44       37
SHOP          21  0.10  4.30  3.20    +1.10 [-1.10,+3.09]   23.2        14        5
TREASURE      13  0.54  0.03  1.50    -1.46 [-3.98,-0.09]  -19.0         1        5
UPGRADE       16  0.19  2.23  2.91    -0.69 [-2.42,+1.39]  -11.0         5        8

## By act
act 1: n 282 gain/dec +0.69 [+0.20,+1.24] sum 194.2
act 2: n 96 gain/dec -0.26 [-0.71,+0.11] sum -25.4
act 3: n 19 gain/dec -0.04 [-0.47,+0.39] sum -0.7

## Disagreements (228): heuristic choice -> V4 choice (coarse), sorted by total gain
  TREASURE   open                         -> opt1                         n=  6 mean -3.17 sum -19.0
  SHOP       buy relic                    -> leave                        n=  1 mean -13.38 sum -13.4
  UPGRADE    pick                         -> pick                         n= 13 mean -0.85 sum -11.0
  EVENT      WeMeetAgain                  -> WeMeetAgain                  n=  1 mean -10.19 sum -10.2
  MAP        TREASURE                     -> TREASURE                     n=  3 mean -1.19 sum -3.6
  REWARDS    take card                    -> take card                    n= 38 mean -0.08 sum -2.9
  REWARDS    relic                        -> key                          n=  3 mean -0.65 sum -1.9
  REST       REST                         -> SMITH                        n=  4 mean -0.02 sum -0.1
  REWARDS    gold                         -> potion                       n=  7 mean +0.00 sum +0.0
  REWARDS    gold                         -> relic                        n=  6 mean +0.00 sum +0.0
  REWARDS    skip card                    -> take card                    n=  5 mean +0.19 sum +0.9
  REWARDS    gold                         -> take card                    n= 40 mean +0.07 sum +2.9
  REWARDS    potion                       -> take card                    n= 15 mean +0.39 sum +5.8
  REWARDS    relic                        -> take card                    n= 11 mean +0.74 sum +8.1
  REST       SMITH                        -> REST                         n=  4 mean +2.67 sum +10.7
  MAP        EVENT                        -> SHOP                         n=  3 mean +4.67 sum +14.0
  EVENT      Living Wall                  -> Living Wall                  n=  3 mean +5.54 sum +16.6
  MAP        MONSTER                      -> MONSTER                      n=  8 mean +3.66 sum +29.2
  SHOP       buy relic                    -> buy card                     n= 10 mean +3.27 sum +32.7
  MAP        EVENT                        -> MONSTER                      n=  6 mean +5.58 sum +33.5
  EVENT      NEOW                         -> NEOW                         n=  5 mean +13.70 sum +68.5

## Does V4 confidence (its own Q margin over the heuristic pick) predict a real gain? (disagreements only)
  V4 Q(best)-Q(heur) in (0.0, 0.25]: n  23 gain/dec -0.40 [-1.36,+0.52]
  V4 Q(best)-Q(heur) in (0.25, 0.5]: n  31 gain/dec +0.53 [-0.93,+2.01]
  V4 Q(best)-Q(heur) in (0.5, 1.0]: n  56 gain/dec +0.12 [-0.77,+0.99]
  V4 Q(best)-Q(heur) in (1.0, 2.0]: n  63 gain/dec +0.15 [-1.21,+1.80]
  V4 Q(best)-Q(heur) in (2.0, 4.0]: n  47 gain/dec +2.24 [+0.61,+4.14]
  V4 Q(best)-Q(heur) in (4.0, 1000000000.0]: n   8 gain/dec +4.96 [+1.50,+9.11]

## Worst 12 V4 overrides
  69109004 f 9 TREASURE  heur 'open' -> V4 'opt1'  -16.00 (best 'open')
  69107011 f 1 REWARDS   heur 'gold' -> V4 'take RUPTURE'  -15.25 (best 'gold')
  69113001 f21 SHOP      heur 'buy relic CLOCKWORK_SOUVENIR' -> V4 'leave'  -13.38 (best 'buy card HEADBUTT')
  69118007 f 4 EVENT     heur 'WeMeetAgain opt3' -> V4 'WeMeetAgain opt1'  -10.19 (best 'WeMeetAgain opt0')
  69120003 f 5 UPGRADE   heur 'STRIKE_RED' -> V4 'UPPERCUT'  -6.75 (best 'STRIKE_RED')
  69104008 f 9 REWARDS   heur 'relic' -> V4 'key'  -6.44 (best 'relic')
  69113000 f30 SHOP      heur 'buy card TWIN_STRIKE' -> V4 'leave'  -6.31 (best 'buy card TWIN_STRIKE')
  69119008 f 4 UPGRADE   heur 'STRIKE_RED' -> V4 'PERFECTED_STRIKE'  -5.94 (best 'STRIKE_RED')
  69120014 f 0 MAP       heur 'MONSTER' -> V4 'MONSTER'  -5.81 (best 'MONSTER')
  69122003 f14 REWARDS   heur 'skip card' -> V4 'take RAMPAGE'  -5.31 (best 'take EVOLVE')
  69117001 f 2 SHOP      heur 'leave' -> V4 'buy potion'  -5.12 (best 'leave')
  69113001 f18 REWARDS   heur 'take CLOTHESLINE' -> V4 'take ARMAMENTS'  -4.56 (best 'take CLOTHESLINE')

## Best 12 V4 overrides
  69122004 f 0 MAP       heur 'MONSTER' -> V4 'MONSTER'  +37.88 (best 'MONSTER')
  69124003 f 0 EVENT     heur 'NEOW opt3' -> V4 'NEOW opt1'  +25.75 (best 'NEOW opt1')
  69116004 f 0 EVENT     heur 'NEOW opt3' -> V4 'NEOW opt0'  +24.94 (best 'NEOW opt2')
  69121004 f 2 MAP       heur 'EVENT' -> V4 'MONSTER'  +17.25 (best 'MONSTER')
  69121004 f 4 MAP       heur 'EVENT' -> V4 'MONSTER'  +14.88 (best 'MONSTER')
  69116009 f 0 EVENT     heur 'NEOW opt3' -> V4 'NEOW opt0'  +13.94 (best 'NEOW opt2')
  69113004 f 4 MAP       heur 'EVENT' -> V4 'SHOP'  +13.44 (best 'SHOP')
  69103011 f 0 UPGRADE   heur 'STRIKE_RED' -> V4 'DEFEND_RED'  +11.19 (best 'DEFEND_RED')
  69107011 f 4 SHOP      heur 'buy relic CLOCKWORK_SOUVENIR' -> V4 'buy card FLAME_BARRIER'  +9.94 (best 'buy potion')
  69101007 f 5 EVENT     heur 'Living Wall opt0' -> V4 'Living Wall opt1'  +9.00 (best 'Living Wall opt1')
  69118004 f 4 SHOP      heur 'buy relic PRESERVED_INSECT' -> V4 'buy card RECKLESS_CHARGE'  +8.50 (best 'buy card RECKLESS_CHARGE')
  69118002 f11 REWARDS   heur 'gold' -> V4 'take CLEAVE'  +8.31 (best 'take DUAL_WIELD')

## Live-style gate on gold decisions: play V4 when its best-vs-second Q margin >= m, else heuristic
  m=0    V4 overrides 228  gain vs heuristic +0.42 [+0.06,+0.83] floors/decision
  m=0.25 V4 overrides 168  gain vs heuristic +0.36 [+0.02,+0.73] floors/decision
  m=0.5  V4 overrides 118  gain vs heuristic +0.18 [-0.02,+0.40] floors/decision
  m=1    V4 overrides  56  gain vs heuristic +0.13 [-0.04,+0.30] floors/decision
  m=2    V4 overrides  21  gain vs heuristic +0.12 [+0.03,+0.23] floors/decision
  m=4    V4 overrides   3  gain vs heuristic +0.06 [-0.00,+0.15] floors/decision
  m=8    V4 overrides   0  gain vs heuristic +0.00 [+0.00,+0.00] floors/decision
```

---
```
model R2W30_best_qtop1: 397 decisions; regret heur 2.26 V4 1.95; V4-minus-heur floors/decision +0.32 [-0.09,+0.74]; agree 0.36

## By screen (gain = V4 label minus heuristic label, floors; + means V4 better)
screen         n agree  regH  regV               gain/dec    sum V4 better V4 worse
BOSS_RELIC     4  0.50  2.52  2.45    +0.06 [-1.83,+2.02]    0.2         1        1
EVENT         36  0.31  5.63  3.14    +2.49 [+0.03,+5.33]   89.8        14        9
MAP           70  0.47  2.92  2.50    +0.43 [-0.91,+2.07]   30.0        15       18
REST          23  0.57  1.15  0.71    +0.43 [-0.24,+1.22]    9.9         5        5
REWARDS      214  0.33  1.53  1.50    +0.03 [-0.24,+0.30]    6.0        52       45
SHOP          21  0.14  4.30  2.79    +1.51 [+0.45,+2.51]   31.7        14        4
TREASURE      13  0.46  0.03  1.75    -1.71 [-4.24,-0.19]  -22.2         1        6
UPGRADE       16  0.25  2.23  3.50    -1.27 [-2.45,-0.18]  -20.3         3        8

## By act
act 1: n 282 gain/dec +0.50 [-0.03,+1.08] sum 140.1
act 2: n 96 gain/dec -0.13 [-0.56,+0.26] sum -12.2
act 3: n 19 gain/dec -0.14 [-0.88,+0.49] sum -2.8

## Disagreements (255): heuristic choice -> V4 choice (coarse), sorted by total gain
  TREASURE   open                         -> opt1                         n=  7 mean -3.18 sum -22.2
  UPGRADE    pick                         -> pick                         n= 12 mean -1.69 sum -20.3
  MAP        SHOP                         -> MONSTER                      n=  1 mean -12.06 sum -12.1
  EVENT      WeMeetAgain                  -> WeMeetAgain                  n=  1 mean -10.19 sum -10.2
  REWARDS    take card                    -> skip                         n=  4 mean -1.48 sum -5.9
  REWARDS    relic                        -> key                          n=  6 mean -0.69 sum -4.1
  MAP        TREASURE                     -> TREASURE                     n=  3 mean -1.19 sum -3.6
  REWARDS    relic                        -> take card                    n= 11 mean -0.27 sum -2.9
  REWARDS    gold                         -> potion                       n=  4 mean +0.00 sum +0.0
  MAP        REST                         -> REST                         n=  3 mean +0.00 sum +0.0
  REWARDS    gold                         -> relic                        n=  6 mean +0.00 sum +0.0
  REWARDS    skip card                    -> take card                    n=  5 mean +0.19 sum +0.9
  REWARDS    potion                       -> take card                    n= 20 mean +0.05 sum +1.0
  EVENT      Match and Keep               -> Match and Keep               n=  3 mean +0.40 sum +1.2
  REST       REST                         -> SMITH                        n=  5 mean +0.82 sum +4.1
  REWARDS    gold                         -> take card                    n= 43 mean +0.12 sum +5.2
  REWARDS    take card                    -> take card                    n= 35 mean +0.15 sum +5.3
  REST       SMITH                        -> REST                         n=  4 mean +2.11 sum +8.4
  EVENT      Living Wall                  -> Living Wall                  n=  3 mean +3.67 sum +11.0
  MAP        EVENT                        -> MONSTER                      n=  8 mean +1.47 sum +11.8
  MAP        EVENT                        -> SHOP                         n=  3 mean +4.67 sum +14.0
  MAP        MONSTER                      -> MONSTER                      n= 10 mean +1.90 sum +19.0
  SHOP       buy relic                    -> buy card                     n=  8 mean +2.55 sum +20.4
  EVENT      NEOW                         -> NEOW                         n=  6 mean +14.40 sum +86.4

## Does V4 confidence (its own Q margin over the heuristic pick) predict a real gain? (disagreements only)
  V4 Q(best)-Q(heur) in (0.0, 0.25]: n  32 gain/dec -0.78 [-1.45,-0.14]
  V4 Q(best)-Q(heur) in (0.25, 0.5]: n  24 gain/dec -0.15 [-1.22,+0.93]
  V4 Q(best)-Q(heur) in (0.5, 1.0]: n  64 gain/dec +0.26 [-0.82,+1.36]
  V4 Q(best)-Q(heur) in (1.0, 2.0]: n  76 gain/dec +0.24 [-0.86,+1.63]
  V4 Q(best)-Q(heur) in (2.0, 4.0]: n  49 gain/dec +1.84 [+0.02,+4.03]
  V4 Q(best)-Q(heur) in (4.0, 1000000000.0]: n  10 gain/dec +2.94 [+0.50,+6.52]

## Worst 12 V4 overrides
  69109004 f 9 TREASURE  heur 'open' -> V4 'opt1'  -16.00 (best 'open')
  69120007 f19 MAP       heur 'EVENT' -> V4 'MONSTER'  -13.62 (best 'EVENT')
  69118006 f 4 MAP       heur 'SHOP' -> V4 'MONSTER'  -12.06 (best 'SHOP')
  69118007 f 4 EVENT     heur 'WeMeetAgain opt3' -> V4 'WeMeetAgain opt1'  -10.19 (best 'WeMeetAgain opt0')
  69111007 f13 REWARDS   heur 'gold' -> V4 'take HEADBUTT'  -8.50 (best 'gold')
  69121015 f 0 MAP       heur 'MONSTER' -> V4 'MONSTER'  -7.12 (best 'MONSTER')
  69120003 f 5 UPGRADE   heur 'STRIKE_RED' -> V4 'UPPERCUT'  -6.75 (best 'STRIKE_RED')
  69104008 f 9 REWARDS   heur 'relic' -> V4 'key'  -6.44 (best 'relic')
  69119008 f 4 UPGRADE   heur 'STRIKE_RED' -> V4 'PERFECTED_STRIKE'  -5.94 (best 'STRIKE_RED')
  69107001 f 1 MAP       heur 'EVENT' -> V4 'MONSTER'  -5.94 (best 'EVENT')
  69120014 f 0 MAP       heur 'MONSTER' -> V4 'MONSTER'  -5.81 (best 'MONSTER')
  69116008 f12 EVENT     heur 'Liars Game opt1' -> V4 'Liars Game opt0'  -5.75 (best 'Liars Game opt1')

## Best 12 V4 overrides
  69122004 f 0 MAP       heur 'MONSTER' -> V4 'MONSTER'  +37.88 (best 'MONSTER')
  69116004 f 0 EVENT     heur 'NEOW opt3' -> V4 'NEOW opt1'  +30.19 (best 'NEOW opt2')
  69124003 f 0 EVENT     heur 'NEOW opt3' -> V4 'NEOW opt1'  +25.75 (best 'NEOW opt1')
  69105010 f 0 EVENT     heur 'NEOW opt3' -> V4 'NEOW opt1'  +24.25 (best 'NEOW opt2')
  69121004 f 2 MAP       heur 'EVENT' -> V4 'MONSTER'  +17.25 (best 'MONSTER')
  69121004 f 4 MAP       heur 'EVENT' -> V4 'MONSTER'  +14.88 (best 'MONSTER')
  69113004 f 4 MAP       heur 'EVENT' -> V4 'SHOP'  +13.44 (best 'SHOP')
  69116009 f 0 EVENT     heur 'NEOW opt3' -> V4 'NEOW opt1'  +9.81 (best 'NEOW opt2')
  69101007 f 5 EVENT     heur 'Living Wall opt0' -> V4 'Living Wall opt1'  +9.00 (best 'Living Wall opt1')
  69118002 f11 REWARDS   heur 'gold' -> V4 'take CLEAVE'  +8.31 (best 'take DUAL_WIELD')
  69123000 f 3 REWARDS   heur 'take WHIRLWIND' -> V4 'take INFERNAL_BLADE'  +8.31 (best 'take INFERNAL_BLADE')
  69115002 f 5 MAP       heur 'ELITE' -> V4 'REST'  +7.19 (best 'REST')

## Live-style gate on gold decisions: play V4 when its best-vs-second Q margin >= m, else heuristic
  m=0    V4 overrides 255  gain vs heuristic +0.32 [-0.08,+0.75] floors/decision
  m=0.25 V4 overrides 194  gain vs heuristic +0.40 [+0.02,+0.82] floors/decision
  m=0.5  V4 overrides 150  gain vs heuristic +0.18 [-0.11,+0.51] floors/decision
  m=1    V4 overrides  84  gain vs heuristic +0.09 [-0.08,+0.26] floors/decision
  m=2    V4 overrides  23  gain vs heuristic +0.12 [+0.03,+0.24] floors/decision
  m=4    V4 overrides   4  gain vs heuristic +0.06 [-0.00,+0.17] floors/decision
  m=8    V4 overrides   1  gain vs heuristic +0.01 [+0.00,+0.04] floors/decision
```
