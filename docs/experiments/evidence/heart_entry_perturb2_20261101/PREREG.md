# Heart-entry perturbation labels, round 2: pre-registration

Status: FROZEN at this commit (prelaunch review before launch). Philipp: "Go auf 16 workern" (2026-11-01 07:20Z).

## Why
§731 produced 16,000 paired Heart fights on 1,000 Heart-entry states. §732 and §733 found that at this size no
flexible model learns more than the average price per kind of change (A and Silver's leaf both −0.0014 against
predicting no effect, an operator-mean predictor −0.0011). Philipp chose more labels (decision card, 2026-11-01
07:09Z). Round 2 labels the remaining 3,253 distinct Heart-entry states the same way, for 4,253 bases and 68,048
fights in total.

## Design (as §731, changed only where stated)
- Bases: `make_variants.py` (§731, unchanged) run with N = 4,253 on the same heart.pkl and seed 20261031; its first
  1,000 lines are byte-identical to §731's variants (checked), lines 1,000-4,252 are this round's bases (global base
  index = 1000 + line). Same 16 variants per base: control, reseed, 14 single changes (operator mix below).
- Play: `one_combat act4replay`, one fight per (base, variant), the research Heart search of §723/§724/§731 (learned
  stop gbt-0cac7cc64364 ≤ 10k per root, one-action roots unsearched, Act 4 strong off, node reuse cap 262,144,
  g7f_E root table and prior), same environment as §731's `run_unit.sh`.
- Seeds (new, from free blocks): battle seed 111341024 + J for every variant of line J except the reseed, which uses
  111350256 + J; J = 0..3,252, so 111341024-111344276 and 111350256-111353508.
- Binary: main e55f4827 (b8f0628b…). Its build inputs differ from §731's f063e9ff only in
  `apps/one_combat/ooc_mcts_adapter.*` and `run_driver.cpp` (STS_OOC_VALUE_CHOOSER, out-of-combat, default off).
  Equivalence smoke: §731 units replayed with this binary must give identical rows (SMOKE.md).
- Operator counts (14 per base, 45,542 changes): hp_down 5,658, card_add 4,240, card_remove 4,192, relic_remove
  4,184, relic_add 4,170, card_upgrade 4,137, relic_counter 3,438, potion_add 3,212, hp_up 2,757, potion_swap
  2,732, potion_remove 2,681, max_hp_up 2,116, max_hp_down 2,025.

## Checks (`analyze.py` = §731's with this round's seeds; frozen)
A base counts if its unit ended with rc=0 and all 16 fights are valid. CIs: bootstrap over source seeds (10,000,
seed 20261101). Sign checks and **labels usable** as §731 (HP up/down, potion added/removed, card upgraded, max HP
up; usable = no INCONSISTENT sign). Co-reported as §731, plus each operator's effect next to §731's (replication).
Output `labels.csv` (global base index) and `labels_all.csv` (both rounds) for the next model fit, which gets its own
pre-registration before any fitting on round-2 labels.

## Cost
3,253 units × 16 fights ≈ 52,000 Heart fights; §731 averaged 44 CPU-s per fight → ≈ 640 CPU-h. With 4 lanes per
worker: 16 workers ≈ 10 h, 32 workers ≈ 5 h. Share: ≈ 65 MB input + ≈ 320 MB of unit tars, ≈ 3,300 files.
Authorized: 16 workers (Philipp, 07:20Z), ≈ 10 h.
