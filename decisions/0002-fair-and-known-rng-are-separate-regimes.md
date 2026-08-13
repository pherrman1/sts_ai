# ADR-0002: Fair and known-RNG evaluation are separate regimes

Date: 2026-08-13
Status: accepted

## Context

Combat-search configurations expose different information assumptions. A single metric series would imply comparability that the implementations do not provide.

## Decision

Label project-fair and known-RNG results as separate regimes and never combine them into one benchmark progression or baseline comparison.

## Rationale

Searcher2's known-RNG mode determinizes from concrete battle RNG, while fair paths follow different hidden-information handling. The benchmark protocol and maintained invariants make the separation explicit.

## Alternatives considered

- Treat all `bestbench` outcomes as directly comparable — rejected because different information access changes what the measured agent is solving.

## Consequences

Experiment records must state the regime, relevant flags, searcher, and provenance; current-baseline claims must not bridge the two series.

## Affected files

- `apps/one_combat.cpp`
- `src/sim/search/BattleScumSearcher2.cpp`
- `src/sim/search/BattleScumSearcher3.cpp`
- `docs/knowledge-base/evaluation/benchmark-protocol.md`

## Evidence

- `docs/knowledge-base/evaluation/benchmark-protocol.md` — describes Searcher2 known-RNG behavior and forbids grouping it with fair measurements.
- `docs/knowledge-base/behavior/invariants.md` — requires separate metric series for project-fair and known-RNG modes.
