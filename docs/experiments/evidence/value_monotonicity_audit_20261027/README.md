# OOC value counterfactual monotonicity audit (issue #886, plan, 2026-10-27)

Written before the audit run. Diagnostic only: no training, no gameplay change, no new seeds.

## Question

Does the active A20 OOC value estimator violate same-state dominance (less current HP, or one card left
un-upgraded, must not be worth more), and do the violations change decisions?

## Active value path (preflight at main ed2dcb2)

- At A20 the OOC search runs only at map roots (ADR-0061); student_sel decides the other screens from its policy.
- The search leaf is rollout3: three imagined combats (CTM) and the screens in between (student_sel policy), ending in
  the public X2-B GBT (`models/candidates/v_win_x2b_public_trees.txt`, 1006 trees, 428 features) mapped per act with
  M0 (ADR-0057, sigma(a_act + 1.0535 logit X2-B)). M0 is strictly increasing within an act, so X2-B's sign is the
  leaf anchor's sign.
- X2-B reads `curHp`, `maxHp` and, for cards, `dNN` (copies) and `uNN` (upgraded copies) for 93 card ids. An upgrade
  of any other card changes no input: X2-B is blind to it by construction (`run_features.cpp::richFeatureVec`).
- No learned value head is read by the A20 search. student_sel's value head and the SR learning-curve heads
  (25/50/100 %, data branch `claude/az-gen2-data`, 5d7a2ec / 0d84e2c and `gen2/value-sr-crn`) are scored as a
  secondary comparison only.

## Instrument

`STS_OOC_SIBLING_MONO=1` (this PR, research, default off) on the sibling capture: each captured depth-1 leaf of a
map root (a sampled successor of one root action) also scores paired variants in the same forked child:

- **hp:** current HP −24, −12, −6, −3, −1, +1, +3, +6, +12, kept within 1..maxHp;
- **upgrade:** the first upgradable copy of each card id in the deck, upgraded once.

Each variant edits only the leaf's own snapshot and is restored before the next (the full state string must match,
`restoreError` otherwise); candidate metadata is recomputed for each. Recorded per variant: the rich-feature diff
(must be exactly `curHp`, or exactly that card's `uNN`, or nothing for a Searing Blow already upgraded), X2-B, the
calibrated leaf anchor, heart1's value head, and 16 rollout3 leaf evaluations on the repeats' streams (rollout r of
every variant uses repeat r's seed, common across the root's leaves). The base variant's rollouts must reproduce the
leaf's own repeats exactly (determinism check). The mono capture keeps the A20 M0 default (the plain sibling capture
turns it off), so the search, and the game, are those of the uncaptured run.

## Data (no new seeds, pending Philipp's go)

§683 MAP seeds 111374100–111374107, replayed with the §695 replay configuration (`mono_unit.sh`; the same seeds
#881 freezes its roots from), `STS_OOC_SIBLING_EVERY=1`, `MAX_DEPTH=1`, `MAX_LEAVES=24`, `REPEATS=16`,
`COMMON_SEEDS=1`, `MONO_REPEATS=16`. Each replay must reproduce its §683 MAP trace (`trace_check.py` of §695);
a replay that diverges is excluded and reported.

## Classification (fixed now, `analyze.py`)

- **HP pairs** are mechanically dominating unless flagged: act 1 with Hexaghost as the boss (Divider scales with
  current HP), Red Skull (Strength at ≤ 50 % HP), Meat on the Bone (heals only at ≤ 50 % HP). Flagged pairs are
  reported separately as mechanical exceptions. Inference: a policy that plays differently at different HP (rest vs
  smith) is part of the estimator, so the bot-policy value need not be monotone even where the game value is.
- **Upgrades:** class P (only damage/block/magic numbers or cost change) vs class H (draw, innate, exhaust/ethereal
  removal, choice instead of random, unlisted cards): P is dominance modulo enemy HP-threshold mechanics, H is a
  heuristic expectation, not a proof.
- **Violation:** a value change against the dominance direction. X2-B ties (piecewise-constant trees) are counted
  separately, as is "model blind" (no input changed). A rollout violation is material when it exceeds 2 paired SE.
- **Ranking impact:** an action's value is the mean base rollout value of its captured leaves; a violation could
  reorder the root when its wrong-way change exceeds the gap to the adjacent sibling action in that direction.
- **Secondary:** `sr_heads.py` rebuilds every variant's public record from the leaf's record (HP is
  `obs.fixed_observation[0]`, an upgrade adds 1 to `obs.deck.upgrades[i]`) and scores it with heart1score. The rebuild
  must reproduce the capture's student_sel values exactly.

## Smoke (implementation check only, not evidence)

Seed 111374100 replayed with `MAX_LEAVES=64`, stopped after three map roots: the first 76 of 399 §683 trace rows
match; 131 leaves, 1,601 pairs; no feature-diff, restore or determinism failure. A first smoke without the M0 fix
diverged from the §683 trace at row 3, which is how the sibling capture's calibration switch was found. The record
rebuild reproduced student_sel's captured values with max deviation 0.0.

Knowledge impact: environment-variables.md documents `STS_OOC_SIBLING_MONO`; results go to the ledger when run.
