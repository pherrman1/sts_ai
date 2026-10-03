# Learned Silver stopping v2: frozen confirmation plan

Status: frozen before any confirmation seed ran. Code `adbcae75`; the plan
commit follows it and changes no code.

## Why a v2

The v1 model (`gbt-b91dcfea64e1`, ledger §370) passed its replay gate against
#199, but it had three weaknesses:
- It was trained on only 24 seeds.
- It overfit: 0.06% train vs 0.76% held-out disagreement.
- Its A/B had no lock-only arm, so it could not tell how much the model adds
  over the strict visit lock.

Philipp asked for more training runs and for model experiments.

## Model selection (offline, `training/`)

- More data: native exact-10k checkpoint traces for 128 more seeds,
  `41000032..41000159`. They were produced by code `ae7a6d79`, binary sha256
  `2136c77015a1546d9b538bd9603dcee377dd468b6a9f71f3b21e0b875aefa119`, with
  `../training/env.sh`. Together with v1's `41000000..41000031` that makes 160
  seeds and 66,930 multi-action decisions.
- Method: 5-fold seed-grouped cross-validation (`tools/silver_learned_stop_cv.py`,
  `training/cv160.json`). For each variant it reports the out-of-fold
  simulation saving against flat 10k at fixed action-disagreement budgets.
- Variants compared (saving at 0.25% / 0.5% / 0.75% / 1.0% disagreement):

| Variant | Saving |
|---|---|
| #199 | 41.0% at 1.03% |
| strict lock only | 37.1% at 0% |
| GBT v1 hyperparameters | 50.6 / 53.9 / 56.8 / 58.9 |
| smaller regularized GBT | 49.0 / 52.7 / 56.1 / 58.5 |
| monotone-constrained GBT | 48.4 / 51.9 / 55.0 / 57.2 |
| logistic | 45.5 / 49.5 / 52.4 / 54.6 |
| larger GBT (600 × 63 leaves) | 49.6 / 54.2 / 56.5 / 59.0 |
| **v1 GBT + 4 trend features** | **50.8 / 55.2 / 58.1 / 60.1** |
| larger GBT + trend | 51.2 / 55.3 / 58.3 / 59.9 |

- The trend features are the change of gap share, top share, Q gap and
  entropy since the previous checkpoint.
- **Chosen:** v1 hyperparameters plus the trend features, trained on all 160
  seeds. The result is model `gbt-770201c31f7b` (`training/model.json.gz`,
  sha256 `a15661acfd857ca972de94c6516960e47f77adb2d99bb1ba70fa627e101bdb95`).
- Threshold 0.0323: the cross-validated threshold for 0.75% disagreement.
- Train-set disagreement at this threshold is 0.31%, against 0.72% out of
  fold. The gap is much smaller than v1's.
- Parity: on a 2,590-row smoke trace, the C++ risk equals the Python risk
  exactly, and the traced trend features equal the recomputed ones.

## Confirmation A/B

Code `adbcae75`, binary sha256
`8e5e733d5ce48db5f8dd41b6b0c59aaa27509fb1e75c19212c4b88e21a3258c9` (checked by
`launch.sh`), teacher `native-silver-v4-learnedstop2-adbcae75`
(`teacher.json`, the same contract as v1 apart from the hashes).

**Part A (primary): fight replay.**
- Mode: `silverstopreplaygen`, on fresh seeds `44000000..44000127` (128
  seeds), 4 shards of 32.
- Arms:
  - `control`: flat 10k; it must reproduce the source fight.
  - `adaptive199`: the production rule.
  - `lockonly`: strict visit lock only, at the same checkpoints.
  - `learned`: v2.
- The smoke on seed `44009000` (not pooled) reproduced 30/30 control fights,
  at about 163 CPU-seconds per seed.
- Analysis: `tools/analyze_silver_stop_replay.py`. The rule is unchanged from
  v1 after the review fixes.
  - A fight counts when the control replay matched.
  - An invalid arm result in such a fight scores −1.
  - S = 1 − Σ sims(learned) / Σ sims(adaptive199).
  - D = the mean per-fight signedOutcome difference, learned − adaptive199,
    with a 95% source-seed-clustered bootstrap.
- Verdict:
  - `LEARNED_STOP_PASS`: all three of the following hold.
    - S ≥ 0.10.
    - The CI lower bound of D is above −0.005.
    - Fights invalid only under learned stopping do not outnumber fights
      invalid only under #199.
  - `LEARNED_STOP_COMPUTE_FAIL`: S < 0.10.
  - `LEARNED_STOP_QUALITY_FAIL`: otherwise.
- Reported, not part of the verdict:
  - learned − lockonly (what the model adds over the lock);
  - lockonly − adaptive199;
  - each arm against flat 10k;
  - lock and model stop counts;
  - deltas by room.

**Part B (secondary, descriptive): live paired runs.**
- `bestbench` on seeds `45000000..45000127`.
- Arms: production default (`STS_SILVER_ADAPTIVE=1`) against
  `STS_SILVER_ADAPTIVE=0 STS_SILVER_LEARNED_STOP=1`.
- Analysis: `paired_analysis.py`. There is no gate.

**Execution (added before launch, on Philipp's request to run in parallel).**
The same seed ranges and binary are split into 4 disjoint parts with
`launch_part.sh M` (M = 0..3). Each part covers 32 replay seeds
(`44000000+32M..+31`) and 32 live seeds (`45000000+32M..+31`), as 4 shards of
8 seeds. Each part runs on its own 4-CPU cloud machine against the binary in
`/mnt/project-files/silver-learned-stop/one_combat-adbcae75`, and the script
checks the sha256 first. Seeds are processed independently, so the split
changes only scheduling. `launch.sh` remains the single-machine equivalent.

**Budget and stop rule.**
- About 5.8 CPU-hours for Part A and 1.5 for Part B, on 4 CPUs.
- A shard that exits nonzero is kept and not retried. The analysis then runs
  on complete shards and says so.
- Nothing becomes a default here.

**Interpretation note (Inference).** The v1 A/B estimated about an 80% pass
probability at a true D of 0, and this gate is unchanged. A PASS is
non-inferiority evidence, not a superiority claim.
