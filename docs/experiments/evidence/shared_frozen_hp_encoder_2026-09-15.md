# Frozen survival representation for signed-HP decoding

**Decision: `SHARED_ENCODER_HP_REJECTED`.** A newly initialized signed-HP
decoder trained on the frozen current-main survival representation is materially
worse than the byte-identically initialized decoder trained on the frozen
dedicated HP representation. Stop this shared-encoder path before maxHP/potion
composition, runtime changes, or export work.

## Boundaries and provenance

- Baseline: `cde61c85b8a9ad8500cd3ca6e18607ff33bb6e1a`.
- Experiment code: `d10908c3336ec00db62d41af5cb12dc08167723e`.
- Full-union survival component SHA256:
  `e150180a9112f52a94cfa60770adb6c0a48517a7d94a4c26f6e5896e85269c18`.
- Full-union HP component SHA256:
  `0c8b5aa8c5218d6cd6102b768cc86a474c9ef30953d4b034caedcc41a426109b`.
- Both component receipts bind source `1c31b7eb0a7660d43bc27e0849a8955dd0c3daae`,
  the same preparation cache SHA256
  `e1c25f2758bf56c7cff392ea02342d809f3ad7427c70b64166244a6b714a251d`,
  original source-grouped TRAIN fitting, and VALIDATION-only checkpoint
  selection. The #187 TRAIN+VALIDATION-refit survival encoder was not used.
- TRAIN: 393,677 victories / 19,986 sources. VALIDATION: 48,590 victories /
  2,496 sources. Historical TEST was not scored or selected.
- Row-ID SHA256:
  `02ca974b977dd42784f1c43a60c6216270779ce3d1670e2e2ce975967b9612e2`;
  source-group sequence SHA256:
  `f29f43065913889181fcb27981536701cf29d8273c54425798984ff801545995`.

## Frozen paired recipe

Both encoders were frozen and cached once as 64-dimensional FP32 arrays with
the MHA fastpath disabled identically. Each arm used the same seed (`20260912`),
12 epochs, AdamW, learning rate `1e-3`, weight decay `1e-4`, batch size 512,
gradient clip 1, and AMP-FP16 decoder arithmetic. Only a maxHP-delta embedding
and `64 + 8 -> 64 -> 304` ReLU head trained. Decoder initial-state hashes and
complete batch-order hashes are identical. Only TRAIN rows entered gradient
updates; each arm independently retained its earliest strict minimum VALIDATION
NLL checkpoint.

The cached reference/dedicated-HP representation SHA256 is
`e0c5181193a3b279740744634c129247c6dc9cc72124c8ede71ce629aeb700dc`;
the candidate/survival representation SHA256 is
`f5e6f4ed62eec4ab8859d09edb328224a7d876682a65e7f0a3429173951cf4a4`.
Every evaluated distribution normalized within `1e-6` and assigned exactly
zero probability outside the legal signed-HP support.

## Validation result

| Metric | Dedicated HP A | Survival B | B - A | Relative |
| --- | ---: | ---: | ---: | ---: |
| signed-HP NLL | 2.496705532 | 2.680527687 | +0.183822155 | +7.362589% |
| signed-HP CRPS | 3.618011474 | 4.087017666 | +0.469006192 | +12.963093% |
| expected ending-HP MAE | 5.355416796 | 5.986446000 | +0.631029204 HP | +11.7828% |

The relative MAE is descriptive; the decision gate uses the absolute HP delta.
The reference selected epoch 8 and the candidate selected epoch 12.

Important existing slices also regress:

| Slice | Rows | NLL relative | CRPS relative | expected-HP MAE delta |
| --- | ---: | ---: | ---: | ---: |
| healing | 10,629 | +16.4324% | +26.9187% | +1.224851 HP |
| low pre-HP fraction | 433 | +14.3458% | +35.7311% | +1.350284 HP |
| damage | 24,466 | +4.6550% | +9.1848% | +0.517771 HP |

The candidate misses the preregistered limits of at most +1% NLL, +1% CRPS,
and +0.1 HP expected-MAE by wide margins. The frozen survival representation
does not support competitive signed-HP decoding under this fixed decoder and
training recipe. Because its selected epoch is the final allowed epoch, this
screen does not distinguish absent information from information that this
head/optimizer decodes more slowly or with greater difficulty. No extra epochs
were run because that would be a new experiment. This is not a claim that no
shared architecture could work.

## Receipts and scope

External immutable run directory:
`/home/philippherrmann/sts_sweep/runs/shared-frozen-hp-encoder-20260915/`.
`results.json` SHA256 is
`40281ce7fd5a7bb7f1e99469529c9ee483ce575ce2db7a92e5e8ba3fdf091e87`;
`validation_predictions.npz` SHA256 is
`e56e0631aa4201464001ee21959e4e2fd22df1e90219c889314f2b08775351b6`.
The tracked compact `shared_frozen_hp_encoder_2026-09-15/results.json` retains
the complete per-epoch TRAIN NLL and VALIDATION NLL/CRPS/expected-MAE history,
selected epochs, parity checks, artifact bindings and final decision. The large
prediction arrays remain external.
Caching took 46.28 seconds; complete decoder fit/scoring stages took 62.10
seconds (reference) and 47.94 seconds (candidate), descriptive only.

No new data, simulator/gameplay seeds, TEST evaluation, encoder tuning,
adapter, maxHP/potion/relic changes, runtime integration, export, or composed
qualification ran.
