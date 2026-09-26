# Contextual V4 native runtime evidence — prototype withdrawn after review

Experiment baseline at capture: `6bae3a67c63d1f724908e2ee87b27d51e32d30a0`
(`origin/main` at that time).
The fresh Codex-app-managed worktree initially started at
`b65615bb78aa982b0fca097d86876009eb34ec6a`; fetched `origin/main` advanced to
`ffd51f3bc43b03aa356c419567d77b1eecc636a` and then through PR #362 to the final
baseline. PR #362 changed Silver handling for deferred Guardian Mode Shift, so
the task branch was fast-forwarded before final verification. The contextual
header, exporter, evaluator, and ledger were unchanged by that update. After
the experiment, PR #366 added a separate §361 reroot-opportunity entry and
advanced `main` to `212aa25485bc6e8f0a5a91eb35edc7485056cb5a`. This contextual
rejection follows it as §362 in the integrated ledger.

> **Final disposition:** The initial implementation and exact-GELU parity/timing
> results below describe prototype commit `71e9ace30a876a3c0ed12254615eb58814d87d14`.
> A subsequent tanh-GELU speed-only run on the same 6,317 states was 5.171%
> slower than the attention arm for complete prior evaluation. The ≥5%
> improvement gate therefore failed. No high-accuracy approximation was tried;
> the C1 runtime, artifact, exporter/evaluator path, and tests were removed from
> the final PR tree. This packet preserves the implementation evidence and the
> negative follow-up result.

## Frozen inputs and historical candidate identities

| Artifact | SHA-256 |
| --- | --- |
| Contextual checkpoint (used for export only) | `bc22f8b03646da79754c1fcfe04f49f20ed5f51ff9ba5250cf715d390d04a761` |
| Deployed attention teacher | `e62abd833fc8cb9081a1cec4a1a012832ac3b0e3166da3892841911664f1184c` |
| Reconstructed teacher checkpoint | `5bc14fb437131d4bdc531ea775e22eca1f6834976d4670ec0aabb2fb14b735b8` |
| Prototype `OOC_STRAT_C1` artifact (not retained in final tree) | `6d308d5fea278ea8aecc90d1f8bf44efe839b11c57d1362020f1e47f6dba68f7` |
| Captured trace gzip | `192b623ca28887e7da646aca16efaecd041583261265e1af23b83a1eab958370` |

At the prototype revision, the fail-closed exporter verified the checkpoint
SHA, deployed native teacher and reconstructed-teacher identities, all 115
shared tensors, exactly six contextual tensors, and 3,200 contextual parameters.
It produced an 811,976-byte artifact for testing; no checkpoint was retrained
or committed. The exported native artifact is not present in the final PR tree.

The checkpoint's actual contextual block uses PyTorch's default exact GELU
(`torch.nn.functional.gelu` with `approximate="none"`). Although the handoff
requested the V4 tanh approximation for this new block, a tanh implementation
failed the frozen Python parity gates (max deck error `1.055e-3`, source-logit
error `1.065e-3`, normalized-prior error `1.171e-4`). The prototype therefore used exact GELU to reproduce the frozen checkpoint;
existing V4 layers retained their original tanh behavior. The failed tanh
parity replay is retained as `native_contextual_trace_pre_exact_gelu.jsonl.gz`
and `semantic_prior_result_pre_exact_gelu.json`. The prototype runtime was
removed after the speed-only follow-up below.

## Phase 1: native/Python parity

The authoritative saved trace contains 6,317 unique eligible canonical priors
and 37,985 source logits. Native C1 output was checked against the frozen
Python student for each layer below. The existing semantic-prior evaluator
continued to report `CONTEXTUAL_SEMANTIC_PRIOR_PASS`.

| Compared output | Max absolute error | Gate |
| --- | ---: | --- |
| Deck representation | `1.1325e-6` | `<1e-4` |
| Source policy logits | `3.0518e-5` | `<1e-4` |
| Grouped candidate logits | `3.0518e-5` | `<1e-4` |
| Multiplicity-corrected normalized prior | `2.8439e-6` | `<1e-4` |
| Top semantic action | 0 / 6,317 mismatches | exact |

The prior replay preserves trace candidate order, `priorSourceGroups`, group
averaging, primitive multiplicity correction, and temperature. The native
probe reads the trace population from stdin; decompression and parsing are
outside the measured regions.

## Phase 2: controlled Release timing

One thread, one warm-up pass per arm, five measured passes per arm with order
alternated A/B then B/A, and `CLOCK_THREAD_CPUTIME_ID`. Each arm made 31,585
measured calls (6,317 states × five passes). Per-call time includes the full
operation named in the row; the full-prior operation prepares state and policy
features, evaluates all source candidates, averages semantic source groups,
then applies multiplicity correction and normalization. Full distributions,
deck-count buckets and exact samples are in `ab_timing.json`.

| Operation | Arm | Total CPU s | Mean µs/call | Median µs | P90 µs | P99 µs |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Deck encoder | Attention | 1.076375 | 34.079 | 34.204 | 57.397 | 74.931 |
| Deck encoder | Contextual | 1.149302 | 36.388 | 36.839 | 58.870 | 75.722 |
| `prepareState` | Attention | 2.222872 | 70.377 | 69.440 | 95.619 | 115.016 |
| `prepareState` | Contextual | 2.301332 | 72.862 | 72.967 | 97.864 | 115.677 |
| Full prior | Attention | 3.787551 | 119.916 | 112.932 | 165.971 | 203.582 |
| Full prior | Contextual | 3.907124 | 123.702 | 116.668 | 170.690 | 210.615 |

| Operation | Contextual / attention | Reduction |
| --- | ---: | ---: |
| Deck encoder | 1.06775 | `-6.78%` |
| `prepareState` | 1.03530 | `-3.53%` |
| Full prior | 1.03157 | `-3.16%` |

The primary full-prior gate did not pass: C1 was 3.16% slower, below the
required 5% improvement. Phase 3's paired 8-seed smoke was not triggered. No
new gameplay seeds were used for parity or the performance comparison.

## Current-main diagnostic checks

- `live_ooc_protocol` verified the advisor's `ooc_value_distribution_v1` root
  distribution and per-candidate bins. `live_ooc_policy_contextual` passed
  through current `LiveOocMctsPolicy` and returned candidate value data.

## Focused verification

- Frozen checkpoint export: 32 parity checks passed; maximum errors were
  `1.48e-5` logit, `2.50e-5` value, and `1.73e-5` Q. The exporter self-test
  passed on a temporary random checkpoint, and an explicitly missing checkpoint
  failed closed without creating an artifact. Raw logs: `frozen_export.log`,
  `exporter_selftest.log`, and `exporter_missing_checkpoint.log`.
- Native/Python full-trace parity and existing semantic evaluator: passed.
- CTest focused Release set: 10/10 passed — attention compatibility, C1 load,
  C1 trailing-byte rejection, C1 profiler attribution, attention and
  contextual live policy, `live_ooc_parity`, `live_ooc_protocol`,
  `ooc_mcts_adapter`, and `run_profile_analysis`.
- Release targets built: `one_combat`, `test_live_ooc_policy`,
  `ooc_contextual_native_probe`, `one_combat_advisor`, and
  `live_ooc_parity_test`. The shared ccache attempt failed because its cache
  directory is read-only; the same Release preset without ccache built all
  targets successfully.
- Python compilation checks passed for the exporter, semantic evaluator, and
  native verification wrapper.
- GitHub Actions CI was not run locally. The checked-in workflow skips draft
  pull requests; Linux GCC is the authoritative repository check before merge.

Raw current-main outputs are `current_main_native_verification.log`,
`focused_ctest.log`, `release_build.log`, `frozen_export.log`,
and `exporter_selftest.log`. The initial-base build log is retained as
`release_build_pre_rebase.log` for provenance.

Review cleanup omitted 28 profile-only and rejected-preflight artifacts
(58,244 text lines, about 2.1 MB); those diagnostics did not inform parity or
speed decisions.

No default, MCTS, stopping, depth, RNG, semantic-candidate, Silver, or
gameplay-quality promotion is made. C1 support and its artifact are not retained
in the final PR tree.


## Review follow-up: tanh GELU speed-only diagnostic

The exact-GELU C1 candidate was slower than attention by 3.16% for full-prior
evaluation. To isolate `std::erf` cost, a temporary build changed only the C1
activation to the existing V4 tanh approximation. This treatment was for speed
only: its known native/Python fidelity failure was not retested or accepted.

| Operation | Attention CPU s | Tanh C1 CPU s | B/A | Reduction |
| --- | ---: | ---: | ---: | ---: |
| Deck encoder | 1.302093 | 1.531404 | 1.176110 | `-17.611%` |
| `prepareState` | 2.677835 | 2.884597 | 1.077212 | `-7.721%` |
| Complete prior | 4.526272 | 4.760331 | 1.051711 | `-5.171%` |

The decision-bearing ≥5% improvement gate failed: tanh C1 was 5.171% slower.
The measured reduction by deck-token bucket was `-3.469%` for 1–8 tokens
(6,925 calls), `-5.746%` for 9–16 (12,240), `-5.348%` for 17–32 (12,395),
and `-7.229%` for 33–64 (25 calls; weak evidence). The raw timing is
`tanh_speed_diagnostic.json`; treatment/build provenance is in
`tanh_speed_diagnostic.patch` and `tanh_speed_diagnostic_compile.log`.

No high-accuracy GELU approximation was implemented or timed because the
speed-only treatment did not clear the first gate. No 8-seed smoke was run.
The final PR tree removes the C1 model format, loader branch, artifact, and
tests; §362 and the exact-GELU prototype evidence remain for the research record.
