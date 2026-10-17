#include "screen_leaf_continuations.h"
#include "screen_leaf_snapshot.h"
#include "constants/CardPools.h"
#include "game/Game.h"
#include <cstdlib>
#include <iostream>
#include <limits>
#include <vector>

using namespace sts;
using namespace one_combat::screen_leaf;
namespace {
void check(bool ok, const std::string &message) {
    if (!ok) throw std::runtime_error(message);
}
template<class F> void rejects(F &&f) {
    bool rejected = false;
    try { f(); } catch (const std::exception &) { rejected = true; }
    check(rejected, "malformed continuation accepted");
}
const GameContextAction toMap = [](GameContext &gc) {
    gc.screenState = ScreenState::MAP_SCREEN; gc.regainControlAction = nullptr;
};
const GameContextAction setMap = [](GameContext &gc) { gc.screenState = ScreenState::MAP_SCREEN; };

GameContext fixture() {
    // Synthetic state, not a seeded GameContext constructor or gameplay run.
    GameContext gc{};
    gc.info.neowRewards = {};
    gc.cc = CharacterClass::IRONCLAD;
    gc.seed = 31;
    gc.map = std::make_shared<Map>();
    gc.act = 1; gc.ascension = 0; gc.floorNum = 8;
    gc.curHp = 53; gc.maxHp = 80; gc.gold = 73;
    gc.potionCapacity = 3; gc.curRoom = Room::MONSTER;
    gc.screenState = ScreenState::CARD_SELECT;
    gc.deck.obtain(gc, Card(CardId::BASH));
    gc.deck.obtain(gc, Card(CardId::FEED));
    // Face of Cleric checks that event fight continuations run combat-end relics.
    gc.relics.add({RelicId::FACE_OF_CLERIC, 0});
    gc.commonRelicPool = {RelicId::ANCHOR, RelicId::BAG_OF_MARBLES, RelicId::BLOOD_VIAL};
    gc.uncommonRelicPool = {RelicId::KUNAI, RelicId::SHURIKEN, RelicId::MEAT_ON_THE_BONE};
    gc.rareRelicPool = {RelicId::CALIPERS, RelicId::GINGER, RelicId::TORII};
    gc.bossRelicPool = {RelicId::BLACK_STAR, RelicId::COFFEE_DRIPPER, RelicId::ECTOPLASM,
                       RelicId::RUNIC_PYRAMID};
    return gc;
}

Json comparable(GameContext gc) {
    // Current-main methods install ordinary (untagged) callbacks. Compare their
    // effects separately by executing subsequent continuations below.
    gc.regainControlAction = nullptr;
    return snapshotJson(gc, one_combat::PathHistory{}, OocPolicyThreadState{});
}

void compare(const Json &descriptor, const GameContextAction &expected, bool extraRelics = false) {
    std::cerr << "checking " << descriptor.at("kind") << "\n";
    auto left = fixture(), right = fixture();
    if (extraRelics) {
        left.relics.add({RelicId::RED_MASK, 0}); right.relics.add({RelicId::RED_MASK, 0});
        left.relics.add({RelicId::BLACK_STAR, 0}); right.relics.add({RelicId::BLACK_STAR, 0});
    }
    left.regainControlAction = importContinuation(descriptor);
    check(continuationDescriptor(left.regainControlAction) == descriptor, "descriptor roundtrip");
    right.regainControlAction = expected;
    for (int step = 0; step < 3; ++step) {
        check(bool(left.regainControlAction) == bool(right.regainControlAction), "callback presence differs");
        if (!left.regainControlAction) break;
        // Preserve captures when the callback replaces itself.
        const auto rightAction = right.regainControlAction;
        left.regainControlAction(left);
        rightAction(right);
        const auto l = comparable(left), r = comparable(right);
        check(l == r, descriptor.at("kind").get<std::string>() + " state/RNG differs at step "
                    + std::to_string(step) + ": " + Json::diff(l, r).dump());
        check(bool(left.regainControlAction) == bool(right.regainControlAction), "result callback presence differs");
        if (left.screenState == ScreenState::MAP_SCREEN) break;
    }
}
}

int main() {
    try {
        compare({{"kind", "return_to_map"}}, toMap);
        compare({{"kind", "set_map"}}, setMap);
        compare({{"kind", "after_battle"}}, [](auto &gc) { gc.afterBattle(); });
        compare({{"kind", "next_captured_act"}, {"act", 1}}, [](auto &gc) { gc.transitionToAct(2); });
        compare({{"kind", "next_current_act"}}, [](auto &gc) { gc.transitionToAct(gc.act + 1); });
        compare({{"kind", "boss_treasure"}}, [](auto &gc) { gc.enterBossTreasureRoom(); });
        compare({{"kind", "neow_curse"}}, [](auto &gc) {
            const int roll = gc.cardRng.random(static_cast<int>(9));
            gc.deck.obtain(gc, curseCardPool[roll]);
            gc.screenState = ScreenState::MAP_SCREEN; gc.regainControlAction = toMap;
        });
        compare({{"kind", "colosseum_first"}}, [](auto &gc) {
            gc.relicsOnCombatEnd(); gc.screenState = ScreenState::EVENT_SCREEN; gc.regainControlAction = toMap;
        });
        compare({{"kind", "designer_upgrade"}}, [](auto &gc) {
            gc.deck.upgradeRandomCards(gc.miscRng, 1); toMap(gc);
        });
        compare({{"kind", "shop_relic_return"}}, [](auto &gc) {
            gc.screenState = ScreenState::SHOP_ROOM; gc.regainControlAction = setMap;
        });
        compare({{"kind", "shop_remove_return"}, {"previous", {{"kind", "return_to_map"}}}},
            [](auto &gc) { gc.screenState = ScreenState::SHOP_ROOM; gc.regainControlAction = toMap; });
        Rewards remainder; remainder.addGold(11); remainder.addRelic(RelicId::ANCHOR);
        compare({{"kind", "remaining_rewards"}, {"rewards", rewardsJson(remainder)},
                 {"previous", {{"kind", "shop_remove_return"}, {"previous", {{"kind", "return_to_map"}}}}}},
            [remainder](auto &gc) {
                gc.openCombatRewardScreen(remainder);
                gc.regainControlAction = [](auto &g) {
                    g.screenState = ScreenState::SHOP_ROOM; g.regainControlAction = toMap;
                };
            });
        compare({{"kind", "colosseum_rewards"}, {"gold", 125}, {"rare", int(RelicId::GINGER)},
                 {"uncommon", int(RelicId::KUNAI)}}, [](auto &gc) {
            gc.relicsOnCombatEnd(); Rewards r; r.addGold(125); r.addRelic(RelicId::GINGER); r.addRelic(RelicId::KUNAI);
            gc.addPotionRewards(r); r.addCardReward(gc.createCardReward(Room::EVENT));
            gc.openCombatRewardScreen(r); gc.regainControlAction = toMap;
        });
        // Black Star adds a Dead Adventurer relic only under STS_ENGINE_FIDELITY_FIX=0.
        for (bool legacy : {false, true}) {
            if (legacy) setenv("STS_ENGINE_FIDELITY_FIX", "0", 1); else unsetenv("STS_ENGINE_FIDELITY_FIX");
            for (bool add : {false, true}) {
                compare({{"kind", "dead_adventurer_rewards"}, {"gold", 31}, {"addRelic", add},
                         {"relic", int(add ? RelicId::ANCHOR : RelicId::INVALID)}}, [add, legacy](auto &gc) {
                    gc.relicsOnCombatEnd(); Rewards r; r.addGold(31); if (add) r.addRelic(RelicId::ANCHOR);
                    if (legacy && gc.hasRelic(RelicId::BLACK_STAR))
                        r.addRelic(gc.returnNonCampfireRelic(returnRandomRelicTierElite(gc.relicRng)));
                    r.addCardReward(gc.createCardReward(Room::EVENT)); gc.addPotionRewards(r);
                    gc.openCombatRewardScreen(r); gc.regainControlAction = toMap;
                }, true);
            }
        }
        unsetenv("STS_ENGINE_FIDELITY_FIX");
        for (bool duplicateMask : {false, true}) {
            compare({{"kind", "masked_bandits_rewards"}, {"gold", 29}}, [](auto &gc) {
                gc.relicsOnCombatEnd(); Rewards r; r.addGold(29);
                r.addRelic(gc.hasRelic(RelicId::RED_MASK) ? RelicId::CIRCLET : RelicId::RED_MASK);
                gc.addPotionRewards(r); r.addCardReward(gc.createCardReward(Room::EVENT));
                gc.openCombatRewardScreen(r); gc.regainControlAction = toMap;
            }, duplicateMask);
        }
        compare({{"kind", "mind_bloom_rewards"}, {"gold", 50}, {"rare", int(RelicId::GINGER)}}, [](auto &gc) {
            gc.relicsOnCombatEnd(); Rewards r; r.addGold(50); r.addRelic(RelicId::GINGER); gc.addPotionRewards(r);
            r.addCardReward(gc.createCardReward(Room::EVENT));
            gc.openCombatRewardScreen(r); gc.regainControlAction = toMap;
        });
        compare({{"kind", "mushroom_rewards"}, {"gold", 24}}, [](auto &gc) {
            gc.relicsOnCombatEnd(); Rewards r; r.addGold(24); r.addRelic(RelicId::ODD_MUSHROOM); gc.addPotionRewards(r);
            r.addCardReward(gc.createCardReward(Room::EVENT));
            gc.openCombatRewardScreen(r); gc.regainControlAction = toMap;
        });
        check(!importContinuation(nullptr), "null continuation changed");
        rejects([] { importContinuation({{"kind", "unknown"}}); });
        rejects([] { importContinuation({{"kind", "return_to_map"}, {"extra", 1}}); });
        rejects([] { importContinuation({{"kind", "next_captured_act"}, {"act", 0}}); });
        rejects([] { importContinuation({{"kind", "next_captured_act"}, {"act", 1.0}}); });
        rejects([] { importContinuation({{"kind", "next_captured_act"}, {"act", UINT64_MAX}}); });
        rejects([] { importContinuation({{"kind", "mind_bloom_rewards"}, {"gold", 1}, {"rare", -1}}); });
        rejects([] { importContinuation({{"kind", "shop_remove_return"}, {"previous", {{"kind", "unknown"}}}}); });
        rejects([] { continuationDescriptor(toMap); });
        Json deep = nullptr;
        for (int i = 0; i < 66; ++i) deep = {{"kind", "shop_remove_return"}, {"previous", deep}};
        rejects([&] { importContinuation(deep); });
        std::cout << "screen leaf continuations PASS: 17 kinds, nested callbacks, current reward semantics, malformed rejection\n";
    } catch (const std::exception &e) {
        std::cerr << "screen leaf continuations FAIL: " << e.what() << '\n'; return 1;
    }
}
