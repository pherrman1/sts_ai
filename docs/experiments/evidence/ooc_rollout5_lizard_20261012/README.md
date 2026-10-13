# rollout5 with the Lizard-capable CTM (ledger §446)

Plan: [PREREG.md](PREREG.md), launch gate [RERUN-423-70000000.md](RERUN-423-70000000.md) (failed: the Face of Cleric
fix `c7641b07` moved the search, so a same-commit control ran), smoke [SMOKE.md](SMOKE.md). Run commit `b6d00dd0`, code
`3b06c924`, `one_combat` sha256 `10dc2616…`; all 16 workers' `FROZEN.txt` name the same run, code and binary. Seeds
70000000–70000127 (the §422 cohort). 16 cloud workers (8 × `r5liz`, 8 × `lizard`), launched by the coordinator.

## Validity

16/16 tars match the `tar_sha256` in their `DONE.txt` (checked by the coordinator from a second container and again
here). `lizard`: 128/128 units rc=0. `r5liz`: 127/128 rc=0; seed 70000087 rc=1 with
`[bestbench-seed-failure] native Silver backend: stall: exceeded 1000 decisions seed=70000087 floor=24 encounter=34`, an
allowed stall, so it drops out of every pair as pre-registered (127 pairs). No restarts. All 256 logs print the arm's
`"leafCombats"` (5 or 3), `"simulations":2048`, `"leafValue":"native"`, `"prior":"policy"`, the `pathb_r2_lizard`
`combatModel`, `"activeLizardCorrection":true` and `[ctm-research-candidate] candidate_id=pathb-r2`. No hash mismatch in
the §423, §430 or §422 files read. Hashes (tars, then the extracted files the analysis reads): [data-sha256.txt](data-sha256.txt).

## Result ([report.json](report.json), `tools/analyze_rollout5_lizard.py`, 127 pairs)

| | `r5liz` (§446) | `lizard` same commit | §423 `lizard` | §430 `r5` | §422 rollout3 | §422 off |
|---|---|---|---|---|---|---|
| CTM / commit | Lizard / `3b06c924` | Lizard / `3b06c924` | Lizard / `cf801ef2` | #418 / `0ee840b1` | #418 / `cd405b4c` | – |
| wins (of 127) | **113 (89.0%)** | 111 (87.4%) | 111 | 111 | 115 | 100 |
| Δwin r5liz − this [95% CI] | – | **+1.6 [−4.7, +8.7]** | +1.6 [−5.5, +8.7] | +1.6 [−5.5, +9.4] | −1.6 [−8.7, +5.5] | +10.2 [+1.6, +18.9] |
| discordant r5liz / this, McNemar p | – | 10 / 8, 0.81 | 12 / 10, 0.83 | 13 / 11, 0.84 | 9 / 11, 0.82 | 22 / 9, 0.03 |
| Δfloor [95% CI] | – | +0.13 [−0.70, +0.94] | +0.13 | +0.39 | +0.19 | +1.02 [−0.09, +2.17] |
| Δ end HP | – | −0.1 | +0.3 | +2.8 | −3.1 | +10.0 |
| boss deaths | 8 | 13 | 13 | 10 | 10 | 23 |
| seconds per run | 887 | 592 | 1,080 | 1,455 | 938 | 57 |
| MCTS CPU per run | 803 s | 511 s | 995 s | 1,368 s | 851 s | – |
| simulations per run | 126k | 125k | 125k | 88k | 106k | – |
| V4 fallback share | 2.9% | 2.4% | 2.4% | 37.1% | 19.9% | – |
| support aborts per run | 0.6 | 0 | 0 | 43.8 | 21.9 | – |

**Primary label: NOT_SHOWN** (r5liz − same-commit `lizard`, CI spans zero). Counting the stalled seed 70000087 as an
`r5liz` loss instead (the three rollout3 controls lost it at floor 33; §430 `r5` and §422 off won it) gives 113/128 vs 111/128, the same +2 runs.

Same-commit `lizard` vs §423 `lizard` (descriptive, how far the `c7641b07` fix moved rollout3 on these seeds): 111 vs
111 wins on 128 seeds, 2 / 2 discordant; 106/128 runs end with the same won, floor and end HP.

## Reading

- With the Lizard-capable CTM, rollout5 no longer falls back to V4 (2.9% vs 37.1% in §430), but it is not shown to win
  more than rollout3 with the same CTM: +1.6 pp, 10 vs 8 discordant seeds. 127 pairs resolve about ±7 pp.
- Point estimates: rollout5 + Lizard has the fewest boss deaths of any arm on these seeds (8) and ties §422 rollout3
  within two runs; nothing here separates them (**Inference**).
- Cost: rollout5 costs about 1.5x a same-commit rollout3 run (887 vs 592 s). The same-commit rollout3 is much cheaper
  than §423 (592 vs 1,080 s) because of the §436/§437/§439 speedups merged since.
- The §423 gate failure is a simulator rule fix (Face of Cleric), not a search regression; it changed 22 of 128 run
  endings but no net wins. §422-era controls should not be reused byte for byte on commits after #480.

## Decision

No default change (pre-registered). OOC MCTS stays off (ADR-0027).

Raw: `/mnt/project-files/ooc-rollout5-lizard-446/` (16 tars, DONE files, `planning-smoke.tar`, `BRIEF-worker.md`).
Seeds 80009000–80009001 (smokes) are now used.
