# Numeric rich features and contiguous OOC trees

Baseline: PR #183 head `61882889dfb269a88f6bd26bf5386d9f22dd5d04`.
The initial checkout was merge `c3522862b92e48175c25c29004c434cae30cac71`;
its tree is identical to that baseline. Measured/self-inspected implementation:
`04b7a7878679cc7aa1827fa822ab66dafdf6b8bd`. Later evidence commits do not change runtime code.

## Refreshed baseline profile

One guarded seed42 full run, Ironclad A0, OOC512, exact10,000 Silver, fair combat,
copied noncombat RNG, keysOFF, Act3-or-death, CPU0/OMP1. Temporary nested wall
timers scope `selectOocMctsAction`; exclusive buckets subtract children.
Do not sum inclusive buckets. The scoped total is16.9316s.

| Exclusive component | Seconds | Share |
| --- | ---: | ---: |
| Native tree predictions | 5.66754 | 33.5% |
| Rich features and CSV conversion | 2.57668 | 15.2% |
| CTM preparation | 2.74904 | 16.2% |
| CTM sampling/application | 0.118771 | 0.7% |
| V4 deck encoding | 1.65720 | 9.8% |
| V4 state fusion | 1.28387 | 7.6% |
| Prior excluding nested work | 1.32022 | 7.8% |
| Leaf policy excluding nested work | 1.36938 | 8.1% |
| Other leaf/root/tree work | 0.188919 | 1.1% |

Tree predictions167,576; rich vectors87,877; V4 deck/state encodings36,930 each
(down from171,763 in §252). Tree time includes continuation floor/win calls.
Profile outcome, all non-timing counters,28Silver records and support reasons
match both clean runs. Compilation on other CPUs overlapped this profile; it is
component attribution, not the uninstrumented timing baseline. Console rounding
and timer overhead apply. Patch/header preserved in the raw packet; production
source/both clean binaries have no `speedprof::` symbols.

## Implementation and compatibility

`one_combat::richFeatureVec(gc,path)` builds1,017 numeric values directly.
The driver overload retains thread-local path selection and empty-path fallback.
CSV `richRow`/`vFeatCsv` remain unchanged for datasets/server requests. Every
operand in this rich schema is integral, including potionChance/cardRarityFactor;
there are no floating inputs subject to default stream precision. Static casts
are nevertheless checked byte-for-byte against original CSV/character/strtof
parsing over4,098 states: empty/max decks, all card/potion ID bins, bottles of
all three types, upgrades, relic counters, path visits, exhausted encounter lists,
map boundaries/null maps, keys, and integral float-rounding boundaries/extrema.
Existing entire-string/header/index-map fingerprints still pass.

`CompactTreeNet` validates each tree before translating selected feature indices
to final raw indices. Nodes are contiguous; root offsets plus an end sentinel
supply each tree's base/size. Child indices stay tree-relative. Split comparison,
step guard, tree order, float thresholds/leaves, sequential double accumulation,
exp/logistic/clamping retain their original operations/order. Frozen PR #183
loader/predictor independently compares27,177 double outputs bitwise across
live win/floor and E2c artifacts,4,096random vectors per artifact, sampled
threshold equality/adjacent floats,NaN/infinity and reloads. E2c's extra names
are supplied by the test map. No model, schema, sampling/RNG, search/default,
support, or CUDA change.

## Descriptive performance

One fresh uninstrumented ordered baseline/candidate pair, same seed42/configuration
and model hashes. Baseline built from a pristine `git archive 6188288` in a new
Release cache with the verified pinned dependency directories; candidate from
this worktree. Both builds/tests finished before timing. Both binaries preserved.

| Measurement | Baseline | Candidate | Reduction |
| --- | ---: | ---: | ---: |
| Full game | 32.1673s | 30.3124s | 5.77% |
| OOC MCTS | 15.028404s | 12.852105s | 14.48% |
| Process including startup | 32.331635s | 30.459241s | descriptive |

Both exit0, same floor50/Act3 death. All non-timing OOC counters,28full Silver
telemetry lines and support JSON match, including207decisions,148owned/59fallback,
76,792completed/76,815attempted and23support aborts. Live shortcut/saved metrics
remain0. Aggregate equality is not complete trajectory/state parity; no new
full-run state/action trace or decision-quality cohort was collected. One ordered
pair is not an average-speedup claim and is separate from previous timings.

A separate CPU0/OMP1 inference probe uses128synthetic rich states,10,000calls
per arm,5rounds,alternating order. Volatile member-function pointers give both
predictors equivalent indirect calls and prevent unequal cross-TU inlining.
Median old/new win0.242651/0.211992s (12.64% lower), floor0.333326/0.290193s
(12.94% lower); legacy/numeric features0.274986/0.00917239s (29.98x).
This small hot-working-set fixture is descriptive, not full-run attribution.
Initial direct-call probes showed apparent regressions with unequal optimization
opportunities and are superseded. Root-descriptor/resolution-only exploratory
variants and all logs are retained; final source restores the original flattened
candidate exactly, so its full-run/check evidence remains applicable.

## Verification and handoff

- Worktree preflight/check and doctor: pass; clean starting checkout/pinned dependencies.
- Release affected targets and complete default Debug target set: build exit0.
- Seven focused Release CTests:7/7pass. First E2c harness map failure repaired;
  live win/floor bitwise comparisons already passed in that attempt.
- Complete Debug CTest with locked analysis environment:91/91pass.
- Feature parity4,098states and tree parity27,177comparisons: pass in Release and Debug.
- Guarded profile and both clean full-run commands:exit0.
- Source diff checks and both clean binary profiler-symbol audits:pass.

First candidate compile failure from namespace overload hiding was repaired with
a using declaration before rebuilding. Exploratory probe's first relative include
path was repaired before any timing. Existing Silver/SimpleAgent ODR/narrowing/LTO
warnings remain. Independent implementation review and decision-quality cohort
not run. Linux GCC CI is authoritative on the draft PR; do not merge automatically.

Knowledge impact: maintained native rich/tree interfaces in the OOC KB and
chronological engineering evidence (§253). No scientific/default qualification.
[Full raw packet](ooc_rich_tree_speed_2026-09-14.json) includes exact commands,
environment, source/binary/model hashes, raw logs/CSV/metadata/support, timers,
probe source/build helper, exploratory variants and repaired check outcomes.
