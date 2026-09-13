# Winning-combat HP target comparison

## Frozen design

Baseline: current clean main `31c7a1b9adff9d55c158f5ab560f89176c0e99b3`,
authorized in place of the handoff's older main SHA. The sole conceptual
variable is final HP fraction versus signed absolute HP change. Both models
train from scratch with the established 64/2/4/128 typed attention encoder,
an observed max-HP-delta class embedding of width 8, and identical 72→64→1
ReLU HP heads. There are no survival, max-HP, potion, or relic prediction heads.
Max-HP modeling is untouched. No simulator collection or gameplay runs occur.

Corpus SHA256:
`74c08aa0a3c30342d86cd45355fe17ffa9046963ad7c8cf71b1938f9cdc1cfde`.
Nested split SHA256:
`58e35f9f85eefd7617e616ddbfa7ee227c429ed4d312f7dacd470828f9a09094`.
TRAIN combines nested TRAIN and VALIDATION: 17,972 assigned sources,
17,951 sources with supported victories, 286,581 victory rows.
HOLDOUT: 2,014 assigned sources, 2,012 sources with supported victories,
32,345 victory rows. Every globally supported victory participates, without
potion-consumption certification. This HOLDOUT is reused engineering data,
not a pristine never-inspected corpus; it has not been used to choose between
these HP target formulations.

Population target normalization from TRAIN victories only:

| Target | Mean | Standard deviation |
| --- | ---: | ---: |
| Final HP fraction | 0.7833217376696806 | 0.24114241297407096 |
| Signed HP change | -5.9811990327342 | 12.527645158539638 |

Both arms use scalar standardized MSE, AdamW lr 0.001, weight decay 0.0001,
batch 2,048, gradient norm clip 1.0, padding trimming, FP16 AMP (initial
scaler 16,384), dropout 0.1, and exactly ten epochs. Paired seeds are
20260912, 20260913, 20260914. No HOLDOUT epoch selection or tuning.
Encoder continuous-input normalization also uses these same TRAIN victories.
Initialization, shuffled batches, dropout random seeds, and observed delta
conditioning match within each pair; audit hashes verify initialization,
batch order, and conditioning. Each arm resets the RNG before initialization.

Primary scoring reconstructs continuous post-combat HP without rounding or
clamping. Differences are delta-target minus fraction-target absolute errors.
Average each row's differences over paired training seeds first, then source
bootstrap the row-weighted difference with 1,000 resamples, seed 20260914.
Delta wins only if CI is strictly negative and all three seed estimates are
negative; fraction wins only if both conditions are strictly positive;
otherwise the result is HP_TARGET_INCONCLUSIVE. No practical-effect threshold.

Fixed descriptive pre-max-HP bins: [0,60), [60,80), [80,100), [100,120),
[120,∞). Pre-HP-fraction bins are left-closed/right-open quarters, with 100%
included in the last bin. Other slices: act, native room class, HP-change
direction, zero/nonzero max-HP delta. Integer HP uses floor(prediction+0.5)
followed by legal clipping to [1, observed postMaxHp].

## Reproduction and artifacts

```sh
python3 -m unittest tools.test_combat_transition_hp_targets
python3 -m tools.combat_transition_hp_targets prepare \
  --prepared-dir /tmp/sts-phase2-attention-audit-20260913 \
  --output-dir /home/philippherrmann/sts_sweep/runs/hp-targets-20260914 \
  --baseline-sha 31c7a1b9adff9d55c158f5ab560f89176c0e99b3
```

The fit command uses the same arguments with `fit` and `--reviewed-sha` set
to the frozen independently reviewed clean implementation commit. It refuses
changed preflight metadata or existing fit artifacts. Checkpoints, raw
predictions, recipe, preflight, audit hashes, and complete machine-readable
scores remain in the external output directory. A point-target comparison
selects only the parameterization for a future stochastic HP decoder; it does
not qualify a final distribution or runtime model.

Knowledge impact: frozen experiment protocol and evidence here and in the
experiment ledger; active status in current-research. No production default.

Scientific fit pending implementation review; no outcome claimed.
