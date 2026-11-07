# Offline critic ceiling check for the PPO critic (stage 0), pre-registration

Philipp, 2026-11-06 17:35 CET, asked for a thread on the PPO critic ("besserer Critic oder potential basierte
Formung"). It chose "Offline-Messung zuerst" at 17:43 CET. The plan doc (German) is
https://claude.ai/artifact/9vuBefK6eBKK2AFaZVRhak.

Offline only: no seeds, no games, no workers. LONG_C (run 8816689e) is not touched: its trajectory parts on the PC
are only read. Philipp, 2026-11-06 17:55 CET ("Kannst du nicht einfach die neueste Long c version nehmen?"): use the
newest LONG_C data instead of waiting for update 420. The GBM runs on the PC CPU while LONG_C trains (4 threads); the
net needs the GPU (after LONG_C) or runs on CPU with fewer games.

## Question

The online critic of LONG_B/LONG_C barely predicts the outcome in act 1 (EV 0.04 against the outcome, AUC 0.68;
§756 and the LONG_C diagnostics). Is that close to what any critic can get from act-1 states, or does a critic trained
offline on many more games predict clearly better?

With GAE, potential-based shaping with a fixed Φ is the same as using the critic Φ + V, where V learns the residual.
So this check covers both "a better critic" and "shaping with a learned Φ". The general value model (#935, §746) only
covers Heart-entry states, so it cannot be a Φ for acts 1-3.

## Bound (stated before any result)

With a 0/1 outcome y, a critic's MSE against y is Var(y)(1 - EV). An EV gain of d therefore removes only d·Var(y)
(≈ 0.16 d) of the λ-1 advantage variance. In act 1 even a perfect critic may reach only EV ≈ 0.02-0.06 if the true
win chance there varies by 5-10 pp. A GO here means "there is predictable signal the online critic misses", not
"PPO will learn act 1 much faster".

## Data

- Freeze point N: the newest LONG_C update whose 40 parts are all complete when the run starts, rounded down to a
  multiple of 20 (N is recorded in the RESULT before any score is read).
- Test: LONG_C parts of iterations N-20 … N-1 (≈ 10,400 games, played by net-(N-21) … net-(N-2)). The online critic is
  the `value` field of each decision line, which is what PPO trained with.
- Training, primary: LONG_C parts of iterations 220 … N-21. Secondary (descriptive): also LONG_B parts 0-219.
  `--exclude-from` the test parts, and `evaluate --train-seeds-from` refuses any shared seed.
- Per training game: the first net decision of each act plus 8 more drawn uniformly (seeded by the game seed). If host
  memory or CPU time does not fit, `--game-frac` keeps a seed-hashed share. Any value other than 1.0 is reported.

## Estimators

`tools/heart1/critic_ceiling.py` (tests: `tests/test_critic_ceiling.py`, ctest `critic_ceiling_python`):

- **online**: the logged actor value, clipped to [1e-4, 1 − 1e-4] (descriptive only).
- **online_cal**: the logged value recalibrated per act (Platt, y ~ a + b·v, fitted on the logged values of every
  net decision in the training parts; no test data). It is the comparator of the decision rule. The value head is
  trained with MSE, so it is no calibrated probability. A value ≤ 0 in a kill game costs 9.2 nats after clipping, and
  on cov8 the raw online log loss is 0.965, worse than a constant (review K, F1).
- **net**: the trunk of LONG_C `net-(N-21).bin` (the actor net of the first test iteration) (all actor inputs through `ppo_model.featurize`), with its value head
  reset to a logit head at the base rate. Trunk and head train with BCE on the outcome: `--epochs 3 --lr 1e-4
  --head-lr 1e-3 --minibatch 256`. The best epoch is chosen on a 5% seed-hashed split of the training games.
- **gbm**: xgboost on `flat_features()`. Every record field enters (`RECORD_FIELDS`), and so does every key of
  each `fixed_actions` entry, including `info` (`FIXED_ACTION_KEYS`). An unknown field or key is an error. Settings: depth 6, eta 0.05, up to 3,000 rounds, early stopping on the same 5% split.

## Metrics

Computed per act (1-4), at the first decision of the run and over all decisions, on every net decision of the test
games: AUC, log loss, Brier, EV = 1 − Var(y − v)/Var(y), and sd of GAE advantages at λ 0.97 and at λ 1 with that
estimator's values.

## Decision rule (fixed before any score is read; amended 2026-11-06 ≈ 18:05 CET after review K, before any score)

For each offline estimator (net, gbm) and scope (act 1, all decisions), compared with **online_cal**: **BETTER** if all
three of these hold:

- the log-loss difference has a 98.75% game-cluster bootstrap CI (2,000 resamples, seed 20261106) entirely below 0;
- the EV gain has a 98.75% CI entirely above 0;
- the EV gain is ≥ 0.02 (point estimate).

98.75% is Bonferroni over 2 estimators × 2 scopes. Differences against raw online are reported as description.

- **GO** (stage 1 proposal: arm A with Φ = the better offline estimator, needs Philipp's typed go) if any estimator is
  BETTER on any scope.
- **NO_GO** otherwise. The critic direction is then dropped. The result goes to the ledger, together with the
  remaining lever, paired CRN continuations (option G in the plan doc).

## Known bias

The training games come from older nets (220 … N-21) than the test games (N-20 … N-1). The offline estimators predict
a slightly different policy's outcome, which works against GO (review K, F4). The RESULT states this.

## Cost

The PC CPU for the GBM now; the PC GPU for a few hours after LONG_C ends (≈ 22:10 CET 2026-11-06), or the CPU for a
smaller net fit.
No core-hours on cloud workers.
