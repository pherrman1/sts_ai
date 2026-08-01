# 2026-08-02 — Decision log and knowledge-base usage contract

Date: 2026-08-02
Session/task: Establish an in-repo decision log and make AGENTS.md require
consistent knowledge-base use during LLM-agent coding sessions.

## Decision

- Create `docs/knowledge-base/decision-log/` as the chronological, dated record
  of decisions made during LLM-agent coding sessions. One entry file per
  session, appended before the session closes.
- Record architecture/design choices, process/tooling choices, notable rejected
  alternatives, and new facts or corrections to prior understanding.
- Keep `docs/knowledge-base/decisions/` for durable, evidence-backed
  architectural decision records. A logged decision is distilled there only
  when its rationale is supported by repository evidence.
- Update `sts_lightspeed/AGENTS.md` and the workspace-root `AGENTS.md` to
  require: read the knowledge base and recent decision-log entries before
  substantial work; log significant decisions before a session closes; reflect
  stable new understanding in the relevant knowledge-base page in the same
  change.

## Rationale

Decisions were previously scattered across `EXPERIMENTS.md`, knowledge-base
pages, and the external Claude memory archive
(`~/.codex/imports/claude/sts/memory/`). A lightweight in-repo log gives
versioned, chronological, per-session decision history without imposing the
evidence bar of `decisions/`, which still has no records because rationale is
often distributed across dated experiment entries (`decisions/README.md`).

## Alternatives considered

- Reuse `decisions/` only — rejected: its required format demands
  evidence-backed rationale, which does not fit routine session-level
  decisions and process choices.
- Single running log file — rejected in favor of one file per session to avoid
  merge conflicts between parallel agent sessions.
- Leave the memory archive as the decision store — rejected: it is external to
  the repo and not versioned with the code.

## Evidence

- `AGENTS.md` (workspace root) — memory archive pointer.
- `sts_lightspeed/AGENTS.md` — operating contract; "Documentation maintenance".
- `docs/knowledge-base/README.md` — reading paths and ownership.
- `docs/knowledge-base/decisions/README.md` — durable decision-record format.

## Status and follow-up

- Implemented: decision-log directory, template, first entry, AGENTS.md and
  knowledge-base index updates.
- Open: distill this decision into a `decisions/` record if its rationale ever
  needs a durable evidence-backed form.
