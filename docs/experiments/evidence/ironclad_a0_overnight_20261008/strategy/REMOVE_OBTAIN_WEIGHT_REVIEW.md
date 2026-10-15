# Independent review: fallback REMOVE acquisition-weight experiment

Verdict: **PASS for the reviewed implementation, integration, and bounded experiment design. No source or protocol blocker found.** This review does not establish a gameplay improvement. Builds, fixture execution, immutable producer freezing, startup/teacher checks and the diagnostic runtime gate remain coordinator responsibilities; this reviewer ran no games, builds or test executables.

The review compares the candidate with base `b229f3ff2443b0decaacaa762d2a0c429f7e9d47`. It follows the already authorized one-factor hypothesis and does not redesign the removal policy.

## Exact reviewed identities

| Component | SHA256 |
|---|---|
| `git diff -- src/sim/search/ScumSearchAgent2.cpp include/sim/search/ScumSearchAgent2.h` | `e6c357e86b23d31a6bbb793ca7285874c7239c90ccb6e77acca13a2fcce4102d` |
| `tests/remove_obtain_weight_test.cpp` | `b9cef224233e22110e8c872280bcf4cda2951dd70eaaec221dd955a589ab5edd` |
| `git diff -- apps/one_combat.cpp apps/one_combat/combat_datasets.cpp CMakeLists.txt` | `75f8a4243e2d33f8c174d87f18a843e8a81917af813c79065025f7c6145b4784` |
| `analyze_wave_removal.py` | `85f51b7d0d3094f79d6d9b29dbb4a3fad1c04a8f2e08d974543a694af2c07d42` |
| `learning/test_analyze_wave_removal.py` | `ac3ca20a16b699efff82f9990b0bf7516b202b8cb8daf6ad80a7cd81b330a9bc` |
| `protocols/removal-screen-design.json` | `6e98c35db2c997718c7cf94cd1d1ac6642aac5da4f9399b3fab6b6d816b1a5c3` |
| `protocols/removal_development_reservation.json` | `b0f91da044a4a734305cd0e8597447f57661d7509103ba53b5a8949a34e9f3c1` |

## Implementation and integration findings

`oocRemoveLowObtainWeightEnabled()` accepts unset/`0` as false and `1` as true; empty, alternate textual or numeric forms throw. In `cardSelectPolicy`, only `CardSelectScreenType::REMOVE` uses the enabled flag. Its score changes from `-getObtainWeight(cardId)` to `+getObtainWeight(cardId)`, followed by the existing ascending `std::sort`. Thus enabled REMOVE selects the lowest acquisition-weight group. Unset/0 constructs the same scores and invokes the same sort and action execution as before.

The lookup remains card-ID-only. The implementation does not add upgrade weighting, curse priority, synergy rules, contextual models or a new tie-break. Comparison equivalence within equal-weight groups remains unchanged. `std::sort` is not a promised stable sort: the all-equal fixture proves preservation for that case, not a new general tie-stability contract for mixed groups after reversing their order.

BONFIRE_SPIRITS retains its original negative-weight branch. This is substantively necessary: `GameContext::chooseSelectCardScreenOption` awards rarity-dependent benefits, including +10 maximum HP/full healing for a rare sacrifice. Transform, transform-upgrade, upgrade, duplicate, obtain and bottle ordering are untouched. No RNG call was added, and no private-future or run-seed field is consulted.

The policy ranks indices in the existing `info.toSelectCards` list. `openCardSelectScreen(REMOVE, ...)` constructs that list using `canTransform()` and excludes bottled cards. Selection commits through the same `GameAction`/`GameContext` machinery, retaining original deck indices for multi-remove. The patch neither relaxes legality nor synthesizes a deck index. Empty/invalid selector handling is inherited and not altered by this change; there is no new supported-state claim for malformed menus.

The current full-run dispatcher sends a shop REMOVE to native `removeSelectVPolicy` when shopV is enabled, so this treatment applies to the Scum fallback owner rather than rewriting native shop ranking. Living Wall, Peace Pipe, Empty Cage and other fallback REMOVE contexts can be affected. That scope is broader than the two motivating Living Wall examples but is still one conceptual ranking change. The global flag may also affect other users of the same fallback; the campaign control disables MCTS and binds its effective teacher policy.

Coordinator wiring is correct: `main` calls the strict getter in the startup exception boundary, emits an enabled-only banner, and exits on invalid values. `effectiveOocPolicySpecification()` adds `flags.remove_low_obtain_weight=true` only when enabled, preserving the legacy specification when unset/0. CMake registers `remove_obtain_weight_test` with core objects, the repository seed guard, repository working directory and `integration;smoke` labels. Source whitespace checking passed. The startup banner establishes configuration, not proof that a real REMOVE decision reached the changed branch.

## Fixture assessment

The focused test file uses direct public fixtures, not generated runs. Its assertions test actual consequences rather than merely reproducing a scoring formula:

- Living Wall Forget really opens REMOVE, then removes Offering/Shrug under unset/0 and a basic Strike under1. Deck contents and HP/maxHP/gold are checked.
- Peace Pipe Toke really opens REMOVE and keeps Offering when the basic Defend is selected.
- A real selector excludes Ascender's Bane and a bottled Strike. The expected menu index differs from its deck index, so the fixture would catch an erroneous direct-deck-index implementation.
- Singleton and two-card removal cover forced legality, deferred commit and index tracking.
- All-equal65-weight cards, including upgraded copies, compare selected indices across unset/0/1 without assuming stable sort. The upgrade flag intentionally remains irrelevant to this lookup.
- Agent RNG and all fourteen game RNG objects are compared around selections. No extra random tie-break is introduced.
- Bonfire checks the actual rare-card +10 maximum-HP/full-heal transition in all modes. Upgrade/duplicate/obtain/bottle selectors retain their expected action, and transform stops after its first selection to avoid random transformation.
- Malformed flag cases and all three valid settings are explicit.

The other-selector fixtures construct legal menus directly; they are ordering regressions, not full acquisition-event simulations. There is no integrated native-shop routing fixture in this file. For this narrow patch, unchanged dispatcher source supports that boundary; the named default-off runtime comparison remains useful integration evidence. This review inspected the fixture but did not execute it or turn the coordinator's build report into an independent runtime claim.

## Scientific counterexamples and claim boundary

Acquisition weight is an imperfect removal objective. Upgraded basics remain weight0; some curses also fall through to0; Perfected Strike can value retaining strike cards; exhaust/curse/HP-payment synergies can make a nominally high-weight card a sensible removal. Equal-weight choices remain subject to the legacy ordering. These limitations make this an experimental policy alternative, not a deterministic dominance repair or illegal-mechanics correction.

The motivating corrected-reference sources010/011 both won. Their Living Wall decisions support the owner/ranking diagnosis, not an estimate of causal regret or evidence that the candidate rescues losses. The existing Bonfire behavior must remain independent because its sacrifice benefit changes the objective.

## Analyzer and experiment design review

`analyze_wave_removal.py` differs from the active analyzer by exactly three lines: it requires the enabled-only removal banner if and only if the declared environment has `STS_OOC_REMOVE_LOW_OBTAIN_WEIGHT=1`. Existing hash, receipt, complete-pair, source/binary, model, effective-environment, fairness, public-scorer-use, FullHp-banner and confirmation gates are preserved. In particular, an enabled flag with a missing banner and a disabled/unset flag with an unexpected banner are rejected.

The new test module redirects the inherited synthetic fixture suite to the copied analyzer only within that test process. It adds enabled-positive, enabled-missing, disabled/unset-unexpected, explicit-off-positive and preserved-FullHp-gate cases. It does not modify the active analyzer. These synthetic checks test provenance and analysis contracts, not simulator policy quality. Source inspection of the analyzer delta and its fixtures passed; execution remains with the coordinator.

The reviewed design allows four canaries, then a fixed32-pair/64-run discovery screen. Both arms use the same new immutable producer, original models, public8, optionalRecall1, FullHp0, shop-deck-fix0 and learned stopping. Only the candidate enables the new flag. Workers are capped at1 for this lane, campaign game processes at6, discovery wall time at3,600 seconds and each shard at900 seconds. All32 pairs must be valid; strict improvement in observed wins is the advance rule, with no extension.

Source610082010 is explicitly reused for a diagnostic canary after its development outcome was observed. The32 discovery sources are also marked adaptive reuse. Neither is fresh evaluation. The canary should compare an equal public prefix and actual changed Living Wall removal where reached; a banner alone is insufficient activation evidence. Absence of a reached target must remain explicit rather than be relabelled as activation.

The separate fresh allocation610082256..610082383 reserves128 matched Fprod/candidate pairs before runtime results. It is conditional on discovery advancement, disjoint from the earlier128-source development cohort and the separately reserved second development cohort, and not pooled with them. The analyzer requires exact complete seed coverage. No extension, combinations or second confirmation candidate are automatically authorized.

Selecting the greatest paired development gain among qualifying distinct candidates is explicitly exploratory. Different candidates may use different development cohorts, adding sampling noise to that comparison; the selection does not establish superiority or permit pooling. The lower-CPU/earlier-protocol tie rules are predetermined. Only one champion can be frozen and sent to the untouched610083000..610083511 confirmation allocation. Final scientific claims must come from that independently frozen confirmation, not these selection scores.

These documents are design/reservation records, not a launch manifest. Before any launch, the coordinator must bind the committed source, exact immutable binary, model hashes, effective environment, allocation and reviewed analyzer in the final manifest; complete the already planned startup/teacher and runtime gates; and retain failed attempts. This is the normal frozen-producer boundary, not a new request for user permission.

Knowledge impact: review evidence for a default-off experiment. No production default promotion or guaranteed win-rate benefit is established.

## Committed producer and static-check closure

The coordinator committed the reviewed implementation as `d35b42b1d5dc9819ec0f157027c68912bb82b8b7`. The reviewed source/header/fixture/startup/teacher/CMake paths have no diff from that commit. This reviewer rehashed immutable `build/overnight_20261008/binaries/removal-d35b42b1/one_combat` as `1dcc79169e60cc58865218cd66644dd2db61a9e9ceaafdf39c1b8a7b6600a8f5`.

The final four-run canary manifest `protocols/removal_canary.json` has SHA256 `80d32b02f2cabd089b0c0ad638ff425011154b750a91b18698a58daafccf58f7`. Its source/binary, model identities, two source seeds, common flags and sole candidate override match the reviewed design. This is a smoke manifest with explicit `runs`, not the later full paired-analysis manifest. No canary outcomes were opened by this reviewer.

Static receipt `audit/removal-static-checks.json`, SHA256 `6b1cd56edfefd0201188982821b637b7b2e7b59da974a393d288fb56eadace90`, reports successful Debug/Release builds, three focused passing CTests (Recall, FullHp and REMOVE), malformed-value rejection, and the producer self-test. This reviewer independently rehashed every cited build/test/startup/self-test log, read the three-test PASS and rejection/self-test output, and compared the emitted policy JSON: unset equals0 exactly, and1 adds only `flags.remove_low_obtain_weight=true`. These are verified existing executions; the reviewer did not rerun them. The receipt also records comparison to the prior producer's default-off policy; that prior-policy comparison was not independently repeated here.

The source/integration/static contract therefore has no remaining review blocker. Actual full-run default-off parity and changed-removal activation remain the canary's separate runtime gate, with no gameplay-quality conclusion yet.
