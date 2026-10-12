# Gold2: OOC MCTS (§425 searches, prod + rollout3) vs heuristic, per decision type

Picks from docs/experiments/evidence/ooc_mcts_a20_gold_20261011/searches-*.jsonl.gz (4 searches per decision, unowned -> heuristic), scored on Gold2 floor labels. All MCTS models A0; rollout3 on production CTM (25% Lizard/hp_envelope aborts). In live play the chest-open and reward-relic rules (#431) override the TREASURE and relic->skip picks: with those set to 0, prod +0.49 [+0.12,+0.87], rollout3 +0.41 [+0.16,+0.70], V4 +0.31 [-0.05,+0.71] floors/decision.

```
MCTS prod: 387 decisions (skipped {'no search': 11, 'state mismatch (option set differs)': 1}); owned 0.99; regret heur 2.32 MCTS 1.95; MCTS-minus-heur +0.38 [+0.01,+0.78]; all 4 searches = heuristic 0.45

## By screen (gain = MCTS label minus heuristic label, floors, averaged over 4 searches; + = MCTS better)
screen         n owned agree  regH  regM               gain/dec    sum better  worse
BOSS_RELIC     4  1.00  0.75  2.52  1.84    +0.67 [+0.00,+2.02]    2.7      1      0
EVENT         34  0.97  0.24  5.96  2.65    +3.31 [+0.57,+6.51]  112.4     13     12
MAP           68  1.00  0.43  3.01  2.16    +0.85 [-0.25,+2.24]   57.9     23     14
REST          23  1.00  0.74  1.15  0.51    +0.63 [+0.13,+1.30]   14.6      6      0
REWARDS      209  1.00  0.50  1.57  1.69    -0.11 [-0.32,+0.08]  -23.6     27     26
SHOP          21  0.95  0.52  4.30  3.99    +0.31 [-0.45,+1.02]    6.5      8      2
TREASURE      12  1.00  0.00  0.03  2.33    -2.30 [-5.04,-0.65]  -27.6      2     10
UPGRADE       16  1.00  0.19  2.23  2.07    +0.15 [-1.30,+2.02]    2.5      4      8

## By act
act 1: n 278 gain/dec +0.55 [+0.07,+1.09] sum 153.7
act 2: n 90 gain/dec -0.13 [-0.65,+0.29] sum -11.7
act 3: n 19 gain/dec +0.18 [-0.24,+0.65] sum 3.4

## Disagreements (211): heuristic -> MCTS modal pick (coarse), sorted by total gain
  TREASURE   open                         -> opt1                         n= 12 mean -2.30 sum -27.6
  REWARDS    relic                        -> skip                         n=  9 mean -1.64 sum -14.8
  REWARDS    take card                    -> take card                    n= 26 mean -0.56 sum -14.7
  EVENT      WeMeetAgain                  -> WeMeetAgain                  n=  1 mean -10.19 sum -10.2
  EVENT      Liars Game                   -> Liars Game                   n=  3 mean -0.79 sum -2.4
  MAP        REST                         -> ELITE                        n=  5 mean -0.05 sum -0.2
  REWARDS    gold                         -> relic                        n= 18 mean +0.00 sum +0.0
  REWARDS    gold                         -> potion                       n= 15 mean +0.00 sum +0.0
  REWARDS    skip card                    -> take card                    n=  5 mean +0.04 sum +0.2
  SHOP       buy relic                    -> remove                       n=  3 mean +0.21 sum +0.6
  MAP        EVENT                        -> SHOP                         n=  3 mean +0.33 sum +1.0
  REWARDS    gold                         -> skip                         n=  3 mean +0.79 sum +2.4
  UPGRADE    pick                         -> pick                         n= 13 mean +0.19 sum +2.5
  MAP        MONSTER                      -> MONSTER                      n= 12 mean +0.27 sum +3.3
  REWARDS    gold                         -> take card                    n= 24 mean +0.15 sum +3.7
  REST       SMITH                        -> REST                         n=  4 mean +2.94 sum +11.8
  EVENT      The Cleric                   -> The Cleric                   n=  1 mean +16.56 sum +16.6
  EVENT      Scrap Ooze                   -> Scrap Ooze                   n=  2 mean +9.75 sum +19.5
  MAP        EVENT                        -> MONSTER                      n=  6 mean +3.39 sum +20.3
  MAP        MONSTER                      -> SHOP                         n=  1 mean +31.62 sum +31.6
  EVENT      NEOW                         -> NEOW                         n=  5 mean +17.33 sum +86.7

## Worst 10
  69109004 f 9 TREASURE  heur 'open' -> MCTS 'opt1'  -16.00 (best 'open')
  69120007 f19 MAP       heur 'EVENT' -> MCTS 'MONSTER'  -13.62 (best 'EVENT')
  69118007 f 4 EVENT     heur 'WeMeetAgain opt3' -> MCTS 'WeMeetAgain opt1'  -10.19 (best 'WeMeetAgain opt0')
  69119001 f 9 REWARDS   heur 'relic' -> MCTS 'skip'  -9.94 (best 'relic')
  69124009 f17 MAP       heur 'MONSTER' -> MCTS 'MONSTER'  -8.16 (best 'MONSTER')
  69104008 f 9 REWARDS   heur 'relic' -> MCTS 'skip'  -6.44 (best 'relic')
  69116008 f12 EVENT     heur 'Liars Game opt1' -> MCTS 'Liars Game opt0'  -5.75 (best 'Liars Game opt1')
  69120000 f 1 REWARDS   heur 'take RAMPAGE' -> MCTS 'take WARCRY'  -5.69 (best 'take ARMAMENTS')
  69113001 f18 REWARDS   heur 'take CLOTHESLINE' -> MCTS 'take POWER_THROUGH'  -5.44 (best 'take CLOTHESLINE')
  69115001 f 1 REWARDS   heur 'take TWIN_STRIKE' -> MCTS 'take INTIMIDATE'  -5.44 (best 'take TWIN_STRIKE')

## Best 10
  69123005 f 2 MAP       heur 'MONSTER' -> MCTS 'SHOP'  +31.62 (best 'SHOP')
  69116004 f 0 EVENT     heur 'NEOW opt3' -> MCTS 'NEOW opt0'  +26.25 (best 'NEOW opt2')
  69105010 f 0 EVENT     heur 'NEOW opt3' -> MCTS 'NEOW opt1'  +24.25 (best 'NEOW opt2')
  69124003 f 0 EVENT     heur 'NEOW opt3' -> MCTS 'NEOW opt2'  +23.59 (best 'NEOW opt1')
  69121004 f 2 MAP       heur 'EVENT' -> MCTS 'MONSTER'  +17.25 (best 'MONSTER')
  69103005 f 3 EVENT     heur 'Scrap Ooze opt0' -> MCTS 'Scrap Ooze opt1'  +17.19 (best 'Scrap Ooze opt1')
  69102011 f 7 EVENT     heur 'The Cleric opt1' -> MCTS 'The Cleric opt0'  +16.56 (best 'The Cleric opt0')
  69116009 f 0 EVENT     heur 'NEOW opt3' -> MCTS 'NEOW opt0'  +15.88 (best 'NEOW opt2')
  69121004 f 4 MAP       heur 'EVENT' -> MCTS 'MONSTER'  +14.88 (best 'MONSTER')
  69103011 f 0 UPGRADE   heur 'STRIKE_RED' -> MCTS 'DEFEND_RED'  +11.19 (best 'DEFEND_RED')
```

```
MCTS rollout3: 387 decisions (skipped {'no search': 11, 'state mismatch (option set differs)': 1}); owned 0.75; regret heur 2.32 MCTS 1.99; MCTS-minus-heur +0.33 [+0.07,+0.63]; all 4 searches = heuristic 0.48

## By screen (gain = MCTS label minus heuristic label, floors, averaged over 4 searches; + = MCTS better)
screen         n owned agree  regH  regM               gain/dec    sum better  worse
BOSS_RELIC     4  0.94  0.25  2.52  0.64    +1.88 [-0.04,+4.17]    7.5      2      1
EVENT         34  0.70  0.32  5.96  3.48    +2.48 [+0.54,+4.92]   84.3     14      8
MAP           68  0.76  0.50  3.01  2.33    +0.69 [-0.05,+1.61]   46.6     22      8
REST          23  0.74  0.70  1.15  0.87    +0.28 [-0.13,+0.72]    6.4      5      2
REWARDS      209  0.76  0.52  1.57  1.57    +0.01 [-0.14,+0.16]    1.6     29     20
SHOP          21  0.82  0.48  4.30  4.02    +0.29 [-0.67,+1.18]    6.0      8      3
TREASURE      12  0.67  0.08  0.03  1.67    -1.64 [-3.69,-0.44]  -19.7      1     10
UPGRADE       16  0.72  0.25  2.23  2.43    -0.21 [-0.64,+0.19]   -3.3      6      6

## By act
act 1: n 278 gain/dec +0.41 [+0.06,+0.80] sum 113.3
act 2: n 90 gain/dec +0.16 [-0.16,+0.47] sum 14.5
act 3: n 19 gain/dec +0.08 [-0.31,+0.54] sum 1.6

## Disagreements (201): heuristic -> MCTS modal pick (coarse), sorted by total gain
  TREASURE   open                         -> opt1                         n=  9 mean -2.09 sum -18.8
  REWARDS    relic                        -> skip                         n=  9 mean -1.02 sum -9.1
  MAP        SHOP                         -> MONSTER                      n=  1 mean -9.05 sum -9.0
  UPGRADE    pick                         -> pick                         n= 12 mean -0.28 sum -3.3
  EVENT      Living Wall                  -> Living Wall                  n=  3 mean -0.59 sum -1.8
  REWARDS    gold                         -> relic                        n= 16 mean -0.08 sum -1.3
  REWARDS    gold                         -> gold                         n=  8 mean -0.10 sum -0.8
  MAP        REST                         -> ELITE                        n=  3 mean +0.00 sum +0.0
  REWARDS    gold                         -> potion                       n= 14 mean +0.00 sum +0.0
  REWARDS    gold                         -> take card                    n= 16 mean +0.03 sum +0.5
  MAP        EVENT                        -> SHOP                         n=  3 mean +0.33 sum +1.0
  REWARDS    take card                    -> take card                    n= 29 mean +0.07 sum +2.0
  REWARDS    skip card                    -> take card                    n=  3 mean +1.96 sum +5.9
  BOSS_RELIC pick                         -> pick                         n=  3 mean +2.50 sum +7.5
  SHOP       buy card                     -> buy card                     n=  3 mean +2.56 sum +7.7
  EVENT      The Cleric                   -> The Cleric                   n=  1 mean +12.42 sum +12.4
  MAP        MONSTER                      -> MONSTER                      n= 11 mean +1.58 sum +17.3
  EVENT      Scrap Ooze                   -> Scrap Ooze                   n=  2 mean +9.75 sum +19.5
  MAP        MONSTER                      -> SHOP                         n=  1 mean +23.72 sum +23.7
  EVENT      NEOW                         -> NEOW                         n=  5 mean +10.50 sum +52.5

## Worst 10
  69109004 f 9 TREASURE  heur 'open' -> MCTS 'opt1'  -12.00 (best 'open')
  69118006 f 4 MAP       heur 'SHOP' -> MCTS 'MONSTER'  -9.05 (best 'SHOP')
  69104008 f 9 REWARDS   heur 'relic' -> MCTS 'skip'  -6.44 (best 'relic')
  69113000 f30 SHOP      heur 'buy card TWIN_STRIKE' -> MCTS 'leave'  -6.31 (best 'buy card TWIN_STRIKE')
  69115001 f 1 REWARDS   heur 'take TWIN_STRIKE' -> MCTS 'take INTIMIDATE'  -5.44 (best 'take TWIN_STRIKE')
  69113001 f18 REWARDS   heur 'take CLOTHESLINE' -> MCTS 'take POWER_THROUGH'  -5.44 (best 'take CLOTHESLINE')
  69116002 f 3 EVENT     heur 'Transmorgrifier opt0' -> MCTS 'Transmorgrifier opt1'  -4.81 (best 'Transmorgrifier opt0')
  69104005 f16 REWARDS   heur 'take FEED' -> MCTS 'take IMPERVIOUS'  -3.72 (best 'take FEED')
  69121015 f 0 MAP       heur 'MONSTER' -> MCTS 'MONSTER'  -3.69 (best 'MONSTER')
  69119000 f 6 REWARDS   heur 'relic' -> MCTS 'skip'  -3.28 (best 'take WILD_STRIKE')

## Best 10
  69105010 f 0 EVENT     heur 'NEOW opt3' -> MCTS 'NEOW opt1'  +24.25 (best 'NEOW opt2')
  69123005 f 2 MAP       heur 'MONSTER' -> MCTS 'SHOP'  +23.72 (best 'SHOP')
  69116004 f 0 EVENT     heur 'NEOW opt3' -> MCTS 'NEOW opt1'  +22.64 (best 'NEOW opt2')
  69103005 f 3 EVENT     heur 'Scrap Ooze opt0' -> MCTS 'Scrap Ooze opt1'  +17.19 (best 'Scrap Ooze opt1')
  69102011 f 7 EVENT     heur 'The Cleric opt1' -> MCTS 'The Cleric opt0'  +12.42 (best 'The Cleric opt0')
  69120014 f 0 MAP       heur 'MONSTER' -> MCTS 'MONSTER'  +10.36 (best 'MONSTER')
  69116011 f28 SHOP      heur 'buy card PERFECTED_STRIKE' -> MCTS 'buy card SHRUG_IT_OFF'  +6.06 (best 'buy card SHRUG_IT_OFF')
  69123004 f13 REWARDS   heur 'take HEAVY_BLADE' -> MCTS 'take SWORD_BOOMERANG'  +5.69 (best 'take SWORD_BOOMERANG')
  69110001 f17 BOSS_RELIC heur 'ECTOPLASM' -> MCTS 'PANDORAS_BOX'  +5.56 (best 'PANDORAS_BOX')
  69120000 f 1 REWARDS   heur 'take RAMPAGE' -> MCTS 'take ARMAMENTS'  +5.31 (best 'take ARMAMENTS')
```
