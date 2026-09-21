# Silver settled-player queue-item canonicalization

Date: 2026-09-21

Classification: **`QUEUE_ITEM_CANONICALIZATION_REJECT`**

## Question and frozen provenance

This experiment tested whether a default-off, boundary-local relaxed dedup can
ignore only stale `curCardQueueItem` values when both states are settled,
unresolved `PLAYER_NORMAL` states with empty action and card queues. The
implementation did not change `BattleContext::equalForSearch()`,
`hashBattleState()`, reroot identity, reuse cap, DPW, rollout behavior, or any
live/gameplay environment control.

- Baseline main: `39e91c8f6d33a842ddb378b681aeac681b4670c9`
- Frozen implementation candidate: `16054615c6a122b0894bfd11840f5702a7d79285`
- Release replay binary SHA-256:
  `ef09ce52b69aaae4bacbc76c7dc9c573e30bd70f772901420f683f871b797021`
- Input: `hard64-dev-snapshots.jsonl`
- Input SHA-256:
  `ab7c3298754864986c31273a0f1d23967b165fdd79a386261b680b8ad16d0eae`
- Cohort: 64 frozen DEV cases; `hard64-holdout` was not used.
- Build/runtime: Release, `OMP_NUM_THREADS=4`, allocated 32,768-node reuse
  cap, adaptive/exact-lock/rho off, all other settings identical.
- Exact frozen candidate patch: [`frozen-candidate.patch`](frozen-candidate.patch)
  SHA-256 `874d45b52b99561a82747921c1f25ccfedf00a1fe298a5020dbe92befc80384a`.

## Implementation verification

The frozen candidate added `SilverSearchConfig::queueItemCanonicalizationEnabled`,
propagated it to `BattleSearcher`, and exposed it only through
`silver_hard_combat_replay --queue-item-canonicalization`. The candidate's
historical telemetry field `queueItemCanonicalMerges` counts relaxed lookup
hits: a lookup that fails exact equality and succeeds after ignoring
`curCardQueueItem`. It does not count unique exact variants, nodes avoided, or
unique merge groups. This field is therefore called `queueItemRelaxedHits`
below. The rejected implementation is not retained in the core search path;
the exact candidate is preserved as the patch artifact above.

Focused checks passed before the candidate was frozen:

```text
bash tools/seed_guard.sh build/linux-gcc-release/silver_search_optimization_test
silver_search_optimization PASS

ctest --test-dir build/linux-gcc-release --output-on-failure \
  -R 'silver_search_optimization|silver_bridge_boundary|silver_integration_default'
100% tests passed out of 3
```

The optimization test covers default-off parity, eligible and ineligible
states, ordinary field differences, deterministic card continuation, and the
Attack Potion `CARD_SELECT` boundary.

## Phase A: 1,000 simulations per decision

Commands, both run through the repository seed guard, were:

```bash
OMP_NUM_THREADS=4 bash tools/seed_guard.sh \
  build/linux-gcc-release/silver_hard_combat_replay \
  docs/experiments/evidence/silver_hard_combat_v1_20260918/hard64-dev-snapshots.jsonl \
  1000 --arm control

OMP_NUM_THREADS=4 bash tools/seed_guard.sh \
  build/linux-gcc-release/silver_hard_combat_replay \
  docs/experiments/evidence/silver_hard_combat_v1_20260918/hard64-dev-snapshots.jsonl \
  1000 --arm control --queue-item-canonicalization
```

Terminal HP fraction is `hp_end / max_hp` for wins and `0` for losses.

| arm | accepted/failures | wins | mean terminal HP fraction | decisions | simulations | nodes created | nodes/simulation | queueItemRelaxedHits | cases with hit | wall seconds | exact reroots | fallback reroots | fallback fraction |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| control | 64/0 | 51 | 0.344091 | 2,232 | 2,232,000 | 2,063,754 | 0.924621 | 0 | 0/64 | 15.852071 | 1,627 | 541 | 24.954% |
| treatment | 64/0 | 50 | 0.355610 | 2,252 | 2,252,000 | 2,079,300 | 0.923313 | 317,084 | 64/64 | 15.821877 | 1,418 | 770 | 35.192% |

Paired deltas (treatment minus control, except percentages):

- nodes/simulation: `-0.1415%`, below the approximately 1% Phase-A signal
  needed for confirmation;
- wall time: `-0.1905%`, too small to treat as an efficiency result;
- wins: `-1` case;
- mean terminal HP fraction: `+0.011519`;
- fallback reroot fraction: `+10.238` percentage points;
- action-trace hash discordance: `64/64` cases.

## Decision and boundary

The treatment produced many relaxed lookup hits in every case, but the
structural reduction was weak and aggregate fallback rerooting increased by
more than the 2-point warning threshold, with every paired case changing its
action-trace hash. Because the treatment also changed the played trajectory in
every case, this experiment does not isolate whether changed trajectories or
retained-tree identity caused the reroot-opportunity difference. The aggregate
reroot regression is nevertheless sufficient to reject this exact treatment
under the preregistered rule. The treatment quality screen did not
independently cross the HP warning threshold, but that does not override the
reroot and trace failures.

Phase B at 10,000 simulations was **not run**. This result is bounded DEV
evidence only. It authorizes no default promotion, live gameplay support,
reroot relaxation, holdout use, or claim of production equivalence.

## Raw outputs

- [`control-1000.jsonl`](control-1000.jsonl) SHA-256
  `09b28d8c5f54096883f387280374b589be32b3127dfba21ac672ad4638711ad5`
- [`treatment-1000.jsonl`](treatment-1000.jsonl) SHA-256
  `c3b88fc01a7bb6de510be3c7b7cf1785b0a017056935d58c051998e1d4b52172`

The raw JSONL retains the candidate field name `queueItemCanonicalMerges`;
its value is the `queueItemRelaxedHits` lookup-event count described above.

**Knowledge impact:** durable negative Silver search evidence only; no
production behavior, default, RNG, schema, model, live gameplay, or holdout
qualification changed.
