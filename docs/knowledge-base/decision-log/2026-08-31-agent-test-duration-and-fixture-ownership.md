# Agent-test duration reporting and fixture ownership

Date: 2026-08-31
Session/task: Expose and reduce slow `tests/agent` setup in Linux CI.

## Decision

Use Python 3.12's standard `unittest --durations 20` reporting on the complete
agent-test discovery. In `AgentEvalTests`, prepare one immutable class baseline
and derive independent sparse, shared-object Git clones for cases that validate
grading and history semantics. Keep full candidate preparation in tests whose
contract is preparation or skill overlay behavior.

## Rationale

Per-test timing identified repeated full candidate exports as the concentrated
bottleneck. The derived clones retain the complete committed tree and real Git
objects while materializing only the grader, its public tests, and explicitly
mutated paths. This preserves isolation and the ancestry, merge, rename,
rewritten-history, scope, and error contracts without repeatedly copying
irrelevant working-tree files.

## Alternatives considered

- Mock Git subprocesses -- rejected because the slow cases validate real Git
  history and diff semantics.
- Share one mutable prepared working tree -- rejected because mutations would
  create order dependence and cross-test leakage.
- Add a custom timing runner or pytest -- rejected because Python 3.12 already
  provides successful-run duration reporting with unchanged discovery and exit
  behavior.

## Evidence

- `.github/workflows/ci.yml` -- complete discovery plus standard duration
  reporting.
- `tests/agent/test_agent_eval.py::AgentEvalTests` -- immutable baseline and
  isolated sparse-clone fixture ownership.
- WSL-native ext4, Python 3.13.15, locked analysis environment: 118 tests passed
  in 193.113 seconds at `67a8a8c` and 118.392 seconds at `8bdbb9e`.
- GitHub Actions run 33395000182 at `8bdbb9e`: 118 tests passed in 59.670
  seconds; the agent-test step took 65 seconds versus the 114-second PR #105
  reference sample (run 33389737148).

## Status and follow-up

- Implemented in draft PR #106. Hosted-runner timings are single samples; use
  future routine runs to assess variance rather than treating the observed
  reduction as a stable benchmark.
