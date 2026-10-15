# ADR-0020: Silver is the only combat searcher; remove Searcher2 and self-play

Date: 2026-09-24
Status: accepted

Supersedes: the native-searcher opt-out (`STS_SILVER_SEARCH=0`) of
[ADR-0018](0018-silver-default-combat-backend.md), and the remaining Searcher2
default of [ADR-0003](0003-searcher2-default-searcher3-opt-in.md). For
historical results,
[ADR-0002](0002-fair-and-known-rng-are-separate-regimes.md) still applies:
known-RNG rows stay a separate series.

## Context

After ADR-0018 and ADR-0019, `BattleScumSearcher2` remained for three reasons:

- the self-play loop (`selfplay/loop.sh`) used it;
- several data generators and OOC lookahead probes played their fights with it;
- `STS_SILVER_SEARCH=0` still selected it.

The self-play FIGHT arm trained two models that only Searcher2 consumed: the
PUCT policy prior (`policy_trees_c`) and the V_combat leaf value. Silver uses
neither. The project owner decided to consolidate all combat search on Silver
and to remove self-play for now.

## Decision

- Delete `BattleScumSearcher2` and the agent's native combat loops.
  `ScumSearchAgent2::playoutBattle(GameContext&, BattleContext&)` now requires
  an installed combat backend and throws without one.
- `one_combat` always installs Silver. `STS_SILVER_SEARCH=0` and `STS_FAIR=0`
  exit with an error; `=1` and unset are accepted.
- An explicit sims argument selects flat Silver in every mode. Only
  `run`/`bestbench`/`reprobench` called without a sims argument keep adaptive
  Silver by default. `STS_SILVER_ADAPTIVE*` still overrides both.
- Route the kept whole-run and OOC generators and probes through Silver:
  `datagen3`, `strategicgen`, `strategicgen2`, `oocnextgen`, `pathcfgen`,
  `e2cgen`, `runtrace` (including its refight diagnostic), checkpoint and
  next-combat probes, and card rollouts. E2c capture now runs on the Silver
  path.
- Delete the generators whose output is Searcher2 search statistics:
  `combatgen`, `fightgen`, `policygen`, `distgen`, `datagen`, `datagen2`,
  `causalgen` and `searchdiag`. The VNet query log goes with them.
- Delete the Searcher2-only controls: rollout depth, forced-move contraction,
  live-valid selection, TT, turn penalty, convergence and root-stability
  stopping, and `STS_DATAGEN_GATES`. Also delete the Searcher2 combat-model
  loading: `STS_VNET*`, `STS_POLICY`, `STS_CPUCT`, `STS_PVNET*` and
  `STS_DIST_VNET`.
- Remove the self-play loop and its collection scripts. `selfplay/models/` and
  `selfplay/ooc_buffer/` stay because live and research code reads them.

## Rationale

A single combat searcher removes a second rule-and-search stack and its flags,
and it means every generator and benchmark measures the same backend.
Converting the Searcher2-statistics generators would have produced different
data under the same names, so they are deleted rather than silently redefined.

## Alternatives considered

- Retarget self-play to train Silver's own models (leaf value, SilverPriorNet).
  Deferred: that is a new research pipeline and needs its own design.
- Route every generator through Silver. Rejected: generators that record
  Searcher2 visit counts would lose their data, and fight-heavy lookaheads
  become much slower.

## Consequences

- `bestbench` results for Silver are unchanged. The pre-change and post-change
  binaries give identical rows for 4 seeds at 200 sims.
- Kept generators and probes now play Silver fights, so their outputs differ
  from earlier Searcher2-produced datasets and must be treated as a new series.
- The compact policy prior, the V_combat leaf, PVNet and DistVNet artifacts are
  no longer consumed by `one_combat` play. Their libraries remain for parity
  tools (`vnettest`, policy parity).
- Benchmark metadata keeps `fairPlay` (now always true) and the combat-model
  keys (fixed `off`) for schema compatibility.

## Affected files

- `src/sim/search/BattleScumSearcher2.cpp`, `include/sim/search/BattleScumSearcher2.h`, `include/sim/search/SearchDiagnostics.h` (deleted)
- `apps/one_combat/search_diagnostics.{h,cpp}`, `apps/one_combat/vnet_query_log.{h,cpp}` (deleted)
- `selfplay/*.sh`, `selfplay/*.env`, `tools/run/datagen_loop.sh`, `tools/run/datagen2_loop.sh` (deleted)
- `src/sim/search/ScumSearchAgent2.cpp`, `apps/one_combat.cpp`, `apps/one_combat/run_driver.cpp`, `apps/test.cpp`, `apps/small-test.cpp`, `CMakeLists.txt`, `tools/seed_guard.sh`

## Evidence

- Silver `bestbench 200 4 0 500` rows are identical to the pre-campaign
  reference binary.
- Local smoke runs of `run`, `runtrace`, `datagen3`, `strategicgen`,
  `strategicgen2`, `oocnextgen`, `pathcfgen` and `e2cgen` completed with rc=0
  and produced rows.
