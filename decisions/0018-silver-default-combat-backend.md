# ADR-0018: Silver is the default combat backend for whole-run play

Date: 2026-09-24
Status: accepted; the whole-run adaptive default is amended by
[ADR-0026](0026-learned-silver-stopping-default.md) (learned stopping)

Supersedes: [ADR-0003](0003-searcher2-default-searcher3-opt-in.md)

## Context

ADR-0003 kept known-RNG `BattleScumSearcher2` as the executable default. Since
then, the live advisor (`one_combat_advisor`) has searched only with Silver,
and current research producers already require `STS_SILVER_SEARCH=1` (for
example `wholecombatgen`, `tools/silver_prior_dataset.py` and
`tools/ooc_pipeline_contract.py`). A whole-run invocation without flags
therefore fell back to a known-RNG searcher that is not honest play. It also
differed from the backend that current work measures.

## Decision

For the whole-run modes `run`, `bestbench` and `reprobench`, `one_combat`
resolves an unset `STS_SILVER_SEARCH` to `1` and an unset `STS_FAIR` to `1`,
then writes both values to the process environment. When Silver is effective
and the caller passes an explicit sims argument, an unset
`STS_SILVER_ADAPTIVE` resolves to `0`, so Silver searches that flat budget.
This does not apply when `STS_SILVER_ADAPTIVE_RETAINED_ONLY` or
`STS_SILVER_ADAPTIVE_TOP_GAP` is set. An explicit
`STS_SILVER_SEARCH` value, including `0`, is respected. An explicit
`STS_SEARCHER3=1` keeps the native Searcher3 path. Other modes keep their
previous explicit-opt-in behavior.

## Rationale

Silver is the backend that the live advisor and current research producers
use. Making it the whole-run default aligns flag-free runs with that work and
removes the known-RNG fallback from default measurements (ADR-0002). Writing
the resolved values back to the environment lets existing environment-contract
checks and child processes see the effective configuration.

## Alternatives considered

- Make Silver the default for every mode. Rejected for now: many legacy data
  generators and diagnostics (`fairgen`, `combatgen`, `searchdiag`,
  `runtrace`, particle probes) instrument native searchers directly or bypass
  the external backend hook. Under Silver they would silently produce
  different data or none.
- Keep adaptive Silver under an explicit sims argument. Rejected: adaptive
  Silver searches 500 to 10,000 simulations regardless of the argument, so a
  requested budget would be silently ignored.
- Keep ADR-0003 and rely on explicit flags. Rejected because the default then
  measures a searcher that current work no longer uses.

## Consequences

- Flag-free `run`, `bestbench` and `reprobench` results use Silver fair play.
  Earlier default results used known-RNG Searcher2 and form a separate series.
  Result metadata already records `effective_combat_backend`, and the
  `bestbench` configuration banner reports `searcher=Silver` when Silver is
  installed.
- Flag-free runs that pass sims use flat Silver at that budget. Adaptive
  results need `STS_SILVER_ADAPTIVE=1` or no sims argument. Current Silver
  research producers already pin `STS_SILVER_ADAPTIVE=0` and are unaffected.
- Callers that relied on the native default must now set
  `STS_SILVER_SEARCH=0`. `selfplay/loop.sh` pins it so self-play keeps its
  fair Searcher2 behavior. Legacy `tools/run/*.sh` Searcher2 reference arms
  that set neither flag now run Silver.
- Folding Silver into the main simulator and retiring Searcher2/3 are
  separate follow-up changes.

## Affected files

- `apps/one_combat.cpp`
- `selfplay/loop.sh`
- `docs/knowledge-base/architecture/combat-search.md`
- `docs/knowledge-base/operations/environment-variables.md`
- `docs/knowledge-base/CODE_MAP.md`

## Evidence

- `apps/one_combat.cpp::main` resolves the default before the
  `STS_FAIR`/`STS_SILVER_SEARCH` parse. It installs the Silver backend only
  when `STS_SILVER_SEARCH` is non-zero.
- `src/sim/search/ScumSearchAgent2.cpp::playoutBattle(GameContext&, BattleContext&)`
  and `apps/one_combat/run_driver.cpp` route whole-run combats through
  `g_externalCombatBackend`. `runTraceRun` calls the `BattleContext`-only
  overload and bypasses it.
- `apps/one_combat/advisor_stdio.cpp` uses `silver_bridge::SilverSearchSession`
  directly.
