# OOC MCTS without leaf rollout combats vs rollout3 on the current defaults (ledger §472)

Plan: [PREREG.md](PREREG.md), independent pre-launch review PASS (run commit `1d637a92`, delta check for 16 workers
at `1e386af2`). Smoke: [SMOKE.md](SMOKE.md). Run commit `1e386af2`, code `aedbd473` (main after #534),
`one_combat` sha256 `207ddb6a…`; all 16 workers' `FROZEN.txt` name the same run, code and binary. Seeds
101000000–101000127 (fresh), Ironclad A0, 16 cloud workers × 8 seeds × 2 arms, launched by the coordinator.

## Validity

16/16 tars match the `tar_sha256` in their `DONE.txt` and extract cleanly ([data-sha256.txt](data-sha256.txt)). The
first uploads were dropped while project storage was full; all were re-checked from another container after space was
freed (six workers re-uploaded, ten first uploads were present and matched). 256/256 units rc=0, no restarts, no
stalls, 0 Silver seed failures, 128/128 pairs. All 256 `.env` files hold the pinned public futures, X2-B win net,
greedy rollout shop, deck-size fix 1, tree rules 1 and merging 1; `STS_OOC_MCTS_LEAF_COMBATS=0` in all 128 `rollout0`
and `=3` in all 128 `rollout3` units. All logs print `"simulations":4096` and their arm's `"leafCombats"`.

## Result ([report.json](report.json), `tools/analyze_ooc_rollout0_472.py`)

| | rollout0 | rollout3 |
|---|---|---|
| wins | 92/128 (71.9%) | 108/128 (84.4%) |
| boss deaths | 30 | 16 |
| mean floor | 47.41 | 48.95 |
| seconds per run (1 CPU) | 237 | 639 |
| MCTS CPU per run | 165 s | 561 s |
| simulations per run | 210k | 220k |
| V4 fallback share | 3.0% | 2.7% |
| support aborts per run | 0.23 | 0 |
| per-search max tree depth, median / p90 / max | 4 / 8 / 12 | 4 / 8 / 13 |
| mean simulation depth | 5.21 | 5.21 |
| pick = top-prior root candidate | 78.2% | 75.9% |
| pick = top-Q root candidate | 50.2% | 50.8% |

| comparison | Δwin [95% CI] | discordant | McNemar p | Δfloor [95% CI] | Δ end HP |
|---|---|---|---|---|---|
| **rollout0 − rollout3 (primary)** | **−12.5 pp [−21.9, −3.1]** | 11 vs 27 | 0.014 | −1.54 [−3.23, +0.04] | −5.8 |

**Primary label: WORSE.** Secondary: NOT_NONINFERIOR_AT_10PP.

## Reading

- Dropping the three leaf combats costs runs: the CI excludes zero and excludes a loss smaller than 3.1 pp.
- It saves a lot of CPU (wall-time sum ratio 0.37, MCTS CPU ratio 0.29), but the search is not shallower or
  differently shaped without them: tree depth, simulations and pick agreement are almost the same. So the rollout
  combats matter for the quality of the leaf value, not for how deep the tree gets. **Inference:** the native win
  model valued at the next map screen misjudges states whose consequences show only in the next few fights.
- Descriptive only: rollout0 lost 14 more runs on boss floors (30 vs 16 boss deaths), most at the Act 2 and Act 3
  bosses.
- `rollout3` won 84.4% here (§464 `rulesmerge` 83.6% on 93M seeds with the planner rollout shop).

No change (prereg decision): `rollout3` stays the research configuration. Raw data:
`/mnt/project-files/ooc-rollout0-472/wNN.tar` (extract to `wNN/out/`).
