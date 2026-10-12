# Fresh-seed confirmation: rollout3 at 4096 simulations with broad chance widening (ledger §433)

Plan: [PREREG.md](PREREG.md), independent plan review PASS with analysis-time nits (applied below). Smokes:
[SMOKE.md](SMOKE.md). Run commit `1fb2c300`, code `f82eeadd`, `one_combat` sha256 `bab14cd5…`; all 8 workers'
`FROZEN.txt` name the same run, code and binary. Seeds 76000000–76000255 (fresh). All three arms ran in this run, on
this binary. `off` is the §411 research base with flat exact-10k Silver, not the production default stack, so its win
rate is not the production win rate. 8 cloud workers × 32 seeds × 3 arms, launched by the coordinator.

## Validity

8/8 tars match the `tar_sha256` in their `DONE.txt` (also checked by the coordinator from a second container). 768/768
units rc=0, no restarts, 256/256 pairs. **Silver stalls (`[bestbench-seed-failure]`): 0 in every arm**, so no seed was
dropped and counting stalls as losses changes nothing. Config banners checked by grep: all 256 `combo` logs print
`"simulations":4096`, `"wideningK":4,"wideningAlpha":0.75`; all 256 `rollout3` logs print `"simulations":2048`,
`"wideningK":2,"wideningAlpha":0.5`; both with `"leafCombats":3`, `"leafValue":"native"`, `"prior":"policy"` and the
production `combat_model`; 0 of 256 `off` logs print an `[ooc-mcts-config]` banner. Hashes (tars, then the extracted
files the analysis reads): [data-sha256.txt](data-sha256.txt).

## Result ([report.json](report.json), `tools/analyze_rollout3_confirm.py`)

| | combo | rollout3 | off |
|---|---|---|---|
| wins | 224/256 (87.5%) | 213/256 (83.2%) | 199/256 (77.7%) |
| boss deaths | 15 | 32 | 42 |
| seconds per run (1 CPU) | 1,536 | 893 | 55 |
| MCTS CPU per run | 1,453 s | 815 s | – |
| simulations per run | 189k | 102k | – |
| V4 fallback share | 27.8% | 21.6% | – |

| comparison | Δwin [95% CI] | discordant | McNemar p | Δfloor [95% CI] | Δ end HP |
|---|---|---|---|---|---|
| **combo − off (primary)** | **+9.8 pp [+3.9, +16.0]** | 45 vs 20 | 0.003 | +0.57 [−0.20, +1.38] | +6.5 |
| combo − rollout3 | +4.3 pp [−1.6, +10.2] | 35 vs 24 | 0.19 | +0.35 [−0.35, +1.06] | +0.2 |
| rollout3 − off | +5.5 pp [−1.2, +12.1] | 44 vs 30 | 0.13 | +0.22 [−0.55, +0.99] | +6.3 |

**Primary label: CONFIRMED.**

In both MCTS arms 89–92% of V4 fallbacks are support aborts, and 99–100% of those are active Lizard Tail states the
production CTM cannot price, as in §422–§430.

## Reading

- On seeds no OOC MCTS screen had seen, rollout3 with 4096 simulations and broad chance widening wins more runs than
  MCTS off: +9.8 pp, CI clear of zero, and boss deaths drop from 42 to 15.
- **CONFIRMED does not separate `combo` from plain rollout3** (+4.3 pp, CI includes zero). Plain rollout3 costs about
  half as much (893 vs 1,536 s per run), so a default proposal should weigh both. On these seeds plain rollout3's gain
  over off (+5.5 pp) is smaller than on the §422 seeds (+10.9 pp) and its CI includes zero.
- **The `off` arm may be flattered.** `STS_OOC_PUBLIC_FUTURES` is off in all arms (the §422 environment), so the native
  V4 fallback reads the true upcoming encounters (the #397 information-boundary finding). `off` relies on that fallback for
  every decision and the MCTS arms only for their 22–28% fallbacks, so the leak favours `off` most (**Inference**; not
  measured here).
- Both MCTS arms cost 16–28x the CPU of `off`.

No default change from this run alone (PREREG decision). Raw data: `/mnt/project-files/ooc-rollout3-confirm/wNN.tar`
(extract to `wNN/out/`).
