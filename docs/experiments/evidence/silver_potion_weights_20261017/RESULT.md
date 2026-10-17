# Per-type Silver potion weights vs flat 11, paired whole A20 runs: result (ledger-06 §513, 2026-10-17)

Pre-registration: [PREREG.md](PREREG.md). Analysis: [analysis.json](analysis.json)
(`tools/analyze_silver_potion_weights.py` at the run commit).

## Execution

- RUN_COMMIT `56e03b29` (code `ff78230c`, based on main `da1ce052`, so **pre-#594 shop rules**), `one_combat`
  sha256 `0f4bc4a1…41a5` on all four containers. Independent pre-launch review PASS. Philipp's picks (16:31Z):
  student C OOC, 128 seeds, 4 workers.
- Cohort A20 seeds 111152000–111152127, all three arms: 384/384 units rc=0, no seed failure, timeout, stall or
  restart, no dropped seed. Tars ([worker_tars.txt](worker_tars.txt)) on the share in `silver-potion-weights/`, each
  checked from a second container (hash, 96 units, CSV hashes, seed set, `.env`, student C load line in every log).
- Workers 1 and 2 first launched with a zero-padded W and uploaded empty 0-unit tars; their real runs overwrote them
  before verification. `worker.sh` should refuse a padded W (harness note, no effect on data).
- OOC decision sources from the traces: student C (`heart1`) took 98.9% of OOC decisions in every arm (base 13,347,
  level 13,078, type 12,802), the fixed Match and Keep rule the rest (140–150); V4 took none.

## Result

All three contrasts **NOT_SHOWN** (paired seed bootstrap, 10,000 resamples):

| | base (11) | level (7.8) | type (per type) |
|---|---|---|---|
| mean floor | 36.65 | 35.85 | 35.28 |
| act-3 clears (`won`) / 128 | 36 | 30 | 35 |
| boss deaths | 48 | 58 | 55 |
| reached floor 50 | 49 | 49 | 51 |
| seconds per run | 66.3 | 67.9 | 64.7 |

| contrast | Δfloor [95% CI] | label | Δclears | McNemar p | pairs differing |
|---|---|---|---|---|---|
| type − base (primary) | −1.37 [−3.45, +0.74] | NOT_SHOWN | −0.8 pp (12 vs 13) | 1.0 | 98 |
| level − base | −0.80 [−2.96, +1.36] | NOT_SHOWN | −4.7 pp (10 vs 16) | 0.33 | 98 |
| type − level | −0.57 [−2.55, +1.37] | NOT_SHOWN | +3.9 pp (15 vs 10) | 0.42 | 91 |

Descriptive (from the traces, not pre-registered): potions held at battle start 1.05 / 0.92 / 0.93 and at act-boss
battles (floors 16, 33, 50) 1.27 / 1.15 / 1.14 (base / level / type); potions used per battle 0.40 / 0.41 / 0.41.

## Interpretation

- No effect is detectable at this size: the CIs span about ±2 floors, and both point estimates are negative.
- **Inference:** lowering the weights makes Silver spend potions a little more freely, so it reaches act bosses
  with about 0.1 fewer potions; that is the direction §385 warned about, and no floor or clear gain offsets it here.
- Per the pre-registered decision rule the option stays research-only and the weights are not re-tuned on these
  seeds. The flat 11 stays the default.
- Limits: 128 pairs (Philipp's size); weights measured under the V4 policy (§510) and applied with student C;
  pre-#594 shop rules.
