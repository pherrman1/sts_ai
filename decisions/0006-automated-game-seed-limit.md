# ADR-0006: Automated game-seed verification is capped at 128

Date: 2026-08-13
Status: superseded by [ADR-0024](0024-local-research-execution.md).

Historical decision text below is retained as provenance, not current guidance.

## Context

Automated local verification needs a deterministic upper bound on game-seed sweeps. This record predates the separately authorized GCP research path.

## Decision

Route game-seed commands through `tools/seed_guard.sh` and reject local automated requests exceeding `MAX_AUTOMATED_SEEDS=128`. Use smaller focused samples by default; 128 is a ceiling, not a routine target. ADR-0009 supersedes this record only for designated GCP research execution.

## Rationale

The guard implements a concrete cap for configured `one_combat` and Python entry points, and the project operating contract specifies smaller normal verification tiers.

## Alternatives considered

- Let every agent choose an unrestricted statistical sample — rejected because it risks expensive, uncontrolled workloads.

## Consequences

Commands that exercise game seeds need the guard. Local automated runs remain capped; designated GCP research runs use the explicit unbounded mode described by ADR-0009.

## Affected files

- `tools/seed_guard.sh`
- `AGENTS.md`

## Evidence

- `tools/seed_guard.sh::MAX_AUTOMATED_SEEDS` — implements the 128-seed and replay-cell rejection checks.
- `AGENTS.md` — defines the guard and focused verification expectations.
- `decisions/0009-unbounded-gcp-research-seed-runs.md` — superseding GCP operating boundary.
