# Purpose-trained shared transition encoder distillation

**Decision: `SHARED_TRANSITION_ENCODER_REJECTED`.** The single HP-initialized
Attention encoder preserves the dedicated signed-HP teacher within every gate,
but its maxHP categorical NLL is 6.5932% worse than the dedicated maxHP teacher,
above the fixed 2% limit. The rejection is driven by maxHP under-learning; HP
degradation remains within all preregistered gates. The
combined VALIDATION KL was still improving at epoch 12, but the NLL miss is not
narrow enough for the preregistered epoch-12 `INCONCLUSIVE` exception. Stop;
do not add potion, epochs, task reweighting, adapters, or architectural variants.

## Provenance and population

- Current-main baseline: `28d39cdb611865518bed68d57b5f0afb6fcee5b5`.
- Frozen experiment code: `79c6fcf5ae979b5902c3b6c3af79da3902c1bbf0`.
- Dedicated maxHP teacher SHA256:
  `2c5b54d0a9420a9d0e3ab9a26f32b9900c4869490e4af49627009cde21efb4b0`.
- Dedicated HP teacher SHA256:
  `0c8b5aa8c5218d6cd6102b768cc86a474c9ef30953d4b034caedcc41a426109b`.
- Both teachers bind source `1c31b7eb0a7660d43bc27e0849a8955dd0c3daae`
  and preparation cache SHA256
  `e1c25f2758bf56c7cff392ea02342d809f3ad7427c70b64166244a6b714a251d`.
- TRAIN: 393,677 victories / 19,986 sources. VALIDATION: 48,590 victories /
  2,496 sources. TRAIN+VALIDATION row/source sequence SHA256 values are
  `5933a118…` / `e1f313dc…`.
- Teacher maxHP/HP probability arrays are SHA256 `10404b3e…` / `6244ca5e…`.
  Teacher parameters were frozen, outputs were FP32, all probabilities were
  finite and normalized, and HP used the exact native legal mask conditioned
  on each row's observed maxHP-delta class.
- Historical TEST had zero inference rows and no metrics.

## Fixed recipe and epoch history

The student uses exactly one existing typed-token Attention encoder (width 64,
two Transformer layers, four heads, FF width 128, current normalization and
trimmed padding), initialized byte-identically from the current HP specialist.
The maxHP-delta embedding and `72 -> 64 -> 304` HP head are copied from that
specialist. A fresh seeded `Linear(64,11)` maxHP head has initial-state SHA256
`c9124b5c…`; the complete HP initialization is `de1ca790…`.

Pure temperature-1 distillation minimizes equal-weight teacher-to-student KL.
Seed 20260912, AdamW, encoder LR 1e-4, heads LR 1e-3, weight decay 1e-4,
batch 512, clip 1.0 and AMP-FP16 training are fixed. Only TRAIN rows update
parameters; complete batch-order SHA256 is `dd0579e1…`. Selection is the
earliest strict minimum equal-weight VALIDATION KL.

| Epoch | maxHP KL | HP KL | Combined selection loss |
| ---: | ---: | ---: | ---: |
| 1 | 0.026371805 | 0.012746500 | 0.019559152 |
| 2 | 0.014245100 | 0.009836317 | 0.012040708 |
| 3 | 0.009168629 | 0.009170659 | 0.009169644 |
| 4 | 0.007194339 | 0.008212018 | 0.007703179 |
| 5 | 0.006248825 | 0.007573678 | 0.006911251 |
| 6 | 0.005895067 | 0.007220532 | 0.006557799 |
| 7 | 0.005214406 | 0.006806695 | 0.006010551 |
| 8 | 0.004873859 | 0.006448926 | 0.005661392 |
| 9 | 0.004508752 | 0.006283858 | 0.005396305 |
| 10 | 0.004389736 | 0.006010032 | 0.005199884 |
| 11 | 0.004232703 | 0.005874818 | 0.005053760 |
| 12 | 0.003832507 | 0.005607910 | **0.004720209** |

Epoch 12 is selected. Teacher caching took 26.19 seconds and the complete fit,
selection and scoring stage took 323.34 seconds (descriptive wall time).

## VALIDATION metrics

| maxHP metric | Teacher | Student | Delta |
| --- | ---: | ---: | ---: |
| categorical NLL | 0.042686500 | 0.045500919 | +0.002814420 (+6.5932%) |
| accuracy | 98.110722% | 98.003704% | -0.107018 pp |
| expected post-maxHP MAE | 0.081489 | 0.086931 | +0.005442 HP |

Zero-delta NLL/accuracy/MAE are 0.017461/99.2603%/0.042683 for the teacher
and 0.018680/99.1795%/0.046631 for the student. On 1,546 nonzero-delta rows,
teacher versus student NLL is 0.810300→0.861658, accuracy
63.1307%→62.2251% (-0.9056 pp), and MAE 1.262336→1.313238 HP. The nonzero NLL
increase is +0.051359 nat, not catastrophic under the fixed clear-failure guard.

| signed-HP metric | Teacher | Student | Delta |
| --- | ---: | ---: | ---: |
| categorical NLL | 2.498291 | 2.505074 | +0.006782 (+0.2715%) |
| CRPS | 3.619360 | 3.636778 | +0.017418 (+0.4813%) |
| expected ending-HP MAE | 5.341970 | 5.363075 | +0.021105 HP |

Healing, low-pre-HP and damage regress by at most 0.9505% CRPS/NLL and
0.042787 HP MAE, inside the 5% / 0.5 HP slice gates. Student output is finite;
maximum normalization errors are 2.98e-7 and illegal HP probability is exactly
zero.

## Receipts and boundary

External immutable run directory:
`/home/philippherrmann/sts_sweep/runs/shared-transition-encoder-distill-20260915/`.
The full result receipt SHA256 is `f51b062a…`, validation predictions
`620c66ba…`, and non-promoted student checkpoint `c60d18c6…`. The tracked
[compact receipt](shared_transition_encoder_distill_2026-09-15/results.json)
retains the epoch history, principal metrics, gates and hashes.

No survival/potion/relic/downstream fit, support or native/runtime change,
export, promotion, gameplay, simulator seed, multiple seed, hard-label loss,
task-weight tuning, TEST inference or architecture sweep ran. Knowledge impact:
experiment evidence and current research status only; no qualified component
or executable baseline changes.
