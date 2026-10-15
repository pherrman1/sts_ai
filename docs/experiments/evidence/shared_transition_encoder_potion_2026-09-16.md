# Joint shared maxHP+HP+potion encoder distillation

**Decision: `SHARED_TRANSITION_POTION_REJECTED`.** The PR #197 epoch-37
shared maxHP+HP Attention encoder was allowed to adapt jointly with its
maxHP/HP branches and the existing 64-action potion trajectory decoder. The
fixed TRAIN-only normalized loss kept maxHP and HP inside all PR #197
preservation gates, but the potion task remained **3.9830%** worse than the
current dedicated potion specialist on the same VALIDATION rows. Recursive
Brew was **20.5168%** worse, an obvious slice regression under the preregistered
rule.

## Provenance and protocol

- Actual current `main` / base SHA: `c371f3c29ffab07096c71fc66a4ab930e9595952`.
- PR #198 was confirmed merged before this run; its merge commit is the base
  above.
- Reviewed experiment-code SHA:
  `49e2642a69b7c6222648228195a29694c3734896`.
- PR #197 candidate: epoch 37, SHA256
  `daf50b5ec0847fe7a44cde0efd5d592a1939a25e6978f6757dd2b0157a105267`,
  receipt SHA256 `4149c038a2abe9ab181b03c714763e74fb7b37f534020179004696fd465577c7`.
- Frozen teachers: maxHP
  `2c5b54d0a9420a9d0e3ab9a26f32b9900c4869490e4af49627009cde21efb4b0` and HP
  `0c8b5aa8c5218d6cd6102b768cc86a474c9ef30953d4b034caedcc41a426109b`.
- Dedicated potion specialist:
  `ae1a1411990d272579de10564edb48c7f2ec1d14f1c72dacf5390a1415a0f1db`.
- Final-union preparation cache:
  `e1c25f2758bf56c7cff392ea02342d809f3ad7427c70b64166244a6b714a251d`.
- Source provenance SHA: `1c31b7eb0a7660d43bc27e0849a8955dd0c3daae`.
- TRAIN: 393,677 rows / 19,986 sources. VALIDATION: 48,590 rows / 2,496
  sources. TEST inference and metrics: zero.

The 8,192-row deterministic TRAIN calibration cohort has row-ID SHA256
`122776e919b5fd6445b516ae8e9f70aa5db4f4c3d1eccbb994f0e7de80ffa053` and
frozen scales:

| Scale | Value |
| --- | ---: |
| `s_max` | 0.0021965544365230016 |
| `s_hp` | 0.011543620959855616 |
| `s_potion` | 2.281699538230896 |

All three scales were finite and above the `1e-4` stop threshold. The batch
order SHA256 was
`110ff129ce40099ba612986aabe78195cbcc37bcd11597b9e6b3d012f3cf304d`, matching
the fixed seed-20260912 12-epoch order.

Recipe: FP32, AdamW, encoder LR `1e-4`, heads/decoder LR `1e-3`, weight decay
`1e-4`, batch 512, clip 1.0, one seed, 12 epochs. The shared model and maxHP
head came from PR #197; the potion decoder was initialized from the dedicated
component. Teachers were frozen and VALIDATION never entered gradient
updates.

## Validation history

Every epoch was eligible under the PR #197 maxHP/HP gates. Values below show
relative candidate-minus-teacher changes for the preservation metrics and
the candidate's exact potion trajectory NLL.

| Epoch | Potion NLL | Eligible | maxHP NLL | HP NLL | HP CRPS |
| ---: | ---: | :---: | ---: | ---: | ---: |
| 1 | 0.562786052 | yes | +0.701% | +0.148% | +0.268% |
| 2 | 0.548946415 | yes | +0.612% | +0.120% | +0.256% |
| 3 | 0.543072734 | yes | +0.213% | +0.129% | +0.250% |
| 4 | 0.541369420 | yes | +0.392% | +0.138% | +0.271% |
| 5 | 0.536469466 | yes | +0.268% | +0.164% | +0.272% |
| 6 | 0.533312121 | yes | +0.161% | +0.122% | +0.215% |
| 7 | 0.530961373 | yes | +0.342% | +0.141% | +0.237% |
| 8 | 0.530343612 | yes | -0.053% | +0.111% | +0.190% |
| 9 | 0.527917987 | yes | -0.031% | +0.131% | +0.252% |
| 10 | 0.527078966 | yes | -0.075% | +0.129% | +0.233% |
| 11 | 0.525693796 | yes | -0.295% | +0.149% | +0.345% |
| 12 | 0.524099650 | yes | -0.078% | +0.120% | +0.231% |

Epoch 12 was the earliest strict minimum among eligible checkpoints.

## Preservation result

At the selected checkpoint, maxHP NLL changed by `-0.0776%`, accuracy dropped
`0.0185` percentage points, expected post-maxHP MAE increased `0.000554` HP,
and nonzero-delta accuracy improved by `1.2937` percentage points. HP NLL
changed by `+0.1202%`, CRPS by `+0.2306%`, and expected ending-HP MAE by
`+0.012734` HP. Damage, healing, and low-pre-HP slices remained within their
specified limits. The preservation result was therefore eligible.

## Teacher-forced potion result

| Metric | Dedicated | Joint candidate | Gate result |
| --- | ---: | ---: | --- |
| Exact trajectory NLL | 0.504024366 | 0.524099650 | **+3.9830%, fail** (≤+2%) |
| Normal no-change Brier | 0.091516687 | 0.095823318 | +0.00430663, pass |
| Normal action-mode accuracy | 80.7551% | 80.0129% | -0.7422 pp, pass |
| Normal count accuracy | 81.5015% | 80.7093% | -0.7922 pp, descriptive |
| Illegal probability maximum | 0 | 0 | pass |
| Normalization error maximum | 2.04e-7 | 1.94e-7 | pass |

| Slice | Relative NLL change |
| --- | ---: |
| Brew | +8.6531% |
| Smoke | +4.6304% |
| Recursive Brew | **+20.5168%** |
| All trajectory-special | +7.9931% |

The teacher-forced gate failed on primary NLL and recursive Brew. Per the
fixed protocol, the 32-draw ancestral qualification was not run. There was no
TEST scoring, runtime/export, promotion, native C++ change, or gameplay run.

## Artifacts and checks

The complete external result is
`/home/philippherrmann/sts_sweep/runs/shared-transition-potion-distill-20260916/results.json`
(SHA256 `03e31b3d827e1dc327e9316cb62ad86e1093ea34f92d3eeaf6af62ccfe5a5b88`).
The selected checkpoint is external and has SHA256
`e55d16510fa9791f71d8f02b517e60f05653a80494c63c4bfcdc90eaf348c52d`.

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
fixed GPU run: 12/12 epochs completed; all epochs eligible; final receipt written
```

Remaining uncertainty: this is one offline TRAIN/VALIDATION run. The result
rejects the specified jointly adapted shared architecture, recipe, and
12-epoch selection rule; it does not establish that potion-relevant
information is intrinsically absent from every shared representation.

Knowledge impact: experiment evidence and current research status only;
qualified components and executable defaults remain unchanged.
