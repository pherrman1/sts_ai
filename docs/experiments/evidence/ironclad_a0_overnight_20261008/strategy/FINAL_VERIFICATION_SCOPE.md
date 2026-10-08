# Campaign final verification scope

Read-only verification planning against campaign base `a4b3df35d170abba7860e8e854cc24cfd3579075`, current gameplay producer `3ed91ab3491a4cdc1a7de687b2ad87dcc7774fc0`, and the new standalone public probe source SHA `e78ac9e5d229f48f2e28429855eafaa9e158589b359ad50369d3c10536ffda9a`. No checks, builds, gameplay or outcome reads were executed for this planning task. Coordinator receipts determine which checks are complete when the final handoff is assembled.

## Reuse completed evidence

| Changed behavior | Existing proving evidence | Repeat only if |
|---|---|---|
| Public OOC encounter marginalization | `overnight-public-futures-fixed-test.log`; hidden seed/RNG/suffix perturbation, source purity, post-link expectation and default-off fixtures; runtime public-scorer count receipts | Scorer implementation, call routing or effective profile changes |
| Shop hypothetical deck size | Baseline failing fixture plus `overnight-shop-fixed-test.log`; worked real decision case | Shop feature construction changes |
| Optional Ruby Recall eligibility | Baseline failing fixture plus `overnight-recall-fixed-test.log`; off/RNG/order/forced-only boundary fixtures; corrected runtime startup/policy binding | Shared filter, V4 integration or effective policy serialization changes |
| Final-boss binary objective | `overnight-terminal-test.log`: `silver_searcher PASS`, including terminal/context/default fixtures | Silver evaluator/context changes |
| Targeted REST GEN2 producer | `targeted-rest-checks.json`, corrected `vwinrefreshselftest`, exact target preflight and continuation receipts | Target identity, action retention, future indexing, teacher or producer implementation changes |
| Public combat capture | Corrected-runtime review: default-off and capture-enabled trajectory/action/RNG parity for the named source, 72 valid public roots | Capture implementation or gameplay producer changes |
| New analysis scripts | Focused synthetic analyzer tests and independent source reviews, each bound to the reviewed script hash | Analyzer algorithm or input contract changes |

The standalone probe is a new executable linked to existing core objects. It is not linked into `one_combat` or the gameplay backend. Its CMake addition alone does not justify rerunning completed whole-run quality cohorts or changing their immutable producer binaries.

## Cheapest outstanding checks

1. Build `silver-public-pair-probe` from the final reviewed source with the new CMake target. Its target output is `silver_public_pair_probe`; OpenSSL Crypto is linked through the existing `link_ctm_crypto` helper. Preserve the compiler log, source SHA and executable SHA. Run its frozen `check` mode through the seed guard; then use only the separately authorized two-future canary and cost gate. This is the only new gameplay-driving verification introduced by the standalone helper.
2. If not already covered by a final-source receipt, run the narrow CTest integration set below in the existing Debug tree, building only `unit-test` and `one_combat` if required. These checks exercise public wire reconstruction/action lowering and teacher/policy schema compatibility around the changed interfaces. Do not add fresh research seeds to this check set.
3. Run final `git diff --check` and repository-health comparison against the campaign base after task-scoped files are staged or committed. Review the final changed paths and verify that the campaign's immutable artifact receipts still match. Keep protected holdout/TEST numerical data outside these checks.

Suggested narrow integration command, not executed by this reviewer:

```bash
bash tools/seed_guard.sh ctest --test-dir build/linux-gcc-debug --output-on-failure -j1 -R '^(silver_wire_state|silver_semantic_action|card_pile|card_pile_engine|battle_equality|teacher_schema_compat|learned_stop_teacher_contract|vwin_refresh_policy_export)$'
```

`silver_semantic_action` is labeled integration rather than core, and `vwin_refresh_policy_export` has no core/smoke label, so the CI label expression alone does not cover these two relevant interfaces. The new Recall/public-futures/shop fixtures are registered as smoke tests. Final-boss evaluator fixtures live inside `silver_searcher`, labeled core. The existing `vwin_refresh_producer_contract` is core and already has campaign pass receipts.

If a final integrated core/smoke run is still required, reuse the actual CI selection once rather than serially rerunning overlapping subsets:

```bash
bash tools/seed_guard.sh ctest --preset linux-gcc-test -L 'core|smoke' --output-on-failure -j1
```

This broader command includes existing fixed-seed parity and native combat fixtures; the coordinator must schedule it within the shared capacity and reserve. It does not read campaign holdout data. There is no need to run the entire unfiltered CTest suite for this bounded change after its affected checks pass. Debug is required for assertion-dependent core tests such as `cardqueue_overflow`; Release results are not a substitute.

## Authoritative CI and handoff

The executed workflow definition `.github/workflows/ci.yml` is authoritative: non-draft pull requests run the Debug configure/build plus `ctest --preset linux-gcc-test -L 'core|smoke'`, repository prerequisites, repository-health comparison and its focused self-test. The job has `if: !github.event.pull_request.draft`. A draft PR therefore hands off local evidence with **Linux GCC pending until ready_for_review**; creating a draft is not a CI pass. Do not mark the PR ready or merge to obtain that check without the coordinator's authorized handoff scope.

Some maintained build prose still describes an unfiltered CI suite or an additional agent-test discovery step; those claims do not match the current workflow file. Report the actual workflow rather than asserting those broader checks ran. The coordinator can correct the directly relevant maintained wording in its documentation pass without broadening the experimental scope.

The final evidence packet should distinguish implementation/source review, deterministic fixture passes, runtime contract/cost checks, discovery evidence and final confirmation. Neither passing this verification set nor compiling the probe qualifies a new policy or changes a production default.

Knowledge impact: verification routing for this experiment and an identified stale CI description; no source or policy change in this review.
