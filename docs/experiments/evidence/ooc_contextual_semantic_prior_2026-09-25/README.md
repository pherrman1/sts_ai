# OOC contextual deck semantic-prior qualification

## Decision

**`CONTEXTUAL_SEMANTIC_PRIOR_PASS`.** A newly trained 3,200-parameter
contextual O(n) deck block preserves the deployed42 teacher's final semantic
priors on PR #329's captured, prior-covered non-singleton inputs. The
historical `student_epoch_00_eval.pt` file with SHA-256
`45a3ce627eb220b4784bdcd24ad7f77983f8b1de5f378e8a1b848784ccb69aa6` was not
recovered. The new checkpoint is a separate training result; this does not
claim byte-level or training-run reproduction of that missing artifact.

Offline qualification is complete. This result does not establish native
runtime parity, tree equivalence, gameplay quality, or default promotion.

## Frozen inputs and provenance

| Artifact | SHA-256 | Location |
| --- | --- | --- |
| PR #329 trace, compressed | `192b623ca28887e7da646aca16efaecd041583261265e1af23b83a1eab958370` | `/home/philippherrmann/Documents/Codex/2026-09-25/ooc-contextual-semantic-prior/trace_mainline.jsonl.gz` |
| PR #329 trace, decompressed JSONL | `9f95592e9dfbf9b199dbdd81f1b4cae2e654e52a871c227c888ace47f7fb1cb1` | Same gzip stream, decompressed |
| Tier-B corpus | `c428f229bdf7cfe070ff06fd1664978e6e49bbde872d5929ef4fa50f56ba008b` | `/home/philippherrmann/Documents/Codex/2026-09-25/ooc-contextual-semantic-prior/strategic_tierb.csv` |
| Seed-disjoint split | `0efe5b56e1f87c0642827c14e55790db517b55820d54620edd32420012e8b67b` | `/home/philippherrmann/Documents/Codex/2026-09-25/ooc-contextual-semantic-prior/split.json` |
| Deployed42 native teacher | `e62abd833fc8cb9081a1cec4a1a012832ac3b0e3166da3892841911664f1184c` | `selfplay/models/ooc_strategic_tok_final.native` |
| Reconstructed teacher checkpoint | `5bc14fb437131d4bdc531ea775e22eca1f6834976d4670ec0aabb2fb14b735b8` | `/home/philippherrmann/Documents/Codex/2026-09-25/ooc-contextual-semantic-prior/deployed_teacher_reconstructed.pt` |
| New frozen student checkpoint | `bc22f8b03646da79754c1fcfe04f49f20ed5f51ff9ba5250cf715d390d04a761` | `/home/philippherrmann/Documents/Codex/2026-09-25/ooc-contextual-semantic-prior/retrained-contextual-student/contextual_student_frozen.pt` |

The raw trace and the 1.14 MB frozen student remain outside disposable
`.codex/worktrees`. The student checkpoint is read-only. The trace has 24,959
records from eight existing seeds, `12450008..12450015`; no new seeds or trace
records were collected for this qualification.

The recovered corpus contains 3,057,708 rows / 4,650 seeds. The exact split
contains 3,720 training and 930 validation seeds. The state cache used
`raw-to-grouped-v2`, SHA-256
`91792d7f97d0de1d34ecf64f4daa6a5808532cdea0d23aca407e730430c802aa`.

### Trace population

| Population | Count |
| --- | ---: |
| All trace records | 24,959 |
| Singleton records | 12,308 |
| Source-prior-uncovered records | 6,905 |
| Uniform-prior records | 6,905 |
| Eligible prior-covered, non-singleton, nonuniform occurrences | 11,474 |
| Unique canonical prior inputs (primary population) | 6,317 |
| SHOP occurrences / unique SHOP priors | 1,402 / 1,002 |
| Direct primitive / grouped semantic unique priors | 745 / 5,572 |

The three excluded flags can overlap; only prior-covered, non-singleton,
nonuniform rows enter the fidelity population. Captured temperature was
`1.0` throughout.

Raw trace record counts by screen were Card Reward 11,713, MAP 9,115, SHOP
1,849, Event 600, Rest 868, Boss Relic 327, Treasure 329, and Card Select
158. Counts in the result tables below are unique eligible prior inputs,
rather than raw trace occurrences.

## Teacher parity before student evaluation

The repository exporter recreated the tracked native teacher byte-for-byte.
Across 32 numeric parity cases the maximum logit/Q/value differences were
`1.06e-5 / 1.28e-5 / 8.19e-6`.

On all captured trace inputs, the reconstructed Python teacher had maximum
source and candidate logit error `2.6702881e-5` versus captured native values,
below the required `1e-4`; source argmax matched on 6,317/6,317 unique priors.
Rebuilt final teacher priors differed by at most `1.9898164e-6`. Applying the
captured native candidate logits to the captured prior formula reproduced raw
weights and normalized priors within `1.11e-16` and `5.55e-16`. The student
semantic-prior pass was run only after these checks passed.

## Training recipe and frozen model

| Setting | Value |
| --- | --- |
| Seed / epochs | `0` / `30` |
| Optimizer | AdamW |
| Learning rate / weight decay | `1e-3` / `1e-4` |
| Batch size | 4,096 grouped states |
| Loss | Representation MSE only |
| Policy/Q loss / end-to-end fine-tuning | None / None |
| Trainable parameter count | 3,200 |
| Teacher tensors | 115, all exact matches to deployed42 |
| Additional trainable tensors | Exactly six `contextDeck` tensors |

The trained block applies the frozen V4 `deckTok` encoder, concatenates each
token with the valid-token mean, maps `64 -> 32 -> 32` with GELU, adds the
residual through LayerNorm, and mean-pools valid token outputs. Final held-out
representation cosine mean/median was `0.947530 / 0.956957`; validation MSE was
`0.039962`. A plain mean of frozen deck tokens scored cosine `0.468721`, so the
trained context block materially contributes to matching attention.

Checkpoint SHA-256:

```text
bc22f8b03646da79754c1fcfe04f49f20ed5f51ff9ba5250cf715d390d04a761
```

The file is saved at the absolute path in the provenance table above and has
read-only mode `0444`. It contains 115 exact teacher state tensors plus the six
new contextual tensors. No original checkpoint was overwritten or substituted.

## Historical source-policy gate

The reconstructed student passed on the exact held-out validation cohort:

| Population | Groups | Argmax agreement | Median TV | P90 TV |
| --- | ---: | ---: | ---: | ---: |
| Overall | 100,314 | 97.945% | 0.003128 | 0.034804 |
| Card Reward | 58,180 | 99.187% | 0.000005 | 0.024435 |
| SHOP | 4,938 | 93.864% | 0.008026 | 0.027206 |

The declared gate was overall agreement at least 95%, median TV at most 0.03,
p90 TV at most 0.10, plus Card Reward and SHOP guard thresholds. Every check
passed. Card Reward and SHOP values are shown explicitly because those were
the historical watch screens.

## Semantic-prior gate

Primary metrics use one row per unique canonical prior input after semantic
candidate aggregation and primitive-multiplicity correction. The
call-weighted trace is secondary.

| Metric | Unique priors (6,317) | Call-weighted (11,474) |
| --- | ---: | ---: |
| Top semantic action agreement | 98.892% | 98.771% |
| Ordered top-two candidate agreement | 96.881% | 96.828% |
| Median TV | 0.000109 | 0.003513 |
| P90 TV | 0.018815 | 0.028456 |
| P99 TV | 0.066779 | 0.083023 |
| Median / p90 Jensen-Shannon (nats) | 0.000000556 / 0.0002866 | 0.00001760 / 0.0006359 |
| Top-two logit-margin correlation | 0.999871 | 0.999868 |
| Mean absolute top-two margin error | 0.141278 | 0.118651 |

### By screen (unique prior inputs)

| Screen | Unique | Top-action agreement | Median TV | P90 TV |
| --- | ---: | ---: | ---: | ---: |
| Card Reward | 3,671 | 99.619% | <0.000001 | 0.012410 |
| SHOP | 1,002 | 97.705% | 0.002183 | 0.016985 |
| Event | 406 | 94.581% | 0.011271 | 0.047501 |
| MAP | 745 | 98.926% | 0.005030 | 0.015702 |
| Boss Relic | 326 | 99.693% | 0.001962 | 0.030241 |
| Rest | 90 | 97.778% | 0.012611 | 0.077895 |
| Treasure | 72 | 100.000% | 0.002027 | 0.027885 |
| Card Select | 5 | 100.000% | 0.000004 | 0.016299 |

All five broad screens with at least 100 unique inputs passed the evaluator's
screen guards. Event is below 95% agreement but still has 94.58% agreement and
small TV; no broad screen-specific collapse was detected. Rest, Treasure, and
Card Select are lower-count descriptive strata. SHOP, the explicit watch
screen, passes with high agreement and low TV.

### By semantic structure and candidate count

| Stratum | Unique | Top-action agreement | Median TV | P90 TV |
| --- | ---: | ---: | ---: | ---: |
| Direct primitive | 745 | 98.926% | 0.005030 | 0.015702 |
| Grouped semantic candidate | 5,572 | 98.887% | 0.000004 | 0.019260 |
| 2 candidates | 765 | 98.824% | 0.005583 | 0.025727 |
| 3–4 candidates | 1,019 | 97.645% | 0.003659 | 0.027080 |
| 5–8 candidates | 3,512 | 99.516% | <0.000001 | 0.012685 |
| 9+ candidates | 1,021 | 98.041% | 0.001913 | 0.019622 |

No candidate-count or grouped-semantic stratum shows a broad divergence.
Decoded examples for Card Reward, SHOP, grouped semantics, and MAP are retained
in `semantic_prior_result.json`, including cases with nonzero disagreement.

## Source, code, and result hashes

| Item | SHA-256 |
| --- | --- |
| Trainer script | `d468c27a85e9c8eca2a79f94888874c87832f0f4b85b36aa30778ee41243d0bb` |
| Source-policy evaluator | `92d6a3d5a73c62f0eeffef774e954bc4dbac9e21111e34e497c8a27d69b3d207` |
| Semantic-trace evaluator | `56c253ca36ee7dc73038b3f0ac32dbacb5da0396470aeb86c348a03abef3761e` |
| `retraining_result.json` | `dd7ed7a7e904fb87eefa9491edda5f044ba2648190a4f5ac481a4fa83380a434` |
| `teacher_trace_parity.json` | `3d0467a765f7f75d8e9ec9b3100cd63681f33fa9ba9b13c9cd038361a5f36b01` |
| `source_policy_result.json` | `ae740de944b95a83ba3f8fc40a7cbe2de9134597733bbb06072a57ffe7cd8545` |
| `semantic_prior_result.json` | `6f00ab190a3f31b8bc6e06a0d3e6f37a524dd1fa83772076a14defe802750f5d` |

Raw model, cache, data, and trace files stay at the external paths listed above;
the JSON results committed alongside this README are compact and include
additional per-screen, per-stratum, and representative-record detail.

## Current-main drift audit

The task handoff expected `856b3f8f`; by this run `origin/main` was
`0eed6993999386737d87f040e38fb241623b5cf3`. The trace was produced by the PR
#329 branch head `03079d522f05a83be304d709fbe567cfe2fc4d59`. The later OOC
adapter change on current `main` removes trace-only instrumentation and alters
singleton-bypass bookkeeping. Diff inspection found no change to non-singleton
semantic candidate construction, `priorSourceGroups`, source `policyLogits`,
or multiplicity-corrected legal-action weights. Singletons are excluded from
the primary population, so the checked-in trace remains suitable for this
offline comparison. This audit does not claim current-main trace capture was
rerun.

## Exact commands

Commands were run on the task branch from
`/home/philippherrmann/.codex/worktrees/c99d/sts_lightspeed`, with the durable
input and output paths under
`/home/philippherrmann/Documents/Codex/2026-09-25/ooc-contextual-semantic-prior/`.
Each command below completed with exit code 0.

```bash
python3 tools/retrain_ooc_contextual_student.py \
  --csv /home/philippherrmann/Documents/Codex/2026-09-25/ooc-contextual-semantic-prior/strategic_tierb.csv \
  --split /home/philippherrmann/Documents/Codex/2026-09-25/ooc-contextual-semantic-prior/split.json \
  --native selfplay/models/ooc_strategic_tok_final.native \
  --teacher /home/philippherrmann/Documents/Codex/2026-09-25/ooc-contextual-semantic-prior/deployed_teacher_reconstructed.pt \
  --trace /home/philippherrmann/Documents/Codex/2026-09-25/ooc-contextual-semantic-prior/trace_mainline.jsonl.gz \
  --out /home/philippherrmann/Documents/Codex/2026-09-25/ooc-contextual-semantic-prior/retrained-contextual-student
```

The trainer first ran the 32-case native/Python check and captured-trace
teacher preflight, then constructed the v2 state/target caches, trained, and
saved the frozen checkpoint. It reported zero newly collected capture or
gameplay seeds.

```bash
python3 tools/evaluate_ooc_contextual_source_policy.py \
  --csv /home/philippherrmann/Documents/Codex/2026-09-25/ooc-contextual-semantic-prior/strategic_tierb.csv \
  --split /home/philippherrmann/Documents/Codex/2026-09-25/ooc-contextual-semantic-prior/split.json \
  --teacher /home/philippherrmann/Documents/Codex/2026-09-25/ooc-contextual-semantic-prior/deployed_teacher_reconstructed.pt \
  --student /home/philippherrmann/Documents/Codex/2026-09-25/ooc-contextual-semantic-prior/retrained-contextual-student/contextual_student_frozen.pt \
  --state-cache /home/philippherrmann/Documents/Codex/2026-09-25/ooc-contextual-semantic-prior/retrained-contextual-student/tierb_state_raw-to-grouped-v2.f16 \
  --state-manifest /home/philippherrmann/Documents/Codex/2026-09-25/ooc-contextual-semantic-prior/retrained-contextual-student/tierb_state_raw-to-grouped-v2.manifest.json \
  --target-cache /home/philippherrmann/Documents/Codex/2026-09-25/ooc-contextual-semantic-prior/retrained-contextual-student/teacher_deck_z.npy \
  --target-manifest /home/philippherrmann/Documents/Codex/2026-09-25/ooc-contextual-semantic-prior/retrained-contextual-student/teacher_targets.manifest.json \
  --out /home/philippherrmann/Documents/Codex/2026-09-25/ooc-contextual-semantic-prior/retrained-contextual-student/source_policy_result.json
```

```bash
python3 tools/evaluate_ooc_contextual_semantic_trace.py \
  --trace /home/philippherrmann/Documents/Codex/2026-09-25/ooc-contextual-semantic-prior/trace_mainline.jsonl.gz \
  --source-result /home/philippherrmann/Documents/Codex/2026-09-25/ooc-contextual-semantic-prior/retrained-contextual-student/source_policy_result.json \
  --teacher /home/philippherrmann/Documents/Codex/2026-09-25/ooc-contextual-semantic-prior/deployed_teacher_reconstructed.pt \
  --student /home/philippherrmann/Documents/Codex/2026-09-25/ooc-contextual-semantic-prior/retrained-contextual-student/contextual_student_frozen.pt \
  --out /home/philippherrmann/Documents/Codex/2026-09-25/ooc-contextual-semantic-prior/retrained-contextual-student/semantic_prior_result.json
```

`python3 -m py_compile` for the three scripts and `git diff --check` passed.
No C++ build, CTest, native contextual inference, new seed run, or gameplay
evaluation was performed for this offline qualification.
