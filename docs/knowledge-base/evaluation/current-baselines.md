# Current baselines

Last verified: 2026-08-11 against the current working tree (tracked model
artifacts relocated from `build/` to `models/`; V4 token-net artifact =
skewfix §149 model; §148 V_combat leaf = 7k-tuned; Act-4 keys now collected by
default — pre-32281a2 baselines are Act-3-only).
Experiments invalidated by fixes are tracked in the
[rerun ledger](rerun-ledger.md) (2026-08-05 code review, issues 31–46); the
**2026-08-05 §113 battle-skip exploit invalidates every Searcher3 measurement
using the pre-fix (619c12c) enumerator (§107, §111, §112, and the S3 arms of
§99–§105)**; the current recommended row below is the honest §113 re-baseline
on the same 256-seed block. The V4@3k Searcher2 result (§99) is unaffected.

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
`STS_SEARCHER3=1` and `STS_PVNET=<path>` are experimental opt-ins; `STS_PVNET`
adds policy-head priors to default Searcher2 since 2026-08-05 (value leaf is
Searcher3-only), and `STS_DIST_VNET` is consumed only by Searcher3.
Per-encounter combat value specialization (`STS_VNET_PER_ENCOUNTER=<dir>`
per-boss tree overlay, `combat_mlp_meta_v1` in-file deltas from the Reptile
meta-learner) is an experimental research arm implemented 2026-08-09
(`train_value_combat_per_encounter.py` / `train_value_combat_meta.py`), NOT
promoted to any default; the deployed vnet stays the §148 tuned pooled model.
Since 2026-08-06 the project-fair Searcher2 path includes the **forced-move
contraction by default** (exactly-one-legal-action commits without searching;
`STS_FORCED_MOVE=0` disables). It is decision-neutral — two independent
256-seed gates show exact per-seed outcome equality at −16-18% cpu
(EXPERIMENTS.md §120/§121) — so all headline numbers above remain valid.
Since 2026-08-07 the **Searcher3 fair path includes both the forced-move
contraction (confirmed decision-neutral at the §123 S3 gate, 0/256 diffs,
−8.5% cpu) and the STS_LIVE_VALID fair-tree fix by default** (live-valid
edge re-selection; §122 + §123 gates: +5.5pp and +5.9pp win at +7.9% and
+14.6% cpu — the recorded cpu-trade call accepts that cost; `STS_LIVE_VALID=0`
disables). The §113 headline (44.5% @3k) was measured before the live-valid
default flip and remains valid as recorded; a full-stack re-measurement with
the new default is an open follow-up. `STS_CONV_ROOT`, `STS_ROLLOUT_CAPS`,
and the non-fair forced-move variant remain opt-in (falsified at the gates,
§118/§119). Since 2026-08-07 (EXPERIMENTS.md §124/§126) the **Searcher3 fair
path loads a combat value leaf by default** — first the fresh honest-data
804-tree vnet `build/v_combat_honest.txt` at α=0.3 (§126: three significant
paired gates +12.5/+12.1/+12.5pp win at ~2-2.4× cpu; the §126 recorded
cpu-trade call), then promoted to `models/v_combat_7k_tuned.txt` (1000 trees,
§148, 2026-08-09 — the honest model is superseded; `STS_VNET=<path>` overrides,
`STS_VNET=<missing-path>` disables, and the S2 fair / non-fair paths stay
env-only). The §124 re-measurement on the
current binary confirmed the recorded references (flat @1k, +2.3pp n.s.
@3k/256p) and re-confirmed S3−belief−chain as the particle config (belief+
chain ON costs −11.3 to −12.1pp, significant).

**Since 2026-08-09 (commit `32281a2`) the agent collects Act-4 keys by
default** (emerald/sapphire at rewards screens, ruby at rest sites when
act ≥ 3). Every baseline measured before this commit (all entries below
marked "Act-3 run win") reflects Act-3-only wins — the agent never entered
Act 4. Current binary wins require clearing the Heart. Use
`STS_STOP_AFTER_ACT=3` to approximate the pre-commit Act-3-only horizon
(keys are still collected, so it is not bit-identical to the pre-commit
binary).
## Baseline table

| Status / date | Seeds | Ascension | Combat budget | RNG / searcher | OOC and combat models | Metric and result |
| --- | --- | ---: | ---: | --- | --- | --- |
| **Current executable configuration**, verified 2026-07-31 | Caller-selected | Caller-selected | Caller-selected | Default Searcher2 is known-RNG unless `STS_FAIR=1`; opt-in Searcher3 samples particles in either path and `STS_FAIR` controls rebuild/reuse | Native tracked floor/win trees; heuristic path; shop-V; win-rest; tracked policy prior auto-load; no combat value/PVNet by default | Configuration only; **no current-checkout full-run measurement is claimed**. |
| **Recommended configuration — V4 skewfix one-ply gate stack + hyperparameter-tuned V_combat leaf @α=0.3 (7k data)**, 2026-08-09 (§153, GCP sts-test) | 126700–126731 (32) | 0–20 | 1,000 sims/decision (efficient point, 64p); 3,000 sims/decision (win point — not yet measured at this stack) | `STS_FAIR=1`, **Searcher3 with `STS_S3_BELIEF=0 STS_S3_CHAIN=0`** (`STS_S3_PARTICLES=64`), 24 threads | V4 skewfix token-net gate stack (§149, `STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_final.native` sha256 `e62abd83…`, all gates ON, margin 1.0); **`STS_VNET` default ON in the fair-S3 path**: `models/v_combat_7k_tuned.txt` (1000 trees, sha256 `ea35b78c…`, α=0.3) | **Full Act-3+4 run win (current binary default, Act 4 reachable):** A0 **21.9%** (7/32), A5 12.5% (4/32), A10 12.5% (4/32), A15 9.4% (3/32), A20 0.0% (0/32). No-gates baseline: A0 0/32 (but 6.3% across 64 seeds). Act-3 only (`STS_STOP_AFTER_ACT=3`): gates ON 31.2% (10/32), gates OFF 37.5% (12/32 — reproduces §148). V4 gates hurt Act-3 (−6.3pp) but are essential for Act 4 (+15.7pp). See §153. **A0 headline: 21.9% with Act 4; 31.2% Act-3-only.** 32 seeds only — CIs are wide (A0 Wilson 95%: [9.9%, 40.4%]). Full 128/256-seed gate and 3k win point are open follow-ups. |
| **Previous recommended configuration — canonical CARD_SELECT enumerator + `exitBattle` UNDECIDED guard + expanded observation identity + V4 one-ply gate stack**, 2026-08-05 (`EXPERIMENTS.md` §113, §114, §115; re-measured 2026-08-07 §124) | 126700–126955 (256) | 0 | 3,000 sims/decision (win point, 256 particles); 1,000 sims/decision (efficient point, 64 particles) | `STS_FAIR=1`, **Searcher3 with `STS_S3_BELIEF=0 STS_S3_CHAIN=0`** (`STS_S3_PARTICLES=256` or 64), 24 threads | V4 token-net gate stack (`STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_final.native`, `REST/EVENT/SHOP/TREASURE/BOSS_RELIC=1`, `STS_OOC_STRATEGIC_MARGIN=1.0`); canonical CARD_SELECT enumeration (issue 47) + `BattleContext::exitBattle` UNDECIDED→LOSS guard (issue 48) + `CombatObservation` decision-context identity (§114); no combat value/PVNet | Full Act-3 run win on the current binary: **114/256 (44.5%)** at 3k/256p; **96/256 (37.5%)** at 1k/256p and **96/256 (37.5%)** at 1k/64p — **honest re-baseline after the §113 battle-skip-exploit invalidation** (the "60.2% @3k" §107 headline was inflated by control S3 skip-winning battles at WARCRY/GAMBLE CARD_SELECT states; honest control S3 = 9.0% @1k). Particles flat (64p = 256p at 1k, §115). §124 re-measured on the live-valid binary: 37.9% @1k/64p (flat) and 46.9% @3k/256p (+2.3pp n.s.). Future gate rounds pair against `build/b2c_1k_64p.csv` (1k/64p) / `build/b1c_3k_256p.csv` (3k/256p) / `build/b4_3k_64p.csv` (3k/64p). |
| **Previous recommended configuration — V4 one-ply gate stack @3,000 sims**, 2026-08-04 (`EXPERIMENTS.md` §99) | 126700–126955 (256) | 0 | 3,000 sims/decision | `STS_FAIR=1`, default Searcher2, 24 threads | Native tracked floor/win trees; heuristic path/shop/win-rest; **opt-in V4 token net + full one-ply Q gate stack** (`STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_final.native`, `REST/EVENT/SHOP/TREASURE/BOSS_RELIC=1`, `STS_OOC_STRATEGIC_MARGIN=1.0`); no combat value net (vnet A/B'd and rejected under the gates, §97) | Full Act-3 run win: **116/256 (45.3%)**, mean floor 42.9, mean end HP 25.3 — **+8.2pp win (CI [+0.8,+15.6]) and +2.0 floor (CI [+0.3,+3.7]) vs the previous recommended V3@1k reference on the same block**, at 3.4× cpu (31.3 vs 9.2 cpu-sec/run). V4@4k adds only +1.2pp (noise; floor/HP flat), so 3,000 sims is the operating point. Per-seed CSVs `build/simsweep_{2k,3k,4k}_256.csv`, `build/simsweep_v4_{3k,4k}_256.csv`. **S2-based, unaffected by the §113 S3 skip exploit.** |
| **Invalidated S3 headline — S3−belief−chain + V4 one-ply gate stack**, 2026-08-05 (`EXPERIMENTS.md` §106, §107; **invalidated by §113**) | 126700–126955 (256) | 0 | 3,000 sims/decision | `STS_FAIR=1`, Searcher3 with `STS_S3_BELIEF=0 STS_S3_CHAIN=0`, 24 threads | Same V4 gate stack; pre-fix (619c12c) S3 enumerator | **60.2% @3k / 57.4% @1k64p — INVALID: the pre-fix S3 enumerator skip-won battles at WARCRY/GAMBLE CARD_SELECT states (zero valid edges → UNDECIDED break → rewards/advance). Not an honest baseline; superseded by the §113 recommended row.** |
| **Previous recommended configuration — V3 one-ply gate stack @1,000 sims**, 2026-08-03 (`EXPERIMENTS.md` §82) | 126700–126827 (128); also 126700–126955 (256) | 0 | 1,000 sims/decision | `STS_FAIR=1`, default Searcher2, 12 threads | Native tracked floor/win trees; heuristic path/shop/win-rest; **plus the opt-in one-ply Q gate stack** (`STS_OOC_STRATEGIC_NN=selfplay/models/ooc_strategic.native`, `REST/EVENT/SHOP/TREASURE/BOSS_RELIC=1`, `STS_OOC_STRATEGIC_MARGIN=1.0`) | Full Act-3 run win: **51/128 (39.8%)** on the 128 block (reference CSV `build/gates_ref_m1.csv`, bit-identical to §76 m1.0); **95/256 (37.1%, +14.1pp vs the 23.0% flags-off baseline)** on the 256 block (`build/sec256_gate_m1.csv`). Superseded as the recommendation by §99 but still the paired 128-block reference. |
| **Historical top arm — V4 token net + gate stack @1,000 sims**, 2026-08-03 (`EXPERIMENTS.md` §81, §92) | 126700–126827 (128); 126700–126955 (256) | 0 | 1,000 sims/decision | `STS_FAIR=1`, default Searcher2, 12–24 threads | V4 token net (`STS_OOC_STRATEGIC_TOK_NN=…ooc_strategic_tok_final.native`, opt-in) + full gate stack @ m1.0 | Full Act-3 run win: **53/128 (41.4%)** (§81); **105/256 (41.0%)** (§92). Superseded by the §99 3,000-sim measurement. |
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
models/v_rich_trees.txt    sha256 3a3420469b1d648e0e306d6cb6a7e85f3d3499105e3ff3a56eee6c579194ffe3
models/v_win_trees.txt     sha256 fc52c14cb7239a33b3c1f9d0477ccb6c895fd51a07240fe804744e605067ad70
models/policy_trees_c.txt  sha256 24793bd39dd1a35c8865035e458c3aa40616ef021cb26b05f914f72fb5e5a321
models/v_combat_pvnet.txt  sha256 a7a55e5290fd6bece028ab0aeb9509a80dcb304f3103ba444b8205ec17e27b72
models/v_combat_7k_tuned.txt sha256 ea35b78c888e70e09566e1143d296577b0bea2ec8d437276b7aab81a7cdaf15c
selfplay/models/ooc_strategic_tok_final.native sha256 e62abd833fc8cb9081a1cec4a1a012832ac3b0e3166da3892841911664f1184c
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
- The current checkout's default stack is benchmarked at §124 (flat @1k vs the
  §113/§115 references; the recommended config with the §126 vnet default is
  measured at §126).
- Fair-play is partial hidden-information handling, especially under Searcher2.
- The V4 token-net artifact at `selfplay/models/ooc_strategic_tok_final.native` is
  the §149 skewfix model (sha256 `e62abd83…`, 42-glob, honest). On S2-fair it gates
  at +15.6pp (39.1% vs 23.4%, §149). On S3+vnet at Act 3 it **reverses sign**
  (−6.3pp: 31.2% vs 37.5%, §153) but is **essential for Act 4** (+15.7pp:
  21.9% vs 6.3%). The leaky NGLOB=50 model is rejected by the current C++ loader
  (dims-check failure).
- The V3 strategic net at `selfplay/models/ooc_strategic.native`
  (sha256 `b096498abf…`) is also **leaky** — it consumes the full `richRow()`
  feature vector which includes all 8 hidden-information leaks (nextEliteId,
  nextFight0/1/2, remElites, remFights, monOffset, eliteOffset) with no
  filtering. It is not in the recommended configuration (which uses V4 token-net
  gates via `STS_OOC_STRATEGIC_TOK_NN`) but remains a git-tracked artifact and
  is used by several experimental ablation scripts (`tools/run/run_screen_ablate.sh`,
  `tools/run/run_mapgate_ab.sh`, `tools/run/run_distgate_ab.sh`).
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
- All recorded PVNet bot results (§72 re-check and the Phase 4b sweep) predate
  the 2026-08-04 C++ parity fixes (GELU FFN, fixed 14-token layout, policy-head
  dot product; see the decision log `2026-08-04-combat-pvnet-parity-fixes.md`);
  the fixes are not expected to move 100-sim results, which are dominated by
  heuristic OOC choices. The 2026-08-05 3k-sim payoff gate on the fixed binary
  (§102) is negative: no S3+PVNet arm beats same-compute S2/S3, and the A–H
  architecture sweep was stopped accordingly.

## Open questions

- Which exact artifact hashes and flags produced the 39/128 result?
- Should a reproducible baseline bundle include executable/model hashes and
  captured startup output?
- The key-collection commit (`32281a2`) changed the benchmark horizon from
  Act 3 to Act 3+4. All pre-commit baselines are Act-3-only. Should the
  recommended configuration headline be Act-3+4 (current default) or
  Act-3-only (`STS_STOP_AFTER_ACT=3`)?

## Relevant code

- `apps/one_combat.cpp::main`, `runFullRunOOC`, `bestBench`
- `src/sim/search/ScumSearchAgent2.cpp::playoutBattle`
- `src/sim/search/BattleScumSearcher2.cpp::determinize`
- `src/sim/search/BattleScumSearcher3.cpp::g_useSearcher3`
- `src/sim/search/CombatPVNet.cpp::g_pvnetAlpha`
- `EXPERIMENTS.md` §26, §66i, and “Phase 4b PVNet alpha sweep”
- tracked deployable artifacts under `models/` and `selfplay/models/`
