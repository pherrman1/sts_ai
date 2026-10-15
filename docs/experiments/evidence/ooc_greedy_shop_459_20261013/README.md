# §459 evidence: greedy vs bundle-planner shops in rollout3 `combo` leaf rollouts

Design: [PREREG.md](PREREG.md) (frozen before any cohort seed ran; independent review passed on code and
launch). Code `440cf556`, binary sha256 `164264815f00…697527`, run commit `136695a2`. Seeds
89000000–89000127, both arms on every seed, 8 cloud workers × 32 one-seed units.

## Validity

- All 8 tars match the `tar_sha256` in their `DONE.txt`; 256/256 units rc=0; no `[bestbench-seed-failure]`.
- 128/128 cohort seeds present in both arms; no invalid units, no non-cohort seeds.
- Every unit `.env` pins `STS_OOC_PUBLIC_FUTURES=8`, the X2-B public `STS_WIN_NET`,
  `STS_OOC_SHOP_DECK_SIZE_FIX=1` and its own arm's `STS_OOC_MCTS_ROLLOUT_SHOP`.
- Every log shows the deck-size banner, `"simulations":4096` and `"leafCombats":3`; `rollout_shop=greedy`
  appears in every `greedy` log and in no `planner` log.

## Result ([analysis.json](analysis.json), `tools/analyze_ooc_greedy_shop_459.py`)

| | greedy | planner | greedy − planner |
|---|---|---|---|
| wins / 128 | 103 (80.5%) | 101 (78.9%) | +1.6 pp [−5.5, +8.6], **NOT_SHOWN** |
| discordant seeds | 12 | 10 | McNemar p = 0.83 |
| mean floor | 48.41 | 49.12 | −0.70 [−1.77, +0.23] |
| boss deaths | 21 | 23 | |
| seconds per run | 496.5 | 558.2 | ratio 0.889 [0.859, 0.922] |
| MCTS CPU s per run | 426.1 | 482.7 | |
| simulations per run | 241.5k | 248.1k | |
| owned / fallback share | 97.6% / 2.4% | 97.6% / 2.4% | |

The seconds ratio is the paired ratio of total seconds over seeds with a 10,000-resample seed bootstrap
(seed 459); per floor reached it is 0.902 [0.879, 0.925]. This ratio was not pre-registered as a statistic
(the prereg lists seconds per run as descriptive).

Live shop actions per run (descriptive, from the traces; live shop roots are searched by the tree in both
arms, only rollouts differ): greedy card 1.62, relic 2.33, potion 1.06, removal 0.44, leave 2.81;
planner card 1.88, relic 2.20, potion 1.24, removal 0.55, leave 2.87. Shop roots 1,149 vs 1,240, all
executed by MCTS.

## Raw data

`/mnt/project-files/ooc-greedy-shop-459/wNN.tar` and `wNN.DONE.txt` (sha256 prefixes: w01 21619d22,
w02 ba137e49, w03 3046e260, w04 f71a2965, w05 e4427910, w06 8e639ca6, w07 5b5cd53b, w08 c2f2de0b).
Reproduce: extract all tars, then `python3 tools/analyze_ooc_greedy_shop_459.py OUT.json <dir>/wNN/out ...`.
