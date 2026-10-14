# OOC MCTS tree rules plus outcome merging vs §433 `combo` (ledger §464)

Plan: [PREREG.md](PREREG.md), independent pre-launch review PASS. Smoke: [SMOKE.md](SMOKE.md). Run commit
`ae0d66bb`, code `8f0b77b1`, `one_combat` sha256 `9dd31c4e…`; all 16 workers' `FROZEN.txt` name the same run, code and
binary. Seeds 93000000–93000127 (fresh), 16 cloud workers × 8 seeds × 2 arms, launched by the coordinator.

## Validity

16/16 tars match the `tar_sha256` in their `DONE.txt` and extract cleanly. 256/256 units rc=0, no restarts, 128/128
pairs, **0 Silver stalls**. Every unit's `.env` holds the pinned public futures, X2-B win net, planner rollout shop
and `STS_OOC_SHOP_DECK_SIZE_FIX=1`; `STS_OOC_MCTS_TREE_RULES=1` and `STS_OOC_MCTS_MERGE_OUTCOMES=1` appear in all 128
`rulesmerge` and no `combo` `.env`. All 256 logs print `"simulations":4096`. Hashes: [data-sha256.txt](data-sha256.txt).

## Result ([report.json](report.json), `tools/analyze_ooc_tree_rules_464.py`)

| | rulesmerge | combo |
|---|---|---|
| wins | 107/128 (83.6%) | 104/128 (81.3%) |
| boss deaths | 13 | 20 |
| mean floor | 48.74 | 48.91 |
| seconds per run (1 CPU) | 692 | 652 |
| MCTS CPU per run | 608 s | 570 s |
| simulations per run | 220k | 245k |
| V4 fallback share | 2.8% | 2.4% |
| per-search max tree depth, median / p90 / max | 4 / 8 / 14 | 2 / 2 / 2 |
| mean simulation depth | 5.21 | 1.60 |
| pick = top-prior root candidate | 76.2% | 78.8% |
| pick = top-Q root candidate | 51.3% | 46.0% |

| comparison | Δwin [95% CI] | discordant | McNemar p | Δfloor [95% CI] | Δ end HP |
|---|---|---|---|---|---|
| **rulesmerge − combo (primary)** | **+2.3 pp [−6.3, +10.2]** | 16 vs 13 | 0.71 | −0.17 [−1.38, +0.95] | −0.6 |

**Primary label: NOT_SHOWN.**

## Reading

- The pair makes the tree deeper as intended (median search depth 2 → 4, mean simulation depth 1.6 → 5.2) at about
  6% more wall time per run (sum ratio 1.061, not pre-registered), but the win difference is not shown; the CI
  excludes a loss larger than 6.3 pp. NOT_SHOWN does not mean equal.
- Descriptive only: boss deaths 13 vs 20, and picks follow the top-Q candidate slightly more often. Neither was a
  pre-registered test.
- In `rulesmerge` the live rule step took about 43 forced pickups per run that `combo` routes through the chain.
- `combo` won 81.3% here; §463's identical `fixon` arm won 110/128 (85.9%) on 92M seeds.
- Rules and merging changed together, so this run cannot split their effects.

No default change (prereg decision). Raw data: `/mnt/project-files/ooc-tree-rules-464/wNN.tar` (extract to `wNN/out/`).
