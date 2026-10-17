#include <algorithm>
#include <iostream>
#include <stdexcept>
#include <string>

#include "combat/BattleContext.h"
#include "game/GameContext.h"
#include "one_combat/combat_transition.h"
#include "sim/search/Action.h"

namespace {
using namespace sts;

void require(bool ok, const std::string &message) {
    if (!ok) throw std::runtime_error(message);
}

struct Fixture {
    GameContext game{CharacterClass::IRONCLAD, 0xDA663u, 0};
    BattleContext battle;

    Fixture(bool upgraded, MonsterEncounter encounter = MonsterEncounter::CULTIST,
            bool twoDaggers = false, bool daggerInDeck = true) {
        game.deck = Deck{};
        game.deck.obtainRaw(Card(daggerInDeck ? CardId::RITUAL_DAGGER : CardId::STRIKE_RED, upgraded));
        if (twoDaggers) {
            Card second(CardId::RITUAL_DAGGER, !upgraded); second.misc = 31;
            game.deck.obtainRaw(second);
        }
        game.deck.obtainRaw(Card(CardId::STRIKE_RED));
        game.curRoom = Room::MONSTER;
        game.floorNum = 1;
        game.enterBattle(encounter);
        // Exercise the full RAW exit transfer without generating a reward UI.
        game.regainControlAction = [](GameContext &) {};
        battle.init(game, encounter);
        while (battle.inputState != InputState::PLAYER_NORMAL && battle.outcome == Outcome::UNDECIDED)
            battle.executeActions();
        require(battle.inputState == InputState::PLAYER_NORMAL, "fixture did not reach player control");
        for (int i = 0; i < battle.monsters.monsterCount; ++i) {
            battle.monsters.arr[i].curHp = 1;
            battle.monsters.arr[i].block = 0;
        }
    }

    void play(int uniqueId, int target = 0) {
        int index = -1;
        for (int i = 0; i < battle.cards.cardsInHand; ++i)
            if (battle.cards.hand[i].uniqueId == uniqueId) index = i;
        require(index >= 0, "physical fixture card missing from hand");
        const search::Action action(search::ActionType::CARD, index, target);
        require(action.isValidAction(battle), "fixture card action was not legal");
        action.execute(battle);
    }

    void finish() {
        require(battle.outcome == Outcome::PLAYER_VICTORY, "fixture did not win combat");
        battle.exitBattle(game);
    }
};

void lethal(bool upgraded, MonsterEncounter encounter) {
    Fixture f(upgraded, encounter, true);
    int rawCaptures = 0;
    nlohmann::json rawDeck;
    f.play(0);
    {
        one_combat::CombatTransitionRawObserverScope observer([&](const BattleContext &ended, GameContext &raw) {
            require(ended.outcome == Outcome::PLAYER_VICTORY, "RAW capture did not observe real victory");
            require(raw.screenState == ScreenState::BATTLE, "RAW capture ran after screen continuation");
            ++rawCaptures;
            rawDeck = one_combat::combatTransitionStateJson(
                one_combat::captureCombatTransitionState(raw)).at("deck");
        });
        f.finish();
    }
    const int expected = upgraded ? 20 : 18;
    require(rawCaptures == 1 && rawDeck.size() == 3, "missing/repeated RAW deck serialization");
    require(rawDeck.at(0).at("id") == static_cast<int>(CardId::RITUAL_DAGGER)
            && rawDeck.at(0).at("misc") == expected,
            "RAW transition serialized stale lethal Dagger damage");
    require(rawDeck.at(1).at("id") == static_cast<int>(CardId::RITUAL_DAGGER)
            && rawDeck.at(1).at("misc") == 31
            && rawDeck.at(2).at("id") == static_cast<int>(CardId::STRIKE_RED)
            && rawDeck.at(2).at("misc") == 0,
            "RAW serialization changed another physical master card");
    require(f.game.deck.cards[0].misc == expected,
        "lethal Dagger " + std::string(upgraded ? "+" : "base") + " lost growth: got "
        + std::to_string(f.game.deck.cards[0].misc) + ", expected " + std::to_string(expected));
    require(f.game.deck.cards[1].misc == 31, "lethal Dagger mutated the other physical copy");
}

void nonfinal(bool upgraded) {
    Fixture f(upgraded, MonsterEncounter::TWO_LOUSE);
    f.play(0);
    require(f.battle.outcome == Outcome::UNDECIDED, "first Louse unexpectedly ended combat");
    f.play(1, 1); f.finish();
    require(f.game.deck.cards[0].misc == (upgraded ? 20 : 18), "nonfinal Dagger lost growth");
}

void copied(bool upgraded) {
    Fixture f(upgraded);
    // The real Double Tap path plays the physical card nonlethally, then its
    // purge-on-use copy kills. Growth must reach the original UUID once.
    f.battle.monsters.arr[0].curHp = 16;
    f.battle.player.buff<PS::DOUBLE_TAP>(1);
    f.play(0); f.finish();
    require(f.battle.curCardQueueItem.purgeOnUse, "Double Tap copy did not deliver final hit");
    require(f.game.deck.cards[0].misc == (upgraded ? 20 : 18), "copied Dagger lost/doubled persistent growth");
}

void generated() {
    Fixture f(false, MonsterEncounter::CULTIST, false, false);
    const int uniqueId = f.battle.cards.nextUniqueCardId;
    f.battle.cards.createTempCardInHand(CardInstance(Card(CardId::RITUAL_DAGGER)));
    require(uniqueId >= f.game.deck.size(), "generated fixture aliased a master card");
    f.play(uniqueId); f.finish();
    for (const auto &card : f.game.deck.cards)
        require(card.id == CardId::STRIKE_RED && card.misc == 0, "generated Dagger mutated master deck");
}

void nonlethal() {
    Fixture f(false);
    f.battle.monsters.arr[0].curHp = 16;
    f.play(0);
    require(f.battle.outcome == Outcome::UNDECIDED, "nonlethal Dagger won combat");
    f.play(1); f.finish();
    require(f.game.deck.cards[0].misc == 15, "nonlethal Dagger incorrectly grew");
}

void generatedAfterImplant() {
    Fixture f(false, MonsterEncounter::WRITHING_MASS);
    f.battle.monsters.arr[0].miscInfo = 1;
    const int generatedId = f.battle.cards.nextUniqueCardId;
    f.battle.cards.createTempCardInHand(CardInstance(Card(CardId::RITUAL_DAGGER)));
    require(generatedId == f.game.deck.size(), "generated card did not precede appended Parasite");
    f.play(generatedId); f.finish();
    require(f.game.deck.cards[0].misc == 15, "generated kill grew the original Dagger");
    require(f.game.deck.cards[generatedId].id == CardId::PARASITE
            && f.game.deck.cards[generatedId].misc == 0,
            "generated Dagger aliased the Parasite appended before card transfer");
}

void staleCopy() {
    Fixture f(false);
    f.battle.monsters.arr[0].curHp = 16;
    f.battle.player.buff<PS::DOUBLE_TAP>(1);
    f.play(0);
    require(f.battle.curCardQueueItem.purgeOnUse, "stale-copy fixture did not use a copied card");
    auto &physical = f.battle.cards.exhaustPile.front();
    require(physical.uniqueId == 0 && physical.specialData == 18, "copied kill did not update physical Dagger");
    // Repeated copies may hold different ages of one physical identity. An
    // older queue view must not replace its already-grown permanent value.
    physical.specialData = 23;
    f.finish();
    require(f.game.deck.cards[0].misc == 23, "stale copied queue item overwrote newer physical growth");
}

void nonMasterQueueIdentity(int uniqueId) {
    Fixture f(false, MonsterEncounter::CULTIST, false, false);
    f.play(0);
    require(f.battle.outcome == Outcome::PLAYER_VICTORY, "identity fixture did not win");
    // Invalid/default history and mismatched master-card identities cannot
    // alias another card, even if the queue happens to name Ritual Dagger.
    f.battle.curCardQueueItem.card = CardInstance(Card(CardId::RITUAL_DAGGER));
    f.battle.curCardQueueItem.card.uniqueId = uniqueId;
    f.battle.curCardQueueItem.card.specialData = 99;
    f.finish();
    for (const auto &card : f.game.deck.cards)
        require(card.id == CardId::STRIKE_RED && card.misc == 0, "invalid queue identity aliased master deck");
}
}

int main() {
    int failures = 0;
    const auto run = [&](const std::string &label, const auto &test) {
        try { test(); std::cout << label << " PASS\n"; }
        catch (const std::exception &error) { ++failures; std::cerr << label << " FAIL: " << error.what() << '\n'; }
    };
    for (bool upgraded : {false, true}) {
        const std::string suffix = upgraded ? "+" : " base";
        run("final Cultist"+suffix, [&] { lethal(upgraded, MonsterEncounter::CULTIST); });
        run("final Writhing Mass"+suffix, [&] { lethal(upgraded, MonsterEncounter::WRITHING_MASS); });
        run("nonfinal Louse"+suffix, [&] { nonfinal(upgraded); });
        run("Double Tap copy"+suffix, [&] { copied(upgraded); });
    }
    run("generated Dagger", generated);
    run("generated Dagger after Implant", generatedAfterImplant);
    run("nonlethal Dagger", nonlethal);
    run("stale copied queue item", staleCopy);
    run("negative queue identity", [] { nonMasterQueueIdentity(-1); });
    run("mismatched master card type", [] { nonMasterQueueIdentity(0); });
    return failures ? 1 : 0;
}
