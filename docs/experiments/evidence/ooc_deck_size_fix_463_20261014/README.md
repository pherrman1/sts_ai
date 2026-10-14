# §463 evidence: shop deck-size accounting on vs off in §433 `combo`

Design: [PREREG.md](PREREG.md) (frozen before any cohort seed ran; independent pre-launch review passed). Code
`06ff0e75` (main after #528), binary sha256 `b4586cfc…95e1`, run commit `106a7e65`. Seeds 92000000–92000127, both
arms on every seed, 8 cloud workers × 32 one-seed units. Smoke: [SMOKE.md](SMOKE.md).

## Validity

- All 8 tars match the `tar_sha256` in their `DONE.txt`; every DONE names run `106a7e65` and binary `b4586cfc`.
- 256/256 units rc=0; no `[bestbench-seed-failure]`; no restarts.
- 128/128 cohort seeds in both arms; no invalid units, no non-cohort seeds.
- Every `.env` pins `STS_OOC_PUBLIC_FUTURES=8`, the X2-B public `STS_WIN_NET`, `STS_OOC_MCTS_ROLLOUT_SHOP=planner` and
  its arm's `STS_OOC_SHOP_DECK_SIZE_FIX` (fixon 1, fixoff 0).
- Every log shows `"simulations":4096` and `"leafCombats":3`; the deck-size banner appears in every `fixon` log and in
  no `fixoff` log; no log shows `rollout_shop=greedy`.

## Result ([analysis.json](analysis.json), `tools/analyze_ooc_deck_size_463.py`)

| | fixon | fixoff | fixon − fixoff |
|---|---|---|---|
| wins / 128 | 110 (85.9%) | 110 (85.9%) | 0.0 pp [−7.1, +7.8], **NOT_SHOWN** |
| discordant seeds | 12 | 12 | McNemar p = 1.0 |
| mean floor | 50.08 | 49.84 | +0.24 [−0.44, +0.98] |
| boss deaths | 16 | 14 | |
| seconds per run | 583.6 | 590.7 | |
| MCTS CPU s per run | 502.2 | 508.2 | |
| owned / fallback share | 97.5% / 2.5% | 97.5% / 2.5% | |

## Raw data

`/mnt/project-files/ooc-deck-size-463/wNN.tar` and `wNN.DONE.txt` (sha256 prefixes: w01 9419b0a4, w02 a2b0c1d3,
w03 2623adf0, w04 b6f141ad, w05 9c6b167c, w06 403a36a4, w07 93fc2c89, w08 a7557e01).
Reproduce: extract all tars, then `python3 tools/analyze_ooc_deck_size_463.py OUT.json <dir>/wNN/out ...`.
