# Gumbel budget curve in whole runs: G1 at 2,000, 4,000 and 8,000 simulations against combat B (result)

Pre-registration: [PREREG.md](PREREG.md). Analysis: `analyze.py` as frozen with the PREREG in the run commit 391456b0
(before any unit had finished), output `results/result.json`. Prelaunch review: J, in parallel with the launch, no
blocking finding.

## Run

- Run commit 391456b0 (code 13bb97ec, binary b5090b16 from the share's binary cache), 40 workers × 4 lanes, queue.
  The first game started at 00:02 CET and the last ended at 00:31 CET on 2026-11-10. Game wall time sums to
  41.8 lane-hours (G2 5.8, G4 12.4, G8 23.7). The longest games took 216 s (G2-111378648), 445 s (G4-111378495) and
  929 s (G8-111378417); none came near the 2 h timeout.
- `verify_campaign.py`: 512 of 512 units OK, 0 missing, 0 bad, 0 duplicates, all on run 391456b0. Every unit was
  claimed once (claims snapshot `claims.txt` on the share, 512 lines `.a1`; `claims/` removed after it).
- `analyze.py`: 1,536 games, 512 paired seeds in every contrast, 0 drops, 0 combat aborts (the 1k test's B1 and G1 also
  0 drops).

## Primary: Gk − B1, Heart kill, 98.33% (Bonferroni over three)

| contrast | d | 95% | 98.33% | only Gk / only B1 | CPU ratio | verdict |
|---|---|---|---|---|---|---|
| G2 − B1 | +5.27 pp | [+1.17, +9.18] | [+0.39, +10.16] | 69 / 42 | 2.11× | **G2_BETTER** |
| G4 − B1 | +7.81 pp | [+3.71, +11.91] | [+2.73, +12.89] | 81 / 41 | 4.54× | **G4_BETTER** |
| G8 − B1 | +9.77 pp | [+5.86, +13.87] | [+4.88, +14.65] | 83 / 33 | 8.69× | **G8_BETTER** |

## Per arm (same 512 seeds)

| arm | simulations | Heart kill | reach Act 4 | kills per Act-4 arrival | mean final floor | CPU per run |
|---|---|---|---|---|---|---|
| B1 (combat B, 1k test) | 1,000 flat | 21.88% | 33.59% | 65.1% | 36.11 | 19.1 s |
| G1 (1k test) | 1,000 Gumbel | 22.27% | 29.69% | 75.0% | 35.30 | 18.2 s |
| G2 | 2,000 Gumbel | 27.15% | 36.91% | 73.5% | 37.69 | 40.4 s |
| G4 | 4,000 Gumbel | 29.69% | 41.80% | 71.0% | 39.35 | 86.7 s |
| G8 | 8,000 Gumbel | 31.64% | 42.77% | 74.0% | 39.09 | 166.0 s |
| D (§775) | 10,000, learned stop, Act 4 strong | 30.86% | 41.21% | 74.9% | 38.84 | 247.7 s |
| G16 + mb4 (§775) | 16,000 Gumbel, Act 4 strong | 40.43% | 48.63% | 83.1% | 41.42 | 509.0 s |

Kills per Act-4 arrival are descriptive: the Act-4 subsets differ between arms. Gumbel roots and fresh simulations per
run: G2 522 / 970,859, G4 552 / 2,056,075, G8 541 / 4,041,164 (about 1,860, 3,730 and 7,480 per root, single-action
roots included). No combat stalls.

## Secondary (95% intervals, not gates)

| contrast | Heart (pp) | Act-4 reach (pp) | CPU ratio |
|---|---|---|---|
| G2 − G1 | +4.88 [+1.17, +8.79] | +7.23 [+3.13, +11.33] | 2.21× |
| G4 − G1 | +7.42 [+3.52, +11.33] | +12.11 [+7.81, +16.41] | 4.76× |
| G8 − G1 | +9.38 [+5.66, +13.28] | +13.09 [+8.98, +17.19] | 9.10× |
| G4 − G2 | +2.54 [−1.37, +6.64] | +4.88 [+0.78, +9.18] | 2.15× |
| G8 − G4 | +1.95 [−2.15, +6.05] | +0.98 [−3.13, +5.08] | 1.91× |
| G2 − D | −3.71 [−7.81, +0.39] | −4.30 [−8.59, +0.20] | 0.16× |
| G4 − D | −1.17 [−5.08, +2.73] | +0.59 [−3.52, +4.69] | 0.35× |
| G8 − D | +0.78 [−3.12, +4.88] | +1.56 [−2.73, +5.86] | 0.67× |
| G2 − G16 + mb4 | −13.28 [−17.58, −9.18] | −11.72 [−15.82, −7.62] | 0.08× |
| G4 − G16 + mb4 | −10.74 [−14.84, −6.64] | −6.84 [−10.94, −2.73] | 0.17× |
| G8 − G16 + mb4 | −8.79 [−12.89, −4.88] | −5.86 [−9.96, −1.76] | 0.33× |

D and G16 + mb4 are §775's games on binary 0eabb014; §777's 32/32 sentinel showed b5090b16 replays §775's G16 games.

## Reading (Inference)

- The Gumbel root's Heart rate rises with the budget: 22.3% at 1,000, 27.1% at 2,000, 29.7% at 4,000, 31.6% at 8,000
  simulations. From 2,000 to 8,000 each doubling adds about 2-2.5 pp (neither step resolved alone), at about twice the
  CPU per doubling.
- G8 is not distinguishable from the A20 default combat D (+0.78 pp [−3.12, +4.88]) at 0.67× D's CPU; G4 is −1.17
  [−5.08, +2.73] at 0.35×. This test does not show that either equals or beats D (no non-inferiority margin was
  pre-registered).
- The step from G8 to §775's G16 + mb4 (+8.79 pp) is about four times the 2k-8k doublings, but it is not a clean budget
  step. §775 ran with `STS_SILVER_LEARNED_STOP=1`, which leaves Act 4 strong on: under the whole-run Gumbel root the
  Shield and Spear get the larger of 16,000 and their own 10,000 with prior playouts, and the Heart gets 40,000 with the
  Heart reuse cap of 262,144 nodes (`NativeSilverBackend.cpp`, `act4Strong` and `flatBudget`). G1-G8 ran
  `STS_SILVER_ACT4_STRONG=0`, so Act 4 at their own budget, the Shield and Spear without prior playouts and the Heart
  with the 32,768-node cap. Act-4 reach, which Act 4 strong
  cannot change, rises by +5.86 pp [+1.76, +9.96] from G8 to G16 + mb4; kills per Act-4 arrival rise from 74.0% to
  83.1%. Splitting the Heart gap by those two (descriptive, the subsets differ): about 4 pp come from the higher
  conversion in Act 4, about 5 pp from the higher reach. Act-4 reach itself rises about 3.9 pp per doubling from 2,000
  to 16,000 (36.9, 41.8, 42.8, 48.6%), with no clear break at 16,000.
- Above 16,000 §775 found no gain (G32 − G16 −0.39 pp [−3.22, +2.44], G64 − G32 −0.39 [−3.22, +2.44], Act-4 reach
  49.2 / 49.8 / 49.7%). The budget curve therefore rises up to 16,000 and is flat afterwards; how much of the last
  rise is the budget and how much Act 4 strong is not measured. A G16 + mb4 arm with `STS_SILVER_ACT4_STRONG=0` on
  these 512 seeds (about 72 lane-hours) would split it.

## Decision

**G2_BETTER, G4_BETTER, G8_BETTER** against combat B. No default change. None of the arms beats D, so no candidate for
the separate test against D the PREREG names. For the PPO actors' combat the curve prices the Gumbel root: about
+5 pp Heart for 2× combat B's CPU, +8 pp for 4.5×, +10 pp for 8.7×. Seeds: §775's 111378256-111378767 reused, no new
seeds. Cost: 41.8 lane-hours.
