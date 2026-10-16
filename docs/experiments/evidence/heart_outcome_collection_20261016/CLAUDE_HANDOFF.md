# Claude coordinator: observed Heart-outcome collection

Repository: `pherrman1/sts_ai`. Setup/evidence PR:
https://github.com/pherrman1/sts_ai/pull/572

Execute only this finite collection protocol after reviewing the attached PR's
final evidence packet and PROTOCOL.md. Frozen reviewed producer source:
`7527b5d5d07467688101212660461995665512b9` (source/design and local canary PASS).
Local results and hashes are in REPORT.md; they do not replace qualification
of your cloud-rebuilt producer. This is not model training or an RL loop.
Use Claude's native worker VMs. Do not provision GCP or other cloud providers,
restore provider credentials, or dispatch Codex workers.

1. In one native Claude VM, check out the exact independently reviewed source
   SHA from the PR evidence packet. Build Release `one_combat` with the recorded
   GCC/CMake commands and pinned submodules; retain logs and source/binary hashes.
   Python must be ≥3.11 with NumPy installed; `prepare` pins the exact Python
   and NumPy versions for every worker. Ensure Git object
   `9d83adbbbcc0fabf2c8bcd8c6a87f9782d0acbc3` is available: the unchanged
   teacher environment is extracted from that pinned historical runner.
   Obtain original Arm C native weights SHA
   `eff2f74f57dc2f566bbd44be30988592503cc8db51e51ff1e70cd2dec4636509`
   from the existing project artifacts. A verified retrieval source is transport
   commit `d65a365599bb0e32a5b26a4c59aa19dcd1ca0195`, path `bundle/studentc.bin`
   on `claude/arm-c-native-data`: fetch that branch, extract only this blob with
   `git show COMMIT:bundle/studentc.bin > STUDENTC`, and verify SHA256 before use.
   This transport branch is never merged; do not read its sealed TEST corpus.
   Do not train or substitute weights.
2. Run synthetic tests and the native `heartoutcomeselftest` without game seeds.
   Run `python3 tools/heart_outcome_collect.py prepare --repo REPO --binary BINARY
   --student STUDENTC --out CAMPAIGN` from a clean reviewed checkout. The helper
   freezes only the established teacher and exact 1,800 source assignment.
   Preserve its `plan.json`, `bundle/bundle.json` and every bound file.
3. Confirm actual host CPU quota/affinity, memory and session limits. Verify
   source bundle and executable/model load/synthetic scoring. For the latter,
   run `BINARY heart1score STUDENTC
   REPO/docs/experiments/evidence/arm_c_native_preflight_20261016/synthetic-record.jsonl
   PREFLIGHT/synthetic-score.jsonl` with a fresh PREFLIGHT directory outside the
   checkout/campaign. Retain the log and check nonempty finite scores; no games
   are run by this mode. Use an independent
   reviewer for source/design, not the implementer. No cohort sources yet.
4. Run `python3 tools/heart_outcome_collect.py canary --plan CAMPAIGN/plan.json
   --bundle CAMPAIGN/bundle --out CAMPAIGN/cloud-canary --role cloud` once.
   It runs the prescribed three guarded units and writes `canary.json` only on
   successful completion/trace parity. Do not retry a failed canary, alter seeds
   or change teacher/budgets. Stop and preserve failures for local review.
5. Verify a ≥256 MiB native artifact export roundtrip between two different Claude
   containers through the project share; compare original/returned SHA256. Save
   `cloud-canary/export-roundtrip.json` with `bytes`, `sourceHost`,
   `destinationHost`, `sourceSha256`, `returnedSha256`. Git-only checkpoint
   persistence is not proof that raw corpus exports work. No third-party upload.
6. Have an independent reviewer inspect exact completion-anchored artifacts and
   hashes. Only after PASS, save `cloud-canary/canary-reviewed.json` with
   `verdict:"PASS"`, `sourceSha`, `planSha256`, `bundleSha256`, `canarySha256`,
   `durableExportRoundtrip:true`, `exportReceiptSha256`, and review evidence.
   Never regenerate canary completion hashes from altered files.
7. One coordinator runs `python3 BUNDLE/heart_outcome_collect.py activate --plan CAMPAIGN/plan.json --bundle
   CAMPAIGN/bundle --approval CAMPAIGN/cloud-canary/canary-reviewed.json
   --out CAMPAIGN/activation.json`. Preserve the exclusive COHORT-STARTED latch
   and fixed six-hour deadline. Compute and publish activation.json SHA256
   in the reviewed dispatch packet. Never recreate/reset it, including after loss.
8. Dispatch exactly 45 native Claude workers, IDs 0..44, at most 4 concurrent source
   processes each. Copy the **same frozen bundle, plan and activation** to all.
   Also copy COHORT-STARTED.json and the entire reviewed cloud-canary directory
   under the same relative campaign paths. Every worker verifies the approval
   chain and original canary hashes before starting sources.
   Each runs `python3 BUNDLE/heart_outcome_collect.py worker --plan PLAN.json
   --bundle BUNDLE --activation ACTIVATION.json --out FRESH_WORKER_DIRECTORY
   --worker W --activation-sha256 APPROVED_ACTIVATION_SHA256`. Every worker owns only its assigned 40 seeds. Never rerun a lost
   or failed source/worker in another container or directory. Report actual
   requested/launched/running/completed capacity separately; 45 availability is
   a requested ceiling, not proof of successful launch.
9. Export each worker's `train.tar.gz`, `validation.tar.gz`,
   `SEALED-test.tar.gz`, and `worker-receipt.json` durably before declaring it
   delivered. Preserve every raw artifact, including failed/partial trajectories.
   The coordinator may verify TEST archive hashes and completion receipts, but
   must not unpack/read its trajectories, labels, logs or aggregate outcome counts.
10. Return one immutable delivery index binding plan/activation/bundle/source
    hashes, every worker ID and archive/receipt hash, plus source completion
    accounting and failures. Duplicate worker/source deliveries or missing units
    invalidate completeness. Stop for independent import/seal review. No fitting,
    TEST opening, gameplay comparisons, native head deployment or default change.

Expected accounting: 1,800 unique sources; TRAIN 1,080, VALIDATION 360, TEST 360.
Only complete healthy full runs yield labels; failures/timeouts are not deaths.
If source/canary/export/resource/deadline gates fail, report the exact failure
and preserve evidence; do not repair by changing the scientific protocol.
