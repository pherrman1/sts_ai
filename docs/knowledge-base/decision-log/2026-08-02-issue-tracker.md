# 2026-08-02 — Issue tracker in the knowledge base

Date: 2026-08-02
Session/task: Collect knowledge-base issues and sort by importance.

## Decision

Created `docs/knowledge-base/issues/README.md` as a prioritized index of known
issues extracted from the knowledge-base pages, with one entry file per issue
(`2026-08-02-issue-NN-<slug>.md`). Tiers: Critical (silently invalidates
measurements), High (blocks operation/validity), Medium (tooling/evidence
gaps), Low (debt/design). Entries record status, tier, symptom, evidence with
repository-relative paths, why it matters, a candidate fix direction, and a
`Closed by` slot; they are closed by a fixing commit/test, never rewritten.

## Rationale

- The knowledge base documents 30+ issues across its "Known limitations",
  "Blocking discrepancies", and "Open questions" sections, but no single
  place prioritized or tracked them; the `investigations/README.md` candidate
  list covers only 7 of them.
- A prioritized index makes the next working session pick the highest-value
  item without re-reading every page.
- Entry-per-issue lets issues be closed by fixes without rewriting history,
  matching the decision-log convention.

## Alternatives considered

- Response-only list — rejected: knowledge would be lost and not maintained.
- Restructuring `investigations/` into the issue list — rejected:
  investigations have a different contract (reproducible diagnoses); issues
  are the broader superset, so the index links them instead.
- A single page with all issues — rejected: no per-issue close-by tracking.

## Evidence

- `docs/knowledge-base/issues/README.md` — 30-entry prioritized index.
- `docs/knowledge-base/issues/2026-08-02-issue-01-…md` … `issue-30-…md`.
- Source pages: `architecture/combat-search.md`, `architecture/out-of-combat.md`,
  `architecture/overview.md`, `architecture/training-and-inference.md`,
  `behavior/determinism-and-rng.md`, `behavior/invariants.md`,
  `evaluation/current-baselines.md`, `evaluation/benchmark-protocol.md`,
  `operations/build-and-debugging.md`, `operations/selfplay-loop.md`,
  `investigations/README.md`.
- Symbols verified during collection: `BattleScumSearcher3::BattleScumSearcher3`
  (`src/sim/search/BattleScumSearcher3.cpp`), `Belief::update`/`Belief::sample`
  (`src/sim/search/CombatObservation.cpp`), `bestBench`
  (`apps/one_combat.cpp`), `paired_analysis.py::load`,
  `selfplay/loop.sh::baseline_cache_key`/`start_server`/`gate_stats`.

## Status and follow-up

- Implemented in this session; no issue fixed.
- Follow-up: close entries with fixing commits/tests as they land; append new
  issues to the index as the knowledge base evolves.
