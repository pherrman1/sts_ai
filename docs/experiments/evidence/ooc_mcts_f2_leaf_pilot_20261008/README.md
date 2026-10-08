# OOC MCTS F2 leaf pilot (2026-10-08)

Ledger: [§401](../../ledger-06.md). Frozen plan: [PLAN.md](PLAN.md). The plan
passed an independent pre-run review with one launcher fix (`56dee75a`).
Philipp approved the run, on 4 cloud cores.

## Run

- **Binary:** built from `733b9da2`, SHA-256 `b3a17200…`. Plan commit
  `56dee75a`; model hashes are in [run/provenance.txt](run/provenance.txt).
- **Seeds:** `57000000..57000127`, 4 shards × 32 seeds, one CPU each, every
  arm in each shard. All 12 invocations exit 0 and no seed failed.
- **Smoke:** seed `57009000`, not pooled; it passed the plan checks
  ([smoke/](smoke/)).
- **Reproduction:** `analyze.py run --out report.json` reproduces
  [report.json](report.json).

## Results (128 pairs)

| | flat10k | x2b | f2 |
|---|---:|---:|---:|
| Win rate | 74.2% | 76.6% | 63.3% |
| Mean floor | 48.98 | 48.50 | 47.09 |
| CPU s per run | 58.1 | 202.4 | 193.4 |
| Losses on a boss floor | 24/33 | 21/30 | 38/47 |
| Mean HP after a win | 40.2 | 35.4 | 38.3 |

| Difference (95% paired bootstrap) | Wins | Floor | Discordant (+/−) |
|---|---|---|---|
| **f2 − x2b (decides)** | **−13.3 pp [−24.2, −2.3]** | −1.41 [−3.14, +0.20] | 18 / 35 |
| f2 − flat10k | −10.9 pp [−21.9, 0.0] | −1.89 [−3.48, −0.27] | 18 / 32 |
| x2b − flat10k | +2.3 pp [−8.6, +13.3] | −0.48 [−2.09, +1.20] | 26 / 23 |

**Verdict: `F2_WORSE`.**
