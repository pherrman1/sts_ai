# Final confirmation independent scientific review

**Execution validity: PASS. Primary result independently reproduced: `CONFIRMED_IMPROVEMENT`.** The original frozen analyzer verdict is preserved verbatim. No games, source changes, additional candidate selection, extra contrasts, retries or extensions were performed for this review.

The [machine review receipt](FINAL_CONFIRMATION_REVIEW.json), SHA256 `579d8551afba25527c4aa34bf200ae02765e27116695af5b2b731e3973b8a773`, binds 33 control/provenance files and the complete 2,048-file raw input inventory through the original report. The [independent reviewer program](review_final_confirmation.py), SHA256 `f13cc88413f47ec6c7d5fa2127eef97a383c56a9ffbf69c52ea497c8a5c2911e`, re-executes the unchanged frozen validator in memory, independently parses the gameplay CSVs and computes the paired bootstrap, and independently scans every tree profile. Its retained execution log is `build/overnight_20261008/audit/final_confirmation_independent_review.log`, SHA256 `afbbb119a5e1a66974ac47d2619936739ac36e3a260be118814b85d826fe9f6f`. It writes only a new refuse-overwrite review receipt.

## Fixed trial and custody

All **512 allocated pairs / 1,024 full runs / 256 four-seed invocations** are present on exactly seeds `610083000..610083511`. Every invocation completed with exit 0, stayed below its 900-second cap, and has one unique receipt plus precisely its seven declared outputs. The directory inventory has no missing, duplicate, unrecorded or extra attempt/output file. The fixed alternating job list matches the receipt commands exactly; the dispatcher log accounts for all 256 receipts. The runner's existing-output refusal and single completed invocation per declared job support the recorded no-retry execution.

Source, binary, models, learned-stop model source, seed guard, runner, analyzer, imported bootstrap helper, final design, nomination review, runtime/static gates, job list, champion freeze and holdout latch all match their frozen hashes. The Python interpreter hash/version and NumPy 2.5.2 match the declared runtime. The only arm-profile difference is `STS_OOC_REMOVE_LOW_OBTAIN_WEIGHT: 0 -> 1`; both use the original tracked models, native Silver learned stopping, public8 fallback, optional-Recall filtering, keys off and an Act-3 cutoff.

The source is **`d35b42b1d5dc9819ec0f157027c68912bb82b8b7`**, binary SHA256 **`1dcc79169e60cc58865218cd66644dd2db61a9e9ceaafdf39c1b8a7b6600a8f5`**. The newer CardWinRank source and fetched main are not the tested producer.

The champion freeze precedes the holdout latch, which precedes every invocation. The independently reviewed launch package is hash-bound by that latch. The completion record reports no owned game workers; its epoch precedes the saved efficacy report's filesystem modification time and health invocation. Receipt intervals show at most six simultaneous workers, completing in **2,332.70 seconds (38m53s)**. The review does not overwrite the original preparation-time freeze status; the subsequent bound PASS launch review and latch close that gate.

## Primary arithmetic

| Paired outcome | Count |
|---|---:|
| Both win | 368 |
| RemoveLow only wins | 27 |
| Fprod only wins | 13 |
| Neither wins | 104 |
| Total | 512 |

Fprod wins **381/512 = 74.4140625%**. RemoveLow wins **395/512 = 77.1484375%**. The paired gain is **14/512 = 2.734375 percentage points**.

Independent CSV parsing yields every allocated seed exactly once per arm. A separate NumPy implementation samples the sorted 512-seed difference vector with the same fixed RNG 20261008 and 10,000 bootstrap replicates, without calling `paired_analysis.bootstrap_ci`. It exactly reproduces the frozen paired 95% percentile interval: **[+0.390625, +5.2734375] percentage points**. Re-executing the unchanged frozen analyzer also reproduces the entire saved report exactly after validating all bound raw files and effective runtime controls.

Both preregistered criteria pass: the paired lower bound is strictly positive and the **observed** gain exceeds the 2-point practical floor. The raw verdict remains **`CONFIRMED_IMPROVEMENT`**. The interval does **not** establish a true gain of at least 2 points; the minimum-effect criterion was explicitly a point-estimate condition. No post-hoc endpoint, alternative confidence interval or pooled development result is substituted for this primary decision.

## Runtime health

The independent scan reproduces the frozen health report across **457,287 roots** and **1,965,273,000 newly completed simulations**. Every source has tree coverage. Endpoint counts conserve completed simulations; tree/total-depth histograms and evaluator counts conserve their denominators; singleton and learned-stop budgets match their declared modes. Inherited visits are not counted as new work.

| Health metric | Fprod | RemoveLow |
|---|---:|---:|
| Tree roots | 228,340 | 228,947 |
| Completed simulations | 976,618,000 | 988,655,000 |
| Error strings / descent aborts / nonterminal endpoints | 0 / 0 / 0 | 0 / 0 / 0 |
| Cycle rollouts | 1,039 | 650 |
| Turn-limit endpoints | 159 | 218 |
| Engine-stop endpoints | 160 | 179 |
| Roots containing either diagnostic limit | 44 | 73 |

The health verdict is **`PASS_WITH_DIAGNOSTIC_LIMITS`**, with zero fatal findings. Cycle rollouts are recorded search behavior. Existing engine-stop and turn-limit endpoints remain documented diagnostic limits under the frozen protocol; no new outcome-dependent exclusion or quality threshold was introduced. This result must not be described as universally free of search safety stops.

## Scope of the conclusion

This supports a positive average effect for the single frozen removal-ranking treatment in the declared **fair Ironclad A0 Act-3 simulator benchmark regime**, relative to corrected Fprod. It does not show that every individual removal improves a run, that acquisition weights solve removal generally, or that the same effect holds with other models/controllers, keys-on/Act 4, other ascensions or the live game. The public encounter sampler and hypothetical feature approximations retain their previously documented scope.

It is not a comparison against original hidden-queue Bprod or a measurement on newly fetched main. Development supplied the nomination; only the fresh final cohort supplies this confirmation. The original source/binary identity must remain attached to these numbers after any later integration.

The review makes no automatic default-promotion or merge decision. Draft CI is not an authoritative passing check, and no live-game qualification is claimed. These boundaries do not change the faithfully reproduced raw result: **`CONFIRMED_IMPROVEMENT`**.
