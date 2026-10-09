# A20 card ranker on floor reached: offline test (plan, 2026-10-09)

Written and committed before any model is fitted.

## Question

At A20, card-reward options differ in floor reached: the option SD is about
2.0 floors, with a CI that excludes 0 (§402). On win labels they differ by
about 0. Can a GBM trained on the existing A20 counterfactual corpus pick
cards that reach more floors than V4's pick, on held-out states?

## Why

Live OOC MCTS card picks follow the V4 prior. Its leaf (X2-B, a win model)
cannot rank cards, and at A0 card choice barely moves wins (§396). Philipp
chose to pursue cards at A20. A floor-type ranker is the only target with
measurable card signal there.

## Data (existing, no new seeds)

- **Corpus:** `/mnt/project-files/a20-transfer-346/cf-a20-5ba068e0/`, the
  §402 corpus. Producer `ooccfpilotgen` GEN=2 at `5ba068e0`, A20, seeds
  59100000..59101199, K=2 shared futures, learned-stop V4 teacher.
- **Loading:** `tools.vwin_e3_cf.load` / `apply_rules` (manifest SHA checks;
  drop a (state, k) group with any invalid sibling).
- **States:** `CARD_REWARD` only (scoring and the primary arm's training).
- **Target:** `horizonFloor`, the floor of the run's last fight.
- **Features:** the X2-B input features on the option's map row, with the four
  HIDDEN_FUTURE fields dropped (as E3).
- **Split:** `source_split` (70/15/15 by source seed).
  - Early stopping uses an inner set of TRAIN sources: sha256
    `a20-card-floor-v1:{seed}` < 0.2. VALIDATION is used only for scoring, to
    avoid §396's early-stop optimism.
  - TEST stays closed.

## Arms

| arm | training rows | role |
|---|---|---|
| `CARD` | card-reward TRAIN rows | primary |
| `ALL` | card-reward and boss-relic TRAIN rows | diagnostic |
| `CARD_50` | `CARD` on a fixed 50% of TRAIN sources | diagnostic, learning curve |
| `X2B` | frozen X2-B win probability | diagnostic, current leaf anchor |

- Model: XGBoost `reg:squarederror` with the X2-B recipe (depth 6, eta 0.06,
  min_child_weight 10), subsample 0.8, colsample 0.7, up to 2,500 rounds,
  patience 50.
- Each arm is the mean of seeds 0, 1 and 2.
- Each state has total weight 1.

## Metric and decision rule

**Metric:** selection gain on VALIDATION card-reward states. For each state,
take the mean `horizonFloor` (over k) of the arm's argmax option, minus that
of V4's chosen option. Score ties are averaged. CIs are 95% bootstraps that
resample source seeds (2,000 reps).

**Rule (primary arm `CARD` only):**
- `PASS`: CI lower bound > 0. A floor-type card leaf is worth building.
- `NOT_SHOWN`: otherwise.

**Context, not part of the rule:** uniform-random and oracle gains, V4
agreement, skip rate, the `CARD_50` vs `CARD` learning curve (sizing for
more data), and `ALL` and `X2B`.

**Power note:** about 180 VALIDATION card states. With option SD about 2
floors and label noise about 8 floors per future, a true gain of under 1 floor
may not be detected (inference, not computed).

## Cost

Offline only: XGBoost on about 7k map rows on 4 cloud cores. No gameplay seeds.
