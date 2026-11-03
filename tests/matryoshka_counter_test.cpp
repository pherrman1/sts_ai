// STS_MATRYOSHKA_COUNTER_FIX (default on): obtaining Matryoshka sets its
// counter to 2, so the next two non-boss chests add a second relic drawn from
// the Matryoshka tier roll; =0 restores the legacy counter 0, which never
// added a relic. Direct public fixtures: no game seed, map or fight.
#include "game/GameContext.h"
#include "game/Game.h"

#include <cstdlib>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

using namespace sts;

static void require(bool value, const std::string &message) {
    if (!value) throw std::runtime_error(message);
}

static void setFlag(const char *value) {
    if (value) setenv("STS_MATRYOSHKA_COUNTER_FIX", value, 1);
    else unsetenv("STS_MATRYOSHKA_COUNTER_FIX");
}

static GameContext fixture() {
    GameContext gc{};
    gc.cc = CharacterClass::IRONCLAD;
    gc.act = 1;
    gc.floorNum = 2;
    gc.curHp = 40;
    gc.maxHp = 80;
    gc.gold = 123;
    gc.curRoom = Room::TREASURE;
    gc.info.tier = RelicTier::COMMON;
    gc.info.haveGold = false;
    gc.info.chestSize = ChestSize::SMALL;
    gc.commonRelicPool = {RelicId::ANCHOR, RelicId::LANTERN, RelicId::VAJRA,
                          RelicId::BAG_OF_MARBLES, RelicId::ODDLY_SMOOTH_STONE};
    gc.uncommonRelicPool = {RelicId::BLUE_CANDLE, RelicId::GREMLIN_HORN, RelicId::PEN_NIB};
    gc.rareRelicPool = {RelicId::TUNGSTEN_ROD, RelicId::GINGER};
    gc.relicRng = Random(7);
    gc.regainControlAction = [](GameContext &state) { state.screenState = ScreenState::MAP_SCREEN; };
    return gc;
}

static int poolSize(const GameContext &gc) {
    return int(gc.commonRelicPool.size() + gc.uncommonRelicPool.size() + gc.rareRelicPool.size());
}

static void check(bool fixed) {
    auto gc = fixture();
    require(!gc.obtainRelic(RelicId::MATRYOSHKA), "Matryoshka opened a screen");
    require(gc.relics.getRelicValue(RelicId::MATRYOSHKA) == (fixed ? 2 : 0), "initial counter");
    require(gc.gold == 123 && gc.curHp == 40 && gc.maxHp == 80, "Matryoshka changed resources");

    for (int chest = 1; chest <= 3; ++chest) {
        const bool extra = fixed && chest <= 2;
        const int before = poolSize(gc);
        Random expectedRng = gc.relicRng;
        RelicId expectedExtra = RelicId::INVALID;
        if (extra) {
            // The tier roll is the only RNG the extra relic consumes; the
            // relic itself is the front of that tier's pre-shuffled pool.
            const auto tier = getMatryoshkaRelicTier(expectedRng);
            expectedExtra = tier == RelicTier::COMMON ? gc.commonRelicPool.front() : gc.uncommonRelicPool.front();
        }
        gc.openTreasureRoomChest();
        const auto &rewards = gc.info.rewardsContainer;
        require(gc.screenState == ScreenState::REWARDS, "chest did not open rewards");
        require(rewards.relicCount == (extra ? 2 : 1), "chest " + std::to_string(chest) + " relic count");
        if (extra) require(rewards.relics[0] == expectedExtra, "extra relic is not the tier-pool front");
        require(rewards.relics[extra ? 1 : 0] != RelicId::INVALID, "chest relic missing");
        require(gc.relicRng == expectedRng, "chest " + std::to_string(chest) + " relicRng consumption");
        require(before - poolSize(gc) == (extra ? 2 : 1), "pool consumption differs from relics granted");
        require(gc.relics.getRelicValue(RelicId::MATRYOSHKA) == (fixed ? std::max(0, 2 - chest) : 0),
                "counter after chest " + std::to_string(chest));
        require(rewards.goldRewardCount == 0, "no-gold chest added gold");
    }
}

int main() {
    try {
        setFlag(nullptr);
        check(true);
        setFlag("1");
        check(true);
        setFlag("0");
        check(false);
        setFlag("2");
        bool rejected = false;
        try { auto gc = fixture(); gc.obtainRelic(RelicId::MATRYOSHKA); }
        catch (const std::runtime_error &) { rejected = true; }
        require(rejected, "malformed flag accepted");
        setFlag(nullptr);
        std::cout << "matryoshka_counter: OK\n";
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "matryoshka_counter: FAIL: " << e.what() << '\n';
        return 1;
    }
}
