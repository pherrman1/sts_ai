# E2c-v2 production closure and maintenance follow-up

## Date and context

2026-08-22. Review of the designated GCP E2c-v2 2,000-seed production
dataset, followed by two independent maintenance fixes.

## Decision

Close E2c-v2 as **E2C SUPPORTED** and stop at 2,000 seeds. The 20 quarantined
runs remain an implementation-selection-bias caveat: all 40 health failures
were Secret Technique/Secret Weapon selection failures.

Fix Searcher3 by reconciling raw draw-pile-index card-select edges against the
live root before selecting an action, with a focused regression. Ignore the
launcher-created repository-root `/logs/` runtime artifacts so provenance no
longer reports them as source dirtiness.

## Evidence and limits

Production SHA `e029dffb4c72449e8fc5b874391c49a27b2f6a81`; dataset SHA-256
`da692d5979f9df3cad70ee6d76bd34fcf174ac74f557b942fb662e3d8c6a89e2`.
Full evidence is in `docs/experiments/ledger-06.md`. The result supports an
offline RAW-terminal predictor; it does not establish online MCTS action or
win-rate improvement. The production dataset is not regenerated.

The changes are committed and pushed on the reviewed branch. A future
provenance redesign may separately report tracked-source dirtiness and
untracked runtime artifacts.
