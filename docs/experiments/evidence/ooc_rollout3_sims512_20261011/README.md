# rollout3 OOC MCTS at 512 simulations (ledger §424)

Plan: [PREREG.md](PREREG.md), independent review PASS at `3c9493da`, delta PASS at the run commit `ab16de57`
(workers write locally and upload one tar each). Code `cd405b4c`, `one_combat` sha256 `39cdac96…`; all 8 workers'
`FROZEN.txt` name the same run, code and binary. Seeds 70000000–70000127 (the §422 cohort); controls are the §422
`off` and `rollout3` (2048) runs. Smoke 72000002.

## Validity

8/8 tars match the `tar_sha256` in their `DONE.txt`. 128/128 units rc=0, no `[bestbench-seed-failure]`, 128/128
pairs, no §422 hash mismatch. All 128 logs print `"simulations":512`, `"leafValue":"native"`, `"leafCombats":3`,
`"prior":"policy"` and the production `combat_model`. Hashes (tars, then the extracted files the analysis reads):
[data-sha256.txt](data-sha256.txt).

## Result ([report.json](report.json), `tools/analyze_rollout3_sims.py`)

| | r512 | rollout3 (2048) | off |
|---|---|---|---|
| wins | 108/128 (84.4%) | 115/128 (89.8%) | 101/128 (78.9%) |
| boss deaths | 15 | 11 | 23 |
| seconds per run (1 CPU) | 331 | 936 | 57 |
| MCTS CPU per run | 257 s | 850 s | – |
| simulations per run | 29k | 105k | – |
| V4 fallback | 10.3% | 19.8% | – |

- **Primary:** r512 − off +5.5 pp, paired bootstrap 95% CI [−3.9, +14.8] → **NOT_SHOWN**. Discordant 23 vs 16,
  McNemar p = 0.34. Δfloor +0.38 [−0.91, +1.69]; Δ end HP +7.5.
- **Secondary:** r512 − rollout3 (2048) −5.5 pp [−12.5, +1.6]; discordant 7 vs 14, p = 0.19; `within_5pp_of_2048`
  false. Δfloor −0.31 [−1.31, +0.63].
- Fewer fallbacks than at 2048 (10.3% vs 19.8%) because shorter searches hit fewer Lizard Tail states before
  aborting (**Inference**).

## Reading

512 simulations cost about a third of 2048 (331 vs 936 s per run) and land between off and 2048 on every outcome
(wins, boss deaths, floor, end HP). Neither difference is shown at 128 pairs. **Inference:** the gain scales with
the budget rather than saturating by 512, so cheaper budgets give up part of it; 128 pairs cannot say how much.

No default change (PREREG decision).

Raw data: `/mnt/project-files/ooc-rollout3-sims512/w01..w08.tar` (extract to `wNN/out/`).
