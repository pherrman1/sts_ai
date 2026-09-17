# Scratch width-96 DeepSets survival experiment

**SURVIVAL_DEEPSET_REJECTED.** One requested width-96 scratch arm completed.

## Protocol and provenance

- Implementation baseline (PR #217 dependency): `6fa601d9429db1a1a266e34c63252ce4861f9d5a`.
- Frozen execution SHA: `2e56f5de48fab5002684af8080decc988e69189d`.
- Entity and global outputs 96, concat 384, trunk 384→192→96, linear head 96→1.
- Card/relic embeddings remain 48, potion embeddings 32, slots and categorical globals 8. Existing feature transforms and sum pooling reused unchanged.
- Scratch random initialization, no checkpoint or partial warm-start mapping. All 408,183 TRAIN rows supply fixed scalar normalization (constant-feature floor 1e-6).
- Survival BCE only; FP32 AdamW, encoder LR 1e-4, head LR 1e-3, weight decay 1e-3, batch 512, clip 1.0, seed 20260912, minimum 12, maximum 40 epochs, patience 6.
- Original source-disjoint TRAIN/VALIDATION split; 50,406 VALIDATION rows. Earliest strict VALIDATION survival NLL selects the checkpoint.
- Same fixed NLL +2%, Brier +5%, death/low-HP NLL +10% and validity gates.
- 167257 parameters (including 97 in the head); about 1.77x the 94,489-parameter linear width-64 model.

## Result

| Metric | Attention | Width-96 | Relative gap | Gate |
|---|---:|---:|---:|---|
| nll | 0.059494425 | 0.065301903 | +9.7614% | FAIL |
| brier | 0.017815094 | 0.019292932 | +8.2954% | FAIL |
| deaths NLL | 0.989065945 | 1.201135635 | +21.4414% | FAIL |
| lowPreHp NLL | 0.398080587 | 0.430433214 | +8.1272% | PASS |

Selected epoch 14 / 20; patience stop. AUC 0.975520368. Validity passes. No speed screen because quality is not GO.

## Full history

| Epoch | TRAIN NLL | VALIDATION NLL | VALIDATION Brier |
|---:|---:|---:|---:|
| 1 | 0.103043742 | 0.082841039 | 0.023585891 |
| 2 | 0.072781113 | 0.075446166 | 0.022021275 |
| 3 | 0.070130075 | 0.072744623 | 0.021143451 |
| 4 | 0.068368310 | 0.071004182 | 0.020741569 |
| 5 | 0.066918665 | 0.070382036 | 0.020593243 |
| 6 | 0.066039788 | 0.069599696 | 0.020403925 |
| 7 | 0.064801893 | 0.068802953 | 0.020116007 |
| 8 | 0.063673099 | 0.067576773 | 0.019930584 |
| 9 | 0.062827693 | 0.067236930 | 0.019914374 |
| 10 | 0.061889105 | 0.067210823 | 0.019844186 |
| 11 | 0.061097983 | 0.068217807 | 0.019968048 |
| 12 | 0.060483926 | 0.065898694 | 0.019459797 |
| 13 | 0.059627728 | 0.067217425 | 0.019981980 |
| 14 | 0.059017636 | 0.065301903 | 0.019292932 |
| 15 | 0.058249342 | 0.066725515 | 0.019870745 |
| 16 | 0.057562162 | 0.067645155 | 0.020262785 |
| 17 | 0.056725786 | 0.066459365 | 0.019426737 |
| 18 | 0.056016392 | 0.066792570 | 0.019504063 |
| 19 | 0.055111242 | 0.066372842 | 0.019519845 |
| 20 | 0.054414840 | 0.066005476 | 0.019455547 |

## Selected slices

| Slice | Rows | Deaths | NLL | Brier |
|---|---:|---:|---:|---:|
| boss | 5444 | 1169 | 0.303678066 | 0.095465720 |
| deaths | 1816 | 1816 | 1.201135635 | 0.385290921 |
| lowPreHp | 756 | 292 | 0.430433214 | 0.142114684 |
| normal | 44962 | 647 | 0.036439311 | 0.010069929 |
| victories | 48590 | 0 | 0.022851316 | 0.005614143 |

## Interpretation and limits

The specified wider scratch recipe did not salvage survival quality. Its NLL is worse than the earlier warm-started width-64 strong-WD result (0.062930815), but that is not an isolated width comparison: initialization and normalization differ too. No matched width-64 scratch survival-only control or replicate was run. This result does not prove width can never help, nor prove that pairwise interactions are necessary. Reusing VALIDATION across experiments adds selection bias.

Stop this bounded scaling experiment: no extra widths, optimizer tuning, continuation, distillation, TEST, runtime, gameplay, export or promotion. No speed claim follows from parameter count.

## Checks and artifacts

- 10 focused Python tests PASS (0.564 s); CTest 2/2 PASS (3.33 s); worktree and diff checks PASS.
- Separate post-run checkpoint reload exactly reproduced all VALIDATION metrics/slices and predictions; scratch initialization hashes, fixed normalization, selected epoch and every permutation hash verified.
- No independent implementation review passed. Review delegation calls failed before starting any reviewer; local tests/post-run checks do not replace independent review.
- Exactly one scientific fit completed. The earlier failed implementation from the previous turn never trained.

Command at the frozen execution SHA:
```sh
python3 tools/combat_transition_survival_wide96.py --experiment-sha "$(git rev-parse HEAD)" --output /home/philippherrmann/sts_sweep/runs/survival-wide96-20260917
```

Raw receipt: `/home/philippherrmann/sts_sweep/runs/survival-wide96-20260917/results.json`.
SHA256 `1865b7e4ee01cffbc49f9c3bbc5421238d3dc7189423ff326f1e4e39e8b71211`.
Checkpoint: `/home/philippherrmann/sts_sweep/runs/survival-wide96-20260917/selected.pt`.
SHA256 `c1d98c925a7acd6eef699fd52539b733a31a5de33a8ae66fc16f7073063a8050`.
The [complete receipt](survival_wide96_2026-09-17.json) includes all histories, gates, hashes, source bindings and calibration bins.

**Knowledge impact:** experiment evidence and current research status; no qualified default.
