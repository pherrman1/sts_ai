# Result: leaf head, on-policy round 1 (2026-10-23/24)

## Verdict

**G4 FAILS, so the round is a negative result**: in the 16-source smoke the retrained net (`onp1`) scores 0.86 points
per fight below qe2e [−3.43, +1.04] (boss fights +2.06), and 1.52 above production [−2.06, +5.92]. G1 (data) passes.
G2 (shift, descriptive) holds in part: qe2e's error is far larger on the states its own search reaches and biased
upward, as predicted, but on the pre-registered comparison (the whole on-policy pack) it is largest in hallway fights,
not in boss fights; boss fights lead only among fights under 40 turns, a split made after seeing the data. G3 (fit)
passes at the margin: `onp1` fits the on-policy states far better than the reference refit (fold-4 RMSE 21.9 against
105.7) and the production states 0.27 points worse (the gate allows 0.3). Both G3 and G4 sit within their noise: the
same fit on 255 of the 256 units (before the last unit arrived) missed G3 by 0.05 and, in an exploratory smoke, beat
qe2e by 2.85 points per fight and production by 5.22 [+1.45, +9.63].

The main finding is outside the gates (descriptive, not pre-registered): **the head draws fights out.** qe2e's value
rises with the turn number beyond anything in its training data (the production pack's longest fight has 44 turns): at
the fold-4 roots of fights that lasted 40 turns or more it predicts 127 points at turns 0-39 and 552 at turns 400-501,
where production's search at the same roots says 112 and −78 (Silver scores a win 0.4 points lower per turn). So its
search puts off the kill. 46 of 11,133 fights (0.4%) lasted 40 turns or more, and 2 runs stopped at 1,000 decisions in
one fight. 12 of the 46 lasted to turn 499 or later: 8 were won in the last two turns before the engine's 500-turn
limit, and 4 hit it and were lost alive. Of the 46, 34 were won, at a cost of 33.6 HP on average (12 ended at 1 HP), 8
ended in death and those 4 at the turn limit. The head-played runs killed the Heart in 17.2% (95% CI 14.2-20.7)
against 25.5% (22.9-28.2) for production in the a20prod campaign (other seeds, same settings apart from the head and
four engine fixes). `onp1` learned the slope: on the same fights its prediction falls from 111 to −118 while the label
falls from 112 to −78. The smoke's 209 fights sample such fights about once.

## Campaign (G1)

RUN_COMMIT db49b351 (code a8b80139, main with #837), one_combat sha256 0feb879d..., 32 workers, 4 lanes each.
`verify_campaign.py`: 256 of 256 units OK, none missing or bad, no duplicates, every unit rc=0, run db49b3515293
(`results/verify.txt`). Wall 20:07-22:19Z: 255 units by 21:11Z (median unit 11 minutes), the last one
(natural_111390216_2) at 22:19Z after 2 h 11 min; 52.8 lane-hours in all (the plan bounded it at 140).

- Runs: 510 of 512 complete (99.6%; gate 95%). The other 2 stopped at 1,000 decisions in one fight (seed
  111390026, Three Sentries, floor 12; seed 111390213, Sphere and Two Shapes, floor 46); their 2,000 roots have no
  fight row and the pack drops them.
- Fights 11,133 (none invalid), roots 283,935, every one with a label (`labelRoots` = roots); `edgeFallbacks` 13
  (0.005%; gate 1%). The engine's loop guard fired once (seed 111390217, the Collector, at 6 HP: 50 free
  decisions without progress).
- Outcomes (`../silver_leaf_a20_prod_20261022/outcomes.py`, `results/outcomes.txt`):

| runs | Heart killed | act 4 reached | act 3 | act 2 | Heart fights won |
|---|---|---|---|---|---|
| this campaign (head plays), 512 natural, seeds 111390000-511 | **88 (17.2%, 95% CI 14.2-20.7)** | 33.2% | 57.0% | 85.0% | 55.7% |
| a20prod campaign (production), 1,024 natural, seeds 111310000-311023 | 261 (25.5%, 22.9-28.2) | 39.6% | 59.6% | 84.7% | 68.1% |

Unpaired (different seeds) and the a20prod campaign predates the four engine fixes in this binary (#831, #833,
#835, #836); out of combat both play student_sel through the production chain.

## Packs (step 2)

`pack_a20.py` with the campaign binary: 281,924 roots (`onpol`, sha256 bab1e106...; 2,000 dropped without a score,
11 for an edge mismatch; `results/pack.txt`). The production pack `a20prod` as in §664 (777,993 roots, 47efc292...).

## Shift (step 3) and G2

`shift.py` on all units (`results/shift.txt`): the head's action is the label's most visited edge at 63.2% of the
roots (act 1 73.0%, act 4 49.6%, boss fights 55.4%); production's search values the head's choice 1.80 points below
its own (boss fights 3.02, act 4 3.71); the played search values the root 9.08 points above the label (RMS 65.4).
The label search inherits 4,408 visits per root, the played search 6,203 (as the checks predicted).

Those averages mix three kinds of fights (`shift_split.py`, `results/shift_split*.txt`):

| fights | roots | agree | label regret | value gap | gap RMS |
|---|---|---|---|---|---|
| under 40 turns, without the Collector fight below | 265,232 | 0.667 | 1.64 | +3.00 | 8.96 |
| - boss fights | 68,961 | 0.565 | 3.01 | +5.62 | 14.09 |
| - elite fights | 77,396 | 0.675 | 1.80 | +2.86 | 7.93 |
| - hallway fights | 111,279 | 0.725 | 0.70 | +1.49 | 4.66 |
| 40 turns or more | 16,594 | 0.131 | 1.56 | +86.73 | 121.16 |
| stopped at 1,000 decisions | 2,000 | 0.249 | 25.10 | +58.05 | 85.54 |

In one 7-turn fight (the Collector, seed 111390217, 109 roots) the played search's root value (its most visited edge's
Q) ran away to 4,294 points at the last decision while the label stayed at 31-36 over the 57 roots where it exceeded
200: the head valued each further free action higher until the loop guard ended the turn, and the fight was lost. That
fight alone makes the RMS of the value gap 60 in fights under 40 turns.

G2, qe2e's fold-4 error against the label (`train_onpolicy.py`, `stalls.py`; RMSE, bias in brackets):

| states | all | hallway | elite | boss | act 4 | turn 6+ |
|---|---|---|---|---|---|---|
| production pack | 16.91 (+0.45) | 9.87 (+0.80) | 16.33 (+0.60) | 24.65 (−0.47) | 29.77 (−0.19) | 19.59 (+1.10) |
| on-policy pack | 98.44 (+26.01) | 145.95 (+48.16) | 21.21 (+6.45) | 32.60 (+11.89) | 42.04 (+20.59) | 221.25 (+110.99) |
| on-policy, fights under 40 turns | 22.35 (+6.88) | 12.98 (+3.83) | 21.21 (+6.45) | 32.60 (+11.89) | | 28.72 (+12.37) |

The prediction holds in part. As predicted, the error is larger on the on-policy pack and biased upward, in boss
fights too (+11.89). It is not largest in boss fights: on the pre-registered comparison, the whole on-policy pack,
hallway fights (145.95) and turns 6+ (221.25) lead, through the fights the head drew out, and boss fights (32.60) lead
only among fights under 40 turns, a split chosen after seeing the data. Some of the boss-fight error may be label
noise: the label search inherits fewer visits along the head's path (3,645 against the played search's 5,733 in boss
fights under 40 turns).

## The stall (descriptive)

`stalls.py` (`results/stalls.txt`): fights of 40 turns or more by encounter: Three Shapes 7, Three Sentries 5, Lots
of Slimes 4, Four Shapes 4, Awakened One 3, two each of Centurion and Healer, Three Darklings, Donu and Deca, Small
Slimes, Two Louse, Three Louse, one each of six more. In those fights (fold 4, 3,390 roots), prediction / label by
turn:

| turns | roots | qe2e | ref | onp1 | label |
|---|---|---|---|---|---|
| 0-39 | 450 | 126.8 | 124.3 | 110.5 | 111.5 |
| 40-99 | 403 | 149.3 | 162.2 | 71.6 | 86.7 |
| 100-199 | 686 | 241.3 | 256.2 | 42.1 | 50.9 |
| 200-299 | 629 | 329.3 | 352.1 | −32.0 | 1.9 |
| 300-399 | 653 | 441.9 | 469.0 | −77.2 | −42.5 |
| 400-501 | 569 | 552.4 | 600.3 | −117.7 | −78.2 |

qe2e's value grows by about 1 point per turn, the label falls by 0.4 per turn, as Silver's score of a win does. The
win-now cap and the turn penalty of `STS_SILVER_LEAF_HEAD_*` exist for this (§655); this round played without either,
as qe2e's smoke row did.

**Known issue (the generators' fight rows; not this round's labels).** The 4 fights lost at the turn limit have fight
rows with `valid` true and `score` 105-171, above all 8 fights won at turn 499-500 (−76 to −140). The fight row's
score is Silver's terminal evaluation (`SilverSearcher::evaluateEndState`). A loss keeps the draw bonus of 0.03 points
per card drawn in the fight with no cap (the survival credit stops after turn 100, "or stalling would pay"), and in
Three and Four Shapes fights it has no energy-waste term. By turn 500 these fights had drawn 2,514-4,612 cards, worth
about 75-138 points, while a win loses 0.4 points per turn; all 4 are Three or Four Shapes fights. This round's label
is production's searched root value (`qchosen`), so it is unaffected. A net trained on the fight rows' `score` from
runs like these would learn that stalling to the limit pays: drop fights with more than 500 turns (as `combatevalgen`
quarantines turn-cap results) or have the generator mark them invalid. Whether the same terminal score pulled Silver's
own search toward the limit in these fights was not measured.

## Fits (step 4) and G3

`train_onpolicy.py` (`results/train.txt`, `results/fits.json`): fold-4 RMSE (bias) against the label.

| test | net | all | hallway | elite | boss | act 4 | turn 6+ |
|---|---|---|---|---|---|---|---|
| production pack | qe2e | 16.91 (+0.45) | 9.87 | 16.33 | 24.65 | 29.77 | 19.59 |
| | ref | 16.87 (−0.30) | 9.91 | 16.46 | 24.43 | 28.96 | 19.42 |
| | onp1 | **17.14** (−0.92) | 10.07 | 16.29 | 25.13 | 29.86 | 20.99 |
| on-policy pack | qe2e | 98.44 (+26.01) | 145.95 | 21.21 | 32.60 | 42.04 | 221.25 |
| | ref | 105.68 (+26.25) | 157.35 | 21.01 | 31.08 | 40.53 | 238.43 |
| | onp1 | **21.92** (+0.59) | 20.44 | 16.80 | 28.89 | 34.86 | 31.52 |
| on-policy, fights under 40 turns | qe2e | 22.35 (+6.88) | 12.98 | 21.21 | 32.60 | | 28.72 |
| | ref | 21.83 (+5.66) | 13.52 | 21.01 | 31.08 | | 29.18 |
| | onp1 | 19.16 (+2.21) | 11.08 | 16.80 | 28.89 | | 20.19 |

- G3: on-policy 21.92 against ref's 105.68 (at least 0.5 below: yes); production 17.14 against 16.87 (at most 0.3
  above: +0.27, yes). **PASS.**
- ref is the same recipe as qe2e on the same data; their production RMSE differ by 0.04 and their on-policy RMSE by
  7 points (the extrapolation into long fights is unstable). Before the last unit arrived the same three fits on 255
  units gave ref 16.89 and onp1 17.24 on the production pack (+0.35, a fail): G3's production half sits within the
  retrain noise of its threshold. The pre-registered fit is the one on all 256 units.
- onp1 is pessimistic on production states in act 4 (−4.8) and boss fights (−2.9).
- Export (`L/export_e2e.py`): onp1_trunk.txt c39df335..., onp1_head.txt 7b0e8ff9... (checkpoint 6f728640...). Parity
  against PyTorch on 300 leaves dumped by exact_combat_solver (20a81523..., Jaw Worm 111333000): max |value diff|
  1.05e-05 points (`results/parity.txt`).

## Exact leaves (step 5)

`L/leaf_exact.py` on the 69,734 leaves (`results/exact_leaves.txt`):

| net | RMSE | bias | same-turn pairs in order | cross-turn pairs in order |
|---|---|---|---|---|
| qe2e | 3.70 | −0.22 | 0.808 | 0.820 |
| onp1 | 3.53 | +0.71 | 0.812 | 0.839 |

## Smoke (step 6) and G4

`run_smoke16.sh` (one_combat 83de6c12..., production at 10,000 simulations against the net as leaf at 50/50
without turn penalty or cap, 16 sources, R = 2, 209 fights per run; `results/smoke_*`) and `pair.py`
(`results/pair.txt`; production's arm identical in both runs, fight by fight). Score per fight, 95% CI over the 16
sources:

| contrast | all fights (209) | hallway (68) | elite (90) | boss (40) | act 4 (8) |
|---|---|---|---|---|---|
| qe2e − production | +2.38 [−0.82, +6.91] | +2.31 | +5.43 | −4.36 | +3.94 |
| onp1 − production | +1.52 [−2.06, +5.92] | +3.14 | +1.96 | −2.31 | −1.63 |
| **onp1 − qe2e** | **−0.86 [−3.43, +1.04]** | +0.83 | −3.47 | +2.06 [−8.46, +14.74] | −5.56 |
| exploratory: the 255-unit fit − qe2e | +2.85 [−0.48, +6.07] | −0.03 | +4.89 | +4.42 | −0.81 |
| exploratory: the 255-unit fit − production | +5.22 [+1.45, +9.63] | +2.28 | +10.32 | +0.06 | +3.13 |

- G4 (onp1 − qe2e positive over all fights and over boss fights, onp1 − production not WORSE): all fights −0.86,
  boss +2.06, onp1 − production upper bound +5.92. **FAIL** on the first condition.
- onp1 − qe2e in HP lost per fight −0.81 [−2.00, +0.19], fights won −0.5 pp [−1.3, 0.0]. Each net drew out one
  fight (more than twice production's decisions): qe2e an elite, onp1 a hallway fight.
- The 255-unit fit (onp1_255: trunk 27d8141e..., head e66394a8...) ran while the last unit was still out; it is not
  the pre-registered net, and its rows are reported only to show the screen's resolution: two fits that differ by
  0.5% of the on-policy data differ by 3.7 points per fight here, about the ±5 the README gave for the screen.

## What follows

As the plan says for a failed G3 or G4: the round goes to the ledger as a negative result, nothing more is proposed
on this line unless Philipp asks, and no default changes (the leaf head flags and `STS_AZGEN_LABEL_SEARCH` stay off).
For any later decision:

- The smoke cannot resolve effects of this size; the run-level gap (17.2% against 25.5% Heart kills, unpaired) is
  the larger signal, and it comes with rare, very costly fights (the stalls and one runaway loop) that 209 smoke
  fights barely sample.
- onp1's value now falls with the turn in long fights as the label does; whether that removes the stalls in play was
  not measured.
- qe2e played without the turn penalty and the win-now cap that §655 introduced against stalling.

## Files

- `RESULT.md` (this file); `stalls.py` and `shift_split.py` (descriptive, written after the pre-registered steps).
- `results/`: verify.txt, outcomes.txt, pack.txt, shift.txt/.json, shift_split*.txt/.json, stalls.txt, train.txt,
  fits.json, parity.txt, exact_leaves.txt; smoke_{qe2e,onp1,onp1p}_analysis.txt, .json and _inputs.txt (onp1p = the
  exploratory 255-unit fit); pair.txt/.json (onp1 against qe2e) and pair_onp1p.txt/.json (exploratory);
  train_255.txt (the exploratory fits on 255 units).
- Nets and checkpoints (not in git): `/mnt/project-files/silver-leaf-onpolicy/nets/` (onp1 trunk and head, the
  onpolicy and ref checkpoints; the exploratory fit in `onp1_255/`; `SHA256SUMS` in each).
- Analysis inputs (not in git): `/mnt/project-files/silver-leaf-onpolicy/analysis/` (the on-policy pack, the
  production pack's seed, turn and label columns, the fold-4 predictions of the three nets, and `smoke_raw.tgz` with
  the three smokes' raw rows for `pair.py` and `analyze2.py`; its `README.md` gives the commands; `SHA256SUMS`). The
  campaign's 256 units are in `/mnt/project-files/silver-leaf-onpolicy/campaign/units/`.
