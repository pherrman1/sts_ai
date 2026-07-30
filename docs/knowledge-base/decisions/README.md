# Decision records

Last verified: 2026-07-30 against the current working tree, including
uncommitted implementation changes.

This directory is for durable architectural or operating decisions whose
rationale is directly supported by repository evidence. `EXPERIMENTS.md`
remains the place for chronological policy/model benchmark decisions
(`EXPERIMENTS.md`, numbered experiment entries; `AGENTS.md`,
“Experiment-recording rules”).

No standalone decision record has been extracted in this first version. The
repository contains conclusions, but their rationale is often distributed
across dated experiment entries; copying only the outcome would invent or lose
context.

## Required record format

Each record should contain:

- title, status, date, and `Last verified`;
- the decision actually made;
- alternatives that repository evidence explicitly shows were considered;
- evidence with repository-relative paths plus symbols, executable modes, test
  names, or experiment entry identifiers;
- consequences that are directly observed, separated from **Inference**;
- superseding or invalidating evidence;
- a `Relevant code` section.

Do not manufacture intent from code shape. If rationale is absent, write an
**Open question** in an investigation instead.

## When to update

Create or revise a record when a change alters a durable subsystem boundary,
schema, reproducibility contract, deployment model, or evaluation rule and the
reason is captured in code review, tests, or repository documentation. Mark a
record superseded rather than rewriting its history.

## Relevant code

- `AGENTS.md` — documentation and experiment-recording rules.
- `EXPERIMENTS.md` — existing evidence and corrections.
- `docs/knowledge-base/experiments/current-state.md` — current recommendation summary.
