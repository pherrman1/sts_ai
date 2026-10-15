# ADR-0003: Searcher2 is default and Searcher3 is an opt-in particle searcher

Date: 2026-08-13
Status: superseded by [ADR-0018](0018-silver-default-combat-backend.md)

## Context

The integration driver supports two combat tree-search implementations with different hidden-state and inference semantics.

## Decision

Keep `BattleScumSearcher2` as the default combat searcher. Select `BattleScumSearcher3` only through its explicit configuration path, and report its particle-based behavior separately.

## Rationale

The current code map identifies Searcher2 as default and Searcher3 as opt-in; the maintained architecture documents distinct particle conditioning and model-consumption semantics.

## Alternatives considered

- Collapse both searchers behind an undocumented common label — rejected because their RNG treatment, tree reuse, and learned-leaf behavior differ.

## Consequences

Tooling and benchmark provenance must identify the actual searcher and flags.

## Affected files

- `apps/one_combat.cpp`
- `include/sim/search/BattleScumSearcher2.h`
- `include/sim/search/BattleScumSearcher3.h`
- `src/sim/search/ScumSearchAgent2.cpp`

## Evidence

- `docs/knowledge-base/CODE_MAP.md` — designates Searcher2 as default and Searcher3 as opt-in particle ISMCTS.
- `docs/knowledge-base/architecture/combat-search.md` — documents each searcher's differing behavior and model semantics.
