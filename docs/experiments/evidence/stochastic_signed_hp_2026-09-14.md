# Stochastic signed-HP categorical distribution

## Frozen protocol and provenance

Post-#170 clean app-managed baseline:
`443ed45f9bae4c5864dd7188645a04049b268928`.
PR #170 is merged. Its formal `HP_TARGET_INCONCLUSIVE` result is unchanged;
signed absolute ΔHP is the chosen engineering parameterization.

Corpus SHA256:
`74c08aa0a3c30342d86cd45355fe17ffa9046963ad7c8cf71b1938f9cdc1cfde`.
Nested source split SHA256:
`58e35f9f85eefd7617e616ddbfa7ee227c429ed4d312f7dacd470828f9a09094`.
Prepared NPZ SHA256:
`2badbb85ccd8329bcb886d50ef8a0b9b1bd2c043fda9445de9f9c2e7a4b6f9a5`.
TRAIN = nested TRAIN + VALIDATION, 286,581 supported victories,
17,972 assigned sources / 17,951 victory sources. HOLDOUT = nested HOLDOUT,
32,345 supported victories, 2,014 assigned / 2,012 victory sources.
No potion-certification restriction. HOLDOUT is reused engineering data.
There is no new simulator data or gameplay benchmark.

Frozen signed-ΔHP classes: **[-160, 143], K=304**, unit integer spacing.
Only predictor-visible preCurHp/preMaxHp on all globally supported states and
the frozen max-HP-delta class domain enter its derivation:
`min(1-preCurHp)` through `max(preMaxHp-preCurHp)+max(deltaMaxHp)`.
PreCurHp range [1,161], preMaxHp range [24,172]; upstream max-HP-delta
classes [0,3,4,5,6,7,8,9,10,11,12]. Canonical JSON domain provenance SHA256:
`f812c16ab1d220cd60e8a8915ebb368bcd7e6d9e48915eb8cce5c760fad78eec`.
The subsequent structural check verifies all 398,415 globally supported
winning targets are representable and legal. No classes are extended from
post-HP targets.

The established #170 64/2/4/128 attention encoder produces width-64 state;
append width-8 observed max-HP-delta embedding, then Linear(72,64), ReLU,
Linear(64,304). Condition on true observed max-HP delta to isolate HP.
Mask illegal classes to negative infinity before FP32 log-softmax:
`1 <= preCurHp + deltaHp <= preMaxHp + observedDeltaMaxHp`.
NLL is the sole loss. No multitask heads. TRAIN-only continuous-input
normalization, AdamW lr 0.001, weight decay 0.0001, batch 2,048,
gradient clip 1.0, trimmed padding, FP16 AMP initial scaler 16,384.
Train from scratch, seeds 20260912/20260913/20260914, exactly ten epochs;
no epoch selection. All fits finish before HOLDOUT prediction/scoring.

Saved #170 raw point predictions SHA256, verified before comparison:
`22b285413bb31caac4dfe23dba79e80437ec91a42ed2ae534105370db6bca184`.
Match exact row IDs, source IDs and each training seed. For CRPS, round
reconstructed point HP with floor(postHP+0.5), then clamp to [1,postMaxHp],
the documented #170 operational integer control. Its degenerate discrete CRPS
is absolute integer HP error. Categorical CRPS sums squared CDF differences
on the same integer unit spacing (translation from ΔHP to post HP is invariant).
Mean safety MAE compares expected post HP against #170's saved raw continuous
post HP predictions, matching its primary accuracy metric.

For each primary metric, average rowwise categorical-minus-point differences
across the three seeds, then source-bootstrap the row-weighted mean with
1,000 resamples, seed 20260914. CRPS CI strictly below zero and mean-MAE CI
not strictly above zero qualifies; either CI strictly above zero rejects;
otherwise inconclusive. No practical threshold or slice override.
Calibration uses equal-tailed inclusive integer intervals at 50/80/95%;
width = upper-lower HP. Sampling uses 16 categorical draws per HOLDOUT row,
seed 20260915 + training seed. No sampled-HP clipping. Derive ending HP
fraction directly for the existing potion decoder, with no retraining.

## Verification and commands

- `python3 tools/agent/worktree.py preflight .`: app-managed detached baseline,
  external writable Git metadata.
- `python3 tools/agent/worktree.py check .`: pinned submodules OK.
- `tools/agent/doctor.sh`: all checks passed.
- `python3 -m unittest tools.test_combat_transition_stochastic_hp tools.test_combat_transition_hp_targets tools.test_combat_transition_attention_ablation`:
  27 tests, OK (exit 0).
- `python3 tools/test_combat_transition_stochastic_hp.py`: 7 tests, OK.
- `cmake --preset linux-gcc-debug`: configure successful, exit 0.
- `ctest --preset linux-gcc-test -R '^combat_transition_stochastic_hp_selftest$' --output-on-failure`:
  1/1 passed, exit 0.
- `git diff --check`: exit 0.

```sh
python3 -m tools.combat_transition_stochastic_hp prepare \
  --prepared-dir /tmp/sts-phase2-attention-audit-20260913 \
  --control-dir /home/philippherrmann/sts_sweep/runs/hp-targets-20260914 \
  --output-dir /home/philippherrmann/sts_sweep/runs/stochastic-hp-20260914 \
  --baseline-sha 443ed45f9bae4c5864dd7188645a04049b268928
```

Prepare exited 0, validating hashes, counts, source alignment and structural
support. Fits await independent implementation review and a frozen clean SHA.
No scientific classification is available yet. Checkpoints, raw probabilities,
samples, preflight, recipe, results and hashes stay in the external output
directory above. Survival, max-HP modeling, potion weights, relic support and
RNG contracts are unchanged. No runtime C++ integration, relic training or
`combatRng[6]` solution. Knowledge impact: maintained research protocol and,
once executed, experiment evidence/current status.
