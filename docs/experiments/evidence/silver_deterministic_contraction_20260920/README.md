# Silver deterministic action contraction

Date: 2026-09-20
Baseline: `d5e61ae2078244a27ffea8842821aae2304263b8`
Frozen implementation commit: `3a53d8a0`
Cohort: frozen `hard64-dev` only; HOLDOUT was not used.

This is an offline Silver search experiment. It does not change the live
backend, rollout policy, priors, state equality/hash semantics, or production
defaults.

## Configuration and commands

All arms used the same Release GCC executable built from the frozen
implementation commit:

```text
cmake --preset linux-gcc-release
cmake --build --preset linux-gcc-build --target silver-hard-combat-replay -j2
```

The replay configuration was the frozen hard-combat configuration: 32,768
allocated-node reuse cap, adaptive/exact-lock/rho disabled, and no UID
fragmentation diagnostic. Each arm used the same snapshot file and benchmark
seed in every row:

```text
bash tools/seed_guard.sh build/linux-gcc-release/silver_hard_combat_replay \
  docs/experiments/evidence/silver_hard_combat_v1_20260918/hard64-dev-snapshots.jsonl \
  1000 --arm control|A|B

bash tools/seed_guard.sh build/linux-gcc-release/silver_hard_combat_replay \
  docs/experiments/evidence/silver_hard_combat_v1_20260918/hard64-dev-snapshots.jsonl \
  10000 --arm control|A|B
```

The frozen snapshot SHA-256 is
`ab7c3298754864986c31273a0f1d23967b165fdd79a386261b680b8ad16d0eae`.
The final replay binary SHA-256 is
`1c5a076a820c5b5653b84751e73e6fcb70865a0eed92682f8344d92c747a4668`.

`control` preserves the existing primitive edge surface. `A` adds only
RNG-neutral one-option CARD_SELECT contraction. `B` adds A plus one-edge-per-
follow-up deterministic macros for the seven safe PR #237 tasks, requiring at
least two deduplicated follow-ups.

## Results

Wall time is the sum of per-row `wall_seconds` in the raw JSONL. “Reroot” is
reported as exact/fallback; fallback is not a replay failure. All six runs had
64/64 `status=ok` rows and zero replay failures.

| budget | metric | CONTROL | A | B |
| ---: | --- | ---: | ---: | ---: |
| 1,000 | wins / 64 | 51 | 50 | 51 |
| 1,000 | mean HP/maxHP, losses=0 | 0.344091 | 0.326269 | 0.339315 |
| 1,000 | total MCTS invocations | 2,232 | 2,220 | 2,220 |
| 1,000 | total simulations | 2,232,000 | 2,220,000 | 2,220,000 |
| 1,000 | nodes created | 2,063,754 | 2,048,089 | 2,050,013 |
| 1,000 | CARD_SELECT searches | 104 | 100 | 75 |
| 1,000 | forced selects contracted | 0 | 5 | 5 |
| 1,000 | macro-eligible decision nodes | 0 | 0 | 27,203 |
| 1,000 | macro selections taken | 0 | 0 | 40 |
| 1,000 | wall seconds | 23.640 | 23.457 | 24.562 |
| 1,000 | reroot exact / fallback | 1,627 / 541 | 1,618 / 538 | 1,605 / 551 |
| 10,000 | wins / 64 | 59 | 58 | 57 |
| 10,000 | mean HP/maxHP, losses=0 | 0.469434 | 0.453714 | 0.449982 |
| 10,000 | total MCTS invocations | 2,230 | 2,216 | 2,154 |
| 10,000 | total simulations | 22,300,000 | 22,160,000 | 21,540,000 |
| 10,000 | nodes created | 19,756,757 | 19,640,433 | 18,933,106 |
| 10,000 | CARD_SELECT searches | 105 | 98 | 64 |
| 10,000 | forced selects contracted | 0 | 7 | 7 |
| 10,000 | macro-eligible decision nodes | 0 | 0 | 234,233 |
| 10,000 | macro selections taken | 0 | 0 | 36 |
| 10,000 | wall seconds | 271.403 | 268.640 | 274.189 |
| 10,000 | reroot exact / fallback | 1,554 / 612 | 1,539 / 613 | 1,498 / 592 |

### Paired discordances

Counts below compare the same 64 case IDs. An outcome discordance means a
different win/loss or terminal HP; a trace discordance means a different
action trace hash.

| budget | comparison | outcome discordances | trace discordances |
| ---: | --- | ---: | ---: |
| 1,000 | CONTROL vs A | 3 | 8 |
| 1,000 | CONTROL vs B | 26 | 36 |
| 1,000 | A vs B | 23 | 31 |
| 10,000 | CONTROL vs A | 4 | 11 |
| 10,000 | CONTROL vs B | 30 | 43 |
| 10,000 | A vs B | 28 | 39 |

### B macro coverage by selection task

“Eligible options” is the sum of generated follow-up options across all
eligible search nodes. “Selected” counts macros actually chosen during replay.

| task | 1k eligible options | 1k selected | 10k eligible options | 10k selected |
| --- | ---: | ---: | ---: | ---: |
| ARMAMENTS | 19,841 | 9 | 198,574 | 8 |
| EXHAUST_ONE | 21,910 | 6 | 72,011 | 3 |
| EXHUME | 4,599 | 1 | 22,209 | 2 |
| FORETHOUGHT | 1,216 | 0 | 15,824 | 0 |
| HEADBUTT | 170,501 | 21 | 1,621,367 | 20 |
| LIQUID_MEMORIES_POTION | 17,220 | 3 | 134,697 | 3 |
| WARCRY | 204 | 0 | 2,838 | 0 |
| **Total** | **235,491** | **40** | **2,067,520** | **36** |

## Correctness and interpretation

The focused `silver_search_optimization_test` passed, including the required
two-target Headbutt fixture (four canonical macro choices), one-option A
resolution, final-state/RNG equality, stochastic-parent rejection, unsupported
task fallback, Hologram guard, and `getBestAction()` compatibility. A guarded
one-snapshot smoke replay also passed for all three arms with identical terminal
state hashes.

The directly affected `silver_bridge_test` remains blocked by an unrelated
pre-existing failure in untouched live semantic-lowering behavior: its
representative non-target potion expectation fails, followed by an existing
restored CARD_SELECT action legality exception. No `src/` live-combat file is
changed in this experiment; the raw failure was reproduced after the final
build and is recorded rather than repaired as scope expansion.

The technical contract result is:

```text
FORCED_SELECT_CONTRACTION_PASS
SAFE_SELECT_MACRO_REJECTED
```

A measurably removed a small amount of search work, but its one-win DEV
difference and lower mean HP do not establish a quality-neutral improvement.
B had real coverage and reduced CARD_SELECT searches, simulations, and nodes;
however, it did not improve wall time and was lower on both wins and mean HP at
both budgets. The macro flattening hypothesis is therefore rejected for this
bounded DEV screen, with no production/default promotion. These are frozen
offline results, not live-game or whole-run evidence.

## Raw artifacts

The six raw JSONL outputs are kept beside this README:

| artifact | SHA-256 |
| --- | --- |
| `control-1k.jsonl` | `76b65438de314408d81f4953aa85931de4286236175fae7373828a900456ba57` |
| `arm-A-1k.jsonl` | `d862aabcdfbafb8cbd37cec60686cc7553ccbb1935ae1f1a27631d8fe9e7810d` |
| `arm-B-1k.jsonl` | `d69b7f9cfa724707877de4e95a485dd635883ac023d9ca55ceb1d118a3b1dad1` |
| `control-10k.jsonl` | `189d0d31356f0cece059c5bcdccaa117cabddc6df4206aa1db4f1164325dde68` |
| `arm-A-10k.jsonl` | `7d2ab3b23589d0a14c32d04cc4e7694f8711abedbb8177e873397ee3a816b788` |
| `arm-B-10k.jsonl` | `c00a59643194a2952839e24cfa69ad65517893687b797acadce4ae5fc2d9f4e0` |

Knowledge impact: durable experiment evidence and current interpretation; no
production behavior, default promotion, or benchmark gate changed.
