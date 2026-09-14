# First live OOC MCTS paired Silver gameplay gate

**OOC_MCTS_WINRATE_DOWN.** Using MCTS reduced actual paired gameplay under the
current copied-RNG planning environment. Control won 21/32 (65.625%); treatment
won 10/32 (31.25%). Paired treatment-minus-control win difference **-34.375 pp**,
paired bootstrap 95% CI **[-53.125, -15.625] pp**. Classification uses only this CI.
One treatment-only win, twelve control-only wins and nineteen same-result seeds;
exact two-sided McNemar/discordant binomial p = **0.00341796875**, descriptive.

The named hypothesis was that OOC MCTS improves Act-3 win rate over the current
V4 OOC stack. This is an engineering full-game policy A/B. Both arms played
normal real combat through **Silver**; the surrogate was used only in detached
MCTS imagination. The user explicitly replaced the initial Searcher2 real-combat
plan with Silver before any decision-bearing seed ran. The 1,000-simulation
budget and every MCTS parameter remained fixed. No training, artifact regeneration,
support expansion, parameter tuning or extra decision-bearing seeds occurred.

Baseline `3057ea79f8a678ba13f9f2ea2b4834850fa2dd87`; MCTS implementation independently reviewed at
`0c7d932d6231de5d3cd5677d8ddac5d4b023d9d2`; final pre-gate frozen SHA
`c705072f50e12892dd02a6da6dc1e39305b6839e`. Checkout preflight reported a standard checkout already on
`codex/ooc-ctm-benchmark1`, clean at the requested baseline with matching
`origin/main` and pinned submodules. No new worktree was created.

Binary SHA256 `97e275b9b0c191ae9a7daf5a07ea3187a38f85350ce43eb92b9d9dabf44d218b`. Native combat artifact
`/home/philippherrmann/sts_sweep/runs/combat-transition-runtime-native-20260914/combat_transition_v1.native` SHA256
`f9520a14b1fc42e2a22840c0c2cab0b13ebd8ab6285b5c943662f5e0e9cd9233` matched before smoke/freeze and after the gate.
Tracked V4, floor/win and default combat-policy hashes are in [models.sha256](live_ooc_mcts_2026-09-14/models.sha256).
Both arms used the same binary and frozen SHA, A0, four OpenMP threads, no keys,
and Act-3 stop. The effective metadata identifies Silver, allocated reuse cap
32768, exact root budgets and adaptive OFF. Existing native model banner fields
describe configured native flags; **effectiveCombatBackend=silver** identifies
actual played combat.

| Paired outcome | Control mean | Treatment mean | Difference | Bootstrap 95% CI |
| --- | ---: | ---: | ---: | --- |
| floor | 48.00000 | 41.71875 | -6.28125 | [-10.46875, -2.31250] |
| hpEnd | 33.62500 | 12.31250 | -21.31250 | [-31.68750, -10.81250] |
| fightsLost | 0.31250 | 0.68750 | +0.37500 | [+0.18750, +0.56250] |
| deathCombat | 6.25000 | 13.43750 | +7.18750 | [+3.34375, +11.06250] |
| seconds/run | 2.36761 | 10.74972 | +8.38211 | [+6.74538, +10.02677] |

The mean per-run wall-time ratio is **4.5403234x**; outer benchmark wall times
were 19.5 s control and 94.9 s treatment, with sequential arms. Despite its
`cpu_sec/run` banner label, `bestbench` `sec` is steady-clock elapsed time.
Raw deathCombat means include the -1 survivor/event-death sentinel and must not
be read as time to death. Among nine pairs with combat deaths in both arms, the
descriptive mean deathCombat difference is -0.2222222 combats. Secondary outcomes
do not alter classification.

Treatment diagnostics: mean 151 OOC decisions/run, 123.40625 owned, 27.59375
fallback; fallback rate 18.2740066%. Mean 15,796 simulations, 12,764.65625 sampled
action transitions, 980.4375 combat-surrogate calls and 15,771 leaf evaluations/run.
All 32 runs reached maximum search depth 3. Mean MCTS wall/thread CPU time
8.8288376/8.8284433 s per run, 82.1308326% of total per-run wall time. Aggregate
3,949 owned decisions, 31,374 surrogate calls and 702 real Silver combats; control
played 797 real Silver combats. Every ON row satisfies decisions=owned+fallback
and simulations=128*owned; OFF search/ownership/fallback fields are zero.
Seed970004 has95 owned decisions and 0 surrogate samples; individual unsupported
combat states retain native leaves. The arm has substantial search/combat coverage.

These diagnostics do not establish why MCTS hurt. Depth3 is descriptive, not
proof that a larger budget would help. Root action histories were not recorded;
the next bounded investigation should inspect changed strategic decisions and
leaf/boundary behavior before another experiment. Keep MCTS OFF and return this
negative evidence for independent review. No automatic sweeps or extra seed count.
Copied hidden noncombat RNG can bias imagined futures; this result does not
establish unbiased long-horizon MCTS values, scientific stochastic fairness or
deployment qualification.

Exact common benchmark environment (other inherited STS_/STRATEGIC_/OMP_ variables
were cleared by the archived runner):

```text
OMP_NUM_THREADS=4
STS_COLLECT_KEYS=0
STS_EXECUTABLE_GIT_SHA=c705072f50e12892dd02a6da6dc1e39305b6839e
STS_FAIR=1
STS_NATIVE_OOC=1
STS_OOC_STRATEGIC_BOSS_RELIC=1
STS_OOC_STRATEGIC_EVENT=1
STS_OOC_STRATEGIC_MARGIN=1.0
STS_OOC_STRATEGIC_REST=1
STS_OOC_STRATEGIC_SHOP=1
STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_final.native
STS_OOC_STRATEGIC_TREASURE=1
STS_SEARCHER3=0
STS_SILVER_ADAPTIVE=0
STS_SILVER_EXACT_ROOT_BUDGETS=1
STS_SILVER_REUSE_CAP_MODE=allocated
STS_SILVER_SEARCH=1
STS_SILVER_TELEMETRY=1
STS_SILVER_VNET_LEAF_DIRECT=0
STS_STOP_AFTER_ACT=3
```

Control adds `STS_OOC_MCTS=0`. Treatment adds `STS_OOC_MCTS=1`,
`STS_OOC_MCTS_SIMS=128`, and `STS_OOC_MCTS_COMBAT_MODEL` at the artifact path above.
Both set `STS_OOC_MCTS_TRACE` to their respective result CSV plus `.mcts.csv`.
Exact environments/argv are archived in
[control.config.json](live_ooc_mcts_2026-09-14/control.config.json) and
[treatment.config.json](live_ooc_mcts_2026-09-14/treatment.config.json).
Each arm ran the guarded equivalent of:

```bash
bash tools/seed_guard.sh build/linux-gcc-release/one_combat bestbench 1000 32 0 970000 <arm.csv>
```

Fresh paired gate seeds **970000..970031**; no gate overlap and no more than 32
paired seeds. Implementation seeds **969992..969999** are excluded. Eight-seed
OFF parity against the preserved baseline binary matched won/floor/act/hpEnd/
maxHp/fightsLost/deathCombat/deathEncounter exactly on the final implementation.
Eight-seed ON smoke passed with 671 owned decisions, 6073 imagined combat calls
and 125 ordinary real combats (the initial requested Searcher2 backend). After
the user switched the gate to Silver, the excluded seed 969992 established
Silver baseline/branch OFF parity and ON ownership/imagined samples/real dispatch
with zero bridge failure counters. This backend change occurred before gate freeze.

Build: `cmake --preset linux-gcc-release`, then
`cmake --build build/linux-gcc-release --target one_combat ooc-mcts-test -j 8`.
Focused CTest `ctest --test-dir build/linux-gcc-release -R '^ooc_mcts($|_)' --output-on-failure`
passed 3/3. Qualified-artifact startup script passed 11/11 cases. Environment doctor
passed with `UV_CACHE_DIR=/tmp/ooc-uv-cache`. Python compilation and synthetic
UP/DOWN/INCONCLUSIVE analysis checks passed. Independent implementation and
post-run statistical/accounting reviews passed, including exact bootstrap CI
reproduction. The full local CTest suite was not run; GitHub Linux GCC is the
authoritative PR check. The final analysis validation-only repair has no MCTS
or benchmark-binary changes and retains the frozen bootstrap/decision rule.

Preserved invalid attempts: the first ON smoke completed 5/8 and failed 3/8 on
native duplicate GOLD IDs; multi-gold states now use leaf/live fallback, with
candidate enumeration unchanged. The original Silver baseline canary inherited
the task checkout SHA despite using the preserved baseline binary; its metadata
is invalid. A fresh corrected filename with explicit baseline SHA reproduced
exact OFF parity after the sequential gate. The first analysis rejected a
sampleless individual run before bootstrapping; aggregate coverage is the
specified contract and this validation-only bug was corrected. These attempts
and repairs are detailed in [validation-notes.json](live_ooc_mcts_2026-09-14/validation-notes.json).

Raw gameplay is authoritative:
[control CSV](live_ooc_mcts_2026-09-14/control.csv),
[treatment CSV](live_ooc_mcts_2026-09-14/treatment.csv),
[paired analysis JSON](live_ooc_mcts_2026-09-14/result.json),
[freeze](live_ooc_mcts_2026-09-14/freeze.json),
[post-gate integrity](live_ooc_mcts_2026-09-14/post-gate-validation.json).
The directory also preserves per-run traces, effective metadata, gzip-compressed
full Silver logs, build/test logs, smoke rows and the runner.
Reproduce analysis from repository root:

```bash
python3 tools/analyze_ooc_mcts_gameplay.py \
  docs/experiments/evidence/live_ooc_mcts_2026-09-14/control.csv \
  docs/experiments/evidence/live_ooc_mcts_2026-09-14/treatment.csv /tmp/ooc-mcts-result.json
```

Bootstrap: 200,000 paired-seed resamples, NumPy PCG64 seed 20260914, shared pair
indices for all metrics, percentile 2.5/97.5% quantiles with linear interpolation.
Knowledge impact: architecture/live primitive isolation and unique-ID boundary,
configuration interface, code routing and current research status updated in
maintained KB; raw experiment outcome recorded in ledger §243 and this evidence.
