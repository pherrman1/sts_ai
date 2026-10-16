# Claude coordinator: observed Heart-outcome collection

Execute only this finite collection protocol after reviewing the attached PR's
final exact SHA and PROTOCOL.md. This is not model training or an RL loop.
Do not use GCP, paid provider infrastructure, credentials, or Codex workers.

1. In one native Claude VM, check out the exact independently reviewed source
   SHA from the PR evidence packet. Build Release `one_combat` with the recorded
   GCC/CMake commands and pinned submodules; retain logs and source/binary hashes.
   Obtain original Arm C native weights SHA
   `eff2f74f57dc2f566bbd44be30988592503cc8db51e51ff1e70cd2dec4636509`
   from the existing project artifacts. Do not train or substitute weights.
2. Run synthetic tests and the native `heartoutcomeselftest` without game seeds.
   Run `tools/heart_outcome_collect.py prepare --repo REPO --binary BINARY
   --student STUDENTC --out CAMPAIGN` from a clean reviewed checkout. The helper
   freezes only the established teacher and exact1,800 source assignment.
   Preserve its `plan.json`, `bundle/bundle.json` and every bound file.
3. Confirm actual host CPU quota/affinity, memory and session limits. Verify
   source bundle and executable/model load/synthetic scoring. Use an independent
   reviewer for source/design, not the implementer. No cohort sources yet.
4. Run `python3 tools/heart_outcome_collect.py canary --plan CAMPAIGN/plan.json
   --bundle CAMPAIGN/bundle --out CAMPAIGN/cloud-canary --role cloud` once.
   It runs the prescribed three guarded units and writes `canary.json` only on
   successful completion/trace parity. Do not retry a failed canary, alter seeds
   or change teacher/budgets. Stop and preserve failures for local review.
5. Verify a ≥256MiB native artifact export roundtrip between two different Claude
   containers through the project share; compare original/returned SHA256. Save
   `cloud-canary/export-roundtrip.json` with `bytes`, `sourceHost`,
   `destinationHost`, `sourceSha256`, `returnedSha256`. Git-only checkpoint
   persistence is not proof that raw corpus exports work. No third-party upload.
6. Have an independent reviewer inspect exact completion-anchored artifacts and
   hashes. Only after PASS, save `cloud-canary/canary-reviewed.json` with
   `verdict:"PASS"`, `sourceSha`, `planSha256`, `bundleSha256`, `canarySha256`,
   `durableExportRoundtrip:true`, `exportReceiptSha256`, and review evidence.
   Never regenerate canary completion hashes from altered files.
7. One coordinator runs `activate --plan CAMPAIGN/plan.json --bundle
   CAMPAIGN/bundle --approval CAMPAIGN/cloud-canary/canary-reviewed.json
   --out CAMPAIGN/activation.json`. Preserve the exclusive COHORT-STARTED latch
   and fixed six-hour deadline. Never recreate/reset it, including after loss.
8. Dispatch exactly45 native Claude workers, IDs0..44, at most4 concurrent source
   processes each. Copy the **same frozen bundle, plan and activation** to all.
   Each runs `python3 BUNDLE/heart_outcome_collect.py worker --plan PLAN.json
   --bundle BUNDLE --activation ACTIVATION.json --out FRESH_WORKER_DIRECTORY
   --worker W`. Every worker owns only its assigned40seeds. Never rerun a lost
   or failed source/worker in another container or directory. Report actual
   requested/launched/running/completed capacity separately;45 availability is
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

Expected accounting:1,800 unique sources; TRAIN1,080, VALIDATION360, TEST360.
Only complete healthy full runs yield labels; failures/timeouts are not deaths.
If source/canary/export/resource/deadline gates fail, report the exact failure
and preserve evidence; do not repair by changing the scientific protocol.
