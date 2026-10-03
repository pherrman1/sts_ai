# Learned Silver stopping v3: live promotion result

Verdict: **`PROMOTE_learned`** (ledger-06 §373). [PLAN.md](PLAN.md) was frozen
before any seed ran, reviewed (fixes applied in `4a5e1a5`), and run unchanged
after Philipp's go. The verdict is a recommendation: the default flip is a
separate ADR and PR.

## Files

- `run/partM/` (M = 0..3): raw outputs of `launch_part.sh M`, one part per
  4-CPU cloud container, all from commit `4a5e1a5`. Each part has 16 arm
  shards (`<arm>K.csv`, `.meta.json`, `.log`).
  - All 64 shards exited 0, each run once.
  - All 64 sidecars name executable `8c7da1d0`.
  - The 48 learned-stop sidecars name model `gbt-770201c31f7b`, threshold
    0.0323, and the boss settings of their arm.
- `report.json`: output of `analyze.py run`, which carries the verdict.
  Re-running it reproduces the file exactly.
- `run/paired_*.txt`: descriptive `paired_analysis.py` reports (95% CIs at
  one decimal).
- `SHA256SUMS` covers the directory.

Compute: 30.7 CPU-hours, against the 26–28 planned. The control arm ran at
29.3 s per run here, against 26.7 s in §372.

## Primary result (1,024 pairs, 98.33% Bonferroni CI, margin −0.75 floors)

| Variant vs #199 | ΔF floors | 98.33% CI | Wins | s/run (ratio) | Qualifies |
|---|---|---|---|---|---|
| **learned (v2)** | **+0.49** | **[+0.08, +0.91]** | 80.3% vs 78.3% (+2.0 pp, 95% CI [−0.6, +4.5]) | 23.7 (0.81) | **yes** |
| bossfallback | +0.33 | [−0.03, +0.71] | 78.8% (+0.5 pp) | 25.6 (0.87) | yes |
| bossmax30k | +0.32 | [−0.08, +0.75] | 79.2% (+0.9 pp) | 30.7 (1.05) | no (slower) |

The two qualifying variants are learned and bossfallback. Of these, learned
has the higher ΔF, which gives `PROMOTE_learned`.

## Secondary

- **Boss variants against plain v2:** neither helps.
  - bossfallback − learned: −0.2 floors [−0.5, +0.1], −1.5 pp wins, +1.9 s
    per run.
  - bossmax30k − learned: −0.2 floors [−0.4, +0.0], −1.1 pp wins, +7.1 s
    per run.
  - By the plan's rule, the 10k cap stays.
- **Losses:**

  | Arm | Losses | Deaths on an act-boss floor (16/33/50) | Mean floor of a loss |
  |---|---|---|---|
  | #199 | 222 | 163 | 42.3 |
  | learned | 202 | 157 | 43.9 |
  | bossfallback | 217 | 169 | 43.6 |
  | bossmax30k | 213 | 168 | 43.5 |

- **Ending HP:** #199 33.0, learned 33.2.
- **Inference:**
  - The negative floor lean of the 128-seed live runs (§370, §372) did not
    replicate at 1,024 pairs.
  - The v2 replay boss estimate (−0.0074) does not show up as more boss
    deaths live.
  - The positive ΔF is a non-inferiority pass with a positive point estimate.
    It is not a pre-registered superiority test.

Reproduce:

```bash
python3 docs/experiments/evidence/silver_learned_stop/v3/analyze.py docs/experiments/evidence/silver_learned_stop/v3/run
```
