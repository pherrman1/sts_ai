# ADR-0001: Combat outcome is canonical termination

Date: 2026-08-13
Status: accepted

## Context

Combat control needs one terminal-state contract shared by battle loops and post-combat handoff.

## Decision

Continue combat loops only while `BattleContext::outcome == Outcome::UNDECIDED`. Treat `isBattleOver()` as a derived convenience, not an independent source of terminal state.

## Rationale

The current combat-search invariants and loop data flow explicitly use `Outcome::UNDECIDED`; `BattleContext::exitBattle` transfers persistent results after that terminal transition.

## Alternatives considered

- Use `isBattleOver()` as a second terminal contract — rejected because it is derived from `outcome` and could diverge from the canonical state model.

## Consequences

New combat loops, guards, and tests must preserve the outcome-based condition.

## Affected files

- `include/combat/BattleContext.h`
- `src/combat/BattleContext.cpp`
- `src/sim/search/ScumSearchAgent2.cpp`

## Evidence

- `docs/knowledge-base/architecture/combat-search.md` — combat data flow and invariants specify `outcome != Outcome::UNDECIDED` as termination.
- `src/combat/BattleContext.cpp::exitBattle` — terminal state transfers results back to `GameContext`.
