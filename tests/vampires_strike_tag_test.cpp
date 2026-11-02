// STS_VAMPIRES_STRIKE_TAG_FIX (default on): the Vampires event removes every
// STRIKE-tagged card (Twin Strike, Pommel Strike, Swift Strike, ...), as the
// game checks the STRIKE card tag; =0 restores the legacy removal of starter
// Strikes only. Also pins Deck::removeAllMatching's loop bound: it must not
// read the stale slot past the end of the deck. No game seed.
#include "game/GameContext.h"
#include "sim/search/GameAction.h"

#include <cstdlib>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

using namespace sts;
using namespace sts::search;

static void require(bool value, const std::string &message) {
    if (!value) throw std::runtime_error(message);
}

static void setFlag(const char *value) {
    if (value) setenv("STS_VAMPIRES_STRIKE_TAG_FIX", value, 1);
    else unsetenv("STS_VAMPIRES_STRIKE_TAG_FIX");
}

static GameContext fixture(const std::vector<Card> &cards) {
    GameContext gc{};
    gc.cc = CharacterClass::IRONCLAD;
    gc.act = 1;
    gc.floorNum = 2;
    gc.curHp = 40;
    gc.maxHp = 80;
    gc.gold = 123;
    gc.curRoom = Room::EVENT;
    gc.curEvent = Event::VAMPIRES;
    gc.screenState = ScreenState::EVENT_SCREEN;
    for (const auto card : cards) gc.deck.obtainRaw(card);
    gc.regainControlAction = [](GameContext &state) { state.screenState = ScreenState::MAP_SCREEN; };
    return gc;
}

static std::vector<Card> deck(const GameContext &gc) {
    return {gc.deck.cards.begin(), gc.deck.cards.end()};
}

static const std::vector<Card> START {
    Card(CardId::STRIKE_RED), Card(CardId::TWIN_STRIKE), Card(CardId::POMMEL_STRIKE, 1),
    Card(CardId::BASH), Card(CardId::STRIKE_RED), Card(CardId::DEFEND_RED), Card(CardId::SWIFT_STRIKE),
};

static std::vector<Card> expected(bool fixed) {
    std::vector<Card> result = fixed
        ? std::vector<Card>{Card(CardId::BASH), Card(CardId::DEFEND_RED)}
        : std::vector<Card>{Card(CardId::TWIN_STRIKE), Card(CardId::POMMEL_STRIKE, 1), Card(CardId::BASH),
                            Card(CardId::DEFEND_RED), Card(CardId::SWIFT_STRIKE)};
    for (int i = 0; i < 5; ++i) result.push_back(Card(CardId::BITE));
    return result;
}

static void check(bool fixed) {
    auto gc = fixture(START);
    require(!GameAction(0).isValidAction(gc) && GameAction(1).isValidAction(gc), "Vampires options without Blood Vial");
    GameAction(1).execute(gc);
    require(deck(gc) == expected(fixed), "Vampires (max HP) removal set");
    require(gc.maxHp == 56 && gc.curHp == 40, "Vampires max HP loss: " + std::to_string(gc.maxHp));
    require(gc.screenState == ScreenState::MAP_SCREEN && gc.gold == 123, "Vampires did not return control");

    auto vial = fixture(START);
    vial.relics.add({RelicId::BLOOD_VIAL, 0});
    require(GameAction(0).isValidAction(vial), "Blood Vial option missing");
    GameAction(0).execute(vial);
    require(deck(vial) == expected(fixed) && !vial.hasRelic(RelicId::BLOOD_VIAL) && vial.maxHp == 80,
            "Vampires (Blood Vial) removal set");

    auto leave = fixture(START);
    GameAction(2).execute(leave);
    require(deck(leave) == START && leave.maxHp == 80, "Leave changed the deck");
}

// The fixed list keeps a stale copy of a removed card past its end; the old
// loop started there and removing that index dropped the real last card.
static void staleSlot() {
    auto gc = fixture({Card(CardId::BASH), Card(CardId::STRIKE_RED)});
    gc.deck.remove(gc, 1);
    require(deck(gc) == std::vector<Card>{Card(CardId::BASH)}, "fixture removal");
    gc.deck.removeAllMatching(gc, [](const Card &card) { return card.isStarterStrike(); });
    require(deck(gc) == std::vector<Card>{Card(CardId::BASH)}, "removeAllMatching read the stale slot");
    auto empty = fixture({Card(CardId::STRIKE_RED)});
    empty.deck.remove(empty, 0);
    empty.deck.removeAllMatching(empty, [](const Card &) { return true; });
    require(empty.deck.size() == 0, "removeAllMatching on an empty deck");
}

int main() {
    try {
        staleSlot();
        setFlag(nullptr);
        check(true);
        setFlag("1");
        check(true);
        setFlag("0");
        check(false);
        setFlag("yes");
        bool rejected = false;
        try { auto gc = fixture(START); GameAction(1).execute(gc); }
        catch (const std::runtime_error &) { rejected = true; }
        require(rejected, "malformed flag accepted");
        setFlag(nullptr);
        std::cout << "vampires_strike_tag: OK\n";
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "vampires_strike_tag: FAIL: " << e.what() << '\n';
        return 1;
    }
}
