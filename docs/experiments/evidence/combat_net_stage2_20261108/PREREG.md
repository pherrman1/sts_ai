# Combat net, stage 2: training and offline checks (pre-registration, draft)

Status: draft, written before any D1 row and before any training run on the full data. Combat plan stage 2
([plan](https://claude.ai/artifact/HvTqKL592wjb21Zgb3Sho4), section "Stufe 2: Plan"). Philipp chose stage 2 on
2026-11-08 09:07 CET after §770 (TEACHER_FOUND: the Gumbel root at 16,000 simulations loses 0.88 HP per elite or
boss fight less than production). The D1 run and the GPU training each need his typed go.

## Question

Can a combat net learn Silver's root decision and the fight's outcome well enough to be worth a fight gate
(stage 3)? It is trained on D0 (production) and D1 (the Gumbel teacher).

## Data

- **D0:** stage 0 (`../combat_states_20261108`), 1,633,473 root rows from 3,072 A20 runs of production Silver at
  flat 10k (pack sha256 `21e84331…`).
- **D1:** `silverazgen` with `STS_AZGEN_GUMBEL_ROOT=16` at flat 16,000, otherwise stage 0's `record_env.sh`.
  - Every fight of the run plays the Gumbel root.
  - Root rows add each edge's root prior and the Gumbel pick.
  - Planned size: about 1,000 runs (about 0.5M roots), on a new seed block from the coordinator.
- Both go through `pack_states.py` → `tensorize.py`.
- **Holdout:** runs with `(seed · 2654435761) mod 2³² mod 10 = 0`, about 10% of the runs of each data set. Rows of
  one run never cross the split. The holdout is not read until the gate evaluation, except that the training script
  evaluates a fixed 50,000-row sample of it for learning curves.

## Model and training (`tools/combat_net/model.py`, `train.py`)

- **Model:** transformer over the encoder tokens: global (scalars, relics, status bits, potions), cards, monsters,
  status map and queues.
  - 4 layers, d 128, 4 heads, no dropout.
  - Policy logit per legal root action from (CLS, action embedding, target monster token).
  - Value: 21 classes (death, then end HP / max HP in 20 equal bins).
  - Two auxiliary heads: HP lost by the next and the second turn, Huber on HP / 10.
- **Optimizer:** AdamW, lr 3e-4, one-cycle, batch 256.
- **Main net N:** trained on D0, then fine-tuned on the D1 training runs. The policy target is the Gumbel root's
  visit shares after sequential halving. The completed-Q policy is a descriptive alternative.
- Epochs are chosen on the learning-curve sample, not on the gate metrics. That is the only use of the sample.

## Gate (on the D1 holdout runs; fixed before training)

| | check | pass when |
|---|---|---|
| G1 | policy top-1 agreement with the Gumbel teacher's pick (`gumbelChoice`) on multi-edge roots: N against the argmax of the g7f_E root prior on the same roots | paired difference, run-clustered bootstrap (10,000, seed 20261108), 95% CI lo > 0 |
| G2 | value NLL of the 21-class end-HP distribution: N against the empirical distribution per encounter × current-HP decile, fitted on the D1 training runs (+1 Laplace) | per-row NLL difference, run-clustered 95% CI hi < 0 |
| G3 | death calibration of N's death class | 10-bin ECE < 2 pp |

- **STAGE3_GO:** G1, G2 and G3 all pass.
- **NO_GO:** otherwise, with a ledger entry and no stage 3.
- **Measured, not gated:** C++ inference time per root on one core. Stage 3 needs it below 1 ms, or it must pay for
  it in its equal-CPU design.

## Ablations (descriptive, same metrics, 95% CIs)

- N without the auxiliary heads.
- N policy-only (no value loss).
- N trained on D0 only. This shows whether the Gumbel targets add anything beyond production's.

## Cost

- Tensorization and training on the PC GPU (RTX 3060 Ti), one GPU job at a time. That is about 1-2 days including
  ablations.
- D1 is about 65 lane-hours (8 workers × 4 lanes ≈ 2 h).

## Smokes (2026-11-08; not part of the gate)

- **D1 generator:** one natural run, seed 111869993 (stage 0's smoke block), `STS_AZGEN_GUMBEL_ROOT=16`, flat 16,000.
  - rc 0. 31 fights (all won, Act 3 floor 50), 1,147 roots, 1,099 of them with more than one edge.
  - 1,071 s wall, sharing 4 cores with a training smoke, so about 0.9 s per root. Stage 0 at 10k was 0.3 s.
  - Every multi-edge row has a root prior on every edge and a valid `gumbelChoice`.
  - In 1,084 of 1,099 rows the Gumbel pick is the played action exactly. The other 15 differ only in the played
    card's unique id (another copy of the same card). `pack_states.py` now matches those by copy (`chosenByCopy`),
    and `tensorize.py` zeroes the unique id in action features.
  - Cost estimate for D1: at 0.6-0.9 s per root and about 600 roots per run, 1,000 runs take about 100-150
    lane-hours.
- **Training:** 2% of D0 (32,670 rows), CPU, batch 64, 200 steps. The pipeline runs end to end. On the 3,231-row
  holdout: policy CE 1.42, top-1 0.43, value NLL 2.82, death ECE 0.4 pp (untrained-scale numbers, smoke only).
