# Result: turn-dominance (2026-10-23)

Run: RUN_COMMIT bb425024 (code 687e6dcf, binary b62e6190, v3), 8 workers, 12:51-13:40Z. `verify_campaign.py`: 512 of 512
units OK, 0 missing, 0 bad, 0 duplicates, one run commit; every unit rc=0. `analyze.py` output: `result.json`.

512 A20 runs (127 Heart kills, 24.8%), 268,374 searched Silver roots; 267,389 classified (`ok`), 985 capped at 200k
executions (0.4%), no errors. Enumeration took 1,095 s of 73,989 s run time (1.5%); median 20 action executions per root.

## Pre-registered headline

Silver's chosen root edge is **materially** dominated at **0.65%** of classified roots (1,751 of 267,389;
seed-clustered 95% interval [0.59%, 0.73%]). That is below 1%: **DROP**.

| subset | material | raw (any field) |
|---|---|---|
| all | 0.65% [0.59, 0.73] | 1.37% [1.28, 1.47] |
| monotone gate (exact dominance) | 0.08% (2 of 2,484) | 1.53% |
| act 1 / 2 / 3 / 4 | 0.46 / 0.78 / 0.78 / 0.32% | 1.89 / 1.35 / 1.10 / 0.56% |
| normal / elite / boss | 0.70 / 0.61 / 0.60% | 1.48 / 1.48 / 1.03% |

## Descriptive

- Where it happens: 88% of the material flags (1,539 of 1,751) are Silver choosing End Turn with energy left while a
  line that deals damage, applies a debuff or adds needed block exists; the rest are card-order or target choices.
  Most frequent: Nemesis 142, Champ 123, Three Sentries 80, Awakened One 78, Three Darklings 73. Per turn, 1,734 of
  58,099 turns (3.0%) contain one material flag, about 3.4 per run.
- Silver ranks these lines higher itself: at 99.4% of material flags its own Q for the chosen edge is above the best
  non-dominated edge (median +0.55 points). The choices are not under-searched; Silver's leaf or score values the
  dominated line more (for example the energy-waste term and rollouts that play the unspent cards next turn).
  Pruning would override the evaluation, not save budget.
- Pruning upside as a speedup: 41% of roots have at least one dominated edge, but Silver spends only 2.2% of its root
  visits on them.
- Only 50% of chosen edges and 41% of whole roots are closed (every line deterministic); mid-turn draws and other
  chance cut the rest, as expected for Ironclad.
- Outside the monotone gate the dominance is naive (on-death effects, splits, HP thresholds), so 0.65% is an upper
  bound on real mistakes.

## Interpretation

Turn-level enumeration with dominance pruning has no meaningful target in Silver's production play: under 1% of
decisions pick a materially dominated line, those are near-ties by Silver's own values, and the visits it would free
are about 2%. The small remaining signal (ending the turn with energy unspent) is a leaf/score question, not a
search-structure one. Snapshots of the first 40 raw-flagged roots per run are in the rows if anyone wants to solve a
sample exactly later.
