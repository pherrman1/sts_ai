# Gumbel distillation T1: train the combat net on the D2 teacher data (pre-registration)

Status: written before any T1 training run. Plan: [Gumbel-16k als Lehrer
destillieren](https://claude.ai/artifact/K2pXZEopgkhDfYofobTSZ9), stage T1, after T0
([PREREG](../gumbel_distill_t0_20261110/PREREG.md)). Philipp asked on 2026-11-11 07:56 CET "Sollten wir d2 stoppen
und anfangen zu trainieren?". The training run on the PC GPU still needs his typed go. No gameplay, no new seeds, no
workers: D2 data and the PC GPU only.

## What T0 left open

- Policy: on D1, the net already gets close to what the data supports (LC-P q_regret 1.37 / 1.27 / 1.20 / 1.18 at
  F = 0.125 / 0.25 / 0.5 / 1: Δ₁ 0.022 < Δ₂ / 2 = 0.037, so DATA_SATURATING on q_regret). cq:20 is the best
  target (1.159 / 1.163 vs visits 1.176 / 1.188 on two seeds), but the gap is barely outside the seed spread.
- Value: still data-limited on D1 (LC-N value NLL 6.45 / 4.02 / 2.47 / 1.97).
- Boss specialists (all bosses in one net, D1 boss rows): -0.02 to -0.04 q_regret against the generalist. That is
  inside or at the seed spread: NO_SPECIALIST_GAIN. D1 had ~5-10k roots per boss, too few for one net per boss.
- D1 had no max backup. D2's teacher is §775's G16 + max backup 4 (the stronger player), and D2 records both the
  mean Q (`q`) and the max-backed Q (`qBacked`) per edge.

## Data

- D2 + D2b (RUN 242c054e / 6ef822e6, code 823bbad0, binary ed373563): every unit tar on
  `/mnt/project-files/gumbel-distill/{d2,d2b}/units/` and `d2/local/` that `verify_campaign.py` accepts at freeze
  time. At 08:31 CET: 698 of 704 units (5,584 runs, 3.31 M roots, 134 k fights). Roots per boss: 52 k (Collector) to
  158 k (Heart). The missing units are the slowest runs (Heart-heavy). The freeze note names the exact unit list
  and its sha256, and units that arrive later are not added to T1.
- D2c (RUN 6d1c1dd0) did not start and is not used.
- Packing: `pack_states.py` → `tensorize.py`. tensorize.py now also writes `qb.npy` (the max-backed Q per kept edge,
  NaN for an unvisited edge) when the rows carry `qBacked`. All other arrays are unchanged. Smoke on unit
  natural_111952464_8: 4,821 rows; qBacked is present on every visited edge, and qBacked ≥ q on 99.8 % of them.
- Splits unchanged (train.py, 64-bit hash of the run seed): h = 0 is the gate holdout and is **not read** by T1;
  h = 1 is validation; h = 2..9 is training.

## Code (this PR)

- `train.py --q-source mean|backed`: which Q the cq targets and `q_regret` / `top1_qpick` use. The default is
  `mean`, which is bit-identical to T0.
- `train.py --encounters NAME,...`: keep only those encounters' rows, in training and validation, for per-boss
  specialists.

## Grid (PC, RTX 3060 Ti; T0 / §771 settings: batch 256, AdamW 3e-4 one-cycle, bf16, bucketed batches)

All runs start from a §771 D0 checkpoint (polonly_d0 for policy-only, N_d0_w025 for value). Epochs are chosen so
that F = 1 trains about 3 D2 epochs, with `--eval-every 2000`. Seed 20261108 unless noted.

| id | init | value | policy target | q source | F |
|---|---|---|---|---|---|
| P-V | polonly_d0 | off | visits | – | 0.25, 0.5, 1 |
| P-CQm | polonly_d0 | off | cq:20 | mean | 1 |
| P-CQb | polonly_d0 | off | cq:20 | backed | 0.25, 0.5, 1 |
| N | N_d0_w025 | w 0.25, aux | visits | – | 0.25, 0.5, 1 |
| S2 | as above | | P-V, P-CQb, N at F = 1 | | 1, seed 20261109 |
| SPEC-e | best of P-V / P-CQb at F = 1 | off | as its init | as its init | boss e only, 3 epochs, 2 seeds |

SPEC-e runs once per boss encounter: HEXAGHOST, SLIME_BOSS, THE_GUARDIAN, AUTOMATON, CHAMP, COLLECTOR,
AWAKENED_ONE, DONU_AND_DECA, TIME_EATER, SHIELD_AND_SPEAR, THE_HEART. That makes 11 × 2 runs, fine-tuned from the
generalist, with `--encounters e`. In total 13 + 22 = 35 runs. At T0's speed and with about 6x the rows, a generalist
run takes ~15-20 min and a specialist ~2-5 min, so the grid takes ~6-8 GPU hours.

Every final checkpoint is also scored with `--eval-only` under the other q source, so every run reports q_regret
under both mean and backed Q.

## Measures (validation split; final checkpoint)

T0's measures: policy CE to the visit shares, top-1 to the Gumbel pick, `top1_qpick`, `q_regret` (mean and
backed), value NLL and death ECE (N). Specialists are scored on their own encounter's validation rows, next to the
generalist on the same rows (`--eval-only --encounters e`).

## Decision rules (steering, not a gameplay gate)

- **Data** (P-V and P-CQb on q_regret; N on value NLL): T0's rule with Δ₁ = m(0.5) − m(1), Δ₂ = m(0.25) − m(0.5).
  Δ₁ ≥ Δ₂ / 2 means DATA_LIMITED (D2c or more is worth running), Δ₁ < Δ₂ / 2 means DATA_SATURATING, anything else
  is MIXED. A Δ₁ inside the S2 seed spread counts as 0.
- **Target:** P-CQb is **BETTER_TARGET** if its backed q_regret is below P-V's by more than the S2 spread on both
  seeds. P-CQm against P-CQb is reported (mean vs max-backed Q as the target's Q). Same caveat as T0: this shows
  learnability, not better play.
- **Specialists:** encounter e is **SPECIALIST_BETTER** if SPEC-e's q_regret on e's validation rows is below the
  generalist's on both seeds by more than the S2 spread; otherwise NO_SPECIALIST_GAIN. Reported per boss.
- **Value:** N's value NLL / ECE against T0's LC-N (descriptive). Root V (visit-weighted Q, both sources) against
  the fight score via `t0_value_check.py`, by act and room, on h ≠ 0.

## Next (not in T1)

T2 tests in play whether the distilled net (generalist, plus specialists where SPECIALIST_BETTER) helps Silver as
its root prior and/or leaf value, with an SPRT gate (ADR-0064) on fresh seeds. It gets its own PREREG and needs
Philipp's go.

## Not in T1

No gameplay, no new seeds, no default change, no engine change. The gate holdout stays unread.
