# Linux GCC CI gate follow-up

## Date and context

2026-08-22. Follow-up to the E2c branch CI report: 38/41 tests passed, with
missing pandas/SciPy and an unrelated `live_rejuv_attempt_gate` failure.

## Findings and decisions

The `live_rejuv_attempt_gate` failure reproduces on current `main`
(`014ea64`) in a clean detached Debug worktree. Its behavior assertions all
passed; only telemetry failed because the test switched output from
`/tmp/live_rejuv_fixture.csv` to `/tmp/live_rejuv_single_fixture.csv` before
the AI1/placebo1 cases, then read the former and searched for a placebo row.
The test now reads the single-child file and accepts its explicit `ai1` and
`placebo1` mode names. This is a test-fixture correction, not a rejuvenation
algorithm change.

The CI workflow now installs the locked `analysis` extra. That extra includes
pandas, SciPy, scikit-learn, and XGBoost, which are imported by the maintained
CTest analysis self-tests. The full ML extra, including PyTorch, is not needed
for this CI gate.

## Evidence

- Clean current-main Debug reproduction: `live_rejuv_attempt_gate` failed
  only with `telemetry=0`; all other contract fields were true.
- Branch after correction: `live_rejuv_attempt_gate PASS`.
- Full local Debug CTest: **41/41 passed**.
- Affected Python self-tests: particle leaf probe and postcombat raw-terminal
  self-tests passed with `PATH=.venv/bin:$PATH`.

## Status

The CI dependency/test-fixture corrections are separate from the Searcher3
Secret Technique/Weapon gameplay fix. They are ready for the authoritative
Linux GCC workflow to rerun after push.
