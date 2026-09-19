# Silver duplicate potion-slot deduplication (2026-09-19)

This is a bounded structural-correctness and fixed-state efficiency screen for
Silver's search-local potion action enumeration. It is not gameplay equivalence
proof or a production quality gate.

## Provenance and implementation

- Baseline: `9c96f0f95751ba7f041a33a41f1b78a9721e27ab` (merged PR 240).
- Treatment candidate: `4b0bda3083ef808cf23deb545b0e5301317f2d7f`.
- Changed implementation: `third_party/silver_lightspeed/src/sim/search/BattleSearcher.cpp`.
- Changed tests: `apps/silver_search_optimization_test.cpp` and
  `apps/silver_bridge_test.cpp`.
- Conceptual scope: Silver retains the first occupied slot for each potion enum
  while preserving the existing legality and target loops. `Action`, live
  potion behavior, semantic fingerprints, exact potion-slot lowering, potion
  hashing, and production state canonicalization were unchanged.

## Structural correctness

The focused tests passed through the existing `silver_search_optimization` and
`silver_bridge_boundary` CTest entries. They establish:

- `Strength, empty, Strength` exposes one use action from slot `0`; ordinary
  non-potion actions, including `END_TURN`, are unchanged.
- Two `Fire Potion` copies with two targetable monsters expose two actions from
  slot `0`, one per target; targets are not collapsed.
- Three Strength copies remain usable over three successive decisions, with
  one representative at each decision and zero actions only after all three
  copies are consumed.
- Strength and Dexterity retain separate representatives.
- Duplicate Fairy Potions expose one discard only; blocked duplicate Smoke
  Bombs expose one discard only; Gambler's Brew remains one action with a
  nonempty hand and unavailable with an empty hand.
- Executing slot `0` versus slot `2` for deterministic Strength, targeted Fire,
  and Entropic Brew produces equal `equalForSearch` successors after test-only
  potion-belt sorting. Entropic Brew also has equal post-action RNG state and
  equal potion multiset.
- The wire bridge returns one Strength semantic action with `potionSlot=0`,
  resolves it against the exact live slot, and executes it live-validly.

Focused command:

```text
cmake --preset linux-gcc-debug-ccache
cmake --build --preset linux-gcc-debug-ccache-build -j2 \
  --target silver-search-optimization-test silver-bridge-test
ctest --test-dir build/linux-gcc-debug-ccache \
  -R '^(silver_search_optimization|silver_bridge_boundary)$' --output-on-failure
100% tests passed out of 2
```

## Fixed-state Release microbenchmark

Fixture: valid Silver Ironclad `PLAYER_NORMAL` state, empty hand, maximum
five-slot capacity, and five Strength Potions. The benchmark source was the
same treatment source for both arms (`sha256=
d4f93a6b5aecc7c12cf11dbdd3f42d5c63f4e267fad44521de74240a1f2bc16b`). Each arm
used Release GCC, 10,000 simulations, identical root/RNG/search settings, and
seven repetitions.

```text
cmake --preset linux-gcc-release-ccache
cmake --build --preset linux-gcc-release-ccache-build -j2 \
  --target silver-search-optimization-test
```

Baseline libraries were exported by `tools/agent/baseline_build.py` from
`9c96f0f…` and linked with the same current benchmark-source object. The
baseline instrumented executable SHA-256 is
`f5aba8e5c9f6e4eeaa9f86de582f4611d6b870807b092e6a7ee20c63f2e7415e`; the
treatment executable SHA-256 is
`bb5bf65ba95d3aee7a7d160354c0bf3d281487c9f7998367cb9a12fe9106d1c4`.

```text
baseline: 0.0334482, 0.0343304, 0.0346002, 0.0339673, 0.0345303, 0.0285543, 0.0300224
treatment: 0.0266973, 0.0264213, 0.0266100, 0.0274337, 0.0258310, 0.0234443, 0.0222240
```

| arm | root actions | simulations | nodes created | action count | median wall seconds |
|---|---:|---:|---:|---:|---:|
| baseline | 6 | 10,000 | 2,733 | 7 | 0.0339673 |
| treatment | 2 | 10,000 | 1,033 | 11 | 0.0264213 |

The treatment median is `22.22%` lower. This is fixed-root selector evidence,
not a whole-run runtime claim.

## Frozen DEV screen

Both arms ran the stored
`docs/experiments/evidence/silver_hard_combat_v1_20260918/hard64-dev-snapshots.jsonl`
cohort (`sha256=
ab7c3298754864986c31273a0f1d23967b165fdd79a386261b680b8ad16d0eae`) with
1,000 simulations per decision, Release GCC, `OMP_NUM_THREADS=4`, and the
existing fixed replay configuration through `tools/seed_guard.sh`. HOLDOUT was
not used.

| arm | wins | mean terminal HP/maxHP | decisions | simulations | nodes | wall seconds | failures |
|---|---:|---:|---:|---:|---:|---:|---:|
| baseline | 51/64 | 0.329883253 | 2,234 | 2,234,000 | 2,069,231 | 15.628747 | 0 |
| treatment | 51/64 | 0.344091151 | 2,232 | 2,232,000 | 2,063,754 | 15.549843 | 0 |

The baseline and treatment replay executable SHA-256 values were
`b34bb3b242c51cd16cad1e0479be2f9062b1accd751bdf742fdbece09c95f74f` and
`966d132ee94c4324831b2d4930ad909ccc43ab2c61b72d1b8d54787effe3e238`.
Raw outputs were retained in the ignored build directory as
`build/silver_potion_hard64_baseline.jsonl` and
`build/silver_potion_hard64_treatment.jsonl`.

Seven of the 64 starting states contain duplicate nonempty potion types:
`12100027/18`, `12100029/25`, `12100037/22`, `12100037/28`, `12100042/29`,
`12100044/20`, and `12100052/14`. Direct root enumeration found a changed
initial action surface in `5/7` of those cases; the other two had zero legal
potion actions at the initial root. Action-trace hashes differed in `7/64`
cases, exactly those seven duplicate-potion cases. Win count and replay
validity were unchanged. Six of the seven had trajectory-dependent terminal
HP/turn differences, all while retaining the same win/loss outcome as their
paired arm; these are not interpreted as policy improvement or degradation.

The replay output exposes the starting `state_hash`, which was identical
between arms for all 64 cases, but does not expose a terminal state hash.
Consequently final-state-hash differences are **not available from this
screen's schema** and no terminal-hash equivalence claim is made. Action-trace,
outcome, HP, decision, simulation, node, wall-time, and failure fields are the
reported observables.

## Decision

`SILVER_POTION_SLOT_DEDUP_ACCEPT` for implementation correctness and the
bounded fixed-root efficiency screen. This is bounded confirmation, not
equivalence proof or default-promotion evidence. The DEV trajectory changes
are expected consequences of removing physically redundant choices and remain
uncertainty rather than a gameplay-quality claim.

Knowledge impact: durable Silver action-enumeration behavior and experiment
evidence; no model, RNG, semantic schema, search budget, or gameplay default
change.
