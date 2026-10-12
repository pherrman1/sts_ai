# rollout3 combo with the public X2-B win model vs B0 v_win (ledger §449)

Plan: [PREREG.md](PREREG.md), committed in run commit `88944bd5` before any cohort seed. Smoke: [SMOKE.md](SMOKE.md).
Code `94f78fbb` (main after #497), `one_combat` sha256 `85b1482b…`; all 8 workers' `FROZEN.txt` name the same run,
code and binary. Seeds 82000000–82000127, both arms fresh on every seed. 8 cloud workers × 16 seeds × 2 arms, started
by the coordinator on Philipp's card answer "128 pairs, 8 workers".

## Validity

8/8 tars match the `tar_sha256` in their `DONE.txt`. 256/256 units rc=0, no restarts, no `[bestbench-seed-failure]`,
128/128 pairs. All 256 `.env` files hold `STS_OOC_PUBLIC_FUTURES=8`, and all 128 `x2bpub` files hold
`STS_WIN_NET=models/candidates/v_win_x2b_public_trees.txt`. All 256 logs print `[ooc-mcts-config]` with
`"prior":"policy"`, `"wideningK":4,"wideningAlpha":0.75`, `"leafValue":"native","leafWinModel":null,"leafCombats":3,
"leafPolicy":"v4","simulations":4096`. Hashes: [data-sha256.txt](data-sha256.txt).
The coordinator re-verified all 8 tars from a second container. Each tar holds 292 entries: `out/`, `FROZEN.txt`, `DONE.txt`,
`units.txt` and the 288 `vwin-*`/`x2bpub-*` unit files, nothing else.

## Result ([report.json](report.json), `tools/analyze_ooc_x2b_449.py`)

| | x2bpub | vwin |
|---|---|---|
| wins | 114/128 (89.1%) | 111/128 (86.7%) |
| boss deaths | 10 | 12 |
| mean floor | 49.5 | 48.7 |
| seconds per run (1 CPU) | 790 | 795 |
| MCTS CPU per run | 713 s | 721 s |
| simulations per run | 246k | 244k |
| V4 fallback share | 2.6% | 2.4% |
| support aborts per run | 0.21 | 0.00 |

**Primary: NOT_SHOWN.** Δwin x2bpub − vwin +2.3 pp [−5.5, +10.2] (paired bootstrap, seed 449), discordant 15 vs 12,
McNemar p = 0.70. Δfloor +0.84 [−0.59, +2.36]; Δ end HP −1.5.

## Reading

**Inference:** the public X2-B plays at least about as well as B0 inside `combo` here; a loss larger than about 5 pp is
unlikely, a gain is not shown. CPU is the same (the X2-B ensemble has 1,006 trees vs B0's 1,060). Both arms ran with
public futures on, so the comparison is fair to B0's hidden-field use in the native fallback. Whether X2-B replaces
`models/v_win_trees.txt` is Philipp's decision (#397).

Raw: `/mnt/project-files/ooc-x2b-vwin-449/` (one tar per worker, plus `smoke.tar`).
