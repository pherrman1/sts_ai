# rollout3 OOC MCTS replication on the current stack (ledger §422)

Plan: [PREREG.md](PREREG.md), frozen at `f5734322` (independent review PASS at `67a9e6ea`, delta
re-review PASS at `f5734322`). Code `cd405b4c`, `one_combat` sha256 `39cdac96…` built independently
by all 16 cloud workers (every `FROZEN.txt` names the same run, code and binary). Seeds
70000000–70000127; smoke 70009000 passed (both arms won, banners as planned; recorded in
`/mnt/project-files/ooc-rollout3-replication/SMOKE_PASS`).

## Validity

160/160 units rc=0, no `[bestbench-seed-failure]`, no restarts or aborted units, 128/128 pairs.
All 128 rollout3 logs print `leafValue native`, `leafCombats 3`, `prior policy`, `simulations 2048`
and the production combat model `combat_transition_deepsets_pathb_r2.native`; none of the 32 `off`
logs enables OOC MCTS. Result CSV hashes: [data-sha256.txt](data-sha256.txt).

## Result ([report.json](report.json), `tools/analyze_rollout3_replication.py`)

| | rollout3 | off |
|---|---|---|
| wins | 115/128 (89.8%) | 101/128 (78.9%) |
| boss deaths | 11 | 23 |
| seconds per run (1 CPU) | 936 | 57 |

- **Primary:** Δwin +10.9 pp, paired bootstrap 95% CI [+2.3, +19.5] → **REPLICATED**.
  Discordant pairs 23 (rollout3 only) vs 9 (off only), exact McNemar p = 0.020.
- Δfloor +0.69 [−0.65, +2.0]; Δ end HP +12.6.
- rollout3 search: 850 s MCTS CPU per run (about 16x the whole off run), 105k simulations per run,
  3.0 CTM fights per simulation, 80.2% of OOC decisions owned. The 19.8% that fell back to V4 come
  from 21.8 support aborts per run, of which 2,764 in total (99%) are Lizard Tail aborts.
  Per-seed fallback median 16%, max 63%. On the 13 seeds with more than 40% fallback, both arms won
  13 and 12; on the other 115, rollout3 102 vs off 89.

## Reading

The +11 pp gain from §277 (+12.5 pp vs V4, old V2 CTM) reproduces on the current CTM and against the
current research base, now with a CI above zero. The gain comes from fewer boss deaths (11 vs 23).
The cost is about 16x CPU per run. **Inference:** the 3-combat rollout
leaf, not the tree or the prior, carries the value (compare §384 `screengbm` leaf −22 pp and §391
boss-rollout 9/32).

No default changes (PREREG decision). Next steps (not run): improvement screens on the same seeds,
one variable at a time (uniform prior, outcome merging, no early stop, fewer simulations for cost),
and a fresh-seed confirmation before any default change.

Raw data: `/mnt/project-files/ooc-rollout3-replication/w01..w16/`.
