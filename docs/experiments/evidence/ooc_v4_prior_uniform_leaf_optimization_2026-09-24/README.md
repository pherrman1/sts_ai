# V4 policy-prior cost under uniform-leaf OOC MCTS

Date: 2026-09-24. This is a bounded performance and exact-parity experiment on
`main` baseline `41c0f5af5711c452b6e133e6dc66c7756f50874c`. It did not collect
gameplay-quality evidence or change any runtime default.

## Question and fixed workload

The V4 policy prior remained the research prior while leaf policy was fixed to
uniform. The experiment asked whether (1) singleton candidate sets could skip
V4 inference exactly and (2) the policy head could reuse the unchanged state
prefix across candidates. It did not change Q inference, CTM, leaf value,
PUCT/widening, simulations, RNG, action semantics, or candidate encoding.

All seed-driven runs used `tools/seed_guard.sh`, seed `12002032`, Act 3 stop,
2,048 OOC MCTS simulations, policy prior, uniform leaf policy, native leaf
value, and the same DeepSets CTM artifact. Profile configuration and source
metadata are included with the raw rows. The initial one-run refresh used the
same baseline, seed and model hashes; its output is `raw/initial_baseline.*`.

Model hashes:

- DeepSets CTM `/tmp/ooc-deepset-stack-provenance-review.native`:
  `3f6d174950f1e4a8b042cebc78bd8525c7e112a13e31865670a39df4b0f2f586`.
  This is an unqualified/rejected research artifact reused only to reproduce
the requested profile; it is not a qualified model or a gameplay claim.
- V4 prior `selfplay/models/ooc_strategic_tok_final.native`:
  `e62abd833fc8cb9081a1cec4a1a012832ac3b0e3166da3892841911664f1184c`.

## Refreshed bottleneck profile before changes

The refreshed profile had 119,445 MCTS simulations, 115,398 transitions,
145 live OOC decisions (139 owned, 6 fallback), 111,886 expanded nodes,
115,510 metadata builds,
88,566 prior builds, and 88,566 V4 policy/state evaluations. MCTS thread CPU
was 29.823s. Policy prediction exclusive CPU was 5.428s, V4 state-network CPU
7.023s, CTM preparation 5.226s, successor exclusive CPU 2.749s, native leaf
value 3.878s, and real Silver combat 35.516s. The exact JSON is preserved in
`raw/initial_baseline.stderr`.

The expanded-node action census was `0: 0`, `1: 40,599`, `2: 21,831`,
`3+: 49,456`. At singleton nodes, 23,700 calls reached `policyLogits()` and
V4 inference; the remaining singleton-node count returned cached logits.

## Exact changes

- `legalActions()` now returns the sole legal action with normalized prior
  `1.0` and records the exact singleton prior, before any V4 policy inference.
  No unused raw singleton logit is evaluated.
- The policy-only prefix precomputes bias plus state dimensions 0–127 in the
  original accumulation order. Per-candidate scoring resumes at dimensions
  128–183 in their original order, then uses the existing GELU/output path.
  Prepared state, candidate encoding, and Q inference are unchanged.

## Correctness evidence

The `ooc_mcts_adapter` self-test covers map, card reward, shop, event, rest,
upgrade/selectors, boss relic and treasure candidate sets. Existing source
primitives compare optimized and legacy logits exactly and compare semantic
and normalized priors exactly while retaining candidate order. The fixed-work
MAP search compares selected action, root IDs/priors/visits/Q, simulation and
transition counts, action-cardinality census, state fingerprints, and RNG
continuation. The singleton root-restriction check retains the same action ID
and exact unit prior.

Four guarded runs alternated prefix-only baseline / prefix+singleton treatment
/ treatment / baseline. All four had identical run result fields apart from
reported time: won, floor 51, Act 3, 78/81 HP. Search counts and all non-timing
MCTS fields matched. The `.actions.jsonl` and `.support.jsonl` sidecars were
byte-identical across all four runs (action trace SHA-256
`cede2cedf79c24f91a5b778bedb3e438b2d66dbd6bf36bbaa23c5b854bb05f36`). The
CSV's `priorBuilds`-derived policy inference count fell by exactly 23,700;
all other work counters matched.

## Performance results

The table compares the prefix-only binary (`base`) with the prefix+singleton
binary (`both`). All measurements ran the same one-seed guarded workload in
ABBA order. CPU throttling varied substantially during the run, so wall-time
and whole-run seconds are contextual; the OOC MCTS thread-CPU counter is the
closest direct search measurement.

| Run | MCTS CPU (s) | Policy inference calls | V4 state calls | Whole-run reported sec |
|---|---:|---:|---:|---:|
| base1 | 40.618 | 88,566 | 88,566 | 367.927 |
| both1 | 36.308 | 64,866 | 64,866 | 276.213 |
| both2 | 33.467 | 64,866 | 64,866 | 156.831 |
| base2 | 35.115 | 88,566 | 88,566 | 119.230 |
| mean base → both | 37.867 → 34.888 | 88,566 → 64,866 | 88,566 → 64,866 | 243.579 → 216.522 |

The mean MCTS thread CPU decreased 7.9% and policy/state inference calls fell
26.8%. Mean measured whole-process CPU at the profile report decreased from
90.57s to 87.60s (3.3%); the repeated pairs both moved in that direction, but
the magnitude is modest under the observed CPU throttling. This supports
keeping the cheap exact singleton fast path alongside the separately retained
prefix optimization; it does not establish a 3.3% production speedup.

Earlier alternating baseline/prefix-only measurements (before the singleton
change) are preserved in the task evidence used during implementation. Across
those two repetitions, MCTS CPU averaged 30.174s → 26.972s (10.6%) and complete
wall averaged 65.64s → 61.70s (6.0%); policy candidate scoring plus prefix
preparation averaged 5.482s → 3.272s (40.3%). The run result and search traces
matched. That is the independent evidence for retaining the prefix optimization
under the uniform-leaf workload; the older V4-rollout rejection does not apply.

## Remaining state-preparation breakdown

A post-change guarded profile split `prepareState()` without changing its
computation. Across 64,866 calls, V4 state preparation inclusive CPU was
6.166s: deck encoding 3.154s, relic encoding 0.199s, potion encoding 0.070s,
and global/state fusion 2.488s. The enclosing scope's exclusive CPU was
0.255s because the four timed child scopes account for the remainder. These
components were measured only; none was optimized.

## Verification and limits

- `cmake --build build/linux-gcc-release --target one_combat -j4`: passed.
- `ctest --test-dir build/linux-gcc-release -R '^ooc_mcts_adapter$' --output-on-failure`:
  1/1 passed after the final profiling-counter change.
- `git diff --check`: passed.
- No multi-seed gameplay gate, CI run, or production-default change was made.
  One fixed seed establishes deterministic parity and local performance only.

Binary SHA-256 values: prefix-only comparison executable
`f0b260392b43993116510408ae3b33f80da6d84f9affec57e34ca781fee2b7a7`; combined
candidate before the final timing-only encoder counters
`01b2974b80ce5ef2440288b7fbb8fcdd23ff60cc9c53ee9f4ee934a1b814a5f4`; final
profile/test executable `cb1581bb96a19f493e1d5b6d9af6c7d01f967a2d03bda9c746403f0ebfdddaaf`.
Raw CSV, metadata, traces, captured output and `/usr/bin/time -v` records are
under `raw/`. The repeated-run invocation is `run_abba.sh`.

Knowledge impact: record the exact singleton and policy-prefix implementation
and measurements in the maintained OOC architecture and current-research
pages; no default or qualified-baseline update is warranted.
