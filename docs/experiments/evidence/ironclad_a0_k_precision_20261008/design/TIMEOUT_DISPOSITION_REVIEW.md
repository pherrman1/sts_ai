# Timeout disposition and feasibility review

**The preregistered 32-source primary comparison is `EXECUTION_BLOCKED`.** Source `610084217` has a hash-bound timeout receipt with exit 124 and process-wall duration **1,800.033515825 seconds**, against the frozen 1,800-second source cap. It started at 12:01:42.724 and finished at 12:31:42.758 Europe/Berlin on 2026-10-08. The recorded freeze, immutable producer and K32/BOSS command match the accepted experiment.

The [metadata snapshot](TIMEOUT_METADATA_SNAPSHOT.json), SHA256 `653322af20f06fd1f7d8ceb189cb7bc3b4cf27e73194c0497ef611c37fbe6074`, binds the timeout receipt (`a4f6619ed3272702b071f56dbef416fbd4f54ac1af199d85c42337253ddbd137`), protocol, freeze, dispatch authorization, ready bundle and all currently present source receipts. Its non-atomic status snapshot contains 23 completed, one timeout, six running and two not yet started sources. These are invocation statuses, not branch validity or efficacy findings. No game-table rows, profile rows, choices or evaluation outcomes were read for this review.

## Required scientific interpretation

The unchanged protocol requires all 32 allocated sources and all retained siblings to pass custody and validity checks. Its explicit failure rule maps an incomplete or invalid allocation to `EXECUTION_BLOCKED`, without replacement. A timed-out source cannot be treated as a valid no-state source, assigned zero incremental gain, removed from the denominator or replaced by another source. Completing the other 31 sources cannot repair this primary comparison.

No K16 gain, harm, equivalence or conditional-inconclusive efficacy verdict is supported by this execution failure. Do not run the primary selection/evaluation stages on an incomplete subset. Preserve the distinction between a failed collection contract and evidence about the underlying K16-versus-K4 hypothesis. The closed RemoveLow confirmation, its cohort and its verdict remain separate and unchanged.

The coordinator has instructed the **existing fixed queue** to continue under its original source and global caps. That is not authorization for retries, additional sources, replenishment, resumed partial continuations or a longer cap. The absolute collection stop remains 14:22:24, with overall completion by 15:02:24.

## What the timeout says about feasibility

The proposal projected aggregate game-thread CPU: about 8.3 core-hours for typical four-option exposure or 12.4 for six options, before tail overhead. Dividing those totals by six estimated parallel throughput. It did **not** establish that every individual source's K32 continuation workload would finish within 1,800 process-wall seconds.

The earlier 7.1863-second average branch cost also does not bound the upper tail of a new source, its retained options, remaining horizon or machine contention. Process wall time and game-thread CPU are different quantities. This timeout demonstrates that the fixed per-source completion requirement failed for at least one allocated source; it does not, by itself, identify which cost mechanism caused it or prove that the aggregate projection was numerically wrong. The forecast's uncertainty was explicit, but a plausible aggregate budget was insufficient to guarantee complete fixed-cohort collection.

The receipt preserves partial output hashes and byte counts, but lacks a finalized manifest. Empty buffered source/log files do not prove the source trajectory never ran. Partial file size does not establish completed option/future coverage or the reason for the timeout. Integrity's separately scoped metadata/health investigation is the appropriate source for any narrower causal diagnosis.

## Closeout gates after the fixed queue ends

1. Account for all 32 allocated sources exactly once; preserve every successful, timed-out, failed, missing or incomplete receipt and the dispatcher exit status. No source may silently disappear.
2. Confirm the dispatcher and all owned game processes ended within the recorded caps; retain the actual start/end times and process-group termination evidence if applicable.
3. Preserve partial files and their identities. Run only the reviewed validity/accounting checks needed to record the failed collection contract; do not weaken validators to create a passing cohort.
4. Report `EXECUTION_BLOCKED`, the exact failure count and source locators, observed complete and censored cost separately, and the uncertainty of any diagnosis. Do not count unfinished work as zero cost or fabricate unrecorded CPU.
5. Keep the new experiment's disposition separate from the completed overnight result and draft-PR evidence. This review changes no frozen artifact, scientific threshold or production behavior.

Knowledge impact: execution-failure evidence and resource interpretation only. No policy-quality finding or new experimental authorization.
