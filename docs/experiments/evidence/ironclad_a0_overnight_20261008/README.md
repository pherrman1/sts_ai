# Fair Ironclad A0 research campaign

**CONFIRMED_IMPROVEMENT under the frozen campaign criterion.** The one-time
512-pair confirmation finished with every pair valid. RemoveLow, an opt-in
reversal of fallback card-removal ordering, won **395/512 (77.15%)** versus
**381/512 (74.41%)** for its matched corrected-fair reference. The paired gain
was **+2.734375 percentage points**, with a 95% bootstrap interval of
**[+0.390625, +5.2734375]**. There were **27 candidate-only wins and 13
control-only wins**. Both the strictly positive lower bound and the predeclared
2 pp practical threshold pass; the raw analyzer verdict is
`CONFIRMED_IMPROVEMENT`.

| Final arm | Act-3 wins | Descriptive Wilson 95% interval | Game-thread CPU |
|---|---:|---|---:|
| Fprod | 381/512 (74.41%) | 70.46%–78.00% | 6,844.15 s |
| RemoveLow | 395/512 (77.15%) | 73.32%–80.58% | 6,949.05 s |

The paired interval, rather than overlap of the per-arm intervals, governs the
comparison. Final execution took **38.88 minutes elapsed** across at most six
workers and **3.83144 game-core-hours** in total. The candidate used about
1.53% more measured CPU. No final seeds were replaced, repeated or added.
This establishes an improvement for the frozen simulator/profile comparison;
it does not establish live-game parity or authorize default promotion.

RemoveLow was nominated before holdout opening from development's 106/128
versus 104/128 (7/5 discordances, +1.5625 pp, interval [−3.90625, +7.03125]).
Those exploratory outcomes were not pooled with confirmation.

The campaign tests Ironclad Ascension 0, victory over the Act-3 boss, fair
information, and keys off with no optional key detours; forced-only Recall
remains legal. It began at 01:47 Europe/Berlin on
2026-10-08 with an eight-hour cap. All work is isolated on
`codex/ironclad-overnight-20261008`; production defaults and model bytes remain
unchanged. Nothing is merged.

## Read the evidence

- [Ranked hypotheses and dispositions](HYPOTHESES.md): every attempted or
  deferred hypothesis, competing explanations, evidence, uncertainty and cost.
- [Decision cases](DECISION_CASES.md): public-state locators, chosen and
  alternative actions, defect versus policy classifications, tests and limits.
- [Complete results](learning/FINAL_RESULTS.md): all
  21 full-run contrasts, exact discordances and intervals, separate conditional
  experiments, and per-arm CPU/process-wall costs without counting shared
  controls repeatedly.
- [Champion freeze](champion_freeze.json), [final protocol](protocols/final_confirmation.json),
  [independent launch review](strategy/FINAL_CONFIRMATION_LAUNCH_REVIEW.json),
  and [holdout latch](holdout_opened.json): the single fixed 512-pair comparison.
- [Final attempt accounting](learning/ATTEMPT_ACCOUNTING_v3.md): **799 completed
  runtime invocations**, including **2,687 requested full-run trajectories**,
  39 source/conditional-branch invocations, 64 public-combat pair invocations
  and one public-state check. No failed, timed-out or pending game jobs.
  Expected startup failures, build failures, prelaunch rejections and repaired
  validator defects are separately retained.
- [Primary final report](final_confirmation_report.json),
  [complete health audit](audit/final_confirmation_health.json) and
  [worker shutdown receipt](audit/final_execution_completion.json): every one of
  256 final jobs exited successfully, with no remaining campaign game worker.
- [Independent final review](audit/FINAL_CONFIRMATION_REVIEW.md) and
  [machine verdict](campaign_result.json): the frozen report, primary arithmetic,
  bootstrap, all output hashes and complete health counts were independently
  reproduced. The interval supports a positive gain; it does not establish
  that the true gain is at least 2 pp.
- [Current state](STATE.json): process ownership and restart boundaries. An
  opened holdout is not authorization to retry, extend or retune it.

## Reference, champion and custody

The campaign base is `a4b3df35d170abba7860e8e854cc24cfd3579075`. The complete
implementation source at `5add2413281c95a29e32846531d41353c804fd3c` includes all
experimental alternatives. Final confirmation deliberately uses the previously
reviewed immutable removal producer
`d35b42b1d5dc9819ec0f157027c68912bb82b8b7` in **both** arms; the later card-ranking
alternative failed discovery and is disabled/unavailable in this producer.

The final executable is
`build/overnight_20261008/binaries/removal-d35b42b1/one_combat`, SHA256
`1dcc79169e60cc58865218cd66644dd2db61a9e9ceaafdf39c1b8a7b6600a8f5`.
Its baseline and candidate use the same controlled environment:

| Setting | Both arms |
|---|---|
| Objective | Ironclad A0, `STS_STOP_AFTER_ACT=3`, `STS_COLLECT_KEYS=0` |
| Combat | Native Silver, learned stopping on, adaptive off, exact-root budgets off |
| Budget | Nominal argument 10,000; learned checkpoints determine actual added simulations; singleton bypass remains active |
| Reuse | Allocated cap, effective 32,768 |
| OOC | MCTS off; usual V4 REST/event/shop/treasure/boss gates and margin 1 |
| Fair native fallback | `STS_OOC_PUBLIC_FUTURES=8`; legacy actual-future hypothetical policies disabled |
| Common campfire correction | `STS_OOC_SKIP_OPTIONAL_RECALL=1`; forced-only Recall remains legal |
| Other alternatives | FullHp, shop feature fix, final-boss binary objective and alternate card-win paths off |
| Threads | One OpenMP/BLAS thread per process; at most six game processes |
| Sole difference | `STS_OOC_REMOVE_LOW_OBTAIN_WEIGHT=0` for Fprod, `1` for RemoveLow |

The removal change only changes fallback `REMOVE` ranking from high to low
acquisition weight. It preserves legal-card enumeration, bottling restrictions,
multi-removal behavior, native shop removal and Bonfire sacrifice ordering.
It is a policy hypothesis: acquisition weight ignores deck-specific synergy
and upgrades, so reversing it is not a universally correct removal strategy.

All model bytes are unchanged and bound in each manifest:

| Artifact | SHA256 |
|---|---|
| `models/v_rich_trees.txt` | `3a3420469b1d648e0e306d6cb6a7e85f3d3499105e3ff3a56eee6c579194ffe3` |
| `models/v_win_trees.txt` | `fc52c14cb7239a33b3c1f9d0477ccb6c895fd51a07240fe804744e605067ad70` |
| `selfplay/models/ooc_strategic_tok_final.native` | `e62abd833fc8cb9081a1cec4a1a012832ac3b0e3166da3892841911664f1184c` |
| `src/sim/search/NativeSilverStopModel.cpp` | `74c70373f985affb518047829710e91fffd6122901f1addd9285797a95216c1b` |

The final manifest also binds the runner, analyzer, imported `paired_analysis.py`,
seed guard, health auditor, scientific design, nomination review and actual
Python/NumPy runtime. Every invocation rechecks immutable binary/artifact hashes;
analysis checks effective mode/model metadata, inference-use banners, exact seed
coverage and every emitted output hash.

## What the decision audit established

**Reproduced defects.** The original native fallback can read actual unrevealed
encounter identities despite `STS_FAIR=1`. The opt-in public-scenario wrapper
passes hidden-state perturbation, source-state and RNG-preservation checks.
Original Bprod/Bflat measurements are therefore diagnostic, not the primary
fair comparator. A separate keys-off defect allows optional Ruby Recall; its
regression fails before the shared eligibility correction and passes afterward.
Shop hypothetical deck-size arithmetic also fails a baseline fixture. Its
correction is real, but it did not earn strength advancement on fresh development.

**Measured current-reference losses.** In the outcome-unselected corrected
128-source reference, 101 runs won and 27 lost: three losses in Act 1, eight in
Act 2 and sixteen in Act 3. Thirteen losses were at the final boss. The corrected
first twelve trajectories contain both wins and losses and support the
[chronological atlas](strategy/CORRECTED_REFERENCE_ATLAS.md); these counts do not
identify which losses a stronger combat or preparation policy could recover.

**Mechanisms with bounded causal evidence.** A same-state shop example isolates
the arithmetic change in the selected bundle. A Living Wall example changes
removal from Shrug It Off to Strike with an identical public prefix. FullHp and
RemoveLow rescued the same discovery source through different chains: FullHp
enabled Shovel digs and later Anchor, whereas RemoveLow preserved Reaper early.
The whole-run rescue cannot be uniquely attributed to one downstream item, and
these gains are not additive.

**Disconfirmations and open questions.** At one outcome-informed public Champ
root, the probe did not support forcing Shrug It Off over End Turn: 50 versus
51 combat wins on 62 paired conditional future draws under a fresh exact-10k
continuation. These are not 62 independent source decisions or the original
retained learned-stop controller. All three original potions were already used by turn 2.
All 32 free chests and all 112 ordinary relic offers in the corrected first
twelve runs were collected, so a free-treasure omission screen was not justified.
Full-health rest can still be questionable, but one selected Offering-upgrade
counterfactual remained inconclusive. No hidden historical hand, draw order or
combat state was fabricated from aggregate features.

## What the learning lane established

The reviewed GEN2 tranche collected 32 fresh source trajectories, 63 retained
card/boss decisions and 1,968 valid sibling continuations. Selection used
futures 0–3; choices were saved and hashed before a separate evaluation of
futures 4–7. The fixed-rule evaluation contains 252 state/future pairs clustered
within 32 sources; 1,968 counts all retained actions across both splits.
Equal-source rollout-selected gain was −1.171875 pp, source-cluster
95% interval [−5.46875, +3.125]: **LOCAL_CONDITIONAL_INCONCLUSIVE**.

Its apparent selection gain was +10.55 pp. The collapse on independent futures
supports small-K selection optimism as a concrete concern. Queue-blind historical
P0/F2 models also failed to establish action-selection gains. Their 457-feature
mask retains latent potion/rarity counters and labels from an older privileged
teacher; these results do not qualify a fair deployment. Boss-relic probability
bias and larger post-map prediction dispersion do not alone establish temporal
drift, a ranking defect, or map uncertainty as the cause. See the
[primary report](learning/GEN2_TRANCHE_RESULT.md) and
[separately reviewed exploratory analysis](learning/GEN2_EXPLORATORY_RESULT.md).

The tranche consumed 4.15072 observed game-core-hours. This measured cost,
limited label breadth and unresolved selection noise supported keeping the
remaining budget for independent whole-run qualification instead of scaling
collection and training. Existing models were reused; no speculative GPU
training or duplicate CTM retraining was launched. Protected historical TEST
partitions remained unopened. Conditional labels were not pooled into final
whole-run confirmation.

## Verification and limits

Source changes are default off and independently reviewed. Focused checks cover
public-information invariance, shop arithmetic, optional Recall, FullHp,
removal ranking, card ranking, terminal utility, targeted continuation custody,
trace neutrality, startup rejection and teacher-policy serialization. Named
runtime canaries establish actual branch use and default-off trajectory parity.

The Debug all-target build and **67/67 core/smoke tests** passed at `a557ace5`,
before the later FullHp/removal/card-rank additions. The two extra affected
integration checks passed. Each later addition has its own focused Debug,
Release, startup/producer and runtime-canary evidence; the earlier 67/67 result
is not relabeled as a full-suite run at the latest source. See
[integrated verification](audit/integrated-verification.json),
[FullHp checks](audit/fullhp-build-static-checks.json),
[removal checks](audit/removal-static-checks.json), and
[card-ranking checks](audit/cardrank-static-checks.json).

The supplementary full-run health audit validates every root's budgets and
endpoint conservation. Final confirmation covers 457,287 roots and 1,965,273,000
newly completed simulations with zero root errors, descent aborts or nonterminal
endpoints. It retains 1,689 intentional cycle rollouts, 339 engine-stop and 377
turn-limit search endpoints as diagnostic limits. Completed preconfirmation cohorts have no root errors,
descent aborts or unresolved endpoints; intentional cycle fallback and occasional
engine-stop/turn-limit search endpoints are retained as diagnostic limits.
These counters do not establish live-game equivalence. The public-future sampler
is a reviewed conditional approximation, not an exact posterior over every
hidden history. Historical model/controller mismatch and approximate action
features remain limitations.

Final task-scope, local-link, whitespace, worktree/submodule and repository-health
checks passed. A virtual merge with observed main `dd308d3d` has no textual
conflicts after relocating three documentation verification dates; no merged
source was built or used for the experiment. See the
[packaging receipt](audit/FINAL_PACKAGING_CHECKS.json).

GitHub Actions `Linux GCC` is the authoritative repository gate. Its workflow
skips draft PRs; local passes do not establish a CI pass. No live-game
qualification, default promotion, merge or automatic follow-up experiment is
part of this handoff.

## Raw evidence and reproduction

The worktree is
`/home/philippherrmann/.codex/worktrees/ironclad-overnight-20261008/sts_lightspeed`.
Large raw outputs and named immutable binaries remain under its ignored
`build/overnight_20261008/` directory. Small protocols, exact input/output hashes,
source reviews, reports and analysis programs are versioned in this packet.
Preserve that ignored directory before any worktree archival; the tracked
packet alone cannot reproduce the raw trajectories. This worktree is retained.
Every seed-driving command went through `tools/seed_guard.sh`. Every job has a
refuse-overwrite output prefix and a command/environment/exit/hash receipt.

The final job list is `build/overnight_20261008/final_confirmation_jobs.txt`.
The final comparison uses `analyze_wave_removal.py`; older waves retain their
own frozen analyzer versions. Reanalysis must write a new report path. The
recorded launch command is provenance, not permission to retry an opened holdout.

The retained local files support this
read-only reproduction of the primary analysis from the campaign worktree:

```bash
.venv/bin/python docs/experiments/evidence/ironclad_a0_overnight_20261008/analyze_wave_removal.py \
  docs/experiments/evidence/ironclad_a0_overnight_20261008/protocols/final_confirmation.json \
  build/overnight_20261008/final_confirmation \
  --out build/overnight_20261008/final_confirmation_reanalysis.json
```

The output path must not already exist. The frozen reports and receipts bind
absolute paths in this preserved worktree; a fresh clone alone does not contain
the ignored executable and raw trajectories. No game invocation is needed for
reanalysis. Per-arm CPU totals sum measured game-thread CPU, and per-arm process
wall totals sum shard durations; neither is the elapsed parallel campaign time.

## Single best next experiment

Run the proposed fresh 32-source, boss-relic-only **K4 versus K16 selection**
comparison at identical states, freeze both choice sets, then evaluate on shared
independent futures 16–31. This isolates selection precision from source mix and
historical model drift. Its estimate is 8.3 game-core-hours typically or 12.4
with six retained options, before tail cost. The proposed four-worker,
four-hour limit gives a 16-game-core-hour ceiling, not a completion guarantee;
it was not launched. The
[exact proposal](learning/gen2_next_k_experiment_proposal.json) preserves the
no-training and no-adaptive-extension boundaries.

Knowledge impact: experiment outcomes belong in ledger §395; current research
disposition and the native information-boundary caveat belong in maintained
evaluation pages. New opt-in controls and diagnostic interfaces are documented
in the architecture, environment and label-pipeline pages. No production
baseline or model is promoted automatically.
