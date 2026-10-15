# ADR-0005: Deployable model exports are versioned artifacts

Date: 2026-08-13
Status: accepted

## Context

The repository distinguishes deployed native/text/JSON model artifacts from large trainer checkpoints and generated buffers.

## Decision

Track deployable native exports under `selfplay/models/*.native` and deployed text/JSON artifacts under `models/`. Keep trainer checkpoints, buffers, and intermediate data ignored and hand them off separately.

## Rationale

This permits a deployment handoff through Git while avoiding multi-gigabyte training state in the tracked tree. Artifact presence alone does not prove a particular runtime arm loaded or used it.

## Alternatives considered

- Ignore all model artifacts — rejected because deployed exports must travel with their code, hashes, and documentation.
- Track trainer checkpoints — rejected because they are large local training state rather than deployable interfaces.

## Consequences

Deployment changes must include the artifact, its hash, and associated documentation; startup output and arm-specific consumption remain required verification.

## Affected files

- `.gitignore`
- `models/`
- `selfplay/models/`
- `apps/one_combat.cpp`

## Evidence

- `AGENTS.md` — repository-map model-artifact policy and load-verification warning.
- `docs/knowledge-base/CODE_MAP.md` — maps native OOC model artifacts and startup inference loading.
