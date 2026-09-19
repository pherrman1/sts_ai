# Silver stochastic UID-chance merge screen

Baseline: `1b2207125b2737d6af41f27b314678bcc8f561bb` (merged PR #244).
The candidate is the final reviewed implementation commit recorded in the
draft PR for this packet. The Release replay executable SHA-256 was
`097fbad496099213c3384b06ee2073f2f32ef0a546188e28dd3577646bb3379e`.

This is an opt-in research treatment. `SilverSearchConfig::uidChanceMergeEnabled`
defaults to false, no live environment variable enables it, and the normal
Silver path remains exact. No HOLDOUT was run.

## Treatment contract

Only decision states produced by stochastic outcomes may use the treatment.
The exact hash/probe path and `equalForSearch()` remain unchanged. After an
exact miss, a same-hash existing node is eligible only when:

- the PR-244 diagnostic comparator reports equivalent;
- both hand and unknown-draw regions differ;
- both states are `PLAYER_NORMAL`; and
- the physical-card union across hand plus unknown draw is identical by
  unique ID and exact `CardInstance` value, with nonnegative unique IDs and no
  duplicate ID in either union.

Deterministic insertion, known draw positions, discard/exhaust, limbo/stasis,
queues, selectors, special-data cards, and per-copy transient properties remain
exact. Exact matches retain priority over a remembered relaxed candidate.

## Focused verification

`build/linux-gcc-debug-ccache/silver_search_optimization_test` passed. It
covers the pure swap, different physical UID set, per-copy cost reassignment,
special-data and `CARD_SELECT` exclusions, default-off diagnostic parity, and a
fixed-RNG `POMMEL_STRIKE` draw fixture. The draw fixture used identical sampled
outcomes in control and treatment; treatment contracted decision nodes and
recorded relaxed merges. The destination split reconciled every merge as
sibling reuse or global transposition.

The existing PR-244 diagnostic assertions also remain in that focused test.
The default-off arm showed identical action/RNG/ordinary telemetry behavior to
the diagnostic-enabled observation arm, with all treatment counters zero.

## Frozen DEV screen

Both arms used the same Release GCC executable source, `OMP_NUM_THREADS=4`,
`hard64-dev-snapshots.jsonl`, 1,000 simulations per decision, the existing
fixed replay configuration, and the same case order. Control ran with
`--uid-chance-merge` absent; treatment ran with `--uid-chance-merge`. Both
arms completed 64/64 rows with status `ok`.

| Metric | Control all64 | Treatment all64 | Control top10 | Treatment top10 |
|---|---:|---:|---:|---:|
| Wins | 51/64 | 52/64 | 9/10 | 9/10 |
| Mean terminal HP fraction | 0.344091 | 0.358247 | 0.268147 | 0.289056 |
| Decisions | 2,232 | 2,246 | 416 | 400 |
| Simulations | 2,232,000 | 2,246,000 | 416,000 | 400,000 |
| Nodes created | 2,063,754 | 2,079,940 | 390,167 | 373,736 |
| Nodes / simulation | 0.924621 | 0.926064 | 0.937901 | 0.934340 |
| Wall seconds (`/usr/bin/time` real) | 15.77 | 15.90 | 2.972630 | 3.043350 |
| Exact reroots | 1,627 | 1,613 | 306 | 288 |
| Reroot fallbacks | 541 | 569 | 100 | 102 |

The all64 nodes/simulation change was **+0.156%**, not a reduction. The
predeclared top-10 node/simulation change was **-0.380%**, below the 5%
promising threshold and the 2% reject threshold. Wall time was approximately
**0.82% slower**, below the predeclared 2% repeat trigger, so no extra
timing passes were collected. Treatment action traces differed on 53/64
all64 cases and 9/10 top-10 cases. Exact reroots fell by 14 all64 and 18 on
top-10; fallbacks rose by 28 all64 and 2 on top-10.

Treatment-only telemetry:

| Metric | All64 | Top10 |
|---|---:|---:|
| Sampled chance outcomes | 2,317,751 | 484,492 |
| Actual relaxed merges | 205,514 | 99,967 |
| Merge rate / sampled outcome | 8.866958% | 20.633364% |
| END_TURN / CARD / OTHER | 116,136 / 78,223 / 11,155 | 76,779 / 21,582 / 1,606 |
| Sibling reuse / global transposition | 193,678 / 11,836 | 94,172 / 5,795 |

The result is **`SILVER_UID_CHANCE_MERGE_REJECT`**: strict merges were common,
but they did not reduce all64 work, did not reach the predeclared top-10
benefit threshold, were slightly slower, and measurably reduced exact reroot
success. This is a value-of-pursuing-canonicalization result, not a production
promotion gate. The treatment remains default-off pending review; no
identity-canonicalization follow-up is authorized by this screen.

## Raw artifacts and provenance

Commands were run through `tools/seed_guard.sh`:

```text
OMP_NUM_THREADS=4 bash tools/seed_guard.sh \
  build/linux-gcc-release-ccache/silver_hard_combat_replay \
  docs/experiments/evidence/silver_hard_combat_v1_20260918/hard64-dev-snapshots.jsonl \
  1000

OMP_NUM_THREADS=4 bash tools/seed_guard.sh \
  build/linux-gcc-release-ccache/silver_hard_combat_replay \
  docs/experiments/evidence/silver_hard_combat_v1_20260918/hard64-dev-snapshots.jsonl \
  1000 --uid-chance-merge
```

| Artifact | SHA-256 |
|---|---|
| [control.jsonl](control.jsonl) | `c38f777784b5dd0eee22530bfc795c04830fafcfbd061520f52e16a5a5ea7c58` |
| [treatment.jsonl](treatment.jsonl) | `f66213866eb1fab4acb3f33b0fbaae2e878e706dbabe28ed63a932b2e84250f6` |
| [control.time](control.time) | `84c27ccc009a96745dff272faa10cb7f3963541d969221b8584ef9a95b188b4b` |
| [treatment.time](treatment.time) | `e7b13b17d3766325c50cb5b8450baa67a915f392c0bda1336d5b49587a17e007` |

Knowledge impact: durable experiment evidence only; no production default,
live boundary, model, RNG, or semantic-schema change.
