# OOC rollout variance reduction: repository audit and death-share decomposition (issue #883, 2026-10-27)

Offline only. No seeds, no new runs. Baseline: `main` `ed2dcb2b`.

## Data
The §644 common-seed sibling capture (`ooc_sibling_crn_capture_20261022`): 320 A20 sources, RUN_COMMIT `9fad3f60`,
every searched root at depth 1, 32 rollout3 repeats per root child, `STS_OOC_SIBLING_COMMON_SEEDS=1`. The unit tars
are on the share at `/mnt/project-files/ooc-sibling-crn/units/` (320 tars; sha256 of the sorted per-tar sha256 list
`4d173aaf…`). Only the `*.sib.jsonl.gz` files are read.

That capture ran before the A20 CTM calibration (#845) and the M0 leaf calibration (#817) became defaults, with the
uncalibrated CTM, which over-predicts deaths (§670). The death rates below are therefore higher than today's; the
decomposition is a description of that capture, not of today's leaf.

## Method
[death_share.py](death_share.py) `ROOT VALIDATION|TRAIN` (VALIDATION = seed % 4 == 3, as in §644):
- A repeat is a death when it is terminal with value 0 (a CTM death; a rollout victory has value 1).
- **Leaf level:** with death rate q, survivor mean m and survivor variance s², the leaf variance is
  (1 − q) s² + q (1 − q) m² (exact when deaths score 0). The second term is the share of leaf variance carried by
  the death indicator. "One-event RB ratio" is (1 − q)² s² / var: the variance of (1 − q) × (survivor value), i.e.
  what conditioning on survival would leave if a leaf had one death event with a constant probability. It is
  indicative only: a rollout has up to three combats, and the survival probability varies with the sampled path.
- **Sibling level:** for every pair of root children with different actions, d_r = v_i^r − v_j^r over the 32 common
  repeats. Reported: var(d) / (var v_i + var v_j) pooled over pairs (the CRN ratio), the share of Σ_r (d_r − d̄)²
  that comes from repeats where exactly one sibling died, and var(d | both survived) / var(d).

## Result
| | VALIDATION | TRAIN |
|---|---|---|
| leaves | 158,048 | 420,939 |
| mean death rate per rollout | 0.141 | 0.125 |
| leaves with at least one death in 32 repeats | 64.4% | 61.6% |
| leaf variance share of the death term | **0.887** | **0.879** |
| one-event RB variance ratio (indicative) | 0.074 | 0.084 |
| sibling pairs | 1,078,844 | 2,807,953 |
| CRN ratio, pooled | 0.571 | 0.580 |
| repeats with a discordant death (mean over pairs) | 0.111 | 0.100 |
| share of sibling-difference SS from discordant-death repeats | **0.874** | **0.867** |
| var(d \| both survived) / var(d) | 0.094 | 0.094 |

By parent screen (VALIDATION; 1 event, 2 rewards, 3 boss relic, 4 card select, 5 map, 6 treasure, 7 rest, 8 shop):

| screen | pairs | CRN ratio | discordant-death SS share |
|---|---|---|---|
| event | 64,094 | 0.515 | 0.877 |
| rewards (incl. card rewards) | 104,077 | 0.421 | 0.878 |
| boss relic | 40,970 | 0.864 | 0.752 |
| card select | 19,661 | 0.147 | 0.744 |
| map | 390,558 | 0.859 | 0.850 |
| treasure | 441 | 0.739 | 0.940 |
| rest | 226,767 | 0.311 | 0.868 |
| shop | 232,276 | 0.576 | 0.923 |

Raw output: [validation.txt](validation.txt), [train.txt](train.txt) (the TRAIN run printed only its first two screen
rows).

The pooled CRN ratio here (0.57) weights every sibling pair of a root equally and is dominated by map pairs. It is not
the same weighting as §644's 0.36, which came from the 18-root smoke; both say common seeds help, least at map and
boss-relic roots.

## Reading
- In rollout3 labels, the CTM death draw carries about 87–89% of both the leaf variance and the sibling-difference
  variance. The HP, potion and hidden-future draws carry the rest.
- Map and boss-relic siblings gain least from common seeds (0.86); reward, rest and card-select siblings gain most.
  **Inference:** the shared sequential stream desynchronises when siblings take different numbers of draws (different
  rooms, a different potion loop in the near-full CTM, different pool sizes), so map siblings are close to
  independent.
- **Inference:** replacing the sampled death by its CTM probability (conditional Monte Carlo) is the largest single
  candidate. The indicative ratio (≈ 0.08) overstates the gain; the real one needs the experiment in the KB page.

Knowledge impact: [variance-reduction.md](../../../knowledge-base/research/ooc/variance-reduction.md).
