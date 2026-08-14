# ADR-0009: Automated GCP research runs have no fixed seed ceiling

Date: 2026-08-14
Status: accepted

## Context

ADR-0006 established a 128-seed ceiling for automated game-seed verification.
The designated `sts-test` GCP machine is the repository's normal location for
large research runs, and future Cline sessions are explicitly authorized to
choose a scientifically justified sample there.

## Decision

Keep the local automated maximum at 128 seeds. Add an explicit
`tools/seed_guard.sh --gcp-research` mode, used through
`tools/agent/gcp_benchmark.py` on `sts-test`, that retains seed and argument
validation but has no numeric seed ceiling. The launcher uses the user's local
gcloud authentication, starts only the existing designated instance when
needed, checks for active `one_combat`, and launches detached jobs without
managing arbitrary cloud resources.

This supersedes ADR-0006 only with respect to designated GCP research
execution. It does not permit unguarded local execution or raw remote
`one_combat` invocation.

## Rationale

The explicit path preserves the local mistake-prevention boundary while making
large, legitimate research runs reproducible and discoverable to fresh Cline
sessions. No numeric replacement ceiling is introduced. Scientific controls,
provenance, paired seeds, regime separation, comparable budgets, schemas, raw
outputs, and ledger recording remain required.

## Alternatives considered

- Remove the 128 limit globally — rejected because local automated verification
  must remain protected from accidental expensive workloads.
- Replace 128 with another fixed ceiling — rejected because the GCP research
  policy is deliberately numerically unbounded.
- Leave the GCP procedure in prose only — rejected because fragile SSH command
  reconstruction would undermine durable discoverability and guard use.

## Consequences

Future agents may launch a justified GCP run above 128 without another
seed-count approval step. They must still choose the smallest informative
sample and record the experiment design before launch. GCP credentials remain
external local user state and are never stored in Git.

## Affected files

- `tools/seed_guard.sh`
- `tools/agent/gcp_benchmark.py`
- `AGENTS.md`
- `docs/knowledge-base/operations/build-and-debugging.md`
- `.cline/skills/research-experiment/SKILL.md`

## Evidence

- `tools/seed_guard.sh` guard-only checks: local 128 accepted, local 129
  rejected, GCP 129 and 2000 accepted.
- `docs/knowledge-base/operations/build-and-debugging.md` records the existing
  `sts-test` project, zone, user, remote root, gcloud SSH path, and nohup
  workflow.