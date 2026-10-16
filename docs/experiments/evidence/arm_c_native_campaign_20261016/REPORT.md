# §494 native cloud collection: COMPLETE (2026-10-16)

This is the **historical collection-stage snapshot**, before fitting and TEST.
Fitting and one-shot TEST subsequently completed with verdict **NOT_SHOWN**;
see [the retained result](fit/eval/fit/test-result.json) and
[ledger §494, “Fit and one-shot TEST”](../../ledger-06.md#fit-and-one-shot-test-2026-10-16).
The frozen launcher and raw artifacts below describe that completed run; they
are historical evidence, not instructions to launch another campaign.

**64/64 fresh sources collected, all return 0 on attempt 1, inside the single deadline. No fit, no TEST opening.**

## Frozen identities
- RUN_COMMIT `b8aea9001674c28dd2dd6abf2cf15d02ddafcfd8` (PR #568; tools identical to reviewed `ac769d33`;
  lead canaries ran tool code `a64e0a32`, whose canary/unit/bundle paths are identical).
- Scientific source `9d83adbbbcc0fabf2c8bcd8c6a87f9782d0acbc3`; producer `one_combat`
  `86a7569fe56cfdd2f635018147f005b16870598c53c7c164a5d1edd994ecbacf` (Ubuntu GCC 13.3; byte-identical to the
  original local producer, so no new producer). Every worker rebuilt and checked this hash.
- `studentc.bin` `eff2f74f…6509` (project share copy; not re-exported, Philipp 10:28Z).
- Plan `plan32.json` `b4c28ae0…f89e` (32 workers x 2 contiguous seeds; W25-32 TEST only); bundle `f8ecb31a…8b19`.
- Deadline `deadline.json`: 11:31:09Z to 17:31:09Z (21600 s), created once, bound to the plan and reviewed canary.

## Canaries (independently reviewed PASS, bound to canary.json `08383bac…` / canary-lead.tar.gz `23cb550d…`)
- 110163994 capture OFF vs ON: byte-identical decision and action traces.
- Coverage (`validate_rows`, expected policy heart1): 994 ON 352/352 rows, 13 groups; 995 ON 411/411, 15 groups.
- Arm C: tree prior 100% scored, rollout 100% scored, 0 fallbacks, 0 legacy prior-leaf steps, shape 64/4/256/2/trim1.
- 995 repeated in a second container: trace/actions/support byte-identical; capture rows differ only in the
  timing fields `rolloutCpuSeconds`/`anchorCpuSeconds`. Same CPU model, so this is not a cross-CPU check.

## Collection
- 32 Haiku cloud threads, launched 11:31-11:37Z; last receipt 12:43Z. All 32 ran on
  "Intel(R) Xeon(R) Processor @ 2.10GHz" (4 vCPU, 15 GiB), the lead canary's model, so no CPU types were mixed
  and the per-worker cross-CPU canary never triggered.
- Every source: share receipt written after its archive (`collect/sources/seed-N.attempt1[-SEALED].tar.gz`), both
  verified by the lead from its own container. No reruns were needed (all attempt 1).
- Non-TEST sources (48): inner receipt and every file hash match; Arm C contract 100% tree prior and rollout
  scoring on every source; coverage 100% valid rows. Wall seconds min 155.5, median 1203, max 3397.8 (cap 3600).
- Fit gates on non-TEST data: TRAIN 18,570 rows, 663 multi-action groups (>=500); VALIDATION 2,721 rows, 114
  groups (>=100); every TRAIN/VALIDATION source has groups. TEST: 16 sealed archives, hash custody only.
- `lead-verification.json` (per-source checks), `receipts/` (64 share receipts), `corpus-manifest.json`.

## Durable artifacts (project share, `/mnt/project-files/arm-c-native-campaign/`)
- `corpus/corpus-train-validation.tar` `03d29264…0686`, `corpus/corpus-test-SEALED.tar` `42b035fe…bf69`
  (TEST archives packed without extraction), `corpus/corpus-manifest.json` `cd8929b1…1c19`. All three were
  re-read with matching sha256 from a separate container at 12:45Z.
- `collect/` raw per-source archives, receipts, claims, DONE files; `canary-lead.tar.gz`; `canary-cpu2/`.

## Deviations (none affects data or TEST custody)
- W17 started its run step twice; the guard refused the duplicate ("attempt 1 still running here") and that
  invocation wrote a stray `w17-train.DONE.json` with error outcomes; the real run completed normally.
- W24 printed the tail of a VALIDATION source log ("win% 0.0") while checking progress. W29 read TEST share
  receipts (custody metadata only). No TEST JSONL was opened anywhere.
- The first cross-CPU canary thread was refused by its auto-mode classifier for running a script from the share;
  launcher scripts were moved into the repository at a pinned commit and a fresh thread ran it.

## Not yet done at the collection snapshot
- No fit and no TEST opening. Before TEST, the CPU-cost comparison must be frozen and reviewed: the teacher ran
  on one cloud CPU model, so a same-model cloud evaluator is the qualified option.
- No native student deployment, default change or gameplay claim.
