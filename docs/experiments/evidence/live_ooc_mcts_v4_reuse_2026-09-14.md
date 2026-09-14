# Full-run profile and prepared V4 state reuse

Baseline: `eb84039b99e2f3b932e08fdfc51f1f7eebbbeaa5` (PR #183 after CTM reuse
and the sole-root capability gate). Candidate: `b019e694fcdb150b0ff085eaed118b7272103556`.
One instrumented baseline run plus one uninstrumented baseline/candidate pair,
all seed42/Ironclad A0, 512 OOC simulations, exact10,000 Silver real-combat budget,
project-fair combat/copied noncombat RNG, identical models, keysOFF, Act3-or-death,
CPU0/OMP1. All seed commands use seed_guard.sh. No seed selection or quality cohort.

## Where the baseline OOC time went

Nested wall timers scoped only to `selectOocMctsAction` (26.7586s). Exclusive
buckets subtract nested work; do not sum inclusive figures across nested scopes.

| Exclusive component | Seconds | Share |
| --- | ---: | ---: |
| V4 deck attention/encoding | 7.05179 | 26.4% |
| V4 state fusion | 5.67411 | 21.2% |
| Native tree prediction, including leaf/policy value calls | 5.66836 | 21.2% |
| Rich feature construction, CSV serialization and reparsing | 2.54742 | 9.5% |
| CTM preparation | 2.50178 | 9.3% |
| CTM sampling, support and native application | 0.119014 | 0.4% |
| Prior work excluding nested encoders | 1.47835 | 5.5% |
| Leaf policy excluding nested encoders/features/tree prediction | 1.53094 | 5.7% |
| Other leaf work | 0.0791269 | 0.3% |
| Remaining root/tree/adapter work | 0.107694 | 0.4% |

Inclusive prior cost7.6423s and leaf cost16.3878s overlap the component buckets.
The profile called each V4 deck/state encoder171,763 times, rich features87,877
and tree prediction167,576 times. Tree timing includes both floor/win calls in
continuation policies; it is not a measurement of pure final-leaf v_win alone.
Profiler outcome, all non-timing counters, and all28 Silver telemetry records
match the preceding uninstrumented run. Instrumentation overhead/rounding applies.
The patch/header and scoped source hashes are preserved in the packet; none of
the profiler was added to maintained source.

## Change and correctness

V4 state encoding is action-independent but was recomputed for every candidate.
`PreparedState` owns128 floats; `prepareState` preserves deck/relic/potion pooling
and fusion operations/order. Policy/Q overloads reuse that state and retain the
per-action concatenation and head computations. The MCTS prior and eight V4 Q
loops (card reward/rest/upgrade/event/shop/treasure/boss relic/map) prepare once
per immutable candidate set. Live fallback and imagined continuation retain the
same ordered dispatch, margins/ties and agent RNG consumption. Preparations
never persist across a candidate loop, state/path change or model reload.
No model/artifact/schema, tree search, support, sole-root gate, or leaf semantics
changed. Legacy single-action entry points remain available.

Independent probe compiled the pre-change header under a distinct type name:
512 synthetic state/candidate cases, including empty/max token groups, clamping,
all screen/action codes and interleaved preparations. All1,536 bitwise checks
pass for complete184-float representations, policy logits and Q values.
Maintained adapter tests compare prepared/legacy inference across supported
screen candidates and frozen V4 fixtures. Five focused CTests pass: core MCTS,
OOC semantic producer, gameplay analyzer, adapter and live startup. The sole
Wheel RNG/fallback regression remains included and passes. Full CI is tracked
on the PR; independent implementation review remains the draft handoff.

## Uninstrumented paired runtime

| Measurement | Baseline | Candidate | Reduction |
| --- | ---: | ---: | ---: |
| Full run | 43.6509s | 33.8555s | 22.44% (1.289x) |
| OOC MCTS | 25.998381s | 16.063340s | 38.21% (1.618x) |
| Whole process including startup | 43.816466s | 33.996594s | descriptive |

Both exit0 with the same floor50/Act3 death. All non-timing OOC metrics match,
including207 decisions,148owned/59fallback,76,792completed/76,815attempted,
4,497successful surrogate samples and23support aborts. All28 complete Silver
combat telemetry lines and the support-reason JSON match exactly. Trivial-root
bypasses/locked stops/saved simulations are zero. No per-action/full-state trace
was collected; aggregate equality alone is not full trajectory/state parity.

One seed, one ordered pair: descriptive engineering timing, not an average
speedup or decision-quality qualification. Relative to the earlier original
baseline62.3369s, current33.8555s is45.69% lower, but that comparison spans trials.
The remaining measured opportunities include tree prediction and rich-feature
CSV conversion; neither is changed here. Re-profile the candidate before
assuming their original shares still hold.

[Full raw packet](live_ooc_mcts_v4_reuse_2026-09-14.json) contains exact commands,
environment, source/binary/model hashes, instrumentation, independent probe,
raw logs/metadata/CSV and focused test results. Knowledge impact: current V4
preparation lifetime/API in the OOC KB and chronological engineering evidence.
