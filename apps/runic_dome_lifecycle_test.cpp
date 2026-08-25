// Real live-combat lifecycle tests for Runic Dome -> isolated Silver roots.
#include <cstdlib>
#include <iostream>

#include "combat/Actions.h"
#include "combat/BattleContext.h"
#include "game/GameContext.h"
#include "sim/search/Action.h"
#include "sim/search/CombatKnowledge.h"
#include "sim/search/SilverConversion.h"

namespace {

using namespace sts;
using namespace sts::search;

class ObserverScope {
public:
    explicit ObserverScope(CombatKnowledgeState &knowledge)
        : previous_(g_combatKnowledgeObserver) { g_combatKnowledgeObserver = &knowledge; }
    ~ObserverScope() { g_combatKnowledgeObserver = previous_; }
private:
    CombatKnowledgeObserver *previous_;
};

void check(bool value, const char *message) {
    if (!value) {
        std::cerr << "runic_dome_lifecycle FAIL: " << message << '\n';
        std::exit(1);
    }
}

void installDeck(GameContext &gc) {
    gc.deck.cards.clear();
    for (int i = 0; i < 5; ++i) gc.deck.obtainRaw(Card(CardId::STRIKE_RED));
    for (int i = 0; i < 4; ++i) gc.deck.obtainRaw(Card(CardId::DEFEND_RED));
    gc.deck.obtainRaw(Card(CardId::BASH));
}

struct LiveFixture {
    GameContext gc;
    BattleContext bc;
    CombatKnowledgeState knowledge;
    ObserverScope observer;

    LiveFixture(MonsterEncounter encounter, std::uint64_t seed)
        : gc(CharacterClass::IRONCLAD, seed, 0), observer(knowledge) {
        installDeck(gc);
        gc.obtainRelic(RelicId::RUNIC_DOME);
        gc.info.encounter = encounter;
        // This configuration is deliberately before bc.init: Player relic
        // initialization follows monster construction and initial rollMove.
        knowledge.configureHiddenMonsterIntents(gc.relics.has(RelicId::RUNIC_DOME));
        knowledge.initializeFromLiveBattle(bc);
        knowledge.beginCombatInitialization();
        bc.init(gc, encounter);
        knowledge.synchronizeAfterCombatInitialization(bc);
    }

    silver_bridge::BattleStateWire wire() const {
        return makeSilverBattleStateWire(bc, knowledge, makeSilverRunContext(gc), 0xD0E0u);
    }
};

void endTurn(BattleContext &bc) {
    const sts::search::Action action(ActionType::END_TURN);
    check(action.isValidAction(bc), "END_TURN must be a valid real action");
    action.execute(bc);
}

void testInitialAndTurnLifecycle() {
    LiveFixture fixture(MonsterEncounter::BOOK_OF_STABBING, 0xD001u);
    check(fixture.knowledge.hiddenMonsterIntents, "GameContext must configure hidden intent before init");
    check(fixture.knowledge.pendingHiddenIntentRolls[0] == 1,
          "initial Runic Dome roll must create exactly one pending chain");
    const auto initial = silver_bridge::inspectConvertedBattleState(fixture.wire());
    check(initial.accepted && initial.pendingIntentRolls == 1,
          "initial real battle must materialize a pending Silver intent");
    check(initial.monsterMoveHistory[0] == fixture.knowledge.publicMonsterMoveHistory[0]
              && initial.monsterMiscInfo[0] == fixture.knowledge.publicMonsterMiscInfo[0],
          "materialized Silver root must use observer public snapshot");

    endTurn(fixture.bc);
    check(fixture.bc.outcome == Outcome::UNDECIDED, "one Book of Stabbing turn must leave controlled fixture alive");
    check(fixture.knowledge.pendingHiddenIntentRolls[0] == 1,
          "monster action must consume old pending intent before next hidden roll");
    check(fixture.knowledge.publicMonsterMoveHistory[0][0]
              == static_cast<std::int16_t>(fixture.bc.monsters.arr[0].moveHistory[1]),
          "fresh hidden chain must retain previous public move, never current hidden move");

    endTurn(fixture.bc);
    check(fixture.knowledge.pendingHiddenIntentRolls[0] == 1,
          "pending intent count must remain current-chain count across turns");
    check(fixture.knowledge.publicMonsterMoveHistory[0][0]
              == static_cast<std::int16_t>(fixture.bc.monsters.arr[0].moveHistory[1]),
          "two-turn public lastMove snapshot must survive");
    const auto converted = silver_bridge::inspectConvertedBattleState(fixture.wire());
    check(converted.accepted && converted.pendingIntentRolls == 1
              && converted.monsterMoveHistory[0] == fixture.knowledge.publicMonsterMoveHistory[0],
          "actual materialized Silver root must preserve current pending chain and public history");
}

void testHiddenMoveAndLiveRngRedaction() {
    LiveFixture fixture(MonsterEncounter::CULTIST, 0xD005u);
    const auto root = fixture.wire();
    BattleContext differentHiddenMove = fixture.bc;
    differentHiddenMove.monsters.arr[0].moveHistory[0] = MonsterMoveId::CULTIST_INCANTATION;
    const auto differentMoveWire = makeSilverBattleStateWire(
        differentHiddenMove, fixture.knowledge, makeSilverRunContext(fixture.gc), 0xD0E0u);
    check(root.valid && differentMoveWire.valid
              && silver_bridge::convertedStatesEqualForSearch(root, differentMoveWire),
          "actual captured Runic root must redact a changed concrete hidden move");

    BattleContext differentRng = fixture.bc;
    ++differentRng.aiRng.counter;
    ++differentRng.cardRandomRng.counter;
    ++differentRng.miscRng.counter;
    ++differentRng.monsterHpRng.counter;
    ++differentRng.potionRng.counter;
    ++differentRng.shuffleRng.counter;
    const auto differentRngWire = makeSilverBattleStateWire(
        differentRng, fixture.knowledge, makeSilverRunContext(fixture.gc), 0xD0E0u);
    check(differentRngWire.valid && silver_bridge::convertedStatesEqualForSearch(root, differentRngWire),
          "all six live RNG streams must be absent from the materialized Silver root");

    auto inconsistent = fixture.knowledge;
    inconsistent.configureHiddenMonsterIntents(false);
    check(!makeSilverBattleStateWire(fixture.bc, inconsistent, makeSilverRunContext(fixture.gc), 0xD0E0u).valid,
          "missing pre-init hidden-intent configuration must fail closed");
}

void testRestrictedHistoryAndPreRollMiscInfo() {
    LiveFixture restricted(MonsterEncounter::BOOK_OF_STABBING, 0xD002u);
    const auto beforeHistory = restricted.knowledge.publicMonsterMoveHistory[0];
    const int beforeMisc = restricted.knowledge.publicMonsterMiscInfo[0];
    // Drive actual hidden rerolls until Book of Stabbing's roll-time counter
    // mutates. The observer must keep the fresh-chain pre-roll snapshot.
    for (int i = 0; i < 32 && (i == 0 || restricted.bc.monsters.arr[0].miscInfo == beforeMisc); ++i) {
        restricted.bc.monsters.arr[0].rollMove(restricted.bc);
    }
    check(restricted.bc.monsters.arr[0].miscInfo != beforeMisc,
          "fixture must exercise a monster roll that mutates miscInfo");
    check(restricted.knowledge.pendingHiddenIntentRolls[0] > 1,
          "genuine chained hidden rerolls must increment pending chain count");
    const auto converted = silver_bridge::inspectConvertedBattleState(restricted.wire());
    check(converted.accepted && converted.monsterMoveHistory[0] == beforeHistory
              && converted.monsterMiscInfo[0] == beforeMisc,
          "Silver root must retain pre-roll public history/miscInfo, not post-roll live values");
}

void testReactiveChainAndIntentQuery() {
    LiveFixture chained(MonsterEncounter::WRITHING_MASS, 0xD003u);
    chained.bc.monsters.arr[0].setStatus<MS::REACTIVE>(2);
    Actions::ReactiveRollMove().actFunc(chained.bc);
    check(chained.knowledge.pendingHiddenIntentRolls[0] == 3,
          "two real reactive rerolls must extend the deferred chain from one to three");

    LiveFixture queried(MonsterEncounter::CULTIST, 0xD004u);
    check(queried.knowledge.pendingHiddenIntentRolls[0] == 1,
          "query fixture must begin with pending intent");
    Actions::SpotWeaknessAction(0, 3).actFunc(queried.bc);
    check(queried.knowledge.pendingHiddenIntentRolls[0] == 0,
          "Spot Weakness must materialize and consume the pending intent");
    check(queried.knowledge.publicMonsterMoveHistory[0][0]
              == static_cast<std::int16_t>(queried.bc.monsters.arr[0].moveHistory[0]),
          "intent query must publish the materialized move before reading it");
    const auto converted = silver_bridge::inspectConvertedBattleState(queried.wire());
    check(converted.accepted && converted.pendingIntentRolls == 0
              && converted.monsterMoveHistory[0] == queried.knowledge.publicMonsterMoveHistory[0],
          "post-query Silver root must contain public intent, not a fabricated pending roll");
}

void testPostTurnDeterministicAndDirectRandomTransitions() {
    LiveFixture deterministic(MonsterEncounter::CULTIST, 0xD006u);
    // A constructed public fixture state: LICK is the public current move.
    // takeTurn itself performs the real deterministic LICK -> TACKLE update.
    deterministic.bc.monsters.arr[0].id = MonsterId::ACID_SLIME_S;
    deterministic.bc.monsters.arr[0].setMove(MonsterMoveId::ACID_SLIME_S_LICK);
    deterministic.bc.monsters.arr[0].takeTurn(deterministic.bc);
    check(deterministic.knowledge.pendingHiddenIntentRolls[0] == 0
              && deterministic.knowledge.publicMonsterMoveHistory[0][0]
                    == static_cast<std::int16_t>(MonsterMoveId::ACID_SLIME_S_TACKLE),
          "Acid Slime S deterministic LICK -> TACKLE must become known after its real turn");
    const auto deterministicRoot = silver_bridge::inspectConvertedBattleState(deterministic.wire());
    check(deterministicRoot.accepted && deterministicRoot.pendingIntentRolls == 0
              && deterministicRoot.monsterMoveHistory[0][0]
                    == static_cast<std::int16_t>(MonsterMoveId::ACID_SLIME_S_TACKLE),
          "materialized Silver root must carry deterministic next intent, not stale LICK");

    LiveFixture random(MonsterEncounter::LOOTER, 0xD007u);
    // getMonsterTurnNumber() is turn+1; turn=1 selects the Looter direct
    // post-turn 50/50 branch rather than the first-turn deterministic Mug.
    random.bc.turn = 1;
    random.bc.monsters.arr[0].setMove(MonsterMoveId::LOOTER_MUG);
    random.bc.monsters.arr[0].takeTurn(random.bc);
    check(random.knowledge.hasUnrepresentableHiddenIntent[0],
          "Looter direct post-turn RNG must be marked hidden, never published from live setMove");
    check(!random.wire().valid,
          "unrepresented direct post-turn RNG must fail conversion rather than leak its live result");
}

} // namespace

int main() {
    testInitialAndTurnLifecycle();
    testHiddenMoveAndLiveRngRedaction();
    testRestrictedHistoryAndPreRollMiscInfo();
    testReactiveChainAndIntentQuery();
    testPostTurnDeterministicAndDirectRandomTransitions();
    std::cout << "runic_dome_lifecycle PASS\n";
    return 0;
}
