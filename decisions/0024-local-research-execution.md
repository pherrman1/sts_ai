# ADR-0024: Explicitly authorized local research without a fixed seed ceiling

Date: 2026-09-26
Status: accepted; supersedes ADR-0006 and ADR-0009.

## Context

[Issue #359](https://github.com/pherrman1/sts_ai/issues/359) establishes that the
designated cloud research server is unavailable and authorizes retiring its
workflow and the fixed local 128-seed ceiling. Historical experiment identities,
results, and frozen guards remain evidence and must not be rewritten.

## Decision

Use the smallest justified experiment. Larger local runs require explicit
user authorization. Before execution, record frozen source/model/binary
provenance, exact seed ranges/counts, simulation and resource budgets, and
scientific decision rules. A request to modify tooling does not authorize an
experiment. Preserve independent review and the reviewed-SHA freeze boundary.

Remove the host-specific launcher, its launcher-only manifest template and
tests. Port the fixed semantic-confirmation runner to local execution while
retaining its cohort, artifact hashes, review gate and resumed-output checks.
All seed commands still use `tools/seed_guard.sh`; it validates positive counts
for recognized modes without a general numeric ceiling or host-specific bypass.
The semantic pilot's native 1..16 source/decision bounds remain mode contracts.
Guard acceptance neither grants authorization nor verifies experiment provenance.

The operations preflight retains clean environments, exact source/build and
artifact identity, fresh output checks, canaries, and completion validation.
Preserved evidence scripts and frozen guards describe their original runs;
they are not current execution instructions or a general local ceiling.

## Alternatives

- Restore or replace the designated server: not required or authorized by this
  change; the workflow must not depend on unavailable infrastructure.
- Raise the ceiling to another number: does not express experiment cost or
  authorization. Budget and scientific design are the relevant constraints.
- Remove all validation: rejected; malformed counts and native semantic-mode
  constraints remain useful pre-execution checks.

## Evidence and affected files

- `AGENTS.md`, research skill, operations workflow and benchmark protocol:
  explicit authorization, frozen provenance and smallest justified sample.
- `tools/seed_guard.sh`, `tests/agent/test_seed_guard.py` and
  `tests/agent/test_semantic_seed_guard.py`: non-executing large-count acceptance,
  malformed-count rejection, preserved semantic bounds and command passthrough.
- `tools/run_ooc_semantic_confirmation.py` and
  `tests/test_semantic_confirmation_runner.py`: local command construction and
  frozen capture/evaluation binding.
- Current-research and code-map pages retire stale host-only routing. Historical
  ledgers, preparation manifests and results retain their recorded identities.

## Consequences

Larger authorized local experiments need no cloud context or ceiling bypass.
Authorization and provenance are enforced by the research workflow and
experiment-specific validators, not inferred by the shell seed guard. No
scientific experiment or runtime/gameplay default is changed by this decision.
