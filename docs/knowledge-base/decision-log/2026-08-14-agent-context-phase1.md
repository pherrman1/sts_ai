# Agent-context Phase 1

Date: 2026-08-14

## Decision

Reduce the root `AGENTS.md` to the universal project contract and move its
detailed workflow/routing material into
`docs/knowledge-base/operations/agent-context-and-workflow.md`, existing
maintained KB pages, and the two existing Cline skills. Add a conservative root
`.clineignore` for generated/local state with explicit visibility preserved for
tracked deployable models and seed fixtures.

## Rationale

The prior root contract was 488 lines / 26,193 bytes and was intentionally
comprehensive, but most tasks do not need build-server details, benchmark
provenance, experiment reporting templates, or every domain-specific trap at
initial context load. **Inference:** CODE_MAP-first routing plus existing skills
and maintained pages preserves reachability while reducing unconditional context.

## Alternatives considered

- Delete detailed guidance — rejected because it would lose project knowledge.
- Split all material into new pages — rejected because existing maintained pages
  already own build, invariants, determinism, evaluation, self-play, and model
  facts.
- Ignore all self-play CSV/JSON/model files — rejected because tracked native
  deployable models and tracked `selfplay/ooc_buffer` fixtures must remain
  accessible.

## Evidence

- `AGENTS.md` — pre-change section audit and root-contract reduction.
- `docs/knowledge-base/operations/agent-context-and-workflow.md` — explicit
  relocation matrix and retained operating details.
- `.gitignore`; `git ls-files selfplay/models selfplay/ooc_buffer` — local
  artifact patterns and required tracked-file exceptions.
- `.cline/skills/implementation-review/SKILL.md`;
  `.cline/skills/research-experiment/SKILL.md` — retained progressive-disclosure
  procedures.

## Status

Implemented in Phase 1 only; no gameplay, search, ML, model artifact, or
experiment-result behavior changed.
