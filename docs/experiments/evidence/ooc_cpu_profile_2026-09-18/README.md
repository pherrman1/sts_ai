# Current OOC CPU attribution (profiling only)

## Contract and provenance

Fresh Codex-app-managed worktree, clean baseline/current main
`589a7a73c40e5b89e96df1ffec6a00b08c2ea9ba`; not stacked on #220.
Frozen timer implementation **`c886964b9d631a82b4f9ed0926929f466f960c84`**.
No source edits after freezing or between runs. Release O3/LTO build with the
checked-in `linux-gcc-release-ccache` preset. Binary and all model hashes,
exact guarded argv, working directory and STS/OMP environment are in each receipt.
Attention control SHA256 `e9a18951710fdfe9e1a81a2703090a41f039067c670a1d8a0393b5e7e8e0ddfd`;
V4 model SHA256 `e62abd833fc8cb9081a1cec4a1a012832ac3b0e3166da3892841911664f1184c`.

Only historical seeds 12002032 and 12002033, once each, sequentially, through
`tools/seed_guard.sh`. Ironclad A0, project-fair, keys off, Act-3 stop,
exact 10k Silver/reuse cap32768, OOC2048/cPuct1.5/widen2,0.5/depth32,
policy prior/temperature1/visit selection/early stop, native leaf/zero leaf
combats/V4 continuation policy/full strategic gates/margin1, OMP_NUM_THREADS=1.
No fresh seeds, training, model changes, optimization or gameplay comparison.
The supplied Stage-B timing numbers are user-provided prior evidence; current
main's checked-in older paired run has exactly the same non-timing MCTS columns
but different historical thread/timing settings. The current receipts use one thread.

## Stage 0 and verification

`perf --version`: `/bin/bash: perf: command not found` (uid1000,
perf_event_paranoid2). No installation, privilege changes or infrastructure repair.
No sampled symbols or sampled inclusive CPU percentages can be claimed.
The fresh worktree contained no release binary, so the ordinary release target
was built before adding opt-in instrumentation; final build completed successfully.

- Worktree preflight/check: PASS; app-managed, pinned submodules correct.
- Release configure/build, then final one_combat rebuild: PASS; existing
  Silver warnings and LTO type warnings remain, not repaired here.
- `ctest --test-dir build/linux-gcc-release-ccache -R '^(ooc_mcts_adapter|ooc_mcts_live_startup)$' --output-on-failure`: 2/2 PASS (2.01s).
- `STS_OOC_CPU_PROFILE=1 ctest --test-dir build/linux-gcc-release-ccache -R '^ooc_mcts_adapter$' --output-on-failure`: 1/1 PASS (0.14s).
- Both guarded producers: exit0, one complete result/MCTS row each.
- Every non-timing MCTS column exactly matches the existing reference rows,
  including 146876/148170 simulations, 50151/48857 transitions,
 146875/148161 leaves, 206875/237896 projection steps, 50290/49002 metadata
 builds, 23904/26614 priors, 790/1012 preparations and 7581/9184 edge samples.
- Full local build/CTest and independent implementation review: not run;
  this is a bounded profiling experiment, not scientific qualification.

## Timer semantics and limitations

`STS_OOC_CPU_PROFILE=1` enables per-thread counters; unset/other values make
scopes no-ops. JSON is emitted to stderr as `[ooc-cpu-profile]` at the run trace
boundary, independent of the CSV trace switch. Counters reset after each report.
`CLOCK_THREAD_CPUTIME_ID` uses the same CPU domain as existing mctsCpuSec.
`processCpuAtReportSec` is cumulative process CPU at that boundary, not per-run
CPU for multi-seed invocations. Full process CPU here is external GNU time user
+ system including startup/shutdown; exactly one seed per process.

Every table row is exclusive of nested timed scopes. The stored JSON also gives
inclusive values and calls. Direct v_win includes richFeatureVec and native tree
prediction; it is not a pure network-kernel measurement. Projection includes
copying, continuation policy dispatch, action execution and uninstrumented glue,
but excludes timed V4 networks and the final native leaf call. Thus its remainder
is not evidence that copying alone is expensive. The successor remainder includes
all non-combat work for both deterministic and combat-entering successors.
CTM preparation includes predictor-input/support work and composed inference;
combat resolution includes sample, reconstruction, path update and abort handling,
not pure sampling alone. The tested zero-leaf-combat path uses prepared edges.
Non-checkpoint experimental sampling is not separately covered by these timers.
V4 state-network timers run only inside active profiling scopes (in these runs,
MCTS); live fallback V4 belongs to the full-run residual. Real combat includes
external backend dispatch, search, real action execution and battle exit.

Metadata timer calls exceed accumulated metadataBuilds by31/38 because root
fallback probes construct metadata even when their continuation metrics are not
returned by selectOocMctsAction. Timed successor calls include one unsupported
attempt for seed12002032; successful transitionSamples excludes it. Resolution
calls include continuation/root attempts; they need not equal combatEdgeSamples.
MCTS core/residual is existing mctsCpuSec minus all non-overlapping MCTS buckets,
not a direct timer of selection/backprop alone. Clock overhead is distributed
among nested scopes/residual; no artificial overhead subtraction is applied.

Full CPU is +3.55%/+3.16% versus supplied 40.85/60.83s (below the requested 5%
warning threshold). MCTS itself is +7.37%/+5.67% versus17.985/25.472s. These are
cross-run differences, not a causal isolated timer-overhead estimate; host/clock
variation and instrumentation both remain possible. Treat proportions as profiling
evidence, not a production speed benchmark. No second repetition was justified:
the ranking is stable across both seeds.

### Seed 12002032

| Component | Calls | CPU s | % MCTS | % full | us/call |
|---|---:|---:|---:|---:|---:|
| Real Silver combat | 25 | 22.835134 | — | 53.98 | 913405.361 |
| Prior bookkeeping | 23,904 | 0.088405 | 0.46 | 0.21 | 3.698 |
| Prior token/state construction | 23,904 | 0.045069 | 0.23 | 0.11 | 1.885 |
| Prior per-action prediction | 115,343 | 1.832904 | 9.49 | 4.33 | 15.891 |
| V4 state network (prior + continuation) | 50,616 | 4.524121 | 23.43 | 10.70 | 89.381 |
| V4 continuation action-value network | 117,938 | 1.652289 | 8.56 | 3.91 | 14.010 |
| Native leaf/v_win + feature construction | 146,875 | 3.879698 | 20.09 | 9.17 | 26.415 |
| Continuation projection (exclusive) | 146,875 | 2.945576 | 15.25 | 6.96 | 20.055 |
| CTM preparation | 790 | 3.681087 | 19.06 | 8.70 | 4659.604 |
| Combat sampling / resolution | 7,583 | 0.243477 | 1.26 | 0.58 | 32.108 |
| Successor copying/action execution (exclusive) | 50,152 | 0.104565 | 0.54 | 0.25 | 2.085 |
| Metadata/candidate construction | 50,321 | 0.040304 | 0.21 | 0.10 | 0.801 |
| MCTS core/residual | — | 0.272282 | 1.41 | 0.64 | — |
| Other full-run residual | — | 0.155089 | — | 0.37 | — |

MCTS total **19.309777s**; full process **42.30s**. CPU change versus supplied Stage B: **+3.55%**.


### Seed 12002033

| Component | Calls | CPU s | % MCTS | % full | us/call |
|---|---:|---:|---:|---:|---:|
| Real Silver combat | 26 | 35.689436 | — | 56.88 | 1372670.613 |
| Prior bookkeeping | 26,614 | 0.102793 | 0.38 | 0.16 | 3.862 |
| Prior token/state construction | 26,614 | 0.051334 | 0.19 | 0.08 | 1.929 |
| Prior per-action prediction | 136,215 | 2.175672 | 8.08 | 3.47 | 15.972 |
| V4 state network (prior + continuation) | 67,198 | 5.717365 | 21.24 | 9.11 | 85.082 |
| V4 continuation action-value network | 199,952 | 2.873681 | 10.68 | 4.58 | 14.372 |
| Native leaf/v_win + feature construction | 148,161 | 3.954864 | 14.69 | 6.30 | 26.693 |
| Continuation projection (exclusive) | 148,161 | 5.730244 | 21.29 | 9.13 | 38.676 |
| CTM preparation | 1,012 | 5.583076 | 20.74 | 8.90 | 5516.873 |
| Combat sampling / resolution | 9,184 | 0.296360 | 1.10 | 0.47 | 32.269 |
| Successor copying/action execution (exclusive) | 48,857 | 0.106414 | 0.40 | 0.17 | 2.178 |
| Metadata/candidate construction | 49,040 | 0.042565 | 0.16 | 0.07 | 0.868 |
| MCTS core/residual | — | 0.281558 | 1.05 | 0.45 | — |
| Other full-run residual | — | 0.144639 | — | 0.23 | — |

MCTS total **26.915925s**; full process **62.75s**. CPU change versus supplied Stage B: **+3.16%**.

## Inclusive boundaries (do not add to exclusive table)

| Boundary | Calls seed32 / seed33 | CPU s seed32 / seed33 | % full seed32 / seed33 |
|---|---:|---:|---:|
| Real Silver combat | 25 / 26 | 22.835 / 35.689 | 53.98 / 56.88 |
| evaluateLeaf | 146,875 / 148,161 | 10.807 / 15.957 | 25.55 / 25.43 |
| policyLogits | 23,904 / 26,614 | 4.173 / 4.649 | 9.87 / 7.41 |
| Prior token + prepareState | 23,904 / 26,614 | 2.252 / 2.371 | 5.32 / 3.78 |
| CTM preparation | 790 / 1,012 | 3.681 / 5.583 | 8.70 / 8.90 |

## Decision

1. **Largest: real Silver combat, 53.98% / 56.88% of full CPU.** It explains
   99.3% / 99.6% of non-MCTS CPU. Existing Silver telemetry further identifies
   rolloutToEnd as a major contributor: 2,950,559 / 4,306,532 rollout calls,
   12.421 / 18.534 rollout wall seconds out of21.085 /32.837 search wall seconds
   (58.91% /56.44%). This is inclusive **wall** telemetry, not sampled CPU;
   near-identical process wall/CPU makes it useful supporting evidence, not a
   substitute for kernel-level CPU attribution.
2. **Second combined target: V4 policy/prior plus continuation inference.**
   Exclusive V4/prior buckets sum to8.143 /10.921 CPU seconds, 19.25% /17.40%
   of full CPU (42.17% /40.57% of MCTS). State encoding alone is4.524 /5.717s;
   per-action prior/Q heads are3.485 /5.049s. Native v_win is3.880 /3.955s.
3. **Amdahl bound:** eliminating all real-combat CPU gives2.17x /2.32x full-run
   speedup, pooled2.26x. This is an unattainable upper bound for that whole
   component, not a predicted optimization gain. Eliminating only observed
   rollout wall work would suggest roughly1.41–1.42x under a wall≈CPU assumption.
4. **Cheapest plausible next optimization experiment (not performed):**
   target allocation reuse in Silver rollout scratch/action storage, without
   changing action ordering, RNG draws, rollout termination, or simulation budget.
   First confirm an allocation actually occurs in that path; then one bounded
   reserve/reuse change on captured combat replay, checking bit-exact actions,
   RNG/end-state and visit counts before timing. Allocation cost is an **unverified
   hypothesis**, not attributed by this profile. If absent, do not patch speculatively.
   For the second target, investigate sharing/reusing identical V4 state preparations
   only when state/history identity is proven; no model replacement is implied.
5. **Further CTM inference optimization is lower priority.** All preparation is
   only8.70% /8.90% of full CPU, while sampling/resolution is0.58% /0.47%.
   Even making the entire preparation free bounds speedup at1.095x /1.098x;
   inference alone has a lower bound on benefit because preparation includes
   other work. Real-combat and V4 targets offer much more headroom.

Knowledge impact: measured performance evidence in this report/ledger; maintained
OOC architecture documents the opt-in diagnostic contract and current research
routes the next decision. No baseline, gameplay or model qualification changes.
