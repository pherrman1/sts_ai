# ADR-0007: Curated records and raw experiment ledgers have distinct roles

Date: 2026-08-13
Status: accepted

## Context

The repository keeps durable technical understanding and experimental evidence in distinct Git-tracked Markdown surfaces. Historical session narratives remain in Git history only.

## Decision

Keep `EXPERIMENTS.md` and its ledger shards as chronological experiment evidence, the knowledge base as maintained current understanding, and root `decisions/` as a small ADR set for durable evidence-backed rationale.

## Rationale

Each surface has an explicit purpose and authority boundary. Derived tooling may index them but may not replace them.

## Alternatives considered

- Convert every chronological entry or experiment into an ADR — rejected because experiments, transient states, and one-off fixes are not durable architectural choices.

## Consequences

New records must go to the appropriate surface; ADRs link existing curated pages rather than duplicating evolving evidence.

## Affected files

- `EXPERIMENTS.md`
- `docs/experiments/`
- `docs/knowledge-base/`
- `decisions/`

## Evidence

- `EXPERIMENTS.md` — declares the experiment ledger, current append shard, and current-truth routing.
- `docs/knowledge-base/README.md` — defines maintained knowledge-base and decision-record responsibilities.
