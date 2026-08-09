# V_combat training-vs-deployment distribution shift diagnosis

**Date:** 2026-08-09

## Decision

Do NOT build an expensive deployment-leaf relabeling pipeline. The
distribution mismatch between combatgen training states and deployed
Searcher3 VNet-query states is too small to justify it.

## Rationale

A domain classifier (XGBoost, seed-split) achieves ROC-AUC = 0.56 on the
task of distinguishing combatgen states from deployed VNet-query states
using only the canonical 1,766 combat features. This is barely above
chance — the classifier cannot reliably tell which population an
individual state comes from.

**Inference:** The two state distributions overlap almost completely.
The concern that motivated this investigation — that MCTS selects
qualitatively different leaf states than the on-policy trajectory
states used for training — is not supported by the evidence.

The §148 finding (major online win-rate improvement from hyperparameter
tuning despite nearly unchanged offline RMSE) therefore more likely
reflects regularization benefits (stronger L1/L2, higher
min_child_weight, lower learning rate) than a distribution-shift fix.

## Alternatives considered

1. **Build relabeling pipeline** (frontiergen + leafrelabel): rejected
   because the distribution mismatch is not the bottleneck. Cost would
   be substantial (serialize battle states, run high-budget searches
   for terminal labels) with no evidence of payoff.

2. **Relabel only a narrow subset**: rejected because deploy queries
   are spread broadly across HP bands, turns, and encounters — no
   narrow subset accounts for a majority of queries.

3. **Covariate-shift mixture retrain** (§137, already closed): the
   previous mixture retrain (combatgen + leafdiag states) did NOT
   improve held-out search-leaf ranking. This diagnosis explains why:
   the leafdiag states are not fundamentally different from combatgen
   states to begin with.

## Evidence

- ROC-AUC = 0.56 (XGBoost, 200 trees, max_depth=6, seed-split)
- Confirmed with SGD logistic regression (AUC 0.24 — essentially random)
- 1,766 canonical combat features, 287k combatgen + 163k deploy states
- VNet predictions on deploy states (mean 32.9, std 23.5) closely
  mirror combatgen labels (mean 36.4, std 24.1)
- Deploy states show modest shifts (higher turns, more monster HP, more
  relics) but the within-class variance dominates

## Status

Accepted. Do not build relabeling pipeline. The distribution-shift
hypothesis is NOT the explanation for offline/online mismatch.
