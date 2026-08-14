# 2026-08-14 — GCP research seed boundary

Date: 2026-08-14
Session/task: Durable GCP benchmark access and unrestricted GCP research seed mode

## Decision

The user explicitly authorized future Cline sessions to choose any positive
seed count for justified research runs on the designated `sts-test` GCP
machine. Local automated runs retain a hard 128-seed cap. The repository-owned
GCP launcher is the canonical route and invokes the explicit remote guard mode.

## Rationale

The old global ceiling obstructed legitimate large research on the already
documented benchmark machine. Retaining the local cap prevents accidental
workstation consumption. A separate explicit GCP path was chosen instead of
globally disabling the guard so location, intent, process checks, argument
validation, and provenance remain visible. Credential handling remains outside
Git in the user's existing gcloud authentication.

## Alternatives considered

- Remove the cap globally — rejected; local automated safety must remain.
- Add another numeric GCP ceiling — rejected by the explicit user decision.
- Require a one-off human approval for every large GCP count — rejected by the
  explicit authorization; scientific design remains required but is not an
  approval gate.

## Evidence

- `tools/seed_guard.sh` — separate local and `--gcp-research` guard behavior.
- `tools/agent/gcp_benchmark.py` — designated instance defaults, gcloud SSH,
  active-process check, and detached launch path.
- `decisions/0006-automated-game-seed-limit.md` and ADR-0009 — explicit
  supersession limited to GCP research.

## Status and follow-up

- Implemented pending focused tests, live gcloud availability, and PR CI.