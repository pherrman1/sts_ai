# Gumbel distillation T0: offline learning curve and policy targets on D1 (pre-registration)

Status: written before any training run of this grid. Plan: [Gumbel-16k als Lehrer
destillieren](https://claude.ai/artifact/K2pXZEopgkhDfYofobTSZ9), stage T0. Philipp gave the go on 2026-11-10 20:27
CET ("jo go auf t0"). No gameplay, no seeds, no workers: existing D1 data and the PC GPU only.

## Questions

1. **Data:** is the combat net still data-limited at D1's size (1,024 Gumbel-16k runs)? This sets the size of a
   later teacher factory (512 / 4,096 / 10,000 runs).
2. **Policy target:** does training on the completed-Q policy instead of the visit shares give a net that agrees
   better with the teacher's best-Q finalist, at what cost in fit to the visit shares?
3. **Value (descriptive):** how biased and how noisy is the teacher's root Q as a value target, compared with the
   fight's real outcome (Silver score)?

## Data

- D1 (§771, [campaign](../combat_net_d1_20261108/README.md)): 1,024 runs, 24,335 fights, 569,059 roots, Gumbel root
  k 16 at flat 16,000, mean backup (no max backup), production OOC. Re-packed in the cloud from the share's unit tars
  (`verify_campaign.py --extract`, 256/256 OK, run 57413a53; `pack_states.py`: same counts as §771).
- D0 enters only through the existing D0 checkpoints of §771 (N_d0_w025 `ce479413…e3b1`, polonly_d0 `085be0fc…a659`).
- Splits unchanged (train.py): h = 0 gate holdout is **not read** by T0; h = 1 validation; h = 2..9 training.
- tensorize.py now also writes per-edge `visits`, `q` (NaN if unvisited) and per-row `score`, `fight`. The other
  arrays are unchanged.

## Grid (PC, RTX 3060 Ti; §771 settings: batch 256, AdamW 3e-4 one-cycle, bf16, bucketed batches)

Every run fine-tunes a §771 D0 checkpoint on D1 for the same number of steps as §771's 3-epoch D1 fine-tune
(`--epochs 3/F`, so every fraction gets ~5,300 steps), `--eval-every 500`. Seed 20261108 unless noted.

| id | init | value | target | train fraction F |
|---|---|---|---|---|
| LC-N | N_d0_w025 | w 0.25, aux | visits | 0.125, 0.25, 0.5, 1 |
| LC-P | polonly_d0 | off | visits | 0.125, 0.25, 0.5, 1 |
| TG | polonly_d0 | off | cq:paper, cq:5, cq:20 | 1 |
| LC-T | polonly_d0 | off | best TG target (lowest q_regret) | 0.125, 0.25, 0.5 |
| S2 | as above | | LC-N F=1, LC-P F=1, the three TG runs | 1, seed 20261109 |

19 runs, about 2-3 min each. `--train-frac F` keeps nested subsets of the training runs.

## Measures (validation split, all rows, final checkpoint and best checkpoint by the listed measure)

- policy CE to the **visit shares** (comparable across targets), top-1 to the played action (= the Gumbel pick),
  `top1_qpick` (agreement with the best-Q finalist, edges with ≥ half the root's largest visit count),
  `q_regret` (best finalist Q − Q of the net's argmax, in Silver score units), value NLL and death ECE (LC-N).
- `t0_value_check.py` (numpy, h ≠ 0): bias, RMSE, correlation of root V (visit-weighted Q) and of the best
  finalist Q against the fight's score, by room and act, on all roots and on each fight's first root; how often the
  best-Q finalist differs from the played pick; sharpness (max probability, entropy) of each policy target.

## Decision rules (steering, not a gameplay gate)

- **Data** (LC-P and LC-T, on q_regret and policy CE): Δ₁ = m(0.5) − m(1), Δ₂ = m(0.25) − m(0.5).
  - Δ₁ ≥ Δ₂ / 2 on both measures → **DATA_LIMITED**: a factory of ≥ 4,096 runs is justified.
  - Δ₁ < Δ₂ / 2 on both → **DATA_SATURATING**: factory ≤ 2,048 runs; target or model capacity first.
  - otherwise **MIXED**, reported as such.
  - Seed spread at F = 1 (S2) is reported next to Δ₁; a Δ₁ inside the spread counts as 0.
- **Target:** a cq target is **BETTER_TARGET** if its q_regret is lower than LC-P F=1 (visits) by more than both
  seeds' spread, on both seeds. Caveat, fixed now: cq trains toward the Q argmax that `top1_qpick` and `q_regret`
  measure, so this shows learnability, not better play. Only T2 (fight-level) can show that.
- **Value:** descriptive only. D1 has no max backup, so the max-backup bias is measured in T1.

## Not in T0

No gameplay, no new seeds, no change to any default or to the engine. The gate holdout stays unread.
