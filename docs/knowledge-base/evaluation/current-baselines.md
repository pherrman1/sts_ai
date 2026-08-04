# Current baselines

Last verified: 2026-08-03 against commit `6f5a157` and the current working tree.

## Purpose

Provide the single concise source for the current executable configuration,
headline reference, and nearest historical/experimental comparators. Numbers
elsewhere should link here rather than be copied as changing baselines.

## Current implementation

The present executable defaults to native floor/win OOC inference, card skip
`-0.5`, heuristic pathing, shop value, win-shaped rest, Searcher2, and the
tracked compact policy prior when it loads (`apps/one_combat.cpp::main`,
`runFullRunOOC`). The one-ply Q gate stack (cards/rest/events/shop/treasure/
boss relic) is **opt-in** via `STS_OOC_STRATEGIC_*` env flags + a model
artifact; the binary default plays without it. `STS_FAIR=1` must be set explicitly for a project-fair run.
`STS_SEARCHER3=1` and `STS_PVNET=<path>` are experimental opt-ins; PVNet is
consumed only by Searcher3.

## Baseline table

| Status / date | Seeds | Ascension | Combat budget | RNG / searcher | OOC and combat models | Metric and result |
| --- | --- | ---: | ---: | --- | --- | --- |
| **Current executable configuration**, verified 2026-07-31 | Caller-selected | Caller-selected | Caller-selected | Default Searcher2 is known-RNG unless `STS_FAIR=1`; opt-in Searcher3 samples particles in either path and `STS_FAIR` controls rebuild/reuse | Native tracked floor/win trees; heuristic path; shop-V; win-rest; tracked policy prior auto-load; no combat value/PVNet by default | Configuration only; **no current-checkout full-run measurement is claimed**. |
| **Recommended configuration — one-ply gate stack**, 2026-08-03 (`EXPERIMENTS.md` §82) | 126700–126827 (128); also 126700–126955 (256) | 0 | 1,000 sims/decision | `STS_FAIR=1`, default Searcher2, 12 threads | Native tracked floor/win trees; heuristic path/shop/win-rest; **plus the opt-in one-ply Q gate stack** (`STS_OOC_STRATEGIC_NN=selfplay/models/ooc_strategic.native`, `REST/EVENT/SHOP/TREASURE/BOSS_RELIC=1`, `STS_OOC_STRATEGIC_MARGIN=1.0`) | Full Act-3 run win: **51/128 (39.8%)** on the 128 block (reference CSV `build/gates_ref_m1.csv`, bit-identical to §76 m1.0); **95/256 (37.1%, +14.1pp vs the 23.0% flags-off baseline)** on the 256 block (`build/sec256_gate_m1.csv`). Margin 1.0 is the operating point (§82 sweep). **Future gate rounds pair against this reference.** |
| **Experimental top arm — V4 token net + gate stack**, 2026-08-03 (`EXPERIMENTS.md` §81) | 126700–126827 (128) | 0 | 1,000 sims/decision | `STS_FAIR=1`, default Searcher2, 12 threads | V4 token net (`STS_OOC_STRATEGIC_TOK_NN=…ooc_strategic_tok_final.native`, opt-in) + full gate stack @ m1.0 | Full Act-3 run win: **53/128 (41.4%)**; ~3.5× slower per run (27 vs 8 cpu-sec/run). |
| **Current default stack on the recorded block** (default binary, no opt-ins), 2026-08-02 (`EXPERIMENTS.md` §68) | 126700–126827 (128) | 0 | 1,000 sims/decision | `STS_FAIR=1`, default Searcher2, 12 threads | Native tracked floor/win trees (hashes in §68); heuristic path/shop/win-rest; tracked policy prior auto-load; no combat value/PVNet | Full Act-3 run win: **27/128 (21.1%)**; mean floor 37.5; mean end HP 8.6; per-seed CSV retained at `build/bench_2026-08-02_default_fair.csv`. New measurement, not a paired comparison with §66i. |
| **Primary recorded project-fair reference**, 2026-07-23 (`EXPERIMENTS.md` §66i) | 126700–126827 (128) | 0 | 1,000 sims/decision | `STS_FAIR=1`; **Unverified** exact searcher in the historical binary, consistent with default Searcher2 | Native floor/win OOC; heuristic path/shop/win-rest; entry says PUCT/V-combat but names no combat-value path/hash and does not pin every flag | Full Act-3 run win: **39/128 (30.5%)**; mean floor 40.32; mean end HP 11.91. Raw cited directory is absent, so not exactly reproducible; the §68 re-measurement suggests a different historical configuration. |
| **Historical known-RNG comparator**, 2026-07-15 (`EXPERIMENTS.md` §26) | 512 seeds; range not recorded | 0 | 1,000 sims/decision | Known-RNG Searcher2 with PUCT | Server-backed rich V2 floor drafting/shop, win-rest, heuristic path, compact policy prior | Full-run win: **51.6%**. Optimistic diagnostic; never compare directly with the fair reference. |
| **Recorded Searcher3/PVNet experiment**, 2026-07-30 (final ledger section) | 128 seeds; range not recorded | 0 | 50/100/250/500 | Recorded as Searcher3 project-fair PUCT | Ledger says “heuristic OOC baseline + PUCT (GBM policy)” but does not define that OOC stack; opt-in `build/v_combat_pvnet.txt`; policy-only means `STS_PVNET_ALPHA=0` | Full-run win-rate sweep. Best reported 100-sim policy-only point: **66.4%**. **Re-checked 2026-08-02 on the recorded 126700–126827 block: 8.6% at 100 sims (α=0), 5.5% (α=1.0) vs 4.7% same-budget default — the 66.4% headline does not reproduce (EXPERIMENTS.md §72)**; treat the sweep numbers as historical. |

The older 62.3% at 3,000 simulations is also a known-RNG §26 result. Historical
20,000-simulation data shows UCB above PUCT; the claimed 6,000–10,000 crossover
was an interpretation without paired UCB points throughout that interval.

## Important data flow

A baseline is defined by source revision, executable mode, environment, model
artifacts, seed block, simulations, ascension, searcher, and metric. Startup
messages establish which optional artifacts loaded; `bestBench` then records
one row per seed. The table above separates configuration identity from measured
historical evidence.

Current tracked artifact identities:

```text
build/v_rich_trees.txt    sha256 3a3420469b1d648e0e306d6cb6a7e85f3d3499105e3ff3a56eee6c579194ffe3
build/v_win_trees.txt     sha256 fc52c14cb7239a33b3c1f9d0477ccb6c895fd51a07240fe804744e605067ad70
build/policy_trees_c.txt  sha256 24793bd39dd1a35c8865035e458c3aa40616ef021cb26b05f914f72fb5e5a321
build/v_combat_pvnet.txt  sha256 05d809298921623af7c87c06e7dd31f5129abfd77cc702f75b9867949a59533f
```

These hashes identify the current tracked files, not the unavailable historical
artifact set behind §66i.

## Invariants and assumptions

- “Current executable configuration” is not a measured benchmark.
- Project-fair and known-RNG results are separate regimes.
- Default and experimental/opt-in configurations are separate statuses.
- Re-running historical seeds with different artifacts or defaults creates a
  new measurement.
- `bestbench` writes `won` from `GameOutcome::PLAYER_VICTORY`. The simulator
  normally sets this after Act 3, but proceeds to Act 4 when all three keys were
  obtained; `STS_STOP_AFTER_ACT` defines a separate scoped success.

## Known limitations

- The primary fair result cannot be exactly reproduced from tracked artifacts.
- The current checkout has no fresh benchmark proving the current default stack
  equals or exceeds the primary reference.
- Fair-play is partial hidden-information handling, especially under Searcher2.
- The PVNet sweep omits a recorded seed range and exact full command, and its
  “heuristic OOC baseline” label is not a reproducible policy definition.
  The 2026-08-02 re-check (§72) on the recorded block did not reproduce the
  66.4% headline (8.6% at 100 sims, α=0).
- Current Searcher3 expansion calls `computeEdgePriors` only when the separate
  policy net is loaded. PVNet policy evidence therefore also depends on that
  enabling condition even though PVNet supplies the logits.
- The tracked PVNet's training data is described as fair, but the archived
  producer invocation records `STS_SEARCHER3=1` without `STS_FAIR=1`, and the
  raw dataset is not tracked. The project-fair integration provenance is
  therefore unverified.

## Open questions

- Which exact artifact hashes and flags produced the 39/128 result?
- Should a reproducible baseline bundle include executable/model hashes and
  captured startup output?

## Relevant code

- `apps/one_combat.cpp::main`, `runFullRunOOC`, `bestBench`
- `src/sim/search/ScumSearchAgent2.cpp::playoutBattle`
- `src/sim/search/BattleScumSearcher2.cpp::determinize`
- `src/sim/search/BattleScumSearcher3.cpp::g_useSearcher3`
- `src/sim/search/CombatPVNet.cpp::g_pvnetAlpha`
- `EXPERIMENTS.md` §26, §66i, and “Phase 4b PVNet alpha sweep”
- tracked artifacts under `build/`
