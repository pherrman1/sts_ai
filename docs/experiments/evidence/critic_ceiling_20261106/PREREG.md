# Offline critic ceiling check for the PPO critic (stage 0), pre-registration

Philipp, 2026-11-06 17:35 CET, asked for a thread on the PPO critic ("besserer Critic oder potential basierte
Formung"). It chose "Offline-Messung zuerst" at 17:43 CET. The plan doc (German) is
https://claude.ai/artifact/9vuBefK6eBKK2AFaZVRhak.

Offline only: no seeds, no games, no workers. LONG_C (run 8816689e) is not touched. Its trajectory parts are read
only after the run has finished (update 420), on the PC, with the GPU free.

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

- Test: LONG_C parts of iterations 400-419 (20 × 40 parts, ≈ 10,400 games, played by net-0399 … net-0418). The online
  critic is the `value` field of each decision line, which is what PPO trained with.
- Training, primary: LONG_C parts of iterations 220-399 (≈ 93,600 games). Secondary (descriptive): also LONG_B parts
  0-219. `--exclude-from` the test parts, and `evaluate --train-seeds-from` refuses any shared seed.
- Per training game: the first net decision of each act plus 8 more drawn uniformly (seeded by the game seed). If host
  memory does not fit, `--game-frac` keeps a seed-hashed share. Any value other than 1.0 is reported.

## Estimators

`tools/heart1/critic_ceiling.py` (tests: `tests/test_critic_ceiling.py`, ctest `critic_ceiling_python`):

- **online**: the logged actor value, clipped to [1e-4, 1 − 1e-4].
- **net**: the trunk of LONG_C `net-0399.bin` (all actor inputs through `ppo_model.featurize`), with its value head
  reset to a logit head at the base rate. Trunk and head train with BCE on the outcome: `--epochs 3 --lr 1e-4
  --head-lr 1e-3 --minibatch 256`. The best epoch is chosen on a 5% seed-hashed split of the training games.
- **gbm**: xgboost on `flat_features()`. Every record field enters (`RECORD_FIELDS`), and an unknown field is an
  error. Settings: depth 6, eta 0.05, up to 3,000 rounds, early stopping on the same 5% split.

## Metrics

Computed per act (1-4), at the first decision of the run and over all decisions, on every net decision of the test
games: AUC, log loss, Brier, EV = 1 − Var(y − v)/Var(y), and sd of GAE advantages at λ 0.97 and at λ 1 with that
estimator's values.

## Decision rule (fixed before any score is read)

For each offline estimator (net, gbm) and scope (act 1, all decisions): **BETTER** if the log-loss difference against
online has a 97.5% game-cluster bootstrap CI (2,000 resamples, seed 20261106) entirely below 0 **and** the EV gain is
≥ 0.02 (point estimate). Bonferroni covers the two estimators; the two scopes are both reported.

- **GO** (stage 1 proposal: arm A with Φ = the better offline estimator, needs Philipp's typed go) if any estimator is
  BETTER on any scope.
- **NO_GO** otherwise. The critic direction is then dropped. The result goes to the ledger, together with the
  remaining lever, paired CRN continuations (option G in the plan doc).

## Cost

The PC GPU for a few hours after LONG_C ends (≈ 22:10 CET 2026-11-06 at the earliest), plus CPU for the GBM.
No core-hours on cloud workers.
