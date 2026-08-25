// Focused live->wire->isolated-Silver boundary tests.  This executable has a
// separate link closure so ordinary unit-test never links the full vendor model.
#include <algorithm>
#include <iostream>

#include "combat/BattleContext.h"
#include "game/GameContext.h"
#include "sim/search/CombatKnowledge.h"
#include "sim/search/ScumSearchAgent2.h"
#include "sim/search/SilverBridge.h"
#include "sim/search/SilverConversion.h"
#include "sim/search/SilverSemanticAction.h"

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

    // The bridge session must retain the exact private child selected at one
    // Silver decision and reroot into it at the next. This is an entirely
    // native/private action execution: no live BattleContext is touched.
    silver_bridge::SilverSearchConfig reuseConfig;
    reuseConfig.simulationsPerDecision = 32;
    const auto reuse = silver_bridge::probeSilverSearchSessionReuse(firstWire, reuseConfig);
    check(reuse.accepted && reuse.rerootExact == 1 && reuse.rerootFallback == 0
              && reuse.inheritedVisits > 0,
          "private Silver session must exact-reroot and retain prior subtree visits");

    // Cross the actual boundary once: Silver emits an index-free semantic
    // action, the ordinary live simulator executes its resolved action, and
    // the next wire is materialized with the same public battle seed. This
    // catches an accidental per-decision root seed, which would make Silver
    // equalForSearch reject every live successor before it reaches reroot.
    auto boundaryKnowledge = firstKnowledge;
    auto boundaryLive = first;
    auto boundarySession = silver_bridge::makeSilverSearchSession();
    const auto firstBoundaryDecision = silver_bridge::runSilverDecision(*boundarySession, firstWire, reuseConfig);
    const auto firstBoundaryAction = search::resolveSilverSemanticAction(
        boundaryLive, firstBoundaryDecision.action);
    check(firstBoundaryDecision.accepted
              && firstBoundaryDecision.action.type == silver_bridge::SemanticActionType::CARD
              && firstBoundaryAction.ok,
          "first real-boundary Silver decision must be a resolvable deterministic card action");
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
    transactionLive.cards.cardsInHand = 2;
    transactionLive.cards.hand[0] = card(CardId::STRIKE_RED, 81);
    transactionLive.cards.hand[1] = card(CardId::DEFEND_RED, 82);
    transactionLive.inputState = InputState::CARD_SELECT;
    transactionLive.cardSelectInfo.cardSelectTask = CardSelectTask::GAMBLE;
    transactionLive.cardSelectInfo.canPickAnyNumber = true;
    search::CombatKnowledgeState transactionKnowledge;
    transactionKnowledge.initializeFromLiveBattle(transactionLive);
    const BattleContext transactionBefore = transactionLive;
    silver_bridge::SilverSearchConfig transactionConfig;
    transactionConfig.simulationsPerDecision = 16;
    const auto transaction = silver_bridge::runSequentialSelectionTransaction(
        convert(transactionLive, gc, transactionKnowledge), transactionConfig);
    if (!transaction.accepted) {
        std::cerr << "  GAMBLE transaction diagnostic: " << transaction.failure
                  << " decisions=" << transaction.searchDecisions
                  << " sims=" << transaction.totalSimulations << '\n';
    }
    check(transaction.accepted && transaction.finalConfirmation && transaction.privateStateOnly
          && transaction.searchDecisions >= 1 && transaction.totalSimulations >= transaction.searchDecisions,
          "GAMBLE transaction must return a private final confirmation after full-budget subdecisions");
    check(transaction.finalAction.type == silver_bridge::SemanticActionType::MULTI_CARD_SELECT
          && transaction.intermediateSelections.size() == transaction.selectedBitsAfterEachIntermediate.size()
          && (transaction.selectedBitsAfterEachIntermediate.empty()
              || transaction.selectedBitsAfterEachIntermediate.front() != 0),
          "GAMBLE transaction must retain private selectedBits and return only a final semantic subset");
    check(transactionLive.inputState == transactionBefore.inputState
          && transactionLive.cardSelectInfo.cardSelectTask == transactionBefore.cardSelectInfo.cardSelectTask
          && transactionLive.cards.cardsInHand == transactionBefore.cards.cardsInHand
          && transactionLive.cards.hand[0].uniqueId == transactionBefore.cards.hand[0].uniqueId
          && transactionLive.cards.hand[1].uniqueId == transactionBefore.cards.hand[1].uniqueId
          && transactionLive.aiRng.counter == transactionBefore.aiRng.counter
          && transactionLive.cardRandomRng.counter == transactionBefore.cardRandomRng.counter
          && transactionLive.shuffleRng.counter == transactionBefore.shuffleRng.counter,
          "private sequential selection transaction must not mutate live state or live RNG");

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
