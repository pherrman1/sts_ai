# Order dominance round 2 (#1057): more rules, waste and equal-CPU picks at G16 roots (pre-registration, 2026-11-15)

**Scope.** The same small data run as round 1 ([../order_dominance_pilot_20261115](../order_dominance_pilot_20261115/PREREG.md)):
32 A20 runs of §797's seed block, replayed bit-identically in the thread's own container (4 cores), no workers, no new
seeds. No gate, no default change.

Request: Philipp, 2026-11-15 21:34 CET, after round 1's DROP: test more dominance checks, since the mass would matter,
not one small case.

## Round 1 in one line

The order test alone (a then b dominated by b then a) touched 2.2% of simulations; picks at equal CPU did not improve
(DROP).

## Rules (SilverDominance.h, `STS_SILVER_ORDER_DOMINANCE` = rule mask, default 0)

- `DOM_SWAP` (1): round 1's order test.
- `DOM_RELAX` (2): every rule also counts more player block, less monster block and more energy as better. Off at
  states with a damage payoff (Red Skull, Centennial Puzzle, Runic Cube, Self-Forming Clay, Emotion Chip, Meat on the
  Bone, Static Discharge, Blood for Blood).
- `DOM_END_ADJ` (4): End Turn at X is dominated when "card c, then End Turn" reaches an end state that dominates End
  Turn's. End states stop before the first monster acts (hand discarded, end-of-turn relics and powers, monster block
  loss); energy and the per-turn counters are ignored there (not with Ice Cream, Pocketwatch, Art of War).
- `DOM_SEG_STATE` (8), `DOM_SEG_END` (16): every decision node and every end state is compared with the others of the
  same deterministic segment (reached from the root or one chance outcome with no chance node between), whatever order
  of card plays led there.
- `DOM_ROOT` (32): the Gumbel root drops End Turn from its candidates when `DOM_END_ADJ` flags it.
- Monster-HP guard as round 1 (Mystic, Centurion, Champ, Time Eater). A node is tested once it has 8 simulations
  (`STS_SILVER_DOMINANCE_MIN_VISITS=8`), which keeps the tests near 9% of the search's CPU in the smoke.

## Data run

- [record_env.sh](record_env.sh): §797's environment, the played search observes rules 31 (flags computed, never
  honored: `domWaste` rows), and two fresh Gumbel searches per root with all rules honored (63) at 16k and 8k, seeded
  like §797's ladder slots 5 and 4 (`STS_AZGEN_DOMINANCE_LADDER=16000:5:63,8000:4:63`).
- Seeds 111980000-111980031 (round 1's; `run_unit.sh` refuses others). Sentinel: every run's played choices equal
  §797's rows of that seed.
- Smoke (seed 111980003, 67 roots, not part of the decision): any rule 27.5% of simulations (End Turn rules nearly
  all of it), root End Turn 7% of root visits; paired loss 16k +0.027 Q, 8k +0.048 Q.

## Measurements (frozen before the data)

1. **Waste** (played tree, `domWaste`): share of the root's simulations whose path entered an edge flagged by each
   rule and by any rule; root End Turn flagged share of root visits; by group (hallway, elite, boss, Shield and Spear,
   Heart); the tests' share of the played search's CPU.
2. **Equal-CPU picks** (round 1's [analyze.py](../order_dominance_pilot_20261115/analyze.py), §797's metric): loss
   = Q_ref(best) − Q_ref(pick), Q_ref the played 16k tree's max-backed Q; paired dom:b − §797 slot pick at the same
   Gumbel seed, CPU ratio, and frontier against §797's 1k-16k curve; run-clustered bootstrap (10,000, seed 20261115).

## Decision rule

As round 1: **ASK_FULL_RUN** if dom:16000 or dom:8000 has a frontier Δ < 0 with 95% upper bound < 0, or a paired Δ < 0
with upper bound < 0 at CPU ratio ≤ 1.1. **DROP** if both arms' point estimates are ≥ 0 on both comparisons.
Otherwise **INCONCLUSIVE**.

Caveat stated in advance: Q_ref comes from the unpruned played tree, so where the rules change which End Turn or
card line a pick takes, the reference scores it with the unpruned search's noisy values. A pruned pick that avoids a
dominated End Turn is scored by that End Turn's competitor in the unpruned tree, not by a proof. A whole-run gate is
the only unbiased test and needs Philipp's go.
