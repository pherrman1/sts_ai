# Frozen HP representation for maxHP-delta decoding

**Decision: `SHARED_HP_ENCODER_MAXHP_REJECTED`.** A fresh categorical
maxHP-delta head on the frozen dedicated HP representation is materially worse
than its byte-identically initialized control on the frozen dedicated maxHP
representation. Per the sequential design, the HP-encoder potion screen did
not run.

## Provenance and paired recipe

- Baseline: `cde61c85b8a9ad8500cd3ca6e18607ff33bb6e1a`.
- Experiment code: `af46e32cbb5fcb71d598f735be2edc9ab5d830d4`.
- Dedicated maxHP component SHA256:
  `2c5b54d0a9420a9d0e3ab9a26f32b9900c4869490e4af49627009cde21efb4b0`.
- Dedicated HP component SHA256:
  `0c8b5aa8c5218d6cd6102b768cc86a474c9ef30953d4b034caedcc41a426109b`.
- Post-#187 applicability: #187 changed only the survival component. The exact
  maxHP and HP component hashes tested here are unchanged on current main, so
  the result remains directly applicable and no scientific rerun is required.
- Both component receipts bind source `1c31b7eb0a7660d43bc27e0849a8955dd0c3daae`,
  original source-grouped TRAIN fitting, VALIDATION-only checkpoint selection,
  and preparation cache SHA256
  `e1c25f2758bf56c7cff392ea02342d809f3ad7427c70b64166244a6b714a251d`.
- TRAIN: 393,677 victories / 19,986 sources. VALIDATION: 48,590 victories /
  2,496 sources. Historical TEST was neither scored nor selected.
- Row-ID SHA256:
  `02ca974b977dd42784f1c43a60c6216270779ce3d1670e2e2ce975967b9612e2`;
  source sequence SHA256:
  `f29f43065913889181fcb27981536701cf29d8273c54425798984ff801545995`.

Both frozen encoders were cached as 64-dimensional FP32 arrays with identical
MHA backend settings. Both fresh `Linear(64,11)` heads used seed `20260912`,
12 epochs, AdamW, learning rate `1e-3`, weight decay `1e-4`, batch size 512,
gradient clip 1, FP32 arithmetic, identical row order and identical batches.
Only the fresh head trained. Encoder parameters were frozen; no VALIDATION rows
entered gradient updates. Head initial-state and complete batch-order hashes
are byte-identical.

Preregistered pass gates were candidate NLL no more than 1% worse, class
accuracy no more than 0.5 percentage points worse, and expected post-maxHP MAE
no more than 0.1 HP worse. Values within 20% beyond a numeric gate were to be
`INCONCLUSIVE`; larger misses reject.

## Validation result

| Metric | Dedicated maxHP A | HP representation B | B - A | Relative |
| --- | ---: | ---: | ---: | ---: |
| maxHP-delta NLL | 0.042742204 | 0.159130603 | +0.116388399 | +272.3032% |
| class accuracy | 98.069562% | 96.820333% | -1.249228 pp | -1.2738% |
| expected post-maxHP MAE | 0.081355842 | 0.234179750 | +0.152823909 HP | +187.8476% |

On the decision-critical nonzero-delta slice (1,546 rows), accuracy falls from
63.1307% to 0.0647%, NLL rises from 0.787493 to 3.897300, and expected
post-maxHP MAE rises from 1.231053 to 3.450993 HP. On the dominant zero-delta
slice (47,044 rows), the candidate predicts the mode exactly but still worsens
NLL and expected error.

The control selected epoch 8; the candidate selected epoch 12, the final
allowed epoch. Thus this frozen screen does not establish intrinsic absence of
maxHP information in the HP representation; it establishes failure under this
fixed linear-head/training recipe. No extra epochs or tuning were run.

## Receipts and scope

External run directory:
`/home/philippherrmann/sts_sweep/runs/shared-frozen-maxhp-encoder-20260915/`.
Full `results.json` SHA256:
`53e240701d58cb30cdf0e575c58dff69064e2efb8a8eb45eaa7865c50b75cfef`;
validation predictions SHA256:
`67bde21409d8eabc5ca22c9daa67630341868e42ee0c2fa82b0db481c99e5704`.
The tracked compact receipt retains both complete 12-epoch NLL histories,
selected guard metrics, slices, parity, provenance and the sequential stop.

Caching took 32.59 seconds and complete fit/scoring took 7.67 seconds per arm,
descriptive only. No potion screen, TEST, gameplay, new data, runtime/export,
model promotion, encoder tuning, extra epochs or hyperparameter sweep ran.
