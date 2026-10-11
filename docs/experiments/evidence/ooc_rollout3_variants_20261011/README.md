# Four one-setting rollout3 variants (ledger §427–§430)

Plan: [PREREG.md](PREREG.md), launch gate [RERUN-422-70000000.md](RERUN-422-70000000.md) (passed), smokes
[SMOKE.md](SMOKE.md). Run commit `4eeded75`, code `0ee840b1`, `one_combat` sha256 `3269ece9…`; all 32 workers'
`FROZEN.txt` name the same run, code and binary. Seeds 70000000–70000127 (the §422 cohort); controls are the §422 `off`
and `rollout3` (2048) runs. 32 cloud workers (8 per arm × 16 seeds), launched by the coordinator.

## Validity

32/32 tars match the `tar_sha256` in their `DONE.txt`. Per arm, 128/128 units rc=0, no `[bestbench-seed-failure]`, no
restarts, 128/128 pairs, no §422 hash mismatch. All 512 logs print the arm's `"simulations"`, `"wideningK"`,
`"wideningAlpha"` and `"leafCombats"`, plus `"leafValue":"native"`, `"prior":"policy"` and the production `combat_model`.
Hashes (tars, then the extracted files the analysis reads): [data-sha256.txt](data-sha256.txt).

## Result ([report.json](report.json), `tools/analyze_rollout3_variants.py`)

| | rollout3 (§422) | `s4096` §427 | `wnarrow` §428 | `wbroad` §429 | `r5` §430 | off (§422) |
|---|---|---|---|---|---|---|
| wins | 115/128 (89.8%) | 119 (93.0%) | 101 (78.9%) | 117 (91.4%) | 112 (87.5%) | 101 (78.9%) |
| Δwin vs rollout3 [95% CI] | – | +3.1 [−3.1, +9.4] | **−10.9 [−19.5, −2.3]** | +1.6 [−4.7, +7.8] | −2.3 [−10.2, +5.5] | – |
| label | – | NOT_SHOWN | **WORSE** | NOT_SHOWN | NOT_SHOWN | – |
| discordant arm / rollout3, McNemar p | – | 11 / 7, 0.48 | 9 / 23, 0.020 | 10 / 8, 0.81 | 11 / 14, 0.69 | – |
| Δwin vs off [95% CI] | +10.9 [+2.3, +19.5] | +14.1 [+6.3, +21.9] | 0.0 [−9.4, +9.4] | +12.5 [+4.7, +21.1] | +8.6 [−0.8, +18.0] | – |
| Δfloor vs rollout3 [95% CI] | – | +0.25 [−0.63, +1.06] | −0.44 [−1.52, +0.66] | +0.72 [+0.11, +1.44] | −0.05 [−1.27, +1.12] | – |
| Δ end HP vs rollout3 | – | −0.6 | −9.2 | −1.8 | −5.6 | – |
| boss deaths | 11 | 8 | 22 | 9 | 10 | 23 |
| seconds per run | 936 | 1,784 | 1,290 | 988 | 1,458 | 57 |
| MCTS CPU per run | 850 s | 1,693 s | 1,200 s | 898 s | 1,371 s | – |
| simulations per run | 105k | 194k | 105k | 109k | 88k | – |
| V4 fallback share | 19.8% | 27.6% | 21.1% | 19.7% | 37.1% | – |
| support aborts (all runs) | 2,791 | 4,083 | 2,972 | 2,827 | 5,610 | – |

Support aborts are almost all active Lizard Tail states the production CTM cannot price (Fairy Potion + Tail, Entropic
Brew + Tail), as in §422/§423: 98–100% in every arm.

## Reading

- **Fewer chance outcomes (`wnarrow`) is worse**: it gives back the whole rollout3 gain (78.9%, same as off; boss deaths
  22 vs 11). With 4 arms labelled separately and no multiplicity correction, this is the only arm whose CI excludes zero, at
  p = 0.02. **Inference:** a few sampled outcomes per chance node make Q estimates depend on a handful of draws.
- **4096 simulations and more chance outcomes (`wbroad`) point up but are not shown**: +3.1 and +1.6 pp. Both beat off
  clearly. `wbroad` costs only 5% more than rollout3; `s4096` costs about 1.9x.
- **5 rollout combats (`r5`) is not better** (−2.3 pp) and runs fewer simulations per run (88k vs 105k). It falls back to V4
  on 37% of decisions, almost twice rollout3, because longer rollouts reach more active Lizard Tail states (**Inference**
  from the abort reasons). §423's Lizard-capable CTM removes those aborts but did not change wins at 3 combats.
- **Inference:** the ordering s4096 > wbroad > rollout3 > r5 > wnarrow is consistent with "more and more varied samples
  help, fewer samples hurt", but 128 pairs cannot separate the top three.

No default change (PREREG decision). Raw data: `/mnt/project-files/ooc-rollout3-variants/ARM-wNN.tar` (extract to
`ARM-wNN/out/`).
