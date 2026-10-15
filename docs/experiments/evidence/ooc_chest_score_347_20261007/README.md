# #347 chest reward scoring on the map screen (2026-10-07)

Follow-up to ledger §390. In the C arm (OOC MCTS + chest rule) the search left
the relic on the reward screen at 8 of 11 chests. Philipp asked to score each
chest state with and without the relic, both on the map screen. Descriptive
only: no new seeds, no gameplay or default change. Ledger §390 (addendum).

## Method

- Diagnostic hook `STS_347_CHEST_SCORE` ([diag-chest-score.patch](diag-chest-score.patch),
  commit `8674b83` on top of the §390 build `1911f044`; not merged). At each
  treasure reward screen with a relic, it builds detached copies and scores
  them with the live leaf models of the run (`screengbm`: screen GBM residual
  where it covers the screen, X2-B anchor otherwise and on the map):
  - `relic_map`: take the gold, take the relic, leave to the map;
  - `gold_map`: take the gold, leave the relic, leave to the map;
  - `root`, `leave`, `gold_screen`, `relic_screen`: the reward screen itself
    and the other one-step children, for comparison.
- Binary `linux-gcc-release` `one_combat`, SHA-256
  `4a73cc75002c3e1639937f4954b3b007a48254834799cd4c074efb4eac9d2e32`.
  `run.sh` is the §390 runner with the hook exported instead of the profile;
  the four C sources of `../ooc_counterfactual_347_20261007/selection.json`.
- Read-only check: all four decision traces are byte-identical to the §390 C
  traces, and the boss rows match except CPU/wall time.

## Result (`chest_stats.py run`, [stats.txt](stats.txt))

| seed | floor | relic | map with relic | map without | delta |
|---|---|---|---|---|---|
| 48000014 | 9 | Whetstone | 0.6789 | 0.7003 | -0.0214 |
| 48000014 | 26 | Maw Bank | 0.8361 | 0.8382 | -0.0021 |
| 48000014 | 43 | Smiling Mask | 0.8992 | 0.9093 | -0.0101 |
| 48000024 | 9 | Calipers | 0.8232 | 0.8232 | 0 |
| 48000024 | 26 | Bag of Marbles | 0.8011 | 0.8028 | -0.0017 |
| 48000095 | 9 | Bottled Flame | 0.8646* | 0.8646 | 0 |
| 48000095 | 11 | Meal Ticket | 0.8632 | 0.8632 | 0 |
| 48000095 | 26 | Meat on the Bone | 0.9240 | 0.9273 | -0.0033 |
| 48000095 | 43 | Bag of Preparation | 0.9645 | 0.9583 | +0.0062 |
| 48000116 | 9 | Meal Ticket | 0.7797 | 0.7797 | 0 |
| 48000116 | 26 | Potion Belt | 0.6425 | 0.6425 | 0 |

\* Bottled Flame opens its card select, so that copy is scored there (X2-B).

On the map the leaf value (X2-B v_win) gives the relic exactly zero at 5 of 11
chests, less than leaving it at 5, and more at 1. Mean delta -0.0029, median 0.
The same model does see gold: on 48000116 floor 9, taking 27 gold moves the
map value from 0.7636 to 0.7797. X2-B has a one-hot feature for every relic,
so the relic is visible; the trees put no or negative value on these ones.

**Inference:** the relic skipping in §390 is not a reward-screen versus
map-screen artifact. The leaf value model the search uses prices these chest
relics at about zero, so with a uniform prior on chest reward screens (no card
reward, so V4 does not score them) the choice is decided by sampling noise.
Not shown: whether X2-B is wrong about these relics' effect on act-boss wins;
four selected seeds, eleven states.
