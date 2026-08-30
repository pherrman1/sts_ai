# Coding-agent evaluation harness

Last verified: 2026-08-31 against the current working tree.

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
python3 tools/agent/eval.py prepare <task-id> \
  --skill-file <path-to-SKILL.md> --skill-name <safe-slug>
# Work on the printed workspace with Codex or another agent.
python3 tools/agent/eval.py grade <task-id> <workspace> --agent codex --model <label>
python3 tools/agent/eval.py self-test
```

`prepare` exports tracked content using `git archive`, materializes checked-out
submodule contents when present, applies the setup mutation, removes `evals/`,
initializes a fresh Git repository, and commits a clean candidate baseline.
Runtime workspaces and result records live below `.agent-eval/`, which is
ignored. A human can point Codex at the printed workspace, give it the printed
public prompt, and grade the workspace afterward.

When both skill options are supplied, `prepare` validates the regular source
file and lowercase hyphenated slug, copies the skill to
`.agents/skills/<skill-name>/SKILL.md`, and includes that overlay in the clean
candidate baseline. The returned JSON includes `skill_name`, the source-byte
`skill_sha256`, and a public-prompt prefix explicitly invoking the skill. The
overlay therefore is not an agent-produced diff. Omitting both options
preserves ordinary preparation behavior; supplying only one fails closed.

Preparation also records the exact baseline commit in evaluator-owned runtime
metadata outside the candidate repository. Grading requires candidate `HEAD`
to descend from that commit and evaluates the union of committed-history,
staged, unstaged, and untracked paths. `baseline_commit` is the recorded
prepared SHA; `candidate_commit` is the graded `HEAD`. Missing metadata,
missing baseline objects, and rewritten or non-descendant history are
infrastructure errors rather than silently changing the comparison baseline.

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

The `guardrail-command-policy` task intentionally retains
`tools/agent/cline_guardrails.py` and its focused tests as an agent-agnostic
Python maintenance fixture. Those files are not connected to Codex or to an
active repository hook.

## Hidden-data boundary

The reference checkout owns task manifests, setup patches, and private graders.
Preparation applies the patch before `git init`, then removes the complete
`evals/` directory. Consequently candidate files and candidate Git history do
not contain the hidden grader or oracle mutation. The grader executes from the
reference checkout and receives only the candidate workspace path.

Grading disables Git rename detection and expands merge diffs when enumerating
paths, constructing the candidate patch, and counting changed lines. A rename
therefore remains an old-path deletion plus a new-path addition, and merge-only
changes remain visible, independent of host Git configuration.

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

The four tasks are a no-regression smoke, not proof that a skill improves all
implementation work. Compare a staged proposal as follows:

1. Prepare, run, and grade arm A with the current `codex-implementation` skill.
2. Prepare, run, and grade arm B with the staged SkillOpt candidate.
3. Keep task, model, reasoning effort, host, and configuration identical.
4. Run each task once initially; repeat only discordant tasks twice.
5. Reject a majority regression, scope violation, infrastructure error, or
   clearly higher cost without compensating benefit.

Adoption requires all four conditions: SkillOpt internal validation accepted,
the `sts_ai` evaluator did not regress, human diff review passed, and the edit
enters through the normal branch, draft-PR, and CI workflow.
