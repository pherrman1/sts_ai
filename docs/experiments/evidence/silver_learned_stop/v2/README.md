# Learned Silver stopping v2: confirmation result

Result: **`LEARNED_STOP_PASS`** (ledger-06 §372). The plan is
[PLAN.md](PLAN.md), frozen before any confirmation seed ran and run unchanged.
Model `gbt-770201c31f7b`, threshold 0.0323, code `adbcae75`, binary sha256
`8e5e733d5ce48db5f8dd41b6b0c59aaa27509fb1e75c19212c4b88e21a3258c9`.

## Files

- `training/`: the 128 extra trace seeds, the cross-validation reports and the
  fitted model.
  - `cv160.json` compares the variants on the 18 base features.
  - `cv160_trend.json` is GBT v1 with the 4 trend features (the chosen
    variant). It was regenerated after the plan with
    `tools/silver_learned_stop_cv.py --features all --variants gbt_v1` and
    reproduces the plan table: 58.1% saving at 0.72% disagreement, threshold
    0.032271.
- `run/partM/` (M = 0..3): raw outputs of `launch_part.sh M`. Each part ran on
  its own 4-CPU cloud container from commit `0fa711e`; the script checked the
  binary hash before any shard started.
  - `replayK.*` are the `silverstopreplaygen` outputs. `replayK.arms.csv.gz`
    is gzipped, and the manifest hashes refer to the uncompressed file.
  - `live_{control,learned}K.csv` with `.meta.json` sidecars and logs are the
    `bestbench` outputs. All 16 learned sidecars name model
    `gbt-770201c31f7b`; all 32 name executable `adbcae75`.
- `run/live_paired.txt` is the `paired_analysis.py` output over the pooled
  live CSVs.
- `report.json` is the full replay analysis.
- `SHA256SUMS` covers the directory.

All 48 shards exited 0, each run once. Compute: 6.1 CPU-hours for replay and
1.6 for live, against a planned 7.3.

Reproduce:

```bash
cd docs/experiments/evidence/silver_learned_stop/v2
for f in run/part*/replay*.arms.csv.gz; do gunzip -k $f; done
python3 ../../../../../tools/analyze_silver_stop_replay.py run/part{0,1,2,3}/replay{0,1,2,3}
for a in control learned; do head -1 run/part0/live_${a}0.csv > /tmp/live_$a.csv
  for f in run/part{0,1,2,3}/live_$a{0,1,2,3}.csv; do tail -n +2 $f >> /tmp/live_$a.csv; done; done
python3 ../../../../../paired_analysis.py /tmp/live_control.csv /tmp/live_learned.csv "#199" learned
```

## Part A: fight replay (primary)

All 128 sources (`44000000..44000127`) were valid, and 3,412 fights were
captured. The control replay reproduced 3,385 of them; all 27 exclusions were
escapes. No arm had an invalid result in any counted fight.

| Comparison, 3,385 fights | signedOutcome/fight | 95% CI | Simulation saving | CPU ratio |
|---|---|---|---|---|
| **learned − #199** | **−0.0007** | **[−0.0031, +0.0018]** | **21.3%** [20.3, 22.3] | 0.79 |
| learned − lock-only | +0.0006 | [−0.0017, +0.0030] | 30.2% | 0.71 |
| lock-only − #199 | −0.0013 | [−0.0036, +0.0008] | −12.7% | 1.12 |
| #199 − flat 10k | +0.0013 | [−0.0010, +0.0037] | 45.1% | 0.54 |
| lock-only − flat 10k | −0.0000 | [−0.0026, +0.0025] | 38.1% | 0.60 |
| learned − flat 10k | +0.0006 | [−0.0018, +0.0032] | 56.8% | 0.43 |

All three gate conditions hold: S = 21.3% ≥ 10%, the CI lower bound
−0.0031 > −0.005, and there are 0 learned-only invalid fights.

Stop counts:
- learned: 9,629 lock stops and 35,598 model stops;
- lock-only: 40,123 lock stops.

By room, learned − #199:

| Room | Fights | Difference | 95% CI | Saving |
|---|---|---|---|---|
| Normal | 2,082 | +0.0002 | [−0.0009, +0.0013] | 22.6% |
| Elite | 827 | −0.0005 | [−0.0046, +0.0037] | 23.2% |
| Boss | 367 | −0.0074 | [−0.0246, +0.0101] | 17.2% |
| Other | 109 | +0.0037 | [−0.0048, +0.0120] | 20.8% |

## Part B: live paired runs (descriptive)

128 paired `bestbench` runs on `45000000..45000127`, production default (#199)
against learned stopping:
- wins 76.6% → 77.3%, +0.8 pp [−7.0, +8.6], with 12 #199-only and 13
  learned-only wins;
- floor −1.0 [−2.1, +0.0];
- ending HP +0.0;
- seconds per run 26.7 → 20.0 (−25%).

## Reading

- The v2 model passes again on fresh seeds and saves slightly more than v1
  did (21.3% vs 19.4% against #199).
- The model adds a clear saving over the strict lock alone (30% fewer
  simulations) with no detectable quality cost. The lock alone saves less
  than #199.
- **Inference:** the boss point estimate is negative but its CI is wide
  (367 fights). The live floor difference is slightly negative in both v1
  (−1.1) and v2 (−1.0), each with a CI touching zero. Neither is evidence of
  harm, but both are worth watching in any promotion run.
- As in v1, this is non-inferiority evidence, not a superiority claim.
