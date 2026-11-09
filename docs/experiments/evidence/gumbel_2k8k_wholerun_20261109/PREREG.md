# Gumbel budget curve in whole runs: G1 at 2,000, 4,000 and 8,000 simulations (pre-registration)

**Authorization.** Philipp, 2026-11-09 23:58 CET: "Okay dann baller doch mal gumbel 2k, 4k und 8k auf den gleichen seeds
durch, mit dashboard pls", after the 1k test ([../gumbel_1k_wholerun_20261109/RESULT.md](../gumbel_1k_wholerun_20261109/RESULT.md),
G1 − B1 +0.39 pp). 40 workers as in that test, his count of 23:41 CET. J's prelaunch review runs in parallel with
the launch, as in the 1k test; a blocking finding stops the queue.

## Question

Between combat B's 1,000 simulations (B1, G1: 21.9%, 22.3% Heart) and §775's G16 + mb4 at 16,000 (40.4% on the same
seeds), where does the Gumbel root's Heart rate rise, and does it pass the A20 default combat D (30.9%, 10,000
simulations with the learned stop)?

## Design

- Seeds: the 1k test's 512 (§775's 111378256-111378767), no new seeds. One unit per seed holds the three arms, in an
  order rotated by seed (`run_unit.sh`, `units.txt`).
- Arms G2, G4, G8 = the 1k test's G1 (combat B plus `STS_SILVER_GUMBEL_ROOT=16 STS_SILVER_GUMBEL_ROOT_MAX_BACKUP=4`
  in every fight, Act 4 included, Act 4 strong off) at bestbench 2000 / 4000 / 8000. Nothing else changes, so their
  environment equals G1's.
- Comparison arms reused, no reruns: B1 and G1 from the 1k test (same binary b5090b16, same seeds, same environment
  apart from the simulation count), D and G16 + mb4 from §775 (binary 0eabb014; §777's 32/32 sentinel showed b5090b16
  replays §775's G16 games).
- Binary b5090b16 (code 13bb97ec) from the share's binary cache. Timeout 2 h per game.
- Smoke (local, 2026-11-10 00:00 CET): G4-111378256 rc 0 in 61 s with the Gumbel banner, roots and tree reuse line;
  the launch did not wait for the smoke's other games (same checks, only the simulation count differs).

## Primary (analyze.py, frozen with this file)

For k = 2, 4, 8: Heart kill Gk − B1, paired by seed, seed bootstrap (10,000 resamples, seed 20261109) at 98.33%
(Bonferroni over the three contrasts): **Gk_BETTER** if the lower end > 0, **Gk_WORSE** if the upper end < 0, else
**NO_DIFFERENCE_SHOWN**. No SPRT, every seed runs. A game with rc ≠ 0, a wrong environment or a missing BEST line is a
drop; each contrast uses the seeds where both its games count. More than 10 of this campaign's seeds with a drop:
every verdict **NOT_EVALUABLE**.

## Secondary (not gates)

95% intervals of Gk − B1, Gk − G1, Gk − D, Gk − G16, G4 − G2 and G8 − G4; per arm Heart, Act-4 reach, final floor,
CPU per run and per floor reached; Gumbel roots and simulations per run; combat stalls.

## Cost

Smoke (below) and the 1k test's 18 s per G1 run: CPU about proportional to the budget, so about 36 + 73 + 146 s per
seed before longer runs, about 40-50 lane-hours.

## Decision

No default change. The curve says which budget a Gumbel teacher or PPO actor combat would need. A Gk that beats D at
lower CPU would be a candidate for a separate, pre-registered test against D with Philipp's go.
