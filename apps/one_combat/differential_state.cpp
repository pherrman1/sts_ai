#include "differential_state.h"

#include "combat/BattleContext.h"
#include "sim/search/SilverWireJson.h"

namespace one_combat::differential {
namespace {
using J = nlohmann::json;
using namespace sts;

J card(const Card &c, int bottle = -1) {
    return {{"id", static_cast<int>(c.id)}, {"upgraded", c.upgraded},
            {"misc", c.misc}, {"bottleBinding", bottle}};
}

J random(const Random &r) {
    return {{"counter", r.counter}, {"seed0", std::to_string(r.seed0)},
            {"seed1", std::to_string(r.seed1)}};
}

J map(const GameContext &gc) {
    if (!gc.map) return nullptr;
    J nodes = J::array();
    for (int y = 0; y < 15; ++y) for (int x = 0; x < 7; ++x) {
        const auto &n = gc.map->nodes[y][x];
        J edges = J::array();
        for (int i = 0; i < n.edgeCount; ++i) edges.push_back(n.edges[i]);
        nodes.push_back({{"x", x}, {"y", y}, {"room", static_cast<int>(n.room)},
                         {"edges", std::move(edges)}});
    }
    return {{"x", gc.curMapNodeX}, {"y", gc.curMapNodeY},
            {"burningEliteX", gc.map->burningEliteX},
            {"burningEliteY", gc.map->burningEliteY}, {"nodes", std::move(nodes)}};
}

J details(const GameContext &gc) {
    // ScreenStateInfo retains data from earlier screens. Only fields imported
    // from the currently visible screen can be compared with a fresh capture.
    J out = J::object();
    if (gc.screenState == ScreenState::CARD_SELECT) {
        out["selectScreenType"] = static_cast<int>(gc.info.selectScreenType);
        out["toSelectCount"] = gc.info.toSelectCount;
        J select = J::array();
        for (const auto &v : gc.info.toSelectCards)
            select.push_back({{"deckIndex", v.deckIdx}, {"card", card(v.card)}});
        out["toSelectCards"] = std::move(select);
    }
    if (gc.screenState == ScreenState::REWARDS) {
        const auto &r = gc.info.rewardsContainer;
        J rewards = {{"gold", J::array()}, {"cards", J::array()}, {"relics", J::array()},
                     {"potions", J::array()}, {"emeraldKey", r.emeraldKey},
                     {"sapphireKey", r.sapphireKey}};
        for (int i = 0; i < r.goldRewardCount; ++i) rewards["gold"].push_back(r.gold[i]);
        for (int i = 0; i < r.cardRewardCount; ++i) {
            J group = J::array(); for (const auto &c : r.cardRewards[i]) group.push_back(card(c));
            rewards["cards"].push_back(std::move(group));
        }
        for (int i = 0; i < r.relicCount; ++i) rewards["relics"].push_back(static_cast<int>(r.relics[i]));
        for (int i = 0; i < r.potionCount; ++i) rewards["potions"].push_back(static_cast<int>(r.potions[i]));
        out["rewards"] = std::move(rewards);
    }
    if (gc.screenState == ScreenState::SHOP_ROOM) {
        J shop = {{"cards", J::array()}, {"relics", J::array()}, {"potions", J::array()},
                  {"removeCost", gc.info.shop.removeCost}};
        for (int i = 0; i < 7; ++i) {
            const int price = gc.info.shop.cardPrice(i);
            shop["cards"].push_back({{"card", price < 0 ? J(nullptr) : card(gc.info.shop.cards[i])},
                                      {"price", price}});
        }
        for (int i = 0; i < 3; ++i) {
            const int relicPrice = gc.info.shop.relicPrice(i);
            const int potionPrice = gc.info.shop.potionPrice(i);
            shop["relics"].push_back({{"id", relicPrice < 0 ? J(nullptr) : J(static_cast<int>(gc.info.shop.relics[i]))},
                                       {"price", relicPrice}});
            shop["potions"].push_back({{"id", potionPrice < 0 ? J(nullptr) : J(static_cast<int>(gc.info.shop.potions[i]))},
                                        {"price", potionPrice}});
        }
        out["shop"] = std::move(shop);
    }
    if (gc.screenState == ScreenState::BOSS_RELIC_REWARDS) {
        J boss = J::array(); for (auto id : gc.info.bossRelics) boss.push_back(static_cast<int>(id));
        out["bossRelics"] = std::move(boss);
    }
    if (gc.screenState == ScreenState::EVENT_SCREEN) {
        // Other event fields in the live import are fixed placeholders, not
        // observed public state.
        out["event"] = static_cast<int>(gc.curEvent);
        if (gc.curEvent == Event::NEOW) {
            J neow = J::array();
            for (const auto &v : gc.info.neowRewards) {
                if (v.r == Neow::Bonus::INVALID) continue;
                neow.push_back({{"bonus", static_cast<int>(v.r)}, {"drawback", static_cast<int>(v.d)}});
            }
            out["neow"] = std::move(neow);
        }
    }
    return out;
}
}

J canonicalCombatState(silver_bridge::BattleStateWire wire) {
    // These are observer/session bookkeeping, not simulator semantics.
    wire.isolatedSearchSeed = 0;
    wire.observedGeneration = 0;
    return {{"schema", "sts_differential_combat_v1"}, {"state", wire}};
}

J canonicalOocState(const GameContext &gc, const PathHistory &path) {
    J deck = J::array();
    for (int i = 0; i < gc.deck.size(); ++i) {
        int bottle = -1;
        for (int b = 0; b < 3; ++b) if (gc.deck.bottleIdxs[b] == i) bottle = b;
        deck.push_back(card(gc.deck.cards[i], bottle));
    }
    J relics = J::array();
    for (const auto &r : gc.relics.relics)
        relics.push_back({{"id", static_cast<int>(r.id)}, {"data", r.data}});
    J potions = J::array(); for (auto p : gc.potions) potions.push_back(static_cast<int>(p));
    J result = {{"schema", "sts_differential_ooc_v1"},
            {"character", static_cast<int>(gc.cc)}, {"ascension", gc.ascension},
            {"act", gc.act}, {"floor", gc.floorNum}, {"screen", static_cast<int>(gc.screenState)},
            {"hp", gc.curHp}, {"maxHp", gc.maxHp}, {"gold", gc.gold},
            {"keys", {gc.blueKey, gc.greenKey, gc.redKey}},
            {"potionCapacity", gc.potionCapacity}, {"potions", std::move(potions)},
            {"deck", std::move(deck)}, {"relics", std::move(relics)}, {"map", map(gc)},
            {"pathVisits", path.roomVisits}, {"details", details(gc)}};
    // Preserve byte-identical identities/seeds for states without the relic.
    if (gc.hasRelic(RelicId::WING_BOOTS)) result["wingBootsCharges"] = gc.wingBootsCharges;
    return result;
}

J gameRng(const GameContext &gc, const BattleContext *battle) {
    const auto &ai = battle ? battle->aiRng : gc.aiRng;
    const auto &cardRandom = battle ? battle->cardRandomRng : gc.cardRandomRng;
    const auto &misc = battle ? battle->miscRng : gc.miscRng;
    const auto &monsterHp = battle ? battle->monsterHpRng : gc.monsterHpRng;
    const auto &potion = battle ? battle->potionRng : gc.potionRng;
    const auto &shuffle = battle ? battle->shuffleRng : gc.shuffleRng;
    return {{"schema", "sts_java_rng_v1"}, {"available", true}, {"streams", {
        {"aiRng", random(ai)}, {"cardRandomRng", random(cardRandom)},
        {"cardRng", random(gc.cardRng)}, {"eventRng", random(gc.eventRng)},
        {"merchantRng", random(gc.merchantRng)}, {"miscRng", random(misc)},
        {"monsterHpRng", random(monsterHp)}, {"monsterRng", random(gc.monsterRng)},
        {"potionRng", random(potion)}, {"relicRng", random(gc.relicRng)},
        {"shuffleRng", random(shuffle)}, {"treasureRng", random(gc.treasureRng)}}}};
}
}
