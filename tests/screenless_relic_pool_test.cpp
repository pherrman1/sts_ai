// returnRandomScreenlessRelic contract (reviewed 2026-11-02, no flag): event
// relics and Calling Bell draw with returnRandomRelic until the relic is not
// Bottled Flame/Lightning/Tornado or Whetstone, and the skipped relics stay
// out of the pool, as Java AbstractDungeon.returnRandomScreenlessRelic does
// (recalled, not re-read from bytecode). The plain draw does not skip them.
// No game seed: pools are set directly.
#include "game/GameContext.h"

#include <cstdlib>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

using namespace sts;

static void require(bool value, const std::string &message) {
    if (!value) throw std::runtime_error(message);
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
    // Non-basic attack, skill and power so every Bottled relic can spawn and
    // the screenless loop, not relicCanSpawn's back-of-pool fallback, skips it.
    gc.deck.obtainRaw(Card(CardId::CLEAVE));
    gc.deck.obtainRaw(Card(CardId::SHRUG_IT_OFF));
    gc.deck.obtainRaw(Card(CardId::INFLAME));
    gc.relicRng = Random(3);
    gc.commonRelicPool = {RelicId::WHETSTONE, RelicId::BOTTLED_FLAME, RelicId::ANCHOR, RelicId::LANTERN};
    gc.uncommonRelicPool = {RelicId::BOTTLED_LIGHTNING, RelicId::BOTTLED_TORNADO, RelicId::BLUE_CANDLE,
                            RelicId::GREMLIN_HORN};
    gc.rareRelicPool = {RelicId::BOTTLED_TORNADO, RelicId::TUNGSTEN_ROD, RelicId::GINGER};
    gc.regainControlAction = [](GameContext &state) { state.screenState = ScreenState::MAP_SCREEN; };
    return gc;
}

int main() {
    try {
        auto gc = fixture();
        const auto rng = gc.relicRng;
        require(gc.returnRandomScreenlessRelic(RelicTier::COMMON) == RelicId::ANCHOR, "common screenless draw");
        require(gc.commonRelicPool == std::vector<RelicId>{RelicId::LANTERN},
                "skipped common relics must leave the pool");
        require(gc.returnRandomScreenlessRelic(RelicTier::UNCOMMON) == RelicId::BLUE_CANDLE, "uncommon screenless draw");
        require(gc.uncommonRelicPool == std::vector<RelicId>{RelicId::GREMLIN_HORN},
                "skipped uncommon relics must leave the pool");
        require(gc.returnRandomScreenlessRelic(RelicTier::RARE) == RelicId::TUNGSTEN_ROD, "rare screenless draw");
        require(gc.rareRelicPool == std::vector<RelicId>{RelicId::GINGER}, "skipped rare relic must leave the pool");
        require(gc.relicRng == rng, "pool draws must not consume relicRng");
        // Later draws see the shifted pool: the next common relic is Lantern.
        require(gc.returnRandomRelic(RelicTier::COMMON) == RelicId::LANTERN && gc.commonRelicPool.empty(),
                "later plain draw");

        auto plain = fixture();
        require(plain.returnRandomRelic(RelicTier::COMMON) == RelicId::WHETSTONE
                && plain.returnRandomRelic(RelicTier::COMMON) == RelicId::BOTTLED_FLAME,
                "the plain draw must still grant screen relics (chests, elites)");

        // Calling Bell draws its three relics screenlessly.
        setenv("STS_CALLING_BELL_CARD_RNG_FIX", "0", 1);
        auto bell = fixture();
        require(bell.obtainRelic(RelicId::CALLING_BELL), "Calling Bell did not open rewards");
        const auto &rewards = bell.info.rewardsContainer;
        require(rewards.relicCount == 3 && rewards.relics[0] == RelicId::ANCHOR
                && rewards.relics[1] == RelicId::BLUE_CANDLE && rewards.relics[2] == RelicId::TUNGSTEN_ROD,
                "Calling Bell relics");
        require(bell.commonRelicPool == std::vector<RelicId>{RelicId::LANTERN}
                && bell.uncommonRelicPool == std::vector<RelicId>{RelicId::GREMLIN_HORN}
                && bell.rareRelicPool == std::vector<RelicId>{RelicId::GINGER}, "Calling Bell pools");
        require(bell.deck.size() == 4 && bell.deck.cards[3] == Card(CardId::CURSE_OF_THE_BELL), "Curse of the Bell");
        unsetenv("STS_CALLING_BELL_CARD_RNG_FIX");
        std::cout << "screenless_relic_pool: OK\n";
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "screenless_relic_pool: FAIL: " << e.what() << '\n';
        return 1;
    }
}
