# StS AI agent contract

Last verified: 2026-09-26 for local research execution (ADR-0024); 2026-09-12 for documentation routing and completion boundaries.

## Purpose and authority

This repository builds an inspectable Ironclad agent for *Slay the Spire* on
the `sts_lightspeed` C++ simulator. The active integration executable is
`one_combat` (`apps/one_combat.cpp::main`).

When sources disagree, follow this order and update stale maintained knowledge
in the same change:

1. Executed code and executable behavior.
2. Tests and reproducible benchmark artifacts, within their stated
   configuration.
3. `CMakeLists.txt` for the target graph.
4. `EXPERIMENTS.md` plus `docs/experiments/ledger-*.md` for chronological
   experiment evidence.
5. `docs/knowledge-base/` for maintained current understanding.
6. `README.md` for human-facing orientation.

Do not invent rationale. Label unsupported conclusions **Inference**,
**Unverified**, or **Open question**.

## Task-dependent documentation routing

For tasks requiring real Slay the Spire interaction, live-mod verification,
game-state reproduction, or validation of CTM/Silver output, use the
`sts-live-game` skill and the configured `slay_the_spire` MCP server. Prefer
structured MCP control over native GUI interaction. Treat
`~/.cache/sts-model-inspector/latest.json` as machine-readable
inspector/advisor output and verify session/sequence/observationHash before
using a response.

Use [CODE_MAP.md](docs/knowledge-base/CODE_MAP.md) to locate unfamiliar code,
understand subsystem boundaries, or assess cross-subsystem changes. Read
maintained KB pages when the affected interface, invariant, procedure,
evaluation protocol, or research question requires them. For localized,
already-understood changes, start with the relevant code, tests, or docs. The
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
  that drives game seeds must go through the repository seed-run guard. Seed-based
  runs use the smallest justified experiment. Larger local runs require explicit
  authorization, with frozen provenance, seed ranges/counts, budgets, and
  decision rules recorded before execution; there is no fixed numerical ceiling. See
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

## Verification tiers

Run the tier a change needs, not everything. `python3 tools/agent/verify_changed.py`
picks it from the paths changed against `origin/main` (`--dry-run` prints the plan):

| Change | Tier | Checks |
|---|---|---|
| `docs/`, Markdown only | docs | repository health |
| Python/shell tooling, dashboards, default-off Python flags | python | repository health, affected test modules (900 s cap each), affected CTest entries; no C++ build |
| anything compiled, CMake, submodules | native | above, plus incremental Debug build in `build/linux-gcc-debug` and `ctest -L 'core\|smoke' -j<cores> --timeout 600` (the CI gate) |
| engine fix or default change | `--tier native` | the CI gate, plus the independent review |

- Never use a Release build (`-O3 -flto`, ~30 min on 4 cores) as verification;
  build Release only for a binary that will actually run games.
- Reuse the build directory; do not wipe it or configure a fresh one per check.
  An incremental rebuild after a one-file change takes under 30 s.
- Do not run the whole Python suite (`pytest tests/`) or the unfiltered CTest
  suite for a small change. Run them only when the tier says so or the user asks.
- A timeout or failure in a known flaky test (`test_run_train_resume`,
  `az_eval_cache_ema_amber`, `az_eval_cache_compact`) is reported as
  pre-existing, not chased.

## Workflow-v2 handoff boundary

Continue the requested change through implementation, affected checks, repair
of failures caused by the change, rerunning affected checks, final diff
inspection, and the permitted draft-PR handoff. Do not stop merely because the
first implementation is complete or an ordinary check failed. Stop when the
completion criteria are met, progress is blocked without new evidence, a
material design decision is missing, or an existing permission, safety, or
review boundary is reached; report any blocker.

This repair loop does not override the seed guard or local seed ceiling,
worktree/Git restrictions, preservation of ignored data, model/schema/RNG
invariants, experimental provenance, independent scientific review, or PR/CI
publication boundaries.

The draft pull request is the Codex-to-reviewer handoff. It must include an
evidence packet: baseline and reviewed SHA, scope, changed paths, checks run
and their raw outcomes, checks not run, and remaining uncertainty. Minor review
corrections continue the same Codex session. A conceptual redesign, new
hypothesis, or changed success criterion starts a new session. After
implementation review passes, freeze the reviewed SHA before any expensive
scientific run.

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
