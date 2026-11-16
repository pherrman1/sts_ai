# Order dominance pilot (#1057): result (2026-11-15)

**Decision: DROP** (PREREG rule: both dom:16000 and dom:8000 have point estimates ≥ 0 on the paired and the frontier
comparison).

Run: 32 A20 runs, seeds 111980000-111980031 (§797's block, reused), 4 lanes in the thread's cloud container,
17:43-20:45 CET. Code faebbc9, binary sha256 4672e0920c2ec42d (linux-gcc-release). 32 / 32 rc 0, sentinel 0 / 32 runs
differing (play bit-identical to §797, so the option-off path is unchanged in whole runs). Raw units:
`/mnt/project-files/order-dominance-pilot/units.tar` (sha256 ff7c1b32f04a534f). Analysis: `analyze.py`, `results/result.json`.

## Equal-CPU picks (16,946 roots; loss in Silver Q, run-clustered bootstrap 10,000, 95 %)

| budget | loss pruned | loss §797 | paired Δ | 95 % | CPU ratio | frontier Δ | 95 % |
|---|---|---|---|---|---|---|---|
| 16k | 0.445 | 0.445 | +0.000 | [−0.015, +0.016] | 1.003 | +0.000 | [−0.015, +0.016] |
| 8k | 0.507 | 0.491 | +0.016 | [+0.006, +0.027] | 1.005 | +0.016 | [+0.006, +0.027] |
| 4k | 0.589 | 0.584 | +0.005 | [−0.014, +0.023] | 1.004 | +0.005 | [−0.013, +0.023] |

By group (paired Δ at 16k): hallway +0.009 [−0.003, +0.021], elite +0.005, boss −0.017 [−0.059, +0.026], Shield and
Spear −0.045 [−0.141, +0.042], Heart 0 (no pruning there, see below). No group shows a gain whose interval excludes 0;
the 8k loss comes from hallway fights (+0.020 [+0.006, +0.034]).

## Frequency

- Played (unpruned) tree, nodes with ≥ 16 simulations: 45 % of searched roots hold a dominated edge; 2.5 % of tested
  card edges are dominated; **2.2 % of all simulations** entered a dominated edge first on their path (elite 3.8 %,
  boss 2.1 %, hallway 1.9 %, Shield and Spear 2.0 %, Heart 0).
- Pruned searches: 7.2 % of card edges pruned per tested node; 5.5 % of tested nodes guarded (Champ, Time Eater,
  Mystic/Centurion); the test costs 0.46 % of the search's CPU.
- **Heart: never.** Invincible decrements with damage, so two orders that deal different damage never compare equal.

## Soundness (descriptive)

Dominated pair vs its dominator in the played tree, both ≥ 256 simulations: 2,807 pairs; the dominated child's
max-backed Q is higher in 34 % (by > 1 point in 8 %); mean difference −0.48, median −0.07. Consistent with exact
dominance under search noise (max-backed Q of two subtrees with different visit counts), no sign of a missing guard.

## Interpretation (Inference)

Pruning frees about 2 % of G16's simulations, and Silver's own search already puts little budget into the dominated
orders (it ranks them low). Freeing 2 % of the budget is worth about 0.06 Q per doubling (§797) × log2(1 / 0.98) ≈ 0.002 Q, far below this pilot's resolution, and the measured paired deltas are ≥ 0. A full 256-run block would
narrow the interval about 2.8× and could at best show an effect of that size, so it is not requested.
