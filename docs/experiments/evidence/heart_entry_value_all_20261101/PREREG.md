# All-feature Heart-entry value on both label rounds (stage B3): pre-registration

Status: written while round 2 (#935) was still running, before any round-2 label was read. The only run before
freezing is a `--permute` debug run on §731's labels (labels shuffled within each base); its numbers are not reported.

## Question
Philipp chose more labels after §732/§733 (at 16,000 labels no flexible model priced single changes better than
Silver's leaf). With 4,253 bases (68,048 fights), does §732's all-feature value A now predict single-change effects
better than the leaf's structure, and does its skill grow with the number of training bases?

## Data
Round 2's `labels_all.csv` (§731's 1,000 bases + round 2's 3,253; written by round 2's frozen `analyze.py`) and
`make_variants.py`'s v0..v15.jsonl for N = 4,253 (line = global base). Only bases that pass round 2's validity rule
(rc=0, 16 valid fights) enter; §731's 1,000 all passed.

## Models and fitting (`fit_all.py`)
- A: §732's all-feature GBM, code imported unchanged (grid depth {2, 3, 4, 6} × min child weight {5, 20}, 4-fold CV
  grouped by source seed inside each outer training set).
- L: Silver's S&S win leaf (unused-Lizard-Tail fix), logistic on float64, max_iter 10,000 (as §733).
- 5 outer folds by source seed mod 5 across both rounds (552 source seeds occur in both rounds; all their bases fall in
  one fold).
- Learning curve: A refitted on 25% and 50% of each outer fold's training source seeds (drawn once, seed 20261102) and
  on 100%; all three scored on the same held-out pairs.
- Exploratory ceiling as §732: cross-fit operator-mean predictor.

## Primary
On all pairs (base, k = 2..15; about 59,500): mean of (D − D̂_A)² − (D − D̂_L)², 95% CI bootstrap over source seeds
(10,000, seed 20261102). PASS if the CI upper bound < 0; WORSE if the lower bound > 0; else NOT_SHOWN.

## Co-reported
The primary statistic on round-2 pairs only; A − L at 25/50/100% with CIs; A100 − A50; each model's skill against predicting no effect (A at 25/50/100%, L,
operator mean); A(100%) − A(25%); correlation of D̂ with D; per operator mean D and mean D̂.

## Decision
- PASS → pre-register stage C (A as Silver's S&S win leaf in §724's S&S → Heart chain; runs need Philipp's go).
- NOT_SHOWN with skill still growing at the top of the curve (A100 − A50 CI < 0 and A − L smaller at 100% than at
  50%; `curve_branch` in all.json) → report the curve to Philipp: more labels would help, with a descriptive
  extrapolation of A − L against log2(training bases) and where it would reach 0.
- Otherwise → the single-change labels do not support a general value at this scale; report, no stage C.

## Versions
The verdict is the one computed in the author's container (xgboost 3.0.5, scikit-learn 1.9.1; versions written to
all.json). §733's verdict changed between xgboost 3.0.5 and 3.4.1; a reviewer rerun on another version is reported
next to it.

## Review change before reading round 2
The prereg review found that A100 − A25 < 0 holds even on §731's labels alone (A25 trains on about 190 bases, worse than
predicting no effect), so the "more labels help" branch now uses the top of the curve (A100 vs A50) and the A − L gap.
