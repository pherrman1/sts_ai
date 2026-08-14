# StS AI agent contract

Last verified: 2026-08-14 against the current working tree.

## Purpose and authority

This repository builds an inspectable Ironclad agent for *Slay the Spire* on
the `sts_lightspeed` C++ simulator. The active integration executable is
`one_combat` (`apps/one_combat.cpp::main`).

When sources disagree, follow this order and update stale maintained knowledge
in the same change:

1. Executed code and executable behavior.
2. Tests and reproducible benchmark artifacts, within their stated
   configuration.
3. `CMakeLists.txt` for the target graph; `selfplay/loop.sh` for self-play and
   gate mechanics.
4. `EXPERIMENTS.md` plus `docs/experiments/ledger-*.md` for chronological
   experiment evidence.
5. `docs/knowledge-base/` for maintained current understanding.
6. `README.md` for human-facing orientation.

Do not invent rationale. Label unsupported conclusions **Inference**,
**Unverified**, or **Open question**.

## Navigate before changing

Start with [CODE_MAP.md](docs/knowledge-base/CODE_MAP.md), then read the
relevant linked maintained page before broad search or edits. The
[knowledge-base index](docs/knowledge-base/README.md) routes architecture,
behavior, evaluation, operations, research, decisions, and investigations.
`docs/archive/` is historical, not current instruction.

Use [operations/agent-context-and-workflow.md](docs/knowledge-base/operations/agent-context-and-workflow.md)
for the full agent-workflow contract, the AGENTS relocation audit, safe Git
procedure, documentation/decision/experiment recording, and deeper safety
routing.

## Work principles

- Inspect `git status` before editing; preserve unrelated and ignored local
  data.
- State the success criterion and cheapest proving check. Make the smallest
  scoped change that satisfies the request; do not bundle cleanup, refactors,
  gameplay, model, or research changes.
- Use Cline for interactive work, Serena for live semantic code navigation and
  approved semantic refactoring, RepoWise only for advisory architecture/history
  signals, and targeted reads plus the maintained KB for evidence. Code, tests,
  ledgers, maintained KB pages, and accepted ADRs override tool-generated
  summaries.
- Use the cheapest focused verification that proves the change. Every command
  that drives game seeds must go through the repository seed-run guard. Local
  automated execution is capped at 128 seeds. Large research sweeps run
  through the designated GCP research path, which has no fixed seed ceiling;
  agents choose the smallest sample justified by the experiment design. See
  [build-and-debugging.md](docs/knowledge-base/operations/build-and-debugging.md)
  and the [research-experiment skill](.cline/skills/research-experiment/SKILL.md).
- GitHub Actions CI (`.github/workflows/ci.yml`) is the authoritative
  repository verification check. Changes should reach `main` through a pull
  request only after the `Linux GCC` check passes. Branch-protection enforcement
  is not currently available for this private repository on its GitHub plan.

## Critical safety and Git rules

- Combat termination is `bc.outcome == Outcome::UNDECIDED`; `isBattleOver()` is
  derived. Preserve documented state, RNG, model-load, schema, and fair-vs-
  known-RNG invariants; route to the relevant page from `CODE_MAP.md`.
- Never treat a model file as proof it loaded or was used. Do not delete ignored
  self-play data casually. Do not use broad `pkill -f v_server.py`.
- Do not create Serena memories, commit `.repowise/`, or use paid RepoWise
  generation without explicit authorization. RepoWise dead-code results are
  hypotheses, not deletion authority.
- Stage only task-scoped changes. Never rewrite history, force-push, delete
  branches, or push a remote/refspec. Follow the commit/push procedure in the
  workflow page; an explicit user instruction not to commit or push overrides
  it.

## Deeper instructions

- [Build and debugging](docs/knowledge-base/operations/build-and-debugging.md)
- [Benchmark protocol](docs/knowledge-base/evaluation/benchmark-protocol.md)
- [Self-play loop](docs/knowledge-base/operations/selfplay-loop.md)
- [Invariants](docs/knowledge-base/behavior/invariants.md) and
  [determinism/RNG](docs/knowledge-base/behavior/determinism-and-rng.md)
- [Decision log](docs/knowledge-base/decision-log/README.md) and
  [experiment ledger](EXPERIMENTS.md)
- [Implementation-review skill](.cline/skills/implementation-review/SKILL.md)
  and [research-experiment skill](.cline/skills/research-experiment/SKILL.md)
