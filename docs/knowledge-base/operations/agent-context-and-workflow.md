# Agent context and workflow

Last verified: 2026-09-04 against the current working tree.

## Purpose

Keep `AGENTS.md` a small universal contract while preserving the detailed
workflow, safety, and recording guidance needed only after a task is routed.
Read this page after [CODE_MAP.md](../CODE_MAP.md) when an agent needs the
implementation, review, experiment, documentation, or Git procedure.

## Current implementation

`AGENTS.md` contains the project purpose, authority hierarchy, CODE_MAP-first
navigation, minimal-change principle, bounded Codex handoff boundary,
seed-guard rule, critical safety/Git rules, and links here. Repository skills
under `.agents/skills/` provide progressive disclosure for ordinary
implementation, research, and implementation review. `.codex/config.toml`
contains conservative repository-scoped Codex sandbox defaults. The normal
Codex path is MCP-free.

### Workflow-v2 operating boundary

The external ChatGPT/Sol handoff is an accepted design plan when it states the
baseline commit or branch, goal and hypothesis when research-facing, relevant
facts verified against the current repository, required behavior, explicit
non-goals, and cheapest verification criteria with expected evidence.

Within this workflow, a `Session` is the coordinating Codex session. It may use
native subtasks under the same accepted design when independent inspection,
non-overlapping implementation, or verification makes execution cheaper or
faster. Those subtasks do not independently redesign the plan or expand its
scope, and the coordinator retains responsibility for integration, final diff
inspection, verification, and the PR evidence packet. Subtasks for one accepted
change may share its worktree; separate worktrees are for independent branches
or experiments, not individual subtasks.

Codex's bounded preflight is limited to checking branch/HEAD/status and
upstream divergence; reading `AGENTS.md`, `CODE_MAP.md`, the routed page and
relevant symbols/tests; checking handoff paths and assumptions; and identifying
contradictions, missing prerequisites, or unsafe scope. It may refine an
implementation detail from local evidence, but must not repeat broad
literature review, architecture discovery, or experiment redesign when the
handoff is consistent. A material contradiction changes the baseline, required
behavior, affected subsystem, safety constraint, or verification decision rule.

The draft PR is the implementation-to-reviewer handoff. Its evidence packet
records the baseline, final reviewed SHA, changed paths, exact checks and
outcomes, omitted checks, and open uncertainty. The reviewer separates
implementation correctness from scientific-design quality. A minor correction
continues the same Codex session; a conceptual redesign, new hypothesis, or
changed success criterion starts a new session. After repeated failures or
conceptual ambiguity, stop and report the blocker. Once implementation review
passes, freeze the reviewed SHA before expensive scientific runs. Keep mutable
run state such as "CI pending" out of the durable PR description: GitHub checks
are authoritative, and a short SHA-tied comment may record a later transition.

### AGENTS.md relocation audit (Phase 1)

| Previous `AGENTS.md` section | Destination | Treatment |
| --- | --- | --- |
| Purpose and required reading | `AGENTS.md`, KB index, this page | Condensed universal contract; detailed reading routes remain linked. |
| Authoritative sources | `AGENTS.md` | Kept as the universal source hierarchy. |
| Repository map | `CODE_MAP.md`; [architecture overview](../architecture/overview.md); [self-play loop](selfplay-loop.md); [tools README](../../../tools/README.md) | Existing subsystem maps remain authoritative; artifact handling is below. Legacy `.opencode/`/`opencode.json` rollback configuration remains documented in `CODE_MAP.md`. |
| Agent workflow and tool routing | `AGENTS.md`; [ADR-0011](../../../decisions/0011-mcp-free-codex-skillopt-pilot.md); this page | Concise routing stays universal; operating limits are retained below. ADR-0010 and ADR-0008 remain historical records. |
| Agent context and large-file navigation | This page | Retained below as focused-reading guidance. |
| Build and focused checks | [build and debugging](build-and-debugging.md); this page | Commands, target graph, GCP details, and caveats remain on the build page. |
| Build and focused checks / Automated agent verification limits | [build and debugging](build-and-debugging.md); `AGENTS.md`; [ADR-0006](../../../decisions/0006-automated-game-seed-limit.md); research skill | Commands, target graph, GCP details, guard rule, and sample guidance remain reachable. |
| Modification workflow / Default completion: commit and push | This page | Retained below. |
| Research experiment handoffs | [research-experiment skill](../../../.agents/skills/research-experiment/SKILL.md) | The skill is the progressive-disclosure procedure. |
| Critical safety and correctness traps | [invariants](../behavior/invariants.md), [determinism/RNG](../behavior/determinism-and-rng.md), [benchmark protocol](../evaluation/benchmark-protocol.md), [self-play loop](selfplay-loop.md), [environment variables](environment-variables.md), [architecture overview](../architecture/overview.md) | Existing maintained pages hold the technical facts; the routing list below preserves every former trap. |
| Documentation maintenance / Decision logging / Experiment-recording rules / Definition of done | [KB index](../README.md), [decision records](../../../decisions/README.md), [research-experiment skill](../../../.agents/skills/research-experiment/SKILL.md), this page | Current routing is retained below; historical session material is in Git history only. |
| Prohibited assumptions | This page and the linked technical pages | Retained as an operational checklist below. |

### Focused context navigation

- Search for a symbol, mode, experiment number, keyword, caller, artifact, or
  date before reading a large source/history file. Read a focused symbol or
  region, then expand only when dependencies require it.
- Search `EXPERIMENTS.md` before reading a ledger shard. Identify subsystem
  boundaries before reading the integration driver.
- Do not inspect generated `build/` artifacts, ignored self-play data,
  or `.ai/` unless the task requires them. Reviewers may expand
  scope when necessary to prove semantics.
- Use Git, `rg`, focused file reads, compiler diagnostics, and focused tests.
  No repository MCP server is required.

### Artifact and local-data handling

`models/` and `selfplay/models/*.native` are deployable tracked artifacts;
trainer checkpoints (`*_state.bin`, `.pt`, `.npz`, `.torchscript`), buffers,
CSVs, and other loop state are local handoff data. A deployable retraining
change ships its artifact, hash, and documentation together. Artifact presence
does not prove runtime loading or branch use. See
[ADR-0005](../../../decisions/0005-deployable-models-are-versioned-artifacts.md),
[training and inference](../architecture/training-and-inference.md), and
[self-play loop](selfplay-loop.md).

## Important data flow

1. Read `AGENTS.md` for universal constraints.
2. Route through `CODE_MAP.md` and the relevant maintained page.
3. Use the ordinary implementation skill unless a specialized research or
   review skill applies. The research skill distinguishes an external-handoff
   path from a Codex-originated-research path.
4. Inspect status, state the success criterion, make the smallest change, and
   run the cheapest proving check.
5. Inspect the complete diff and record documentation, decisions, or experiment
   evidence at the authoritative destination.
6. Stage only task changes, commit one focused change, and push only when the
   procedure below permits it.

## Invariants and assumptions

### Verification and build procedure

Build and target details are authoritative in `CMakeLists.txt` and documented
in [build and debugging](build-and-debugging.md). Build the relevant target
before running it; fresh clones and linked worktrees need their own initialized
submodules. Never claim
a configure/build/toolchain result that was not performed in the reported
environment. Header-layout changes to `Node`, `Edge`, or searcher structures
require every including translation unit to be rebuilt.

Use the cheapest proving check. All game-seed commands must use
`tools/seed_guard.sh`. Local automated execution is capped at 128 seeds:
prefer 8–16 seeds for iterative smoke checks, at most 32 for ordinary focused
validation, and at most 64 when a small statistical check is sufficient. Large
research runs use the tracked
[`tools/agent/gcp_benchmark.py`](../../../tools/agent/gcp_benchmark.py) path on
`sts-test`; its explicit `--gcp-research` guard mode has no numeric ceiling.
Agents may choose a justified GCP seed count without a separate approval step,
but must state the scientific design and use the smallest informative sample.
Long-run details are in [build and debugging](build-and-debugging.md).

### Modification and Git procedure

1. Capture `git status --short` before editing and preserve unrelated changes
   and ignored data. Record the current branch, `origin` URL, and baseline
   `HEAD`; when an upstream exists, also record
   `git log --oneline @{upstream}..HEAD`.
2. Read the routed KB page, implementation, and focused tests. State the
   behavioral success criterion and cheapest proving check. Ask when a material
   interpretation is genuinely ambiguous. Native subtasks within the same
   accepted change may share the coordinating session's worktree; parallelize
   only independent work and avoid duplicate investigation, competing
   implementations, overlapping edits, and scope expansion. The Codex app may
   create and remove its own app-managed worktrees. An app-managed worktree may
   begin on detached `HEAD`; before committing or pushing, create or switch to
   the task branch. After entering one, run
   `python tools/agent/worktree.py check .` and use `repair .` if pinned
   submodules are not initialized or correct. CLI/manual linked-worktree
   creation and removal remain on the `python tools/agent/worktree.py` path,
   which initializes, verifies, and safely discards checkout-specific
   submodules. For a fresh clone or existing checkout, run `repair` before
   configuring. See [build and debugging](build-and-debugging.md).
3. Make the smallest scoped change; do not improve adjacent code, comments, or
   formatting. For a feasible bug fix, add a reproducing test first. Rebuild all
   affected translation units and run focused checks before broader checks.
4. Inspect `git diff --check`, the complete diff, status, paths, symbols, and
   generated artifacts. Stage only task-scoped files. For coupled command-line
   inputs, booleans that may be explicitly false, or backend-specific required
   fields, enumerate the small truth table before publication: all present,
   each independently omitted, all omitted, and each meaningful mismatch. For
   an expected boolean, cover both successful values (expected/actual true and
   expected/actual false), omission, and both mismatch directions. Exercise
   those states with focused tests instead of relying only on one successful
   path.
5. A changed handoff normally creates one focused commit. Before publishing,
   compare the committed range with the recorded baseline and confirm that
   only task-scoped commits would be sent. Re-sync a moving base before final
   verification only when its movement affects relevant paths or behavior,
   mergeability, or the task decision; unrelated movement alone does not
   justify rebuilding or repeating evidence. Tie final evidence to one
   candidate SHA. If a later review correction changes evidence-relevant
   behavior, repeat only the affected evidence on the corrected candidate. If
   the current task created a new,
   non-`main` branch with no upstream, the agent may establish exactly
   `origin/<current-branch>` with `git push --set-upstream origin HEAD` only
   after all of the following are true: implementation and focused
   verification succeeded; the task changes are committed; `origin` is the
   intended remote; no unrelated pre-existing local commits would be
   published; and the remote branch is absent or has no unexpected/unrelated
   history. Otherwise, stop and report the push blocker. Once an upstream
   exists, use plain `git push`. Never force-push, rewrite history, delete
   branches, push to/from `main`, or enable Git's global `autoSetupRemote`.
   Do not create an empty commit for read-only work.

6. For nontrivial successful branch work, the default completion is focused
   commit, permitted push, and creation or update of a draft pull request when
   the repository's PR workflow supports it. Keep the existing PR-centered
   workflow-v2 semantics: `main` receives changes through a pull request after
   the authoritative CI check passes; do not merge, approve, or bypass that
   review path automatically. Record exact commands and artifact paths in the
   PR body; for long or quote-sensitive bodies, write a UTF-8 body file and pass
   it to the GitHub CLI rather than constructing a shell-escaped inline string.

### Recording and documentation

Classify durable knowledge impact before completion and update the single
authoritative destination in the same change. If no maintained knowledge
change is warranted, record `Knowledge impact: none` with a brief reason.

| Learned information | Destination |
| --- | --- |
| Stable current architecture, behavior, invariant, interface, schema, environment, build, or operational fact | Relevant maintained KB page |
| Changed navigation path or important symbol | `CODE_MAP.md` |
| Benchmarked result, including null, negative, inconclusive, or invalid | Experiment ledger plus evidence |
| Active, parked, or closed research status | `evaluation/current-research.md` |
| Qualified production default or headline baseline | `evaluation/current-baselines.md` |
| Durable architecture or workflow decision | ADR |
| Reproducible unresolved diagnosis | Investigation page |
| Temporary task detail | Do not preserve |

Update the relevant KB page when code changes architecture, model interfaces,
environment variables, training/self-play pipelines, benchmark protocols,
deployed configuration, build commands, invariants, schemas, artifact formats,
or documented limitations. Technical pages retain Purpose, Current
implementation, Important data flow, Invariants and assumptions, Relevant code,
Known limitations, Open questions when applicable, and Last verified date.

Put benchmarked outcomes—including negative/inconclusive/invalid results—in the
current `EXPERIMENTS.md` ledger shard with mode, flags, artifacts/hashes,
budget, ascension, seeds, threads, regime, searcher, OOC configuration, metric,
schema, and artifact location. Use paired common seeds and keep offline,
combat-only, Act-clear, and full-run outcomes distinct. Current headline
qualification belongs only in `evaluation/current-baselines.md`.

Do not add per-session historical entries. Route current facts to the maintained knowledge base, durable choices
to an ADR, benchmarked outcomes to `EXPERIMENTS.md`, and reproducible
unresolved diagnoses to `investigations/`. Temporary task detail belongs in
the PR or commit only. Existing dated entries are retained unchanged.

### Safety routing checklist

- Combat termination, live action validation, map detachment, layout rebuilds,
  model/schema contracts, and bindings: [invariants](../behavior/invariants.md)
  and [architecture overview](../architecture/overview.md).
- Project-fair vs known-RNG separation, Searcher2/3 behavior, particle fallback,
  and counterfactual RNG: [determinism and RNG](../behavior/determinism-and-rng.md)
  and [combat search](../architecture/combat-search.md).
- Model/environment consumption, `STS_DIST_VNET`, `STS_PVNET`, and arm-specific
  load verification: [environment variables](environment-variables.md) and
  [training and inference](../architecture/training-and-inference.md).
- `bestbench` provenance, producer/consumer headers, paired comparisons, and
  `runtrace` limits: [benchmark protocol](../evaluation/benchmark-protocol.md)
  and [build and debugging](build-and-debugging.md).
- Native OOC/server distinction, exact server PID handling, self-play bootstrap,
  and expensive append/resume-safe buffers: [self-play loop](selfplay-loop.md).
- Expert policy features and restrictions on new hand-authored objectives:
  [combat search](../architecture/combat-search.md).

## Known limitations

The concise root contract cannot enumerate subsystem-specific facts. `CODE_MAP`
and the technical pages above must be consulted before changing a subsystem.
Codex searches must honor the focused-context exclusions above and normal Git
ignore boundaries. Tracked deployable models, source, maintained docs, tests,
and recorded experiment evidence remain available when the task requires them.

## Open questions

None for this workflow split. Future context reductions should update the
relocation audit rather than silently deleting an instruction.

## Agent mechanical guardrails

### Codex app and CLI

Repository-scoped Codex defaults live in `.codex/config.toml`. They select the
`workspace-write` sandbox, retain approval-on-request, disable sandboxed network
access, and configure no repository MCP server. Codex must be launched with
this Git worktree as its root so project configuration, skills, and paths agree.

The Codex desktop app may manage the creation and removal of its own linked
worktrees. Treat an app-created detached `HEAD` as valid pre-branch state;
validate it with `python tools/agent/worktree.py check .` and repair pinned
submodules with `repair .` when needed. The CLI remains the maintenance and
manual-worktree path; use `create|check|repair|remove` there and never raw
`git worktree add` or `git worktree remove`. Create or switch to a task branch
in an app-managed worktree before committing or pushing.

No repository Codex hook adapter is configured. The mechanical execution
boundary for seeded game commands is `tools/seed_guard.sh`, while sandboxing,
approvals, `AGENTS.md`, and the completion checks below provide the remaining
layers. Never use `--dangerously-bypass-approvals-and-sandbox` for repository
work.

Before completion, run the cheapest relevant tests plus `git diff --check`,
inspect the complete diff and untracked files, and report checks that were not
run. C++/CMake changes require focused build/test verification; GitHub Actions
Linux GCC remains the authoritative repository check.

Do not hold the session inside an unbounded foreground CI watcher such as
`gh run watch` or `gh pr checks --watch`. Query once with `gh run view` or
`gh pr checks`, continue independent local work when possible, and poll again
at a bounded interval. A pending or queued run is status, not a reason to make
the agent unresponsive; report the latest conclusion after each poll.

### Legacy command-policy evaluation fixture

`tools/agent/cline_guardrails.py` and its focused tests remain because the
model-agnostic `guardrail-command-policy` coding-agent evaluation task invokes
them and CI runs the evaluator tests. They are not connected to Codex or to any
active repository hook and must not be described as runtime enforcement. The
retired runtime configuration and its historical rationale remain available in
the dated decision records.

## Relevant code

- `AGENTS.md`
- `.agents/skills/implementation-review/SKILL.md`
- `.agents/skills/research-experiment/SKILL.md`
- `.agents/skills/codex-implementation/SKILL.md`
- `.codex/config.toml`
- `docs/knowledge-base/operations/skillopt-sleep.md`
- `tools/seed_guard.sh`
- `tools/agent/eval.py`; `tools/agent/cline_guardrails.py`
- `.gitignore`
- `docs/knowledge-base/CODE_MAP.md`; `docs/knowledge-base/README.md`
