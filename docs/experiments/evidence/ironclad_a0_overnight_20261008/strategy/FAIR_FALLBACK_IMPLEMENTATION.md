# Public encounter mixture for native OOC fallback

## Finding and bounded repair

The current V4 token builder explicitly omits eight legacy queue-derived fields. Its one-ply Q calculations do not read floor-model features. When its card/shop gates decline ownership, native fallback methods build the complete rich row from the real GameContext. Four fields (`nextEliteId`, `nextFight0`, `nextFight1`, `nextFight2`) expose the actual unrevealed encounter suffix. Thus `STS_FAIR=1` alone does not establish a fair whole-run OOC profile.

Authorized opt-in repair: `STS_OOC_PUBLIC_FUTURES=8`. Unset/0 preserves legacy predictions; malformed settings and positive-mode acts outside 1..3 fail closed. All native fallback model predictions share one sampled scenario set per decision. Each scenario replaces those four fields using the same native encounter population/exclusion rules as the existing `sampleNoncombatFuture` helper, conditional on the already observed encounter prefix. Scenarios are seeded by a versioned FNV hash of public rich fields and the current screen; the true game seed, RNG state, and all eight legacy queue-derived fields are excluded. Actual game/RNG state, visible map, published offers and other pools remain unchanged. The model consumes supported categorical encounter IDs. We average predicted outputs, including averaging probabilities after the logistic transform.

The representation intentionally preserves the project's approved simulator continuation contract for encounter counts/offsets and other historical counters. This correction does not replace that contract with a live-observation importer or claim a broader sensor audit.

## Owned source and tests

- `apps/one_combat/ooc_native_fallback.{cpp,h}`: internal public scenario scorer and `nativeOocValue(gc,path,model)` entry point; all fallback card/shop/removal/heal/upgrade predictions use it.
- `apps/test_ooc_public_futures.cpp`: one fixed native fixture, no whole-run traversal. Tests a deliberately hidden-sensitive legacy card model; unset/0 exact equivalence; all four hidden fields over three acts; all RNG seeds and counters plus true game seed and hidden suffix changes; selected-card/removal/upgrade/heal/shop invariance; source fingerprint unchanged; exhausted suffix; logistic probability mixture; malformed configuration and unsupported act rejection.
- Coordinator owns CMake linkage, direct `nativeFloorValue`/`vStateWin` wrapper routing and execution. No tests/builds were run by this specialist.

Independent source review was requested from the integrity specialist before execution. Its initial review found no blocker in the controlled acts1..3 profile and requested empty-suffix/non-target-act coverage, which was added. Await executed tests and final review before freezing the new baseline.

## Controls beyond this helper

The controlled campaign profile must keep unrelated alternate policies disabled. In particular, `nativeWinCardPick` in main still uses raw vectors when `STS_CARD_WIN=1`; the campaign sets it to zero. The generic `vStateWinNativeFeatures(raw)` is also used for model diagnostics and sampled MCTS states and was not globally rewritten.

`bossRelicVPolicy`, `neowVPolicy` and `eventVPolicy` first execute copied actions against real RNG before valuing a successor. Replacing the value helper does not make those preexisting stochastic action previews fair. Keep `STS_BOSS_RELIC=0`, `STS_NEOW_V=0`, `STS_EVENT_V=0` and all legacy probe/route/shop-beam policies off in the primary profile. V4 token Q scoring is already based on public predecision state.

The same fair mixture must be present in both arms of a strength comparison. Do not reuse pre-repair historical or campaign legacy results as a fair control or relabel them retrospectively. Qualification of gameplay improvements remains separate from this information-boundary correction.

## Execution receipt and follow-up

The coordinator reported `apps/test_ooc_public_futures.cpp` passed, with raw output at `build/overnight-public-futures-test.log`. Source review then added per-thread actual-scorer counters and exported validated configuration getters for startup/provenance receipts. Counter updates cannot affect scenario seeds, game state or action choices. The final build/test receipt remains coordinator-owned.

S01 was separately reproduced by the coordinator's synthetic native model fixture (`tests/native_ooc_shop_features_test.cpp`): frozen pre-fix run failed with `relic purchase incorrectly adds a card` (`build/overnight-shop-baseline-fail.log`). The opt-in `STS_OOC_SHOP_DECK_SIZE_FIX=1` now counts selected cards, excludes ordinary relics from generic deck growth, and subtracts one for a planned removal. It deliberately does not attempt to model card-changing relic effects or alter other feature approximations. Unset/0 retains legacy accounting. The correction is a separate experimental flag, not silently included in the fair-information baseline. Independent integrity review and executed correction test remain required.
