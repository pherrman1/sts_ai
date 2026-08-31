# 2026-08-31 — Evaluator hidden-object isolation

Date: 2026-08-31
Session/task: Correct candidate preparation after private evaluator data was found in unreachable Git objects.

## Decision

Initialize an empty candidate repository before setup-patch application, but
defer the first and only staging pass and root commit until after `evals/` is
removed and any skill overlay is installed. Candidate preparation must never
write hidden evaluator blobs into its object database, including as unreachable
objects.

## Rationale

The previous commit-then-amend sequence removed `evals/` from visible history
but retained the original commit, trees, task manifest, setup patch, and private
grader as recoverable candidate-local unreachable objects. Deleting a path from
the working tree or amended history is not a sufficient hidden-data boundary.

## Alternatives considered

- Garbage-collect after amending — rejected because correctness would depend on
  reflog/pruning details after private objects had already entered the candidate.
- Copy or share an existing Git repository and remove hidden refs — rejected
  because borrowed objects, alternates, and source-lifetime dependencies widen
  the candidate boundary.
- Stage the export before deleting `evals/`, then make one commit — rejected
  because `git add` itself writes the private blobs into `.git/objects`.

## Evidence

- `tools/agent/eval.py::prepare` — setup mutation and hidden-data removal now
  precede the only `git add` and root commit.
- `tests/agent/test_agent_eval.py::test_prepare_isolated_and_hides_reference_data`
  — requires no unreachable objects, alternates, nested module metadata, or
  exact hidden grader, setup-patch, and manifest blobs in two real candidates.

## Status and follow-up

- Implemented as a focused correctness correction. Production export caching
  or further preparation-speed work remains separate and must preserve this
  object-isolation invariant.
