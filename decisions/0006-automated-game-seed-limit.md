# ADR-0006: Automated game-seed verification is capped at 128

Date: 2026-08-13
Status: accepted

## Context

Automated agent verification needs a deterministic upper bound on game-seed sweeps while leaving larger research runs under human control.

## Decision

Route game-seed commands through `tools/seed_guard.sh` and reject automated requests exceeding `MAX_AUTOMATED_SEEDS=128`. Use smaller focused samples by default; 128 is a ceiling, not a routine target.

## Rationale

The guard implements a concrete cap for configured `one_combat` and Python entry points, and the project operating contract specifies smaller normal verification tiers.

## Alternatives considered

- Let every agent choose an unrestricted statistical sample — rejected because it risks expensive, uncontrolled workloads.

## Consequences

Commands that exercise game seeds need the guard; larger sweeps are manual research work, not autonomous validation.

## Affected files

- `tools/seed_guard.sh`
- `AGENTS.md`

## Evidence

- `tools/seed_guard.sh::MAX_AUTOMATED_SEEDS` — implements the 128-seed and replay-cell rejection checks.
- `AGENTS.md` — defines the guard and focused verification expectations.
