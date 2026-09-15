# Live OOC visit-lock stopping enabled

Baseline: `5b2a5b51fcbce2ced657281dbb3ac9c6795833c2`.
Validated source: `1a3f552` (compiled C++ source `05f87de6f4bfc3a3b6ec24d3071345235bf684b1`;
subsequent source commit changes only the Python startup expectation).

Live `STS_OOC_MCTS=1` now enables strict visit-lock stopping by default.
`STS_OOC_MCTS_EARLY_STOP=0` restores the provider-guarantee requirement.
The generic planner default remains guarantee-bound. Mean-Q selection and
`STS_OOC_MCTS_ROOT_LOCK_TRACE` suppress stopping. Unqualified singleton roots
complete at least one simulation before a stop; zero-simulation bypass still
requires a qualified provider.

The user explicitly requested enablement despite remaining Smoke support.
The provider's non-aborting guarantee remains false. Early stopping may skip a
later support/continuation abort and execute an action where full-budget search
would fall back. Model support, RNG continuation and real combat are unchanged.
This policy change is documented in ADR-0014; no full-support claim is made.

## Paired engineering check

One common seed 42, same frozen Release binary and model hashes: Ironclad A0,
OOC 512, exact 10k Silver, fair combat/copied noncombat RNG, keys OFF, Act3-or-death,
CPU 0 / OMP 1. The full-budget arm explicitly sets EARLY_STOP=0; the stopped arm
leaves it unset and its startup record confirms `earlyStop=true`. Commands use
the seed guard. Both exit 0. This is a single engineering comparison, not an
average speedup or a quality sweep; timing is subject to ordinary desktop noise.

| Measure | Full budget | Default early stop |
| --- | ---: | ---: |
| Completed simulations | 79,360 | 39,174 |
| Stopped roots | 0 | 155 |
| Saved simulations | 0 | 40,186 |
| OOC search wall seconds | 11.193670 | 6.758811 |
| Full-run elapsed seconds | 35.8988 | 31.3939 |

OOC search time fell 39.62% and full-run elapsed time
fell 12.55% on this paired seed. Saved simulations match
the earlier full-budget observer's 40,186 exactly. Both runs retain 188 decisions,
155 owned / 33 fallback and 0 support/continuation aborts. All non-timing outcome
fields and all 26 Silver telemetry records match: Act 3 win, floor 51, hp 16 / max 85.
These checks do not constitute a complete live-state trajectory comparison.
No abort-skipping frequency or multi-seed quality claim follows from this seed.

## Validation and knowledge impact

- Full default Debug build succeeds; full guarded CTest exits 0, 101/101 pass.
- Focused Release core/adapter/startup CTest exits 0, 3/3 pass; 13 startup cases.
- Core regressions prove exact 52/100 strict crossing with the same winner,
  observer precedence, mean-Q exclusion, and deliberate singleton stop at 1
  skipping the abort that the full-budget/observer searches encounter at 7.
- Live fixtures verify detached execution/real combat pending, and rollback
  preserving the Wheel's ordered fallback state and agent RNG.
- Earlier failed checks are retained in the raw packet: old disabled-stop and
  fixed 128 simulation assertions were updated, plus the expected strict-control
  error wording. Final checks pass; no dependency or model changes were needed.
- No support expansion, GPU work, multi-seed sweep or full trajectory trace.
  Linux GCC CI for the final PR head is reported on PR #186; no automatic merge.

Knowledge impact: live stopping policy/rollback and observer precedence are
maintained in architecture, environment controls, CODE_MAP and ADR-0014;
measurements remain in ledger 260 and this source-bound evidence packet.

[Raw commands, environments, hashes, output and checks](ooc_early_stop_enabled_2026-09-15.json).
[Earlier full-budget opportunity measurement](ooc_root_lock_observation_2026-09-15.md).
