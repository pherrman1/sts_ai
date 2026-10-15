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
support. Independent implementation and accepted-design review passed on clean
execution SHA `521e364a08735ad095ed99682e3d5058a6748a46`. The three fixed fits
completed ten epochs each; the guarded fit command exited 0. Checkpoints,
raw probabilities,
samples, preflight, recipe, results and hashes stay in the external output
directory above. Survival, max-HP modeling, potion weights, relic support and
RNG contracts are unchanged. No runtime C++ integration, relic training or
`combatRng[6]` solution. Knowledge impact: maintained research protocol, empirical experiment
evidence and current research status.


```sh
tools/seed_guard.sh python3 -m tools.combat_transition_stochastic_hp fit \
  --prepared-dir /tmp/sts-phase2-attention-audit-20260913 \
  --control-dir /home/philippherrmann/sts_sweep/runs/hp-targets-20260914 \
  --output-dir /home/philippherrmann/sts_sweep/runs/stochastic-hp-20260914 \
  --baseline-sha 443ed45f9bae4c5864dd7188645a04049b268928 \
  --reviewed-sha 521e364a08735ad095ed99682e3d5058a6748a46
```

## Decision and primary scores

Final classification: **`STOCHASTIC_DELTA_HP_QUALIFIED`**.
Both aggregate differences are categorical minus matching signed-delta point
control, averaged rowwise across seeds before source bootstrap.

| Metric | Paired estimate (HP) | 95% source-bootstrap CI |
| --- | ---: | --- |
| Discrete CRPS | -1.686834343709 | [-1.715728961915, -1.658630531456] |
| Expected-HP MAE | 0.011839527787 | [-0.007041513460, 0.029256256343] |

2,012 HOLDOUT source groups; 1,000 repetitions, seed 20260914.
Mode exact accuracy below is a fraction; MAE/RMSE/CRPS are in HP units.

| Seed | NLL | CRPS | Expected-HP MAE | Expected-HP RMSE | Mode MAE | Mode exact accuracy | Point CRPS | Point raw MAE | Paired CRPS Δ | Paired mean-MAE Δ |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 20260912 | 2.504864931 | 3.673978516 | 5.400272679 | 8.298837686 | 6.441706601 | 0.365249652 | 5.414592673 | 5.470876119 | -1.740614156 | -0.070603440 |
| 20260913 | 2.497160196 | 3.643171465 | 5.397913096 | 8.236257430 | 6.398237749 | 0.364662235 | 5.328458804 | 5.355005343 | -1.685287339 | 0.042907753 |
| 20260914 | 2.503982544 | 3.679759261 | 5.501783652 | 8.319700159 | 6.306600711 | 0.364600402 | 5.314360798 | 5.438569382 | -1.634601536 | 0.063214270 |

## Interval calibration

Coverage is a fraction of the 32,345 HOLDOUT rows. Discrete equal-tailed
intervals can exceed nominal coverage because atoms cannot be split.

| Seed | Nominal coverage | Observed coverage | Mean width (HP) |
| --- | ---: | ---: | ---: |
| 20260912 | 50% | 0.658741691 | 8.453207606 |
| 20260912 | 80% | 0.869377029 | 16.050208688 |
| 20260912 | 95% | 0.972731489 | 24.638769516 |
| 20260913 | 50% | 0.666161694 | 8.867089195 |
| 20260913 | 80% | 0.879795950 | 16.798206833 |
| 20260913 | 95% | 0.978049158 | 25.687401453 |
| 20260914 | 50% | 0.661555109 | 9.054258773 |
| 20260914 | 80% | 0.880228783 | 17.131055805 |
| 20260914 | 95% | 0.978203741 | 26.137455557 |

## Descriptive slices

These do not change the decision. Pre-HP fraction quarters are left-closed,
right-open, with 100% included in the final quarter. Native room IDs:
2 event, 3 elite, 4 normal, 6 boss. No potion-certification restriction is applied.

| Seed | Slice | Rows | NLL | CRPS | Expected-HP MAE |
| --- | --- | ---: | ---: | ---: | ---: |
| 20260912 | act:1 | 15735 | 2.086410284 | 2.558779834 | 3.771426125 |
| 20260912 | act:2 | 10550 | 2.982521772 | 4.628838578 | 6.732930912 |
| 20260912 | act:3 | 6060 | 2.759834528 | 4.907291656 | 7.309572378 |
| 20260912 | gains HP | 6662 | 2.287390471 | 3.096807857 | 5.292844011 |
| 20260912 | loses HP | 16238 | 3.697865009 | 5.522942488 | 7.301769268 |
| 20260912 | max-HP delta nonzero | 1084 | 2.771952868 | 3.955699152 | 5.683843978 |
| 20260912 | preFraction:0-0.25 | 288 | 3.034270287 | 3.497708315 | 4.874491634 |
| 20260912 | preFraction:0.25-0.5 | 1826 | 3.217217922 | 4.370654887 | 6.309754566 |
| 20260912 | preFraction:0.5-0.75 | 5560 | 3.341358423 | 5.049624716 | 7.226165860 |
| 20260912 | preFraction:0.75-1 | 24671 | 2.257443905 | 3.314448781 | 4.927602132 |
| 20260912 | event | 528 | 3.102271795 | 4.973965712 | 7.329634150 |
| 20260912 | elite | 7758 | 3.439431667 | 5.828063959 | 8.407914887 |
| 20260912 | normal | 21182 | 1.973996520 | 2.329082373 | 3.501511377 |
| 20260912 | boss | 2877 | 3.783648014 | 7.528619463 | 10.915591001 |
| 20260912 | unchanged HP | 9445 | 0.607234895 | 0.902314563 | 2.206962799 |
| 20260912 | max-HP delta zero | 31261 | 2.495603800 | 3.664209630 | 5.390439619 |
| 20260913 | act:1 | 15735 | 2.078628778 | 2.543379347 | 3.768096328 |
| 20260913 | act:2 | 10550 | 2.973119736 | 4.567401321 | 6.687505545 |
| 20260913 | act:3 | 6060 | 2.755281925 | 4.889805786 | 7.384706248 |
| 20260913 | gains HP | 6662 | 2.297590256 | 3.254348822 | 5.656567582 |
| 20260913 | loses HP | 16238 | 3.695907354 | 5.416887058 | 7.158814821 |
| 20260913 | max-HP delta nonzero | 1084 | 2.764935970 | 3.941413954 | 5.733433929 |
| 20260913 | preFraction:0-0.25 | 288 | 3.004497528 | 3.345930773 | 4.712457933 |
| 20260913 | preFraction:0.25-0.5 | 1826 | 3.207341671 | 4.326593910 | 6.278804782 |
| 20260913 | preFraction:0.5-0.75 | 5560 | 3.333673239 | 5.012822715 | 7.227246012 |
| 20260913 | preFraction:0.75-1 | 24671 | 2.250153065 | 3.287385927 | 4.928447401 |
| 20260913 | event | 528 | 3.123957396 | 5.035247482 | 7.521794736 |
| 20260913 | elite | 7758 | 3.425841570 | 5.749173306 | 8.369032022 |
| 20260913 | normal | 21182 | 1.967551470 | 2.314108804 | 3.514334287 |
| 20260913 | boss | 2877 | 3.777143478 | 7.493997629 | 10.864237805 |
| 20260913 | unchanged HP | 9445 | 0.577020764 | 0.868025106 | 2.188100667 |
| 20260913 | max-HP delta zero | 31261 | 2.487874746 | 3.632829670 | 5.386278644 |
| 20260914 | act:1 | 15735 | 2.085862637 | 2.575193165 | 3.811858741 |
| 20260914 | act:2 | 10550 | 2.980541468 | 4.607171790 | 6.832283600 |
| 20260914 | act:3 | 6060 | 2.759992123 | 4.933248593 | 7.573432829 |
| 20260914 | gains HP | 6662 | 2.344972610 | 3.474094637 | 5.969717548 |
| 20260914 | loses HP | 16238 | 3.676725626 | 5.320577293 | 7.110860360 |
| 20260914 | max-HP delta nonzero | 1084 | 2.784077168 | 4.016943489 | 5.898902200 |
| 20260914 | preFraction:0-0.25 | 288 | 3.004763603 | 3.448587808 | 4.814817970 |
| 20260914 | preFraction:0.25-0.5 | 1826 | 3.213647366 | 4.359108831 | 6.331699059 |
| 20260914 | preFraction:0.5-0.75 | 5560 | 3.340562105 | 5.052188201 | 7.318991025 |
| 20260914 | preFraction:0.75-1 | 24671 | 2.257074833 | 3.322877909 | 5.038841233 |
| 20260914 | event | 528 | 3.135105133 | 5.153490949 | 7.603079584 |
| 20260914 | elite | 7758 | 3.429481983 | 5.755127363 | 8.402605099 |
| 20260914 | normal | 21182 | 1.972410202 | 2.335386871 | 3.606895074 |
| 20260914 | boss | 2877 | 3.806207418 | 7.710923638 | 11.245083205 |
| 20260914 | unchanged HP | 9445 | 0.599940240 | 1.003902673 | 2.405376748 |
| 20260914 | max-HP delta zero | 31261 | 2.494270086 | 3.668067131 | 5.488013251 |

### Healing inspection

All 6,662 healing rows are included. These paired descriptive comparisons
use the same verified #170 raw predictions; they are not decision gates.

| Seed | Categorical CRPS | Point CRPS | Expected-HP MAE | Point raw MAE |
| --- | ---: | ---: | ---: | ---: |
| 20260912 | 3.096807857 | 5.973281297 | 5.292844011 | 5.986120846 |
| 20260913 | 3.254348822 | 5.020414290 | 5.656567582 | 5.026201854 |
| 20260914 | 3.474094637 | 6.096967878 | 5.969717548 | 6.130325927 |

CRPS improves on healing rows for all seeds. Healing expected-HP MAE improves
for seeds 20260912 and 20260914, and worsens for 20260913; no uniform healing
mean-accuracy win is claimed. Equal-tail intervals over-cover nominal levels
on the overall HOLDOUT. No temperature tuning or calibration threshold was
added after evaluation.

## Sampling validity

| Seed | Draws | HP < 1 | HP > postMaxHp | Unsupported class probability | Derived fraction consistent |
| --- | ---: | ---: | ---: | ---: | --- |
| 20260912 | 517520 | 0 | 0 | 0.0 | True |
| 20260913 | 517520 | 0 | 0 | 0.0 | True |
| 20260914 | 517520 | 0 | 0 | 0.0 | True |

## External artifacts

Raw complete results include all secondary slice metrics and training audit
hashes. Every epoch is recorded in `fit.log`. No raw probabilities or
checkpoints are tracked in Git.

| Artifact | SHA256 |
| --- | --- |
| 20260912.pt | `a667a3cfa7d7eca3cb07b46f50321e443c75e8a58f7627becb1fd69bf90f08c9` |
| 20260913.pt | `12c8c59229399355e407aae0ac528a65635de2a43b85948b543e7db4200c13b7` |
| 20260914.pt | `5855e92344eb446ea2e18678b9a960ec39cd957418ce120c5759505020c45833` |
| predictions.npz | `313e6087ce9e7599252e56dbd168ab717aa1761d37924a1908d3416e8bb19f66` |
| preflight.json | `a3c3d9c55e3a0cee8cc22b6512d56df664d0dc8b11f73f61f09a933e48d3e877` |
| recipe.json | `c10ad35de3318c5a7b2465f53f34befab148d904844c521cf61b7444488e1d96` |
| results.json | `cf6e2c063c85501735622a7c2f6453120d8d7e4504c411491c1e5e9b74b6cfad` |
| review-and-environment.json | `b6491cfa8c928d4d9bc948368f00c1686802ef46c00c9848170f232a96192b30` |

Post-run raw-artifact verification recomputed CRPS using the independent
energy-distance formula, reproduced both source-bootstrap estimates/CIs
within 1e-5 HP (FP32 probability normalization tolerance), and reproduced
NLL/expected-MAE scores. All originally emitted artifact hashes verified.
`verification.json` records this check; raw fit log is also hashed below.

| Additional artifact | SHA256 |
| --- | --- |
| verification.json | `fb1c12198b51df14b1b20a9ca4091cd491caf466d0f58195edd59eb7598b2c18` |
| fit.log | `22bf67d09e0345c6c05ef6ea37d962f5dfe3d3b754afd01c0e7bbae951e9e662` |

## Scope and limits

This is offline engineering qualification on reused source HOLDOUT, conditioned
on observed max-HP delta. It does not establish performance with sampled
upstream max HP, downstream potion/relic composition, multi-fight planning,
or gameplay. Survival, max-HP modeling, potion weights, relic and RNG
contracts were unchanged. No simulator collection, gameplay checks, C++
runtime integration or relic fitting ran. GitHub Linux GCC is the authoritative
repository verification; local verification covered the changed Python
protocol and CTest registration.
