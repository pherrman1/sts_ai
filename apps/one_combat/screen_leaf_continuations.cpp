#include "screen_leaf_continuations.h"
#include "screen_leaf_snapshot.h"
#include "constants/CardPools.h"
#include "game/Game.h"
#include <limits>
#include <set>

namespace one_combat::screen_leaf {
namespace {
using namespace sts;

void fields(const Json &d, std::initializer_list<const char *> expected) {
    std::set<std::string> names;
    for (const auto *name : expected) names.insert(name);
    names.insert("kind");
    if (!d.is_object() || d.size() != names.size())
        throw std::runtime_error("screen leaf: continuation descriptor fields");
    for (const auto &name : names)
        if (!d.contains(name))
            throw std::runtime_error("screen leaf: missing continuation field " + name);
}

int integer(const Json &d, const char *name) {
    if (!d.at(name).is_number_integer())
        throw std::runtime_error("screen leaf: noninteger continuation field");
    if (d.at(name).is_number_unsigned()
        && d.at(name).get<std::uint64_t>() > static_cast<std::uint64_t>(std::numeric_limits<int>::max()))
        throw std::runtime_error("screen leaf: continuation integer overflow");
    const auto v = d.at(name).get<std::int64_t>();
    if (v < std::numeric_limits<int>::min() || v > std::numeric_limits<int>::max())
        throw std::runtime_error("screen leaf: continuation integer overflow");
    return static_cast<int>(v);
}

GameContextAction build(const Json &d, unsigned depth) {
    if (depth > 64) throw std::runtime_error("screen leaf: continuation nesting limit");
    if (d.is_null()) return {};
    if (!d.is_object() || !d.contains("kind") || !d.at("kind").is_string())
        throw std::runtime_error("screen leaf: malformed continuation descriptor");
    const auto kind = d.at("kind").get<std::string>();
    GameContextAction action;
    const auto returnToMap = [] (GameContext &gc) {
        gc.screenState = ScreenState::MAP_SCREEN;
        gc.regainControlAction = nullptr;
    };
    if (kind == "return_to_map") {
        fields(d, {}); action = returnToMap;
    } else if (kind == "set_map") {
        fields(d, {});
        action = [] (GameContext &gc) { gc.screenState = ScreenState::MAP_SCREEN; };
    } else if (kind == "after_battle") {
        fields(d, {}); action = [] (GameContext &gc) { gc.afterBattle(); };
    } else if (kind == "next_captured_act") {
        fields(d, {"act"}); const int act = integer(d, "act");
        if (act < 1 || act > 3) throw std::runtime_error("screen leaf: invalid captured act");
        action = [act] (GameContext &gc) { gc.transitionToAct(act + 1); };
    } else if (kind == "next_current_act") {
        fields(d, {}); action = [] (GameContext &gc) { gc.transitionToAct(gc.act + 1); };
    } else if (kind == "boss_treasure") {
        fields(d, {}); action = [] (GameContext &gc) { gc.enterBossTreasureRoom(); };
    } else if (kind == "neow_curse") {
        fields(d, {});
        action = [] (GameContext &gc) {
            const int roll = gc.cardRng.random(static_cast<int>(9));
            gc.deck.obtain(gc, curseCardPool[roll]);
            gc.screenState = ScreenState::MAP_SCREEN;
            gc.regainControlAction = importContinuation({{"kind", "return_to_map"}});
        };
    } else if (kind == "colosseum_first") {
        fields(d, {});
        action = [] (GameContext &gc) {
            gc.screenState = ScreenState::EVENT_SCREEN;
            gc.regainControlAction = importContinuation({{"kind", "return_to_map"}});
        };
    } else if (kind == "designer_upgrade") {
        fields(d, {});
        action = [returnToMap] (GameContext &gc) {
            gc.deck.upgradeRandomCards(gc.miscRng, 1); returnToMap(gc);
        };
    } else if (kind == "shop_relic_return") {
        fields(d, {});
        action = [] (GameContext &gc) {
            gc.screenState = ScreenState::SHOP_ROOM;
            gc.regainControlAction = importContinuation({{"kind", "set_map"}});
        };
    } else if (kind == "shop_remove_return") {
        fields(d, {"previous"}); const auto previous = build(d.at("previous"), depth + 1);
        action = [previous] (GameContext &gc) {
            gc.screenState = ScreenState::SHOP_ROOM; gc.regainControlAction = previous;
        };
    } else if (kind == "remaining_rewards") {
        fields(d, {"rewards", "previous"});
        const auto rewards = rewardsFromJson(d.at("rewards"));
        const auto previous = build(d.at("previous"), depth + 1);
        action = [rewards, previous] (GameContext &gc) {
            gc.openCombatRewardScreen(rewards); gc.regainControlAction = previous;
        };
    } else if (kind == "colosseum_rewards" || kind == "dead_adventurer_rewards"
               || kind == "masked_bandits_rewards" || kind == "mind_bloom_rewards"
               || kind == "mushroom_rewards") {
        if (kind == "colosseum_rewards") fields(d, {"gold", "rare", "uncommon"});
        else if (kind == "dead_adventurer_rewards") fields(d, {"gold", "addRelic", "relic"});
        else if (kind == "mind_bloom_rewards") fields(d, {"gold", "rare"});
        else fields(d, {"gold"});
        const int gold = integer(d, "gold");
        const int rare = d.contains("rare") ? integer(d, "rare") : 0;
        const int uncommon = d.contains("uncommon") ? integer(d, "uncommon") : 0;
        const int relic = d.contains("relic") ? integer(d, "relic") : 0;
        if (d.contains("addRelic") && !d.at("addRelic").is_boolean())
            throw std::runtime_error("screen leaf: invalid addRelic flag");
        const bool addRelic = d.value("addRelic", false);
        if (gold < 0 || (d.contains("rare") && (rare < 0 || rare >= int(RelicId::INVALID)))
            || (d.contains("uncommon") && (uncommon < 0 || uncommon >= int(RelicId::INVALID)))
            || (d.contains("relic") && (relic < 0 || relic > int(RelicId::INVALID)))
            || (addRelic && relic == int(RelicId::INVALID)))
            throw std::runtime_error("screen leaf: invalid reward continuation value");
        action = [kind, gold, rare, uncommon, relic, addRelic] (GameContext &gc) {
            Rewards reward; reward.addGold(gold);
            if (kind == "colosseum_rewards") {
                reward.addRelic(static_cast<RelicId>(rare));
                reward.addRelic(static_cast<RelicId>(uncommon));
            } else if (kind == "dead_adventurer_rewards") {
                if (addRelic) reward.addRelic(static_cast<RelicId>(relic));
                if (gc.hasRelic(RelicId::BLACK_STAR))
                    reward.addRelic(gc.returnNonCampfireRelic(returnRandomRelicTierElite(gc.relicRng)));
            } else if (kind == "masked_bandits_rewards") {
                // Current-main semantics intentionally differ from old producer:
                // duplicate Red Mask becomes Circlet, and potion rewards apply.
                reward.addRelic(gc.hasRelic(RelicId::RED_MASK) ? RelicId::CIRCLET : RelicId::RED_MASK);
            } else if (kind == "mind_bloom_rewards") reward.addRelic(static_cast<RelicId>(rare));
            else reward.addRelic(RelicId::ODD_MUSHROOM);
            if (kind == "dead_adventurer_rewards") {
                reward.addCardReward(gc.createCardReward(Room::EVENT)); gc.addPotionRewards(reward);
            } else {
                gc.addPotionRewards(reward); reward.addCardReward(gc.createCardReward(Room::EVENT));
            }
            gc.openCombatRewardScreen(reward);
            gc.regainControlAction = importContinuation({{"kind", "return_to_map"}});
        };
    } else throw std::runtime_error("screen leaf: unknown continuation " + kind);
    return tagContinuation(d, std::move(action));
}
}

sts::GameContextAction importContinuation(const Json &descriptor) {
    return build(descriptor, 0);
}
}
