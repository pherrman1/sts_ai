# Six-arm survival DeepSets LR/weight-decay sweep

**SURVIVAL_DEEPSET_SWEEP_REJECTED**. All six fixed arms completed and failed
at least one unchanged gate. This is evidence about these six optimizer
settings under this budget, not a proof that DeepSets cannot model survival.

## Provenance and protocol

- Main baseline: `0b7d4607c49b5db8082f4cad89579f3e33635f41`.
- Frozen six-arm execution: `92b404e03a91a6c95a592de80c7e04fe78f2d9af`.
- Identical corrected PR #205 warm-start and fresh linear survival head for
  all arms, seed 20260912, identical original TRAIN epoch permutations.
- FP32 AdamW, batch 512, clip 1.0, unweighted survival BCE. Per-arm earliest
  strict VALIDATION NLL minimum; floor 12, cap 40, patience 6. Only LR/WD vary.
- TRAIN 408,183 rows / 19,986 sources; VALIDATION 50,406 / 2,496; same
  hash-bound original split. TEST encoding/inference/scoring all zero.
- Fixed acceptance limits: relative overall NLL +2%, Brier +5%, death NLL
  +10%, low-pre-HP NLL +10%, plus finite/probability/population validity.
- Each saved checkpoint was reloaded and its full VALIDATION metrics/slices
  reproduced exactly. All batch-order hashes were regenerated and checked;
  all source memberships, normalization buffers and initial states verified.

## Results

| Arm | Encoder LR | Head LR | WD | Selected / completed epoch | Stop | NLL | Brier | NLL gap | Brier gap |
|---|---:|---:|---:|---:|---|---:|---:|---:|---:|
| baseline | 0.0001 | 0.001 | 0.0001 | 23 / 29 | patience | 0.063063473 | 0.018898282 | +5.9990% | +6.0802% |
| lowerLr | 5e-05 | 0.0005 | 0.0001 | 34 / 40 | patience | 0.063237533 | 0.018927718 | +6.2915% | +6.2454% |
| lowerLrWd | 5e-05 | 0.0005 | 0.0005 | 34 / 40 | patience | 0.063131146 | 0.018883642 | +6.1127% | +5.9980% |
| moreWd | 0.0001 | 0.001 | 0.0005 | 24 / 30 | patience | 0.063048050 | 0.018904224 | +5.9730% | +6.1135% |
| muchLowerLr | 2e-05 | 0.0002 | 0.0001 | 39 / 40 | max epoch | 0.064092025 | 0.019041218 | +7.7278% | +6.8825% |
| strongWd | 0.0001 | 0.001 | 0.001 | 20 / 26 | patience | 0.062930815 | 0.018841730 | +5.7760% | +5.7627% |

All arms fail overall NLL and Brier. `muchLowerLr` also fails death NLL
(+13.2822%); the other death and all low-pre-HP NLL gates pass. All validity
checks pass. `lowerLr` and `lowerLrWd` reach patience exactly at epoch 40;
`muchLowerLr` reaches the cap without patience, selecting epoch 39. Its late
improvement leaves schedule-specific optimization uncertainty, but it is
still rejected under the fixed 40-epoch contract. No arm is extended.

The reference NLL is 0.05949442461133003 and Brier 0.01781509444117546.
Strong-WD selects epoch 20: NLL 0.06293081492185593, Brier
0.018841730430722237. It improves baseline NLL by only 0.2104% and Brier by
0.2992%, leaving +5.7760% / +5.7627% gaps to Attention. No setting materially
closes the quality gap.

### Strong-WD slices (Attention / DeepSets)

| Slice | Rows | Deaths | NLL A | NLL B | Brier A | Brier B |
|---|---:|---:|---:|---:|---:|---:|
| boss | 5444 | 1169 | 0.280834377 | 0.294944167 | 0.088252187 | 0.092734195 |
| deaths | 1816 | 1816 | 0.989065945 | 1.058280587 | 0.323512346 | 0.339271605 |
| lowPreHp | 756 | 292 | 0.398080587 | 0.410817713 | 0.129600912 | 0.134829372 |
| normal | 44962 | 647 | 0.032694578 | 0.034838628 | 0.009286569 | 0.009894829 |
| victories | 48590 | 0 | 0.024752669 | 0.025730664 | 0.006389983 | 0.006866002 |

## Validation histories: baseline versus strong-WD

Only the NLL-selected checkpoints retain Brier scores. Per-epoch Brier was
not recorded and cannot be reconstructed from unretained epoch checkpoints.
The full 205-epoch histories for all arms are in the JSON receipt.

| Epoch | Baseline TRAIN NLL | Baseline VALIDATION NLL | Strong-WD TRAIN NLL | Strong-WD VALIDATION NLL |
|---:|---:|---:|---:|---:|
| 1 | 0.091265066 | 0.074052602 | 0.091264387 | 0.074056700 |
| 2 | 0.067889201 | 0.070584677 | 0.067870392 | 0.070546068 |
| 3 | 0.065362033 | 0.067974590 | 0.065338117 | 0.067941569 |
| 4 | 0.063570540 | 0.066336691 | 0.063502087 | 0.066303477 |
| 5 | 0.062093827 | 0.066631958 | 0.062006875 | 0.066668347 |
| 6 | 0.061473539 | 0.065461121 | 0.061367404 | 0.065433070 |
| 7 | 0.060663820 | 0.064579062 | 0.060585360 | 0.064594954 |
| 8 | 0.059899431 | 0.064710528 | 0.059858746 | 0.064690500 |
| 9 | 0.059586292 | 0.065480903 | 0.059532898 | 0.065304257 |
| 10 | 0.059107696 | 0.064673029 | 0.059026685 | 0.064432465 |
| 11 | 0.058624613 | 0.065938599 | 0.058556315 | 0.065674864 |
| 12 | 0.058327233 | 0.063616231 | 0.058282351 | 0.063559726 |
| 13 | 0.057869859 | 0.065026127 | 0.057803188 | 0.065325916 |
| 14 | 0.057543185 | 0.063342273 | 0.057486847 | 0.063389599 |
| 15 | 0.057114045 | 0.064687185 | 0.057063740 | 0.064624012 |
| 16 | 0.056808861 | 0.063912779 | 0.056766463 | 0.063944347 |
| 17 | 0.056466189 | 0.064569116 | 0.056413774 | 0.064541832 |
| 18 | 0.056111907 | 0.063840538 | 0.056059524 | 0.063733853 |
| 19 | 0.055712736 | 0.064175881 | 0.055657430 | 0.064485162 |
| 20 | 0.055516714 | 0.063118055 | 0.055460007 | 0.062930815 |
| 21 | 0.055307713 | 0.064052805 | 0.055289746 | 0.064104669 |
| 22 | 0.054829676 | 0.064160526 | 0.054765564 | 0.064230062 |
| 23 | 0.054579460 | 0.063063473 | 0.054556265 | 0.062964179 |
| 24 | 0.054247818 | 0.063214809 | 0.054264661 | 0.063217610 |
| 25 | 0.053931686 | 0.063909620 | 0.053987121 | 0.064021841 |
| 26 | 0.053707421 | 0.063221678 | 0.053703360 | 0.063042052 |
| 27 | 0.053355021 | 0.063418075 | — | — |
| 28 | 0.053383287 | 0.064332530 | — | — |
| 29 | 0.052640811 | 0.063824207 | — | — |

## Interpretation and limits

The train/validation divergence is consistent with overfitting or calibration
limitations, but does not identify a unique cause or prove adequate capacity.
This small LR/WD sweep did not improve generalization enough. Original rejected
fit evidence is unchanged. Further LR decay is optional and remains a separate
experiment with a fixed schedule; **no continuation was executed**. No speed
screen ran because quality did not pass. No architecture/loss change, TEST,
runtime, gameplay, native export, or promotion occurred. Reusing VALIDATION
for six-arm selection increases selection optimism; this is development
validation, not an independent holdout result.

## Execution and reporting corrections

The initial attempt at `d97debe0af696a811446e890f7f09031b77bdc86` was
interrupted during lowerLr. It is preserved, excluded, and not treated as a
completed arm. The final six-arm run started every arm fresh; no partial
resume or additional seed was used. Total final training time was 843.18 s.

Post-run inspection found reporting defects: the aggregate decision checked
only overall gates, optimizer-scope LR fields retained defaults, and the
recipe contained unused optional-continuation metadata with an arbitrary
trigger. Per-arm full evaluation already checked all gates correctly. The
continuation branch never ran. Reporting was repaired and the unused path
removed after execution, without changing six-arm updates or selections.
The raw receipt is preserved verbatim; the audited receipt explicitly records
these differences and recomputes all gates from reloaded checkpoints.

No independent implementation review passed before execution. Focused tests
and post-run checkpoint verification are not an independent review. The draft
PR remains the review handoff. An attempted broad local build/CTest run was
interrupted and is not claimed as passing; focused suites and CTest are used.

## Artifacts

Raw receipt:
`/home/philippherrmann/sts_sweep/runs/survival-specific-deepset-sweep-20260917-final/results.json`.
SHA256 `f347d12cf8b1778cc01961f720fd63d96f6fca6bda740893da27ec37f058c555`.
Checkpoints remain under each arm's external `selected.pt`; their exact
hashes, model states, complete histories and all slices are in the
[audited receipt](survival_deepset_sweep_2026-09-17.json).

**Knowledge impact:** current research and chronological experiment evidence;
no architecture or runtime default is qualified or changed.
