# rollout3 combo at 8192 simulations and with WIDEN_K=8 vs the same-commit combo (ledger §451)

Plan: [PREREG.md](PREREG.md), committed before any cohort seed. Smoke: [SMOKE.md](SMOKE.md). Run commit `f06f49ee`, code
`19cfc1ae` (main after #505), `one_combat` sha256 `015c90e2…`; all 8 workers' `FROZEN.txt` name the same run, code and
binary. Seeds 83000000–83000127, arms `combo` (§433 combo, control), `s8192` and `wide`, all on every seed.
`STS_OOC_PUBLIC_FUTURES=8` pinned. The leaf and fallback win model is the B0 `v_win` (the default at `19cfc1ae`; after
ADR-0029 rerun with `STS_WIN_NET=1` to reproduce). 8 cloud workers × 16 seeds × 3 arms, launched by the coordinator.

## Validity

8/8 tars match the `tar_sha256` in their `DONE.txt`, and every CSV matches its listed sha256. 384/384 units rc=0, no
`[bestbench-seed-failure]`, 128/128 seeds paired in all arms. Worker 6's container restarted once: its four
interrupted units (`s8192`/`combo`/`wide` 83000093, `s8192` 83000094) were moved to `out/aborted-20261012T223042Z/`
and rerun whole, as the protocol says. Every `.env` holds `STS_OOC_PUBLIC_FUTURES=8` and the arm's
`STS_OOC_MCTS_SIMS` / `STS_OOC_MCTS_WIDEN_K`; all 384 logs print `[ooc-mcts-config]` with `"prior":"policy"`,
`"leafPolicy":"v4"`, `"leafValue":"native"`, `"leafCombats":3`, `"wideningAlpha":0.75` and the arm's simulations
(4096 / 8192 / 4096) and `wideningK` (4 / 4 / 8). `wide` made 0 particle revisits in the whole run (31.8M outcome
particles for 31.8M simulations) vs 9.7M revisits for `combo`. Hashes: [data-sha256.txt](data-sha256.txt).

## Result ([report.json](report.json), `tools/analyze_ooc_451.py`)

| | combo | s8192 | wide |
|---|---|---|---|
| wins | 118/128 (92.2%) | 117/128 (91.4%) | 119/128 (93.0%) |
| boss deaths | 9 | 8 | 7 |
| mean floor | 49.3 | 49.8 | 49.7 |
| seconds per run (1 CPU, 4 units per container) | 546 | 1,054 | 542 |
| MCTS CPU per run | 477 s | 977 s | 472 s |
| simulations per run | 248k | 501k | 249k |
| V4 fallback share | 2.5% | 2.6% | 2.5% |

| comparison | Δwin [95% CI] | discordant | McNemar p | Δfloor [95% CI] | Δ end HP |
|---|---|---|---|---|---|
| **s8192 − combo (primary)** | **−0.8 pp [−7.0, +5.5]** | 8 vs 9 | 1.0 | +0.46 [−0.62, +1.62] | +0.5 |
| **wide − combo (primary)** | **+0.8 pp [−5.5, +7.0]** | 8 vs 7 | 1.0 | +0.37 [−0.81, +1.62] | +0.3 |

**Primary labels: both NOT_SHOWN.**

## Reading

- Doubling the simulation budget costs about 2x MCTS CPU and changes nothing visible in wins or floors on these
  128 seeds. **Inference:** 4096 simulations are past the point where more search helps this leaf; §427 (2048 → 4096,
  +3.1 pp) was already NOT_SHOWN.
- Sampling a fresh chance outcome on every visit (`wide`) costs the same as `combo` and is also not separated from
  it. With §428 (fewer outcomes, −10.9 pp, WORSE) and §429 (wbroad, +1.6 pp), the knob only matters on the narrow side.
- `combo` won 92.2% here vs 87.5% in §433 (other seeds, older binary, `STS_OOC_PUBLIC_FUTURES` off, before the #480
  fix). At this level only 15–17 seeds per comparison are discordant, so 128 pairs resolve about ±6 pp; NOT_SHOWN does
  not mean equal.

No default change (PREREG decision). Raw data: `/mnt/project-files/rollout3-8192-wide-451/wNN.tar` (extract to
`wNN/out/`), smoke `smoke.tar`.
