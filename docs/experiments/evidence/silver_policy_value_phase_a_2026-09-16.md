# Silver policy/value Phase A diagnostic — 2026-09-16

This is an offline engineering diagnostic. It does not train a model, load a
new model, change gameplay, change Silver action selection, or redesign the
terminal utility.

## Binding and scope

- Requested baseline SHA: `77fec051c2453d79f05bad5e813989b861fa5d0a`
- PR base SHA at the final correction: `3f8ca7b59c2de1ba78a2d8bab0f280f849dd6845`
- Experiment implementation SHA: `71d669a5779e3180f679dfd15301c6f371d9a11b`
- Upstream Silver SHA: `84ab3ead9d88c01c4be09a6773fb9a947f57d5ff`
- Source executable Git SHA recorded in the run metadata: the experiment
  implementation SHA above
- Supported input: visible `PLAYER_NORMAL` combat state only
- Candidate contract: one shared state encoder, one scalar value, and all
  currently legal Silver sibling actions
- Canonical widths: 1,766 state features plus 22 action features = 1,788
  canonical policy features
- Prospective model input: the 1,766 canonical state features plus exact
  isolated-Silver root effective gold and root max HP = 1,768 state inputs
- Utility: existing `BattleSearcher::evaluateEndState`, with the original root
  retained as teacher-only reference context and existing gold/maxHP
  root-relative weights (`0.25`, `2.0`)

The converter writes separate `parent_policy` and `leaf_value` records. A
parent policy record contains no child utility label. A value record uses the
teacher utility from that same actual rollout leaf and preserves its incoming
semantic action fingerprint; it never substitutes a parent or first-child
label. Hidden pending-intent fields and interpreter/provenance-only fields are
redacted before feature extraction. The canonical projection remains
explicitly lossy for draw order, some card-instance metadata, per-monster
detail, card-select/queue context, and full relic-counter detail.

## A1 — full Silver rollout cost and supported-leaf coverage

Run artifact directory:
`build/phase_a_final_omp1/`. The guarded source command was:

```text
OMP_NUM_THREADS=1 STS_FAIR=1 STS_SEARCHER3=0 STS_SILVER_SEARCH=1
STS_SILVER_EXACT_ROOT_BUDGETS=1 STS_SILVER_REUSE_CAP_MODE=none
STS_SILVER_ADAPTIVE=0 STS_SILVER_VNET_LEAF_DIRECT=0 STS_NATIVE_OOC=1
STS_SILVER_TELEMETRY=1 STS_SILVER_LEAF_CORPUS=.../source.corpus.jsonl
STS_SILVER_LEAF_CORPUS_GROUP_MODULUS=1
STS_SILVER_LEAF_CORPUS_MAX_PER_GROUP=16
STS_EXECUTABLE_GIT_SHA=71d669a5779e3180f679dfd15301c6f371d9a11b
bash tools/seed_guard.sh .../one_combat bestbench 100 8 0 100 .../source.csv
```

The run used seeds `100..107`, Release `one_combat`, exact 100 simulations
per decision, fair Silver, reuse-cap mode `none`, and one worker thread. The
raw timing output is preserved in `source.log`; its SHA-256 is listed below.
There were 169 per-combat telemetry summaries and no telemetry, conversion,
semantic, transaction, or knowledge failures.

The full-search denominator is the sum of the raw `[silver-combat]` telemetry
lines, not the sampled corpus:

| Metric | Result |
| --- | ---: |
| decisions / simulations / rollout calls | 3,334 / 333,400 / 315,816 |
| total search wall | 145.152346 s |
| total rollout wall | 76.768818 s |
| rollout wall fraction | 52.8893% |
| `PLAYER_NORMAL` rollout calls | 290,326 (91.9288% of rollout calls) |
| `PLAYER_NORMAL` rollout wall | 71.752385 s (93.4655% of rollout wall) |
| `PLAYER_NORMAL` rollout wall / total search wall | 49.4325% |
| `PLAYER_NORMAL` call-weighted mean | 247.144 µs |

The rollout-start input-state mapping is `0=EXECUTING_ACTIONS`,
`1=PLAYER_NORMAL`, `2=CARD_SELECT`, and `3..9=other/unused` for this run:

| Input state | Calls | Wall micros |
| --- | ---: | ---: |
| `EXECUTING_ACTIONS` (0) | 6,117 | 313.388 |
| `PLAYER_NORMAL` (1) | 290,326 | 71,752,384.900 |
| `CARD_SELECT` (2) | 19,373 | 5,016,105.890 |
| 3..9 | 0 | 0 |

The corpus contains 127,797 rows across 17,158 complete groups. It is a
sampled observation artifact, not the full denominator: 116,696 rows are
`PLAYER_NORMAL` leaves and 11,101 are `CARD_SELECT` leaves. The sampled corpus
has no state-0 rows because the complete-group capture selects rollout leaves
at supported decision parents. Its state-1 action count was
`14.704 / 12 / 30 / 48` mean/median/p90/p99 (range 1..80), with turn delta
`2.689 / 2 / 6 / 10` (range 0..18). State 2 was
`20.395 / 17 / 39 / 59` actions (range 2..78), with turn delta
`3.617 / 3 / 7 / 11` (range 0..15). The full telemetry values above, rather
than these sampled row counts, are used for the break-even calculation.

## A2–A4 — contract and representative examples

`apps/silver_policy_value_phase_a.cpp` writes
`silver_policy_value_phase_a_v2` JSONL. The selected artifact contains 16
`parent_policy` records and 16 `leaf_value` records. Parent records contain
the exact legal sibling set in Silver order, semantic card/potion/select/target
identity, unique fingerprints, 1,766 canonical state features, and the two
root reference scalars. Leaf records contain the actual visible leaf state,
the same 1,766 canonical features plus the two scalar inputs, the leaf's
incoming action fingerprint, and its own `utility_original_root` label. The
header records the sampled coverage and both record counts.

The original root state remains under `root_reference_context.teacher_only`.
The derived effective-gold and max-HP scalars are the only root context passed
to the prospective model input; the full root snapshot is not a model feature.

## A5 — native synthetic CPU benchmark

Binary: `silver_policy_value_phase_a`, Release, `OMP_NUM_THREADS=1`. The
benchmark uses the selected actual supported `PLAYER_NORMAL` leaves, not a
synthetic zero state. Its fixed weights are deterministic and its checksum is
accumulated from every value and every legal-action logit, with the result
observed in the JSON output to prevent dead-code elimination.

The timed region is visible leaf wire materialization, canonical feature
preparation, exact root scalar derivation, one shared `1768 -> 64 -> 64`
ReLU encoder, `64 -> 1` value head, and all legal `[64,22] -> 32 -> 1`
action scores.

| Metric | Result |
| --- | ---: |
| examples / iterations / calls | 16 / 200 / 3,200 |
| action scores | 13,000 |
| call mean / median / p90 / p99 | 123.434 / 119.679 / 141.623 / 160.248 µs |
| calls/s / action scores/s | 8,101.50 / 32,912.34 |
| legal actions mean / median / p90 / p99 | 4.0625 / 4 / 6 / 6 |
| observed checksum | `127.37751752097392` |

## End-to-end break-even calculation

The candidate mean is compared with the full-run call-weighted
`PLAYER_NORMAL` rollout mean:

```text
replaceable_rollout_wall = 290,326 * 123.43394 us
                       = 34,895,301.07 us

estimated_search_wall = 145,152,345.90 - 71,752,384.90
                        + 34,895,301.07
                      = 109,236,043.06 us

estimated_reduction = 1 - 109,236,043.06 / 145,152,345.90
                    = 24.7439%
estimated_speedup = 1.3288x
candidate / PLAYER_NORMAL rollout mean = 0.4994x
```

Thus the bounded engineering classification is **`PV_COST_FEASIBLE`** for
this machine, source configuration, and representative supported-leaf
sample. This is a cost classification only; no action-ranking quality,
terminal-label quality, hidden-state sufficiency, or gameplay benefit has
been established.

## Provenance and hashes

Hardware/software identity:

- CPU: AMD Ryzen 5 7500F 6-Core Processor, 1 socket, 6 cores, 2 threads/core
- OS/kernel: Linux x86_64, kernel `7.1.5-76070105-generic`
- Source run: one worker thread; candidate benchmark: one thread

| Artifact | SHA-256 |
| --- | --- |
| Release `silver_policy_value_phase_a` | `fbd340962c227d0db4bd58d99334a73ccadddad673843e29cc4a803893411f0e` |
| `source.corpus.jsonl` | `f19f012bc0acc9c7bac517de7d4270a85a00fde4d7d2967fc9e18f41bed2a843` |
| raw telemetry/timing `source.log` | `2299aa893a97f0297e5c700e3aa0bb227776ea69e88bb4404985a3b94b043660` |
| source results `source.csv` | `6ea1355f9cedec5819b4886d7ce471f3eeffd907c53706f0d86e2319efbcf3ba` |
| source metadata `source.csv.meta.json` | `639bc6b1ea335a7623724ab76dfe7c145eef54066d29dfabad72550788326a41` |
| selected examples `examples.jsonl` | `5a8bd180628ccc0d221c63f738e5e5c8707253698aed13b5fca993b44a08d20f` |
| benchmark JSON `benchmark.json` | `3fd886df7623739451fc2c9a0e428346585985962d6447743d4650855f3ec9fd` |

The source run and benchmark artifacts are generated build outputs and are
intentionally not committed. The implementation SHA, executable hash, source
corpus hash, selected-example hash, benchmark hash, raw timing-log hash, and
hardware identity above make the uncommitted evidence reproducible and
reviewable.

## Verification and boundaries

- Release build passed for `silver-policy-value-phase-a`, `one_combat`,
  `silver-native-test`, `silver-bridge-test`, and `unit-test`.
- Focused native CTest passed 4/4:
  `silver_random_bridge`, `silver_semantic_action`,
  `silver_searcher_link_closure`, and `silver_bridge_boundary`.
- The final source run went through `tools/seed_guard.sh` and stayed below the
  local 128-seed ceiling.
- The diagnostic-off path remains default-off; no search policy, model loading,
  utility, RNG, or gameplay default changed.
- GitHub Actions `Linux GCC` is the authoritative post-push check and must be
  read back for the final PR head.
- Remaining uncertainty: the canonical projection is intentionally lossy, the
  sample is bounded and corpus-provided, root scalar materialization is not yet
  runtime integration, and this does not qualify predictor quality or a
  gameplay gate.

Knowledge impact: the maintained policy/value contract, corrected 1,788
feature arithmetic, and Phase-A engineering evidence were updated; runtime
defaults and research qualification remain unchanged.
