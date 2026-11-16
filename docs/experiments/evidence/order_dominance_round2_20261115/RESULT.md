# Order dominance round 2 (#1057): result — INCONCLUSIVE (null at equal CPU)

[PREREG](PREREG.md). Code 12d04dc (binary 8608be73, `bin/sha256.txt` in the units tar), evidence `results/result.json`
(round 1's [analyze.py](../order_dominance_pilot_20261115/analyze.py)) and `results/waste.json`
([analyze_waste.py](analyze_waste.py)). Units: `/mnt/project-files/order-dominance-round2/units.tar` (sha256
b940f6b535f7ea2e…). Thread container, 4 lanes, 2026-11-16 00:33-03:20 CET, 10.5 lane-hours.

## Run

32 / 32 rc 0; 0 runs differ from §797's played choices (the played search observed all rules, never honoring them);
16,946 roots with a §797 reference, 16,970 with `domWaste`.

## Waste (played tree, rules observed)

| group | roots | swap | End Turn (card then End) | state, whole turn | End Turn, whole turn | any rule | root End Turn visits |
|---|---:|---:|---:|---:|---:|---:|---:|
| all | 16,970 | 2.6 % | 6.7 % | 2.9 % | 8.6 % | **11.4 %** | 2.2 % |
| hallway | 7,631 | 2.4 % | 9.0 % | 2.8 % | 10.5 % | 13.3 % | 2.9 % |
| elite | 4,523 | 4.3 % | 8.7 % | 4.8 % | 11.5 % | 15.6 % | 2.9 % |
| boss | 3,388 | 2.6 % | 4.2 % | 2.7 % | 5.9 % | 8.7 % | 1.2 % |
| Shield and Spear | 568 | 2.3 % | 0.3 % | 2.5 % | 1.8 % | 4.0 % | 0.1 % |
| Heart | 860 | 0.2 % | 0.1 % | 0.1 % | 1.7 % | 1.9 % | 0.04 % |

Five times round 1's 2.2 %, mostly a dominated End Turn ("play the card first, then end"). 26 % of roots have a
dominated End Turn. Tests cost 0.8 % of the played search's CPU at `MIN_VISITS=8`. 42 % of tested nodes had the
relaxed comparison off (`relaxGuarded`: one of the damage payoffs in the state; which one is not recorded). The
single smoke seed (27.5 %) was far above the average.

## Picks at equal CPU (all rules honored, root filter on)

| budget | loss pruned | loss §797 | paired Δ | 95 % | CPU ratio | frontier Δ | 95 % |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 16k | 0.461 | 0.445 | +0.016 | [−0.006, +0.042] | 0.99× | +0.016 | [−0.006, +0.041] |
| 8k | 0.490 | 0.491 | −0.000 | [−0.020, +0.017] | 0.99× | −0.001 | [−0.021, +0.016] |

By group no interval excludes 0 (hallway 16k +0.007 [−0.009, +0.024]; boss 8k −0.030 [−0.080, +0.013], 16k +0.043
[−0.023, +0.120]).

## Decision (PREREG rule)

Not ASK_FULL_RUN (no upper bound below 0). Not DROP: the 8k point estimates are −0.0003 (paired) and −0.0012
(frontier), just below 0. Therefore **INCONCLUSIVE**; practically a null result.

## Interpretation (Inference)

- Freeing 11 % of the simulations is worth about log2(1/0.89) × 0.06 ≈ 0.010 Q by §797's slope. That is half the 32-run
  interval width, so this run cannot see it, and the 16k point estimate points the other way.
- Caveat stated in the PREREG: Q_ref comes from the unpruned tree, which scores a pick that avoids a dominated End Turn
  with that tree's noisy values. Only a whole-run gate is unbiased.
- What could still add mass: lifting the relax guard on 42 % of nodes (most guards are payoffs that rarely matter this
  turn) and caching end states so nodes are tested from their first visit (30.8 % vs 27.5 % in the smoke). Both are
  small next to the budget needed to show 0.01 Q (about 8x these runs for a ±0.007 interval).
