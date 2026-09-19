// Focused live->wire->isolated-Silver boundary tests.  This executable has a
// separate link closure so ordinary unit-test never links the full vendor model.
#include <algorithm>
#include <cmath>
#include <iostream>
#include <set>
#include <fstream>
#include "sim/search/SilverRootMechanism.h"

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

int main(int argc, char **argv) {
    int failures = 0;
    const auto check = [&failures](bool ok, const char *message) {
        if (!ok) { std::cerr << "  " << message << '\n'; ++failures; }
    };
    const auto sameRootUncertainty = [](const silver_bridge::SilverRootUncertainty &lhs,
                                        const silver_bridge::SilverRootUncertainty &rhs) {
        return lhs.valid == rhs.valid
            && lhs.rootVisits == rhs.rootVisits
            && lhs.topVisits == rhs.topVisits
            && lhs.secondVisits == rhs.secondVisits
            && lhs.legalActions == rhs.legalActions
            && lhs.topVisitShare == rhs.topVisitShare
            && lhs.topTwoVisitGapShare == rhs.topTwoVisitGapShare
            && lhs.topQGap == rhs.topQGap
            && lhs.visitEntropy == rhs.visitEntropy
            && lhs.topQGapValid == rhs.topQGapValid;
    };
    const auto sameRootActionSummaries = [](const auto &lhs, const auto &rhs) {
        if (lhs.size() != rhs.size()) return false;
        for (std::size_t i = 0; i < lhs.size(); ++i) {
            if (silver_bridge::semanticActionFingerprint(lhs[i].action)
                    != silver_bridge::semanticActionFingerprint(rhs[i].action)
                    || lhs[i].edgeVisits != rhs[i].edgeVisits
                    || lhs[i].childSimulations != rhs[i].childSimulations
                    || lhs[i].childEvaluationSum != rhs[i].childEvaluationSum
                    || lhs[i].childVictoryCount != rhs[i].childVictoryCount
                    || lhs[i].selectionQValid != rhs[i].selectionQValid
                    || lhs[i].selectionQ != rhs[i].selectionQ) return false;
        }
        return true;
    };

    GameContext gc(CharacterClass::IRONCLAD, 0x5151u, 0);
    BattleContext first;
    first.init(gc, MonsterEncounter::CULTIST);
    installPile(first);
    if (argc == 2 && std::string(argv[1]) == "--capture-neutrality-fixture") {
        gc.info.encounter = MonsterEncounter::CULTIST;
        search::ScumSearchAgent2 agent;
        agent.simulationCountBase = 8;
        agent.bossSimulationMultiplier = 1;
        search::installSilverLiveBackend();
        search::setSilverLiveActionTraceForTest(true);
        BattleContext live;
        search::g_externalCombatBackend(agent, gc, live);
        search::uninstallSilverLiveBackend();
        nlohmann::json result = {{"outcome", static_cast<int>(live.outcome)},
            {"hp", live.player.curHp}, {"turn", live.turn},
            {"actions", search::g_silverLiveDiagnostics.actionFingerprints},
            {"simulations", search::g_silverLiveDiagnostics.simulations},
            {"ai_counter", live.aiRng.counter}, {"shuffle_counter", live.shuffleRng.counter}};
        std::cout << result.dump() << '\n';
        return 0;
    }

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

    // Gambler's Brew enters GAMBLE, which has no legal selection when the
    // live hand is empty. Silver must not offer a semantic potion action that
    // the live legality boundary will reject.
    BattleContext emptyGambleHand = first;
    emptyGambleHand.cards.cardsInHand = 0;
    emptyGambleHand.potions[1] = Potion::GAMBLERS_BREW;
    emptyGambleHand.potionCount = 1;
    search::CombatKnowledgeState emptyGambleKnowledge;
    emptyGambleKnowledge.initializeFromLiveBattle(emptyGambleHand);
    const auto emptyGambleWire = convert(emptyGambleHand, gc, emptyGambleKnowledge);
    const auto emptyGambleActions = silver_bridge::enumerateSilverLegalActions(emptyGambleWire);
    const bool silverOffersEmptyHandGamble = std::any_of(
        emptyGambleActions.begin(), emptyGambleActions.end(), [](const auto &action) {
            return action.type == silver_bridge::SemanticActionType::POTION
                && action.potionId == static_cast<std::int16_t>(Potion::GAMBLERS_BREW);
        });
    check(!silverOffersEmptyHandGamble,
          "Silver must not enumerate Gambler's Brew when the live hand is empty");

    // Duplicate potion slots are reduced only inside Silver. The semantic
    // boundary remains slot-exact: Silver must return the first representative
    // and live lowering must resolve that exact identity without searching for
    // an equivalent slot.
    BattleContext duplicatePotionLive = first;
    duplicatePotionLive.potions.fill(Potion::EMPTY_POTION_SLOT);
    duplicatePotionLive.potions[0] = Potion::STRENGTH_POTION;
    duplicatePotionLive.potions[2] = Potion::STRENGTH_POTION;
    duplicatePotionLive.potionCapacity = 3;
    duplicatePotionLive.potionCount = 2;
    search::CombatKnowledgeState duplicatePotionKnowledge;
    duplicatePotionKnowledge.initializeFromLiveBattle(duplicatePotionLive);
    const auto duplicatePotionWire = convert(
        duplicatePotionLive, gc, duplicatePotionKnowledge);
    const auto duplicatePotionActions = silver_bridge::enumerateSilverLegalActions(
        duplicatePotionWire);
    std::vector<silver_bridge::SemanticAction> strengthActions;
    for (const auto &action : duplicatePotionActions) {
        if (action.type == silver_bridge::SemanticActionType::POTION
                && action.potionId == static_cast<std::int16_t>(Potion::STRENGTH_POTION)) {
            strengthActions.push_back(action);
        }
    }
    check(strengthActions.size() == 1 && strengthActions.front().potionSlot == 0,
          "Silver semantic enumeration must retain only the first duplicate potion slot");
    if (strengthActions.size() == 1) {
        const auto lowered = search::resolveSilverSemanticAction(
            duplicatePotionLive, strengthActions.front());
        check(lowered.ok
                  && lowered.action == search::Action(search::ActionType::POTION, 0),
              "representative duplicate potion must lower against the exact live slot");
        if (lowered.ok) {
            auto executedDuplicatePotion = duplicatePotionLive;
            search::ScumSearchAgent2 executor;
            executor.takeAction(executedDuplicatePotion, lowered.action);
            check(executedDuplicatePotion.potionCount == 1
                      && executedDuplicatePotion.potions[0] == Potion::EMPTY_POTION_SLOT
                      && executedDuplicatePotion.potions[2] == Potion::STRENGTH_POTION,
                  "lowered representative potion must remain live-valid when executed");
        }
    }

    BattleContext permuted = first;
    std::swap(permuted.cards.drawPile[0], permuted.cards.drawPile[2]);
    search::CombatKnowledgeState firstKnowledge, permutedKnowledge;
    firstKnowledge.initializeFromLiveBattle(first);
    permutedKnowledge.initializeFromLiveBattle(permuted);
    const auto firstWire = convert(first, gc, firstKnowledge);

    silver_bridge::SilverSearchConfig completeReplayConfig;
    completeReplayConfig.simulationsPerDecision = 8;
    completeReplayConfig.reuseCap = silver_bridge::kSilverProductionReuseCap;
    const auto replayA = silver_bridge::runSilverCombatReplay(firstWire, completeReplayConfig);
    const auto replayB = silver_bridge::runSilverCombatReplay(firstWire, completeReplayConfig);
    check(replayA.accepted && replayA.decisions > 1,
          "isolated complete-fight replay must reach terminal after multiple decisions");
    check(replayA.accepted
              && replayA.rerootExact + replayA.rerootFallback == replayA.decisions - 1,
          "complete-fight replay must reroot only between decisions");
    check(replayA.accepted && replayB.accepted
              && replayA.won == replayB.won
              && replayA.terminalHp == replayB.terminalHp
              && replayA.terminalTurn == replayB.terminalTurn
              && replayA.decisions == replayB.decisions
              && replayA.simulations == replayB.simulations
              && replayA.actionTraceHash == replayB.actionTraceHash,
          "complete-fight replay must be deterministic for the same snapshot and budget");

    // Start from PLAYER_NORMAL with the only useful card action being a
    // deterministic Gambler's Brew opportunity. This exercises the complete
    // replay loop across the private sequential-selection protocol, including
    // post-confirm draw/RNG advancement, rather than only the helper API that
    // starts on CARD_SELECT.
    BattleContext gambleReplayLive = first;
    gambleReplayLive.cards.cardsInHand = 5;
    for (int i = 0; i < gambleReplayLive.cards.cardsInHand; ++i)
        gambleReplayLive.cards.hand[i] = card(CardId::REGRET, static_cast<std::int16_t>(181 + i));
    gambleReplayLive.potions[0] = Potion::GAMBLERS_BREW;
    gambleReplayLive.potionCount = 1;
    gambleReplayLive.inputState = InputState::PLAYER_NORMAL;
    search::CombatKnowledgeState gambleReplayKnowledge;
    gambleReplayKnowledge.initializeFromLiveBattle(gambleReplayLive);
    auto gambleReplayConfig = completeReplayConfig;
    gambleReplayConfig.simulationsPerDecision = 16;
    const auto gambleReplayWire = convert(gambleReplayLive, gc, gambleReplayKnowledge);
    const auto gambleReplayA = silver_bridge::runSilverCombatReplay(
        gambleReplayWire, gambleReplayConfig);
    const auto gambleReplayB = silver_bridge::runSilverCombatReplay(
        gambleReplayWire, gambleReplayConfig);
    if (!(gambleReplayA.accepted && gambleReplayA.traversedGamble
              && gambleReplayA.singleCardSelectActions > 0
              && gambleReplayA.multiCardSelectActions > 0)) {
        std::cerr << "  complete GAMBLE replay diagnostic: accepted=" << gambleReplayA.accepted
                  << " failure=" << gambleReplayA.failureReason
                  << " decisions=" << gambleReplayA.decisions
                  << " single=" << gambleReplayA.singleCardSelectActions
                  << " multi=" << gambleReplayA.multiCardSelectActions
                  << " gamble=" << gambleReplayA.traversedGamble
                  << " hp=" << gambleReplayA.terminalHp
                  << " turn=" << gambleReplayA.terminalTurn << '\n';
    }
    check(gambleReplayA.accepted && gambleReplayA.traversedGamble
              && gambleReplayA.singleCardSelectActions > 0
              && gambleReplayA.multiCardSelectActions > 0,
          "complete replay must traverse PLAYER_NORMAL GAMBLE selection and confirmation");
    check(gambleReplayA.accepted
              && gambleReplayA.rerootExact + gambleReplayA.rerootFallback
                  == gambleReplayA.decisions - 1,
          "GAMBLE complete replay must not reroot after terminal confirmation");
    check(gambleReplayA.accepted && gambleReplayB.accepted
              && gambleReplayA.won == gambleReplayB.won
              && gambleReplayA.terminalHp == gambleReplayB.terminalHp
              && gambleReplayA.terminalTurn == gambleReplayB.terminalTurn
              && gambleReplayA.decisions == gambleReplayB.decisions
              && gambleReplayA.simulations == gambleReplayB.simulations
              && gambleReplayA.rerootExact == gambleReplayB.rerootExact
              && gambleReplayA.rerootFallback == gambleReplayB.rerootFallback
              && gambleReplayA.actionTraceHash == gambleReplayB.actionTraceHash,
          "GAMBLE complete replay must repeat with identical terminal and reroot results");
    const auto permutedWire = convert(permuted, gc, permutedKnowledge);
    check(silver_bridge::inspectConvertedBattleState(firstWire).accepted,
          "ordinary wire must materialize a private Silver root");
    check(silver_bridge::convertedStatesEqualForSearch(firstWire, permutedWire),
          "hidden live draw-order permutations must materialize equivalent Silver roots");

    const auto serializedWire = silver_bridge::battleStateWireEnvelope(firstWire).dump();
    const auto reloadedWire = silver_bridge::battleStateWireFromEnvelope(
        nlohmann::json::parse(serializedWire));
    const auto snapshot = silver_bridge::rootMechanismSnapshot(firstWire, gc.seed, "1/1/cultist", 0,
        "be5b6ac2c9914b0a56244f2522b7573f81360067");
    check(!snapshot.is_null(), "capture fixture must be eligible");
    const auto capturedWire = silver_bridge::validateRootMechanismSnapshot(snapshot);
    check(silver_bridge::battleStateWireEnvelope(capturedWire).dump() == serializedWire,
          "capture must round-trip every visible wire field");
    if (argc == 3 && std::string(argv[1]) == "--root-mechanism-fixture") {
        std::ofstream output(argv[2]);
        output << snapshot.dump() << '\n';
        return failures || !output ? 1 : 0;
    }
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
    auto cardSelectWire = reloadedWire;
    cardSelectWire.inputState = static_cast<int>(InputState::CARD_SELECT);
    cardSelectWire.cardSelect.task = static_cast<std::int16_t>(CardSelectTask::WARCRY);
    cardSelectWire.cardSelect.pickCount = 1;
    const auto cardSelectActions = silver_bridge::enumerateSilverLegalActions(cardSelectWire);
    const auto cardSelectRows = search::silverLiveParentPolicyFeatures(cardSelectWire);
    check(!cardSelectRows.empty() && cardSelectRows.size() == cardSelectActions.size(),
          "stored card-select wire must lower every Silver action to a canonical policy row");
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
    auto replayConfig = serializedSearchConfig;
    replayConfig.simulationsPerDecision = 32;
    const auto ordinaryReplay = silver_bridge::runSilverDecision(reloadedWire, replayConfig);
    const auto nativeOrder = snapshot.at("native_order").get<std::vector<std::string>>();
    auto reversedOrder = nativeOrder;
    std::reverse(reversedOrder.begin(), reversedOrder.end());
    const auto baselineReplay = silver_bridge::replaySilverRoot(reloadedWire, nativeOrder, nativeOrder, {}, false);
    check(baselineReplay.accepted && sameRootActionSummaries(ordinaryReplay.rootActionSummaries,
              baselineReplay.rootActionSummaries), "baseline replay exact ordinary root statistics");
    for (const bool puct : {false, true}) for (const bool reorder : {false, true}) {
        const auto &order = reorder ? reversedOrder : nativeOrder;
        const auto priors = puct ? std::vector<double>(order.size(), 1.0 / order.size()) : std::vector<double>{};
        const auto result = silver_bridge::replaySilverRoot(reloadedWire, nativeOrder, order, priors, puct);
        check(result.accepted && result.simulations == 32 && result.inheritedVisits == 0,
              "four mechanisms run exact fresh budget");
        std::vector<std::string> actual;
        for (const auto &summary : result.rootActionSummaries)
            actual.push_back(silver_bridge::semanticActionFingerprint(summary.action));
        check(actual == order, "replay preserves requested semantic order and full action set");
    }
    for (const auto bad : {std::vector<double>{}, std::vector<double>(nativeOrder.size(), 0.0),
             std::vector<double>(nativeOrder.size(), -1.0),
             std::vector<double>(nativeOrder.size(), std::numeric_limits<double>::quiet_NaN())})
        check(!silver_bridge::replaySilverRoot(reloadedWire, nativeOrder, nativeOrder, bad, true).accepted,
              "invalid priors fail closed");
    auto wrongOrder = nativeOrder;
    wrongOrder[0] = "not-an-action";
    check(!silver_bridge::replaySilverRoot(reloadedWire, nativeOrder, wrongOrder, {}, false).accepted,
          "unknown replay action fails closed");
    check(inMemorySearch.accepted && reloadedSearch.accepted
          && silver_bridge::semanticActionFingerprint(inMemorySearch.action)
              == silver_bridge::semanticActionFingerprint(reloadedSearch.action)
          && inMemorySearch.rootActionSummaries.size() == reloadedSearch.rootActionSummaries.size(),
          "serialized/reloaded leaf must reproduce an identical deterministic small-budget search");

    // The paired-budget probe must expose the same 500-step prefix as an
    // independent fresh 500-step search, while its final result comes from
    // the unchanged same-session continuation.
    auto prefixConfig = serializedSearchConfig;
    prefixConfig.simulationsPerDecision = 500;
    const auto standalonePrefix = silver_bridge::runSilverDecision(firstWire, prefixConfig);
    auto pairedConfig = serializedSearchConfig;
    pairedConfig.simulationsPerDecision = 1000;
    pairedConfig.collectBudgetDiagnostics = true;
    pairedConfig.budgetDiagnosticCheckpoint = 500;
    auto pairedSession = silver_bridge::makeSilverSearchSession();
    const auto paired = silver_bridge::runSilverDecisionWithCheckpoint(
        *pairedSession, firstWire, pairedConfig);
    check(standalonePrefix.accepted && paired.accepted && paired.budgetDiagnostic.valid
          && paired.simulations == 1000
          && silver_bridge::semanticActionFingerprint(standalonePrefix.action)
              == paired.budgetDiagnostic.checkpointActionFingerprint
          && paired.budgetDiagnostic.checkpointSimulations == 500
          && paired.budgetDiagnostic.totalSimulations == 1000
          && paired.budgetDiagnostic.checkpointRootUncertainty.valid
          && paired.budgetDiagnostic.checkpointRootUncertainty.legalActions > 0,
          "paired budget probe must preserve the exact standalone 500-step prefix and sensible root statistics");

    // The full split search must match an uninterrupted search at the final
    // root, not only at the checkpoint action. This is a fresh ordinary root
    // with no retained predecessor.
    auto uninterruptedConfig = serializedSearchConfig;
    uninterruptedConfig.simulationsPerDecision = 1000;
    uninterruptedConfig.collectRootActionSummaries = true;
    uninterruptedConfig.collectDecisionDiagnostics = true;
    const auto uninterrupted = silver_bridge::runSilverDecision(firstWire, uninterruptedConfig);
    const auto splitFinal = paired;
    check(uninterrupted.accepted && splitFinal.accepted
              && silver_bridge::semanticActionFingerprint(uninterrupted.action)
                  == silver_bridge::semanticActionFingerprint(splitFinal.action)
              && sameRootActionSummaries(uninterrupted.rootActionSummaries,
                                          splitFinal.rootActionSummaries)
              && sameRootUncertainty(uninterrupted.rootUncertainty,
                                     splitFinal.budgetDiagnostic.finalRootUncertainty),
          "ordinary split continuation must match uninterrupted final action and root statistics");

    // The sequential diagnostic visits a geometric schedule on one private
    // root. Its final result must remain byte-for-byte equivalent to the
    // uninterrupted reference, while every chunk reports its exact cumulative
    // simulation count and the final action label.
    auto sequentialConfig = serializedSearchConfig;
    sequentialConfig.simulationsPerDecision = 1000;
    sequentialConfig.collectDecisionDiagnostics = true;
    sequentialConfig.collectRootActionSummaries = true;
    sequentialConfig.budgetDiagnosticCheckpoints = {250, 500, 750, 1000};
    const auto sequential = silver_bridge::runSilverDecision(firstWire, sequentialConfig);
    check(sequential.accepted && sequential.simulations == 1000
              && sequential.checkpointDiagnostics.size() == 4
              && silver_bridge::semanticActionFingerprint(sequential.action)
                  == silver_bridge::semanticActionFingerprint(uninterrupted.action)
              && sameRootActionSummaries(sequential.rootActionSummaries,
                                          uninterrupted.rootActionSummaries),
          "multi-checkpoint continuation must preserve the uninterrupted final result");
    bool checkpointsExact = true;
    for (std::size_t i = 0; i < sequential.checkpointDiagnostics.size(); ++i) {
        const auto &checkpoint = sequential.checkpointDiagnostics[i];
        checkpointsExact = checkpointsExact && checkpoint.valid
            && checkpoint.checkpointSimulations == sequentialConfig.budgetDiagnosticCheckpoints[i]
            && !checkpoint.checkpointActionFingerprint.empty()
            && checkpoint.finalActionFingerprint
                == silver_bridge::semanticActionFingerprint(sequential.action)
            && checkpoint.rootUncertainty.rootVisits
                == checkpoint.checkpointSimulations;
    }
    check(checkpointsExact,
          "multi-checkpoint continuation must expose exact cumulative budgets and final labels");

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

    // A forced action is searched from its post-action state.  A lethal Feed
    // therefore moves the fresh search root past the +3 max-HP gain.  The
    // forced-action evaluator must restore the original-root victory utility,
    // including the terminal case where there are no continuation playouts.
    BattleContext lethalFeed = first;
    lethalFeed.cards.cardsInHand = 1;
    lethalFeed.cards.hand[0] = card(CardId::FEED, 90);
    lethalFeed.player.energy = 2;
    lethalFeed.monsters.arr[0].curHp = 1;
    search::CombatKnowledgeState lethalFeedKnowledge;
    lethalFeedKnowledge.initializeFromLiveBattle(lethalFeed);
    const auto lethalFeedWire = convert(lethalFeed, gc, lethalFeedKnowledge);
    silver_bridge::SilverSearchConfig forcedFeedConfig;
    forcedFeedConfig.reuseCapMode = silver_bridge::SilverReuseCapMode::NONE;
    const auto forcedFeed = silver_bridge::runSilverForcedActionReferences(
        lethalFeedWire, forcedFeedConfig, 8, 1);
    const auto feedReference = std::find_if(forcedFeed.begin(), forcedFeed.end(), [](const auto &ref) {
        return ref.action.type == silver_bridge::SemanticActionType::CARD
            && ref.action.card.id == static_cast<std::int16_t>(CardId::FEED);
    });
    check(feedReference != forcedFeed.end() && feedReference->accepted
              && feedReference->rawReplicates.size() == 1
              && feedReference->rawReplicates[0].terminalAfterAction
              && feedReference->rawReplicates[0].simulations == 0
              && feedReference->rawReplicates[0].victories == 1
              && std::abs(feedReference->rawReplicates[0].victoryBaselineCorrection - 6.0) < 1e-12
              && std::abs(feedReference->rawReplicates[0].appliedBaselineCorrection - 6.0) < 1e-12
              && std::abs(feedReference->rawReplicates[0].value
                  - feedReference->rawReplicates[0].leafRootValue - 6.0) < 1e-12,
          "lethal Feed forced action must restore original-root max-HP victory utility");

    // The bridge session must retain the exact private child selected at one
    // Silver decision and reroot into it at the next. This is an entirely
    // native/private action execution: no live BattleContext is touched.
    silver_bridge::SilverSearchConfig reuseConfig;
    reuseConfig.simulationsPerDecision = 64;
    reuseConfig.budgetDiagnosticCheckpoint = 32;
    const auto reuse = silver_bridge::probeSilverSearchSessionReuse(firstWire, reuseConfig);
    check(reuse.accepted && reuse.rerootExact == 1 && reuse.rerootFallback == 0
              && reuse.inheritedVisits > 0
              && reuse.splitFinalActionMatches
              && reuse.splitFinalRootStatisticsMatch,
          "retained-root split continuation must match uninterrupted action/root statistics");

    check(silver_bridge::SilverSearchConfig{}.reuseCap == 32768, "production reuse cap must remain 32k");
    const auto capFixture = silver_bridge::probeSilverReuseCapFixture(firstWire);
    check(capFixture.defaultEqualsExplicitAllocated,
          "unset/default and explicit allocated reuse-cap modes must agree");
    check(capFixture.retainedAllocationAboveCapAfterReset && capFixture.activeBelowCapAfterReset,
          "setRoot must retain allocation while resetting active pool usage");
    check(!capFixture.allocatedCapBlocked
              && capFixture.allocatedDiagnostic.exactCandidateFound
              && capFixture.allocatedDiagnostic.fallbackReason
                  == silver_bridge::SilverRerootFallbackReason::NONE,
          "allocated mode must discard historical allocation before checking the cap");
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
    observerConfig.collectRootActionSummaries = true;
    observerConfig.collectRolloutDiagnostics = true;
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
    check(noObserver.accepted && observed.accepted
              && silver_bridge::semanticActionFingerprint(noObserver.action)
                  == silver_bridge::semanticActionFingerprint(observed.action)
              && noObserver.simulations == observed.simulations
              && noObserver.telemetry.rolloutCalls == observed.telemetry.rolloutCalls
              && noObserver.telemetry.rolloutActionCount == observed.telemetry.rolloutActionCount
              && noObserver.telemetry.rolloutTurnDelta == observed.telemetry.rolloutTurnDelta
              && sameRootActionSummaries(noObserver.rootActionSummaries,
                                          observed.rootActionSummaries),
          "same-seed observer OFF/ON must preserve action, search counters, and root statistics");

    const auto directRolloutA = silver_bridge::runSilverSimpleRollout(firstWire, firstWire);
    const auto directRolloutB = silver_bridge::runSilverSimpleRollout(firstWire, firstWire);
    check(directRolloutA.accepted && directRolloutA.terminalOutcome != static_cast<int>(Outcome::UNDECIDED)
              && directRolloutA.rolloutActionCount > 0
              && directRolloutA.rolloutActionCount == static_cast<std::int64_t>(
                  directRolloutA.rolloutActionFingerprints.size())
              && directRolloutA.originalRootCorrectedUtility == directRolloutA.leafRootUtility,
          "stored PLAYER_NORMAL leaf must replay through the canonical SimpleAgent rollout seam");
    check(directRolloutA.accepted == directRolloutB.accepted
              && directRolloutA.terminalOutcome == directRolloutB.terminalOutcome
              && directRolloutA.terminalHp == directRolloutB.terminalHp
              && directRolloutA.leafRootUtility == directRolloutB.leafRootUtility
              && directRolloutA.rolloutActionFingerprints == directRolloutB.rolloutActionFingerprints,
          "canonical diagnostic rollout must be deterministic for a fixed stored RNG identity");

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

    // The retained-root treatment must continue fresh roots even when their
    // gap is above threshold, then permit an early stop only after exact
    // rerooting into a non-forced root with inherited visits.
    auto retainedPolicyConfig = adaptiveConfig;
    retainedPolicyConfig.adaptiveRequireRetainedRoot = true;
    retainedPolicyConfig.adaptiveTopTwoVisitGapThreshold = 0.0;
    const auto retainedPolicyFresh = silver_bridge::runSilverDecision(
        firstWire, retainedPolicyConfig);
    check(retainedPolicyFresh.accepted && retainedPolicyFresh.inheritedVisits == 0
              && retainedPolicyFresh.simulations == 32
              && retainedPolicyFresh.adaptiveEscalated,
          "retained-only adaptive policy must continue fresh roots to its total budget");
    const auto retainedPolicyReuse = silver_bridge::probeSilverSearchSessionReuse(
        firstWire, retainedPolicyConfig);
    check(retainedPolicyReuse.accepted && retainedPolicyReuse.inheritedVisits > 0
              && retainedPolicyReuse.firstSimulations == 32
              && retainedPolicyReuse.secondSimulations == 16,
          "retained-only adaptive policy must stop eligible retained roots at its initial budget");

    silver_bridge::SilverRootUncertainty exactBoundary;
    exactBoundary.valid = true;
    exactBoundary.topVisits = 10;
    exactBoundary.secondVisits = 7;
    check(!silver_bridge::silverExactVisitLockHolds(exactBoundary, 1000, 0)
              && !silver_bridge::silverExactVisitLockHolds(exactBoundary, 1000, 997)
              && silver_bridge::silverExactVisitLockHolds(exactBoundary, 1000, 998),
          "exact visit lock must use strict margin > remaining boundary");
    auto invalidExactBoundary = exactBoundary;
    invalidExactBoundary.valid = false;
    check(!silver_bridge::silverExactVisitLockHolds(invalidExactBoundary, 1, 0),
          "invalid or incomplete root summaries must never exact-lock");
    check(!silver_bridge::silverRhoRacingStopHolds(exactBoundary, 1000, 0, 2)
              && !silver_bridge::silverRhoRacingStopHolds(exactBoundary, 1000, 1000, 2)
              && !silver_bridge::silverRhoRacingStopHolds(exactBoundary, 1000, 998, 1)
              && silver_bridge::silverRhoRacingStopHolds(exactBoundary, 1000, 998, 2),
          "rho racing must require observations, remaining budget, and two stable leaders");
    auto rhoHalfBoundary = exactBoundary;
    rhoHalfBoundary.topVisits = 9;
    rhoHalfBoundary.secondVisits = 5;
    check(!silver_bridge::silverRhoRacingStopHolds(rhoHalfBoundary, 1000, 991, 2)
              && silver_bridge::silverRhoRacingStopHolds(rhoHalfBoundary, 1000, 992, 2),
          "rho racing must use the integer visit margin at the >= 0.50 boundary");
    auto incompatibleExactConfig = disabledConfig;
    incompatibleExactConfig.exactVisitLockEnabled = true;
    incompatibleExactConfig.adaptiveEnabled = true;
    const auto incompatibleExact = silver_bridge::runSilverDecision(
        firstWire, incompatibleExactConfig);
    check(!incompatibleExact.accepted
              && incompatibleExact.failureReason
                  == "exact_visit_lock_and_adaptive_are_incompatible",
          "exact visit-lock and retained-adaptive policies must fail closed when combined");

    // Exact visit-lock uses the caller's budget, not a 10k-specific constant.
    for (const auto maxBudget : {1000LL, 3700LL, 10000LL}) {
        auto exactConfig = disabledConfig;
        exactConfig.simulationsPerDecision = maxBudget;
        exactConfig.exactVisitLockEnabled = true;
        exactConfig.collectRootActionSummaries = true;
        exactConfig.collectDecisionDiagnostics = true;
        const auto freshExact = silver_bridge::runSilverDecision(firstWire, exactConfig);
        check(freshExact.accepted && freshExact.simulations == maxBudget
                  && !freshExact.diagnostic.exactVisitLockFired
                  && freshExact.diagnostic.exactVisitLockMaxBudget == maxBudget
                  && freshExact.diagnostic.exactVisitLockNewSimulationsUsed == maxBudget
                  && !freshExact.diagnostic.exactVisitLockFinalAction.empty(),
              "fresh exact visit-lock roots must run to each caller-supplied maximum budget");
    }
    auto exactReuseConfig = disabledConfig;
    exactReuseConfig.simulationsPerDecision = 1000;
    exactReuseConfig.exactVisitLockEnabled = true;
    exactReuseConfig.collectRootActionSummaries = true;
    exactReuseConfig.collectDecisionDiagnostics = true;
    const auto exactReuse = silver_bridge::probeSilverSearchSessionReuse(
        firstWire, exactReuseConfig);
    check(exactReuse.accepted && exactReuse.rerootExact == 1
              && exactReuse.rerootFallback == 0 && exactReuse.inheritedVisits > 0
              && exactReuse.secondSimulations <= exactReuseConfig.simulationsPerDecision
              && !exactReuse.rhoRacingFired
              && exactReuse.exactVisitLockActionMatchesFullBudget
              && exactReuse.exactVisitLockCheckpointCount >= 2
              && exactReuse.exactVisitLockTelemetryMatchesCheckpointTrace
              && exactReuse.exactVisitLockNodesMatchCheckpointTrace,
          "retained exact visit-lock search must preserve the uninterrupted max-budget action");
    auto exactZeroConfig = exactReuseConfig;
    exactZeroConfig.simulationsPerDecision = 1;
    const auto exactZero = silver_bridge::probeSilverSearchSessionReuse(
        firstWire, exactZeroConfig);
    check(exactZero.accepted && exactZero.exactVisitLockFiredAtZero
              && exactZero.secondSimulations == 0,
          "retained exact visit-lock must support a safe zero-new-simulation stop");

    auto rhoConfig = disabledConfig;
    rhoConfig.simulationsPerDecision = 1000;
    rhoConfig.rhoRacingEnabled = true;
    rhoConfig.collectRootActionSummaries = true;
    rhoConfig.collectDecisionDiagnostics = true;
    const auto rhoFresh = silver_bridge::runSilverDecision(firstWire, rhoConfig);
    check(rhoFresh.accepted && rhoFresh.inheritedVisits == 0
              && rhoFresh.simulations == rhoConfig.simulationsPerDecision
              && rhoFresh.diagnostic.rhoRacingEnabled
              && !rhoFresh.diagnostic.rhoRacingFired,
          "rho racing must never soft-stop a fresh root");
    const auto rhoReuse = silver_bridge::probeSilverSearchSessionReuse(firstWire, rhoConfig);
    check(rhoReuse.accepted && rhoReuse.inheritedVisits > 0
              && rhoReuse.secondSimulations <= rhoConfig.simulationsPerDecision
              && rhoReuse.secondRootVisitsAfterSearch
                  == rhoReuse.inheritedVisits + rhoReuse.secondSimulations,
          "rho racing retained-root continuation must preserve visit accounting");
    check(!(rhoReuse.exactVisitLockFired && rhoReuse.rhoRacingFired),
          "rho racing must give exact locking priority when both predicates could hold at a checkpoint");
    auto incompatibleRhoConfig = rhoConfig;
    incompatibleRhoConfig.exactVisitLockEnabled = true;
    const auto incompatibleRho = silver_bridge::runSilverDecision(
        firstWire, incompatibleRhoConfig);
    check(!incompatibleRho.accepted
              && incompatibleRho.failureReason
                  == "exact_visit_lock_and_rho_racing_are_incompatible",
          "rho racing must fail closed when the exact-lock-only controller is also selected");

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
    const auto staleConversion = search::makeSilverBattleStateConversion(
        first, stale, search::makeSilverRunContext(gc), 0xA11CEu);
    const auto &staleWire = staleConversion.wire;
    check(!staleWire.valid && !silver_bridge::inspectConvertedBattleState(staleWire).accepted,
          "stale positional knowledge must fail closed rather than inspect hidden pile positions");
    check(staleConversion.failureReason.find("stale_draw_pile_positional_knowledge") == 0,
          "failed Silver conversion must identify the public fail-closed reason");

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

    auto uninterruptedTransactionConfig = transactionConfig;
    uninterruptedTransactionConfig.collectRootActionSummaries = true;
    const auto uninterruptedTransaction = silver_bridge::runSequentialSelectionTransaction(
        convert(transactionLive, gc, transactionKnowledge), uninterruptedTransactionConfig);
    auto splitTransactionConfig = uninterruptedTransactionConfig;
    splitTransactionConfig.collectBudgetDiagnostics = true;
    splitTransactionConfig.budgetDiagnosticCheckpoint = 8;
    const auto splitTransaction = silver_bridge::runSequentialSelectionTransaction(
        convert(transactionLive, gc, transactionKnowledge), splitTransactionConfig);
    bool sequentialRootStatsMatch = uninterruptedTransaction.accepted
        && splitTransaction.accepted
        && uninterruptedTransaction.searchDecisions == splitTransaction.searchDecisions
        && uninterruptedTransaction.budgetDiagnostics.empty()
        && splitTransaction.budgetDiagnostics.size()
            == static_cast<std::size_t>(splitTransaction.searchDecisions)
        && silver_bridge::semanticActionFingerprint(uninterruptedTransaction.finalAction)
            == silver_bridge::semanticActionFingerprint(splitTransaction.finalAction);
    if (sequentialRootStatsMatch) {
        for (std::size_t i = 0; i < splitTransaction.budgetDiagnostics.size(); ++i) {
            sequentialRootStatsMatch = sequentialRootStatsMatch
                && sameRootUncertainty(uninterruptedTransaction.searchDiagnostics[i].rootUncertainty,
                                       splitTransaction.budgetDiagnostics[i].finalRootUncertainty);
        }
    }
    check(sequentialRootStatsMatch,
          "sequential-selection split continuation must match uninterrupted final action/root statistics");

    auto multiTransactionConfig = uninterruptedTransactionConfig;
    multiTransactionConfig.budgetDiagnosticCheckpoints = {4, 8, 12, 16};
    const auto multiTransaction = silver_bridge::runSequentialSelectionTransaction(
        convert(transactionLive, gc, transactionKnowledge), multiTransactionConfig);
    bool multiTransactionComplete = multiTransaction.accepted
        && multiTransaction.finalConfirmation
        && multiTransaction.searchDecisions == uninterruptedTransaction.searchDecisions
        && multiTransaction.checkpointDiagnostics.size()
            == static_cast<std::size_t>(multiTransaction.searchDecisions)
        && silver_bridge::semanticActionFingerprint(multiTransaction.finalAction)
            == silver_bridge::semanticActionFingerprint(uninterruptedTransaction.finalAction);
    if (multiTransactionComplete) {
        for (std::size_t subdecisionIndex = 0;
             subdecisionIndex < multiTransaction.checkpointDiagnostics.size();
             ++subdecisionIndex) {
            const auto &subdecision = multiTransaction.checkpointDiagnostics[subdecisionIndex];
            multiTransactionComplete = multiTransactionComplete && subdecision.size() == 4;
            for (std::size_t i = 0; i < subdecision.size(); ++i) {
                multiTransactionComplete = multiTransactionComplete
                    && subdecision[i].valid
                    && subdecision[i].checkpointSimulations
                        == multiTransactionConfig.budgetDiagnosticCheckpoints[i]
                    && !subdecision[i].checkpointActionFingerprint.empty()
                    && !subdecision[i].finalActionFingerprint.empty()
                    && subdecision[i].rootVisitsAfterSearch
                        == multiTransaction.searchDiagnostics[subdecisionIndex].inheritedVisits
                            + multiTransactionConfig.budgetDiagnosticCheckpoints[i];
            }
        }
    }
    check(multiTransactionComplete,
          "sequential-selection multi-checkpoint continuation must cover every private subdecision");
    auto exactTransactionConfig = transactionConfig;
    exactTransactionConfig.simulationsPerDecision = 32;
    exactTransactionConfig.exactVisitLockEnabled = true;
    exactTransactionConfig.collectRootActionSummaries = true;
    exactTransactionConfig.collectDecisionDiagnostics = true;
    const auto exactTransaction = silver_bridge::runSequentialSelectionTransaction(
        convert(transactionLive, gc, transactionKnowledge), exactTransactionConfig);
    bool exactTransactionAccounting = exactTransaction.accepted
        && exactTransaction.finalConfirmation
        && exactTransaction.searchDiagnostics.size()
            == static_cast<std::size_t>(exactTransaction.searchDecisions);
    for (const auto &diagnostic : exactTransaction.searchDiagnostics) {
        exactTransactionAccounting = exactTransactionAccounting
            && diagnostic.exactVisitLockEnabled
            && diagnostic.exactVisitLockNewSimulationsUsed <= 32
            && diagnostic.exactVisitLockRemainingBudget >= 0;
    }
    check(exactTransactionAccounting,
          "exact visit-lock must preserve transactional sequential card selection and accounting");
    auto rhoTransactionConfig = exactTransactionConfig;
    rhoTransactionConfig.exactVisitLockEnabled = false;
    rhoTransactionConfig.rhoRacingEnabled = true;
    const auto rhoTransaction = silver_bridge::runSequentialSelectionTransaction(
        convert(transactionLive, gc, transactionKnowledge), rhoTransactionConfig);
    bool rhoTransactionAccounting = rhoTransaction.accepted
        && rhoTransaction.finalConfirmation
        && rhoTransaction.searchDiagnostics.size()
            == static_cast<std::size_t>(rhoTransaction.searchDecisions);
    for (const auto &diagnostic : rhoTransaction.searchDiagnostics) {
        rhoTransactionAccounting = rhoTransactionAccounting
            && diagnostic.rhoRacingEnabled
            && diagnostic.exactVisitLockNewSimulationsUsed <= 32
            && diagnostic.exactVisitLockRemainingBudget >= 0
            && diagnostic.rootVisitsAfterSearch
                == diagnostic.inheritedVisits + diagnostic.simulationsAdded;
    }
    check(rhoTransactionAccounting,
          "rho racing must preserve transactional sequential card selection and accounting");
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
