# V_A4 Act-4 entry perturbations, pilot (2026-10-30)

Follows §722 (#915). V_A4 is data-limited: the CV learning curve is about −0.01 BCE per doubling, and the old
data is exhausted. Philipp proposed freezing Act-4 entry states and playing realistic perturbations of them
(HP, gold, cards, upgrades, relics, relic counters). The plan is
`/mnt/project-files/value-a4-improve/PERTURB-PLAN.md`, the mechanism `STS_A4_PERTURB` (#917, research flag,
default off). Philipp gave the go for this pilot on 16 workers (2026-10-30 17:41Z).

## What runs
One unit per run-1 Act-4 entry: one `heartoutcomegen` game in run 1's environment
([`../value_clean_labels_run1_20261029/run_unit.sh`](../value_clean_labels_run1_20261029/run_unit.sh), the A20
default of 10-29, verbatim), plus `STS_A4_PERTURB=INDEX:0:16:SEED`.

- The game is replayed unchanged up to INDEX, the entry's first Act-4 decision in run 1 (`units.txt`).
- There `runFullRunOOC` forks K = 16 children, one after the other, on the game's own hidden future (SALT 0), so
  all children of an entry share one future (common random numbers).
- Child 0 is the unchanged control. With SALT 0 it must reproduce run 1's base game from that entry (checked
  after the run, see Verify).
- Children 1-15 apply one perturbation each, drawn from (SPECSEED = SEED, k), from the #917 menu: HP, max HP, gold,
  add or remove a card, upgrade or un-upgrade, add, remove or swap a relic, redraw a counter, add or remove a potion.
- [`a4_perturb.py`](a4_perturb.py) checks the parent's `a4_perturb` row (K children, all exit 0, fork at INDEX in
  act 4) and that every child replays the parent up to the entry, then writes `a4p-SEED.json`. That file holds,
  per child, the perturbation, the entry record after it (heart1-public-record-v2) and the outcome.

## Seeds
Only replays of used seeds, no new seeds. The units are 64 of run 1's 406 dev-pool Act-4 entries (seed % 4 ≠ 3;
536 entries in total), drawn with numpy `default_rng(20261030)`. 47 come from expert-anchored-ab
(111384000-385023) and 17 from card-rule-ab (111387000-255). The run-1 TEST seeds (seed % 4 = 3) are not used, so
the perturbations can only enter training folds.

## Cost (estimate)
- The replay to the entry takes about 14 min (run 1).
- In the #917 smoke 2 (4 processes on 4 CPUs), Act 4 took 6.3-10.3 min per child, mean about 8.5.
- A unit is therefore about 14 + 16 × 8.5 ≈ 150 min, up to about 4 h. In total that is about 160 lane-h.
- 16 workers × 4 lanes = 64 lanes, one unit each, so about 2.5-4 h wall.
- Storage is about 17 games' jsonl per unit, gzip ≈ 0.5 MB per unit and 64 tars.

## Verify (before the analysis)
- Every unit has rc 0 and an `a4p-SEED.json` with 16 children.
- **Control reproduces run 1.** In every unit, the child-0 game rows must be identical to run 1's
  `base-SEED.jsonl` (`/mnt/project-files/value-clean-labels-run1/units/`), apart from the header. A mismatch means
  this binary does not replay run 1. Such a unit's children are then still valid perturbation data, but the
  control is not run 1's base game, and the count is reported.
- Each child's entry record differs from the control's only in its operator's fields (as in the #917 self-test).

## Analysis (offline; the gate is fixed before the run)
- **Gate.** Use the CV of #915 (`../value_a4_improve_20261030/tools/core.py`: dev pool, seed-grouped 5-fold × 3).
  ENS_rc + perturbation rows (children 1-15; their seed's fold decides where they go, so they are only ever in
  training folds of their own seed) is compared with ENS_rc, both scored on the real dev entries. The
  perturbation rows get the source flag `perturbed`.
  - **PASS:** the paired seed-cluster bootstrap 95% CI of the BCE difference is below 0. Then the next step is to
    scale up to a few hundred entries, which needs Philipp's go.
  - **Otherwise:** NOT_SHOWN, and the ledger records it.
- **Secondary.** CRN effects per operator (paired child − control, per entry), as a sanity check of signs and a
  direct read of HP, gold, potion and relic worth at the Act-4 entry.
