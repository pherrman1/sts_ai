# Heart leaf v1 (issue #605): offline gate, fixed before the full fit

Written 2026-10-17 ~17:45Z, after a smoke fit on ~1.4k partial TRAIN roots with an
inner TRAIN holdout; no VALIDATION row had been scored.

Data: §503 round-2 TRAIN (1,088 runs) and VALIDATION (320 runs), MAP roots that carry
a native snapshot (`STS_OOC_MCTS_ROOT_TRACE`). §503 CONFIRM and §497 TEST stay sealed.
Tails: `one_combat heartleaftail 111159000 16` on `ed3ba6f` (binary sha256
`fa70262b…6536b`), the §503 producer environment (student C prior and rollout policy,
rollout3, LEAF_VALUE=native, keys on).

Fit: `tools/heart_leaf_fit.py fit`, anchor weight w = 0.5, 3 TD rounds, XGBoost residual on
a TRAIN Platt base. VALIDATION picks the round and early-stops trees; nothing else is tuned
on it.

Gate on VALIDATION MAP roots, run-weighted (each run weighs the same), against public X2-B
recalibrated by the same TRAIN Platt fit:

1. BCE vs the real Heart outcome lower than Platt X2-B.
2. Per-act calibration for acts 1-3: |mean prediction − mean outcome| ≤ 0.03.
3. AUC not lower than Platt X2-B by more than 0.01.

PASS on all three makes the model a candidate for a paired A20 Heart A/B against the
public X2-B leaf, which needs Philipp's go. Any FAIL is reported as is; the model stays
research-only either way. Act 4 is reported, not gated (few snapshot roots).
