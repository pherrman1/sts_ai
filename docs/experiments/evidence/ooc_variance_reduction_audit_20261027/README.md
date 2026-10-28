# OOC rollout variance reduction: repository audit and death-share decomposition (issue #883, 2026-10-27)

Offline only. No seeds, no new runs. Baseline: `main` `ed2dcb2b`.

## Data
The §644 common-seed sibling capture (`ooc_sibling_crn_capture_20261022`): 320 A20 sources, RUN_COMMIT `9fad3f60`,
every searched root at depth 1, 32 rollout3 repeats per root child, `STS_OOC_SIBLING_COMMON_SEEDS=1`. The unit tars
are on the share at `/mnt/project-files/ooc-sibling-crn/units/` (320 tars; `sha256sum /mnt/project-files/ooc-sibling-crn/units/*.tar | sha256sum`
= `4d173aaf…`, i.e. the hash of the glob-ordered `sha256sum` lines including the absolute paths). Only the `*.sib.jsonl.gz` files are read.

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
  indicative only. q(1 − q)m² is a population-scale term; divided by the ddof = 1 leaf variance it gives the reported
  share, which is conservative (against the population variance it is 0.916 VALIDATION, 0.907 TRAIN). The ratio is
  indicative only: a rollout has up to three combats, and the survival probability varies with the sampled path.
- **Sibling level:** for every pair of root children with different actions, d_r = v_i^r − v_j^r over the 32 common
  repeats. Reported: var(d) / (var v_i + var v_j) pooled over pairs (the CRN ratio), the share of Σ_r (d_r − d̄)²
  that comes from repeats where exactly one sibling died, and var(d | both survived) / var(d). Pairs with var(d) = 0
  (perfectly coupled; 28,607 VALIDATION, 73,063 TRAIN) are kept with numerator 0.

## Result
| | VALIDATION | TRAIN |
|---|---|---|
| leaves | 158,048 | 420,939 |
| mean death rate per rollout | 0.141 | 0.125 |
| leaves with at least one death in 32 repeats | 64.4% | 61.6% |
| leaf variance share of the death term | **0.887** | **0.879** |
| one-event RB variance ratio (indicative) | 0.074 | 0.084 |
| sibling pairs | 1,107,451 | 2,881,016 |
| CRN ratio, pooled over row pairs | 0.543 | 0.555 |
| repeats with a discordant death (mean over pairs) | 0.108 | 0.097 |
| share of sibling-difference SS from discordant-death repeats | **0.874** | **0.867** |
| var(d \| both survived) / var(d) | 0.094 | 0.094 |

By parent screen (1 event, 2 rewards, 3 boss relic, 4 card select, 5 map, 6 treasure, 7 rest, 8 shop):

| screen | pairs VAL | CRN ratio VAL | CRN ratio TRAIN | discordant-death SS share VAL / TRAIN |
|---|---|---|---|---|
| event | 64,109 | 0.515 | 0.529 | 0.877 / 0.877 |
| rewards (incl. card rewards) | 104,888 | 0.419 | 0.409 | 0.878 / 0.878 |
| boss relic | 40,970 | 0.864 | 0.873 | 0.752 / 0.747 |
| card select | 19,919 | 0.135 | 0.423 | 0.744 / 0.803 |
| map | 399,443 | 0.824 | 0.863 | 0.850 / 0.846 |
| treasure | 441 | 0.739 | 0.764 | 0.940 / 0.906 |
| rest | 230,836 | 0.299 | 0.300 | 0.868 / 0.856 |
| shop | 246,845 | 0.525 | 0.517 | 0.923 / 0.916 |

Raw output: [validation.txt](validation.txt), [train.txt](train.txt). Card select rests on only 62 VALIDATION roots,
hence the VAL/TRAIN gap.

**Weighting.** The pooled CRN ratio here sums over all row pairs of a root, so map pairs dominate it. §644's 0.36
(TRAIN 0.37) is measured on the same full capture with `crn_analyze.py`'s weighting (action-merged pairs, averaged per
root, then per source); the independent review of this PR reproduced 0.358 from the same rows. Both say common seeds
help. The by-screen ordering is weighting-robust for the weakest screens (map 0.73–0.86, boss relic ≈ 0.85 under
every weighting tried) but not for event (0.23–0.57).

## Reading
- In rollout3 labels, the CTM death draw carries about 87–89% of both the leaf variance and the sibling-difference
  variance. The HP, potion and hidden-future draws carry the rest.
- Map and boss-relic siblings gain least from common seeds (≈ 0.82–0.87); rest and reward siblings gain most.
  **Inference:** the shared sequential stream desynchronises when siblings take different numbers of draws (different
  rooms, a different potion loop in the near-full CTM, different pool sizes), so map siblings are close to
  independent.
- **Inference:** replacing the sampled death by its CTM probability (conditional Monte Carlo) is the largest single
  candidate. The indicative ratio (≈ 0.08) overstates the gain; the real one needs the experiment in the KB page.

Knowledge impact: [variance-reduction.md](../../../knowledge-base/research/ooc/variance-reduction.md).
