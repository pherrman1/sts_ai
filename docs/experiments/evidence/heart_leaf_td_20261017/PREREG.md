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

Amendment 2026-10-17 ~17:20Z, before any full fit: at Philipp's request (keys thread,
17:12Z/17:14Z) the features gained key reachability inputs (schema
`heart-leaf-features-v2`, `d6cf4b8`, binary sha256 `e976634c…`); the v1 tail run was stopped
at about half and is not used. No hand-made key bonus: key value comes only from the Heart
labels. Gate unchanged.

## Amendment 2 (2026-10-17 ~19:15Z): retrain candidate and one CONFIRM scoring

Written after the VALIDATION work below and before any §503 CONFIRM file is extracted.
Philipp chose "Retrain, then CONFIRM" (18:13Z); the coordinator relayed that CONFIRM may be
opened once for a frozen, reviewed candidate.

VALIDATION-era changes (all chosen on VALIDATION, so VALIDATION is no longer a clean test):

- Variants (`variants_td2.*`): anchor weight 0.5 stays (1.0, 0.25 and 0 are worse on BCE).
- New column `hlCritic` (feature schema v3): an XGBoost regression of the heart1 value head
  (`heartleaftail` rows with `STS_OOC_HEART1=heart1.bin`, `h1rows.jsonl` sha256 `b69c492d…`)
  on the v2 features, fit on TRAIN roots; the native model evaluates it from the features,
  summed in float32 like XGBoost (`CompactTreeNet::marginFloat32`).
- One Act-4 logit offset (−0.713), fitted on out-of-fold TRAIN margins (4 seed folds). TRAIN
  and VALIDATION both show the rollout tails overrating Act 4 (TRAIN 0.61 vs 0.46). Per-act
  offsets for acts 1-3 fitted the same way made VALIDATION worse (`actcal_td2.*`) and are not used.
- The #611 key-flag runs do not exist (Philipp declined a key-timing A/B, 17:29Z), so no
  key-run data was added.

Frozen candidate `models/candidates/heart_leaf_td2/` (manifest sha256 `1b1ad13e…`, residual
`c7a42e88…` 129 trees, critic `417769c0…` 600 trees, TD round 2). Native parity on 2,000
VALIDATION roots: max |Δ| 2.1e-7. The `score` command re-evaluates the exported tree files
without XGBoost and reproduces the fit on VALIDATION:

| VALIDATION (320 runs) | BCE | AUC | act 1 pred/real | act 2 | act 3 | act 4 |
|---|---:|---:|---|---|---|---|
| Platt X2-B | 0.3133 | 0.699 | 0.086/0.103 | 0.129/0.119 | 0.292/0.202 | 0.344/0.423 |
| td2 | 0.3038 | 0.735 | 0.088/0.103 | 0.124/0.119 | 0.233/0.202 | 0.418/0.423 |

Paired run-bootstrap BCE difference −0.0094 [−0.0171, −0.0010]. Act 3 misses the 0.03 bar
by 0.001 (run-bootstrap gap interval [−0.031, +0.092]), so the strict gate is FAIL on
VALIDATION.

CONFIRM procedure, run once after an independent review of the frozen SHA:

1. Extract every `deliveries/w*/SEALED-confirm.tar.gz` of §503 round 2 into a new directory.
2. `one_combat heartleaftail 0 0 OUT ROOTS…` on the frozen commit over the CONFIRM root
   traces (features only: no rollouts, no heart1, no seeds started).
3. `tools/heart_leaf_fit.py score --manifest models/candidates/heart_leaf_td2/heart_leaf.json
   --split confirm` on those rows.

Decision rule: the same three criteria as above, run-weighted on CONFIRM MAP roots with
snapshots: BCE below Platt X2-B (TRAIN Platt from the manifest); |mean − actual| ≤ 0.03 in
acts 1-3; AUC not lower by more than 0.01. PASS on all three: the candidate may go to a
paired A20 Heart A/B against the X2-B leaf, size and workers from Philipp. Any FAIL: reported
as is, no A/B on this candidate. The paired BCE interval and per-act intervals are reported
as description. No refit, threshold change or second CONFIRM scoring follows either outcome.
