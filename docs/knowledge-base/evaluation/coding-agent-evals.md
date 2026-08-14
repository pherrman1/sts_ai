# Coding-agent evaluation harness

Last verified: 2026-08-14 against the current working tree.

## Purpose

The Phase 7 harness measures repository outcome, not an agent's explanation or
claimed test run. It is stdlib-only, deterministic, model-agnostic, and never
invokes a paid model API.

## Terms

- **Task**: a JSON manifest, public prompt, setup mutation, and hidden grader.
- **Candidate workspace**: a disposable Git repository containing an exported
  and deliberately mutated repository state.
- **Agent/harness**: the human-operated coding agent working inside that
  candidate workspace. Phase 7 does not invoke it.
- **Grader**: an independent executable kept in the reference checkout that
  runs functional and regression checks against the candidate.
- **Result**: a JSON record containing checks, changed paths, commits, hashes,
  duration, environment, and optional labels.
- **PASS** means every required check passed; **FAIL** means the candidate did
  not satisfy at least one functional, regression, or scope check;
  **INFRA_ERROR** means the evaluator could not perform a valid evaluation.

## Commands

```bash
python3 tools/agent/eval.py list
python3 tools/agent/eval.py prepare <task-id>
# Work on the printed workspace with Cline or another agent.
python3 tools/agent/eval.py grade <task-id> <workspace> --agent cline --model <label>
python3 tools/agent/eval.py self-test
```

`prepare` exports tracked content using `git archive`, materializes checked-out
submodule contents when present, applies the setup mutation, removes `evals/`,
initializes a fresh Git repository, and commits a clean candidate baseline.
Runtime workspaces and result records live below `.agent-eval/`, which is
ignored. A human can point Cline at the printed workspace, give it the printed
public prompt, and grade the workspace afterward.

## Manifest schema

Each task has exactly these fields:

```json
{
  "schema_version": 1,
  "id": "example-task",
  "version": 1,
  "title": "Short title",
  "prompt_file": "prompt.md",
  "setup_patch": "setup.patch",
  "timeout_seconds": 300,
  "allowed_changed_paths": ["tools/example/**"],
  "forbidden_changed_paths": ["src/**"],
  "grader": "private/grader.py"
}
```

Unknown or missing fields, duplicate IDs, missing files, absolute paths, and
`..` traversal are rejected. Graders must allow alternative correct solutions;
the harness does not compare exact patches or reward small diffs.

## Initial tasks

| ID | Capability measured |
| --- | --- |
| `guardrail-command-policy` | Python command parsing and safety regression control |
| `doctor-submodule-validation` | Shell validation of synthetic Git/submodule state |
| `simhealth-empty-hand` | Narrow C++ simulator-health invariant and nearby regression |
| `cmake-target-contract` | Observable CMake target/output contract |

The C++ and CMake graders configure/build only the required target and run no
gameplay seed sweep.

## Hidden-data boundary

The reference checkout owns task manifests, setup patches, and private graders.
Preparation applies the patch before `git init`, then removes the complete
`evals/` directory. Consequently candidate files and candidate Git history do
not contain the hidden grader or oracle mutation. The grader executes from the
reference checkout and receives only the candidate workspace path.

## Adding a task

Create one directory under `evals/coding_agent/tasks/` with the strict manifest,
public prompt, setup patch, and `private/grader.py`. Mutate current known-good
code exactly once, make the grader independently test the observable behavior,
and run `python3 tools/agent/eval.py self-test`. The self-test is the inclusion
gate: the untouched mutation must FAIL and reversing the setup patch must PASS.

## Limitations

Phase 7 has no agent orchestration, LLM-as-judge, token/cost accounting,
leaderboard, Docker isolation, stochastic gameplay benchmarks, or formal OS
sandbox. The disposable workspace is a repository boundary, not a security
sandbox; agents should still be run under the normal host safety policy.