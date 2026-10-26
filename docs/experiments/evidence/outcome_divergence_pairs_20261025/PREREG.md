# Outcome-label value head on first-divergence pairs (offline, no seeds), pre-registration

Thread "Evaluate full-game rollout labels" (Philipp, 2026-10-25 09:31Z; "Stufe 0 starten" 09:49Z, revised design
announced 10:0xZ). Plan doc: https://claude.ai/artifact/LuB6LLggR5TF4em1fKzBYG. Written before any TEST outcome or
any head prediction was looked at (one TRAIN seed, 111374100, was opened to check the file format).

## Question
Full production rollouts to the Heart give one Bernoulli label per state, the same label every recorded game
already carries. Two things decide whether buying more such labels (or cleaner counterfactual ones) is worth it:
1. **rho:** how strongly the whole-game outcomes of two children of the same root correlate under common seeds.
   It sets the cost of any common-seed sibling referee: SE(diff)^2 = 2 p(1-p)(1-rho)/n.
2. **Head signal:** does a value head trained only on real game outcomes (no X2-B, no rollouts) pick the child that
   went on to win, more often than chance, at real roots it never saw?

## Why not the log-loss gate of the plan doc
§515/§522 already fit a residual GBM over X2-B on real outcomes: CONFIRM BCE 0.335 vs Platt X2-B 0.348, yet the A20
A/B was NOT_SHOWN with act-1 deaths 114 vs 69. Level log loss does not predict play, so it is reported only as a
description. X2-B cannot be scored on stored public records without replaying games, so no X2-B arm is fit here.

## Data (existing, no new seeds)
`heartoutcomegen` JSONL of three paired A20 campaigns on the share, copied read-only:
- §683 `ooc-map-only-search/units` (arms D, MAP, OFF; seeds 111374100-111375123),
- §661 `value-level-ab/units` (four leaf arms),
- §676 `ctm-calibration-ab/units` (two CTM arms).
A game is used only with an `outcome` footer that has `complete` and `integrityPassed`. Arms of one seed play the
same seed and are identical until the first decision that differs.

**First-divergence pair:** for two arms a, b of one seed, k = first state index whose public `record` differs;
the root is state k-1 (identical in both), the children are state k of each arm. Pairs whose state sequences never
differ are dropped (counted). Outcome y = `heartKilled` (primary), Act-4 arrival = `finalAct` == 4 (secondary).

**Splits by seed:** TEST = seed % 4 == 3 (sealed until the head is frozen); VALIDATION = seed % 4 == 2 (early
stopping only); TRAIN = seed % 4 in {0, 1}. Every state of a TRAIN/VALIDATION game is a training row labelled with
that game's outcome, weighted 1 / (states in the game) so that every game counts once.

## Head G (frozen before TEST)
XGBoost 3.0.2 `binary:logistic`, max_depth 6, eta 0.05, subsample 0.8, colsample_bytree 0.5, min_child_weight 1,
up to 2,000 rounds, early stopping 100 rounds on VALIDATION weighted log loss, tree_method hist, seed 0.
Features from the public record only: `obs.fixed_observation`; deck counts per card id and per upgraded card id;
relic multi-hot; potion counts; counts of each room type above the current map row; mapX, mapY; act; floor;
screen_state and select_screen_type one-hot; number of cards, relics, potions and paths offered.
The feature code and model hash are committed before TEST is read.

## Measures
- **rho (descriptive, all splits; no head involved):** phi correlation of (y_a, y_b) over pairs, and
  1 - var(y_a - y_b) / (var(y_a) + var(y_b)), by campaign and by act of the root; 95% CI by bootstrap over seeds.
- **Primary, head advantage A_h (TEST):** mean over TEST pairs of (y_a - y_b) * sign(G(child_a) - G(child_b)),
  in Heart kills per divergence (ties count 0). 95% CI by 10,000 bootstrap resamples of seeds (all pairs of a seed
  move together).
- Secondary (TEST, descriptive): A_h for Act-4 arrival; A_h by campaign, arm pair, act and screen of the root;
  head accuracy on discordant pairs; on search-vs-OFF pairs of §683 the search's own advantage
  A_s = mean(y_search - y_off) and A_h - A_s with CI; VALIDATION/TEST log loss and AUC by act.

## Decision rule
- **SIGNAL:** A_h 95% CI lower bound > 0. Outcome-only labels carry sibling signal without X2-B; the next step
  (Philipp's call) is a comparison with M0 at the same roots (needs root replays or an online A/B).
- **NO_SIGNAL:** otherwise. Inference: one outcome label per state at this scale does not rank children; a better
  head needs counterfactual labels, whose cost follows from rho: rollouts per child for SE 1 pp of a mean advantage
  over R roots ~ 3,800 (1 - rho) / R. If that projects above a paired 1,024-seed A/B (~310 core-h) per comparison,
  the full-rollout label line stops.
No default, code path or seed block changes either way.

## Cost
Cloud thread CPU only: copying ~0.5 GB, parsing, one GBM fit; estimated < 5 core-h.
