# Shared maxHP+HP encoder as the potion encoder

**Decision: `SHARED_ENCODER_POTION_REJECTED`.** The frozen epoch-37 shared
maxHP+HP encoder was tested as a replacement for the dedicated potion encoder
with a fresh decoder-only fit. The shared representation is 4.6457% worse in
VALIDATION exact trajectory NLL, above the fixed 2% limit. The recursive-Brew
slice is 22.3968% worse, also an obvious slice regression. The no-change Brier
delta (+0.00527133) and action-mode accuracy drop (0.8673 percentage points)
were inside their limits, but the primary NLL and slice gates failed.

## Protocol and provenance

- Frozen experiment code: `877f6f6feb5781c609ceca76374588e7bbb047e7`.
- Baseline: current `origin/main` SHA `af9cbac36cf769674d28249d762fdb8f2ee6d9e6`.
- Candidate: PR #197 epoch 37 checkpoint SHA256
  `daf50b5ec0847fe7a44cde0efd5d592a1939a25e6978f6757dd2b0157a105267`,
  already qualified by `SHARED_TRANSITION_ENCODER_GO`.
- Dedicated potion component SHA256:
  `ae1a1411990d272579de10564edb48c7f2ec1d14f1c72dacf5390a1415a0f1db`.
- MaxHP and HP teacher component SHA256 values:
  `2c5b54d0a9420a9d0e3ab9a26f32b9900c4869490e4af49627009cde21efb4b0` and
  `0c8b5aa8c5218d6cd6102b768cc86a474c9ef30953d4b034caedcc41a426109b`.
- Regenerated preparation cache SHA256:
  `e1c25f2758bf56c7cff392ea02342d809f3ad7427c70b64166244a6b714a251d`.
  Its exact files matched `prepared.npz` `2badbb85…`,
  `prepared_manifest.json` `13b2c91f…`, and `target_spec.json` `e2315620…`.
- Population: TRAIN 393,677 winning rows / 19,986 sources; VALIDATION
  48,590 winning rows / 2,496 sources. TEST inference rows: zero.
- Both encoders were frozen and cached once. The decoder initialization and
  fixed 12-epoch batch order were byte-identical between arms. Recipe:
  FP32, AdamW, batch 512, learning rate 1e-3, weight decay 1e-4, gradient
  clip 1.0, seed 20260912.
- Both arms selected epoch 12. Cached encoding took 4.98 seconds for A and
  4.81 seconds for B; decoder fitting, selection and scoring took 77.00
  seconds total. These timings are descriptive only.

## Teacher-forced VALIDATION results

Both arms selected epoch 12. The complete validation curves were:

| Epoch | Dedicated A | Shared B | B minus A |
| ---: | ---: | ---: | ---: |
| 1 | 0.547908432 | 0.573346112 | +0.025437679 |
| 2 | 0.537373456 | 0.562709399 | +0.025335943 |
| 3 | 0.528723733 | 0.554323639 | +0.025599906 |
| 4 | 0.526914184 | 0.551210152 | +0.024295967 |
| 5 | 0.518582775 | 0.546295819 | +0.027713044 |
| 6 | 0.515517131 | 0.540650853 | +0.025133722 |
| 7 | 0.513288989 | 0.538576193 | +0.025287204 |
| 8 | 0.512925290 | 0.537742147 | +0.024816858 |
| 9 | 0.509348665 | 0.535079229 | +0.025730564 |
| 10 | 0.511312060 | 0.534518831 | +0.023206772 |
| 11 | 0.507510264 | 0.530950705 | +0.023440441 |
| 12 | 0.507205895 | 0.530769047 | +0.023563152 |

The shared curve descends through the final epoch, but the absolute gap does
not close at the endpoint; relative to A it is 4.619% at epoch 11 and 4.646%
at epoch 12. A longer decoder-only continuation would therefore be a cheap,
separate follow-up rather than evidence that this screen passed.

Post-run implementation review corrected the unexecuted ancestral checkpoint
loader to derive its Attention normalization width from the 10 continuous
global features. A focused synthetic-checkpoint test now exercises strict
loading of that helper. This correction does not alter the completed fit or
its decision because the ancestral path was correctly skipped after the
teacher-forced failure.

| Metric | Dedicated potion (A) | Shared maxHP+HP (B) | Gate result |
| --- | ---: | ---: | --- |
| Exact trajectory NLL | 0.507205895 | 0.530769047 | **+4.6457%, fail** (limit +2%) |
| Normal no-change Brier | 0.092079017 | 0.097350347 | +0.00527133, pass (limit +0.01) |
| Normal action-mode accuracy | 80.7301% | 79.8628% | -0.8673 pp, pass (limit -1 pp) |
| Normal count accuracy | 81.5807% | 80.5904% | -0.9902 pp, descriptive |
| Illegal probability maximum | 0 | 0 | pass, exact zero |
| Normalization error maximum | 1.90e-7 | 1.92e-7 | pass (limit 1e-6) |

| Slice | Dedicated NLL | Shared NLL | Relative change |
| --- | ---: | ---: | ---: |
| Brew | 1.817043064 | 1.923820987 | +5.8765% |
| Smoke | 0.295576288 | 0.321553335 | +8.7886% |
| Recursive Brew | 2.392938650 | 2.928879477 | **+22.3968%**, obvious regression |
| All trajectory-special | 0.980723987 | 1.043087325 | +6.3589% |

Because teacher-forced acceptance failed, the bounded 32-draw ancestral
diagnostic was not run. There was no TEST scoring, simulator execution,
runtime integration, export, promotion, or gameplay change. The rejection is
for this frozen representation-substitution and decoder recipe; it does not
authorize joint fine-tuning or establish intrinsic information absence.

## Reproduction and receipt

The preparation command was:

```text
python3 tools/combat_transition_surrogate.py prepare --corpus-manifest /home/philippherrmann/sts_sweep/runs/combat-transition-runtime-25k/combat-transition-25k.jsonl.manifest.json --output-dir /tmp/sts-phase2-attention-audit-20260913 --expected-corpus-sha256 74c08aa0a3c30342d86cd45355fe17ffa9046963ad7c8cf71b1938f9cdc1cfde
```

The complete external result is
`/home/philippherrmann/sts_sweep/runs/shared-potion-encoder-screen-20260916/results.json`
(SHA256 `4709efbf3df750c45bf503f931c5b40c9028dca8c89b547cd9385fdd7a27f54d`).
The compact tracked receipt is
`shared_potion_encoder_screen_2026-09-16.json`.
The tracked implementation and its four focused tests are in
`tools/combat_transition_shared_potion_encoder.py` and
`tools/test_combat_transition_shared_potion_encoder.py`.

Knowledge impact: experiment evidence and current research status only;
qualified encoders and executable defaults remain unchanged.
