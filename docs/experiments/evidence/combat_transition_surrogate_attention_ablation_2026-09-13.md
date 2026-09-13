# Phase-2 attention representation ablation

Date: 2026-09-13. This is the frozen one-variable comparison of the corrected
Phase-1 small attention representation against the merged Phase-2 DeepSets
result. The corpus, source-group split, support predicate, targets, losses,
optimizer, batch size, epoch cap, patience, and training seed were held fixed.

Knowledge impact: durable negative-transfer result; current research and the
experiment ledger are updated in the same change.

## Decision

**Classification: `ATTENTION_CORE_REGRESSION`.** Attention Phase-2 improves
expected winning HP and transition-head signals, but shared multitask training
degrades survival relative to the attention point-control model. The
source-seed bootstrap 95% intervals for both primary error deltas are strictly
positive:

| Core metric | Attention point-control | Attention Phase-2 | Phase-2 minus control | Relative delta | Source-seed bootstrap 95% |
| --- | ---: | ---: | ---: | ---: | ---: |
| Survival Brier | 0.019039775 | 0.019920463 | +0.000880687 | +4.6255% | [+0.000501706, +0.001289956] |
| Survival log loss | 0.063621797 | 0.066628456 | +0.003006653 | +4.7258% | [+0.001811163, +0.004202626] |
| Survival AUC | 0.978065501 | 0.975830813 | −0.002234688 | −0.2285% | [−0.003290071, −0.001156204] |
| Winning expected-HP fraction MAE | 0.071425542 | 0.067770742 | −0.003654793 | −5.1169% | [−0.004062013, −0.003260710] |
| Joint alive-HP fraction MAE | 0.077747025 | 0.074977458 | −0.002769572 | −3.5623% | [−0.003244952, −0.002334161] |

The decision rule uses no absolute `+0.005` Brier allowance. Positive error is
worse; regression is classified when a primary survival or HP error interval
is strictly above zero. The survival intervals meet that condition. The
bootstrap used 1,000 repetitions over 2,512 TEST source groups.

## Frozen inputs and support

- Baseline/head SHA: `6ccad271eefa5d42ea0d2debe4ff6bed486aa3f9`.
- Corpus SHA-256:
  `74c08aa0a3c30342d86cd45355fe17ffa9046963ad7c8cf71b1938f9cdc1cfde`.
- Source-split SHA-256:
  `e9043bcceb9d95027711e6ff33afbfe1cae3cf9528f820c0ff68bddbb419db32`.
- Corpus: 510,030 rows from 24,999 completed source seeds; one quarantined
  source (`4102275`, `process_exit_134`).
- Support: 413,799/510,030 (81.1323%); fallback 96,231.
- Supported split: TRAIN 331,225, VALIDATION 41,120, TEST 41,454.
- Supported deaths: 15,384/18,133 (84.8398%). Act 1/2/3 support rates were
  82.5107% / 79.4053% / 80.7983%; EVENT/ELITE/MONSTER/BOSS rates were
  83.9126% / 84.0875% / 79.5760% / 83.7653%.
- The final predicate is unchanged from PR #162: Ironclad; no Writhing Mass,
  Looter/Two Thieves/Exordium Thugs, Ritual Dagger, Hand of Greed, Jack of All
  Trades, Transmutation, Toolbox, Smoke Bomb, Entropic Brew, Colorless Potion,
  pre-combat `smokeBombUsed`, or nonzero `stolenGold`.
- Repeated audit: PASS. Gold mutations (21,781), `stolenGold` mutations
  (37,894), deck-structure mutations (1,151), card-misc mutations (109), and
  Smoke Bomb mutations (3,001) all had zero supported rows. Copy-through was
  exact; no RNG state was modeled or invented.

## Attention architecture and protocol

Both models use the corrected Phase-1 attention representation: width 64, two
Transformer encoder layers, four heads, feed-forward width 128, typed GLOBAL /
CARD / RELIC / POTION tokens, categorical global embeddings, explicit relic
order and potion slot, and no arbitrary positional embeddings for exchangeable
card tokens. The learned input is exactly `combat_predictor_input_v1`;
`pre.smokeBombUsed` and `pre.stolenGold` remain adapter-only eligibility fields.

The merged Phase-2 losses and weights were reused unchanged with AdamW
(`lr=1e-3`, weight decay `1e-4`), batch 2,048, eight threads, max 12 epochs,
patience 3, training seed `20260912`, and CUDA on an RTX 3060 Ti. Validation
selection ran 12 epochs independently for each model and selected Phase-2
epoch 11 (score `0.165629169`) and point-control epoch 10 (score
`0.172498332`). Each selected count was then refit from scratch on the
372,345-row TRAIN+VALIDATION set before the single fixed TEST evaluation.

The initial frozen fit completed all 24 validation-selection epochs and all 21
final-refit epochs, and wrote both checkpoints. A post-fit evidence serializer
then used the wrong prepared-audit key (`mutationAudit` instead of the merged
audit's `intentionalOmittedMutationCoverage`) and exited before writing JSON.
The key was corrected; the exact saved checkpoints were reloaded and the TEST,
bootstrap, transition, sampling, latency, and evidence stages were rerun. No
training, weights, inputs, or TEST-based selection changed during recovery.

Commands:

```text
python3 tools/combat_transition_surrogate.py prepare \
  --corpus-manifest /home/philippherrmann/sts_sweep/runs/combat-transition-runtime-25k/combat-transition-25k.jsonl.manifest.json \
  --output-dir /tmp/sts-phase2-attention-audit-20260913

python3 tools/combat_transition_attention_ablation.py fit \
  --prepared-dir /tmp/sts-phase2-attention-audit-20260913 \
  --output-dir /tmp/sts-phase2-attention-fit-20260913 \
  --device cuda --threads 8 --nn-batch 2048 --nn-epochs 12 --nn-patience 3 \
  --training-seed 20260912 --bootstrap-seed 20260913 --bootstrap-reps 1000 \
  --sampling-seed 20260914 \
  --baseline-head-sha 6ccad271eefa5d42ea0d2debe4ff6bed486aa3f9
```

External artifact hashes:

| Artifact | SHA-256 |
| --- | --- |
| `prepared.npz` | `2badbb85ccd8329bcb886d50ef8a0b9b1bd2c043fda9445de9f9c2e7a4b6f9a5` |
| `prepared_manifest.json` | `13b2c91fd0ced713f8c429bbf8995ceb58b6e3e57d1555de42f5e67d7f9a389f` |
| `support_audit.json` | `ad532082ea6773609679c4f6cc4753a5c3a3b75ef93afd436f976d8be9b6e2d6` |
| `target_spec.json` | `e2315620d512578542d6b3bfbd362eb07b086f0e9fa7770cc23f4fa4c226e229` |
| `phase2_attention.pt` | `66ac8f70da69e29bf9b1364243f6f903e4f74dda1ec8a909ef54a7ea97dc6479` |
| `point_control_attention.pt` | `2447b2daf1a48a619a5f071488908afd6f0fb83bfd855ee9f379c04120efeaef` |
| `attention_ablation_evidence.json` | `6866b9847b29f76b0deb33f07e6ca127faa0867e6c6a46a3965ca0f0acc8bcdf` |

## Transition and distribution results

| Metric | Attention Phase-2 | Attention point-control / copy-through |
| --- | ---: | ---: |
| Winning expected HP fraction MAE | 0.067770742 | 0.071425542 |
| Joint alive HP fraction MAE | 0.074977458 | 0.077747025 |
| Winning expected HP MAE | 5.403836 | 5.723867 |
| Joint alive HP MAE | 5.903266 | 6.161391 |
| HP/maxHP mode exact pair | 0.329066 | 0.287357 copy-through |
| HP mode accuracy | 0.329868 | 0.288509 copy-through |
| maxHP mode accuracy | 0.974574 | 0.960821 copy-through |
| All modeled persistent fields exact | 0.183998 | 0.210151 copy-through |

The HP distribution has categorical NLL `2.666314` and discrete CRPS
`0.045763`, improving over the attention point-control degenerate prediction
CRPS `0.070421` by `0.024658`. Its interval coverage/width is 50%
`0.664947 / 10.89` bins, 80% `0.879055 / 21.01`, and 95%
`0.974223 / 32.59`. The point-control degenerate intervals have zero width and
coverage `0.122448` at all three levels.

Potion results are per active slot 0–4 log loss / accuracy:
`0.734541/0.642701`, `0.635845/0.711992`, `0.482141/0.816503`,
`0.375119/0.886849`, and `0.203749/0.949045`; unavailable-slot accuracy was
1.0. Full-vector exact accuracy was `0.491094` versus copy-through `0.728150`;
the 10,852 changed rows had exact accuracy `0.394674` versus copy-through 0;
potion-count accuracy was `0.741902` versus copy-through `0.728150`.

Relic-counter results were per-token log loss `0.452449`, per-token accuracy
`0.825196` over 60,239 mutable tokens, full-vector exact accuracy `0.777174`
versus copy-through `0.764348`, and changed-counter accuracy `0.118426`
over 11,180 changed tokens versus 0 for copy-through. Changed-counter MAE was
`2.140429` versus copy-through `3.199106`.

The sampled-state gate produced 16 valid sampled winning transitions in 16
attempts, with zero invalid HP/potion/relic/copy-through states and no RNG
field. Batch-1 latency on the fit device was `0.9337 ms` for Phase-2 and
`0.7731 ms` for point-control. The checkpoints contain 139,140 and 114,178
parameters and occupy 576,866 and 472,249 bytes respectively.

## Frozen DeepSets comparison

These are historical PR #162 numbers, not retrains:

| Metric | DeepSets Phase-2 | Attention Phase-2 |
| --- | ---: | ---: |
| Survival Brier | 0.020880 | 0.019920 |
| Survival log loss | 0.070470 | 0.066628 |
| Winning expected-HP MAE | 0.071845 | 0.067771 |
| Joint alive-HP MAE | 0.079171 | 0.074977 |
| HP discrete CRPS | 0.048484 | 0.045763 |
| Potion vector exact | 0.460983 | 0.491094 |
| Relic vector exact | 0.773967 | 0.777174 |
| Batch-1 latency | 0.3916 ms | 0.9337 ms |
| Parameters | 119,536 | 139,140 |
| Checkpoint bytes | 493,271 | 576,866 |

The attention absolute metrics are not evidence of a representation win:
attention has its own point-control baseline, and its Phase-2 survival
regression remains statistically supported. The result supports H2: the
shared outcome/transition multitask objective is the likely bottleneck, not
DeepSets specifically. The next experiment should freeze or separate the core
predictor; do not increase Transformer size/depth.

This remains offline research evidence only. There is no runtime C++
integration, Silver replacement, gameplay benchmark, or valid multi-fight
rollout. `combatRng[6]` remains an unchanged continuation blocker.
