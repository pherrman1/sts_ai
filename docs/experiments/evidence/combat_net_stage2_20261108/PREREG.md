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
- **Splits:** by run, h = `(seed · 2654435761) mod 2³² mod 10`; rows of one run never cross a split.
  - h = 0 is the gate holdout, about 10% of the runs of each data set. Only `gate.py` reads it, once, after training
    is fixed.
  - h = 1 is the validation split for learning curves and the choice of epochs (`train.py`, sample of up to 50,000
    rows).
  - h = 2..9 trains. The G2 baseline is fitted on D1's h = 2..9 rows.

## Model and training (`tools/combat_net/model.py`, `train.py`)

- **Model:** transformer over the encoder tokens: global (scalars, relics, status bits, potions), cards, monsters,
  status map and queues.
  - 4 layers, d 128, 4 heads, no dropout.
  - Policy logit per legal root action from (CLS, action embedding, target monster token).
  - Value: 21 classes (death, then end HP / max HP in 20 equal bins).
  - Two auxiliary heads: HP lost by the next and the second turn, Huber on HP / 10.
- **Optimizer:** AdamW, lr 3e-4, one-cycle, batch 256.
- **Main net N:** trained on D0, then fine-tuned on the D1 training runs.
- **Policy target: the Gumbel root's visit shares after sequential halving.** The completed-Q policy of Danihelka
  et al. is a descriptive alternative. Reason: at 16,000 simulations the σ scale (c_visit + max visits) · c_scale is
  in the thousands, so softmax(logit + σ(q)) is one-hot on the q-argmax almost everywhere. It then carries about one
  bit per root, the pick. The visit shares keep the halving's ranking of the 16 sampled edges: which edges survived
  which round. That is more signal per root, at the price of reflecting the schedule. Stage 3 tests the result in
  play either way.
- Epochs are chosen on the validation split (h = 1), never on the gate holdout.

## Gate (on the D1 holdout runs; fixed before training)

| | check | pass when |
|---|---|---|
| G1 | policy cross-entropy to the Gumbel teacher's target (visit shares) on multi-edge holdout roots that have a root prior on every kept edge: N minus the g7f_E root prior (renormalized over the kept edges, floored at 1e-12 as in the search) | per-row difference, run-clustered bootstrap (10,000, seed 20261108), 95% CI hi < 0 |
| G2 | value NLL of the 21-class end-HP label: N minus the baseline. The baseline is the empirical class distribution per (encounter name, HP decile) of D1's training split, decile = min(9, ⌊10 · hp / maxHp⌋) at the root, +1 Laplace over the 21 classes. An unseen cell falls back to the encounter's distribution, an unseen encounter to the global one (same +1). Encounters are joined by name. | per-row difference, run-clustered 95% CI hi < 0 |

- **G3 (sanity, not gated):** death-class reliability in 10 bins (rows, mean predicted, observed) and its ECE. At a
  low row-level death rate an ECE threshold passes almost automatically, so it is reported, not gated.
- Both gates are floors: the prior is what Silver uses today, and the baseline is the simplest state-aware value.
  Stage 3 (fights) decides whether the net helps.
- **Descriptive, reported with run-clustered 95% CIs:**
  - top-1 agreement with the Gumbel pick (`gumbelChoice`) for N, for the prior argmax and for the D0-only ablation;
  - N minus each of the two, also by room.
  - The D0-only comparison is the informative one: it shows how much of the Gumbel teacher's choice the D1
    fine-tune adds beyond production's targets. The teacher's own repeat agreement is not measured, since its pick
    depends on the Gumbel draws.
- Code: `tools/combat_net/gate.py` (G1, G2, G3 and the descriptive table, `--ref` for the ablation).
- **STAGE3_GO:** G1 and G2 both pass.
- **NO_GO:** otherwise, with a ledger entry and no stage 3.
- **Measured, not gated:** C++ inference time per root on one core. Stage 3 needs it below 1 ms, or it must pay for
  it in its equal-CPU design.

## Ablations (descriptive, same metrics, 95% CIs)

- N without the auxiliary heads.
- N policy-only (no value loss).
- N trained on D0 only. This shows whether the Gumbel targets add anything beyond production's. It is N's D0 checkpoint before the D1 fine-tune.

## Cost

- Tensorization and training on the PC GPU (RTX 3060 Ti), one GPU job at a time.
  - D0 tensorizes in about 5 minutes (1,633,473 rows, 5.4 GB of arrays).
  - `train.py` batches by length buckets, collates in DataLoader workers and runs bfloat16 autocast on CUDA. None
    of it changes targets or splits. On CPU, bucketing alone cut forward plus backward per batch of 256 from 1.74 s
    to 0.73 s (105 to 50 tokens).
  - The D0-only ablation is N's D0 checkpoint before the D1 fine-tune, so it costs no extra run.
  - Expected: well under an hour of GPU time for N and the ablations (first measured on the PC).
- D1 is about 100-150 lane-hours (see the smoke below; Philipp's go: 40 workers × 4 lanes, about 1 h).

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
