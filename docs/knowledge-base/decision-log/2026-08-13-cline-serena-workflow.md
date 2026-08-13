# 2026-08-13 — Cline harness with Serena semantic tooling

Date: 2026-08-13

## Decision

The repository's local AI workflow is migrated conceptually from the legacy
OpenCode-specific contract to Cline Plan/Act with Serena as the preferred
semantic code-intelligence layer. `AGENTS.md` remains the canonical,
tool-independent project policy. The existing OpenCode configuration is
retained temporarily for rollback and is not mechanically translated.

## Rationale

Cline already provides planning, implementation, terminal execution, approval
gates, and optional subagents. Serena supplies symbol navigation, definitions,
references, and targeted semantic refactoring. The project-specific behavior
that must remain is in `AGENTS.md`, `tools/seed_guard.sh`, the build/test graph,
the knowledge base, the experiment ledger, and the decision log. A second
orchestration framework would duplicate native harness capabilities.

## Evidence

- Serena connected to the active `sts_ai` project with the C++ language server.
- Serena returned a symbol overview for `apps/one_combat.cpp` and completed a
  reference lookup for `WinNet/predict` without modifying source code.
- `tools/ai_cycle.py` and its tests are not present in the current tracked tree;
  historical records identify that orchestration as superseded.
- The migration changes only `AGENTS.md`, `.gitignore`, and two reusable Cline
  skills; OpenCode files and gameplay/research implementation remain untouched.

## Alternatives considered

- Mechanically translate `opencode.json` into Cline configuration — rejected:
  Cline's native Plan/Act and approval model is the intended harness boundary.
- Add `tools/cline_cycle.py` immediately — rejected: no current wrapper gap has
  been demonstrated, and bounded verification remains project policy rather
  than a second agent framework.
- Migrate `.ai/`, `.pi/`, or enable Serena memory — rejected: these are
  transient or historical state, not durable project knowledge.

## Status and follow-up

Implemented as the initial migration. Validate the workflow with small
documentation, semantic-investigation, Plan→Act, and research-methodology
tasks before considering deletion of the retained OpenCode rollback files.