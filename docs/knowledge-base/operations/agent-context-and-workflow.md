# Agent context and workflow

Last verified: 2026-08-14 against the current working tree.

## Purpose

Keep `AGENTS.md` a small universal contract while preserving the detailed
workflow, safety, and recording guidance needed only after a task is routed.
Read this page after [CODE_MAP.md](../CODE_MAP.md) when an agent needs the
implementation, review, experiment, documentation, or Git procedure.

## Current implementation

`AGENTS.md` contains the project purpose, authority hierarchy, CODE_MAP-first
navigation, minimal-change principle, concise tool routing, seed-guard rule,
critical safety/Git rules, and links here. Cline skills provide progressive
disclosure for research experiments and implementation reviews.

### AGENTS.md relocation audit (Phase 1)

| Previous `AGENTS.md` section | Destination | Treatment |
| --- | --- | --- |
| Purpose and required reading | `AGENTS.md`, KB index, this page | Condensed universal contract; detailed reading routes remain linked. |
| Authoritative sources | `AGENTS.md` | Kept as the universal source hierarchy. |
| Repository map | `CODE_MAP.md`; [architecture overview](../architecture/overview.md); [self-play loop](selfplay-loop.md); [tools README](../../../tools/README.md) | Existing subsystem maps remain authoritative; artifact handling is below. Legacy `.opencode/`/`opencode.json` rollback configuration remains documented in `CODE_MAP.md`. |
| Agent workflow / Cline, Serena, and RepoWise routing | `AGENTS.md`; [ADR-0008](../../../decisions/0008-guarded-cline-serena-repowise-routing.md); this page | Concise routing stays universal; operating limits are retained below. |
| Agent context and large-file navigation | This page | Retained below as focused-reading guidance. |
| Build and focused checks | [build and debugging](build-and-debugging.md); this page | Commands, target graph, GCP details, and caveats remain on the build page. |
| Build and focused checks / Automated agent verification limits | [build and debugging](build-and-debugging.md); `AGENTS.md`; [ADR-0006](../../../decisions/0006-automated-game-seed-limit.md); research skill | Commands, target graph, GCP details, guard rule, and sample guidance remain reachable. |
| Modification workflow / Default completion: commit and push | This page | Retained below. |
| Research experiment handoffs | [research-experiment skill](../../../.cline/skills/research-experiment/SKILL.md) | The skill is the progressive-disclosure procedure. |
| Critical safety and correctness traps | [invariants](../behavior/invariants.md), [determinism/RNG](../behavior/determinism-and-rng.md), [benchmark protocol](../evaluation/benchmark-protocol.md), [self-play loop](selfplay-loop.md), [environment variables](environment-variables.md), [architecture overview](../architecture/overview.md) | Existing maintained pages hold the technical facts; the routing list below preserves every former trap. |
| Documentation maintenance / Decision logging / Experiment-recording rules / Definition of done | [KB index](../README.md), [decision log](../decision-log/README.md), [research-experiment skill](../../../.cline/skills/research-experiment/SKILL.md), this page | Recording destinations and completion procedure are retained below. |
| Prohibited assumptions | This page and the linked technical pages | Retained as an operational checklist below. |

### Focused context navigation

- Search for a symbol, mode, experiment number, keyword, caller, artifact, or
  date before reading a large source/history file. Read a focused symbol or
  region, then expand only when dependencies require it.
- Search `EXPERIMENTS.md` before reading a ledger shard. Identify subsystem
  boundaries before reading the integration driver.
- Do not inspect generated `build/` artifacts, ignored self-play data,
  `.ai/`, or `docs/archive/` unless the task requires them. Reviewers may expand
  scope when necessary to prove semantics.
- Use Serena for C++/Python definitions, implementations, references,
  diagnostics, and approved semantic edits. Use ordinary targeted reads for
  Markdown, config, logs, git history, and experiment output. RepoWise is
  advisory only: do not create Serena memories; do not let RepoWise replace
  tracked documentation; do not use paid generation without explicit approval.

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
3. Use a task-specific skill when reviewing or conducting research.
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
before running it; fresh clones need `git submodule update --init`. Never claim
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
   and ignored data. When an upstream exists, also record
   `git log --oneline @{upstream}..HEAD`.
2. Read the routed KB page, implementation, and focused tests. State the
   behavioral success criterion and cheapest proving check. Ask when a material
   interpretation is genuinely ambiguous.
3. Make the smallest scoped change; do not improve adjacent code, comments, or
   formatting. For a feasible bug fix, add a reproducing test first. Rebuild all
   affected translation units and run focused checks before broader checks.
4. Inspect `git diff --check`, the complete diff, status, paths, symbols, and
   generated artifacts. Stage only task-scoped files.
5. A changed handoff normally creates one focused commit. Before a plain
   `git push`, compare `@{upstream}..HEAD` with the recorded starting set. Do
   not push pre-existing ahead commits without explicit authorization; do not
   invent an upstream. Never force-push, rewrite history, delete branches, or
   push a remote/refspec. Do not create an empty commit for read-only work.

### Recording and documentation

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

Log significant session decisions in
[decision-log/](../decision-log/README.md) before closing: architecture,
interfaces, schemas, environment/deployed configuration, process/tooling,
rejected alternatives, and corrected facts. Use the dated template; never
rewrite earlier entries. Promote stable evidence-backed rationale to
`decisions/` and reproducible unresolved diagnoses to `investigations/`.

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
`.clineignore` intentionally hides generated/local state from default agent
context; tracked deployable models, source, maintained docs, tests, and recorded
experiment evidence remain visible through explicit exceptions.

## Open questions

None for this workflow split. Future context reductions should update the
relocation audit rather than silently deleting an instruction.

## Cline mechanical guardrails

Repository-owned hooks live in `.clinerules/hooks/`. The extensionless
`TaskStart`, `PreToolUse`, and `TaskComplete` files are the sole entry points
(removed 2026-08-14: the former `.ps1` Windows wrappers were deleted because
Cline 4.1.8 executes `.ps1` hooks through `pwsh` even on Linux, and `pwsh` is
absent here, so every hook event aborted with `spawn pwsh ENOENT` — see the
decision log). All wrappers delegate to the same stdlib-only
`tools/agent/cline_guardrails.py` policy
implementation. Cline's current hook protocol supplies JSON on stdin and
expects one JSON object on stdout; diagnostics are written to stderr.

`TaskStart` records the task ID, baseline `HEAD`, and branch in a task-specific,
hashed Git-local untracked path resolved by `git rev-parse --git-path`.
`PreToolUse` mechanically cancels clear hazards: destructive Git history or
working-tree operations, force pushes and pushes to `main`, pushes from
`main`, broad process termination and privilege escalation, recursive file
deletion, direct execution of the `one_combat` binary (including through
argv-forwarding wrappers such as `env`, `time`, `nohup`, `nice`, `setsid`,
`command`, and `ionice`) or of `check_replay.py` outside
`tools/seed_guard.sh`, and normal project-file edit tools while on `main`.
Merely mentioning `one_combat` as an argument (for example
`cmake --build build --target one_combat` or `rg one_combat CMakeLists.txt`)
is allowed; only executing the binary requires `tools/seed_guard.sh`.
Read/search tools, normal read-only Git commands, builds, CTest, and
seed-guard-wrapped commands remain available. Other shell commands remain
approval-controlled; this hook is intentionally conservative rather than a
complete shell security model.

Before `attempt_completion` or `submit_and_exit`, `PreToolUse` validates the
baseline-to-HEAD committed diff, staged and unstaged diffs, and relevant
untracked files. It runs `git diff --check`, Python syntax checks, `bash -n`
for maintained shell files when Bash is available, and standard-library JSON
parsing. Failures cancel the completion tool. C++/header/CMake changes never
launch a full build. A reminder is returned where the Cline runtime preserves
PreToolUse context, but it is not guaranteed to be displayed; the PR Linux GCC
check remains authoritative. Markdown-only changes remain cheap.

`TaskComplete` is not a blocking validation gate in the current Cline
integration. It only removes the recorded baseline state as best-effort
cleanup and returns an allow response.

To enable or diagnose hooks, ensure the extensionless Linux/macOS wrappers are
executable (`chmod +x .clinerules/hooks/PreToolUse
.clinerules/hooks/TaskComplete`) and pipe synthetic JSON into them. If a safe
command is falsely blocked, inspect the stderr diagnostic and reproduce the
smallest synthetic input locally; do not weaken the hook by adding a broad path
allowlist. Ask the user to perform the one-off operation manually if needed.

GitHub Actions CI is the authoritative repository verification check. Changes
should reach `main` through a pull request only after the Linux GCC check
passes. Branch-protection enforcement is not currently available for this
private repository on its GitHub plan.

## Relevant code

- `AGENTS.md`
- `.cline/skills/implementation-review/SKILL.md`
- `.cline/skills/research-experiment/SKILL.md`
- `tools/seed_guard.sh`
- `.gitignore`; `.clineignore`
- `docs/knowledge-base/CODE_MAP.md`; `docs/knowledge-base/README.md`
