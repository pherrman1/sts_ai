# Step 0: does an outcome-trained OOC leaf pick better with more own-play games? (pre-registration, 2026-10-09)

Requested by Philipp (2026-10-09, "lets go") as the cheapest first step before any
expert-iteration loop (uniform/V4-prior OOC MCTS, run-victory labels, retrain leaf
and prior). Design rationale: `/mnt/project-files/ooc-selfplay-loop/DESIGN.md`.

Offline only: no gameplay, no seeds, TEST components and E3 TEST states closed.

## Question

The current leaf input X2-B is a GBM on run-victory labels of our own games (#334).
If more such games improved its option ranking, a self-play loop that adds games
could pay off. Does the X2-B recipe's selection gain rise with the number of
training games?

## Data (frozen)

- #334 corpus index `corpus-mixed-1024.json`, SHA-256 `ae56f963...0dfa00`,
  TRAIN/VALIDATION/TEST sources 696/155/173 (checked by `tools.vwin_e1_focal.load_split_tables`).
- E3 corpus (§396), seeds 55000000..999, VALIDATION states only (source split as §396).
- Frozen X2-B tree dump `models/candidates/v_win_x2b_trees.txt` (feature list, NLL reference).

## Arms

X2-B recipe exactly as P0 in §394 (public 457 features, weights 1, depth 6, eta 0.06,
min_child_weight 10, `curHp` monotone, subsample 0.8, colsample 0.7, hist, up to
2,500 rounds, early stopping 50 on all #334 VALIDATION rows), seeds 0/1/2,
prediction = 3-seed probability mean. Nested fractions 1/8, 1/4, 1/2, 1/1 of the
696 TRAIN sources, ordered by SHA-256 of `outcome-curve-v1:<seed>`, in two corpora:

- **SRC (primary):** source-trajectory rows only (`branchId == "source"`): what N games
  of own play with run-victory labels give. 87 / 174 / 348 / 696 games.
- **ALL (secondary):** source plus counterfactual branch rows (X2-B's training set).

## Metrics (VALIDATION)

1. #334 VALIDATION map-row NLL.
2. Selection gain vs V4's chosen option: (a) on #334 VALIDATION sampled sibling
   decisions (`tools.vwin_e1_focal.selection_gain`, all types); (b) on E3 VALIDATION
   card-reward and boss-relic states (`tools.vwin_e3_cf.selection_rows`).
3. E3 card-reward skip-pick share.
4. **Slope per doubling:** per decision, the least-squares slope of its gain on
   log2(fraction) over the four fractions (weights −0.3, −0.1, +0.1, +0.3); pooled
   mean with source-clustered bootstrap (2,000 reps), separately for (2a) and (2b).

## Decision rule (SRC corpus)

- `GO`: on (2a) or (2b) the pooled slope is ≥ +0.005 per doubling with 95% CI
  lower bound > 0, **and** the E3 card-reward skip share at 1/1 is below 1/8.
- `STOP`: on both (2a) and (2b) the CI upper bound is < +0.005. Outcome labels from
  more own-play games do not improve option ranking at this scale; the self-play
  loop is shelved and the result goes to the ledger as a negative.
- Otherwise `INCONCLUSIVE`: report and ask Philipp.

ALL, NLL and per-type numbers are descriptive. Known in advance: NLL improves with
data (`DATA_SCALE_SIGNAL`, §368: X1 half→full TRAIN 0.4729→0.4445); the E3-only
curve was flat (§396 RESULT: card gain +0.005/−0.004/+0.010 at 25/50/100%).
Anchor: ALL at 1/1 is the §394 P0 arm (trees 278/355/373, NLL 0.4237); reported,
not enforced (thread counts may differ).

## Command

```
python3 -m tools.vwin_outcome_curve INDEX E3_ROOT --output build/outcome-curve-<sha8> --threads 4
```
Tool: `tools/vwin_outcome_curve.py` (selftest `tools/test_vwin_outcome_curve.py`).
