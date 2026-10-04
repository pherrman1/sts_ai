# OOC MCTS reroot opportunity (issue #339, Phase A, measurement only)

## Contract and provenance

- Source: `f330b7dc98526774559e2f038cdc49b454708125` (base `main`
  `8ce8565a38500b49a23372c926b9c6d5e6130d9a` plus the opt-in observer only).
- Binary: release `linux-gcc-release` preset, `one_combat` SHA256
  `64c9df5e2782fccfde89830d52cc8a5503f7ea2d65702246c47b8b339633d52c`.
- Models (SHA256): CTM `combat_transition_near_full_except_smoke_v2.native`
  `e9a18951…e0ddfd`; V4 `ooc_strategic_tok_final.native` `e62abd83…1184c`;
  `v_win_trees.txt` `fc52c14c…67ad70`; `v_rich_trees.txt` `3a342046…ffe3`.
- Workload: the 2026-09-18 OOC CPU-profile workload ([evidence](../ooc_cpu_profile_2026-09-18/README.md)), seeds
  **12002032 and 12002033**, once each, through `tools/seed_guard.sh`. Ironclad
  A0, project-fair, keys off, Act-3 stop, flat 10k native Silver, OOC 2048 /
  cPuct 1.5 / widening 2, 0.5 / current default max depth 512 / policy prior,
  temperature 1 / visit selection / early stop / native leaf / zero leaf
  combats / V4 continuation / full strategic gates / margin 1, `OMP_NUM_THREADS=1`.
  Exact environment: [`run.sh`](run.sh) (the `/tmp` output paths are the
  original scratch locations). `STS_SILVER_TELEMETRY` and
  `STS_SILVER_REUSE_CAP` were dropped from the historical receipt because
  ADR-0022 rejects them.
- No fresh seeds, training, model or policy changes.

## Observer

`STS_OOC_MCTS_REUSE_TRACE=<fresh.jsonl>` captures each completed live search
tree (node cap 100,000; no capture was truncated) and fingerprints every stored
decision node. At the next real OOC decision the real root's fingerprint is
matched against that index. Singleton-bypass decisions are also matched but keep
the earlier index, so forced chains are measured against the last real search.
An aborted search clears the index.

Two identities are recorded:

- **public**: all state the sampled live search holds fixed, i.e. the
  `oocStateFingerprint` fields and `PathHistory`, minus what
  `sampleNoncombatFuture` re-determinizes at every transition: stream seeds,
  pool order (pools compared as sets), the unrevealed normal/elite encounter
  suffix, the A20 second boss, hidden chest contents and unsearched Dead
  Adventurer rewards. Native room/potion/rarity counters are kept.
- **rng**: public plus the 14 RNG stream draw counters.

The observer is read-only. Trace-off reruns of both seeds with the same binary
give byte-identical `actions.jsonl` and every non-timing column of the MCTS CSV
identical (`*.trace_off.*`). Observer overhead was +9.6% and +8.6% MCTS CPU
(fingerprinting), which is irrelevant to the measured counts.

## Results (273 real OOC decisions: 162 searched, 110 singleton, 1 abort)

Full output: [`analysis.txt`](analysis.txt) from
`tools/analyze_ooc_reuse_trace.py`.

| Identity | Searched decisions matching the selected branch | Depth 1 / 2 / 3+ | Best single node visits (median / max) | Retained / all searched simulations |
|---|---:|---:|---:|---:|
| rng | 0 / 159 | — | — | 0% |
| public | 94 / 159 (58%) | 60 / 25 / 9 | 30 / 42 | **0.90%** |

Including singleton decisions, 198 / 268 decisions with a previous search match
publicly (72.5%). No match ever crosses a real combat; every searched miss
follows a floor/room transition (map → room, room → next map). Among public
hits, 24 passed through a chance node with more than one distinct public
outcome.

**Why RNG identity never matches.** Sampling itself advances the counters:
`sampleNoncombatFuture` redraws the unrevealed encounter suffix from
`monsterRng`, so every stored particle's `monsterRng`/`neowRng` counters differ
from the real state's (for example 35 real versus 64–79 in stored particles at
the first Neow decision). Exact full-state reuse is therefore never available.

**Why public hits retain little work.** In sampled mode every visit to a chance
node may create a fresh independent particle (`ceil(2·N^0.5)`), even when the
public outcome is deterministic. A matched real successor corresponds to a
median of **64** publicly identical sibling particles, each with about √N/2
visits. Rerooting to one particle keeps a median of 30 visits: 1.4% of a 2048
budget at the matched decisions, 0.90% of all searched simulations.

Upper bound, not an allowed mechanism: summing the visits of all publicly
identical particles on the selected branch would give 26.6% of searched
simulations (median 875 visits, about 40% of a 2048 budget at hit decisions).
Reaching that requires merging independent particles, i.e. belief-state or
transposition reuse, which issue #339 excludes without separate evidence.

## Decision

Per the issue's decision rule, **direct selected-branch rerooting is not
implemented**: exact (RNG) opportunities never occur, and public-identity
single-node rerooting retains under 1% of search work. No persistent-tree code
is added. The observer stays for future measurements.

**Open question:** whether collapsing publicly deterministic sampled
transitions into one particle (or merging identical public particles) is
semantically sound. That changes search semantics and hidden-counter
handling, and needs its own design and evidence.

## Checks

- Measurement runs: 4 guarded runs (2 seeds × trace on/off), exit 0.
- `ooc_mcts_live_startup`: fails on pristine `main` 8ce8565 at the
  pre-existing `oocmctsselftest` case "old sole wheel search reaches
  unsupported combat and aborts" (verified with a `baseline_build.py` binary);
  not caused by this change. The two new startup cases (unwritable reuse trace,
  reuse+graph rejection) were checked manually with the same command form.
