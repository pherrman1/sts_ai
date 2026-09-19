# Silver `GAMBLE` multiplicity-dedup screen (2026-09-19)

This is a bounded correctness and fixed-state efficiency screen for the
Silver-only sequential `GAMBLE` selector. It is not gameplay equivalence proof
or a production quality gate.

## Provenance and implementation

- Baseline: `9cb66773d65e98f3e8a23ff582c52aaf151b47fc` (merged PR 237).
- Treatment: `codex/silver-gamble-multiplicity` working-tree candidate based on
  that baseline; the final reviewed commit is recorded by the PR handoff.
- Changed code: `third_party/silver_lightspeed/src/sim/search/Action.cpp`.
- Focused tests: `apps/silver_search_optimization_test.cpp` and the existing
  `apps/silver_bridge_test.cpp` sequential-transaction coverage.
- Scope: only `CardSelectTask::GAMBLE` next-action enumeration changed;
  `EXHAUST_MANY`, `selectedBits`, semantic fingerprints, native multi-select,
  and search budgets were unchanged.

The treatment reuses `Action::areCardsEquivalentForSearch` and scans only
currently unselected cards. It keeps the first unselected representative in
hand order and always retains confirmation. The bounded `EXHAUST_MANY` audit
found the concrete unresolved issue that exhaust selection invokes
`triggerAndMoveToExhaustPile` per physical index, so equivalent copies may
participate in index-dependent trigger ordering with distinct selected cards.

## Structural correctness

`silver_search_optimization_test` passed the following deterministic checks:

- `Strike, Defend, Strike, Strike`: initial singles are indices `0,1` plus
  confirmation; after selecting one Strike, index `2` appears; after two,
  index `3` appears; a noncanonical incoming selection remains valid.
- A `2 Strike + 2 Defend` hand reaches exactly the same semantic count tuples
  as all `16` original physical masks: `9` tuples (`3 * 3`).
- A `5 Strike + 5 Defend` hand reaches exactly `36` semantic tuples (`6 * 6`)
  instead of `1,024` physical masks.
- Upgraded, distinct `costForTurn`, and distinct `retain` copies remain
  separate. Identity-sensitive special-data copies with different `uniqueId`s
  remain separate under the existing helper.
- `silver_bridge_boundary` passed with duplicate-heavy sequential `GAMBLE`
  transaction coverage: intermediate private picks, exact reroot, final
  confirmation, live-state resolution, and no live-state mutation.

Focused command outcomes:

```text
ctest --test-dir build/linux-gcc-debug-ccache \
  -R '^(silver_search_optimization|silver_bridge_boundary)$' --output-on-failure
100% tests passed out of 2
```

## Fixed-state local microbenchmark

Fixture: valid Silver Ironclad combat state with `5 Strike + 5 Defend` in hand;
10,000 simulations; identical Release GCC build settings, root state, RNG, and
search budget. The benchmark source was the same pushed
`apps/silver_search_optimization_test.cpp` (`sha256=
9abd4aff781fe6e1480a325b856276c4117c270b6bc34b9c4a80f76afba9c803`) for both
arms. Seven repetitions per arm produced:

```text
baseline: 0.121032, 0.116324, 0.113559, 0.116201, 0.109390, 0.105897, 0.119517
treatment: 0.0901018, 0.0893465, 0.0890767, 0.0907252, 0.0903225, 0.0946379, 0.0971926
```

| arm | root actions | action count | nodes created | median wall seconds |
|---|---:|---:|---:|---:|
| baseline | 11 | 23 | 10,000 | 0.1162010 |
| treatment | 3 | 24 | 10,000 | 0.0903225 |

The baseline root has ten physical card picks plus confirmation; treatment has
one Strike representative, one Defend representative, plus confirmation. The
Release median was `22.27%` lower for treatment. This is a local selector
screen, not a whole-run runtime claim.

Treatment was built with:

```text
cmake --preset linux-gcc-release-ccache
cmake --build --preset linux-gcc-release-ccache-build --target silver-search-optimization-test -j2
```

The pristine baseline libraries were exported with the repository baseline
helper from `9cb66773d65e98f3e8a23ff582c52aaf151b47fc`, using the same
`linux-gcc-release-ccache` configure/build presets. Because the baseline commit
predates the optional microbenchmark mode, the identical current test source
object was compiled with the generated Release flags and linked against those
baseline libraries:

```text
/usr/bin/g++ -O3 -DNDEBUG -std=gnu++20 -Wno-shift-count-overflow -fopenmp -O3 -flto \
  -DagentMtRunner=silver_agentMtRunner -Dfixed_list=silver_fixed_list -DinitMaps=silver_initMaps \
  -Djava=sts_silver_java -DrollWeightedIdx=silver_rollWeightedIdx -DsimulationIdx=silver_simulationIdx -Dsts=sts_silver \
  -I<worktree>/third_party/silver_lightspeed/include -I<worktree>/include \
  -c apps/silver_search_optimization_test.cpp -o build/release-baseline-instrumented/silver_search_optimization_test.o
/usr/bin/g++ -O3 -DNDEBUG -fopenmp -flto -Wl,--gc-sections \
  build/release-baseline-instrumented/silver_search_optimization_test.o \
  build/baselines/9cb66773d65e-release/libsilver_combat_model.a \
  build/baselines/9cb66773d65e-release/libsilver_combat_search_bridge.a \
  build/baselines/9cb66773d65e-release/libsilver_combat_model.a \
  -o build/release-baseline-instrumented/silver_search_optimization_test
```

Release artifact SHA-256 values were baseline instrumented executable
`672013e136cab4515e46fdc260f2d159e5c90673a4428bd83a7369c7e7b9f84f`, treatment
executable `485100a35b95f991aff950aa305ae06090b03a1c841f2d40324beab194dede44`,
baseline model library
`2484ec31aca6b4772e563e62a52cdf2003d3f96d8e64d1c44b928d57e2ce36d5`, and
baseline bridge library
`c0d09b3fff8b429e66aaa7d83e098371792551dcef044e4979eee342612b3f10`.

## Frozen DEV no-harm screen

Both arms ran the frozen
`docs/experiments/evidence/silver_hard_combat_v1_20260918/hard64-dev-snapshots.jsonl`
cohort at 1,000 simulations per decision through `tools/seed_guard.sh`.
HOLDOUT was not used.

| arm | wins | mean HP fraction | decisions | simulations | nodes | wall seconds | failures |
|---|---:|---:|---:|---:|---:|---:|---:|
| baseline | 51/64 | 0.329883253 | 2,234 | 2,234,000 | 2,069,231 | 119.801067 | 0 |
| treatment | 51/64 | 0.329883253 | 2,234 | 2,234,000 | 2,069,231 | 120.799379 | 0 |

Action-trace hashes, outcome/HP, decision counts, and final state hashes were
identical for all 64 cases. The DEV null is expected because duplicate-heavy
`GAMBLE` states are rare in this cohort; it is not evidence against the fixed
state result and not a gameplay equivalence claim.

Replay executable SHA-256 values were baseline
`1dff5015e38a15473dc3a64a7e720d502b419a3bca0e44133e02b878f4c83269` and
treatment `ae6c6920d47f56dda8de2f87d609be17fd8708b6eb221e625738dfa6a776ba21`.
Raw JSONL outputs were retained in the local ignored build directory as
`build/silver_gamble_hard64_baseline.jsonl` and
`build/silver_gamble_hard64_treatment.jsonl`.

## Decision

`SILVER_GAMBLE_MULTIPLICITY_DEDUP_ACCEPT` for implementation correctness and
the bounded local selector-efficiency screen. This is bounded confirmation,
not equivalence/default promotion. `EXHAUST_MANY` remains an open separate
proof/experiment.

Knowledge impact: durable Silver action-enumeration behavior and experiment
evidence; no model, RNG, semantic schema, search budget, or gameplay default
change.
