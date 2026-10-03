# Learned Silver stopping: frozen A/B plan

Status: frozen before any A/B seed ran, then run unchanged. Result:
`LEARNED_STOP_PASS`, see [README.md](README.md) and ledger-06 §370.
 The code is commit `ae7a6d79`, and
the plan commits that follow it change no code. The independent pre-run review
returned GO WITH FIXES. Its three required fixes are applied here:
- invalid-arm scoring;
- the training env and full hashes;
- the binary check in `launch.sh`.

## Question

Can a learned stop/continue model at fixed search checkpoints save Silver
compute against the production #199 retained-root rule without making
fights worse? Ledger §285 rejected a logistic version of this idea (it almost
never stopped). This plan tests a gradient-boosted version that may also stop
fresh roots.

## Policy under test

- `STS_SILVER_LEARNED_STOP=1` (needs `STS_SILVER_ADAPTIVE=0`). Each root with
  more than one legal action is searched to the checkpoints
  250/500/1,000/2,000/4,000/8,000/10,000 new simulations. Search stops at the
  first checkpoint where either:
  - a strict visit lock holds (`N1 - N2 > 10,000 - used`), or
  - the model risk is below 0.03.
- One-action roots are committed unsearched, as in production.
- Model `gbt-b91dcfea64e1`: 300 sklearn `HistGradientBoostingClassifier`
  trees over 18 root features (visit shares, gap, entropy, Q gap, inherited
  visits, fresh flag, checkpoint, leader streak, rho, lock, turn, act, room).
  It is compiled into `src/sim/search/NativeSilverStopModel.cpp` by
  `tools/silver_learned_stop.py`. On 3,000 trace rows the C++ evaluation
  equals the Python evaluation exactly.
- Training data (`training/`):
  - Native exact-10k checkpoint traces (`STS_SILVER_STOP_TRACE`) for seeds
    `41000000..41000031`, produced by code `78347c7e`, binary sha256
    `21b4128e22e9c75086f47f6b3ae81240160f541aceed94ec75649b28d1a3573c`, with
    the environment in `training/env.sh` (identical to `live_env.sh`).
  - Fit on `41000000..41000023` (62,118 checkpoint rows).
  - The label is "checkpoint leader differs from the 10k leader".
  - The fitted model is `training/model.json.gz` (sha256
    `e83f6ab899eab0e29ba357a8fed9075753c04ad03006ff6bf40ece9aa7e0f5ad`).
    The A/B binary has sha256
    `2136c77015a1546d9b538bd9603dcee377dd468b6a9f71f3b21e0b875aefa119`, and
    `launch.sh` checks it before any shard starts.
- Threshold rule: the largest value in {0.005, 0.01, 0.02, 0.03, 0.05} whose
  disagreement on the 8 held-out seeds `41000024..41000031` does not exceed
  #199's. This rule was decided before the held-out results were seen but was
  not committed before them.

Held-out offline result for multi-action decisions:

| Policy | Saving vs flat 10k | Disagreement with the 10k action |
|---|---|---|
| #199 | 42.5% | 0.99% |
| learned 0.02 | 54.2% | 0.37% |
| learned 0.03 (chosen) | 58.1% | 0.76% |
| learned 0.05 | 63.4% | 1.41% |

## Part A (primary): fight-replay A/B

- Mode: `one_combat silverstopreplaygen`.
- Each source seed is played with the exact-10k teacher
  `native-silver-v4-learnedstop-ae7a6d79` (`teacher.json`, V4-gated OOC,
  project-fair, Ascension 0).
- Every real fight is replayed from a detached pre-battle copy under three
  arms:
  - `control`: flat 10k. It must reproduce the source fight's outcome, HP,
    post-battle HP and first action.
  - `adaptive199`: the production #199 rule.
  - `learned`: the policy above.
- Seeds `42000000..42000095` (96 seeds, about 2,400 fights), 4 shards of 24,
  one CPU each, all through `tools/seed_guard.sh`. The smoke on seed
  `42009000` (not pooled) reproduced 25/25 control fights at about
  120 CPU-seconds per seed.
- A fight counts when the control replay matched. If the adaptive199 or
  learned result in such a fight is invalid (escape, turn cap, non-death
  loss), that arm scores signedOutcome −1 and won 0. The analysis reports
  per-arm invalid counts.
- Analysis: `tools/analyze_silver_stop_replay.py`. The self-test is in ctest.
  - S = 1 − Σ simulations(learned) / Σ simulations(adaptive199).
  - D = mean per-fight `signedOutcome(learned) − signedOutcome(adaptive199)`,
    with a 95% source-seed-clustered bootstrap (2,000 replicates, seed 0).
- Verdict:
  - `LEARNED_STOP_PASS`: all three of the following hold.
    - S ≥ 0.10.
    - The CI lower bound of D is above −0.005 (about 0.4 HP at 80 max HP per
      fight).
    - There are no more learned-only invalid fights than adaptive199-only
      invalid fights.
  - `LEARNED_STOP_COMPUTE_FAIL`: S < 0.10.
  - `LEARNED_STOP_QUALITY_FAIL`: otherwise.
- Reported, not part of the verdict:
  - each arm against flat 10k;
  - win rate, potions and CPU deltas;
  - the same comparisons by room class.

## Part B (secondary, descriptive): live paired runs

- `bestbench` on seeds `43000000..43000127` (128 seeds).
- Arms:
  - control: the production default (`STS_SILVER_ADAPTIVE=1`).
  - treatment: `STS_SILVER_ADAPTIVE=0 STS_SILVER_LEARNED_STOP=1`.
- Both arms use `live_env.sh` (exact root budgets off, same OOC stack).
- Analysis: `paired_analysis.py`, strict seed pairing. It reports win rate,
  floor, ending HP, and the CPU-seconds ratio.
- No gate. The whole-run outcome difference is too noisy at N=128 to decide
  quality; it is a live sanity check of compute and an obvious-harm screen.

## Budget and stop rule

- About 3.2 CPU-hours for Part A and about 2.8 for Part B, on a 4-CPU
  container (`launch.sh`).
- A shard that exits nonzero is kept as evidence and not retried. The
  analysis then runs on complete shards and says so.
- Nothing becomes a default in this change. Whether to promote is a separate
  decision.
