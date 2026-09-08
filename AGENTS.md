# StS AI agent contract

Last verified: 2026-09-08 against the current working tree.

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
Use [operations/agent-context-and-workflow.md](docs/knowledge-base/operations/agent-context-and-workflow.md)
for the full agent-workflow contract, the AGENTS relocation audit, safe Git
procedure, documentation/decision/experiment recording, and deeper safety
routing.

## Work principles

- Inspect `git status` before editing; preserve unrelated and ignored local
  data.
- Distinguish Codex app-managed worktrees from manually/CLI-managed linked
  worktrees. The Codex app may create and remove its own worktrees, and an
  app-created worktree may initially be on a detached `HEAD`. After entering
  one, run `python tools/agent/worktree.py preflight .` so external read-only
  Git metadata is identified before branch, staging, or commit operations,
  then validate it with `python tools/agent/worktree.py check .`; if pinned
  submodules are not initialized or are at the wrong revisions, use
  `python tools/agent/worktree.py repair .` before configuring or building.
- For manual or CLI-managed linked-worktree creation and removal, use
  `python tools/agent/worktree.py`; do not bypass it with raw Git commands.
- State the success criterion and cheapest proving check. Make the smallest
  scoped change that satisfies the request; do not bundle cleanup, refactors,
  gameplay, model, or research changes.
- Use the [codex-implementation skill](.agents/skills/codex-implementation/SKILL.md)
  for ordinary implementation, debugging, build, test, and PR tasks when no
  specialized research or review skill applies.
- When asked to review recent Codex sessions for repeated inefficiency,
  rediscovery, or workflow improvement, use the
  [session-retrospective skill](.agents/skills/session-retrospective/SKILL.md).
  Its persistent lessons are evidence, not project truth; route durable facts
  to the canonical KB, code, or decision destination.
- Use the repo-grounded ChatGPT/Sol handoff as the accepted design plan when it
  includes the baseline, goal/hypothesis, verified repo facts, required
  behavior, non-goals, and verification criteria. Codex performs a bounded
  local preflight and does not restart broad research or planning unless local
  evidence materially contradicts the handoff. Use Git, `rg`, focused file
  reads, compiler diagnostics, and focused tests. No repository MCP server is
  required.
- One coordinating Codex session may delegate native subtasks within that
  accepted design when independent inspection, non-overlapping implementation,
  or verification makes execution cheaper or faster. Subtasks execute rather
  than redesign the plan: avoid duplicate investigation, competing
  implementations, overlapping edits, and scope expansion. Subtasks for one
  accepted change may share its worktree; use separate worktrees for
  independent branches or experiments.
- Use the cheapest focused verification that proves the change. Every command
  that drives game seeds must go through the repository seed-run guard. Local
  automated execution is capped at 128 seeds. Large research sweeps run
  through the designated GCP research path, which has no fixed seed ceiling;
  agents choose the smallest sample justified by the experiment design. See
  [build-and-debugging.md](docs/knowledge-base/operations/build-and-debugging.md)
  and the [research-experiment skill](.agents/skills/research-experiment/SKILL.md).
- GitHub Actions CI (`.github/workflows/ci.yml`) is the authoritative
  repository verification check. Changes should reach `main` through a pull
  request only after the `Linux GCC` check passes. Branch-protection enforcement
  is not currently available for this private repository on its GitHub plan.
- Before completion, classify the task's durable knowledge impact and update
  its authoritative destination in the same change. Record
  `Knowledge impact: none` with a brief reason when no maintained knowledge
  change is warranted.

## Workflow-v2 handoff boundary

The draft pull request is the Codex-to-reviewer handoff. It must include an
evidence packet: baseline and reviewed SHA, scope, changed paths, checks run
and their raw outcomes, checks not run, and remaining uncertainty. Minor review
corrections continue the same Codex session. A conceptual redesign, new
hypothesis, or changed success criterion starts a new session. After repeated
failures or unresolved conceptual ambiguity, stop and report the blocker rather
than wandering into unbounded re-investigation. After implementation review
passes, freeze the reviewed SHA before any expensive scientific run.

## Critical safety and Git rules

- Combat termination is `bc.outcome == Outcome::UNDECIDED`; `isBattleOver()` is
  derived. Preserve documented state, RNG, model-load, schema, and fair-vs-
  known-RNG invariants; route to the relevant page from `CODE_MAP.md`.
- Never treat a model file as proof it loaded or was used. Do not delete ignored
  self-play data casually. Do not use broad `pkill -f v_server.py`.
- For manual or CLI-managed linked-worktree lifecycle operations, use only
  `python tools/agent/worktree.py create|check|repair|remove`. The Codex app
  may create or remove its own app-managed worktrees; after entering one,
  validate or repair its pinned submodules with the same `check`/`repair`
  commands. Do not use raw `git worktree add`, `git worktree remove`, `git
  submodule deinit`, or manual submodule initialization in linked worktrees.
  If the lifecycle tool cannot complete a manual operation, stop and report
  the failure instead of bypassing it.
- Stage only task-scoped changes. Never rewrite history, force-push, delete
  branches, or push from `main`. After successful verification and commit,
  follow the controlled task-branch first-push and PR procedure in the
  workflow page; an explicit user instruction not to commit or push overrides
  it.

## Deeper instructions

- [Build and debugging](docs/knowledge-base/operations/build-and-debugging.md)
- [Benchmark protocol](docs/knowledge-base/evaluation/benchmark-protocol.md)
- [Self-play loop](docs/knowledge-base/operations/selfplay-loop.md)
- [Invariants](docs/knowledge-base/behavior/invariants.md) and
  [determinism/RNG](docs/knowledge-base/behavior/determinism-and-rng.md)
- [Decision routing](decisions/README.md) and
  [experiment ledger](EXPERIMENTS.md)
- [Implementation-review skill](.agents/skills/implementation-review/SKILL.md)
  and [research-experiment skill](.agents/skills/research-experiment/SKILL.md)

Documentation routing is frozen by ADR-0012: current facts go to the maintained
knowledge base, durable choices to ADRs, experiments to the ledger, unresolved
diagnoses to investigations, and temporary task detail to PRs or commits only.
Do not add per-session historical entries; route current facts to maintained
pages, ADRs, experiment ledgers, or investigations.
