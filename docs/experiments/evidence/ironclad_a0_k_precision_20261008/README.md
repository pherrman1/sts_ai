# Boss-relic selection precision: K4 versus K16

**EXECUTION_BLOCKED.** The fixed collection finished with **31 completed sources
and one timeout**, and no game worker remained. Source `610084217` exceeded its
frozen 1,800-second cap. The complete-cohort contract returned `INVALID`, so
neither selection nor evaluation ran on these data. There is **no K4-versus-K16
quality verdict** and no substitute analysis of the completed subset.

The user authorized this separate four-hour follow-on after the original
campaign. Collection ran from **11:21:54 to 13:02:19 Europe/Berlin on
2026-10-08**, taking **100.4147 minutes** at a maximum of six one-thread workers.
Every reserved source was attempted exactly once; there was no retry,
replacement, cap change or extension.

| Retained execution evidence | Value |
| --- | ---: |
| Source invocations | 32: 31 exit 0, one timeout/exit 124 |
| Branch records from completed sources | 3,968 |
| Additional intact branch records from the timed-out source | 100 |
| Observed source CPU | 412.584270 seconds; one source unavailable |
| Observed branch CPU | 32,650.585663 seconds; interrupted work incomplete |
| Total emitted CPU cost | 33,063.169933 seconds = 9.184214 core-hours, censored |
| Sum of invocation wall times | 33,290.747188 seconds |
| Parallel dispatch elapsed | 6,024.881753 seconds |

These costs are distinct measures. Emitted CPU is a lower bound because source
217's source cost and buffered/in-progress continuation cost are missing. The
process-wall sum measures occupied process time; it is not parallel elapsed
time or an exact game-CPU total. The
[metadata accounting](analysis/BLOCKED_RESULT.md) and
[complete machine inventory](analysis/blocked_accounting.json) retain all 32
statuses, 255 source files and the dispatch log. Missing cost is not imputed as
zero. Available option rows from a truncated file do not define a complete
branch allocation.

The [timeout audit](audit/TIMEOUT_610084217_REVIEW.md) found 100 intact saved
continuations consuming 1,747.39344 CPU seconds—17.4739 seconds per recorded
branch, 2.43 times the historical average used for planning. All 38,235 saved
profiles passed the recorded health checks, and the profile was still
advancing immediately before termination. This supports a compute-cost tail,
within the limits of interrupted and buffered output. The aggregate cost
forecast did not bound this source's runtime. The timeout does not establish
K16 harm, equivalence or superiority.

Independent [custody and closeout review](audit/CLOSEOUT_REVIEW.md) passed
`PASS_BLOCKED_CLOSEOUT`; [scientific interpretation review](design/FINAL_INTERPRETATION_REVIEW.md)
passed for this failure accounting. Across all sources, 990,256 saved profiles
passed recorded health checks; interrupted and buffered work remains uncertified.
The [machine result](RESULT.json) records null efficacy and interval fields.

The earlier RemoveLow confirmation remains closed and unchanged:
`CONFIRMED_IMPROVEMENT` on its separate 512-pair cohort. Nothing from this failed
conditional attempt is pooled into that result.

The experiment asks whether using sixteen selection futures instead of four
improves the action chosen at the same boss-relic state. Thirty-two fresh source
seeds (`610084200..610084231`) each contribute at most one deterministically
sampled state. Both selectors share the same retained options, continuation
policy and tie rule. K4 uses futures 0–3, K16 uses 0–15; futures 16–31 evaluate
both frozen choices. An otherwise valid source with no state contributes zero
to the equal-weight mean over all 32 sources. A failed or missing source blocks
the primary result and is never converted to a zero or replaced.

The sole primary comparison is K16 minus K4 conditional final-win probability.
The 95% interval resamples whole source runs 10,000 times with RNG seed 20261008.
A positive lower bound supports a local conditional gain; a negative upper
bound supports harm; otherwise the result is inconclusive. This does not test a
whole-run policy or carry the earlier campaign's two-percentage-point threshold.
See the [frozen protocol](PROTOCOL.md) for the exact estimand and decision rule.

## Identity and execution

- Reviewed tools/protocol commit: `54c97fd0995c043ca584e75ff6af6da2fb032cf3`.
- Unchanged gameplay producer: `3ed91ab3491a4cdc1a7de687b2ad87dcc7774fc0`.
- Binary SHA256: `27a78efd3f5da731897d36dd9b50a622d2ace4f54dae69dfc157bf6712b027c7`.
- [Freeze](freeze.json) SHA256: `fc86c6e538618bf9212ffca58d422bda472954aa00f67a9216c3129c1a0df859`.
- [Ready bundle](ready_bundle.json), [dispatch specification](dispatch_spec.json),
  [one-time authorization](dispatch_authorization.json) and
  [initial process verification](initial_execution.json) preserve the release.
- Six one-thread CPU workers, each source capped at 1,800 seconds. The dispatcher
  had a 10,800-second process-group timeout ending by 14:21:54, slightly before
  the protocol's absolute 14:22:24 stop. It finished at 13:02:19, inside both caps.
- Raw outputs remain under
  `/home/philippherrmann/.codex/worktrees/ironclad-overnight-20261008/sts_lightspeed/build/overnight_20261008/learning/gen2-k-precision-3ed9/`
  in the preserved collection checkout. Each source receipt binds its command, environment and output hashes.

The original reviewed runner invokes every game through `tools/seed_guard.sh`.
It rejects prior output paths. This dispatch is fixed, with no retry, source
replacement, extension or outcome-driven stopping. The initial process check
observed all six workers, each with one thread and the frozen fair/Act-3/native
learned-stop environment. No training or GPU workload is part of this comparison.

## Review and reproduction

The [reviewer handoff](HANDOFF.md) separates scientific custody from the later
[integration checks](integration/README.md). The task branch was synchronized
with main at `61b9616a`; Debug configure/build passed, 21 of 22 selected checks
passed initially, and a standalone fixture's C++17-to-C++20 flag repair passed
the remaining test. The failed launcher invocation and compiler check are retained with their repairs.
The [static reconciliation review](audit/INTEGRATION_RECONCILIATION_REVIEW.md)
verified preservation of both parents and all frozen artifacts at that first integration.
Later main movement was integrated separately at `0734f3d1`, in the publication
checkout, while the collection checkout remains clean and detached at `08863cc6`.
[Collection custody](COLLECTION_CUSTODY.json) records the two absolute paths and
the intentional publication-only seed-guard difference. The [publication checks](integration_publication/README.md) passed the clean
eleven-target Debug build, 27/27 guarded CTests and a separate guarded observer
neutrality fixture. They are separate from the earlier 22 checks; neither
transfers gameplay qualification.

[Scientific review](design/SCIENTIFIC_DESIGN_REVIEW.md),
[source freshness inventory](design/source_freshness_inventory.json),
[independent verifier review](design/VERIFIER_IMPLEMENTATION_REVIEW.json),
[independent analyzer/prelaunch review](audit/PRELAUNCH_REVIEW.md), and
[final launch review](design/FROZEN_LAUNCH_REVIEW.json) preceded dispatch.
The new verifier and analyzer each passed twelve synthetic tests; the
metadata-only accounting helper passed ten. Each suite was independently
repeated by the other reviewer. No gameplay source or old frozen tool changed
for collection. Later branch synchronization is an integration check and does
not transfer the frozen producers' gameplay qualification to merged source.

The verifier checks all 32 source receipts, artifact custody, complete sibling
and MAP joins, terminal-label domains and native search health. It reports no
evaluation efficacy. On a complete valid collection, the analyzer would write a refuse-overwrite
choice file from selection outcomes only; a separate invocation would require
that exact file hash before interpreting evaluation outcomes. Here the
[contract receipt](audit/contract_receipt.json) is `INVALID`, so neither step was
invoked. The raw checker exit code is 1; dispatcher exit 123 preserves the one
failed child despite the other 31 successful invocations. The
[analysis methods and commands](analysis/README.md) document these stages.
Metadata reproduction needs the preserved raw files and executable/model
identities; a fresh Git clone does not include ignored raw artifacts. The
reviewed `account_blocked_collection.py` accepts the exact dispatcher-completion
and process-closeout hashes with a fresh exclusive output path. No game run is
needed. Do not redispatch the job list or invoke efficacy analysis on this
blocked allocation. The [process closeout](process_closeout.json) independently
records zero remaining workers and unchanged closed-confirmation hashes.

## Scope

Only retained legal options are compared. The existing sampler retains latent
counters and pool membership, so it is a conditional approximation rather than
an exact posterior over player-visible histories. The native profile has no
branch-ID tag: it checks seed membership and health without claiming a combat
profile for every branch. A valid branch can contain no combat. Search cycle,
engine-stop and turn-limit counts are reported separately from fatal errors.

The earlier RemoveLow champion and its completed 512-pair confirmation are
closed and unchanged. Historical protected TEST is outside this experiment.
No online selector, model training, production-default change, PR merge or further
holdout opening follows from this result.

Knowledge impact: a conditional experiment result and its uncertainty belong in
the experiment ledger and maintained current research page. No default baseline
promotion is implied.
