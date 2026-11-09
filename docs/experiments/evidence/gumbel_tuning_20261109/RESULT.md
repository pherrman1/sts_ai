# Gumbel teacher tuning (result)

Pre-registration: [PREREG.md](PREREG.md). Analysis: `analyze.py` as frozen (stage 2 only adds the reading of
`arms_*.tsv`, which leaves the stage-1 output byte-identical), outputs `results/analysis_screen.json` and
`results/analysis_combine.json`. Follows §772 and
§774 ([max backup at high budget](../gumbel_mb_budget_20261108/RESULT.md)).

## Stage 1: screening

### Run

- Scout: run commit 220db5a8, 500 units on 40 workers, 2026-11-09 12:49-13:56 CET, 500/500 rc 0, 104.5 lane-h.
- Stage 1: run commit b641060e (code 9279ce26, binary e5ba1aad), 40 workers, queue schedule, 4 lanes each. The first
  unit started at 14:08 CET, the last ended at 18:12 CET on 2026-11-09. Unit wall time sums to 567 lane-h (projected
  769 with 1.5 per arm copy); the median unit took 28 min, the longest 60 min (`111860017 3 scr062`).
- Every unit was claimed once. One unit (`111860041 1 scr013`) left a `failed` mark with `rc=upload`, but its tar is
  on the share and verifies.
- `verify_campaign.py`: 1,262 of 1,262 units OK, 0 extra tars. All 1,262 units rc 0; nothing excluded.
- `analyze.py screen`: 1,207 screening fights (304 design, 903 more), **0 dropped**, 0 conflicts between copies seen in
  more than one unit.

### Reproduction (gate for the pairing)

Every unit's fights are the scout's (1,262 of 1,262). Production copy 0 equals the scout's in 28,583 of 28,643
compared fights (99.79%). Both rates are ≥ 99%, so the result is **PAIRED**. The 60 differing copies include fights on
a floor with two combats (the Colosseum event): `analyze.py` keys the scout's fights by floor, so the first of two
fights on one floor is compared with the scout's second (seed 111860055 floor 30: the unit's list of fights equals the
scout's). This only lowers the copy-0 rate; arm fights (elites and bosses, one per floor) are not affected.

### Results (HP lost per fight, seed-clustered bootstrap, 10,000 resamples, 95%)

**gnr (primary): GNR_HURTS.** gnr − ctl = **+1.58 [+1.14, +2.02]** on all 1,207 screening fights (ctl 13.71, gnr
15.28 HP lost). gnr costs 34.4 s CPU per copy, ctl 36.3 s. Gumbel MuZero's selection below the root loses about 1.6 HP
per elite or boss fight against production UCB below the root, at the same CPU.

**Main effects (primary, 304 design fights)**, high − low; negative = the high level loses less HP:

| factor | low → high | high − low | 95% | verdict |
|---|---|---|---|---|
| A k (root candidates) | 8 → 32 | −0.11 | [−0.27, +0.07] | INACTIVE |
| B c_scale | 0.5 → 2 | +0.03 | [−0.13, +0.18] | INACTIVE |
| C Gumbel noise | 0 → 1 | +0.13 | [−0.04, +0.32] | INACTIVE |
| D halving budget | equal → back-loaded | −0.02 | [−0.20, +0.16] | INACTIVE |
| E max backup from M visits | 2 → 8 | +0.15 | [−0.10, +0.40] | INACTIVE |
| F UCB exploration | 12.5 → 50 | +0.25 | [+0.08, +0.41] | LOW_BETTER |
| G prior bonus weight | 100 → 1,600 | +0.19 | [+0.02, +0.36] | LOW_BETTER |
| H tree prior from N visits | 2 → 32 | −0.16 | [−0.30, −0.03] | HIGH_BETTER |
| J widening C, end-turn chance nodes | 1.85 → 7.4 | **−1.13** | [−1.35, −0.91] | HIGH_BETTER |
| K widening C, other chance nodes | 1.85 → 7.4 | **+0.59** | [+0.34, +0.86] | LOW_BETTER |

No correction across the ten factors (PREREG: screening only chooses what stage 2 combines). The five root parameters
are all inactive; the active factors are all below the root, and the two widening constants carry most of it, in
opposite directions.

**Secondary.**

- Curvature: mean of the 32 design arms − ctl = +1.00 [+0.50, +1.46]; adjusted for the control's ends of C and D
  +1.08 [+0.56, +1.57]. The control loses about 1 HP less than the average corner of the design: the response is
  strongly curved over these ranges (factors 2 to 4 from the control), or the corners carry large interactions.
- Each design arm − ctl: none is better than the control (best d30 +0.00 [−0.59, +0.56], d03 +0.02, d18 +0.05);
  19 of 32 are worse (worst d07 +2.61 [+1.92, +3.31] and d26 +2.59).
- Two-factor interactions, 21 alias groups (resolution IV): three intervals exclude 0 — AB = JK −0.23 [−0.41, −0.04],
  BG = DJ +0.18 [+0.04, +0.32], CD = GH −0.26 [−0.48, −0.05]. With 21 groups, about one would by chance.
- ctl − production (the scout's `prod` copies on the same copy seeds): −1.26 [−1.64, −0.87] at about 3 times the
  CPU, the teacher's gain over production on these D0 fights (§772 found −1.17 on the Baalorlord states).

### Consequence for stage 2

ACTIVE, by |main effect|: J (high), K (low), F (low), G (low), H (high). GNR_HURTS, so stage 2's arms 4-6 take the
next factor one step further instead of gnr. `combine.py` builds the arms from `results/analysis_screen.json`; the
arms and their units are recorded in PREREG.md before the stage-2 launch.

## Stage 2: combination

### Run

- Run commit ba9302d3 (code 9279ce26, binary e5ba1aad, as stage 1), 40 workers, queue schedule. The first unit
  started at 18:43 CET, the last ended at 20:45 CET on 2026-11-09. Unit wall time sums to 270 lane-h (projected 362);
  the median unit took 27 min, the longest 52 min (`111860153 3 cmb009`).
- `verify_campaign.py`: 600 of 600 units OK, 0 missing, 0 bad, 0 duplicates, 0 extra tars, 40/40 worker DONE files.
  Every unit was claimed once, no `failed` mark, all 600 rc 0.
- `analyze.py combine`: 602 combination fights, **0 dropped**, 0 conflicts.

### Reproduction

Every unit's fights are the scout's (600 of 600); production copy 0 equals the scout's in 14,098 of 14,109 compared
fights (99.92%). **PAIRED.**

### Results (HP lost per fight, seed-clustered bootstrap, 10,000 resamples, 95%; arm − ctl)

| arm | changed parts (the rest = ctl `gsh16+flat16000+mb4`) | mean | arm − ctl | 95% |
|---|---|---|---|---|
| ctl | | 13.11 | | |
| **c2** | `ucb12.5+pw100+tp32+wet14.8+wch1.85` | **12.00** | **−1.12** | [−1.67, −0.59] |
| c1 | `ucb12.5+pw100+tp32+wet7.4+wch1.85` | 12.40 | −0.71 | [−1.26, −0.18] |
| c5 | `ucb6.25+pw100+tp32+wet14.8+wch1.85` | 12.47 | −0.64 | [−1.19, −0.10] |
| x1 | `wet7.4+wch1.85` | 12.48 | −0.63 | [−1.23, −0.05] |
| c4 | `ucb6.25+pw100+tp32+wet7.4+wch1.85` | 12.66 | −0.45 | [−0.95, +0.04] |
| x2 | `ucb17.6777+pw200+tp16+wet5.2346+wch2.6173` | 12.67 | −0.44 | [−0.97, +0.09] |
| c3 | `ucb12.5+pw100+tp32+wet14.8+wch0.925` | 12.70 | −0.42 | [−1.05, +0.22] |
| c6 | `ucb6.25+pw100+tp32+wet14.8+wch0.925` | 13.31 | +0.20 | [−0.37, +0.75] |

**Pick (PREREG: lowest mean HP lost): c2** = `gsh16+flat16000+mb4+ucb12.5+pw100+tp32+wet14.8+wch1.85`. It goes to the
confirmation unchanged. Stage 2 is a pick, not a test: the pick's estimate carries the winner's curse; only the
confirmation counts. Philipp (2026-11-09 20:53 CET, "okay ja lass und c2 in ganzen läufen prüfen. node cap danach
ebenfalls") replaced the pre-registered stage 3 (paired fights at 16k and 64k) by a whole-run test of c2 against §775's
G16 + mb4 and a node-cap test after it: [wholerun/PREREG.md](wholerun/PREREG.md).

Descriptive (from the live view's merge, same fights): c2's CPU is 1.05× ctl's, its death rate 0.5 pp lower. ctl −
production (the scout's `prod` copies) on the combination fights: −1.00 [−1.53, −0.48].

Reading (not a test): stepping the end-turn widening further (c1 → c2, 7.4 → 14.8) gains another 0.4 HP, while the
other further steps (K to 0.925, F to 6.25) lose what c1 or c2 had; F and K are at or past their optimum at the
stage-1 level, J may not be yet.
