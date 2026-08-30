# 2026-08-31 — Skill overlay evaluator corrections

Date: 2026-08-31
Session/task: Correct PR #99 evaluator provenance and SkillOpt setup evidence.

## Decision

Anchor grading to evaluator-owned prepared-baseline metadata, reject
non-descendant candidate history, and include committed, staged, unstaged, and
untracked paths in scope evaluation. Treat the SkillOpt `Learned guidance`
boundary as a configured preference plus mandatory staged-diff review, not as
mechanical engine isolation.

## Rationale

Using candidate `HEAD` as both baseline and candidate hid committed changes.
External prepared metadata preserves the comparison SHA even when the agent
commits. SkillOpt preferences influence proposals but do not enforce output
paths, so adoption safety requires explicit diff rejection.

## Alternatives considered

- Store the baseline only in a candidate Git ref — rejected because candidate
  history and refs are agent-mutable.
- Add a SkillOpt wrapper or config loader — rejected because the pinned engine
  already reads `~/.skillopt-sleep/config.json` and its module CLI is usable.

## Evidence

- `tools/agent/eval.py::load_prepared_baseline` and `grade` — immutable
  comparison anchor and ancestry check.
- `tests/agent/test_agent_eval.py::test_committed_forbidden_path_is_still_scoped_against_prepared_baseline`
  — committed forbidden path remains a scope failure.
- `evals/coding_agent/tasks/cmake-target-contract/setup.patch` — current
  `$<TARGET_OBJECTS:sts_core_objects>` fixture syntax.
- `docs/knowledge-base/operations/skillopt-sleep.md` — exact pin, config,
  module commands, effective-config assertion, and Windows limitation.

## Status and follow-up

- Implemented as a correction to the existing pilot PR. No provider-backed
  SkillOpt run or skill proposal adoption was performed.
