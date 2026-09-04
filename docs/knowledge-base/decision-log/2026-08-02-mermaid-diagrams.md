# 2026-08-02 — Mermaid diagrams in docs

Date: 2026-08-02
Session/task: Replaced ASCII diagrams with mermaid; added illustrative mermaid to data-flow sections.

## Decision

- Replaced 5 ASCII diagrams with ` ```mermaid ` flowcharts (both files under
  Git history plus the network-topology diagram in
  `docs/knowledge-base/architecture/ooc-strategic-v4.md`).
- Kept the ASCII version **alongside** mermaid in `ooc-strategic-v4.md` only.
- Added illustrative mermaid diagrams to six knowledge-base pages whose
  "Important data flow" sections were prose-only: `overview.md`,
  `out-of-combat.md`, `selfplay-loop.md` (bootstrap state machine + loop flow),
  `combat-search.md`, `training-and-inference.md`, `determinism-and-rng.md`.
- Documented the convention in `docs/knowledge-base/README.md`.

## Rationale

- Both ASCII and mermaid are plain text, so both are LLM-readable; the deciding
  factor is information fidelity. Structural diagrams that duplicate nearby
  prose were replaced; the V4 network contract keeps its ASCII because its
  exact concat ordering and rung-mask annotations are spec precision mermaid
  renders loosely (**Inference**: mermaid edge labels can express this, but
  less exactly, and the section is a fixed-topology contract).
- Mermaid renders on GitHub, where the plain-markdown docs are read by humans;
  the prose lists remain the LLM-facing source of truth.

## Alternatives considered

- Leave archives untouched — rejected: `ooc-action-plan-2026-08.md` is the
  active plan referenced by KB pages, and the superseded
  `combat-action-plan-2026-07.md` contains the same diagram style.
- Replace the V4 ASCII entirely — rejected for the fidelity reason above.

## Evidence

- Archived July 2026 combat and August 2026 OOC plans (converted diagrams)
- `docs/knowledge-base/architecture/ooc-strategic-v4.md` (kept both)
- `docs/knowledge-base/architecture/{overview,out-of-combat,combat-search,training-and-inference}.md`
- `docs/knowledge-base/behavior/determinism-and-rng.md`
- `docs/knowledge-base/operations/selfplay-loop.md`
- `docs/knowledge-base/README.md` (convention note)

## Status and follow-up

- Implemented; mermaid blocks not render-checked locally (no mermaid CLI on
  this machine) — verify on GitHub rendering or via `@mermaid-js/mermaid-cli`
  if a browser is available.
