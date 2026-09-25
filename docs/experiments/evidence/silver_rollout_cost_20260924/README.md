# Silver rollout cost screen — 2026-09-24

**Status:** the original fixed-work quality screen is invalid because it
shared RNG between the control and its teacher. Its raw data are preserved but
withdrawn from quality interpretation. The corrected independent-teacher and
uninstrumented CPU follow-up is complete and recorded in
[`review_followup/README.md`](review_followup/README.md), under the frozen
[`review_followup/PROTOCOL.md`](review_followup/PROTOCOL.md). Its first-action
DEV results are directionally positive; B remains default-off and is not
qualified by this screen.

## Baseline and provenance

The handoff named baseline `7b4244ef8af4508466e01a1a6b515c70015e6274`.
Current `main` had advanced, so this work used
`1ed96f2aa564742156cc6593a1fc1915ea4e9033` as the baseline. The task branch is
`codex/silver-rollout-cost-20260924`. Origin was
`git@github.com:pherrman1/sts_ai.git`; pinned dependencies passed the worktree
check at json `2222d386c905e6a6ebf73c61571a8a2cf196e843` and pybind11
`63d627c5747befad7720a43ebbe5614fd5d83247`.

All decision screens used the frozen `hard64-dev` first-decision snapshots at
[`hard64-dev-snapshots.jsonl`](../silver_hard_combat_v1_20260918/hard64-dev-snapshots.jsonl),
SHA-256 `ab7c3298754864986c31273a0f1d23967b165fdd79a386261b680b8ad16d0eae`.
The 64-row input consistently produced 59 valid decision rows and five
`transactional_selection_required` API failures. The same five roots failed in
every arm and budget; all performance and action-agreement summaries use the
59 valid roots. No `hard64-holdout` file was read or run.

The performance binaries used GCC 13.3 Release (`-O3 -flto`). The replay
harness enabled the existing rollout diagnostics and emitted identical fields
for control and candidate. All seed-driving replay commands went through
`tools/seed_guard.sh`, used CPU 2, and set `OMP_NUM_THREADS=1`. The telemetry
collection is instrumentation overhead, so these ratios compare the matched
instrumented binaries and do not claim an uninstrumented production speedup.
The control binary SHA-256 is
`520f5ebbea6570b857c953074c37a8c23bbdb6acd78971a6bee1480bf3821118`; the B
candidate binary SHA-256 is
`b6b588dfd8f7b77e01bef6c518bc31c0ad45f20694ef8a1bb4b49f155f9fa431`.

The fixed-work invocation was
`taskset -c 2 env OMP_NUM_THREADS=1 bash tools/seed_guard.sh BINARY docs/experiments/evidence/silver_hard_combat_v1_20260918/hard64-dev-snapshots.jsonl 1000 --first-decision-only`.
`BINARY` was the saved current-main control, early-energy treatment, or
unsorted-pile treatment for the corresponding arm. The deeper reference used
the same guarded command at budget `10000` and the control binary. Every
command returned process exit 1 because the same five rows report
`transactional_selection_required`; valid rows and summaries are retained in
[`raw/`](raw/). Per-run outer timings are in [`timings.tsv`](timings.tsv).

## A — early energy rejection

A moved the energy-affordability rejection earlier in `CardInstance::canUse`.
Across four matched 1,000-simulation repetitions, every non-timing output
field, status, and selected-action fingerprint matched control. It did not
help throughput: summed search wall averaged 1,286,513 µs for control and
1,401,721 µs for A; summed rollout wall averaged 1,048,707 µs and 1,150,141
µs. The two complete outer CPU samples averaged 1.015 s for control and 1.035
s for A (A was 2.0% slower). Timing was noisy, but no repeatable speed gain
appeared. A was reverted. Its temporary treatment binary SHA-256 was
`a2f1cde38d214759d716b1f408548ed8a393ba58b8ea265fab59256cfb1426b1`.

## B — rollout-only unordered unknown piles

B sets an unsorted-unknown-region flag only on the copied draw, discard, and
exhaust piles as `rolloutToEnd` begins. Normal pile insertion, hashing, and
retained tree states stay canonical. Unknown draws remain uniform by index;
known top and bottom positions remain ordered. Diagnostic rollouts now use
scratch state, and the bridge canonicalizes a terminal scratch copy before
serialization. Debug assertions guard `getOrCreateNode` against fast-mode
piles. The focused test covers duplicate draw frequencies, known stacks,
shuffle-in, reshuffle, absorb, cost mutation, and tree isolation.

Four repetitions per arm used 59 valid roots × 1,000 simulations. Order was
control/B/B/control followed by B/control/control/B. Each arm completed
58,965 rollouts and 59,000 simulations per repetition. Means below are across
the four repetitions; medians are medians of the four run aggregates.

| Metric | Current-main control | B | Change |
| --- | ---: | ---: | ---: |
| Summed search wall, mean | 1,274,480 µs | 1,143,222 µs | −10.3% |
| Summed search wall, median | 1,128,885 µs | 1,064,157 µs | −5.7% |
| Summed rollout wall, mean | 1,035,434 µs | 900,665 µs | −13.0% |
| Summed rollout wall, median | 918,010 µs | 844,973 µs | −8.0% |
| Mean of per-run median search time per root | 20,915 µs | 17,521 µs | −16.2% |
| Mean of per-run median rollout time per root | 16,621 µs | 14,095 µs | −15.2% |
| Rollout wall per call | 17.56 µs | 15.28 µs | −13.0% |
| Process user CPU, mean | 1.0275 s | 0.9150 s | −10.9% |
| Simulations per process user-CPU second | 57,421 | 64,481 | +12.3% |

The four process-CPU samples were 0.99–1.07 s for control and 0.90–0.93 s
for B. Search-wall timing had outliers in both arms; the median aggregate
reduction was smaller than the mean. B also executed slightly more rollout
work because RNG-to-card mapping changed: 1,976,784 actions and 355,583 turns
versus control's 1,971,990 actions and 354,687 turns (about +0.24% and +0.25%).

The existing chance telemetry reported fresh executions / sibling reuses by
category (`END_TURN`, card play, other):

| Arm | Fresh executions | Existing-sibling reuses | Reuse fraction |
| --- | --- | --- | ---: |
| Control | 13,094 / 30,334 / 3,336 (46,764 total) | 59 / 15,242 / 209 (15,510 total) | 33.17% |
| B | 13,297 / 30,324 / 4,056 (47,677 total) | 41 / 15,531 / 137 (15,709 total) | 32.95% |

The category-1/card-play sibling reuse was about 50% in both arms. These
counters show duplicate executions, not whether the node's complete support
had already been observed.

## Fixed-work quality screen

**Review correction (2026-09-25):** the original comparison below is
`QUALITY_SCREEN_INVALID_SHARED_REFERENCE_RNG`. Control at 1k and the control
10k reference used the same `benchmark_seed`, so the former was a literal
prefix of its teacher. B used a different RNG-to-card mapping. The preserved
`40/59` and `35/59` counts are not evidence of harm or of no harm and must not
drive a promotion decision. See the independent-seed protocol in
[`review_followup/PROTOCOL.md`](review_followup/PROTOCOL.md).

The invalid original shared-RNG comparison generated a 10,000-simulation
reference on the same roots with the control binary: 590,000 valid simulations
total, with the same five technical failures. Its selected-action fingerprints
were:

| 1,000-simulation arm | Agreement with current-main 10k | Rate |
| --- | ---: | ---: |
| Current-main control | 40 / 59 | 67.8% |
| B | 35 / 59 | 59.3% |

The previously reported paired difference was −8.5 percentage points, with
eight control-only versus three B-only agreements. Because of the shared-RNG
coupling, this statistic is now withdrawn; neither a no-harm failure nor a
quality regression is established. The corrected follow-up used three
independent teachers and four matched search identities per root and arm. Its
fixed-work B-minus-control mean was `+4.3 pp` (root-cluster 95% interval
`[-1.4,+10.1] pp`); the conditional 1,100-versus-1,000 equal-time-equivalent
first-action screen was `+7.2 pp` (95% interval `[+1.0,+13.5] pp`). A separate
uninstrumented 1k CPU check measured mean user CPU `0.740/0.675 s` (control/B,
`-8.8%`). These are DEV first-action and local CPU results, not a complete-
combat or gameplay conclusion; B was not tuned on these roots. Details and raw
files are in the [corrected follow-up packet](review_followup/README.md). A
final evidence audit found the helper's seed-domain spelling differed from the
literal in the protocol frozen with the implementation; all seeds remained
deterministic and pairwise distinct, but exact protocol fidelity is unresolved.

## C and D — stop decisions

C was not implemented. A separate `-pg -O2 -fno-inline` diagnostic build of
the B branch, run on the same guarded fixed-work cohort, recorded 1,543,022
`getIncomingDamage` calls and estimated 0.07 s inclusive time out of 2.51 s
(2.6%) in gprof. This is an instrumented profile estimate, not Release timing.
The function's exact inputs span monster move/misc/strength/weak/death state,
pending moves, ascension/turn, and player damage modifiers. That small profile
share does not justify a fragile cache.

D remained diagnostic-only. The existing per-category counters show 15,709
below-cap sibling re-executions in B, but no exact support-exhaustion detector
was added. The number an exact detector could safely avoid is therefore not
identified: the certified count is zero and the observed duplicate count is
only an upper bound. Most repeats came from card-play stochastic actions;
exact support would require action-specific enumeration or additional random
source plumbing. The task's stop rule applies, and the chance algorithm was
not changed.

## Correctness, review, and remaining checks

- Release build: `cmake --build build/linux-gcc-release --target silver-search-optimization-test silver-hard-combat-replay -j2` completed.
- Release focused test: `ctest --test-dir build/linux-gcc-release -R '^silver_search_optimization$' --output-on-failure` passed, 1/1.
- Debug build: `cmake --preset linux-gcc-debug`, then `cmake --build build/linux-gcc-debug --target silver-search-optimization-test silver-hard-combat-replay -j2` completed.
- Debug focused test: `ctest --test-dir build/linux-gcc-debug -R '^silver_search_optimization$' --output-on-failure` passed, 1/1; this exercises the tree-isolation assertions.
- An independent read-only implementation review found no blocking semantic defect. It flagged stale sorting comments; those comments were corrected.
- The corrected follow-up separately ran its conditional 1,100-versus-1,000
  first-action screen and uninstrumented CPU confirmation. Full CTest,
  complete-combat gameplay, and holdout were not run. Linux GCC GitHub Actions
  remains the PR verification gate.

Raw JSONL outputs for every A and B repetition and the 10k reference are in
[`raw/`](raw/); [`SHA256SUMS`](raw/SHA256SUMS) covers those files. The frozen
input is already in the repository and is not duplicated here.
The supporting gprof excerpt is [`gprof-summary.txt`](gprof-summary.txt).

**Knowledge impact:** the rollout scratch-state invariant and default-off B
configuration are updated in maintained combat-search documentation. The
shared-RNG quality screen is withdrawn and the corrected independent-seed
follow-up is complete and recorded in maintained current-research status. No
gameplay qualification or default promotion is claimed.
