# Decision records (historical/superseded)

Last verified: 2026-09-04 against the current working tree.

> This legacy knowledge-base index is historical and superseded. New durable
> decisions belong in the root [`decisions/`](../../../decisions/) ADR
> directory. The dated session record remains frozen in
> [`decision-log/`](../decision-log/).

This directory is for durable architectural or operating decisions whose
rationale is directly supported by repository evidence. `EXPERIMENTS.md`
remains the place for chronological policy/model benchmark decisions
(`EXPERIMENTS.md`, numbered experiment entries; `AGENTS.md`,
“Experiment-recording rules”).

## Index

| Record | Topic |
| --- | --- |
| [`2026-08-02-semi-markov-strategic-model.md`](2026-08-02-semi-markov-strategic-model.md) | Semi-Markov run-level strategic model: combat as a temporally extended transition, unified candidate scoring, run-value as the shared pricing language, margin-gated overrides, hidden-information boundary. |
| [`2026-08-02-one-ply-q-gate.md`](2026-08-02-one-ply-q-gate.md) | Margin-gated one-ply Q gate: run-level overrides scored with the Q(s,a) head on Tier-B one-ply counterfactual labels, argmax executed only at/above `STS_OOC_STRATEGIC_MARGIN` (default 1.0); successor-value and un-gated paths rejected; V3 deployed, V4 opt-in. |

The chronological, session-level record — including process and tooling
choices, rejected alternatives, and new facts — lives in the frozen
[decision log](../decision-log/README.md). Existing records here are retained
for historical context; do not add new records to this superseded directory.

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
- `docs/knowledge-base/evaluation/current-baselines.md` — current configuration and benchmark qualification.
