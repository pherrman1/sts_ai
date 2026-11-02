// STS_OLD_COIN_GOLD_FIX (default on): obtaining Old Coin gains 300 gold
// through the ordinary gold gain (Ectoplasm blocks it, Bloody Idol heals 5);
// =0 restores the legacy pickup, which granted nothing. No game seed.
#include "game/GameContext.h"

#include <cstdlib>
#include <iostream>
#include <stdexcept>
#include <string>

using namespace sts;

static void require(bool value, const std::string &message) {
    if (!value) throw std::runtime_error(message);
}

static void setFlag(const char *value) {
    if (value) setenv("STS_OLD_COIN_GOLD_FIX", value, 1);
    else unsetenv("STS_OLD_COIN_GOLD_FIX");
}

static GameContext fixture() {
    GameContext gc{};
    gc.cc = CharacterClass::IRONCLAD;
    gc.act = 1;
    gc.floorNum = 2;
    gc.curHp = 40;
    gc.maxHp = 80;
    gc.gold = 123;
    gc.curRoom = Room::EVENT;
    gc.regainControlAction = [](GameContext &state) { state.screenState = ScreenState::MAP_SCREEN; };
    return gc;
}

static void check(bool fixed) {
    auto gc = fixture();
    require(!gc.obtainRelic(RelicId::OLD_COIN), "Old Coin opened a screen");
    require(gc.hasRelic(RelicId::OLD_COIN), "Old Coin not owned");
    require(gc.gold == (fixed ? 423 : 123), "Old Coin gold: " + std::to_string(gc.gold));
    require(gc.curHp == 40 && gc.maxHp == 80, "Old Coin changed HP");

    auto blocked = fixture();
    blocked.obtainRelic(RelicId::ECTOPLASM);
    blocked.obtainRelic(RelicId::OLD_COIN);
    require(blocked.gold == 123, "Ectoplasm did not block Old Coin");

    auto idol = fixture();
    idol.obtainRelic(RelicId::BLOODY_IDOL);
    idol.obtainRelic(RelicId::OLD_COIN);
    require(idol.gold == (fixed ? 423 : 123) && idol.curHp == (fixed ? 45 : 40),
            "Bloody Idol on Old Coin gold");
}

int main() {
    try {
        setFlag(nullptr);
        check(true);
        setFlag("1");
        check(true);
        setFlag("0");
        check(false);
        setFlag("x");
        bool rejected = false;
        try { auto gc = fixture(); gc.obtainRelic(RelicId::OLD_COIN); }
        catch (const std::runtime_error &) { rejected = true; }
        require(rejected, "malformed flag accepted");
        setFlag(nullptr);
        std::cout << "old_coin_gold: OK\n";
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "old_coin_gold: FAIL: " << e.what() << '\n';
        return 1;
    }
}
