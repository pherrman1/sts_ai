# A20 card correction on top of the teacher's pick (plan, 2026-10-09)

Written and committed before any model is fitted. This is a follow-up to §409,
which found a GBM ranking every option from scratch `NOT_SHOWN`: −0.47 floors
versus the teacher's pick. Philipp asked to try a correction model instead.

## Hypothesis

A model that only predicts how much better or worse each alternative is than
the teacher's (V4 pipeline's) chosen card, and deviates only when that
predicted difference is positive, beats the teacher on floor reached. It can
fall back to the teacher wherever it has no evidence.

The corpus stores only the teacher's choice, not its per-option scores.
Recomputing those would need a gameplay replay, so this test conditions on
the choice instead.

## Data (existing, no new seeds)

- **Corpus and loading:** as §409 (`/mnt/project-files/a20-transfer-346/cf-a20-5ba068e0/`,
  `tools.vwin_e3_cf.load` / `apply_rules`, `CARD_REWARD` only).
- **Split:** as §409. `source_split`, with the early-stop inner set taken
  from TRAIN sources (sha256 `a20-card-floor-v1:{seed}` < 0.2).
- **Leak exclusion (new, from the §409 review):** states whose map row lies
  in a later act than the decision (`mapAct != act` on any row) are dropped
  from training and scoring. These are the boss card rewards.
- **States:** only those with exactly one chosen option and at least two
  options.

## Model

- **Rows:** each non-chosen option × future k.
- **Target:** d = `horizonFloor`(option, k) − `horizonFloor`(chosen, k). The
  futures are shared, so this is a paired difference.
- **Features:** the option's public map-row features (X2-B list minus
  HIDDEN_FUTURE), then the same features minus the chosen option's row.
- **Weights:** each state has total weight 1, rescaled to mean 1.
- **Training:** XGBoost `reg:squarederror` with the §409 recipe and the inner
  early stop. Seeds 0, 1 and 2, mean prediction.

## Policy and metric

**Policy:** in each state, let a* be the non-chosen option with the highest
predicted d (mean over k). Pick a* if its predicted d > 0; otherwise keep the
teacher's pick.

**Metric:** selection gain in floors over the teacher's pick. It is 0 when
the policy keeps the teacher's pick, and the mean-over-k floor difference
when it switches. CIs are 95% bootstraps that resample source seeds (2,000
reps). The switch rate is also reported.

## Decision rule

- **VALIDATION (primary):** `PASS_VALIDATION` if the CI lower bound > 0;
  otherwise `NOT_SHOWN`, and we stop.
- **TEST:** only after `PASS_VALIDATION`, the frozen model is scored once on
  TEST. `PASS` if the TEST CI lower bound > 0 as well.
- **Context, not part of the rule:**
  - an oracle switch (the best observed option, noise-inflated);
  - a random alternative switched in at the same rate;
  - the §409 full ranker on the same leak-free states.

VALIDATION was already looked at once, in §409, under a different model. This
is a second hypothesis on the same split, which is why TEST confirmation is
part of the rule.

## Cost

Offline only, on 4 cloud cores, a few minutes. No gameplay seeds.
