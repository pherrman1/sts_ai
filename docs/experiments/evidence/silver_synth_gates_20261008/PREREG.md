# Synthetic Silver prior pilot: Gate A / Gate B pre-registration

Frozen 2026-10-08, before any model was trained or any label was inspected
beyond corpus integrity counts. Corpus: `corpus-450376c8/` (README there).
Plan: `ASSESSMENT.md` section 7. Everything here is offline; no gameplay.

## Data, features, split

- Features: the engine's combat feature layout (`combatExtractFeatures`, rich
  block on; `combatFillActionFeatures` for actions), extracted by
  `one_combat silversynthfeatures` from each row's wire state.
- Fold = (seed - 56000000) mod 5 for natural, (seed - 56002000) mod 5 for
  perturbed. Fold 4 = test, fold 3 = validation (early stopping, prior weight),
  folds 0-2 = train. Split is by source seed, never by row.
- Two training arms: **nat** (natural folds 0-2) and **nat+pert** (natural and
  perturbed folds 0-2). **nat+pert is primary** for both gates; nat is the
  shift check.
- Every gate metric is computed on **natural fold 4** only. Perturbed fold 4 is
  reported as a secondary column.
- Models: LightGBM only. num_leaves 63, learning_rate 0.05, min_data_in_leaf
  100, feature_fraction 0.8, bagging_fraction 0.8 (freq 1), lambda_l2 1, up to
  2000 rounds, early stopping 50 rounds on the validation fold.
- CIs: 95% percentile bootstrap, 2000 resamples, clustered by source seed.

## Gate A (learned leaf vs one rollout)

- Groups: natural test roots with continuation labels, >= 2 actions, every
  label replicate valid. Label L_e = mean of the two continuation values.
- Scores per root action e, all on the same probe child (the action executed
  with an independent seed): R1 = first SimpleAgent rollout, R4 = mean of four,
  V = model on the probe child's features. A terminal probe child uses its exact
  terminal score for every predictor.
- Regret = max_e L_e - L at the predictor's argmax (ties: lowest e).
  Concordance = over pairs with L_i != L_j, share ordered like L (score tie 0.5).
- Models: **V_cont** (primary), regression on label children of training-fold
  continuation roots, target = that replicate's continuation value. V_roll
  (secondary), regression on leaf rows, target = their rollout value.
- **Pass**: for V_cont nat+pert, mean(regret_V - regret_R1) has CI upper bound
  < 0 AND concordance(V) > concordance(R1). Pass of a secondary model alone =
  inconclusive. Fail closes variant (a); pass allows only the 32-pair boss
  rollout-cutoff screen named in ASSESSMENT.md.

## Gate B (root prior bonus vs plain UCB, root replay)

- Prior P: LightGBM cross-entropy on (state ++ action) rows of training-fold
  roots with >= 2 actions, target = the 10k root visit share; P normalized
  within each root.
- Search: `silversynthreplay`, native Silver from the wire, root bonus
  w * P(a) / (1 + n_a) on visited root edges (unvisited stay +inf).
- Weight w chosen on up to 2,000 natural validation roots with a second teacher
  from {25, 50, 100, 200, 400} by mean regret at 256 sims (ties: smaller w).
- Test roots: natural fold 4, >= 2 actions, with a second 10k teacher.
  Teacher value T_e = mean of the available Q of the two 10k searches; an edge
  with neither gets the root's lowest T. Regret = max T - T at the replay's most
  visited action. Two replay seeds per root per arm, budgets 256 and 1000 (the
  1000 run continues the 256 tree). Roots whose replayed actions do not match
  the recorded ones are dropped and counted.
- **Pass**: mean(regret_prior - regret_plain) at 256 has CI upper bound < 0, AND
  at both 256 and 1000 the count of root-seed runs with regret >= 3 under the
  prior is no larger than under plain UCB. Pass leads to proposing the 32-pair
  screen (seeds 56001000-56001031); fail stops variant (b) unless a new target
  definition appears.
- Reported alongside, not gating: an oracle prior (the teacher's own visit
  share) as headroom, and the nat-only prior.

## Shift check

Both gates are reported for nat and nat+pert. If nat+pert passes and nat does
not, and perturbed data helps only on perturbed fold 4, the result is
inconclusive.
