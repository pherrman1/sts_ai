# 2026-08-11 - Research documentation cleanup

## Decision

Use `docs/knowledge-base/evaluation/current-research.md` as the single routing
source for active, parked, and closed research lines. Keep stable technical
facts in maintained knowledge-base pages, chronological results in
`EXPERIMENTS.md`, and move completed plans, handoffs, session snapshots, and
resolved investigation reports to `docs/archive/research/`.

Delete ignored `.ai/` runtime state after preserving unique summary-level
experiment evidence in `EXPERIMENTS.md` §166.

## Rationale

The maintained knowledge-base index linked several mutually inconsistent dated
plans as active. Intermediate encounter-marginalization reports also disagreed
about completed tests, output schemas, and whether training had begun. Keeping
those snapshots in the maintained routing surface made stale instructions look
authoritative.

**Inference:** one current-status page plus subject-oriented maintained pages
reduces agent routing ambiguity without discarding historical evidence.

## Alternatives considered

- Delete all dated documentation: rejected because historical experiment
  interpretation depends on the original contracts and intermediate evidence.
- Leave files in place and change only status labels: rejected because dated
  plans would remain mixed with maintained technical references.
- Move every closed issue record: deferred because it would create broad link
  churn. The issues index now puts a compact open queue before the historical
  table instead.

## Evidence

- `docs/knowledge-base/README.md` previously listed multiple dated plans with
  active or ready-to-execute labels.
- `docs/knowledge-base/encounter-marg-final-summary-2026-08-10.md` records
  completed M0/M1 training and gating, superseding four earlier snapshots.
- `.gitignore` ignores `/.ai/`; commit `a5e415b` removed the Pi orchestration
  workflow that generated most of that local state.
- `EXPERIMENTS.md` §166 preserves the unique MCTS-leaf MLP/deep-target arc from
  the ignored summaries with explicit unverified provenance.

## Status

Adopted. Archived material is historical evidence and must not be treated as
current execution guidance.
