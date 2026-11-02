// STS_GOLD_REWARD_IDOL_FIX (default on): Golden Idol adds round(25%) to every
// non-stolen gold reward item, as Java RewardItem(int gold) does: chest gold,
// Tiny House and the event fights (Dead Adventurer, Masked Bandits, Mind
// Bloom, Mushrooms, Mysterious Sphere); =0 restores the legacy bonus on
// ordinary combat rewards only. RNG is read from copies, so the expected
// base amounts come from the same rolls. No game seed, map or fight.
#include "game/GameContext.h"
#include "sim/search/GameAction.h"

#include <cmath>
#include <cstdlib>
#include <iostream>
#include <stdexcept>
#include <string>

using namespace sts;
using namespace sts::search;

static void require(bool value, const std::string &message) {
    if (!value) throw std::runtime_error(message);
}

static void setFlag(const char *value) {
    if (value) setenv("STS_GOLD_REWARD_IDOL_FIX", value, 1);
    else unsetenv("STS_GOLD_REWARD_IDOL_FIX");
}

static int idol(int base) {
    return base + static_cast<int>(std::round(static_cast<float>(base) * 0.25f));
}

static GameContext fixture(bool goldenIdol = true) {
    GameContext gc{};
    gc.cc = CharacterClass::IRONCLAD;
    gc.act = 1;
    gc.ascension = 0;
    gc.floorNum = 2;
    gc.curHp = 40;
    gc.maxHp = 80;
    gc.gold = 123;
    gc.curRoom = Room::EVENT;
    gc.screenState = ScreenState::EVENT_SCREEN;
    gc.deck.obtainRaw(Card(CardId::STRIKE_RED));
    gc.deck.obtainRaw(Card(CardId::BASH));
    gc.rareRelicPool = {RelicId::TUNGSTEN_ROD, RelicId::GINGER};
    gc.commonRelicPool = {RelicId::ANCHOR, RelicId::LANTERN};
    gc.uncommonRelicPool = {RelicId::BLUE_CANDLE};
    gc.treasureRng = Random(3);
    gc.miscRng = Random(11);
    if (goldenIdol) gc.relics.add({RelicId::GOLDEN_IDOL, 0});
    gc.regainControlAction = [](GameContext &state) { state.screenState = ScreenState::MAP_SCREEN; };
    return gc;
}

static int rewardGold(const GameContext &gc, const char *what) {
    require(gc.screenState == ScreenState::REWARDS, std::string(what) + ": no reward screen");
    require(gc.info.rewardsContainer.goldRewardCount == 1, std::string(what) + ": gold reward count");
    return gc.info.rewardsContainer.gold[0];
}

static void expectGold(const GameContext &gc, int base, bool fixed, const char *what) {
    const int got = rewardGold(gc, what);
    const int want = fixed ? idol(base) : base;
    require(got == want, std::string(what) + ": got " + std::to_string(got) + " want " + std::to_string(want));
}

// Runs the fight event option and its post-combat reward continuation.
static void fightEvent(GameContext &gc, Event event, int option, const char *what) {
    gc.curEvent = event;
    require(GameAction(option).isValidAction(gc), std::string(what) + ": option not legal");
    GameAction(option).execute(gc);
    require(gc.screenState == ScreenState::BATTLE, std::string(what) + ": no fight");
    gc.regainControlAction(gc);
}

static void check(bool fixed) {
    { // chest gold
        auto gc = fixture();
        gc.curRoom = Room::TREASURE;
        gc.info.tier = RelicTier::COMMON;
        gc.info.haveGold = true;
        gc.info.chestSize = ChestSize::SMALL;
        Random copy = gc.treasureRng;
        const int base = static_cast<int>(std::round(copy.random(25 * 0.9f, 25 * 1.1f)));
        gc.openTreasureRoomChest();
        expectGold(gc, base, fixed, "chest");
        require(gc.treasureRng == copy, "chest consumed extra treasureRng");

        auto plain = fixture(false);
        plain.curRoom = Room::TREASURE;
        plain.info.tier = RelicTier::COMMON;
        plain.info.haveGold = true;
        plain.info.chestSize = ChestSize::SMALL;
        plain.openTreasureRoomChest();
        require(rewardGold(plain, "chest without idol") == base, "chest gold without Golden Idol changed");
    }
    { // Tiny House
        auto gc = fixture();
        require(gc.obtainRelic(RelicId::TINY_HOUSE), "Tiny House did not open rewards");
        expectGold(gc, 50, fixed, "Tiny House");
        require(gc.maxHp == 85, "Tiny House max HP");
    }
    { // Mysterious Sphere: gold is fixed when the fight is chosen, bonus at the reward.
        auto gc = fixture();
        gc.curEvent = Event::MYSTERIOUS_SPHERE;
        gc.info.gold = 50;
        gc.info.bossRelics[0] = RelicId::ANCHOR;
        gc.afterBattle();
        expectGold(gc, 50, fixed, "Mysterious Sphere");
        require(gc.info.rewardsContainer.relics[0] == RelicId::ANCHOR, "Mysterious Sphere relic");
    }
    { // Masked Bandits: Fight
        auto gc = fixture();
        Random copy = gc.miscRng;
        const int base = copy.random(25, 35);
        fightEvent(gc, Event::MASKED_BANDITS, 1, "Masked Bandits");
        expectGold(gc, base, fixed, "Masked Bandits");
        require(gc.info.rewardsContainer.relics[0] == RelicId::RED_MASK, "Masked Bandits relic");
    }
    { // Hypnotizing Colored Mushrooms: Stomp
        auto gc = fixture();
        Random copy = gc.miscRng;
        const int base = copy.random(20, 30);
        fightEvent(gc, Event::HYPNOTIZING_COLORED_MUSHROOMS, 0, "Mushrooms");
        expectGold(gc, base, fixed, "Mushrooms");
    }
    { // Mind Bloom: I am War (50 gold below A15)
        auto gc = fixture();
        fightEvent(gc, Event::MINDBLOOM, 0, "Mind Bloom");
        expectGold(gc, 50, fixed, "Mind Bloom");
    }
    { // Dead Adventurer: phase 2 (75% encounter), one unfound gold reward (+30)
        auto gc = fixture();
        gc.info.phase = 2;
        gc.info.rewards = {0, 0, 0};
        int seed = 1;
        for (;; ++seed) { Random probe(seed); if (probe.random(99) < 75) break; }
        gc.miscRng = Random(seed);
        Random copy = gc.miscRng;
        copy.random(99);
        const int base = copy.random(25, 35) + 30;
        fightEvent(gc, Event::DEAD_ADVENTURER, 0, "Dead Adventurer");
        expectGold(gc, base, fixed, "Dead Adventurer");
        require(gc.info.rewardsContainer.relicCount == 0, "Dead Adventurer gold-only rewards added a relic");
    }
    { // Ordinary combat reward: unchanged by the flag.
        auto gc = fixture();
        Random copy = gc.treasureRng;
        const int base = copy.random(10, 20);
        const auto reward = gc.createCombatReward();
        require(reward.gold[0] == idol(base), "ordinary combat reward bonus changed");
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
        setFlag("on");
        bool rejected = false;
        try { auto gc = fixture(); gc.obtainRelic(RelicId::TINY_HOUSE); }
        catch (const std::runtime_error &) { rejected = true; }
        require(rejected, "malformed flag accepted");
        setFlag(nullptr);
        std::cout << "gold_reward_idol: OK\n";
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "gold_reward_idol: FAIL: " << e.what() << '\n';
        return 1;
    }
}
