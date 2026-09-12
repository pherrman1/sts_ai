# Combat-transition model v1 — corrected rerun after independent review

Date: 2026-09-12. This is a corrected offline rerun on the already-collected
whole-combat transition corpus. The frozen source split and all Phase-1
targets are unchanged. No simulator collection, runtime Silver replacement,
model export, gameplay gate, or GCP job change was made.

Knowledge impact: durable experiment status and encoding protocol; the current
research KB and experiment ledger are updated in the same change.

## Decision

**Classification: `STRUCTURED_NEURAL_WINS_NO_CLEAR_FAMILY`.** XGBoost is
rejected as sufficient: both DeepSets and attention clearly improve Phase-1
prediction on the corrected frozen TEST split. Attention was the validation
finalist, but the attention-versus-DeepSets source-bootstrap intervals overlap,
so there is no evidence that attention improves over DeepSets. DeepSets is
selected as the Phase-2 default by a simplicity tie-breaker. This is an
offline interpretation only: TEST was inspected previously under the flawed
implementation, so these numbers are a corrected rerun of that frozen TEST
split, not an untouched first TEST. No runtime integration or Phase-2
implementation is authorized.

## Frozen corpus and provenance

- Producer Git SHA: `f0bbd7721e7cc1453976ebb91ee11ebe6127a2bf`
- Release executable SHA256:
  `d0a1c66faa931498660811a7406fbc6be93d63c5e7ef4f6f24c910e4f57c2872`
- Teacher: `silver-ordinary-fair-exact10k-combat-transition-runtime16-f0bbd77`
- Frozen teacher model hashes: policy
  `24793bd39dd1a35c8865035e458c3aa40616ef021cb26b05f914f72fb5e5a321`,
  floor `3a3420469b1d648e0e306d6cb6a7e85f3d3499105e3ff3a56eee6c579194ffe3`,
  win `fc52c14cb7239a33b3c1f9d0477ccb6c895fd51a07240fe804744e605067ad70`
- Input contract: `combat_predictor_input_v1`, field-schema hash
  `1a92692da9247008`; transition row: `combat_transition_row_v2` under
  `combat_transition_v1`.
- Source range: 25,000 requested seeds `4100016..4125015`; 24,999 completed;
  one quarantined source, `4102275` (`process_exit_134`).
- Corpus: 510,030 rows, SHA256
  `74c08aa0a3c30342d86cd45355fe17ffa9046963ad7c8cf71b1938f9cdc1cfde`.
- Final manifest SHA256:
  `33669cd99eed8317987192825b5111a68d1e60269c166def2fe568364e20ad59`.
- Shard audit: 322/322 shard manifests validated; no overlapping or
  out-of-range source groups; every row had exactly one valid raw capture.

The source-group split is
`SHA256("combat-transition-model-v1:" + sourceSeed)` interpreted as a
big-endian 64-bit value modulo 100: `<80` train, `<90` validation, otherwise
test. Counts are train 19,986, validation 2,496, test 2,517; split SHA256 is
`e9043bcceb9d95027711e6ff33afbfe1cae3cf9528f820c0ff68bddbb419db32`.

## Domain and encoding correction

The experiment now derives the entity domains from the repository canonical
constants in `apps/one_combat/run_features.h`: cards 372, relics 181, and
potions 48. Invalid entity IDs fail closed before either flat or neural
encoding; neural embeddings no longer clamp IDs.

| Entity | Canonical domain | Observed IDs | Previous bound | Previous flat truncation | Previous neural clamp/collision |
| --- | ---: | --- | ---: | ---: | ---: |
| Cards | 372 | 11..369 | 371 | 0 tokens / 0 rows | 0 tokens / 0 rows |
| Relics | 181 | 0..177 | 128 | 890,897 tokens / 339,996 rows | 890,897 tokens / 339,996 rows |
| Potions | 48 | 1..43 | 44 | 0 tokens / 0 rows | 0 tokens / 0 rows |

The corrected flattened representation has 3,115 fields, with continuous
globals kept continuous and `characterClass`, `encounter`, `roomClass`, and
`lastRoom` represented by deterministic one-hot fields. Neural models use
small embeddings for those four categorical globals and for card, relic, and
potion IDs. The corrected final models have 94,554 DeepSets parameters and
114,178 attention parameters.

## Model protocol and corrected results

Exact fit command:

```text
OMP_NUM_THREADS=8 /usr/bin/time -v -o /home/philippherrmann/sts_sweep/runs/combat-transition-model-v1/fit-time.txt python3 tools/combat_transition_model_experiment.py fit --prepared-dir /home/philippherrmann/sts_sweep/runs/combat-transition-model-v1 --output-dir /home/philippherrmann/sts_sweep/runs/combat-transition-model-v1 --device cuda --threads 8 --xgb-rounds 400 --nn-batch 2048 --nn-epochs 12 --nn-patience 3 --training-seed 20260911 --bootstrap-reps 1000
```

CUDA was required and used for XGBoost, DeepSets, and attention. The
validation-only selection froze XGBoost depth 6 with 400 survival rounds and
400 winning-HP rounds, DeepSets at 12 epochs, and attention at 12 epochs.
After that freeze, all three families were refit from scratch on
TRAIN+VALIDATION with those fixed lengths and then evaluated on TEST. No TEST
metric was used for early stopping or model selection. The same documented
seed `20260911` was used for NumPy/Torch family fits and XGBoost
`random_state`.

Validation composite scores (lower is better) were XGBoost `0.179316`,
DeepSets `0.171834`, and attention `0.169172`; validation selected attention.

Corrected TEST aggregate metrics (lower is better except AUC) were:

| Family | Survival AUC / Brier / logloss | Winning-HP MAE / RMSE / bias | Joint alive-HP MAE / RMSE / bias |
| --- | --- | --- | --- |
| XGBoost | 0.974997 / 0.018985 / 0.065183 | 0.075141 / 0.110923 / +0.000285 | 0.082427 / 0.125750 / −0.000703 |
| DeepSets | 0.978864 / 0.017780 / 0.060430 | 0.072614 / 0.106994 / −0.004751 | 0.078684 / 0.120493 / −0.003636 |
| Attention | 0.978805 / 0.017901 / 0.060792 | 0.072575 / 0.107032 / +0.000318 | 0.078781 / 0.120692 / +0.001465 |

Source-bootstrap 95% intervals for model-minus-model error were:

| Difference | Brier | Winning-HP MAE | Joint alive-HP MAE |
| --- | --- | --- | --- |
| DeepSets − XGBoost | [−0.001565, −0.000872] | [−0.002921, −0.002169] | [−0.004213, −0.003336] |
| Attention − XGBoost | [−0.001451, −0.000711] | [−0.002957, −0.002183] | [−0.004076, −0.003218] |
| Attention − DeepSets | [−0.000159, +0.000430] | [−0.000337, +0.000319] | [−0.000258, +0.000482] |

The first two rows are clearly below zero, but the attention-versus-DeepSets
row is not separated. The corrected comparison is therefore classified as
`STRUCTURED_NEURAL_WINS_NO_CLEAR_FAMILY`: XGBoost is rejected as sufficient,
both neural families clearly improve Phase-1 prediction, and DeepSets is
selected as the Phase-2 default by simplicity tie-breaker because attention has
no demonstrated improvement over DeepSets. This is not a claim that a numeric
practical-improvement threshold was preregistered.

## Cost, validation, and outputs

- Wall time: 2,132.17 s (35:32.17).
- CPU time: 2,204.24 s user+system (2,156.91 + 47.33).
- Peak resident memory: 17,515,476 kB (16.704 GiB).
- GPU: RTX 3060 Ti, CUDA `cuda:0`; peak observed fit use was approximately
  5.5 GiB VRAM at 100% utilization.
- Serialized model sizes and SHA256:
  - XGBoost survival: 2,377,591 bytes,
    `ed64dbc79b97af6b61d428975a3cb0acf5d12cf9cd5952a93eb55320f411883b`
  - XGBoost winning-HP: 2,601,729 bytes,
    `12807cbb02c8e53e1f7262a0ffab5521c5f32518af7a436c8491ad878cbd0352`
  - DeepSets: 388,702 bytes,
    `328c65f150ac7daa9db7dc7e2047b77cf8b88ef3c09b3da8ef57d75b7a2fd4c3`
  - Attention: 472,689 bytes,
    `a4545c54c8b99afb059b64c6ee36523f472e2e636040e166b32ded4218614b6f`
- Repository transition validator: PASS, exit 0; 510,030 rows, 24,999
  completed source seeds, one quarantined source in the manifest, zero
  quarantined rows, and outcomes 491,897 wins / 18,133 deaths.
- Unexpected health failures: zero. No new collection or retry was run.

Derived evidence is preserved at:

- Corpus run: `/home/philippherrmann/sts_sweep/runs/combat-transition-runtime-25k/`
- Experiment run: `/home/philippherrmann/sts_sweep/runs/combat-transition-model-v1/`
- Audit: `corpus_audit.json`; split: `split_manifest.json` and
  `split_manifest.sha256`; prepared data: `prepared.npz`;
  validator output: `final-transition-validation.json`.
- Model evidence: `model_evidence.json`; exact command: `fit-command.txt`;
  stdout: `fit-stdout.txt`; stderr: `fit-stderr.txt`; timing: `fit-time.txt`.

The experiment code and focused tests are committed; raw corpus/prepared data,
logs, and fitted model binaries remain external and are not added to Git.
