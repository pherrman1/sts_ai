// Focused live->wire->isolated-Silver boundary tests.  This executable has a
// separate link closure so ordinary unit-test never links the full vendor model.
#include <algorithm>
#include <cmath>
#include <iostream>
#include <set>

#include "combat/BattleContext.h"
#include "game/GameContext.h"
#include "sim/search/CombatKnowledge.h"
#include "sim/search/CombatValueNet.h"
#include "sim/search/ScumSearchAgent2.h"
#include "sim/search/SilverBridge.h"
#include "sim/search/SilverConversion.h"
#include "sim/search/SilverLiveBackend.h"
#include "sim/search/SilverSemanticAction.h"
#include "sim/search/SilverWireJson.h"

using namespace sts;

namespace {

CardInstance card(CardId id, std::int16_t uid) {
    CardInstance result(id);
    result.uniqueId = uid;
    return result;
}

void installPile(BattleContext &bc) {
    bc.cards.drawPile = {card(CardId::STRIKE_RED, 11), card(CardId::DEFEND_RED, 12), card(CardId::BASH, 13)};
}

silver_bridge::BattleStateWire convert(const BattleContext &bc, const GameContext &gc,
                                       const search::CombatKnowledgeState &knowledge) {
    return search::makeSilverBattleStateWire(bc, knowledge, search::makeSilverRunContext(gc), 0xA11CEu);
}

} // namespace

int main() {
    int failures = 0;
    const auto check = [&failures](bool ok, const char *message) {
        if (!ok) { std::cerr << "  " << message << '\n'; ++failures; }
    };

    GameContext gc(CharacterClass::IRONCLAD, 0x5151u, 0);
    BattleContext first;
    first.init(gc, MonsterEncounter::CULTIST);
    installPile(first);

    // Smoke Bomb is a shared live-simulator rule. Silver communicates the
    // visible potion identity/slot semantically; lowering must accept its use
    // on an eligible hallway fight and reject use (while retaining discard)
    // when the live combat blocks escape. There is intentionally no
    // Silver-specific Smoke Bomb adaptation here.
    BattleContext smoke = first;
    smoke.potions[0] = Potion::SMOKE_BOMB;
    smoke.potionCount = 1;
    silver_bridge::SemanticAction smokeUse;
    smokeUse.type = silver_bridge::SemanticActionType::POTION;
    smokeUse.potionId = static_cast<std::int16_t>(Potion::SMOKE_BOMB);
    smokeUse.potionSlot = 0;
    smokeUse.target = 0;
    const auto resolvedSmoke = search::resolveSilverSemanticAction(smoke, smokeUse);
    check(resolvedSmoke.ok
              && resolvedSmoke.action == search::Action(search::ActionType::POTION, 0),
          "eligible Silver Smoke Bomb use must resolve to the live use action");

    BattleContext blockedSmoke = smoke;
    blockedSmoke.encounter = MonsterEncounter::HEXAGHOST;
    const auto blockedUse = search::resolveSilverSemanticAction(blockedSmoke, smokeUse);
    check(!blockedUse.ok,
          "blocked Silver Smoke Bomb use must fail live semantic resolution");
    smokeUse.discardPotion = true;
    const auto blockedDiscard = search::resolveSilverSemanticAction(blockedSmoke, smokeUse);
    check(blockedDiscard.ok
              && blockedDiscard.action == search::Action(search::ActionType::POTION, 0, 6),
          "blocked Silver Smoke Bomb must retain a valid discard resolution");

    BattleContext permuted = first;
    std::swap(permuted.cards.drawPile[0], permuted.cards.drawPile[2]);
    search::CombatKnowledgeState firstKnowledge, permutedKnowledge;
    firstKnowledge.initializeFromLiveBattle(first);
    permutedKnowledge.initializeFromLiveBattle(permuted);
    const auto firstWire = convert(first, gc, firstKnowledge);
    const auto permutedWire = convert(permuted, gc, permutedKnowledge);
    check(silver_bridge::inspectConvertedBattleState(firstWire).accepted,
          "ordinary wire must materialize a private Silver root");
    check(silver_bridge::convertedStatesEqualForSearch(firstWire, permutedWire),
          "hidden live draw-order permutations must materialize equivalent Silver roots");

    const auto serializedWire = silver_bridge::battleStateWireEnvelope(firstWire).dump();
    const auto reloadedWire = silver_bridge::battleStateWireFromEnvelope(
        nlohmann::json::parse(serializedWire));
    check(silver_bridge::convertedStatesEqualForSearch(firstWire, reloadedWire),
          "BattleStateWire JSON round-trip must preserve the exact Silver search state");
    search::g_richCombatFeatures = true;
    std::vector<float> directFeatures(search::combatFeatureCount());
    search::combatExtractFeatures(first, directFeatures.data());
    const auto wireFeatures = search::silverLiveLeafCanonicalFeatures(reloadedWire);
    check(wireFeatures == directFeatures,
          "stored Silver wire must reproduce canonical rich combat features exactly");
    const auto teacherActions = silver_bridge::enumerateSilverLegalActions(reloadedWire);
    const auto policyRows = search::silverLiveParentPolicyFeatures(reloadedWire);
    check(!policyRows.empty(), "restored parent must emit policy feature rows");
    check(policyRows.size() == teacherActions.size(),
          "teacher/restored/emitted policy action counts must match");
    std::set<std::string> teacherSet, restoredSet, emittedSet;
    for (const auto &action : teacherActions)
        teacherSet.insert(silver_bridge::semanticActionFingerprint(action));
    for (const auto &row : policyRows) {
        restoredSet.insert(row.actionFingerprint);
        emittedSet.insert(row.actionFingerprint);
        check(row.features.size() == static_cast<std::size_t>(search::combatPolicyFeatureCount()),
              "policy row must use current canonical feature count");
    }
    check(teacherSet.size() == teacherActions.size(),
          "restored legal semantic fingerprints must be unique");
    check(teacherSet == restoredSet && restoredSet == emittedSet,
          "teacher action fingerprints == restored legal fingerprints == emitted feature rows");
    auto incompatibleEnvelope = silver_bridge::battleStateWireEnvelope(firstWire);
    incompatibleEnvelope["wire_version"] = 999;
    bool incompatibleRejected = false;
    try { (void)silver_bridge::battleStateWireFromEnvelope(incompatibleEnvelope); }
    catch (const std::invalid_argument &) { incompatibleRejected = true; }
    check(incompatibleRejected, "incompatible BattleStateWire schema must fail closed");

    silver_bridge::SilverSearchConfig serializedSearchConfig;
    serializedSearchConfig.simulationsPerDecision = 12;
    serializedSearchConfig.reuseCapMode = silver_bridge::SilverReuseCapMode::NONE;
    serializedSearchConfig.collectRootActionSummaries = true;
    const auto inMemorySearch = silver_bridge::runSilverDecision(firstWire, serializedSearchConfig);
    const auto reloadedSearch = silver_bridge::runSilverDecision(reloadedWire, serializedSearchConfig);
    check(inMemorySearch.accepted && reloadedSearch.accepted
          && silver_bridge::semanticActionFingerprint(inMemorySearch.action)
              == silver_bridge::semanticActionFingerprint(reloadedSearch.action)
          && inMemorySearch.rootActionSummaries.size() == reloadedSearch.rootActionSummaries.size(),
          "serialized/reloaded leaf must reproduce an identical deterministic small-budget search");

    silver_bridge::SilverLeafObservation capturedLeaf;
    bool capturedLeafStart = false;
    auto parentObserverConfig = serializedSearchConfig;
    parentObserverConfig.simulationsPerDecision = 16;
    parentObserverConfig.leafObserver = [&](silver_bridge::SilverLeafObservation &o) {
        if (!capturedLeafStart && o.phase == silver_bridge::SilverLeafObservationPhase::START) {
            capturedLeaf = o;
            capturedLeafStart = true;
        }
    };
    (void)silver_bridge::runSilverDecision(firstWire, parentObserverConfig);
    check(capturedLeafStart && capturedLeaf.parentState.valid
          && capturedLeaf.originalRootState.valid
          && !capturedLeaf.parentLegalActionFingerprints.empty()
          && !capturedLeaf.incomingActionFingerprint.empty(),
          "leaf observer must retain exact root/parent states and complete parent action identity");
    if (capturedLeafStart) {
        const auto parentReloaded = silver_bridge::battleStateWireFromEnvelope(
            nlohmann::json::parse(
                silver_bridge::battleStateWireEnvelope(capturedLeaf.parentState).dump()));
        auto parentConfig = serializedSearchConfig;
        parentConfig.simulationsPerDecision = 1;
        const auto parentDecision = silver_bridge::runSilverDecision(parentReloaded, parentConfig);
        std::vector<std::string> parentFingerprints;
        for (const auto &summary : parentDecision.rootActionSummaries)
            parentFingerprints.push_back(silver_bridge::semanticActionFingerprint(summary.action));
        std::sort(parentFingerprints.begin(), parentFingerprints.end());
        auto observedFingerprints = capturedLeaf.parentLegalActionFingerprints;
        std::sort(observedFingerprints.begin(), observedFingerprints.end());
        check(parentDecision.accepted && parentFingerprints == observedFingerprints,
              "parent round-trip must preserve its complete legal action fingerprint set");
    }

    // Entropic Brew can replace itself in a one-slot belt. Silver deduplicates
    // that stochastic outcome back to the decision node already on the path,
    // so provenance must describe the traversed parent/action rather than try
    // to infer them from the aliased leaf node.
    auto cycleWire = firstWire;
    cycleWire.potionCapacity = 1;
    cycleWire.potionCount = 1;
    cycleWire.potions.fill(static_cast<std::int16_t>(Potion::EMPTY_POTION_SLOT));
    cycleWire.potions[0] = static_cast<std::int16_t>(Potion::ENTROPIC_BREW);
    silver_bridge::SemanticAction entropicAction;
    entropicAction.type = silver_bridge::SemanticActionType::POTION;
    entropicAction.potionId = static_cast<std::int16_t>(Potion::ENTROPIC_BREW);
    entropicAction.potionSlot = 0;
    entropicAction.target = 0;
    const auto entropicFingerprint = silver_bridge::semanticActionFingerprint(entropicAction);
    bool observedCycleIdentity = false;
    auto cycleConfig = serializedSearchConfig;
    cycleConfig.simulationsPerDecision = 512;
    cycleConfig.leafObserver = [&](silver_bridge::SilverLeafObservation &o) {
        if (o.phase != silver_bridge::SilverLeafObservationPhase::START) return;
        if (o.incomingActionFingerprint == entropicFingerprint
                && silver_bridge::convertedStatesEqualForSearch(o.state, o.parentState)) {
            observedCycleIdentity = std::find(o.parentLegalActionFingerprints.begin(),
                                              o.parentLegalActionFingerprints.end(),
                                              entropicFingerprint)
                != o.parentLegalActionFingerprints.end();
        }
        o.skipRollout = true;
        o.directValue = 0.0;
    };
    (void)silver_bridge::runSilverDecision(cycleWire, cycleConfig);
    check(observedCycleIdentity,
          "self-loop rollout must retain the explicit decision parent and incoming action identity");

    auto advancedLeaf = firstWire;
    advancedLeaf.player.gold += 5;
    advancedLeaf.player.maxHp += 2;
    check(std::abs(silver_bridge::silverVictoryBaselineCorrection(firstWire, advancedLeaf) - 5.25) < 1e-12,
          "original-root victory correction must exactly reconstruct gold and max-HP baselines");

    // The bridge session must retain the exact private child selected at one
    // Silver decision and reroot into it at the next. This is an entirely
    // native/private action execution: no live BattleContext is touched.
    silver_bridge::SilverSearchConfig reuseConfig;
    reuseConfig.simulationsPerDecision = 32;
    const auto reuse = silver_bridge::probeSilverSearchSessionReuse(firstWire, reuseConfig);
    check(reuse.accepted && reuse.rerootExact == 1 && reuse.rerootFallback == 0
              && reuse.inheritedVisits > 0,
          "private Silver session must exact-reroot and retain prior subtree visits");

    const auto capFixture = silver_bridge::probeSilverReuseCapFixture(firstWire);
    check(capFixture.defaultEqualsExplicitAllocated,
          "unset/default and explicit allocated reuse-cap modes must agree");
    check(capFixture.retainedAllocationAboveCapAfterReset && capFixture.activeBelowCapAfterReset,
          "setRoot must retain allocation while resetting active pool usage");
    check(capFixture.allocatedCapBlocked
              && capFixture.allocatedDiagnostic.exactCandidateFound
              && capFixture.allocatedDiagnostic.fallbackReason
                  == silver_bridge::SilverRerootFallbackReason::ALLOCATED_CAP,
          "allocated mode must cap-block an exact candidate after retained allocation growth");
    check(capFixture.activeExactReroot && capFixture.activeInheritsVisits
              && capFixture.activeDiagnostic.fallbackReason
                  == silver_bridge::SilverRerootFallbackReason::NONE,
          "active mode must exact-reroot and inherit visits below the active cap");
    check(capFixture.activeCapBlocked
              && capFixture.activeCapDiagnostic.fallbackReason
                  == silver_bridge::SilverRerootFallbackReason::ACTIVE_CAP,
          "active mode must still cap-block when active pool usage reaches the cap");
    check(capFixture.candidateMissingUnchanged,
          "candidate-missing fallback must remain identical in both cap modes");
    check(capFixture.handOrderMandatory && capFixture.handPermutationRejected,
          "exact hand order must remain mandatory and reject a hand-permuted candidate");
    check(capFixture.noneDisablesReuse,
          "none mode must reset through the fresh-root path without candidate matching");
    check(capFixture.noneReportsDisabled,
          "none mode must report reuse_disabled rather than candidate-missing or cap-blocked");
    check(capFixture.noneFreshRootBudget,
          "none mode must execute the exact requested fresh-search simulation budget");

    // The quality probe compares existing index-free values, never private
    // Silver indices.  A root summary exposes the exact visit rank and UCB
    // child-Q statistic without changing the searcher's selection algorithm.
    silver_bridge::SilverSearchConfig qualityConfig;
    qualityConfig.simulationsPerDecision = 16;
    qualityConfig.collectDecisionDiagnostics = true;
    qualityConfig.collectRootActionSummaries = true;
    const auto qualityFresh = silver_bridge::runSilverDecision(firstWire, qualityConfig);
    const auto qualityFingerprint = silver_bridge::semanticActionFingerprint(qualityFresh.action);
    bool chosenInSummary = false;
    for (const auto &summary : qualityFresh.rootActionSummaries) {
        chosenInSummary = chosenInSummary || silver_bridge::semanticActionFingerprint(summary.action) == qualityFingerprint;
    }
    check(qualityFresh.accepted && qualityFresh.inheritedVisits == 0
              && qualityFresh.simulations == 16 && !qualityFingerprint.empty() && chosenInSummary,
          "fresh quality search must have zero inherited visits and describe its chosen semantic root action");

    // The leaf observer is the narrow, type-free seam used by live Silver
    // instrumentation.  A shadow observer must see the same leaf at START
    // and END without changing the search result; a direct observer may
    // replace only the nonterminal rollout value.
    silver_bridge::SilverSearchConfig observerConfig;
    observerConfig.simulationsPerDecision = 12;
    int observedStarts = 0;
    int observedEnds = 0;
    bool observedRolloutFields = true;
    observerConfig.leafObserver = [&](silver_bridge::SilverLeafObservation &observation) {
        if (observation.phase == silver_bridge::SilverLeafObservationPhase::START) {
            ++observedStarts;
            observation.collectResult = true;
        } else {
            ++observedEnds;
            observedRolloutFields = observedRolloutFields
                && observation.terminalOutcome != static_cast<int>(Outcome::UNDECIDED)
                && observation.rolloutActionCount >= 0
                && observation.rolloutTurnDelta >= 0
                && observation.rolloutWallMicros >= 0
                && observation.rolloutUtility == observation.rolloutUtility;
        }
    };
    auto noObserverConfig = observerConfig;
    noObserverConfig.leafObserver = {};
    const auto noObserver = silver_bridge::runSilverDecision(firstWire, noObserverConfig);
    const auto observed = silver_bridge::runSilverDecision(firstWire, observerConfig);
    check(observed.accepted && observedStarts > 0 && observedEnds == observedStarts
              && observedRolloutFields && observed.telemetry.rolloutSkippedVNet == 0
              && noObserver.accepted
              && silver_bridge::semanticActionFingerprint(noObserver.action)
                  == silver_bridge::semanticActionFingerprint(observed.action),
          "leaf observer must report every sampled rollout start and completed terminal result");

    auto directConfig = observerConfig;
    int directStarts = 0;
    directConfig.leafObserver = [&](silver_bridge::SilverLeafObservation &observation) {
        if (observation.phase == silver_bridge::SilverLeafObservationPhase::START) {
            ++directStarts;
            observation.skipRollout = true;
            observation.directValue = 17.25;
        }
    };
    const auto direct = silver_bridge::runSilverDecision(firstWire, directConfig);
    check(direct.accepted && directStarts > 0
              && direct.telemetry.rolloutCalls == 0
              && direct.telemetry.rolloutSkippedVNet > 0,
          "direct leaf observer must replace nonterminal rollouts with its supplied value");
    check(silver_bridge::silverBlendRolloutUtility(10.0, 30.0, 0.0) == 10.0
              && silver_bridge::silverBlendRolloutUtility(10.0, 30.0, 1.0) == 30.0
              && silver_bridge::silverBlendRolloutUtility(10.0, 30.0, 0.25) == 15.0,
          "leaf blend arithmetic must be the exact affine combination");
    auto blendConfig = observerConfig;
    blendConfig.collectRolloutDiagnostics = true;
    int blendStarts = 0, blendEnds = 0;
    bool blendBackpropagatedExact = true;
    blendConfig.leafObserver = [&](silver_bridge::SilverLeafObservation &observation) {
        if (observation.phase == silver_bridge::SilverLeafObservationPhase::START) {
            ++blendStarts;
            observation.blendRollout = true;
            observation.blendAlpha = 1.0;
            observation.vnetRawPrediction = 17.25;
            observation.collectResult = true;
        } else {
            ++blendEnds;
            blendBackpropagatedExact = blendBackpropagatedExact
                && observation.backpropagatedUtility == 17.25;
        }
    };
    const auto blended = silver_bridge::runSilverDecision(firstWire, blendConfig);
    check(blended.accepted && blendStarts > 0 && blendEnds == blendStarts
              && blended.telemetry.rolloutCalls > 0
              && blended.telemetry.rolloutSkippedVNet == 0
              && blendBackpropagatedExact,
          "alpha-one blending must still perform ordinary nonterminal rollouts");
    check(!silver_bridge::silverBlendInvokesModel(0.0, 0, 10, false)
              && !silver_bridge::silverBlendInvokesModel(0.25, 5, 4, false)
              && silver_bridge::silverBlendInvokesModel(0.25, 5, 5, false)
              && silver_bridge::silverBlendInvokesModel(0.25, 5, 6, false)
              && !silver_bridge::silverBlendInvokesModel(1.0, 0, 10, true),
          "leaf blend model invocation must honor alpha zero, terminal exactness, and the inclusive depth boundary");
    auto terminalWire = firstWire;
    terminalWire.outcome = static_cast<int>(Outcome::PLAYER_VICTORY);
    int terminalObserverCalls = 0;
    auto terminalConfig = observerConfig;
    terminalConfig.leafObserver = [&](silver_bridge::SilverLeafObservation &) {
        ++terminalObserverCalls;
    };
    const auto terminalDecision = silver_bridge::runSilverDecision(terminalWire, terminalConfig);
    check(terminalObserverCalls == 0 && terminalDecision.telemetry.rolloutCalls == 0,
          "terminal roots must remain exact without rollout or leaf-model observation");
    // The adaptive API must be a strict two-tier continuation of the same
    // private root.  A zero threshold is the no-escalation boundary; the
    // threshold equal to the observed share is also non-escalating because
    // the policy deliberately escalates only below the threshold.
    silver_bridge::SilverSearchConfig adaptiveConfig;
    adaptiveConfig.simulationsPerDecision = 16;
    adaptiveConfig.adaptiveEnabled = true;
    adaptiveConfig.adaptiveInitialSimulations = 16;
    adaptiveConfig.adaptiveTotalSimulations = 32;
    adaptiveConfig.adaptiveTopTwoVisitGapThreshold = 0.0;
    adaptiveConfig.collectRootActionSummaries = true;
    adaptiveConfig.collectDecisionDiagnostics = true;
    const auto noEscalation = silver_bridge::runSilverDecision(firstWire, adaptiveConfig);
    check(noEscalation.accepted && noEscalation.simulations == 16
              && !noEscalation.adaptiveEscalated
              && noEscalation.initialActionFingerprint
                  == silver_bridge::semanticActionFingerprint(noEscalation.action)
              && noEscalation.diagnostic.adaptiveEnabled
              && !noEscalation.diagnostic.adaptiveEscalated,
          "adaptive confidence path must return the exact initial-budget action without continuation");
    if (noEscalation.rootUncertainty.valid) {
        auto boundaryConfig = adaptiveConfig;
        boundaryConfig.adaptiveTopTwoVisitGapThreshold = noEscalation.rootUncertainty.topTwoVisitGapShare;
        const auto boundary = silver_bridge::runSilverDecision(firstWire, boundaryConfig);
        check(boundary.accepted && boundary.simulations == 16 && !boundary.adaptiveEscalated,
              "adaptive threshold equality must remain on the confidence side of the boundary");
    }

    auto escalationConfig = adaptiveConfig;
    escalationConfig.adaptiveTopTwoVisitGapThreshold = 1.0;
    const auto escalated = silver_bridge::runSilverDecision(firstWire, escalationConfig);
    check(escalated.accepted && escalated.adaptiveEscalated
              && escalated.simulations == 32
              && escalated.diagnostic.simulationsAdded == 32
              && escalated.diagnostic.rootVisitsAfterSearch == 32,
          "adaptive uncertainty path must continue the existing root to exactly the total budget");

    auto disabledConfig = adaptiveConfig;
    disabledConfig.adaptiveEnabled = false;
    disabledConfig.collectRootActionSummaries = false;
    disabledConfig.collectDecisionDiagnostics = false;
    const auto disabled = silver_bridge::runSilverDecision(firstWire, disabledConfig);
    auto legacyConfig = disabledConfig;
    const auto legacy = silver_bridge::runSilverDecision(firstWire, legacyConfig);
    check(disabled.accepted && legacy.accepted && disabled.simulations == 16
              && silver_bridge::semanticActionFingerprint(disabled.action)
                  == silver_bridge::semanticActionFingerprint(legacy.action),
          "disabled adaptive configuration must preserve the existing production decision");

    auto adaptiveReuseConfig = adaptiveConfig;
    adaptiveReuseConfig.adaptiveTopTwoVisitGapThreshold = 1.0;
    const auto adaptiveReuse = silver_bridge::probeSilverSearchSessionReuse(
        firstWire, adaptiveReuseConfig);
    check(adaptiveReuse.accepted && adaptiveReuse.rerootExact == 1
              && adaptiveReuse.rerootFallback == 0
              && adaptiveReuse.inheritedVisits > 0
              && adaptiveReuse.firstAdaptiveEscalated
              && adaptiveReuse.firstSimulations == 32
              && (adaptiveReuse.secondSimulations == 16
                  || adaptiveReuse.secondSimulations == 32)
              && adaptiveReuse.secondRootVisitsAfterSearch
                  == adaptiveReuse.inheritedVisits + adaptiveReuse.secondSimulations,
          "adaptive exact-reroot path must account for each decision's added simulations separately");

    silver_bridge::SemanticAction fingerprintCard = qualityFresh.action;
    fingerprintCard.type = silver_bridge::SemanticActionType::CARD;
    fingerprintCard.card.uniqueId += 1;
    silver_bridge::SemanticAction fingerprintTarget = fingerprintCard;
    fingerprintTarget.card.uniqueId -= 1;
    fingerprintTarget.target += 1;
    silver_bridge::SemanticAction fingerprintPotion;
    fingerprintPotion.type = silver_bridge::SemanticActionType::POTION;
    fingerprintPotion.potionId = static_cast<std::int16_t>(Potion::FIRE_POTION);
    fingerprintPotion.potionSlot = 0; fingerprintPotion.target = 1;
    auto fingerprintDiscard = fingerprintPotion; fingerprintDiscard.discardPotion = true;
    silver_bridge::SemanticAction fingerprintSelect;
    fingerprintSelect.type = silver_bridge::SemanticActionType::SINGLE_CARD_SELECT;
    fingerprintSelect.source = silver_bridge::CardSource::CARD_SELECT_OPTION;
    fingerprintSelect.optionCardId = static_cast<std::int16_t>(CardId::BASH);
    fingerprintSelect.cardSelectTask = static_cast<std::int16_t>(CardSelectTask::DISCOVERY);
    check(silver_bridge::semanticActionFingerprint(fingerprintCard)
                  != silver_bridge::semanticActionFingerprint(fingerprintTarget)
              && silver_bridge::semanticActionFingerprint(fingerprintPotion)
                  != silver_bridge::semanticActionFingerprint(fingerprintDiscard)
              && silver_bridge::semanticActionFingerprint(fingerprintPotion)
                  != silver_bridge::semanticActionFingerprint(fingerprintSelect),
          "semantic fingerprints must distinguish card UID/target, potion discard, and card-select semantics");

    // Cross the actual boundary once: Silver emits an index-free semantic
    // action, the ordinary live simulator executes its resolved action, and
    // the next wire is materialized with the same public battle seed. This
    // catches an accidental per-decision root seed, which would make Silver
    // equalForSearch reject every live successor before it reaches reroot.
    auto boundaryKnowledge = firstKnowledge;
    auto boundaryLive = first;
    auto boundarySession = silver_bridge::makeSilverSearchSession();
    const auto firstBoundaryDecision = silver_bridge::runSilverDecision(*boundarySession, firstWire, reuseConfig);
    const auto activeFingerprintBeforeShadows = silver_bridge::semanticActionFingerprint(firstBoundaryDecision.action);
    silver_bridge::SilverSearchConfig tinyShadow = reuseConfig;
    tinyShadow.collectDecisionDiagnostics = true;
    tinyShadow.simulationsPerDecision = 4;
    const auto tinyFresh = silver_bridge::runSilverDecision(firstWire, tinyShadow);
    tinyShadow.simulationsPerDecision = 6;
    const auto tinyRef25 = silver_bridge::runSilverDecision(firstWire, tinyShadow);
    tinyShadow.simulationsPerDecision = 8;
    tinyShadow.collectRootActionSummaries = true;
    const auto tinyRef50 = silver_bridge::runSilverDecision(firstWire, tinyShadow);
    const auto firstBoundaryAction = search::resolveSilverSemanticAction(
        boundaryLive, firstBoundaryDecision.action);
    check(firstBoundaryDecision.accepted
              && firstBoundaryDecision.action.type == silver_bridge::SemanticActionType::CARD
              && firstBoundaryAction.ok,
          "first real-boundary Silver decision must be a resolvable deterministic card action");
    check(tinyFresh.accepted && tinyRef25.accepted && tinyRef50.accepted
              && tinyFresh.inheritedVisits == 0 && tinyRef25.inheritedVisits == 0 && tinyRef50.inheritedVisits == 0
              && tinyFresh.simulations == 4 && tinyRef25.simulations == 6 && tinyRef50.simulations == 8
              && !tinyRef50.rootActionSummaries.empty()
              && activeFingerprintBeforeShadows
                  == silver_bridge::semanticActionFingerprint(firstBoundaryDecision.action),
          "fresh shadow searches must use requested budgets, retain no visits, and leave the ACTIVE result value unchanged");
    if (firstBoundaryDecision.accepted && firstBoundaryAction.ok) {
        search::ScumSearchAgent2 executor;
        executor.takeAction(boundaryLive, firstBoundaryAction.action);
        const auto secondWire = convert(boundaryLive, gc, boundaryKnowledge);
        const auto secondBoundaryDecision = silver_bridge::runSilverDecision(
            *boundarySession, secondWire, reuseConfig);
        if (!(secondBoundaryDecision.accepted && secondBoundaryDecision.rerootExact == 1
                  && secondBoundaryDecision.rerootFallback == 0
                  && secondBoundaryDecision.inheritedVisits > 0)) {
            std::cerr << "  live-boundary reroot diagnostic: accepted=" << secondBoundaryDecision.accepted
                      << " exact=" << secondBoundaryDecision.rerootExact
                      << " fallback=" << secondBoundaryDecision.rerootFallback
                      << " inherited=" << secondBoundaryDecision.inheritedVisits
                      << " first_semantic=" << static_cast<int>(firstBoundaryDecision.action.type)
                      << " first_live_bits=" << firstBoundaryAction.action.bits
                      << " private_miss=" << secondBoundaryDecision.rerootMissDiagnostic << '\n';
        }
        check(secondBoundaryDecision.accepted && secondBoundaryDecision.rerootExact == 1
                  && secondBoundaryDecision.rerootFallback == 0
                  && secondBoundaryDecision.inheritedVisits > 0,
              "live->wire successor must exact-reroot with inherited visits under a stable battle seed");
    }

    BattleContext alteredRng = first;
    alteredRng.aiRng = Random(1); alteredRng.cardRandomRng = Random(2); alteredRng.miscRng = Random(3);
    alteredRng.monsterHpRng = Random(4); alteredRng.potionRng = Random(5); alteredRng.shuffleRng = Random(6);
    search::CombatKnowledgeState alteredRngKnowledge;
    alteredRngKnowledge.initializeFromLiveBattle(alteredRng);
    check(silver_bridge::convertedStatesEqualForSearch(firstWire, convert(alteredRng, gc, alteredRngKnowledge)),
          "all six live RNG streams must be absent from the materialized Silver root");

    // Explicit known stacks are position-significant after full materialization.
    auto topKnowledge = firstKnowledge;
    const auto topA = first.cards.drawPile[0];
    const auto topB = first.cards.drawPile[1];
    topKnowledge.observeCombatKnowledgeEvent({search::CombatKnowledgeEventType::KNOWN_TOP_PLACED, topA, true});
    topKnowledge.observeCombatKnowledgeEvent({search::CombatKnowledgeEventType::KNOWN_TOP_PLACED, topB, true});
    BattleContext topLive = first;
    topLive.cards.drawPile = {first.cards.drawPile[2], topA, topB};
    const auto topDigest = silver_bridge::inspectConvertedBattleState(convert(topLive, gc, topKnowledge));
    check(topDigest.accepted && topDigest.knownTop == 2 && topDigest.knownBottom == 0,
          "known top stack must survive private Silver materialization");
    auto reversedTop = topKnowledge;
    std::swap(reversedTop.knownTop[0], reversedTop.knownTop[1]);
    check(!silver_bridge::convertedStatesEqualForSearch(convert(topLive, gc, topKnowledge), convert(topLive, gc, reversedTop)),
          "known top order must remain search-significant");

    auto bottomKnowledge = firstKnowledge;
    bottomKnowledge.observeCombatKnowledgeEvent({search::CombatKnowledgeEventType::KNOWN_BOTTOM_PLACED, topA, true});
    bottomKnowledge.observeCombatKnowledgeEvent({search::CombatKnowledgeEventType::KNOWN_BOTTOM_PLACED, topB, true});
    // This fixture constructs the post-placement pile atomically rather than
    // applying live moves, so retain the actual final size for its observer
    // invariant.
    bottomKnowledge.observedDrawPileSize = 3;
    BattleContext bottomLive = first;
    bottomLive.cards.drawPile = {topB, topA, first.cards.drawPile[2]};
    const auto bottomDigest = silver_bridge::inspectConvertedBattleState(convert(bottomLive, gc, bottomKnowledge));
    check(bottomDigest.accepted && bottomDigest.knownBottom == 2,
          "known bottom stack must survive private Silver materialization");

    auto stale = firstKnowledge;
    stale.knownTop.push_back(card(CardId::INFLAME, 999));
    const auto staleWire = convert(first, gc, stale);
    check(!staleWire.valid && !silver_bridge::inspectConvertedBattleState(staleWire).accepted,
          "stale positional knowledge must fail closed rather than inspect hidden pile positions");

    GameContext eyeGc(CharacterClass::IRONCLAD, 0x5152u, 0);
    eyeGc.obtainRelic(RelicId::FROZEN_EYE);
    BattleContext eyeA, eyeB;
    eyeA.init(eyeGc, MonsterEncounter::CULTIST);
    installPile(eyeA); eyeB = eyeA;
    std::swap(eyeB.cards.drawPile[0], eyeB.cards.drawPile[2]);
    search::CombatKnowledgeState eyeAKnowledge, eyeBKnowledge;
    eyeAKnowledge.initializeFromLiveBattle(eyeA); eyeBKnowledge.initializeFromLiveBattle(eyeB);
    check(!silver_bridge::convertedStatesEqualForSearch(convert(eyeA, eyeGc, eyeAKnowledge), convert(eyeB, eyeGc, eyeBKnowledge)),
          "Frozen Eye must preserve legitimately visible concrete order in materialized root");

    GameContext domeGc(CharacterClass::IRONCLAD, 0x5153u, 0);
    domeGc.obtainRelic(RelicId::RUNIC_DOME);
    BattleContext dome;
    dome.init(domeGc, MonsterEncounter::CULTIST);
    search::CombatKnowledgeState domeKnowledge;
    domeKnowledge.configureHiddenMonsterIntents(true);
    domeKnowledge.initializeFromLiveBattle(dome);
    for (int i = 0; i < dome.monsters.monsterCount; ++i) {
        search::HiddenIntentRollInputs inputs;
        inputs.curHp = static_cast<std::int16_t>(dome.monsters.arr[i].curHp);
        inputs.maxHp = static_cast<std::int16_t>(dome.monsters.arr[i].maxHp);
        inputs.monsterTurnNumber = static_cast<std::int16_t>(dome.getMonsterTurnNumber());
        search::CombatKnowledgeEvent event {search::CombatKnowledgeEventType::HIDDEN_MONSTER_INTENT_ROLL_STARTED};
        event.monsterIdx = i;
        event.hiddenIntentInputs = inputs;
        // This legacy bridge-only redaction check supplies an explicitly
        // public pre-roll state; real lifecycle coverage is in the dedicated
        // runic_dome_lifecycle_test executable.
        event.publicMoveHistory = {static_cast<std::int16_t>(MonsterMoveId::INVALID),
                                   static_cast<std::int16_t>(MonsterMoveId::INVALID)};
        event.publicMonsterMiscInfo = dome.monsters.arr[i].miscInfo;
        event.hasPublicMonsterState = true;
        domeKnowledge.observeCombatKnowledgeEvent(event);
    }
    BattleContext domeDifferentIntent = dome;
    domeDifferentIntent.monsters.arr[0].moveHistory[0] = MonsterMoveId::CULTIST_INCANTATION;
    const auto domeWire = convert(dome, domeGc, domeKnowledge);
    const auto domeChangedWire = convert(domeDifferentIntent, domeGc, domeKnowledge);
    const auto domeDigest = silver_bridge::inspectConvertedBattleState(domeWire);
    check(domeDigest.accepted && domeDigest.pendingIntentRolls > 0,
          "Runic Dome root must carry external pending-intent public inputs");
    check(silver_bridge::convertedStatesEqualForSearch(domeWire, domeChangedWire),
          "Runic Dome materialized hidden live moveHistory must not leak into Silver root");

    // The sequential UI protocol is entirely private.  The bridge receives a
    // wire value, never the live BattleContext, and returns only its final
    // confirmation subset.
    BattleContext transactionLive = first;
    // A status-heavy hand makes at least one discard attractive. This must
    // exercise the actual select -> exact reroot -> search -> confirm path;
    // immediate empty confirmation is not evidence of multi-step parity.
    transactionLive.cards.cardsInHand = 5;
    for (int i = 0; i < transactionLive.cards.cardsInHand; ++i) {
        transactionLive.cards.hand[i] = card(CardId::REGRET, static_cast<std::int16_t>(81 + i));
    }
    transactionLive.inputState = InputState::CARD_SELECT;
    transactionLive.cardSelectInfo.cardSelectTask = CardSelectTask::GAMBLE;
    transactionLive.cardSelectInfo.canPickAnyNumber = true;
    search::CombatKnowledgeState transactionKnowledge;
    transactionKnowledge.initializeFromLiveBattle(transactionLive);
    const BattleContext transactionBefore = transactionLive;
    silver_bridge::SilverSearchConfig transactionConfig;
    transactionConfig.simulationsPerDecision = 16;
    transactionConfig.collectDecisionDiagnostics = true;
    const auto ordinaryTransactionDecision = silver_bridge::runSilverDecision(
        convert(transactionLive, gc, transactionKnowledge), transactionConfig);
    check(!ordinaryTransactionDecision.accepted
              && ordinaryTransactionDecision.simulations == 0
              && ordinaryTransactionDecision.failureReason == "transactional_selection_required",
          "ordinary decision API must explain a zero-simulation transactional-state rejection");
    auto unavailableSession = silver_bridge::makeSilverSearchSession();
    const auto unavailableContinuation = silver_bridge::continueSilverDecision(
        *unavailableSession, 1, transactionConfig);
    check(!unavailableContinuation.accepted
              && unavailableContinuation.failureReason == "search_session_unavailable",
          "continuation rejection must retain a non-empty failure reason");
    const auto transaction = silver_bridge::runSequentialSelectionTransaction(
        convert(transactionLive, gc, transactionKnowledge), transactionConfig);
    if (!transaction.accepted) {
        std::cerr << "  GAMBLE transaction diagnostic: " << transaction.failure
                  << " decisions=" << transaction.searchDecisions
                  << " sims=" << transaction.totalSimulations << '\n';
    }
    check(transaction.accepted && transaction.finalConfirmation && transaction.privateStateOnly
          && transaction.searchDecisions >= 2 && !transaction.intermediateSelections.empty()
          && transaction.rerootExact >= 1 && transaction.rerootFallback == 0
          && transaction.totalSimulations >= transaction.searchDecisions,
          "GAMBLE transaction must select, exact-reroot with inherited state, and then confirm");
    check(transaction.finalAction.type == silver_bridge::SemanticActionType::MULTI_CARD_SELECT
          && transaction.intermediateSelections.size() == transaction.selectedBitsAfterEachIntermediate.size()
          && !transaction.selectedBitsAfterEachIntermediate.empty()
          && transaction.selectedBitsAfterEachIntermediate.front() != 0,
          "GAMBLE transaction must retain private selectedBits and return only a final semantic subset");
    check(transaction.searchDiagnostics.size() == static_cast<std::size_t>(transaction.searchDecisions),
          "GAMBLE diagnostics must contain every private search subdecision");
    check(transaction.searchDiagnostics.size() >= 2
              && transaction.searchDiagnostics[1].exactReroot
              && transaction.searchDiagnostics[1].inheritedVisits > 0,
          "GAMBLE second subdecision must prove exact reroot with inherited visits");
    check(transactionLive.inputState == transactionBefore.inputState
          && transactionLive.cardSelectInfo.cardSelectTask == transactionBefore.cardSelectInfo.cardSelectTask
          && transactionLive.cards.cardsInHand == transactionBefore.cards.cardsInHand
          && transactionLive.cards.hand[0].uniqueId == transactionBefore.cards.hand[0].uniqueId
          && transactionLive.cards.hand[4].uniqueId == transactionBefore.cards.hand[4].uniqueId
          && transactionLive.aiRng.counter == transactionBefore.aiRng.counter
          && transactionLive.cardRandomRng.counter == transactionBefore.cardRandomRng.counter
          && transactionLive.shuffleRng.counter == transactionBefore.shuffleRng.counter,
          "private sequential selection transaction must not mutate live state or live RNG");

    auto adaptiveTransactionConfig = transactionConfig;
    adaptiveTransactionConfig.adaptiveEnabled = true;
    adaptiveTransactionConfig.adaptiveInitialSimulations = 16;
    adaptiveTransactionConfig.adaptiveTotalSimulations = 32;
    adaptiveTransactionConfig.adaptiveTopTwoVisitGapThreshold = 1.0;
    adaptiveTransactionConfig.collectRootActionSummaries = true;
    const auto adaptiveTransaction = silver_bridge::runSequentialSelectionTransaction(
        convert(transactionLive, gc, transactionKnowledge), adaptiveTransactionConfig);
    bool adaptiveTransactionEscalated = false;
    bool adaptiveTransactionBudgetsExact = true;
    std::int64_t adaptiveTransactionDiagnosticSimulations = 0;
    for (const auto &diagnostic : adaptiveTransaction.searchDiagnostics) {
        adaptiveTransactionEscalated = adaptiveTransactionEscalated || diagnostic.adaptiveEscalated;
        adaptiveTransactionBudgetsExact = adaptiveTransactionBudgetsExact
            && (diagnostic.simulationsAdded == 16 || diagnostic.simulationsAdded == 32)
            && diagnostic.rootVisitsAfterSearch
                == diagnostic.inheritedVisits + diagnostic.simulationsAdded;
        adaptiveTransactionDiagnosticSimulations += diagnostic.simulationsAdded;
    }
    check(adaptiveTransaction.accepted && adaptiveTransaction.finalConfirmation
              && adaptiveTransaction.searchDecisions >= 2
              && adaptiveTransactionEscalated
              && adaptiveTransactionBudgetsExact
              && adaptiveTransaction.totalSimulations == adaptiveTransactionDiagnosticSimulations,
          "adaptive sequential selection must preserve confirmation and exact 1k-to-3.7k subdecision budgets");

    auto noneTransactionConfig = transactionConfig;
    noneTransactionConfig.reuseCapMode = silver_bridge::SilverReuseCapMode::NONE;
    const auto noneTransaction = silver_bridge::runSequentialSelectionTransaction(
        convert(transactionLive, gc, transactionKnowledge), noneTransactionConfig);
    const bool nonePrivateFresh = noneTransaction.accepted && noneTransaction.finalConfirmation
        && noneTransaction.totalSimulations
            == noneTransaction.searchDecisions * noneTransactionConfig.simulationsPerDecision
        && std::all_of(noneTransaction.searchDiagnostics.begin(), noneTransaction.searchDiagnostics.end(),
                       [](const auto &diagnostic) {
                           return diagnostic.inheritedVisits == 0
                               && !diagnostic.exactReroot
                               && diagnostic.fallback
                               && diagnostic.fallbackReason
                                   == silver_bridge::SilverRerootFallbackReason::REUSE_DISABLED;
                       });
    check(nonePrivateFresh,
          "NONE sequential private selections must fresh-reset every subdecision at full budget");

    BattleContext exhaustLive = first;
    exhaustLive.cards.cardsInHand = 2;
    exhaustLive.cards.hand[0] = card(CardId::STRIKE_RED, 91);
    exhaustLive.cards.hand[1] = card(CardId::DEFEND_RED, 92);
    exhaustLive.inputState = InputState::CARD_SELECT;
    exhaustLive.cardSelectInfo.cardSelectTask = CardSelectTask::EXHAUST_MANY;
    exhaustLive.cardSelectInfo.canPickAnyNumber = false;
    exhaustLive.cardSelectInfo.canPickZero = true;
    exhaustLive.cardSelectInfo.pickCount = 1;
    search::CombatKnowledgeState exhaustKnowledge;
    exhaustKnowledge.initializeFromLiveBattle(exhaustLive);
    const BattleContext exhaustBefore = exhaustLive;
    const auto exhaustTransaction = silver_bridge::runSequentialSelectionTransaction(
        convert(exhaustLive, gc, exhaustKnowledge), transactionConfig);
    check(exhaustTransaction.accepted && exhaustTransaction.finalConfirmation
          && exhaustTransaction.finalAction.type == silver_bridge::SemanticActionType::MULTI_CARD_SELECT
          && exhaustTransaction.intermediateSelections.size()
              == exhaustTransaction.selectedBitsAfterEachIntermediate.size(),
          "EXHAUST_MANY transaction must retain the upstream private selection protocol");
    check(exhaustTransaction.searchDiagnostics.size()
              == static_cast<std::size_t>(exhaustTransaction.searchDecisions),
          "EXHAUST_MANY diagnostics must contain every private search subdecision");
    check(exhaustLive.cards.cardsInHand == exhaustBefore.cards.cardsInHand
          && exhaustLive.cards.hand[0].uniqueId == exhaustBefore.cards.hand[0].uniqueId
          && exhaustLive.cards.hand[1].uniqueId == exhaustBefore.cards.hand[1].uniqueId
          && exhaustLive.aiRng.counter == exhaustBefore.aiRng.counter
          && exhaustLive.shuffleRng.counter == exhaustBefore.shuffleRng.counter,
          "EXHAUST_MANY private transaction must leave the live atomic selection untouched");

    if (failures != 0) {
        std::cerr << "silver_bridge_boundary FAIL (" << failures << ")\n";
        return 1;
    }
    std::cout << "silver_bridge_boundary PASS\n";
    return 0;
}
