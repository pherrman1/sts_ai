# Campaign attempt accounting

Metadata snapshot 2026-10-08T03:42:45.457514+00:00 to 2026-10-08T03:42:45.560619+00:00. **ALL_INVENTORIED_INVOCATIONS_COMPLETE**.

Inventoried 799 runtime receipts: 799 completed_exit0.

This is invocation accounting, not a quality or validity verdict. No numerical game outcomes were read. Pending jobs are excluded from completion.

| Receipt directory | Status counts |
|---|---|
| `canary` | 3 completed_exit0 |
| `card_rank_canary` | 3 completed_exit0 |
| `champ_d13` | 65 completed_exit0 |
| `corrected_canary` | 6 completed_exit0 |
| `fair_canary` | 10 completed_exit0 |
| `final_confirmation` | 256 completed_exit0 |
| `fullhp_canary` | 5 completed_exit0 |
| `learning/gen2-canary-3ed9` | 4 completed_exit0 |
| `learning/gen2-tranche32-3ed9` | 32 completed_exit0 |
| `removal_canary` | 4 completed_exit0 |
| `removal_development` | 64 completed_exit0 |
| `targeted_rest_631f` | 3 completed_exit0 |
| `wave1` | 64 completed_exit0 |
| `wave2` | 128 completed_exit0 |
| `wave3` | 24 completed_exit0 |
| `wave3_development` | 96 completed_exit0 |
| `wave4_removal` | 16 completed_exit0 |
| `wave5_card_rank` | 16 completed_exit0 |

Expected strict startup negatives: **26**; all occur before game execution. Negative signal exit codes are retained exactly.

| Preserved event | Classification | Resolution |
|---|---|---|
| shop feature regression fixture | `expected_negative_fixture` | Pre-fix synthetic fixture failed; corrected focused fixture passed. No seed run. |
| optional Recall regression fixture | `expected_negative_fixture` | Pre-fix synthetic fixture failed; corrected focused fixture passed. No seed run. |
| missing rest_recall_filter_test build target | `build_orchestration_failure` | CMake target absent before reconfigure; preserved reconfigure and v2 build show repair. No game. Explicit exit code was not recorded in the text log. |
| targeted REST wrong target hash | `prelaunch_rejection` | Hash gate rejected before binary launch or output creation; corrected later invocation separately receipted. |
| GEN2 source-only profiler seed verifier | `postcollection_validator_defect` | Original INVALID preserved. Reviewed exact derived-seed membership repair passed v2 on unchanged collection; no recollection. This did not establish a failed game. |
| GEN2 seed verifier synthetic test identity mismatch | `test_fixture_defect` | One fixture used decision36 with expected decision71 seed set. Fixture corrected; five focused tests and independent review passed. Historical pending-review status remains unchanged. |
| native export parity CRLF fixture header | `read_only_parity_fixture_failure` | First winnettest fixture was rejected with no state block between chosen and won; documented CRLF header limitation. A fresh LF fixture passed both model parity checks. No game seeds, model changes or TEST rows. The preserved failed log records no explicit process exit code. |
| card-win NaN synthetic fixture reviewed before compilation | `preexecution_fixture_design_correction` | Independent source review caught a proposed logistic-NaN fixture whose value would be clamped to one. Author replaced it with the explicit predictor-cycle NaN path; later focused fixtures passed. This was a reviewed test-design correction, not a preserved executed test failure or failed game; no failing exit code is claimed. |
| old 736d GEN2 freeze | `superseded_unlaunched_proposal` | Superseded before collection to include Recall correction; source seeds later consumed only by separately frozen corrected producer. |
| attempt inventory optional capture flag parser | `metadata_inventory_defect` | Initial snapshot preserved all 543 completed receipts but marked one job unresolved because --public-combat was not recognized. Narrow parser fix recognizes this existing flag; no game or bound evidence changed. |

The JSON records every runtime receipt path/hash, command, timestamps, status and source/binary identity; every joblist path/hash and expected receipt; and exact paths/hashes for the named events and startup rejections.

Pending or unresolved scheduled jobs:

None in this snapshot.

Limits:

- Snapshot is not an atomic view of the running campaign; each file has its own stable-read flag.
- A completed exit0 receipt is invocation status, not independent runtime validity or policy strength.
- Only preserved receipts and named diagnostic evidence are accounted; unsaved terminal-only attempts cannot be reconstructed.
- Build logs without recorded process exit metadata are not assigned invented exit codes.
- Synthetic rejection tests are not failed campaign games; queued jobs are not yet attempts.

JSON SHA256: `e4bf69dc2d3ff5587356fff5907297c1a0958d0a816c285d7c6532937caba6a9`.

Refresh after dispatchers stop using a new output prefix; this script refuses overwrites:

```sh
.venv/bin/python docs/experiments/evidence/ironclad_a0_overnight_20261008/learning/inventory_attempt_metadata.py --output-prefix docs/experiments/evidence/ironclad_a0_overnight_20261008/learning/ATTEMPT_ACCOUNTING_v3_v2
```

Knowledge impact: experiment evidence accounting only; no new runtime or policy claim.
