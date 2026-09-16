# Frozen DeepSets survival screen (2026-09-16)

Decision: **`DEEPSET_SURVIVAL_REJECTED`**.

## Question

Can the qualified frozen PR #205 DeepSets representation support survival
prediction when only a new survival head is trained? Arm A uses the frozen
TRAIN-only full-union survival Attention encoder; Arm B uses the frozen
corrected PR #205 DeepSets encoder. Both use the same fresh survival-head
architecture, byte-identical initialization, seed, batch permutations,
optimizer, and 12-epoch recipe.

## Provenance

- Baseline: `4c8ff3fe044626c6d18226e5f4091a0d1cb842d1` (current `main` after PR #210).
- Corpus SHA256: `74c08aa0a3c30342d86cd45355fe17ffa9046963ad7c8cf71b1938f9cdc1cfde`.
- Source SHA: `1c31b7eb0a7660d43bc27e0849a8955dd0c3daae`.
- Preparation cache SHA256: `e1c25f2758bf56c7cff392ea02342d809f3ad7427c70b64166244a6b714a251d`.
- Reference survival component SHA256: `e150180a9112f52a94cfa60770adb6c0a48517a7d94a4c26f6e5896e85269c18`.
- DeepSets checkpoint / receipt SHA256: `bee6800d…c3003dc663` / `83b2482e…5074c769`.
- Reused DeepSets representation / row-ID SHA256: `9232027d…d37352af` / `3dfecd1d…112e437`.
- TRAIN: `408,183` rows / `19,986` sources. VALIDATION: `50,406` rows / `2,496` sources.
- TEST: `51,441` corpus rows, `0` encoded, `0` inferred, `0` scored.
- Fresh-head initialization SHA256: `fd275d8d…322c5e`; A/B byte-identical: `true`.
- Batch-order SHA256: `7b06bbba98360d80aa5ca47b9fb3f7adcd7b80f4bdbe0ccebabd2fbecc93ace7`.

The original reference component validation NLL reproduced as `0.059494425`
against the recorded `0.059494428`. The saved DeepSets representations were
bound by original row ID, and four regenerated DeepSets rows had maximum
absolute error below `1e-5`.

## Training

| Epoch | A validation NLL | B validation NLL |
|---:|---:|---:|
| 1 | 0.059881758 | 0.121707596 |
| 2 | 0.059650283 | 0.102821737 |
| 3 | 0.059547596 | 0.095346451 |
| 4 | 0.059517063 | 0.091958612 |
| 5 | 0.059526265 | 0.089891471 |
| 6 | 0.060001477 | 0.089021959 |
| 7 | 0.059428923 | 0.087176695 |
| 8 | 0.059419435 | 0.086135254 |
| 9 | 0.059489783 | 0.085233875 |
| 10 | **0.059312280** | 0.084455028 |
| 11 | 0.059374176 | 0.083958976 |
| 12 | 0.059382975 | **0.083209150** |

Selected epochs are A=`10` and B=`12`. Only survival-head parameters entered
the AdamW optimizers; both finite forward/backward smoke checks passed. Both
selected checkpoints were reloaded from disk and reproduced their metrics
exactly.

## Metrics

| Metric | A | B | B relative to A |
|---|---:|---:|---:|
| Validation NLL | 0.059312280 | 0.083209150 | **+40.2899%** |
| Brier | 0.017769713 | 0.024436526 | **+37.5178%** |
| ROC-AUC | 0.494014 | 0.504300 | diagnostic |
| Accuracy at 0.5 | 0.975479 | 0.966948 | diagnostic |
| Mean predicted survival | 0.963590 | 0.961702 | diagnostic |
| Observed survival rate | 0.963973 | 0.963973 | matched |

Outcome and severity slices were computed on the same VALIDATION rows. Observed
death NLL was `1.000721` for A versus `1.443890` for B (`+44.2850%`). The
low-pre-HP slice (`pre.curHp / pre.maxHp <= 0.25`) had `756` rows and `292`
deaths; NLL was `0.396740` versus `0.618307` (`+55.8470%`). Victory NLL was
`0.024128` versus `0.032355`; normal-combat NLL was `0.032612` versus
`0.044770`; boss-combat NLL was `0.279827` versus `0.400679`.

## Gates and boundary

- Core NLL gate: `<= +2%` — **failed**.
- Core Brier gate: `<= +5%` — **failed**.
- Observed-death NLL gate: `<= +10%` — **failed**.
- Low-pre-HP NLL gate: `<= +10%` with sufficient support — **failed**.

This rejects the exact frozen PR #205 DeepSets representation plus matched
survival-head recipe for survival. It does not prove intrinsic information
absence, justify fine-tuning the general encoder, or evaluate a separate
survival-specific encoder. No TEST scoring, runtime/native export, C++ change,
gameplay, OOC MCTS, potion work, architecture sweep, or promotion occurred.

**Knowledge impact:** current research status and experiment evidence only;
runtime defaults and qualified components remain unchanged.
