# Retained-root adaptive Silver prospective A/B (N16)

Date: 2026-09-16  
Implementation: `ec3a9266966406c130aff18c0077f69bf4df83c9`  
Binary SHA256: `fc5aa161edef33b55666008c91b0c215047530058847c93fd075f73336a5c302`

## Frozen treatment

Fresh roots run exactly 10,000 Silver simulations. Retained roots first run
500 new simulations and stop at 500 only when
`top_two_visit_gap_share >= 0.2932885906040268`. Otherwise the same private
search continues to 10,000. One-action/forced roots remain on the normal
10,000-simulation path. The treatment is implemented by
`STS_SILVER_ADAPTIVE=1` plus `STS_SILVER_ADAPTIVE_RETAINED_ONLY=1`.

Both arms used fresh paired seeds 64--79, Ironclad A0, fair RNG, exact-root
budgets, allocated reuse cap 131072, native OOC, adaptive CTM off, OOC MCTS
off, sequential arms, and the same `one_combat` executable. Control had
adaptive Silver disabled. No expensive shadow 10k searches were added to the
treatment.

## N16 result

| Measure | Flat 10k control | Retained-root treatment |
| --- | ---: | ---: |
| Wins | 10/16 | 11/16 |
| Mean final floor | 48.25 | 47.25 |
| Mean final HP | 36.00 | 39.06 |
| Wall time | 113.05 s | 66.71 s |
| Silver simulations added | 70,160,000 | 41,362,000 |
| Scaling decisions | 7,016 | 6,800 |
| Fresh roots | 398 | 391 |
| Retained roots | 6,618 | 6,409 |
| Exact reroots | 4,556 | 4,425 |
| Reroot fallbacks | 2,460 | 2,375 |

The treatment reduced added Silver simulations by **41.05%** and outer wall
time by **40.99%** in this exploratory pair. It stopped 2,804/6,800 decisions
at 500 (41.24% of all treatment decisions, 42.84% of non-forced decisions,
and 43.75% of retained-root decisions). The 255 one-action/forced treatment
roots and all 391 fresh treatment roots continued to 10,000. Every 500-stop
row had inherited visits, more than one legal action, and a gap at or above
the frozen threshold.

The paired outcomes had five win disagreements, five final-floor
disagreements, and thirteen final-HP disagreements. This N16 smoke is not a
quality qualification or proof of whole-fight action equivalence; the
descriptive gameplay result is compatible with continuing to the planned
fresh N32 prospective qualification. The live question is compute versus
gameplay under retained-tree reuse, not exact reproduction of every 10k
action.

Classification: **`PER_DECISION_SIGNAL_PROMISING`** — retained-root adaptive
search only; fresh-root early stopping remains rejected. The earlier offline
diagnostic's `500` checkpoints were continuation checkpoints on a 10k-generated
trajectory, not independent fresh searches, and are not pooled with this live
policy result.

## Files

- `control/results.csv` and `treatment/results.csv`: paired game outcomes.
- `control/scaling.csv` and `treatment/scaling.csv`: per-decision budget and
  reroot traces.
- `*.meta.json`: executable and configuration sidecars.
- `*.time.txt`: `/usr/bin/time -v` process timing receipts.
- `paired.csv`: seed-aligned outcome comparison.
- `summary.json`: machine-readable validated summary.
- `analyze_live_ab.py`: reproducible validation and summary script.
