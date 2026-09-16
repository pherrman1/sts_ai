# Joint shared maxHP+HP+potion encoder distillation — 24 epochs

**Decision: `SHARED_TRANSITION_POTION_REJECTED`.** This is the exact follow-up
to the 12-epoch run, with only the training horizon changed from 12 to 24
epochs. The PR #197 epoch-37 shared maxHP+HP Attention encoder was jointly
adapted with its maxHP/HP branches and the existing 64-action potion
trajectory decoder. MaxHP and HP preservation remained eligible, but the
potion decoder remained **3.1740%** worse than the dedicated specialist on
the same VALIDATION rows. Recursive Brew was **20.2797%** worse, an obvious
slice regression under the preregistered rule.

## Provenance and protocol

- Actual current `main` / base SHA:
  `c371f3c29ffab07096c71fc66a4ab930e9595952`.
- PR #198 was confirmed merged before the run; its merge commit is the base
  above.
- Reviewed 24-epoch implementation SHA:
  `71d3d4d6343ed3b1e3ebfbb4b4c9eb230976d0f5`.
- The only implementation difference from the 12-epoch treatment was
  `RECIPE["epochs"]: 12 -> 24`.
- PR #197 candidate: epoch 37, SHA256
  `daf50b5ec0847fe7a44cde0efd5d592a1939a25e6978f6757dd2b0157a105267`,
  receipt SHA256
  `4149c038a2abe9ab181b03c714763e74fb7b37f534020179004696fd465577c7`.
- Frozen maxHP teacher:
  `2c5b54d0a9420a9d0e3ab9a26f32b9900c4869490e4af49627009cde21efb4b0`.
- Frozen HP teacher:
  `0c8b5aa8c5218d6cd6102b768cc86a474c9ef30953d4b034caedcc41a426109b`.
- Dedicated potion specialist:
  `ae1a1411990d272579de10564edb48c7f2ec1d14f1c72dacf5390a1415a0f1db`.
- Final-union preparation cache:
  `e1c25f2758bf56c7cff392ea02342d809f3ad7427c70b64166244a6b714a251d`.
- Source provenance SHA:
  `1c31b7eb0a7660d43bc27e0849a8955dd0c3daae`.
- TRAIN: 393,677 rows / 19,986 sources. VALIDATION: 48,590 rows / 2,496
  sources. TEST inference and metrics: zero.

The architecture, tokenization, exact DAG potion NLL, frozen teachers,
optimizer, learning rates, weight decay, batch size, gradient clipping,
precision, seed, calibration cohort, loss normalization, and checkpoint
selection rule were unchanged from the 12-epoch treatment. The recipe used
FP32, seed `20260912`, AdamW, encoder LR `1e-4`, heads/decoder LR `1e-3`,
weight decay `1e-4`, batch 512, clip 1.0, and 24 epochs.

The deterministic TRAIN-only calibration cohort was 8,192 rows with row-ID
SHA256 `122776e919b5fd6445b516ae8e9f70aa5db4f4c3d1eccbb994f0e7de80ffa053`.
The fixed scales were:

| Scale | Value |
| --- | ---: |
| `s_max` | 0.0021965544365230016 |
| `s_hp` | 0.011543620959855616 |
| `s_potion` | 2.281699538230896 |

All scales were finite and above the `1e-4` stop threshold. The 24-epoch
batch-order SHA256 was
`9615a714605fac562b61f93779f7a1204f3a71d5125b329558eb0a2915e45375`.

## Validation history

All 24 checkpoints were eligible under the PR #197 maxHP/HP preservation
gates. Epoch 23 was the strict minimum potion validation trajectory NLL.

| Epoch | Potion NLL | Eligible |
| ---: | ---: | :---: |
| 1 | 0.562808405 | yes |
| 2 | 0.548993383 | yes |
| 3 | 0.543053314 | yes |
| 4 | 0.541314555 | yes |
| 5 | 0.536671021 | yes |
| 6 | 0.533299093 | yes |
| 7 | 0.530924871 | yes |
| 8 | 0.530505710 | yes |
| 9 | 0.528166508 | yes |
| 10 | 0.527528301 | yes |
| 11 | 0.525793575 | yes |
| 12 | 0.524339669 | yes |
| 13 | 0.524431113 | yes |
| 14 | 0.526996084 | yes |
| 15 | 0.523784882 | yes |
| 16 | 0.522342827 | yes |
| 17 | 0.521914561 | yes |
| 18 | 0.523169580 | yes |
| 19 | 0.522222344 | yes |
| 20 | 0.521448018 | yes |
| 21 | 0.521653218 | yes |
| 22 | 0.520258397 | yes |
| 23 | **0.520021881** | yes |
| 24 | 0.521583582 | yes |

## Preservation result

At selected epoch 23, maxHP NLL changed by `-0.5145%`, accuracy dropped
`0.0165` percentage points, and expected post-maxHP MAE increased
`0.000470` HP. HP NLL changed by `+0.1168%`, CRPS by `+0.2460%`, and expected
ending-HP MAE by `+0.010358` HP. Damage, healing, and low-pre-HP slices
remained inside their specified limits. The preservation result was eligible.

## Teacher-forced potion result

| Metric | Dedicated | Joint candidate | Gate result |
| --- | ---: | ---: | --- |
| Exact trajectory NLL | 0.504024366 | 0.520021881 | **+3.1740%, fail** (≤+2%) |
| Normal no-change Brier | 0.091516687 | 0.094522741 | +0.00300605, pass |
| Normal action-mode accuracy | 80.7551% | 80.3965% | -0.3586 pp, pass |
| Normal count accuracy | 81.5015% | 81.0366% | -0.4649 pp, descriptive |
| Illegal probability maximum | 0 | 0 | pass |
| Normalization error maximum | 2.04e-7 | 1.88e-7 | pass |

| Slice | Relative NLL change |
| --- | ---: |
| Brew | **+12.0600%** |
| Smoke | **+15.5893%** |
| Recursive Brew | **+20.2797%** |
| All trajectory-special | **+12.6391%** |

The primary teacher-forced NLL and obvious recursive-Brew slice gates failed.
Per the fixed protocol, the mandatory 32-draw ancestral qualification was not
run. There was no TEST scoring, runtime/export, promotion, native C++ change,
or gameplay run.

## Artifacts and checks

The complete external result is
`/home/philippherrmann/sts_sweep/runs/shared-transition-potion-distill-24-20260916/results.json`
(SHA256
`2a3c6aa4f08e94965fd92b88a70823d99da760057f657493ae312f78c7e2e87d`). The
selected checkpoint is
`/home/philippherrmann/sts_sweep/runs/shared-transition-potion-distill-24-20260916/selected.pt`
(SHA256
`70c1fbaf8fed3bdf68219edfbad78a6690411326bd9c88133c560c4120c7d23b`). The
run completed in 610.30 seconds.

Focused checks passed:

```text
python3 -m unittest tools.test_combat_transition_shared_encoder_potion \
  tools.test_combat_transition_shared_encoder_distill \
  tools.test_combat_transition_shared_potion_encoder \
  tools.test_combat_transition_potion_trajectory -v
20 tests, OK

python3 -m py_compile tools/combat_transition_shared_encoder_potion.py \
  tools/test_combat_transition_shared_encoder_potion.py
git diff --check
real artifact preflight: maxHP HP potion components and teacher arrays passed
fixed GPU run: 24/24 epochs completed; all epochs eligible; final receipt written
```

Remaining uncertainty: this is one offline TRAIN/VALIDATION run. It rejects
the specified jointly adapted architecture, recipe, and 24-epoch selection
rule; it does not establish that potion-relevant information is intrinsically
absent from every possible shared representation.

Knowledge impact: experiment evidence and current research status only;
qualified components and executable defaults remain unchanged.
