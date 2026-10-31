# Fresh Heart replay at production search: is §726's perturbation gap real or in-game? (2026-10-31)

Follows §726 (#919). In the V_A4 perturbation pilot, perturbed children win the Heart less often than their
unperturbed control: in-game 64% vs 75% on this sample, −10.6 pp [−19, −2]. That holds at equal Heart-entry HP and
even for changes that should help. The results review found no combat-input bug.

A local replay of the same Heart-entry states, rebuilt fresh with `act4replay`, shrank the gap to −3.3 pp [−8, +2]
(control 64%, children 61%). That replay used the incense probe's weaker search (learned stop ≤ 10k).

This run repeats it at production's Act-4 Heart search, so that a fresh rebuild and the in-game fight differ only in
how the state was built. Philipp: "Mach 16 worker" (2026-10-31 19:14Z).

## What runs
- **States:** 240 Heart-entry states from the pilot tars (`build_states.py`, rng 20261031): for each of 60 entries
  whose control reached the Heart, the control plus 3 random children that reached the Heart.
  - Each state comes from the child's CTM `pre` row at the Heart: HP, max HP, deck with upgrades, relics with
    counters, potions, potion capacity.
  - `act4replay` does not carry card misc (Searing Blow, Ritual Dagger), bottles or gold. The combat prior g7f_E
    reads gold (`feat gold`), so the replay plays every state at act4replay's default gold.
  - The tar is `heart_states.tar` (sha256 5daf0619…, holding `meta.json` with the in-game outcome per state).
- **Search:** one unit per state, `one_combat act4replay` with 2 replicates. The battle seed is the entry's seed,
  identical for the control and its children (the second replicate uses seed + 1). The search is production's Heart
  under ADR-0060: flat 40,000 per root, exact root budgets (every root searched), node reuse cap 262,144, g7f_E root
  table and prior, boss prior playouts.
- **Binary:** main 593db4fe (596f14cc…). Its only search change since the pilot binary 93cef2bd is #918's default-off Shield & Spear term, which this run does not set. The smoke `111384012-p00` took 598 CPU-s for one
  fight (won with 10 HP) and printed "flat budget; exact root budgets" and "research node reuse cap 262144".

## Seeds
No new game seeds. Battle seeds are the pilot entries' used seeds and seed + 1. All of them fall inside the used
blocks 111384000-385023 and 111387000-255; the repo seed guard checks only counts.

## Cost
480 fights × about 10 min ≈ 80 CPU-h, so about 1.5-2 h on 16 workers × 4 lanes. Each unit is about 20 min.

## Analysis (fixed before the data is read; `analyze.py`)
- **Primary.** Per entry, take the mean fresh Heart win of its 3 children minus the mean fresh win of its control,
  then the mean over entries, with a seed-cluster bootstrap 95% CI (2,000 draws, rng 7). Compare it with the in-game
  difference on the same states (−0.106).
  - **IN_GAME_ARTIFACT:** the fresh CI includes 0, and the in-game −0.106 lies below the fresh CI. The gap comes from
    how the in-game state was built or played, so look for an engine bug in the perturbed child.
  - **REAL:** the fresh CI excludes 0 and contains −0.106. Perturbed states really are weaker.
  - Otherwise **INCONCLUSIVE**.
- **Also reported.** Fresh vs in-game win rate for controls and for children separately: does the fresh control
  reproduce the in-game 75%? Plus the per-operator fresh differences.
- **Check run.** `analyze.py` on the earlier local learned-stop replay (same 240 states) reproduces −0.033
  [−0.083, +0.017] against in-game −0.106 [−0.194, −0.017]. Under the rule above that run would read
  IN_GAME_ARTIFACT. This run asks whether the verdict holds at production search.
