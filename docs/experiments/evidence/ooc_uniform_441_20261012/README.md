# Deep OOC MCTS with uniform prior and uniform leaf policy (ledger §441)

Plan: [PREREG.md](PREREG.md), written before any cohort seed. Smoke and pairing gate: [SMOKE.md](SMOKE.md). Run commit
`ce614d76`, code `b039e846` (main after #494), `one_combat` sha256 `8f5edf76…`; all 8 workers' `FROZEN.txt` name the
same run, code and binary. Seeds 76000000–76000127, arm `uniform` only; the §433 `combo`, `rollout3` and `off` units on
the same seeds are the paired controls (§433 `combo` seed 76000000 reproduces byte-identically on this binary).
`STS_OOC_PUBLIC_FUTURES=0` is pinned, the value §433 ran with. 8 cloud workers × 16 seeds, launched by the coordinator.

## Validity

8/8 tars match the `tar_sha256` in their `DONE.txt` (w01–w07 also checked by the coordinator from a second container).
128/128 units rc=0, no restarts, no `[bestbench-seed-failure]`, 128/128 pairs. All 128 logs print `[ooc-mcts-config]`
with `"prior":"uniform"`, `"leafPolicy":"uniform"`, `"leafCombats":3`, `"leafValue":"native"`, `"simulations":4096`,
`"wideningK":4,"wideningAlpha":0.75` and the production `combat_model`. Seed 76000125 took 44 min (one long live combat
at floor 21) and was briefly suspected of a hang; it finished on its own before anything was done to it. Hashes:
[data-sha256.txt](data-sha256.txt).

## Result ([report.json](report.json), `tools/analyze_ooc_uniform_441.py`)

| | uniform | combo | rollout3 | off |
|---|---|---|---|---|
| wins | 109/128 (85.2%) | 119/128 (93.0%) | 109/128 (85.2%) | 96/128 (75.0%) |
| boss deaths | 14 | 4 | 17 | 26 |
| mean floor | 48.5 | 50.0 | 49.7 | 49.5 |
| seconds per run (1 CPU) | 477 | 1,579 | 888 | 54 |
| MCTS CPU per run | 376 s | 1,495 s | 811 s | – |
| simulations per run | 226k | 185k | 101k | – |
| V4 fallback share | 23.1% | 28.4% | 22.8% | – |

`combo`, `rollout3` and `off` ran on binary `bab14cd5…` (before the §436/§437 speedups), so their seconds are not
comparable with `uniform`'s; the pairing gate's `combo` seed took 511 s there and 364 s on this binary.

| comparison | Δwin [95% CI] | discordant | McNemar p | Δfloor [95% CI] | Δ end HP |
|---|---|---|---|---|---|
| **uniform − combo (primary)** | **−7.8 pp [−15.6, −0.8]** | 7 vs 17 | 0.064 | −1.54 [−3.08, −0.15] | +1.3 |
| uniform − rollout3 | 0.0 pp [−8.6, +8.6] | 15 vs 15 | 1.0 | −1.19 [−2.80, +0.38] | +2.0 |
| uniform − off | +10.2 pp [0.0, +19.5] | 27 vs 14 | 0.060 | −0.99 [−2.65, +0.55] | +8.7 |

**Primary label: WORSE** (bootstrap CI upper bound below zero). The exact McNemar test on the same pairs gives
p = 0.064, so the evidence is borderline.

## Reading

- Dropping the V4 prior and the V4 leaf policy together costs `combo` wins and floors on these seeds: 10 more losses,
  boss deaths 4 → 14. Which of the two flags carries the loss is not separated (both changed at once, as requested).
- The uniform search still ties plain rollout3 (V4 prior and leaf policy, 2048 simulations) on the same seeds at lower
  MCTS CPU (**Inference** across binaries: 376 s on this binary vs 811 s for rollout3 on the pre-§436/§437 binary; the gate seed ran 0.71x and §437 reports 1.13–1.7x for rollout3, so on equal binaries uniform likely costs about 0.5–0.8x of rollout3) (the uniform leaf skips the native shop planner and the V4 gates, which §437 found to be most of the
  rollout cost), and beats off by +10.2 pp with a CI touching zero.
- `combo` won 93.0% on this half of the §433 cohort against 87.5% on all 256 seeds, so this half favours `combo`
  (**Inference**: chance; the primary comparison is paired, but the gap to `combo` may be smaller on other seeds).

No default change (PREREG decision). Raw data: `/mnt/project-files/ooc-uniform-441/wNN.tar` (extract to `wNN/out/`);
controls `/mnt/project-files/ooc-rollout3-confirm/w01..w04.tar`.
