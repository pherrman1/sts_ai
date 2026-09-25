// Real live-combat lifecycle tests for Runic Dome -> Silver search roots.
#include <array>
#include <cstdlib>
#include <iostream>

#include "combat/Actions.h"
#include "combat/BattleContext.h"
#include "game/GameContext.h"
#include "sim/search/Action.h"
#include "sim/search/CombatKnowledge.h"
#include "sim/search/SilverConversion.h"
#include "sim/search/SilverWireState.h"

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

// The search root the native Silver search builds from a wire state.
struct RootDigest {
    bool accepted = false;
    int pendingIntentRolls = 0;
    int pendingDirectMoveChoices = 0;
    std::array<std::array<std::int16_t, 2>, 5> monsterMoveHistory {};
    std::array<std::int32_t, 5> monsterMiscInfo {};
};

RootDigest digest(const BattleContext &root) {
    RootDigest out;
    out.accepted = true;
    for (int i = 0; i < 5; ++i) {
        const auto &m = root.monsters.arr[i];
        out.pendingIntentRolls += m.pendingMoveRolls;
        out.pendingDirectMoveChoices += m.pendingDirectMoveChoice != 0;
        out.monsterMoveHistory[i] = {static_cast<std::int16_t>(m.moveHistory[0]),
                                     static_cast<std::int16_t>(m.moveHistory[1])};
        out.monsterMiscInfo[i] = m.miscInfo;
    }
    return out;
}

RootDigest inspectRoot(const silver_bridge::BattleStateWire &wire) {
    try {
        return digest(battleContextFromWire(wire));
    } catch (const std::exception &) {
        return {};
    }
}

// Resolves the root's deferred intents with the search's own RNG. Like the
// search, this runs detached from the live knowledge observer.
RootDigest materializedRoot(const silver_bridge::BattleStateWire &wire) {
    CombatKnowledgeObserver *const observer = g_combatKnowledgeObserver;
    g_combatKnowledgeObserver = nullptr;
    RootDigest result;
    try {
        auto root = battleContextFromWire(wire);
        for (int i = 0; i < root.monsters.monsterCount; ++i) root.monsters.arr[i].materializePendingMove(root);
        result = digest(root);
    } catch (const std::exception &) {
    }
    g_combatKnowledgeObserver = observer;
    return result;
}

bool sameRoot(const silver_bridge::BattleStateWire &a, const silver_bridge::BattleStateWire &b) {
    return battleContextFromWire(a).equalForSearch(battleContextFromWire(b));
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
    const auto initial = inspectRoot(fixture.wire());
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
    const auto converted = inspectRoot(fixture.wire());
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
              && sameRoot(root, differentMoveWire),
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
    check(differentRngWire.valid && sameRoot(root, differentRngWire),
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
    const auto converted = inspectRoot(restricted.wire());
    check(converted.accepted && converted.monsterMoveHistory[0] == beforeHistory
              && converted.monsterMiscInfo[0] == beforeMisc,
          "Silver root must retain pre-roll public history/miscInfo, not post-roll live values");
}

void testReactiveChainAndIntentQuery() {
    LiveFixture chained(MonsterEncounter::WRITHING_MASS, 0xD003u);
    chained.bc.monsters.arr[0].setStatus<MS::REACTIVE>(2);
    Actions::ReactiveRollMove()(chained.bc);
    check(chained.knowledge.pendingHiddenIntentRolls[0] == 3,
          "two real reactive rerolls must extend the deferred chain from one to three");

    LiveFixture queried(MonsterEncounter::CULTIST, 0xD004u);
    check(queried.knowledge.pendingHiddenIntentRolls[0] == 1,
          "query fixture must begin with pending intent");
    Actions::SpotWeaknessAction(0, 3)(queried.bc);
    check(queried.knowledge.pendingHiddenIntentRolls[0] == 0,
          "Spot Weakness must materialize and consume the pending intent");
    check(queried.knowledge.publicMonsterMoveHistory[0][0]
              == static_cast<std::int16_t>(queried.bc.monsters.arr[0].moveHistory[0]),
          "intent query must publish the materialized move before reading it");
    const auto converted = inspectRoot(queried.wire());
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
    const auto deterministicRoot = inspectRoot(deterministic.wire());
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
    const auto randomRoot = inspectRoot(random.wire());
    check(randomRoot.accepted && randomRoot.pendingIntentRolls == 0
              && randomRoot.pendingDirectMoveChoices == 1
              && randomRoot.monsterMoveHistory[0][0]
                    == static_cast<std::int16_t>(MonsterMoveId::LOOTER_MUG),
          "Looter direct post-turn RNG must materialize as a private deferred 50/50 choice, never its live result");
    const auto materializedChoice = materializedRoot(random.wire());
    const auto selected = materializedChoice.monsterMoveHistory[0][0];
    check(materializedChoice.accepted && materializedChoice.pendingDirectMoveChoices == 0
              && (selected == static_cast<std::int16_t>(MonsterMoveId::LOOTER_SMOKE_BOMB)
                  || selected == static_cast<std::int16_t>(MonsterMoveId::LOOTER_LUNGE)),
          "deferred Looter choice must sample only its two upstream outcomes inside the isolated model");
    bool sawSmokeBomb = false;
    bool sawLunge = false;
    for (std::uint64_t seed = 1; seed <= 32; ++seed) {
        auto alternative = random.wire();
        alternative.isolatedSearchSeed = seed;
        const auto sampled = materializedRoot(alternative);
        sawSmokeBomb |= sampled.monsterMoveHistory[0][0]
            == static_cast<std::int16_t>(MonsterMoveId::LOOTER_SMOKE_BOMB);
        sawLunge |= sampled.monsterMoveHistory[0][0]
            == static_cast<std::int16_t>(MonsterMoveId::LOOTER_LUNGE);
    }
    check(sawSmokeBomb && sawLunge,
          "the deferred direct choice must remain stochastic across isolated Silver RNG realizations");

    Actions::SpotWeaknessAction(0, 3)(random.bc);
    check(!random.knowledge.hasUnrepresentableHiddenIntent[0],
          "a public intent query must consume the deferred Looter choice marker");
    const auto queriedDirectChoice = inspectRoot(random.wire());
    check(queriedDirectChoice.accepted && queriedDirectChoice.pendingDirectMoveChoices == 0
              && queriedDirectChoice.monsterMoveHistory[0][0]
                    == static_cast<std::int16_t>(random.bc.monsters.arr[0].moveHistory[0]),
          "post-query Silver root must carry the public Looter choice without a stale deferred marker");
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
