# Action plan after Astra's review (2026-10-07)

Goal: an OOC value model that prices picks (card rewards first, then boss
relics), usable later as an MCTS leaf. Following the review, the target is an
**absolute final-win probability** at a **MAP after-state**, uncentered. HP
after a boss is kept only as a diagnostic.

## Corrections accepted

- X2-B was trained on all MAP rows of the #334 corpus, source and branch
  trajectories alike (`tools.vwin_refresh_model`, 696 TRAIN sources), so it
  did see counterfactual branches. "Never sees a different pick" was wrong.
  The open question is whether the branch comparisons were diluted.
- The centered HP target and the mixed horizons are dropped.
- 15% random source actions are dropped for now.
- K=2 pairwise accuracy is not the scaling criterion. The criterion is
  held-out selection gain plus NLL/Brier.

## E0: X2-B at its training boundary (done, cloud, read-only)

X2-B rescored at each branch's first recorded MAP row (the training boundary),
on the 154 cloud #334 sources. Those sources may be in X2-B's training set, so
this view is optimistic.

| Type | Decisions | Best-minus-second gap (median) | Argmax = V4 (random) | Skip best | Win/loss pair accuracy |
|---|---|---|---|---|---|
| Card reward | 154 | 0.0021 | 0.32 (0.26) | 0.40 | 0.60 (205 pairs) |
| Boss relic | 152 | 0.0104 | 0.43 (0.25) | — | 0.70 (238) |
| Campfire | 154 | 0.0115 | 0.59 (0.21) | — | 0.50 (381) |
| Shop | 152 | 0.0039 | 0.34 (0.20) | — | 0.60 (401) |

The boundary does not explain the card-reward failure: the picture is the same
as at the reward screen. Boss relics are priced. Script:
`/mnt/project-files/ooc-card-pricing/` (`boundary.py`).

## E1: focal retrain on the existing #334 corpus (offline, no gameplay)

- **Hypothesis:** branch comparisons were diluted among the many later
  trajectory rows.
- **Data:** the frozen 1,024-source corpus with the same TRAIN/VALIDATION split.
  TEST stays closed.
- **Arms:**
  - X2-B as is.
  - F1: the same XGBoost family trained on focal rows only (the first MAP row
    after each sampled option), with balanced weights per decision.
  - F2: all rows, with focal rows upweighted.
- **Metrics (VALIDATION):**
  - NLL and Brier, overall and on focal rows.
  - Held-out selection gain: the model's choice versus V4's choice, scored by
    the branch outcomes, per type, with source-clustered bootstrap.
  - Sibling ranking (descriptive).
- **Where:** the full corpus is on Philipp's machine, so this runs on a local
  thread. XGBoost CPU training needs Philipp's OK.
- **Decision:**
  - If F1 or F2 shows a clearly positive selection gain on card rewards: focal
    training works, and new data is a scaling question.
  - If not: the corpus has too few or too noisy comparisons, and E3 decides.

## E2: generator v2 (cloud implementation, then an independent review)

Changes to `ooccfpilotgen`:
1. **Horizon:** play to the end of the run. The label is final victory.
   Boss-checkpoint HP and wins are recorded as diagnostics.
2. **Boundary:** finish the current screen under V4, then record the first MAP
   after-state. The immediate post-option row is kept for comparison.
3. **Randomness:** redraw the future before executing the option, so any
   randomness the option itself consumes is part of the K samples. Checks:
   exact replay of an identical branch, visible offers preserved, and the
   effect of option RNG.
4. **Options:**
   - The capped set always keeps the V4 choice and skip/leave.
   - Genuinely equivalent options are deduplicated (for example the same card
     at another deck index).
   - Actual type and act counts are reported.
5. **Cost:** a 12-seed timing run with full-run labels, to measure the cost of
   the remaining suffix.

## E3: first tranche (after E1 and the E2 review, on Philipp's go)

- ~2,000 states, with card rewards and boss relics prioritised, K=2, final-win
  labels.
- Frozen SHA, binary, seeds (55M) and decision rule, following the
  large-research procedure.
- Train an absolute GBM on the #334 focal rows plus the tranche.
- Evaluate by held-out selection gain (source-clustered), NLL/Brier and a
  learning curve over tranche size. The 32-state pilot is a development
  diagnostic only.

## E4: later

1. A one-ply online A/B: the model picks at card rewards and boss relics, V4
   does everything else.
2. Then a leaf-only substitution in otherwise unchanged OOC MCTS.

## Threads (at most two at once)

- **This thread:** E0 (done), then E2.
- **New local thread:** E1, needs Philipp's OK for local CPU training.
- E3 and E4 wait on those results.
