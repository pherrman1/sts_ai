# Fresh Heart replay of run-1 forks: does the rebuild itself lose Heart wins? (2026-10-31)

Follows §728 (#923). Rebuilt fresh at production search, the pilot controls win the Heart 66.7%, against 75.0% for
the same states in game. Run 1's redrawn-future forks of the same entries are unperturbed too, and they win the Heart
74.4% in game (174/234). The perturbed children win 64.4% in game and 66.4% fresh.

The question: does an `act4replay` rebuild lose about 7 pp on unperturbed in-game states? If so, the children's
in-game deficit may share the same cause, namely state that the rebuild and the in-place edit both lose. Gold and
card misc are the candidates.

## What runs
- **States:** `build_fork_states.py`. For the 60 entries of `heart_fresh_replay_20261031`, it takes the Heart-entry
  CTM `pre` row of each of run 1's forks 1-4 that reached the Heart (234 states, `SEED-bNN.jsonl`) from
  `/mnt/project-files/value-clean-labels-run1/units`.
  - These are the same fields as in #923, bottles included; gold and card misc are not carried.
  - Run 1's base game (b00) matches the #923 control state field for field on all 60 entries, so it is not rerun.
  - The tar is `fork_states.tar` (sha256 c7497c47…, with `meta.json` holding the in-game Heart outcome).
- **Search:** identical to #923. `run_unit.sh` differs only in the file names. Two replicates on battle seeds SEED and
  SEED + 1, which are the same as the #923 control's. Binary: main 6c96c25a. Its only change since #923's 593db4fe is #921's default-off out-of-combat value chooser, which this combat-only run does not touch.

## Seeds
None new. The battle seeds are the used entry seeds and seed + 1, the same seeds #923 used.

## Cost
234 units × about 20 min ≈ 78 lane-h, so about 1-1.5 h on 16 workers × 4 lanes.

## Analysis (fixed before the data is read; `analyze.py`)
- **Primary.** Per entry, the in-game Heart win of its forks minus their fresh win (both as means over the entry's
  forks). Then the mean over entries, with a seed-cluster bootstrap 95% CI (2,000 draws, rng 7).
  - **REBUILD_LOSS:** the CI lies above 0. The rebuild loses Heart wins on unperturbed in-game states, so #923's
    fresh numbers are biased low. The next step is to carry gold and misc into `act4replay`, then compare
    rebuild-equivalent children with controls.
  - **NO_REBUILD_LOSS:** the CI includes 0 and lies below +0.083, the #923 control gap. Forks keep their in-game
    level fresh, which makes the 66.7% of the fresh control look like noise.
  - Otherwise **INCONCLUSIVE**.
- **Also reported.** Win rates for forks and controls, in game and fresh, plus the per-entry fresh-fork minus
  fresh-control difference.
