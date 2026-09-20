# Silver deterministic action contraction

Date: 2026-09-20
Baseline: `d5e61ae2078244a27ffea8842821aae2304263b8`
Frozen implementation commit: `796fa5cd6fddae03c46235fd529c41ae585e2b42`
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
`61d2fa0f53ba20fb2f23b6d77577ea653173831d06074092d2908c8359851722`.

`control` preserves the existing primitive edge surface. `A` adds only
RNG-neutral one-option CARD_SELECT contraction. `B` adds A plus one-edge-per-
follow-up deterministic macros for the seven safe PR #237 tasks, requiring at
least two deduplicated follow-ups.

## Corrective implementation rerun

Review identified that the original B eligibility check validated only the
first primitive action's RNG state. A deterministic first action such as True
Grit+ can enter `EXHAUST_ONE`, whose Dead Branch-triggered continuation is
stochastic; the original macro edge stored only the first action and could
therefore replay incompatible chance outcomes. At the frozen corrected commit,
`macroFollowUps()` executes every candidate follow-up on a copy of the
post-first-action state and rejects the entire macro if any candidate changes
RNG. The focused optimization fixture covers True Grit+ with Dead Branch and
three hand cards: it proves the first action is RNG-neutral, the exhaust
continuation consumes RNG, and the search retains the primitive edge without a
continuation. All six result files below were regenerated from this corrected
commit.

## Results

Wall time is the sum of per-row `wall_seconds` in the raw JSONL. “Reroot” is
reported as exact/fallback; fallback is not a replay failure. All six runs had
64/64 `status=ok` rows and zero replay failures.

| budget | metric | CONTROL | A | B |
| ---: | --- | ---: | ---: | ---: |
| 1,000 | wins / 64 | 51 | 50 | 51 |
| 1,000 | mean HP/maxHP, losses=0 | 0.344091 | 0.326269 | 0.333693 |
| 1,000 | total MCTS invocations | 2,232 | 2,220 | 2,230 |
| 1,000 | total simulations | 2,232,000 | 2,220,000 | 2,230,000 |
| 1,000 | nodes created | 2,063,754 | 2,048,089 | 2,060,113 |
| 1,000 | CARD_SELECT searches | 104 | 100 | 79 |
| 1,000 | forced selects contracted | 0 | 5 | 5 |
| 1,000 | macro-eligible decision nodes | 0 | 0 | 22,772 |
| 1,000 | macro selections taken | 0 | 0 | 37 |
| 1,000 | wall seconds | 17.591 | 16.918 | 18.770 |
| 1,000 | reroot exact / fallback | 1,627 / 541 | 1,618 / 538 | 1,618 / 548 |
| 10,000 | wins / 64 | 59 | 58 | 57 |
| 10,000 | mean HP/maxHP, losses=0 | 0.469434 | 0.453714 | 0.458448 |
| 10,000 | total MCTS invocations | 2,230 | 2,216 | 2,176 |
| 10,000 | total simulations | 22,300,000 | 22,160,000 | 21,760,000 |
| 10,000 | nodes created | 19,756,757 | 19,640,433 | 19,170,926 |
| 10,000 | CARD_SELECT searches | 105 | 98 | 68 |
| 10,000 | forced selects contracted | 0 | 7 | 7 |
| 10,000 | macro-eligible decision nodes | 0 | 0 | 215,040 |
| 10,000 | macro selections taken | 0 | 0 | 32 |
| 10,000 | wall seconds | 201.453 | 201.980 | 210.446 |
| 10,000 | reroot exact / fallback | 1,554 / 612 | 1,539 / 613 | 1,515 / 597 |

### Paired discordances

Counts below compare the same 64 case IDs. An outcome discordance means a
different win/loss or terminal HP; a trace discordance means a different
action trace hash.

| budget | comparison | outcome discordances | trace discordances |
| ---: | --- | ---: | ---: |
| 1,000 | CONTROL vs A | 3 | 8 |
| 1,000 | CONTROL vs B | 23 | 35 |
| 1,000 | A vs B | 20 | 30 |
| 10,000 | CONTROL vs A | 4 | 11 |
| 10,000 | CONTROL vs B | 26 | 41 |
| 10,000 | A vs B | 24 | 37 |

### B macro coverage by selection task

“Eligible options” is the sum of generated follow-up options across all
eligible search nodes. “Selected” counts macros actually chosen during replay.

| task | 1k eligible options | 1k selected | 10k eligible options | 10k selected |
| --- | ---: | ---: | ---: | ---: |
| ARMAMENTS | 19,950 | 9 | 198,068 | 8 |
| EXHAUST_ONE | 633 | 1 | 5,624 | 0 |
| EXHUME | 5,175 | 3 | 11,502 | 1 |
| FORETHOUGHT | 1,082 | 0 | 8,907 | 0 |
| HEADBUTT | 177,174 | 21 | 1,720,507 | 20 |
| LIQUID_MEMORIES_POTION | 17,220 | 3 | 134,697 | 3 |
| WARCRY | 198 | 0 | 3,150 | 0 |
| **Total** | **226,432** | **37** | **2,081,955** | **32** |

## Correctness and interpretation

The focused `silver_search_optimization_test` passed, including the required
two-target Headbutt fixture (four canonical macro choices), one-option A
resolution, final-state/RNG equality, stochastic-parent rejection, the True
Grit+/Dead Branch stochastic-continuation regression, unsupported task
fallback, Hologram guard, and `getBestAction()` compatibility. All six
corrected Release replays completed with 64/64 `status=ok` rows and zero replay
failures.

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
| `control-1k.jsonl` | `2328546cf175bc40d17964b3aa7ba1f3ed28b5601d06bcf2ccd12597b42f497d` |
| `arm-A-1k.jsonl` | `2211f33fa8f1e90af6f9503fb6bb07f0309c4cc8d2c8f63b6abae09e01532689` |
| `arm-B-1k.jsonl` | `951d85f96138cfb0d0852dfbc95de245c73e2f6da6f035874018ed51cfa18dcf` |
| `control-10k.jsonl` | `94f2d6f12a7fcdd7af64d2bb0a150ca54e64c6a712c125609c0987c28909e1fa` |
| `arm-A-10k.jsonl` | `e32b72208318431d7c84e009e1d498ab0d270634ce674f2f502497eed7c4c3a6` |
| `arm-B-10k.jsonl` | `11fa4f2db8093f9ef8d7e5093636e73bd06ccd2dc0997ea3e9a010239b1a0ce8` |

Knowledge impact: durable experiment evidence and current interpretation; no
production behavior, default promotion, or benchmark gate changed.
