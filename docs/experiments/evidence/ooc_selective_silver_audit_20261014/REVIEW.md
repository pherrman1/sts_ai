# Prospective implementation review

Baseline:37594e3bab761408cf255621be31dc72d75cc96e, stacked on PR539.
Independent C++/protocol inspection by recent_ooc_evidence and independent
runner/analyzer inspection by stability_protocol passed before scientific seeds.
The sampler/horizon author was not the independent reviewer of those files.

Review corrections: propagate sampler-test failure; require primary improvement
for a matched-compute claim; bind real-context callbacks; bound/reconcile all
fork CPU costs; verify paired CPU stopping, GNU-time receipts and model custody;
reject impossible endpoints/nonfinite JSON; kill the owned process group on any
failed source exit. No cohort, teacher or hypothesis change resulted.

Verification (2026-10-14):

- Release one_combat build:exit0, with existing narrowing/LTO warnings.
- `python3 tests/test_ooc_selective_silver.py`:14 synthetic tests passed.
- `bash tools/seed_guard.sh ctest --test-dir build/linux-gcc-release-ccache
  --output-on-failure -R '^(teacher_schema_compat|a20_teacher_runner|a20_teacher_analysis|a20_teacher_large_analysis|ooc_leaf_replay|ooc_leaf_stability|ooc_selective_silver_sampler|ooc_selective_silver_analysis|ooc_selective_seed_guard_rejects_zero)$'`:
  9/9 passed,4.23 seconds.
- `git diff --check`:exit0.

Raw local checks:build/ooc-selective-silver-audit/checks/build-freeze.log,
ctest-final.log,python-tests-final.log. No gameplay campaign, training, full-run
quality qualification, live-mod parity or authoritative GitHub CI is claimed by
these checks. The frozen producer SHA is recorded by prepare() after this
reviewed implementation is committed. Expensive execution starts with one
excluded canary and never retries a failed latch.

Knowledge impact: narrow default-off diagnostic interfaces documented in
CODE_MAP/out-of-combat; prospective scientific contract in PROTOCOL. Outcomes
belong to the experiment ledger and maintained current research after execution.
