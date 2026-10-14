# OOC MCTS without leaf rollout combats at 16384 simulations vs rollout3 at 4096 (ledger §475)

Plan: [PREREG.md](PREREG.md), independent pre-launch review PASS at run commit `9bd5b848` (code `e8410510`, main
after #542; `one_combat` sha256 `ec42a8ea…`). Smoke: [SMOKE.md](SMOKE.md). All 16 workers' `FROZEN.txt` name the same
run, code and binary. Seeds 103000000–103000127 (fresh), Ironclad A0, 16 cloud workers × 8 seeds × 2 arms, launched
by the coordinator.

## Validity

16/16 tars match the `tar_sha256` in their `DONE.txt` and extract cleanly, verified from a separate container
([data-sha256.txt](data-sha256.txt)). 256/256 units rc=0, no restarts, no stalls, 0 Silver seed failures, 128/128
pairs. All 256 `.env` files hold the pinned public futures, X2-B win net, greedy rollout shop, deck-size fix 1, tree
rules 1 and merging 1; `STS_OOC_MCTS_SIMS=16384` and `STS_OOC_MCTS_LEAF_COMBATS=0` in all 128 `r0s16k` and no
`rollout3` unit, which hold 4096 and 3. All logs print the arm's `"simulations"`.

## Result ([report.json](report.json), `tools/analyze_ooc_rollout0_sims_475.py`)

| | r0s16k | rollout3 |
|---|---|---|
| wins | 102/128 (79.7%) | 115/128 (89.8%) |
| boss deaths | 22 | 10 |
| mean floor | 48.74 | 49.93 |
| seconds per run (1 CPU) | 720 | 661 |
| MCTS CPU per run | 633 s | 574 s |
| simulations per run | 846k | 223k |
| V4 fallback share | 2.8% | 2.7% |
| per-search max tree depth, median / p90 / max | 5 / 9 / 14 | 4 / 8 / 13 |
| mean simulation depth | 6.04 | 5.29 |
| pick = top-prior root candidate | 72.7% | 75.9% |
| pick = top-Q root candidate | 55.5% | 51.1% |

| comparison | Δwin [95% CI] | discordant | McNemar p | Δfloor [95% CI] | Δ end HP |
|---|---|---|---|---|---|
| **r0s16k − rollout3 (primary)** | **−10.2 pp [−18.8, −1.6]** | 9 vs 22 | 0.029 | −1.19 [−2.38, −0.02] | −1.6 |

**Primary label: WORSE.** Secondary: NOT_NONINFERIOR_AT_10PP.

## Reading

- Spending rollout3's CPU on four times the simulations instead of leaf combats still loses runs. The CPU match is
  close but not exact: `r0s16k` used 1.10x the MCTS CPU (wall time 1.09x), so the comparison slightly favours it.
- The extra simulations make the search somewhat deeper (median per-search depth 5 vs 4, mean simulation depth 6.0 vs
  5.3) and the pick follows the top-Q candidate more often, without a win gain. **Inference:** the loss comes from
  the leaf value without the three combats, which more simulations do not correct; leaf-value quality was not
  measured, and on the 31 discordant seeds the arms play different games.
- Descriptive only: 22 vs 10 boss deaths.
- `rollout3` won 89.8% here, on the ADR-0034 defaults (§472's `rollout3` 84.4% on other seeds and older code).

No change (prereg decision): `rollout3` stays the research configuration. Raw data:
`/mnt/project-files/ooc-rollout0-sims-475/wNN.tar` (extract to `wNN/out/`).
